# -*- coding: utf-8 -*-
"""
Rule-based eligibility engine.

Deliberately NOT machine learning -- every match or rejection can be traced
back to a specific, statable reason. This is a feature for a citizen-facing
government tool: a user (and a judge) can always be told exactly *why*
they matched or didn't.
"""

from models.db import get_all_schemes
from data.schemes_data import EMPLOYMENT_SHORT


def user_categories(answers):
    """
    The set of category codes that apply to this person. A person can belong
    to several at once (e.g. SC + BPL + person with disability), so this is a
    set, not a single value. "woman" is derived from gender rather than asked.

    Older sessions stored a single "category" string; still understood.
    """
    cats = set(answers.get("categories") or [])
    legacy = answers.get("category")
    if legacy:
        cats.add(legacy)
    cats.discard("general")  # "General" just means no special category
    if answers.get("gender") == "female":
        cats.add("woman")
    return cats


def _check_rule(scheme, answers):
    """Return a list of (passed: bool, reason: str) tuples for each rule."""
    checks = []

    age = answers["age"]
    if scheme["min_age"] is not None:
        checks.append((age >= scheme["min_age"], f"Minimum age is {scheme['min_age']}"))
    if scheme["max_age"] is not None:
        checks.append((age <= scheme["max_age"], f"Maximum age is {scheme['max_age']}"))

    if scheme["income_max"] is not None:
        checks.append((
            answers["income"] <= scheme["income_max"],
            f"Annual family income must be Rs. {scheme['income_max']:,} or below",
        ))

    if scheme["gender"] != "ALL":
        checks.append((answers["gender"] == scheme["gender"], f"Only for {scheme['gender']} applicants"))

    if scheme["occupations"] != ["ALL"]:
        checks.append((
            answers["occupation"] in scheme["occupations"],
            "Must match one of the scheme's listed occupations",
        ))

    employment = scheme.get("employment", ["ALL"])
    if employment != ["ALL"] and answers.get("employment"):
        wanted = " or ".join(EMPLOYMENT_SHORT.get(e, e) for e in employment)
        checks.append((
            answers["employment"] in employment,
            f"Meant for people who are {wanted}",
        ))

    if scheme["special_categories"] != ["ALL"]:
        checks.append((
            bool(user_categories(answers) & set(scheme["special_categories"])),
            "Must belong to one of the scheme's listed categories",
        ))

    if scheme["states"] != ["ALL"] and answers.get("state"):
        checks.append((
            answers["state"] in scheme["states"],
            "Only available in: " + ", ".join(scheme["states"]),
        ))

    return checks


def evaluate(answers):
    """
    answers: dict with keys age (int), income (int, annual INR),
             gender ("male"/"female"/"other"), occupation (code),
             employment (code), state (name), categories (list of codes)

    Returns: dict with 'matched' (list of scheme dicts with 'why' reasons)
             and 'near_miss' (list of scheme dicts that fail exactly one rule,
             with the single blocking reason) -- shown when matches are thin
             or zero, so the user never sees a blank page.
    """
    schemes = get_all_schemes()
    matched, near_miss = [], []

    for scheme in schemes:
        checks = _check_rule(scheme, answers)
        failed = [reason for passed, reason in checks if not passed]

        if not failed:
            scheme_copy = dict(scheme)
            scheme_copy["why"] = _why_matched(scheme, answers)
            matched.append(scheme_copy)
        elif len(failed) == 1:
            scheme_copy = dict(scheme)
            scheme_copy["blocking_reason"] = failed[0]
            near_miss.append(scheme_copy)

    return {"matched": matched, "near_miss": near_miss}


def _why_matched(scheme, answers):
    """Plain-language reasons a user qualifies, for transparency."""
    reasons = []
    if scheme["min_age"] is not None or scheme["max_age"] is not None:
        reasons.append(f"Your age ({answers['age']}) is within the scheme's allowed range")
    if scheme["income_max"] is not None:
        reasons.append(f"Your stated annual family income (Rs. {answers['income']:,}) is within the Rs. {scheme['income_max']:,} limit")
    if scheme["gender"] != "ALL":
        reasons.append(f"This scheme is for {scheme['gender']} applicants, which matches your profile")
    if scheme["occupations"] != ["ALL"]:
        reasons.append("Your occupation matches what this scheme targets")
    if scheme.get("employment", ["ALL"]) != ["ALL"] and answers.get("employment"):
        reasons.append("Your work arrangement matches who this scheme is meant for")
    if scheme["special_categories"] != ["ALL"]:
        reasons.append("Your category matches what this scheme targets")
    if scheme["states"] != ["ALL"] and answers.get("state"):
        reasons.append(f"This scheme is available in {answers['state']}")
    if not reasons:
        reasons.append("This scheme is open to all citizens with no restricting criteria you'd be excluded by")
    return reasons
