# -*- coding: utf-8 -*-
"""
Generates mock sample "documents" (as images) for demo/testing purposes.

IMPORTANT: All names, ID numbers, and addresses below are entirely fictional,
created for this project. Never use real ID documents (including a team
member's own) anywhere in testing or a live demo -- see the Data Privacy
section of the project blueprint.
"""

import os
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "samples")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_BOLD = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"), 26)
FONT_TITLE = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"), 22)
FONT_BODY = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans.ttf"), 22)


def make_document(filename, header, fields, footer=""):
    W, H = 900, 500
    img = Image.new("RGB", (W, H), color="white")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W - 1, H - 1], outline=(60, 60, 60), width=3)
    draw.rectangle([20, 20, W - 20, 90], fill=(31, 56, 100))
    draw.text((40, 35), header, font=FONT_BOLD, fill="white")

    y = 130
    for label, value in fields:
        draw.text((50, y), f"{label}:", font=FONT_TITLE, fill=(31, 56, 100))
        draw.text((260, y), value, font=FONT_BODY, fill=(20, 20, 20))
        y += 55

    if footer:
        draw.text((50, H - 60), footer, font=FONT_BODY, fill=(120, 120, 120))

    path = os.path.join(OUT_DIR, filename)
    img.save(path)
    print("Created", path)


# ---- Set A: a clean, fully MATCHING pair ----
make_document(
    "sample_matched_aadhaar.png",
    "GOVERNMENT OF INDIA - AADHAAR CARD (SAMPLE)",
    [
        ("Name", "Rohan Kumar Sharma"),
        ("DOB", "14-03-2003"),
        ("Address", "House 22, Sector 9, Rohini, Delhi"),
        ("Aadhaar No", "XXXX XXXX 4821"),
    ],
    footer="This is a fictional sample document created for demo/testing purposes only.",
)

make_document(
    "sample_matched_income_cert.png",
    "INCOME CERTIFICATE (SAMPLE)",
    [
        ("Name", "Rohan Kumar Sharma"),
        ("DOB", "14-03-2003"),
        ("Address", "House 22, Sector 9, Rohini, Delhi"),
        ("Annual Income", "Rs. 1,80,000"),
    ],
    footer="This is a fictional sample document created for demo/testing purposes only.",
)

# ---- Set B: a pair with a NAME + DOB mismatch, to demo the checker catching it ----
make_document(
    "sample_mismatch_aadhaar.png",
    "GOVERNMENT OF INDIA - AADHAAR CARD (SAMPLE)",
    [
        ("Name", "Taranpreet Kaur"),
        ("DOB", "15-08-2004"),
        ("Address", "House 12, Sector 5, Delhi"),
        ("Aadhaar No", "XXXX XXXX 1190"),
    ],
    footer="This is a fictional sample document created for demo/testing purposes only.",
)

make_document(
    "sample_mismatch_scholarship_form.png",
    "SCHOLARSHIP APPLICATION FORM (SAMPLE)",
    [
        ("Name", "Tarandeep Kaur"),
        ("DOB", "15-08-2006"),
        ("Address", "House 12, Sector 5, New Delhi"),
        ("Course", "B.Tech CSE, 2nd Year"),
    ],
    footer="This is a fictional sample document created for demo/testing purposes only.",
)

print("Done.")
