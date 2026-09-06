# -*- coding: utf-8 -*-
"""
Yojana Ready -- Document Readiness & Rejection Risk Checker
Smart India Hackathon 2026 project.

A citizen-facing platform that goes beyond scheme eligibility checking to
catch document errors before submission, and to help a citizen recover
after a rejection -- the two stages no existing government portal
currently covers.
"""

import os
import io
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, Response

from models.db import get_all_schemes, get_scheme, init_db, DB_PATH
from models.eligibility import evaluate
from models.document_check import extract_fields, compare_multi, overall_status, readiness_score, sequencing_advice
from models.chatbot import get_response as chatbot_response
from models.rejection import decode_rejection, draft_grievance, CPGRAMS_URL
from models.auth import init_auth_tables, create_user, verify_login
from models.casefile_store import save_case_file, load_case_file
from data.schemes_data import OCCUPATION_LABELS, CATEGORY_LABELS, MISMATCH_GUIDE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

if not os.path.exists(DB_PATH):
    init_db()
init_auth_tables()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "yojana-ready-demo-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap

ALLOWED_EXT = {"png", "jpg", "jpeg", "pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def update_case_file(**kwargs):
    """
    Ties eligibility -> document check -> rejection recovery into one
    continuous thread instead of three disconnected tools -- something
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
        save_case_file(session["user_id"], case)


@app.context_processor
def inject_globals():
    user = None
    if session.get("user_id"):
        user = {"id": session["user_id"], "username": session.get("username", "")}
    return {"lang": session.get("lang", "en"), "current_user": user}


@app.route("/set-language/<code>")
def set_language(code):
    if code in ("en", "hi"):
        session["lang"] = code
    return redirect(request.referrer or url_for("landing"))


@app.route("/")
def landing():
    return render_template("landing.html", scheme_count=len(get_all_schemes()))


# ---------------- Authentication ----------------

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

        user_id = create_user(username, password)
        if user_id is None:
            return render_template("register.html", error="That username is already taken.")

        session["user_id"] = user_id
        session["username"] = username
        return redirect(url_for("landing"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = verify_login(username, password)
        if not user:
            return render_template("login.html", error="Incorrect username or password.")

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        # Load this user's persisted case file into the session, so
        # returning users see their prior progress, not a blank state.
        session["case_file"] = load_case_file(user["id"])

        next_url = request.args.get("next") or url_for("landing")
        return redirect(next_url)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ---------------- Eligibility Checker ----------------

@app.route("/eligibility", methods=["GET", "POST"])
def eligibility_questionnaire():
    if request.method == "POST":
        session["answers"] = {
            "age": int(request.form["age"]),
            "income": int(request.form["income"]),
            "gender": request.form["gender"],
            "occupation": request.form["occupation"],
            "category": request.form["category"],
        }
        return redirect(url_for("eligibility_results"))
    return render_template(
        "questionnaire.html",
        occupations=OCCUPATION_LABELS,
        categories=CATEGORY_LABELS,
        journey_stage=1,
    )


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
    return render_template("results.html", result=result, answers=answers, journey_stage=1)


@app.route("/scheme/<scheme_id>")
def scheme_detail(scheme_id):
    scheme = get_scheme(scheme_id)
    if not scheme:
        return redirect(url_for("landing"))
    return render_template("scheme_detail.html", scheme=scheme, journey_stage=1)


# ---------------- Document Consistency Checker ----------------

@app.route("/documents/upload", methods=["GET", "POST"])
def document_upload():
    if request.method == "POST":
        doc_paths, doc_labels = [], []
        for key in ("doc1", "doc2", "doc3", "doc4"):
            file = request.files.get(key)
            label = request.form.get(f"{key}_label", "").strip()
            sample = request.form.get(f"{key}_sample", "")

            if file and file.filename and allowed_file(file.filename):
                safe_name = f"{key}_{os.urandom(4).hex()}_{file.filename}"
                path = os.path.join(UPLOAD_DIR, safe_name)
                file.save(path)
                doc_paths.append(path)
                doc_labels.append(label or key.replace("doc", "Document "))
            elif sample:
                doc_paths.append(os.path.join(BASE_DIR, "static", "img", "samples", sample))
                doc_labels.append(label or key.replace("doc", "Document "))

        if len(doc_paths) < 2:
            return render_template("upload.html", error="Please provide at least 2 documents (upload or choose a sample).", journey_stage=2)

        all_fields = [extract_fields(p) for p in doc_paths]
        report = compare_multi(all_fields, doc_labels)
        status = overall_status(report)
        score = readiness_score(report)
        sequencing = sequencing_advice(report, doc_labels[0])

        session["last_report"] = {
            "report": report, "status": status, "labels": doc_labels,
            "score": score, "sequencing": sequencing,
        }
        update_case_file(
            documents_done=True, documents_status=status,
            documents_score=f"{score['passed']}/{score['total']}",
        )
        return redirect(url_for("document_report"))

    return render_template("upload.html", journey_stage=2)


@app.route("/documents/report")
def document_report():
    data = session.get("last_report")
    if not data:
        return redirect(url_for("document_upload"))
    return render_template("report.html", **data, mismatch_guide=MISMATCH_GUIDE, journey_stage=2)


# ---------------- Post-Rejection Recovery (the core differentiator) ----------------

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


# ---------------- Chatbot API ----------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    message = request.json.get("message", "") if request.is_json else request.form.get("message", "")
    reply = chatbot_response(message)
    return jsonify({"reply": reply})


# ---------------- Case File (ties every module into one thread) ----------------

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
