# -*- coding: utf-8 -*-
"""
Post-Rejection Recovery -- Module 4 of the blueprint, and the actual core
differentiator of this project. Nothing else in the current government
digital ecosystem helps a citizen after a rejection notice lands; this is
the piece that makes this project more than "a smaller MyScheme."

Deliberately rule-based (keyword/pattern matching over the pasted rejection
text), not an LLM call -- for the same reason as the chatbot: wrong guidance
at this stage could genuinely mislead someone about a real government
process, so every explanation traces back to a stated rule, never a
generated guess.
"""

import re
from data.schemes_data import MISMATCH_GUIDE

CPGRAMS_URL = "https://pgportal.gov.in"

# Each category: trigger keywords -> (plain-language explanation, fix-it steps)
REJECTION_CATEGORIES = [
    {
        "id": "document_mismatch",
        "keywords": ["mismatch", "does not match", "discrepancy", "inconsistent", "does not tally"],
        "title": "Your documents likely had a mismatch",
        "explanation": (
            "This usually means a detail on one document (often your name, date of birth, or address) "
            "did not exactly match the same detail on another document you submitted."
        ),
        "steps": MISMATCH_GUIDE["name"]["steps"],
        "recommend_document_check": True,
    },
    {
        "id": "missing_document",
        "keywords": ["missing", "not submitted", "not attached", "incomplete document", "document not found", "not uploaded", "incomplete"],
        "title": "A required document was missing or unclear",
        "explanation": (
            "The application was likely rejected because one of the required documents was not "
            "submitted, or the uploaded copy could not be read/verified."
        ),
        "steps": MISMATCH_GUIDE["unreadable"]["steps"] + [
            "Re-check the scheme's full document checklist and make sure every required document was actually attached, not just uploaded but skipped by mistake.",
        ],
        "recommend_document_check": True,
    },
    {
        "id": "not_eligible",
        "keywords": ["not eligible", "does not meet", "ineligible", "criteria not met", "eligibility criteria"],
        "title": "You were marked as not meeting the eligibility criteria",
        "explanation": (
            "This means the department's records show you don't meet one of the scheme's rules "
            "(for example, age, income, or category) -- not a document problem."
        ),
        "steps": [
            "Re-check the scheme's exact eligibility criteria (age, income, category, occupation) against your own details.",
            "If you believe your details were recorded incorrectly by the department, this is worth raising as a grievance rather than a simple document fix.",
            "If a genuine criterion is not met, unfortunately this scheme may not be reapplicable -- check the Eligibility Checker on this site for other schemes you may qualify for instead.",
        ],
        "recommend_document_check": False,
    },
    {
        "id": "income_exceeds",
        "keywords": ["income exceeds", "income limit", "above the prescribed", "income criteria"],
        "title": "Your stated income was recorded as above the scheme's limit",
        "explanation": "The department's records show an income figure above what this scheme allows.",
        "steps": [
            "Double check the income certificate you submitted shows the correct, current figure.",
            "If the certificate is outdated or incorrect, get a fresh income certificate from the issuing authority (usually the Tehsildar/SDM office) before reapplying.",
            "If your income has genuinely changed since the certificate was issued, a new certificate reflecting current income is needed.",
        ],
        "recommend_document_check": True,
    },
    {
        "id": "deadline_missed",
        "keywords": ["late", "deadline", "time limit", "period expired", "application window", "last date"],
        "title": "The application appears to have been rejected for timing reasons",
        "explanation": "This usually means the application was submitted after the scheme's application window closed.",
        "steps": [
            "Check if the scheme has a new application cycle or window opening -- many schemes reopen annually.",
            "If you believe your application was actually submitted on time and this is an error, this is worth raising as a grievance with proof of your submission date/time.",
        ],
        "recommend_document_check": False,
    },
    {
        "id": "duplicate",
        "keywords": ["already availed", "duplicate", "already registered", "already enrolled", "already a beneficiary"],
        "title": "The system shows you (or a family member) as already enrolled",
        "explanation": (
            "Many schemes allow only one beneficiary per family or per person. This rejection usually "
            "means the department's records show the benefit as already claimed."
        ),
        "steps": [
            "Check with family members if someone has already applied for or received this specific scheme.",
            "If you're certain this is incorrect (identity mixed up, wrong record), this is a strong case for a grievance -- include any proof that you have not previously received the benefit.",
        ],
        "recommend_document_check": False,
    },
]

FALLBACK_CATEGORY = {
    "id": "unclear",
    "title": "We couldn't automatically identify a clear reason",
    "explanation": (
        "The rejection message didn't clearly match a common pattern we recognise. This doesn't mean "
        "the rejection is wrong -- it just means you may need to read the notice closely or contact the "
        "issuing department directly."
    ),
    "steps": [
        "Re-read the rejection notice carefully for any reference/application number and reason code.",
        "Contact the scheme's helpdesk (listed on the scheme's official page) with your application number for a specific reason.",
        "If you still believe the rejection is wrong after checking, use the Grievance Draft Assistant below.",
    ],
    "recommend_document_check": True,
}


def _contains_keyword(text_lower, keyword):
    """Word-boundary match so substrings inside unrelated words don't false-positive
    (e.g. 'late' inside 'unrelated')."""
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text_lower) is not None


def decode_rejection(text):
    """
    Match pasted rejection text against known rejection patterns.
    Returns the matched category dict (title, explanation, steps), or the
    fallback category if nothing matches -- the user is never told a wrong
    guessed reason, only a real matched one or an honest "unclear."
    """
    text_lower = (text or "").lower()
    for category in REJECTION_CATEGORIES:
        if any(_contains_keyword(text_lower, kw) for kw in category["keywords"]):
            return category
    return FALLBACK_CATEGORY


def draft_grievance(name, scheme_name, application_ref, reason_text):
    """
    Rule-based template, not an LLM call -- the draft is built from a fixed
    structure so it is predictable and always reviewable, never a
    hallucinated claim. The output is explicitly for the user to review and
    edit before submitting themselves on CPGRAMS -- never auto-submitted.
    """
    ref_line = f"Application/Reference Number: {application_ref}\n" if application_ref else ""
    draft = f"""To,
The Grievance Redressal Officer

Subject: Grievance regarding rejection of application for {scheme_name}

Respected Sir/Madam,

I, {name}, had applied for the {scheme_name} scheme. {ref_line}My application was rejected, and I believe this rejection was incorrect for the following reason:

{reason_text}

I request you to kindly review my application again and share the specific reason for rejection, along with guidance on how to proceed. I have attached/can provide all relevant supporting documents on request.

I look forward to your response and resolution at the earliest.

Thank you,
{name}
"""
    return draft.strip()
