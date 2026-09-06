# -*- coding: utf-8 -*-
"""
Scheme Chatbot -- deliberately rule-based, not an open-ended LLM wrapper.

Every answer is retrieved directly from the verified scheme database,
never generated freely, so it cannot hallucinate a wrong eligibility rule
or a fake scheme. This is presented to users and judges as a trust
feature, not a limitation.
"""

import difflib
import re
from models.db import get_all_schemes
from data.schemes_data import MISMATCH_GUIDE

GREETING_WORDS = {"hi", "hello", "hey", "namaste", "namaskar", "vanakkam", "\u0928\u092e\u0938\u094d\u0924\u0947"}
ELIGIBILITY_WORDS = {"eligible", "eligibility", "qualify", "qualification", "\u092a\u093e\u0924\u094d\u0930"}
DOCUMENT_WORDS = {"document", "documents", "papers", "\u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c"}
BENEFIT_WORDS = {"benefit", "benefits", "money", "amount"}
HELP_WORDS = {"help", "what can you do", "\u092e\u0926\u0926"}
THANKS_WORDS = {"thanks", "thank you", "thankyou", "ok", "okay", "great", "cool", "bye", "goodbye", "dhanyavad", "shukriya"}

# Category/occupation-based discovery -- lets a citizen browse by who they
# are, not just look up a scheme they already know the name of.
CATEGORY_KEYWORDS = {
    "farmer": ["farmer", "farmers", "farming", "kisan", "agriculture", "krishi"],
    "student": ["student", "students", "scholarship", "education", "study", "college"],
    "women": ["women", "woman", "girl", "mahila", "female", "mother", "maternity"],
    "senior": ["senior", "old age", "elderly", "pension", "retirement"],
    "health": ["health", "hospital", "medical", "illness", "treatment", "insurance"],
    "housing": ["house", "housing", "home", "awas"],
    "business": ["business", "entrepreneur", "startup", "loan", "enterprise"],
    "bpl": ["poor", "bpl", "below poverty"],
}

FALLBACK_MSG = (
    "I can only help with questions about government welfare schemes and how "
    "to use this platform. Try asking about a specific scheme, or something like "
    "\"schemes for farmers\" or \"list schemes\" to see everything I know about."
)

GREETING_MSG = (
    "Hello! I'm the scheme assistant for this platform. Ask me things like "
    "\"Am I eligible for PM-KISAN?\", \"schemes for women\", or \"what documents "
    "do I need for Ayushman Bharat?\" I only answer using our verified scheme "
    "database, so I won't guess."
)

THANKS_MSG = "You're welcome! Let me know if you have any other questions about a scheme."

HELP_MSG = (
    "I can help you with:\n"
    "- Finding schemes for a group you belong to (e.g. \"schemes for farmers\", \"schemes for women\")\n"
    "- Checking what a specific scheme is and who it's for\n"
    "- Listing documents required for a scheme\n"
    "- Pointing you to the full eligibility checker on this site\n"
    "Try: \"tell me about PM-KISAN\" or \"documents for Sukanya Samriddhi\""
)

STOPWORDS = {
    "a", "an", "the", "is", "am", "are", "do", "does", "did", "i", "you", "me", "my",
    "for", "of", "in", "on", "at", "to", "what", "which", "who", "how", "can", "could",
    "tell", "about", "need", "needs", "needed", "get", "check", "please", "list",
    "scheme", "schemes", "this", "that", "and", "or", "with", "eligible", "eligibility",
    "document", "documents", "papers", "benefit", "benefits", "yojana", "pradhan",
    "mantri", "pm", "national", "india", "indian", "apply", "help",
}


def _content_words(text):
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def _find_scheme_by_name(message, schemes):
    """
    Match a scheme mentioned in the message against the scheme database.
    Deliberately conservative: requires an actual distinctive-word overlap
    with the scheme's name/id, never a loose similarity over the whole
    sentence -- that caused unrelated questions to wrongly match a scheme.
    """
    msg_lower = message.lower()
    msg_words = set(_content_words(message))
    if not msg_words:
        return None

    for s in schemes:
        short = s["id"].replace("-", " ")
        if len(short) > 3 and short in msg_lower:
            return s

    best_scheme, best_score = None, 0
    for s in schemes:
        scheme_words = set(_content_words(s["name"])) | set(s["id"].split("-"))
        overlap = msg_words & scheme_words
        if overlap and len(overlap) > best_score:
            best_score, best_scheme = len(overlap), s
    if best_scheme:
        return best_scheme

    for s in schemes:
        scheme_words = set(_content_words(s["name"])) | set(s["id"].split("-"))
        for w in msg_words:
            if difflib.get_close_matches(w, scheme_words, n=1, cutoff=0.85):
                return s
    return None


def _find_category_matches(message, schemes):
    """Category/occupation-based discovery, e.g. 'schemes for farmers'."""
    msg_lower = message.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if not any(kw in msg_lower for kw in keywords):
            continue

        if category == "farmer":
            return [s for s in schemes if "farmer" in s["occupations"]]
        if category == "student":
            return [s for s in schemes if "student" in s["occupations"] or s["category"] == "Education"]
        if category == "women":
            return [s for s in schemes if s["gender"] == "female"]
        if category == "senior":
            return [s for s in schemes if s["category"] == "Pension"]
        if category == "health":
            return [s for s in schemes if s["category"] in ("Health", "Insurance")]
        if category == "housing":
            return [s for s in schemes if s["category"] == "Housing"]
        if category == "business":
            return [s for s in schemes if s["category"] == "Entrepreneurship"]
        if category == "bpl":
            return [s for s in schemes if "bpl" in s["special_categories"]]
    return None


def get_response(message):
    message = (message or "").strip()
    if not message:
        return FALLBACK_MSG

    msg_lower = message.lower()
    word_count = len(msg_lower.split())
    schemes = get_all_schemes()

    if any(w in msg_lower for w in GREETING_WORDS) and word_count <= 3:
        return GREETING_MSG

    if any(w in msg_lower for w in THANKS_WORDS) and word_count <= 4:
        return THANKS_MSG

    if "list" in msg_lower and "scheme" in msg_lower:
        names = "\n".join(f"- {s['name']}" for s in schemes)
        return f"Here are the schemes I know about:\n{names}\n\nAsk me about any one of these by name."

    # Specific scheme lookups take priority over generic help/category
    # matches, so a real question never gets hijacked by a stray keyword.
    matched_scheme = _find_scheme_by_name(message, schemes)

    if matched_scheme:
        if any(w in msg_lower for w in DOCUMENT_WORDS):
            docs = "\n".join(f"- {d}" for d in matched_scheme["required_documents"])
            return f"Documents typically required for {matched_scheme['name']}:\n{docs}"

        if any(w in msg_lower for w in ELIGIBILITY_WORDS):
            parts = [matched_scheme["description"]]
            if matched_scheme["min_age"]:
                parts.append(f"Minimum age: {matched_scheme['min_age']}")
            if matched_scheme["max_age"]:
                parts.append(f"Maximum age: {matched_scheme['max_age']}")
            if matched_scheme["income_max"]:
                parts.append(f"Annual family income should be under Rs. {matched_scheme['income_max']:,}")
            if matched_scheme["extra_conditions"]:
                parts.append(f"Also: {matched_scheme['extra_conditions']}")
            parts.append("For a personalised check, use the Eligibility Checker on this site.")
            return "\n".join(parts)

        if any(w in msg_lower for w in BENEFIT_WORDS):
            return f"{matched_scheme['name']} offers: {matched_scheme['benefit_summary']}"

        return f"{matched_scheme['name']}: {matched_scheme['description']} Benefit: {matched_scheme['benefit_summary']}"

    category_matches = _find_category_matches(message, schemes)
    if category_matches:
        if not category_matches:
            return "I couldn't find a scheme matching that group in our current list. Try the full Eligibility Checker on this site for a complete personalised result."
        names = "\n".join(f"- {s['name']}" for s in category_matches[:8])
        return f"Here are relevant schemes:\n{names}\n\nAsk me about any one by name, or use the Eligibility Checker for a personalised match."

    if any(w in msg_lower for w in HELP_WORDS):
        return HELP_MSG

    if any(w in msg_lower for w in ELIGIBILITY_WORDS):
        return (
            "I can check eligibility if you tell me which scheme you mean, or you can "
            "use the full Eligibility Checker on this site for a personalised result "
            "across all schemes at once."
        )

    if any(w in msg_lower for w in DOCUMENT_WORDS):
        for key, guide in MISMATCH_GUIDE.items():
            if key in msg_lower or any(w in msg_lower for w in guide["title"].lower().split()):
                steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(guide["steps"]))
                return f"{guide['title']}:\n{steps}"
        return "Which scheme's documents would you like to know about? You can also try the Document Consistency Checker to verify your documents directly."

    return FALLBACK_MSG
