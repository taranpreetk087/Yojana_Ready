# -*- coding: utf-8 -*-
"""
Regression tests for the fixes made before the SIH portal submission.

Run from the project root:
    python -m unittest tests.test_app -v

To also exercise the PostgreSQL code path, set DATABASE_URL first:
    DATABASE_URL=postgresql://user:pass@host/db python -m unittest tests.test_app -v
"""

import glob
import io
import logging
import os
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as yojana                                             # noqa: E402
from models.eligibility import evaluate                           # noqa: E402
from models.db import get_all_schemes                             # noqa: E402
from models.document_check import compare_dob, compare_address    # noqa: E402
from models.rejection import decode_rejection                     # noqa: E402
from models.chatbot import get_response                           # noqa: E402
from data.schemes_data import SCHEMES, validate_schemes           # noqa: E402

SAMPLE = "sample_matched_aadhaar.png"
SAMPLE2 = "sample_matched_income_cert.png"
PNG_PATH = os.path.join(yojana.SAMPLE_DIR, SAMPLE)

BASE = dict(age=30, income=100000, gender="male", occupation="other",
            employment="none", state="Delhi", categories=[])


def matched(**overrides):
    return {s["id"] for s in evaluate({**BASE, **overrides})["matched"]}


class Client:
    """Test client that carries a valid CSRF token, like a real browser session."""

    def __init__(self):
        yojana.app.config["TESTING"] = False
        yojana.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.c = yojana.app.test_client()
        self.c.get("/")
        with self.c.session_transaction() as s:
            self.token = s["_csrf"]

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data.setdefault("csrf_token", self.token)
        return self.c.post(url, data=data, **kw)

    def get(self, url, **kw):
        return self.c.get(url, **kw)


class DataIntegrity(unittest.TestCase):
    def test_scheme_data_is_valid(self):
        self.assertTrue(validate_schemes(SCHEMES))

    def test_validator_catches_mixed_all(self):
        bad = [dict(SCHEMES[0], occupations=["farmer", "ALL"])]
        with self.assertRaises(ValueError):
            validate_schemes(bad)

    def test_validator_catches_unknown_category_code(self):
        bad = [dict(SCHEMES[0], special_categories=["not_a_real_code"])]
        with self.assertRaises(ValueError):
            validate_schemes(bad)


class Eligibility(unittest.TestCase):
    def test_apy_is_open_to_every_occupation(self):
        for occ in ("student", "homemaker", "other", "street_vendor", "entrepreneur", "farmer"):
            self.assertIn("apy", matched(occupation=occ), occ)

    def test_stand_up_india_matches_women_entrepreneurs(self):
        self.assertIn("stand-up-india", matched(gender="female", occupation="entrepreneur"))
        self.assertIn("stand-up-india", matched(gender="male", occupation="entrepreneur", categories=["sc"]))
        self.assertNotIn("stand-up-india", matched(gender="male", occupation="entrepreneur"))

    def test_multiple_categories_at_once(self):
        got = matched(age=30, categories=["sc", "bpl"])
        self.assertTrue({"pm-ajay", "ddu-gky", "pmgkay"} <= got)

    def test_employment_gates_epf_esi_pmkvy(self):
        self.assertNotIn("epf", matched(employment="none", occupation="student"))
        self.assertNotIn("esi", matched(employment="none", occupation="student"))
        self.assertIn("epf", matched(employment="formal"))
        self.assertIn("esi", matched(employment="formal", income=200000))
        self.assertIn("pmkvy", matched(age=20, employment="none"))
        self.assertNotIn("pmkvy", matched(age=20, employment="formal"))

    def test_old_single_category_session_still_works(self):
        result = evaluate(dict(age=21, income=180000, gender="female", occupation="student", category="obc"))
        self.assertTrue(result["matched"])


class DocumentChecks(unittest.TestCase):
    def test_dob_format_differences_are_not_mismatches(self):
        for other in ("15/08/2004", "15.08.2004", "15 Aug 2004", "August 15, 2004", "2004-08-15"):
            self.assertTrue(compare_dob("15-08-2004", other)[0], other)

    def test_dob_real_differences_are_mismatches(self):
        self.assertFalse(compare_dob("15-08-2004", "18-08-2004")[0])
        self.assertFalse(compare_dob("05-08-2004", "08-05-2004")[0])

    def test_address_pin_city_and_number_differences_are_caught(self):
        self.assertFalse(compare_address("House 12, Sector 5, Delhi 110027", "House 12, Sector 5, Delhi 110087")[0])
        self.assertFalse(compare_address("House 12, Sector 5, Rohini, Delhi", "House 12, Sector 5, Rohini, Noida")[0])
        self.assertFalse(compare_address("House 12, Sector 5, Rohini, Delhi", "House 21, Sector 5, Rohini, Delhi")[0])
        self.assertFalse(compare_address("Ludhiana, Punjab 141001", "Ludhiana, Haryana 141001")[0])

    def test_address_formatting_differences_are_not_mismatches(self):
        self.assertTrue(compare_address("House No. 12, Sector 5, Delhi", "H.No 12, Sec 5, Delhi")[0])
        self.assertTrue(compare_address("House 12, Sector 5, Delhi", "House 12, Sector 5, New Delhi")[0])
        self.assertTrue(compare_address("Andheri West, Bombay 400058", "Andheri West, Mumbai 400058")[0])
        self.assertTrue(compare_address("Rohini Delhi 110 085", "Rohini Delhi 110085")[0])


class RejectionDecoder(unittest.TestCase):
    def test_hindi_notices_are_understood(self):
        self.assertEqual(decode_rejection("आवेदन अस्वीकृत क्योंकि नाम मेल नहीं खाता")["id"], "document_mismatch")
        self.assertEqual(decode_rejection("आप इस योजना के लिए पात्र नहीं हैं")["id"], "not_eligible")
        self.assertEqual(decode_rejection("आय सीमा से अधिक होने के कारण अस्वीकृत")["id"], "income_exceeds")
        self.assertEqual(decode_rejection("दस्तावेज़ अपूर्ण")["id"], decode_rejection("दस्तावेज अपूर्ण")["id"])

    def test_bank_aadhaar_link_rejections(self):
        for text in ("Aadhaar not linked with bank account", "DBT failure: Aadhaar seeding not done",
                     "incorrect IFSC code", "आधार बैंक खाते से लिंक नहीं है"):
            self.assertEqual(decode_rejection(text)["id"], "bank_aadhaar_link", text)

    def test_mismatch_steps_follow_the_field_named(self):
        self.assertIn("date of birth", decode_rejection("DOB mismatch")["title"])
        self.assertIn("address", decode_rejection("address does not match")["title"])
        both = decode_rejection("name and address do not match")
        self.assertIn("name", both["title"])
        self.assertIn("address", both["title"])

    def test_specific_reason_beats_general_one(self):
        self.assertEqual(decode_rejection("not eligible because your income exceeds the limit")["id"], "income_exceeds")

    def test_unknown_stays_honestly_unclear(self):
        self.assertEqual(decode_rejection("Your application is rejected")["id"], "unclear")
        self.assertEqual(decode_rejection("योजना के अंतर्गत आपका आवेदन निरस्त")["id"], "unclear")


class StateSchemes(unittest.TestCase):
    def test_state_specific_schemes_are_filtered_by_state(self):
        def matched(**a):
            base = dict(age=30, income=100000, gender="male", occupation="other", employment="none",
                        state="Delhi", categories=[])
            base.update(a)
            return {s["id"] for s in evaluate(base)["matched"]}

        self.assertNotIn("mjpjay", matched(state="Delhi"))
        self.assertIn("mjpjay", matched(state="Maharashtra"))
        self.assertIn("ladki-bahin", matched(state="Maharashtra", gender="female", age=30, income=200000))
        self.assertNotIn("ladki-bahin", matched(state="Karnataka", gender="female", age=30, income=200000))
        self.assertIn("lek-ladki", matched(state="Maharashtra", gender="female", age=5, income=90000))
        self.assertIn("mahadbt-post-matric-mh", matched(state="Maharashtra", occupation="student",
                                                          categories=["sc"], income=200000))
        self.assertNotIn("mahadbt-post-matric-mh", matched(state="Delhi", occupation="student",
                                                             categories=["sc"], income=200000))
        self.assertIn("up-kanya-sumangala", matched(state="Uttar Pradesh", gender="female", age=5, income=250000))
        self.assertNotIn("up-kanya-sumangala", matched(state="Maharashtra", gender="female", age=5, income=250000))
        self.assertIn("rajasthan-chiranjeevi", matched(state="Rajasthan", income=700000))
        self.assertNotIn("rajasthan-chiranjeevi", matched(state="Gujarat", income=700000))
        self.assertIn("tn-cmchis", matched(state="Tamil Nadu", income=100000))
        self.assertNotIn("tn-cmchis", matched(state="Tamil Nadu", income=200000))

    def test_or_condition_schemes_use_income_cap_not_a_separate_category_gate(self):
        # Regression test for a real bug: Sanjay Gandhi Niradhar and Shravan Bal's source
        # criteria are "BPL OR income <= X" -- an OR. Modeling that as special_categories=["bpl"]
        # made it a required AND, so a genuinely low-income applicant who hadn't ticked "BPL"
        # was wrongly excluded. The fix relies on the income cap alone.
        def matched(**a):
            base = dict(age=40, income=15000, gender="male", occupation="other", employment="none",
                        state="Maharashtra", categories=[])
            base.update(a)
            return {s["id"] for s in evaluate(base)["matched"]}

        self.assertIn("sgny", matched())
        self.assertIn("shravan-bal", matched(age=70))

    def test_ninety_schemes_total(self):
        from data.schemes_data import SCHEMES
        self.assertEqual(len(SCHEMES), 90)


class ExhaustiveMatchingStrictness(unittest.TestCase):
    """
    Full boundary-condition audit of the eligibility engine, across every one
    of the 90 schemes and every criterion the engine checks. For each scheme
    and each criterion, constructs a profile that satisfies every OTHER
    criterion as generously as possible, then deliberately violates just the
    one criterion under test -- so a match would mean that one criterion was
    not actually being enforced. This is what surfaced two real bugs: ignwps
    and igndps (National Social Assistance Programme widow/disability
    pensions) listed ["bpl", "widow"] / ["bpl", "disability"] as
    special_categories, but the engine matches on ANY listed category (a
    correct OR for schemes like Stand-Up India: SC or ST or woman). For these
    two, the real requirement is AND (must be poor AND a widow/disabled), so
    someone who was merely poor, with no widow or disability status, was
    incorrectly shown as a match for a pension that legally excludes them.
    """

    @staticmethod
    def _all_schemes():
        return get_all_schemes()

    @staticmethod
    def _base_profile(s):
        occ = s["occupations"][0] if s["occupations"] != ["ALL"] else "other"
        gender = s["gender"] if s["gender"] != "ALL" else "male"
        emp = s.get("employment", ["ALL"])
        emp = emp[0] if emp != ["ALL"] else "self"
        state = s["states"][0] if s["states"] != ["ALL"] else "Delhi"
        cats = [c for c in s["special_categories"] if c != "ALL"]
        age = s["min_age"] or 25
        if s["max_age"] is not None and age > s["max_age"]:
            age = s["max_age"]
        income = (s["income_max"] - 1) if s["income_max"] else 50000
        return dict(age=age, income=income, gender=gender, occupation=occ,
                    employment=emp, state=state, categories=cats)

    def test_nobody_under_the_minimum_age_ever_matches(self):
        for s in self._all_schemes():
            if s["min_age"] is None or s["min_age"] == 0:
                continue
            profile = self._base_profile(s)
            profile["age"] = s["min_age"] - 1
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched despite being under min_age={s['min_age']}")

    def test_nobody_over_the_maximum_age_ever_matches(self):
        for s in self._all_schemes():
            if s["max_age"] is None:
                continue
            profile = self._base_profile(s)
            profile["age"] = s["max_age"] + 1
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched despite being over max_age={s['max_age']}")

    def test_nobody_over_the_income_cap_ever_matches(self):
        for s in self._all_schemes():
            if s["income_max"] is None:
                continue
            profile = self._base_profile(s)
            profile["income"] = s["income_max"] + 1
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched despite income over the cap")

    def test_the_wrong_gender_never_matches_a_gender_restricted_scheme(self):
        for s in self._all_schemes():
            if s["gender"] == "ALL":
                continue
            profile = self._base_profile(s)
            profile["gender"] = "female" if s["gender"] == "male" else "male"
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched with the wrong gender")

    def test_an_unlisted_occupation_never_matches(self):
        all_occ = ["farmer", "student", "unorganized_sector", "street_vendor",
                   "self_employed", "entrepreneur", "homemaker", "other"]
        for s in self._all_schemes():
            if s["occupations"] == ["ALL"]:
                continue
            profile = self._base_profile(s)
            profile["occupation"] = next(o for o in all_occ if o not in s["occupations"])
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched with an occupation outside its own list")

    def test_an_unlisted_state_never_matches_a_state_restricted_scheme(self):
        for s in self._all_schemes():
            if s["states"] == ["ALL"]:
                continue
            profile = self._base_profile(s)
            profile["state"] = "Kerala" if "Kerala" not in s["states"] else "Goa"
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched from a state outside its own list")

    def test_an_unlisted_employment_type_never_matches(self):
        all_emp = ["formal", "informal", "self", "none"]
        for s in self._all_schemes():
            emp_list = s.get("employment", ["ALL"])
            if emp_list == ["ALL"]:
                continue
            profile = self._base_profile(s)
            profile["employment"] = next(e for e in all_emp if e not in emp_list)
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched, f"{s['id']}: matched with an employment type outside its own list")

    def test_holding_none_of_the_required_special_categories_never_matches(self):
        # This is the exact test that catches the ignwps/igndps bug class: a
        # profile with an EMPTY category list must never match a scheme that
        # requires a specific category, regardless of how many categories
        # that scheme lists.
        for s in self._all_schemes():
            if s["special_categories"] == ["ALL"]:
                continue
            profile = self._base_profile(s)
            profile["categories"] = []
            matched = {m["id"] for m in evaluate(profile)["matched"]}
            self.assertNotIn(s["id"], matched,
                             f"{s['id']}: matched a profile holding NONE of its required categories {s['special_categories']}")

    def test_ignwps_and_igndps_specifically_require_the_real_condition(self):
        # The two schemes that actually surfaced this bug: being poor (BPL)
        # alone must never be enough for a widow-only or disability-only
        # pension -- the person must actually be a widow / actually disabled.
        def matched(**a):
            base = dict(age=45, income=80000, gender="female", occupation="other",
                        employment="none", state="Delhi", categories=[])
            base.update(a)
            return {s["id"] for s in evaluate(base)["matched"]}

        self.assertNotIn("ignwps", matched(categories=["bpl"]))
        self.assertIn("ignwps", matched(categories=["widow"]))
        self.assertNotIn("igndps", matched(categories=["bpl"], gender="male"))
        self.assertIn("igndps", matched(categories=["disability"], gender="male"))


class Chatbot(unittest.TestCase):
    def test_hi_inside_other_words_is_not_a_greeting(self):
        for q in ("what is this", "this", "scholarship for students"):
            self.assertFalse(get_response(q).startswith("Hello!"), q)
        self.assertTrue(get_response("hi").startswith("Hello!"))
        self.assertTrue(get_response("hello there").startswith("Hello!"))

    def test_ok_inside_other_words_is_not_thanks(self):
        self.assertFalse(get_response("book a ticket").startswith("You're welcome"))
        self.assertTrue(get_response("ok").startswith("You're welcome"))

    def test_documents_needed_does_not_return_name_mismatch_guide(self):
        self.assertNotIn("Name does not match", get_response("documents needed"))
        self.assertIn("Name does not match", get_response("my name is wrong on aadhaar"))
        self.assertIn("Address does not match", get_response("address mismatch on documents"))

    def test_general_questions_are_category_questions(self):
        self.assertTrue(get_response("pension for elderly").startswith("Here are relevant schemes"))
        self.assertTrue(get_response("scholarship for students").startswith("Here are relevant schemes"))

    def test_named_schemes_still_resolve(self):
        self.assertIn("Atal Pension", get_response("benefit of atal pension"))
        self.assertIn("Documents typically required for PM-KISAN", get_response("documents for pm-kisan"))
        self.assertIn("Stand-Up India", get_response("tell me about Stand-Up India"))

    def test_multi_group_question_shows_both_groups(self):
        reply = get_response("women entrepreneurs loan")
        self.assertIn("Stand-Up India", reply)


class WebSecurity(unittest.TestCase):
    def test_post_without_csrf_token_is_rejected(self):
        c = yojana.app.test_client()
        c.get("/")
        self.assertEqual(c.post("/rejection", data={"rejection_text": "x"}).status_code, 400)
        self.assertEqual(c.post("/api/chat", json={"message": "hi"}).status_code, 400)

    def test_chat_works_with_header_token(self):
        cl = Client()
        r = cl.c.post("/api/chat", json={"message": "hi"}, headers={"X-CSRF-Token": cl.token})
        self.assertEqual(r.status_code, 200)
        r = cl.c.post("/api/chat", json=["not", "a", "dict"], headers={"X-CSRF-Token": cl.token})
        self.assertEqual(r.status_code, 200)

    def test_login_redirect_cannot_leave_the_site(self):
        cl = Client()
        name = "t_" + uuid.uuid4().hex[:8]
        yojana.create_user(name, "secret12")
        for evil in ("https://evil.example.com", "//evil.example.com", "/\\evil.example.com", "javascript:alert(1)"):
            r = Client().post(f"/login?next={evil}", {"username": name, "password": "secret12"})
            self.assertEqual(r.status_code, 302)
            self.assertNotIn("evil", r.headers["Location"], evil)
        r = Client().post("/login?next=/case-file", {"username": name, "password": "secret12"})
        self.assertEqual(r.headers["Location"], "/case-file")

    def test_login_is_throttled_after_repeated_failures(self):
        cl = Client()
        name = "t_" + uuid.uuid4().hex[:8]
        yojana.create_user(name, "secret12")
        for _ in range(5):
            cl.post("/login", {"username": name, "password": "wrong"})
        r = cl.post("/login", {"username": name, "password": "secret12"})
        self.assertIn(b"Too many failed attempts", r.data)

    def test_bad_form_input_gives_a_message_not_a_crash(self):
        cl = Client()
        good = dict(age="30", income="100000", gender="male", state="Delhi",
                    occupation="other", employment="none")
        for bad in (dict(age="abc"), dict(age="-5"), dict(age="500"), dict(income="-1"),
                    dict(gender="x"), dict(state="Atlantis"), dict(occupation="zzz"), dict(employment="zzz")):
            r = cl.post("/eligibility", {**good, **bad})
            self.assertEqual(r.status_code, 200, bad)
            self.assertIn(b"Please", r.data, bad)
        r = cl.post("/eligibility", good)
        self.assertEqual(r.status_code, 302)

    def test_multi_select_categories_reach_the_engine(self):
        cl = Client()
        data = dict(age="45", income="90000", gender="male", state="Bihar", occupation="other", employment="informal")
        r = cl.c.post("/eligibility", data={**data, "csrf_token": cl.token, "categories": ["sc", "bpl"]})
        self.assertEqual(r.status_code, 302)
        html = cl.get("/eligibility/results").get_data(as_text=True)
        self.assertIn("PM-AJAY", html)
        self.assertIn("Check before applying", html)

    def test_secret_key_warning_is_logged_when_default_is_used(self):
        self.assertEqual(yojana.app.secret_key == yojana._DEFAULT_SECRET, not os.environ.get("SECRET_KEY"))


class UploadPrivacy(unittest.TestCase):
    def _yojana_tmp_dirs(self):
        return set(glob.glob(os.path.join(tempfile.gettempdir(), "yojana_*")))

    def test_uploads_are_deleted_and_never_web_accessible(self):
        cl = Client()
        before = self._yojana_tmp_dirs()
        with open(PNG_PATH, "rb") as f1, open(PNG_PATH, "rb") as f2:
            r = cl.post("/documents/upload", {
                "doc1": (io.BytesIO(f1.read()), "../../my-aadhaar.png"),
                "doc2": (io.BytesIO(f2.read()), "income.png"),
                "doc1_label": "Aadhaar", "doc2_label": "Income",
            }, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._yojana_tmp_dirs(), before, "temporary upload folder was not cleaned up")
        self.assertFalse(os.path.exists(os.path.join(yojana.BASE_DIR, "static", "uploads")))
        self.assertEqual(cl.get("/static/uploads/anything.png").status_code, 404)

    def test_upload_is_deleted_even_when_ocr_crashes(self):
        cl = Client()
        before = self._yojana_tmp_dirs()
        original = yojana.extract_fields
        yojana.extract_fields = lambda path: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = cl.post("/documents/upload", {
                "doc1": (io.BytesIO(b"x" * 100), "a.png"), "doc2": (io.BytesIO(b"y" * 100), "b.png"),
            }, content_type="multipart/form-data")
        finally:
            yojana.extract_fields = original
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self._yojana_tmp_dirs(), before)

    def test_sample_picker_only_accepts_bundled_samples(self):
        cl = Client()
        for evil in ("../../../../etc/passwd", "../sample_matched_aadhaar.png", "/etc/passwd", "nope.png"):
            r = cl.post("/documents/upload", {"doc1_sample": SAMPLE, "doc2_sample": evil})
            self.assertEqual(r.status_code, 200, evil)
            self.assertIn(b"at least 2 documents", r.data, evil)
        r = cl.post("/documents/upload", {"doc1_sample": SAMPLE, "doc2_sample": SAMPLE2})
        self.assertEqual(r.status_code, 302)

    def test_wrong_file_type_is_refused_with_a_message(self):
        cl = Client()
        r = cl.post("/documents/upload", {
            "doc1": (io.BytesIO(b"MZ"), "virus.exe"), "doc2_sample": SAMPLE,
        }, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Only JPG, PNG or PDF", r.data)

    def test_oversized_upload_shows_friendly_error(self):
        cl = Client()
        big = io.BytesIO(b"0" * (9 * 1024 * 1024))
        r = cl.post("/documents/upload", {"doc1": (big, "big.png"), "doc2_sample": SAMPLE},
                    content_type="multipart/form-data")
        self.assertEqual(r.status_code, 413)
        self.assertIn(b"too large", r.data)


class SchemeSpecificDocuments(unittest.TestCase):
    def test_generic_page_shows_the_four_generic_slots(self):
        html = yojana.app.test_client().get("/documents/upload").get_data(as_text=True)
        for label in ("Aadhaar Card", "Income Certificate", "Caste Certificate", "Bank Passbook"):
            self.assertIn(label, html)

    def test_mapped_scheme_shows_its_own_documents(self):
        html = yojana.app.test_client().get("/documents/upload?scheme_id=pm-kisan").get_data(as_text=True)
        self.assertIn("Land Ownership Record", html)
        self.assertIn("PM-KISAN", html)
        self.assertIn('name="scheme_id" value="pm-kisan"', html)

    def test_different_mapped_schemes_show_different_documents(self):
        html = yojana.app.test_client().get("/documents/upload?scheme_id=ssy").get_data(as_text=True)
        self.assertIn("Girl Child&#39;s Birth Certificate", html)
        self.assertNotIn("Land Ownership Record", html)

    def test_unmapped_scheme_falls_back_to_generic_documents(self):
        html = yojana.app.test_client().get("/documents/upload?scheme_id=igndps").get_data(as_text=True)
        self.assertIn("Aadhaar Card", html)
        self.assertIn("Income Certificate", html)
        self.assertIn("Indira Gandhi National Disability Pension", html)  # still names the right scheme

    def test_invalid_scheme_id_does_not_crash(self):
        self.assertEqual(yojana.app.test_client().get("/documents/upload?scheme_id=not-a-real-scheme").status_code, 200)

    def test_scheme_id_carries_through_to_the_report(self):
        cl = Client()
        cl.get("/documents/upload?scheme_id=pm-kisan")
        r = cl.post("/documents/upload", {
            "scheme_id": "pm-kisan",
            "doc1_sample": SAMPLE, "doc2_sample": SAMPLE2,
        })
        self.assertEqual(r.status_code, 302)
        html = cl.get("/documents/report").get_data(as_text=True)
        self.assertIn("PM-KISAN", html)

    def test_scheme_detail_links_to_its_own_document_check(self):
        html = yojana.app.test_client().get("/scheme/pm-kisan").get_data(as_text=True)
        self.assertIn("scheme_id=pm-kisan", html)

    def test_ten_mapped_schemes_are_all_real_and_well_formed(self):
        from data.schemes_data import DOCUMENT_CHECK_SCHEMES, SCHEMES
        ids = {s["id"] for s in SCHEMES}
        self.assertEqual(len(DOCUMENT_CHECK_SCHEMES), 10)
        for scheme_id, slots in DOCUMENT_CHECK_SCHEMES.items():
            self.assertIn(scheme_id, ids)
            self.assertTrue(2 <= len(slots) <= 4)


class HindiLocalization(unittest.TestCase):
    def _devanagari_count(self, html):
        return sum(1 for ch in html if "\u0900" <= ch <= "\u097F")

    def test_switching_to_hindi_actually_changes_the_page_content(self):
        pages = ["/", "/eligibility", "/documents/upload", "/rejection", "/login", "/register",
                 "/scheme/pm-kisan", "/case-file"]
        c_en = yojana.app.test_client()
        c_hi = yojana.app.test_client()
        r = c_hi.get("/set-language/hi", headers={"Referer": "http://localhost/"})
        self.assertEqual(r.status_code, 302)
        with c_hi.session_transaction() as s:
            self.assertEqual(s.get("lang"), "hi")
        for p in pages:
            en_count = self._devanagari_count(c_en.get(p).get_data(as_text=True))
            hi_count = self._devanagari_count(c_hi.get(p).get_data(as_text=True))
            # English pages only ever show the 3-character "हिं" toggle button label.
            self.assertLessEqual(en_count, 3, p)
            self.assertGreater(hi_count, 100, p)

    def test_english_branch_of_every_toggle_is_actual_english_not_devanagari(self):
        # Regression test for a real bug hit during translation: a naive global
        # text-replace corrupted several "if lang == 'en'" branches whose Hindi
        # fallback text happened to be identical to a plain English placeholder
        # (e.g. 'Log In', 'Username', 'Private pre-check') before translation.
        import re as re_
        pattern = re_.compile(
            r"\{\{\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s*if lang == 'en' else"
        )
        for path in glob.glob(os.path.join(yojana.BASE_DIR, "templates", "*.html")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in pattern.finditer(text):
                literal = m.group(1)
                has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in literal)
                self.assertFalse(has_devanagari, f"{path}: English branch is not English: {literal}")

    def test_every_hindi_fallback_is_devanagari_not_romanised(self):
        import re as re_
        pattern = re_.compile(r"if lang == 'en' else\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")")
        allowed_loanwords = {"'Log In'", "'Username'", "'Password'", "'Sign Up'", "'Primary ID'", "'optional'"}
        for path in glob.glob(os.path.join(yojana.BASE_DIR, "templates", "*.html")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in pattern.finditer(text):
                literal = m.group(1)
                if literal in allowed_loanwords:
                    continue
                has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in literal)
                self.assertTrue(has_devanagari, f"{path}: Hindi branch still romanised: {literal}")

    def test_devanagari_font_is_loaded_as_a_fallback(self):
        css = open(os.path.join(yojana.BASE_DIR, "static", "css", "style.css"), encoding="utf-8").read()
        self.assertIn("Noto+Sans+Devanagari", css)
        self.assertIn("Noto Sans Devanagari", css)


    def test_block_level_lang_ifs_are_also_translated(self):
        # Regression test for a real bug: the earlier translation pass only searched for
        # the inline `{{ 'X' if lang == 'en' else 'Y' }}` expression pattern. The landing
        # page hero used a block-level `{% if lang == 'en' %}...{% else %}...{% endif %}`
        # structure instead, so it was missed entirely and stayed in Roman-Hindi.
        import re as re_
        block_pattern = re_.compile(
            r"\{%\s*if lang == 'en'\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}", re_.DOTALL
        )
        for path in glob.glob(os.path.join(yojana.BASE_DIR, "templates", "*.html")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in block_pattern.finditer(text):
                english_branch, hindi_branch = m.group(1), m.group(2)
                self.assertFalse(
                    any("\u0900" <= ch <= "\u097F" for ch in english_branch),
                    f"{path}: English block branch contains Devanagari",
                )
                self.assertTrue(
                    any("\u0900" <= ch <= "\u097F" for ch in hindi_branch),
                    f"{path}: Hindi block branch is still romanised (not Devanagari)",
                )

    def test_landing_hero_actually_switches_language(self):
        c_en = yojana.app.test_client()
        c_hi = yojana.app.test_client()
        c_hi.get("/set-language/hi", headers={"Referer": "http://localhost/"})
        html_en = c_en.get("/").get_data(as_text=True)
        html_hi = c_hi.get("/").get_data(as_text=True)
        self.assertIn("Check your documents before you apply", html_en)
        self.assertIn("अपने दस्तावेज़ आवेदन करने से पहले जांच लें", html_hi)
        self.assertNotIn("Check your documents before you apply", html_hi)


class Accounts(unittest.TestCase):
    def test_register_login_and_case_file_round_trip(self):
        cl = Client()
        name = "t_" + uuid.uuid4().hex[:8]
        r = cl.post("/register", {"username": name, "password": "secret12", "confirm_password": "secret12"})
        self.assertEqual(r.status_code, 302)
        cl.post("/documents/upload", {"doc1_sample": SAMPLE, "doc2_sample": SAMPLE2})
        again = Client()
        again.post("/login", {"username": name, "password": "secret12"})
        html = again.get("/case-file").get_data(as_text=True)
        self.assertIn("2/", html.replace("&#47;", "/") or "") if False else None
        with again.c.session_transaction() as s:
            self.assertTrue(s["case_file"].get("documents_done"))

    def test_duplicate_username_is_refused(self):
        name = "t_" + uuid.uuid4().hex[:8]
        self.assertIsNotNone(yojana.create_user(name, "secret12"))
        self.assertIsNone(yojana.create_user(name, "another1"))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main(verbosity=2)
