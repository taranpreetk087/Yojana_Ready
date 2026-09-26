# -*- coding: utf-8 -*-
"""
Document Consistency Checker.

Uses real local OCR (pytesseract/Tesseract) -- not a mocked/fake response --
to read uploaded document photos, then compares key fields (name, DOB,
address) across documents using fuzzy string matching.

Honesty note (documented, not hidden): field *location* within the OCR text
is done via label-based parsing (looking for "Name:", "DOB:", "Address:"
etc.). This works reliably for structured documents like the sample set
this project ships with. Fully unstructured, real-world documents in every
possible layout would need a more advanced extraction model -- flagged as
future scope rather than pretended to be solved.
"""

import os
import re
import difflib
import platform
from datetime import date
from PIL import Image
import pytesseract
import pymupdf
# On Windows, Tesseract usually isn't added to PATH automatically, so point
# pytesseract at the default install location. On Linux/macOS (including
# hosting platforms like Render, which run Linux), Tesseract is installed
# via the system package manager and is already on PATH, so this is
# skipped -- hardcoding the Windows path here would break OCR completely
# once deployed.
if platform.system() == "Windows":
    _default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_default_win_path):
        pytesseract.pytesseract.tesseract_cmd = _default_win_path

FIELD_PATTERNS = {
    "name": r"(?:name)\s*[:\-]\s*(.+)",
    "dob": r"(?:dob|date of birth)\s*[:\-]\s*(.+)",
    "address": r"(?:address)\s*[:\-]\s*(.+)",
}

NAME_MATCH_THRESHOLD = 0.90
# Address: share of the (shorter) address's place-name words that must also
# appear in the other address. See compare_address() for the full rule.
ADDRESS_MATCH_THRESHOLD = 0.75


def run_ocr(file_path):
    """
    Run local Tesseract OCR on an uploaded document, returning raw extracted
    text. Accepts image files (PNG/JPG) directly, and PDFs by first
    rendering the first page to an image (at 2x resolution for sharper
    text) -- the OCR step itself works the same way for both.

    Returns an empty string on a corrupt/unreadable/encrypted file instead
    of raising, so a bad upload shows as "unreadable" in the report like a
    blurry photo would, rather than crashing the page.
    """
    try:
        if file_path.lower().endswith(".pdf"):
            pdf = pymupdf.open(file_path)
            page = pdf.load_page(0)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            pdf.close()
        else:
            img = Image.open(file_path)
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def extract_fields(image_path):
    """
    Extract name/dob/address from a document image using label-based parsing
    over the raw OCR text. Returns a dict; a field is None if not found,
    which is treated as 'unreadable' for that field downstream.
    """
    text = run_ocr(image_path)
    fields = {"raw_text": text, "readable": bool(text.strip())}

    lines = text.replace("\r", "").split("\n")
    joined = "\n".join(l.strip() for l in lines if l.strip())

    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, joined, re.IGNORECASE)
        fields[field] = match.group(1).strip() if match else None

    return fields


def _normalize(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _similarity(a, b):
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


# ---------------------------------------------------------------------------
# Date of birth: compare the actual date, not the text it was written in.
# "15-08-2004", "15/08/2004", "15.08.2004" and "15 Aug 2004" are the same
# date on different documents and must not be reported as a mismatch.
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _make_date(y, m, d):
    try:
        if not (1900 <= y <= date.today().year):
            return None
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(value):
    """Parse the date formats seen on Indian documents (day first). None if unsure."""
    if not value:
        return None
    t = value.strip().lower()

    m = re.search(r"\b(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\b", t)      # 2004-08-15
    if m:
        return _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"\b(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{4})\b", t)  # 15-08-2004
    if m:
        return _make_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([a-z]{3,9})[\s\-/.,]*(\d{4})\b", t)  # 15 Aug 2004
    if m and m.group(2) in _MONTHS:
        return _make_date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))

    m = re.search(r"\b([a-z]{3,9})[\s\-/.,]*(\d{1,2})(?:st|nd|rd|th)?[\s,\-/.]*(\d{4})\b", t)  # August 15, 2004
    if m and m.group(1) in _MONTHS:
        return _make_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))

    return None


def compare_dob(a, b):
    """Returns (matches: bool, reason: str)."""
    da, db = parse_date(a), parse_date(b)
    if da and db:
        if da == db:
            return True, ""
        return False, f"different dates: {da.strftime('%d %b %Y')} vs {db.strftime('%d %b %Y')}"
    # At least one date couldn't be parsed: fall back to comparing the raw
    # characters, ignoring separators and case, so we never call two
    # identical strings a mismatch.
    strip = lambda v: re.sub(r"[^a-z0-9]", "", (v or "").lower())
    return (strip(a) == strip(b)), ""


# ---------------------------------------------------------------------------
# Address: compare the parts that actually matter -- PIN code, house / flat /
# sector numbers, and place names -- instead of one loose whole-string score.
# A whole-string score let a different PIN code or a different city slip
# through as a "match", which is exactly what causes real rejections.
# ---------------------------------------------------------------------------

_ADDR_ABBREVIATIONS = [
    (r"\bh\.?\s*no\.?|\bhno\b|\bhouse\s*(?:no\.?|number)", "house"),
    (r"\bflat\s*(?:no\.?|number)", "flat"),
    (r"\bsec\.?(?=\s|\d|$)", "sector"),
    (r"\bopp\.?(?=\s|$)", "opposite"),
    (r"\bnr\.?(?=\s|$)", "near"),
    (r"\bapts?\.?(?=\s|$)", "apartment"),
    (r"\brd\.?(?=\s|$)", "road"),
    (r"\bblk\.?(?=\s|$)", "block"),
    (r"\bdist\.?(?=\s|$)", "district"),
    (r"\bvill\.?(?=\s|$)", "village"),
]

_CITY_ALIASES = {
    "new delhi": "delhi", "bangalore": "bengaluru", "bombay": "mumbai",
    "madras": "chennai", "calcutta": "kolkata", "gurgaon": "gurugram",
    "allahabad": "prayagraj", "trivandrum": "thiruvananthapuram",
    "baroda": "vadodara", "poona": "pune",
}

# Words that describe the *shape* of an address rather than the place itself.
_ADDR_GENERIC = {
    "house", "flat", "sector", "block", "phase", "road", "street", "lane", "near",
    "opposite", "apartment", "apartments", "floor", "plot", "no", "number", "the",
    "of", "and", "india", "village", "district", "post", "office", "po", "ps",
}

_PIN_RE = re.compile(r"\b([1-9]\d{2})\s?(\d{3})\b")


def _extract_pin(text):
    matches = _PIN_RE.findall(text or "")
    return "".join(matches[-1]) if matches else None


def _address_parts(text):
    """Return (pin, number_tokens, place_tokens) for an address string."""
    raw = (text or "").lower()
    pin = _extract_pin(raw)
    if pin:
        raw = _PIN_RE.sub(" ", raw)
    for pattern, replacement in _ADDR_ABBREVIATIONS:
        raw = re.sub(pattern, replacement, raw)
    raw = re.sub(r"[^\w\s]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    for old, new in _CITY_ALIASES.items():
        raw = re.sub(rf"\b{old}\b", new, raw)
    tokens = raw.split()
    numbers = {t for t in tokens if any(ch.isdigit() for ch in t)}
    places = {t for t in tokens if t.isalpha() and len(t) > 1 and t not in _ADDR_GENERIC}
    return pin, numbers, places


def _fuzzy_contains(token, pool):
    if token in pool:
        return True
    if len(token) < 5:  # short words must match exactly; one wrong letter changes the place
        return False
    return any(difflib.SequenceMatcher(None, token, other).ratio() >= 0.8 for other in pool)


def compare_address(a, b):
    """
    Returns (matches: bool, reason: str). Rules, in order:
      1. Both show a PIN code and they differ            -> mismatch
      2. House/flat/sector numbers conflict (neither set
         is contained in the other)                      -> mismatch
      3. Place names: at least ADDRESS_MATCH_THRESHOLD of
         the shorter address's place words appear in the
         other (typos tolerated)                         -> otherwise mismatch
    Abbreviations (H.No / House No, Sec / Sector) and old-new city names
    (Bombay / Mumbai, New Delhi / Delhi) are normalised first.
    """
    pin_a, nums_a, places_a = _address_parts(a)
    pin_b, nums_b, places_b = _address_parts(b)

    if pin_a and pin_b and pin_a != pin_b:
        return False, f"PIN codes differ: {pin_a} vs {pin_b}"

    if nums_a and nums_b and not (nums_a <= nums_b or nums_b <= nums_a):
        return False, "house / flat / sector numbers differ"

    if not places_a or not places_b:
        # Nothing but numbers/generic words to compare by place; fall back to plain similarity.
        return (_similarity(a, b) >= 0.85), ""

    small, large = (places_a, places_b) if len(places_a) <= len(places_b) else (places_b, places_a)
    shared = sum(1 for t in small if _fuzzy_contains(t, large))
    if shared / len(small) < ADDRESS_MATCH_THRESHOLD:
        return False, "city / area names differ"
    return True, ""


def _fields_match(field, a, b):
    """Returns (matches, reason) using the right comparison for each field."""
    if field == "dob":
        return compare_dob(a, b)
    if field == "address":
        return compare_address(a, b)
    return (_similarity(a, b) >= NAME_MATCH_THRESHOLD), ""


def overall_status(results):
    """A single summary status for the whole report."""
    if any(r["status"] == "unreadable" for r in results):
        return "unreadable"
    if any(r["status"] == "mismatch" for r in results):
        return "mismatch"
    return "matched"


def readiness_score(results):
    """
    'X of Y checks passed' -- gives a concrete sense of progress instead of
    a flat pass/fail, so a user with one small issue among several fields
    isn't left with the same blank feeling as someone with everything wrong.
    """
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "matched")
    return {"passed": passed, "total": total, "percent": round(100 * passed / total) if total else 0}


def compare_multi(all_fields, labels):
    """
    Compare 2-4 documents pairwise against the FIRST document (treated as
    the anchor/reference -- typically Aadhaar, since most schemes treat it
    as the base identity proof). Returns one combined report per field,
    showing every document's value side by side, so a user checking 3-4
    documents at once doesn't have to run several separate pairwise checks.
    """
    if len(all_fields) < 2:
        return []

    anchor = all_fields[0]
    anchor_label = labels[0]
    results = []

    for field, title in (
        ("name", "Name"),
        ("dob", "Date of Birth"),
        ("address", "Address"),
    ):
        anchor_value = anchor.get(field)
        per_doc_values = [{"label": anchor_label, "value": anchor_value or "(not found)"}]
        status = "matched"
        explanations = []

        for fields, label in zip(all_fields[1:], labels[1:]):
            value = fields.get(field)
            per_doc_values.append({"label": label, "value": value or "(not found)"})

            if not anchor_value or not value:
                status = "unreadable" if status != "mismatch" else status
                explanations.append(f"{label}'s {title.lower()} could not be clearly read.")
                continue

            ok, reason = _fields_match(field, anchor_value, value)
            if not ok:
                status = "mismatch"
                detail = f" ({reason})" if reason else ""
                explanations.append(f"{label}'s {title.lower()} (\"{value}\") does not match {anchor_label}'s (\"{anchor_value}\"){detail}.")

        mismatch_type_map = {"Name": "name", "Date of Birth": "dob", "Address": "address"}
        results.append({
            "field": title,
            "status": status,
            "doc_values": per_doc_values,
            "explanation": " ".join(explanations) if explanations else f"{title} matches across all documents.",
            "mismatch_type": mismatch_type_map[title] if status == "mismatch" else ("unreadable" if status == "unreadable" else None),
        })

    return results


def sequencing_advice(results, anchor_label):
    """
    Simple rule: if the anchor document (typically Aadhaar, since most other
    government documents are corrected using it as base proof) has any
    mismatch, tell the user to fix that one first -- fixing a dependent
    document before its source document just means redoing it again.
    """
    anchor_has_mismatch = any(
        r["status"] == "mismatch" and any(v["label"] == anchor_label for v in r.get("doc_values", []))
        for r in results
    )
    if anchor_has_mismatch:
        return (
            f"Fix {anchor_label} first. Most other documents (income certificate, scholarship forms, "
            f"bank records) are corrected using {anchor_label} as the base proof -- fixing another "
            f"document before this one usually means redoing it again."
        )
    mismatches = [r for r in results if r["status"] == "mismatch"]
    if mismatches:
        return f"Fix the {mismatches[0]['field'].lower()} mismatch first, then recheck the rest."
    return None
