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
import unicodedata
from data.schemes_data import MISMATCH_GUIDE

CPGRAMS_URL = "https://pgportal.gov.in"

# Each category: trigger keywords -> (plain-language explanation, fix-it steps)
REJECTION_CATEGORIES = [
    {
        "id": "document_mismatch",
        "keywords": ["mismatch", "does not match", "discrepancy", "inconsistent", "does not tally", "मेल नहीं खाता", "मेल नहीं खाती", "मेल नहीं खा", "मेल नहीं", "मिलान नहीं", "असंगत", "विसंगति", "mel nahi", "match nahi", "do not match", "did not match", "not matching", "doesn't match", "doesn’t match", "mismatched", "inconsistency", "discrepancies", "does not correspond"],
        "title": "Your documents likely had a mismatch",
        "explanation": (
            "This usually means a detail on one document (often your name, date of birth, or address) "
            "did not exactly match the same detail on another document you submitted."
        ),
        "steps": MISMATCH_GUIDE["name"]["steps"],
        "recommend_document_check": True,
    },
    {
        "id": "bank_aadhaar_link",
        "keywords": [
            "not linked", "aadhaar not linked", "aadhaar seeding", "not seeded", "seeding", "npci", "dbt",
            "account inactive", "inactive account", "account is inactive", "account closed", "invalid account",
            "ifsc", "bank details", "bank account", "account number",
            "आधार लिंक नहीं", "आधार से लिंक नहीं", "आधार सीडिंग", "बैंक खाता", "बैंक विवरण",
            "खाता निष्क्रिय", "खाता बंद", "आईएफएससी", "बैंक खाते", "लिंक नहीं",
        ],
        "title": "Your bank account or Aadhaar linking needs attention",
        "explanation": (
            "Most scheme payments go straight to your bank account through Aadhaar-based direct benefit "
            "transfer (DBT). Applications are often rejected because the account is not linked to Aadhaar, "
            "is inactive or closed, or the account details entered do not match the bank's records."
        ),
        "steps": [
            "Ask your bank (branch, net banking or app) to confirm your account is active and linked to your Aadhaar number.",
            "If it isn't linked, submit the Aadhaar linking (seeding) request at your bank branch with your Aadhaar and passbook, and ask them to enable the account for direct benefit transfer.",
            "Check the account number, IFSC code and the name on the passbook against what you entered in the application -- one wrong digit, or a name that differs from your Aadhaar, is a common cause.",
            "If a copy of your passbook or cancelled cheque was not attached, attach a clear one when you reapply.",
            "Once the bank confirms, reapply or ask the scheme office to re-verify the application, and keep the bank's confirmation slip.",
        ],
        "recommend_document_check": True,
    },
    {
        "id": "missing_document",
        "keywords": ["missing", "not submitted", "not attached", "incomplete document", "document not found", "not uploaded", "incomplete", "दस्तावेज़ नहीं", "दस्तावेज़ अपूर्ण", "दस्तावेज़ उपलब्ध नहीं", "अपूर्ण", "अधूरा", "अधूरे", "संलग्न नहीं", "अपलोड नहीं", "प्रस्तुत नहीं", "document nahi", "adhura"],
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
        "id": "income_exceeds",
        "keywords": ["income exceeds", "income limit", "above the prescribed", "income criteria", "आय सीमा", "आय अधिक", "आय से अधिक", "आय की सीमा", "आमदनी अधिक", "aay adhik", "income zyada"],
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
        "id": "not_eligible",
        "keywords": ["not eligible", "does not meet", "ineligible", "criteria not met", "eligibility criteria", "पात्र नहीं", "अपात्र", "पात्रता मानदंड", "पात्रता शर्तें", "योग्य नहीं", "patra nahi"],
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
        "id": "deadline_missed",
        "keywords": ["late", "deadline", "time limit", "period expired", "application window", "last date", "अंतिम तिथि", "समय सीमा", "देर से", "विलंब", "अवधि समाप्त", "समय समाप्त", "तिथि के बाद"],
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
        "keywords": ["already availed", "duplicate", "already registered", "already enrolled", "already a beneficiary", "पहले से पंजीकृत", "पहले से लाभ", "पहले ही लाभ", "पहले से नामांकित", "डुप्लिकेट", "दोहरा", "दोहराव"],
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


def _norm(text):
    """Lower-case, normalise Unicode and drop the Devanagari nukta so the same Hindi word
    typed or spoken with/without it (दस्तावेज़ / दस्तावेज) is treated as identical."""
    t = unicodedata.normalize("NFC", text or "").lower().replace("\u093c", "")
    return re.sub(r"\s+", " ", t)


def _contains_keyword(text_norm, keyword):
    """
    English keywords use a word-boundary match so substrings inside unrelated
    words don't false-positive (e.g. 'late' inside 'unrelated'). Hindi
    keywords use a plain substring match: Python's \\b treats Devanagari
    vowel signs as non-word characters, which breaks word-boundary matching.
    """
    kw = _norm(keyword)
    if kw.isascii():
        return re.search(r"\b" + re.escape(kw) + r"\b", text_norm) is not None
    return kw in text_norm


# Which document field(s) a "mismatch" notice is talking about.
_MISMATCH_FIELD_WORDS = {
    "name": ["name", "names", "naam", "नाम"],
    "dob": ["dob", "date of birth", "birth date", "birth", "janm", "जन्म"],
    "address": ["address", "addresses", "pin code", "pincode", "पता", "पते"],
}
_FIELD_TITLES = {"name": "name", "dob": "date of birth", "address": "address"}


def _specialise_mismatch(category, text_norm):
    """Return a copy of the mismatch category whose steps fit the field(s) named in the notice."""
    fields = [f for f, words in _MISMATCH_FIELD_WORDS.items()
              if any(_contains_keyword(text_norm, w) for w in words)]
    result = dict(category)
    if fields:
        steps = []
        for f in fields:
            steps += [step for step in MISMATCH_GUIDE[f]["steps"] if step not in steps]
        result["steps"] = steps
        result["title"] = category["title"] + " (" + ", ".join(_FIELD_TITLES[f] for f in fields) + ")"
    else:
        # The notice didn't say which detail; give the first fix for each, not just the name.
        result["steps"] = [MISMATCH_GUIDE[f]["steps"][0] for f in ("name", "dob", "address")] + [
            "Use the Document Checker on this site to see exactly which detail differs between your documents.",
        ]
    return result


def decode_rejection(text):
    """
    Match pasted rejection text (English, Hindi, or Hinglish) against known
    rejection patterns. Returns the matched category dict (title, explanation,
    steps), or the fallback category if nothing matches -- the user is never
    told a wrong guessed reason, only a real matched one or an honest "unclear."
    """
    text_norm = _norm(text)
    for category in REJECTION_CATEGORIES:
        if any(_contains_keyword(text_norm, kw) for kw in category["keywords"]):
            if category["id"] == "document_mismatch":
                return _specialise_mismatch(category, text_norm)
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
