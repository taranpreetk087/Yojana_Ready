"""
Yojana Ready, Document Readiness & Rejection Risk Checker
Smart India Hackathon 2026 project, Team "Tech Maniacs".

A citizen-facing platform that goes beyond scheme eligibility checking to
catch document errors before submission and to help a citizen recover
after a rejection of an application
"""

import os
import io
import hmac
import time
import uuid
import logging
import secrets
import tempfile
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, Response, abort
from werkzeug.exceptions import HTTPException

from models.db import get_all_schemes, get_scheme, ensure_schemes_db, USING_PG
from models.eligibility import evaluate
from models.document_check import extract_fields, compare_multi, overall_status, readiness_score, sequencing_advice
from models.chatbot import get_response as chatbot_response
from models.rejection import decode_rejection, draft_grievance, CPGRAMS_URL
from models.auth import init_auth_tables, create_user, verify_login
from models.casefile_store import save_case_file, load_case_file
from data.schemes_data import OCCUPATION_LABELS, CATEGORY_LABELS, EMPLOYMENT_LABELS, STATES, MISMATCH_GUIDE, DOCUMENT_CHECK_SCHEMES

log = logging.getLogger("yojana")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(BASE_DIR, "static", "img", "samples")

# Only these bundled demo files can be loaded through the "sample document"
# picker. Never build a file path from raw form input.
SAMPLE_FILES = {
    f for f in os.listdir(SAMPLE_DIR)
    if f.lower().endswith((".png", ".jpg", ".jpeg", ".pdf"))
}

ensure_schemes_db()
try:
    init_auth_tables()
except Exception:  # database unreachable at boot: guests still work, accounts retry on first use
    log.exception("Could not initialise the accounts database at startup")
log.warning("User accounts stored in: %s", "PostgreSQL (DATABASE_URL)" if USING_PG else "local SQLite file (set DATABASE_URL for persistent accounts)")

app = Flask(__name__)

_DEFAULT_SECRET = "yojana-ready-demo-secret-key-change-in-production"
app.secret_key = os.environ.get("SECRET_KEY") or _DEFAULT_SECRET
if app.secret_key == _DEFAULT_SECRET:
    log.warning(
        "SECRET_KEY is not set: using the public default key from the source code. "
        "Anyone can forge login sessions with it. Set a long random SECRET_KEY "
        "environment variable (on Render: Environment tab) before real users sign up."
    )

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER"))  # Render serves over HTTPS

ALLOWED_EXT = {"png", "jpg", "jpeg", "pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ---------------------------------------------------------------- security helpers

def _csrf_token():
    """One random token per browser session, embedded in every form."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


@app.before_request
def _csrf_protect():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
        abort(400, description="Your session expired or the form was opened in another tab. Please go back, reload the page and try again.")


def _safe_local_path(target, fallback):
    """Only ever redirect to a path on this site, never to another domain."""
    if not target:
        return fallback
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        # A full URL is fine only if it points at this same host (e.g. the Referer header).
        if parsed.netloc != request.host:
            return fallback
        target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    if not target.startswith("/") or target.startswith("//") or target.startswith("/\\"):
        return fallback
    return target


def _parse_int(value, low, high):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


# Login throttle: 5 failed attempts per username+IP per 10 minutes. Kept in
# memory per worker, which is enough to stop casual password guessing.
_LOGIN_FAILS = {}
_LOGIN_MAX_FAILS, _LOGIN_WINDOW = 5, 600


def _login_key(username):
    ip = request.access_route[0] if request.access_route else (request.remote_addr or "")
    return f"{username.lower()}|{ip}"


def _login_blocked(key):
    now = time.time()
    recent = [t for t in _LOGIN_FAILS.get(key, []) if now - t < _LOGIN_WINDOW]
    if recent:
        _LOGIN_FAILS[key] = recent
    else:
        _LOGIN_FAILS.pop(key, None)
    return len(recent) >= _LOGIN_MAX_FAILS


def _login_failed(key):
    if len(_LOGIN_FAILS) > 5000:  # never let this grow without bound
        _LOGIN_FAILS.clear()
    _LOGIN_FAILS.setdefault(key, []).append(time.time())


def update_case_file(**kwargs):
    """
    Ties eligibility -> document check -> rejection recovery into one
    continuous thread instead of three disconnected tools, something
    neither MyScheme nor UMANG can offer, since neither has a document or
    rejection module to connect anything to in the first place.

    Guests get this via the browser session (as before). Logged-in users
    additionally get it persisted to the database, so it survives across
    logins and devices, not just the current browser session.
    """
    case = session.get("case_file", {})
    case.update(kwargs)
    case["updated_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    session["case_file"] = case
    if session.get("user_id"):
        try:
            save_case_file(session["user_id"], case)
        except Exception:
            # The browser-session copy above is already saved, so the user's
            # flow continues even if the database is briefly unreachable.
            log.exception("Could not save case file to the database")


@app.context_processor
def inject_globals():
    user = None
    if session.get("user_id"):
        user = {"id": session["user_id"], "username": session.get("username", "")}
    return {"lang": session.get("lang", "en"), "current_user": user, "csrf_token": _csrf_token}


@app.route("/set-language/<code>")
def set_language(code):
    if code in ("en", "hi"):
        session["lang"] = code
    return redirect(_safe_local_path(request.referrer, url_for("landing")))


@app.route("/")
def landing():
    return render_template("landing.html", scheme_count=len(get_all_schemes()))


# Authentication

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not password:
            return render_template("register.html", error="Please fill in both fields.")
        if password != confirm:
            return render_template("register.html", error="Passwords do not match.")
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters.")

        try:
            user_id = create_user(username, password)
        except Exception:
            log.exception("Registration failed: database error")
            return render_template("register.html", error="Accounts are temporarily unavailable. You can still use every tool as a guest.")
        if user_id is None:
            return render_template("register.html", error="That username is already taken.")

        session["user_id"] = user_id
        session["username"] = username
        return redirect(url_for("landing"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_local_path(request.values.get("next"), url_for("landing"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = _login_key(username)
        if _login_blocked(key):
            return render_template("login.html", next_url=next_url, error="Too many failed attempts. Please wait a few minutes and try again.")
        try:
            user = verify_login(username, password)
        except Exception:
            log.exception("Login failed: database error")
            return render_template("login.html", next_url=next_url, error="Accounts are temporarily unavailable. You can still use every tool as a guest.")
        if not user:
            _login_failed(key)
            return render_template("login.html", next_url=next_url, error="Incorrect username or password.")

        _LOGIN_FAILS.pop(key, None)
        session["user_id"] = user["id"]
        session["username"] = user["username"]

        # Load this user's persisted case file into the session so returning users see their prior progress, not a blank state.
        try:
            session["case_file"] = load_case_file(user["id"])
        except Exception:
            log.exception("Could not load saved case file")
            session["case_file"] = {}

        return redirect(next_url)

    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# Eligibility Checker

def _render_questionnaire(error=None, prev=None):
    return render_template(
        "questionnaire.html",
        occupations=OCCUPATION_LABELS,
        employment_types=EMPLOYMENT_LABELS,
        categories={c: l for c, l in CATEGORY_LABELS.items() if c != "general"},
        states=STATES,
        error=error, prev=prev or {},
        journey_stage=1,
    )


@app.route("/eligibility", methods=["GET", "POST"])
def eligibility_questionnaire():
    if request.method == "POST":
        form = request.form
        age = _parse_int(form.get("age"), 0, 120)
        income = _parse_int(form.get("income"), 0, 10**10)
        prev = {
            "age": form.get("age", ""), "income": form.get("income", ""),
            "gender": form.get("gender", ""), "state": form.get("state", ""),
            "occupation": form.get("occupation", ""), "employment": form.get("employment", ""),
            "categories": form.getlist("categories"),
        }
        if age is None:
            return _render_questionnaire("Please enter your age as a whole number between 0 and 120.", prev)
        if income is None:
            return _render_questionnaire("Please enter your yearly family income in rupees as a whole number (0 or more).", prev)
        if form.get("gender") not in ("male", "female", "other"):
            return _render_questionnaire("Please choose an option for gender.", prev)
        if form.get("state") not in STATES:
            return _render_questionnaire("Please choose your state or union territory from the list.", prev)
        if form.get("occupation") not in OCCUPATION_LABELS:
            return _render_questionnaire("Please choose your occupation from the list.", prev)
        if form.get("employment") not in EMPLOYMENT_LABELS:
            return _render_questionnaire("Please choose how you work from the list.", prev)

        session["answers"] = {
            "age": age,
            "income": income,
            "gender": form["gender"],
            "state": form["state"],
            "occupation": form["occupation"],
            "employment": form["employment"],
            # Any number of categories can apply at once; an empty list means General.
            "categories": [c for c in form.getlist("categories") if c in CATEGORY_LABELS and c != "general"],
        }
        return redirect(url_for("eligibility_results"))
    return _render_questionnaire()


@app.route("/eligibility/results")
def eligibility_results():
    answers = session.get("answers")
    if not answers:
        return redirect(url_for("eligibility_questionnaire"))
    result = evaluate(answers)
    update_case_file(
        eligibility_done=True,
        matched_count=len(result["matched"]),
        matched_names=[s["name"] for s in result["matched"][:5]],
    )
    state_filtering_active = any(s["states"] != ["ALL"] for s in get_all_schemes())
    return render_template("results.html", result=result, answers=answers,
                           state_filtering_active=state_filtering_active, journey_stage=1)
@app.route("/scheme/<scheme_id>")
def scheme_detail(scheme_id):
    scheme = get_scheme(scheme_id)
    if not scheme:
        return redirect(url_for("landing"))
    return render_template("scheme_detail.html", scheme=scheme, journey_stage=1)

# Document Consistency Checker 
# Generic fallback when no scheme is selected, or the selected scheme has no
# entry in DOCUMENT_CHECK_SCHEMES: the same 4 slots the checker always used.
_GENERIC_DOC_SLOTS = [
    ("Aadhaar Card", True),
    ("Income Certificate", True),
    ("Caste Certificate", False),
    ("Bank Passbook", False),
]


def _doc_slots_for(scheme_id):
    """(scheme, doc_slots) for the upload form. doc_slots is a list of
    (slot_number, default_label, required) tuples, always 4 long so the
    template always has 4 upload slots to render (docs 3-4 optional)."""
    scheme = get_scheme(scheme_id) if scheme_id else None
    slots = DOCUMENT_CHECK_SCHEMES.get(scheme_id) if scheme else None
    slots = list(slots) if slots else list(_GENERIC_DOC_SLOTS)
    while len(slots) < 4:
        slots.append((f"Document {len(slots) + 1}", False))
    return scheme, [(i + 1, label, required) for i, (label, required) in enumerate(slots[:4])]


@app.route("/documents/upload", methods=["GET", "POST"])
def document_upload():
    if request.method == "POST":
        scheme_id = request.form.get("scheme_id", "")
        scheme, doc_slots = _doc_slots_for(scheme_id)
        doc_labels, doc_specs = [], []  # spec = ("upload", FileStorage, ext) or ("sample", filename)

        for key in ("doc1", "doc2", "doc3", "doc4"):
            file = request.files.get(key)
            label = request.form.get(f"{key}_label", "").strip()[:60]
            sample = request.form.get(f"{key}_sample", "")
            default_label = key.replace("doc", "Document ")

            if file and file.filename:
                if not allowed_file(file.filename):
                    return render_template("upload.html", error="Only JPG, PNG or PDF files can be checked.",
                                           scheme=scheme, doc_slots=doc_slots, schemes=get_all_schemes(), journey_stage=2)
                doc_specs.append(("upload", file, file.filename.rsplit(".", 1)[1].lower()))
                doc_labels.append(label or default_label)
            elif sample in SAMPLE_FILES:
                doc_specs.append(("sample", sample, None))
                doc_labels.append(label or default_label)

        if len(doc_specs) < 2:
            return render_template("upload.html", error="Please provide at least 2 documents (upload or choose a sample).",
                                   scheme=scheme, doc_slots=doc_slots, schemes=get_all_schemes(), journey_stage=2)

        # Uploads are written to a private temporary folder (never under static/,
        # so they are never publicly downloadable), read once by the OCR step,
        # and the whole folder is deleted as soon as this block ends -- even if
        # OCR fails. The name on disk is random; the user's filename is never used.
        all_fields = []
        with tempfile.TemporaryDirectory(prefix="yojana_") as tmp_dir:
            for kind, item, ext in doc_specs:
                if kind == "upload":
                    path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.{ext}")
                    item.save(path)
                else:
                    path = os.path.join(SAMPLE_DIR, item)
                all_fields.append(extract_fields(path))

        report = compare_multi(all_fields, doc_labels)
        status = overall_status(report)
        score = readiness_score(report)
        sequencing = sequencing_advice(report, doc_labels[0])

        session["last_report"] = {
            "report": report, "status": status, "labels": doc_labels,
            "score": score, "sequencing": sequencing,
            "scheme_name": scheme["name"] if scheme else None,
        }
        update_case_file(
            documents_done=True, documents_status=status,
            documents_score=f"{score['passed']}/{score['total']}",
        )
        return redirect(url_for("document_report"))

    scheme, doc_slots = _doc_slots_for(request.args.get("scheme_id", ""))
    return render_template("upload.html", scheme=scheme, doc_slots=doc_slots, schemes=get_all_schemes(), journey_stage=2)


@app.route("/documents/report")
def document_report():
    data = session.get("last_report")
    if not data:
        return redirect(url_for("document_upload"))
    return render_template("report.html", **data, mismatch_guide=MISMATCH_GUIDE, journey_stage=2)


# Post-Rejection Recovery (the core differentiator) Our main and unique feature

@app.route("/rejection", methods=["GET", "POST"])
def rejection_decoder():
    if request.method == "POST":
        text = request.form.get("rejection_text", "")
        scheme_id = request.form.get("scheme_id", "")
        category = decode_rejection(text)
        session["last_rejection"] = {
            "category_id": category["id"],
            "title": category["title"],
            "explanation": category["explanation"],
            "steps": category["steps"],
            "recommend_document_check": category.get("recommend_document_check", False),
            "scheme_id": scheme_id,
            "scheme_name": get_scheme(scheme_id)["name"] if scheme_id and get_scheme(scheme_id) else "",
        }
        update_case_file(rejection_done=True, rejection_title=category["title"])
        return redirect(url_for("rejection_result"))
    return render_template("rejection.html", schemes=get_all_schemes(), journey_stage=3)


@app.route("/rejection/result")
def rejection_result():
    data = session.get("last_rejection")
    if not data:
        return redirect(url_for("rejection_decoder"))
    return render_template("rejection_result.html", **data, journey_stage=3)


@app.route("/rejection/grievance", methods=["GET", "POST"])
def grievance_assistant():
    draft = None
    if request.method == "POST":
        draft = draft_grievance(
            name=request.form.get("name", ""),
            scheme_name=request.form.get("scheme_name", ""),
            application_ref=request.form.get("application_ref", ""),
            reason_text=request.form.get("reason_text", ""),
        )
    prefill_scheme = session.get("last_rejection", {}).get("scheme_name", "")
    return render_template(
        "grievance.html", draft=draft, prefill_scheme=prefill_scheme,
        cpgrams_url=CPGRAMS_URL, journey_stage=3,
    )


# Chatbot API
@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(silent=True)
    message = payload.get("message", "") if isinstance(payload, dict) else request.form.get("message", "")
    if not isinstance(message, str):
        message = ""
    reply = chatbot_response(message[:500])
    return jsonify({"reply": reply})


# Case File 
@app.route("/case-file")
def case_file_view():
    case = session.get("case_file", {})
    return render_template("case_file.html", case=case)


@app.route("/case-file/download")
def case_file_download():
    case = session.get("case_file", {})
    lines = [
        "YOJANA READY -- APPLICATION CASE FILE SUMMARY",
        f"Generated: {case.get('updated_at', datetime.now().strftime('%d %b %Y, %I:%M %p'))}",
        "=" * 50, "",
    ]
    if case.get("eligibility_done"):
        lines += [
            "ELIGIBILITY CHECK", "-" * 20,
            f"Schemes matched: {case.get('matched_count', 0)}",
        ]
        for name in case.get("matched_names", []):
            lines.append(f"  - {name}")
        lines.append("")
    if case.get("documents_done"):
        lines += [
            "DOCUMENT CONSISTENCY CHECK", "-" * 20,
            f"Result: {case.get('documents_status', 'unknown').upper()}",
            f"Checks passed: {case.get('documents_score', 'N/A')}", "",
        ]
    if case.get("rejection_done"):
        lines += [
            "REJECTION RECOVERY", "-" * 20,
            f"Decoded reason: {case.get('rejection_title', 'N/A')}", "",
        ]
    if not any(case.get(k) for k in ("eligibility_done", "documents_done", "rejection_done")):
        lines.append("No steps completed yet. Use the Eligibility Checker, Document Checker, or Rejection Decoder first.")

    lines.append("Note: this summary is for your personal reference (e.g. to carry to a Common")
    lines.append("Service Centre). It is not an official government document.")

    buffer = io.BytesIO("\n".join(lines).encode("utf-8"))
    return Response(
        buffer.getvalue(), mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=yojana_ready_case_file.txt"},
    )


# Error pages

@app.errorhandler(413)
def too_large(_e):
    if request.endpoint == "document_upload":
        _, doc_slots = _doc_slots_for(None)  # form body may be unavailable once the size limit is hit
        return render_template("upload.html", error="That file is too large. Please upload files under 8 MB each (a phone photo can be shrunk or saved as a PDF).",
                               scheme=None, doc_slots=doc_slots, schemes=get_all_schemes(), journey_stage=2), 413
    return render_template("error.html", code=413, message="That upload is too large."), 413


@app.errorhandler(HTTPException)
def http_error(e):
    return render_template("error.html", code=e.code, message=e.description), e.code


@app.errorhandler(Exception)
def unexpected_error(e):
    log.exception("Unhandled error")
    return render_template("error.html", code=500, message="Something went wrong on our side. Please try again in a moment."), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
