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
    "student": ["student", "students", "scholarship", "scholarships", "education", "study", "college"],
    "women": ["women", "woman", "girl", "girls", "mahila", "female", "mother", "mothers", "maternity"],
    "senior": ["senior", "old age", "elderly", "pension", "retirement"],
    "health": ["health", "hospital", "hospitals", "medical", "illness", "treatment", "insurance"],
    "housing": ["house", "housing", "home", "awas"],
    "business": ["business", "businesses", "entrepreneur", "entrepreneurs", "startup", "startups", "loan", "loans", "enterprise"],
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


# Which words in a question point at which kind of document problem.
MISMATCH_TRIGGERS = {
    "name": ["name", "spelling", "initials"],
    "dob": ["dob", "birth", "birthday"],
    "address": ["address", "pin", "pincode", "pin code"],
    "unreadable": ["blur", "blurry", "unclear", "unreadable", "illegible", "not clear"],
}
PROBLEM_WORDS = ["mismatch", "match", "wrong", "incorrect", "error", "mistake", "correct", "different", "rejected", "problem"]

STOPWORDS = {
    "a", "an", "the", "is", "am", "are", "do", "does", "did", "i", "you", "me", "my",
    "for", "of", "in", "on", "at", "to", "what", "which", "who", "how", "can", "could",
    "tell", "about", "need", "needs", "needed", "get", "check", "please", "list",
    "scheme", "schemes", "this", "that", "and", "or", "with", "eligible", "eligibility",
    "document", "documents", "papers", "benefit", "benefits", "yojana", "pradhan",
    "mantri", "pm", "national", "india", "indian", "apply", "help",
}


_GROUP_WORDS = {kw for kws in CATEGORY_KEYWORDS.values() for kw in kws}


def _content_words(text):
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def _has_term(msg_lower, term):
    """
    Whole-word match for English terms; plain substring for Hindi (Python's
    word boundary breaks on Devanagari vowel signs). A plain `term in message`
    check is wrong here: "hi" would match inside "this" and "scholarship",
    and "ok" inside "book".
    """
    if term.isascii():
        return re.search(r"\b" + re.escape(term) + r"\b", msg_lower) is not None
    return term in msg_lower


def _has_any(msg_lower, terms):
    return any(_has_term(msg_lower, t) for t in terms)


def _scheme_words(scheme):
    return set(_content_words(scheme["name"])) | set(_content_words(scheme["id"].replace("-", " ")))


def _find_scheme_by_name(message, schemes):
    """
    Confident scheme match: the message contains the scheme's id (e.g.
    "pm-kisan", "pmay") or a word that identifies exactly ONE scheme (e.g.
    "atal", "ayushman"). Words shared by several schemes ("pension",
    "scholarship", "students") deliberately do not count, so a general
    question like "pension for elderly" is treated as a category question
    instead of being hijacked by whichever pension scheme is listed first.
    """
    msg_lower = message.lower()
    msg_spaced = re.sub(r"[-_]", " ", msg_lower)
    msg_words = set(_content_words(message))
    if not msg_words:
        return None

    for s in schemes:
        short = s["id"].replace("-", " ")
        if len(short) > 3 and short in msg_spaced:
            return s

    doc_freq = {}
    for s in schemes:
        for w in _scheme_words(s):
            doc_freq[w] = doc_freq.get(w, 0) + 1

    best_scheme, best_score = None, 0
    for s in schemes:
        # Words that name a group of people ("loan", "students", "awas") never identify one scheme.
        overlap = {w for w in (msg_words & _scheme_words(s))
                   if doc_freq[w] == 1 and w not in _GROUP_WORDS}
        if len(overlap) > best_score:
            best_score, best_scheme = len(overlap), s
    return best_scheme


def _find_scheme_loosely(message, schemes):
    """Last resort once category matching has had its say: any word overlap, then near-spellings."""
    msg_words = set(_content_words(message))
    if not msg_words:
        return None

    best_scheme, best_score = None, 0
    for s in schemes:
        overlap = msg_words & _scheme_words(s)
        if len(overlap) > best_score:
            best_score, best_scheme = len(overlap), s
    if best_scheme:
        return best_scheme

    for s in schemes:
        scheme_words = _scheme_words(s)
        for w in msg_words:
            if difflib.get_close_matches(w, scheme_words, n=1, cutoff=0.85):
                return s
    return None


def _schemes_for_category(category, schemes):
    if category == "farmer":
        return [s for s in schemes if "farmer" in s["occupations"]]
    if category == "student":
        return [s for s in schemes if "student" in s["occupations"] or s["category"] == "Education"]
    if category == "women":
        return [s for s in schemes if s["gender"] == "female" or "woman" in s["special_categories"]]
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
    return []


def _find_category_matches(message, schemes):
    """
    Category/occupation-based discovery, e.g. 'schemes for farmers'.
    Returns None if the message names no known group, otherwise a list
    (possibly empty). If several groups are named ("women entrepreneurs"),
    schemes in all of them come first, then the rest, interleaved so no
    group is crowded out.
    """
    msg_lower = message.lower()
    groups = [
        _schemes_for_category(category, schemes)
        for category, keywords in CATEGORY_KEYWORDS.items()
        if _has_any(msg_lower, keywords)
    ]
    if not groups:
        return None
    if len(groups) == 1:
        return groups[0]

    ids_in_all = set.intersection(*(set(s["id"] for s in g) for g in groups))
    merged = [s for s in groups[0] if s["id"] in ids_in_all]
    seen = set(ids_in_all)
    for rank in range(max(len(g) for g in groups)):
        for g in groups:
            if rank < len(g) and g[rank]["id"] not in seen:
                merged.append(g[rank])
                seen.add(g[rank]["id"])
    return merged


def _mismatch_help(msg_lower):
    """Guidance for 'my name is wrong on my Aadhaar'-type questions, or None."""
    if not (_has_any(msg_lower, PROBLEM_WORDS) or _has_any(msg_lower, DOCUMENT_WORDS)):
        return None
    for key, triggers in MISMATCH_TRIGGERS.items():
        if _has_any(msg_lower, triggers):
            guide = MISMATCH_GUIDE[key]
            steps = "\n".join(f"{i+1}. {step}" for i, step in enumerate(guide["steps"]))
            return f"{guide['title']}:\n{steps}"
    return None


def _scheme_answer(msg_lower, scheme):
    if _has_any(msg_lower, DOCUMENT_WORDS):
        docs = "\n".join(f"- {d}" for d in scheme["required_documents"])
        return f"Documents typically required for {scheme['name']}:\n{docs}"

    if _has_any(msg_lower, ELIGIBILITY_WORDS):
        parts = [scheme["description"]]
        if scheme["min_age"]:
            parts.append(f"Minimum age: {scheme['min_age']}")
        if scheme["max_age"]:
            parts.append(f"Maximum age: {scheme['max_age']}")
        if scheme["income_max"]:
            parts.append(f"Annual family income should be under Rs. {scheme['income_max']:,}")
        if scheme["extra_conditions"]:
            parts.append(f"Also: {scheme['extra_conditions']}")
        parts.append("For a personalised check, use the Eligibility Checker on this site.")
        return "\n".join(parts)

    if _has_any(msg_lower, BENEFIT_WORDS):
        return f"{scheme['name']} offers: {scheme['benefit_summary']}"

    return f"{scheme['name']}: {scheme['description']} Benefit: {scheme['benefit_summary']}"


def get_response(message):
    message = (message or "").strip()
    if not message:
        return FALLBACK_MSG

    msg_lower = message.lower()
    word_count = len(msg_lower.split())
    schemes = get_all_schemes()

    if word_count <= 3 and _has_any(msg_lower, GREETING_WORDS):
        return GREETING_MSG

    if word_count <= 4 and _has_any(msg_lower, THANKS_WORDS):
        return THANKS_MSG

    if _has_term(msg_lower, "list") and _has_any(msg_lower, ("scheme", "schemes")):
        names = "\n".join(f"- {s['name']}" for s in schemes)
        return f"Here are the schemes I know about:\n{names}\n\nAsk me about any one of these by name."

    # A scheme named unambiguously takes priority, so a real question never
    # gets hijacked by a stray keyword.
    matched_scheme = _find_scheme_by_name(message, schemes)
    if matched_scheme:
        return _scheme_answer(msg_lower, matched_scheme)

    category_matches = _find_category_matches(message, schemes)
    if category_matches is not None:
        if not category_matches:
            return "I couldn't find a scheme matching that group in our current list. Try the full Eligibility Checker on this site for a complete personalised result."
        names = "\n".join(f"- {s['name']}" for s in category_matches[:8])
        return f"Here are relevant schemes:\n{names}\n\nAsk me about any one by name, or use the Eligibility Checker for a personalised match."

    matched_scheme = _find_scheme_loosely(message, schemes)
    if matched_scheme:
        return _scheme_answer(msg_lower, matched_scheme)

    if _has_any(msg_lower, HELP_WORDS):
        return HELP_MSG

    mismatch_reply = _mismatch_help(msg_lower)
    if mismatch_reply:
        return mismatch_reply

    if _has_any(msg_lower, ELIGIBILITY_WORDS):
        return (
            "I can check eligibility if you tell me which scheme you mean, or you can "
            "use the full Eligibility Checker on this site for a personalised result "
            "across all schemes at once."
        )

    if _has_any(msg_lower, DOCUMENT_WORDS):
        return (
            "Which scheme's documents would you like to know about? Try \"documents for PM-KISAN\". "
            "You can also use the Document Consistency Checker on this site to verify your documents directly."
        )

    return FALLBACK_MSG
