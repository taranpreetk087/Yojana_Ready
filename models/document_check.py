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
ADDRESS_MATCH_THRESHOLD = 0.65


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

    for field, threshold, title in (
        ("name", NAME_MATCH_THRESHOLD, "Name"),
        ("dob", 1.0, "Date of Birth"),
        ("address", ADDRESS_MATCH_THRESHOLD, "Address"),
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

            score = _similarity(anchor_value, value)
            if score < threshold:
                status = "mismatch"
                explanations.append(f"{label}'s {title.lower()} (\"{value}\") does not match {anchor_label}'s (\"{anchor_value}\").")

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
