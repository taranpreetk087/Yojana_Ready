# Yojana Ready -- deployment image
# Uses Docker so Tesseract OCR (a system binary, not a Python package) is
# guaranteed to be present. Render's standard Python buildpack does not
# include Tesseract, so a plain "Python" service type would fail the
# Document Consistency Checker in production even though it works locally.

FROM python:3.12-slim

# Tesseract OCR binary + fonts used by generate_samples.py
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python models/db.py

# Render sets $PORT at runtime; gunicorn binds to it here.
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 app:app
