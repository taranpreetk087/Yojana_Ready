# -*- coding: utf-8 -*-
"""
Rule-based eligibility engine.

Deliberately NOT machine learning -- every match or rejection can be traced
back to a specific, statable reason. This is a feature for a citizen-facing
government tool: a user (and a judge) can always be told exactly *why*
they matched or didn't.
"""

from models.db import get_all_schemes


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

    if scheme["special_categories"] != ["ALL"]:
        checks.append((
            answers["category"] in scheme["special_categories"],
            "Must belong to one of the scheme's listed categories",
        ))

    return checks


def evaluate(answers):
    """
    answers: dict with keys age (int), income (int, annual INR),
             gender ("male"/"female"/"other"), occupation (code), category (code)

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
    if scheme["special_categories"] != ["ALL"]:
        reasons.append("Your category matches what this scheme targets")
    if not reasons:
        reasons.append("This scheme is open to all citizens with no restricting criteria you'd be excluded by")
    return reasons
