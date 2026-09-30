# Yojana Ready

Yojana ready single point of access for government welfare schemes, so citizens no longer have to navigate multiple disconnected portals to find a scheme or check their documents and recover from a rejection.

**Smart India Hackathon 2026**
Problem Statement ID: SIH26129

Problem Statement Title: System integration and interoperability among government digital platforms, resulting in fragmented service delivery

Theme: Smart Automation

Category: Software

Institution: Guru Tegh Bahadur Institute of Technology (GTBIT), Rajouri Garden, New Delhi


## Team Name: "Tech Maniacs"
| Name | Role |
|---|---|
| Ravneet Kaur | Team Leader, Planning + Executor, Worked on website changes or alters |
| Taranpreet Kaur | Research Features, Tester, Deployer, Backend |
| Anisha | Research & Testing Features |
| Bhanu Pratap | PPT, Presentation of the whole Idea and Pitching |
| Kanishk Mittal | Front-end, UI/ UX |
| Manjeet | Front- end, UI/ UX |

## The Problem

Citizens today have to move across several separate government platforms just to apply for a single welfare scheme, one portal to discover the scheme another to check eligibility and no platform at all once an application gets rejected. This fragmentation is exactly what our assigned problem statement points to. Most rejections do not even happen because a citizen is ineligible. They happen because of small avoidable document errors such as a name spelled differently across Aadhaar and an income certificate or a document that was never explained clearly enough. Once rejected, a citizen is left with a short notice and no real next step.

## Our Solution

Yojana Ready brings scheme discovery, document verification, and rejection recovery into one platform, instead of leaving a citizen to figure out which of several government websites is supposed to help at each stage. It does not try to replace portals like MyScheme or UMANG which already handle scheme discovery well. It picks up exactly where they stop, catching document errors before submission and guiding a citizen through what to do after a rejection to complement those and easy navigations

## Key Features

- **Eligibility Checker**: a rule-based engine that matches a citizen's age, income, occupation, gender, work arrangement, state and category (multiple categories at once, e.g. SC + BPL) against 90 real government schemes,80 central schemes plus 10 state-specific schemes (7 Maharashtra, 3 from Uttar Pradesh/Rajasthan/Tamil Nadu) sourced and cross-checked from myscheme.gov.in, MahaDBT, Aaple Sarkar, and the concerned ministries and state departments and explains in plain language why they matched or came close. State-specific schemes are filtered by the citizen's state.
- **Document Consistency Checker**: reads uploaded documents (JPG, PNG, or PDF) using real OCR and checks name, date of birth and address across up to four documents at once. It gives an Application Readiness Score and tells the citizen what all documents are needed or which document to correct first (scheme specific documents)
- **Rejection Decoder**: a citizen who has already been rejected can paste the rejection notice they received. The system identifies the likely reason (document mismatch, missing document, ineligibility, income limit, missed deadline or a duplicate claim) and gives step by step guidance to fix it. If the reason cannot be confidently identified it says so honestly rather than guessing and guides you through CPGRAMS.
- **Grievance Draft Assistant**: if a citizen believes their rejection was wrong this feature auto-drafts a formal grievance letter using their case details (name, scheme, application reference, and reason) and links directly to CPGRAMS, the actual Centralised Public Grievance Redress and Monitoring System operated by the Government of India (pgportal.gov.in) The citizen reviews and edits the draft themselves before submitting it. Nothing is ever submitted on their behalf.
- **Case File**: ties the eligibility check, document check, and rejection recovery into a single record per citizen, downloadable as a plain text summary for the records for further use
- **User Accounts**: registration and login with hashed passwords, rate-limited against repeated failed attempts, so a logged-in citizen's Case File is saved to the database and stays available across sessions and devices. Accounts and case files are stored in an external PostgreSQL database (via `DATABASE_URL`) when configured so they survive redeploys on hosts with an ephemeral filesystem, such as Render's free tier.
- **Scheme Assistant Chatbot**: a rule-based assistant that answers from the verified scheme database only. It supports category based questions such as "schemes for farmers" or "schemes for women" and refuses to answer anything outside its scope rather than guessing.
- **Voice Input**: free browser based voice input on the chatbot and the rejection notice field so a citizen can speak instead of type.
- **Bilingual Interface**: English and Hindi toggle across the site.

## Technical Approach

- **Backend**: Flask (Python). The 90-scheme catalogue is rebuilt from `data/schemes_data.py` into a local SQLite file on every startup (it is read-only reference data, not user data so losing it on redeploy is harmless). User accounts and case files go to an external PostgreSQL database when `DATABASE_URL` is set (see "Persistent Accounts" below); without it, they fall back to the same local SQLite file for zero-setup local development.
- **Document OCR**: Tesseract accessed through pytesseract which reads text directly from uploaded document images. PDF uploads are converted to an image using PyMuPDF before the same OCR step runs so both file types go through one consistent pipeline. Field extraction uses label-based text parsing (looking for patterns like "Name:", "DOB:", "Address:") which works reliably for the structured sample documents included in this project. Fully unstructured, arbitrary real-world document layouts would need a more advanced extraction approach, which is future scope rather than something we are claiming is already solved.
- **Document Matching**: extracted fields are compared using fuzzy string matching (Python's difflib) with a tuned similarity threshold so that a real mismatch is caught while small OCR noise is not wrongly flagged.
- **Eligibility Logic**: a plain rule based engine not machine learning. Every match or near miss can be traced back to a specific rule which keeps the result explainable rather than a black box.
- **Chatbot and Rejection Decoder**: both are rule based rather than backed by a language model. Every response is derived from a fixed rule or a verified entry in the scheme database so the system cannot invent a scheme, a wrong criterion or a wrong rejection reason. This was a deliberate choice, not a limitation we are hiding.
- **Grievance Drafting**: built from a fixed letter template filled in with the citizen's case details not generated freely, so the output is predictable and always reviewable before submission.
- **Security**: CSRF tokens on every form and on the chat API, login throttling (5 failed attempts per 10 minutes), redirect targets restricted to this site (no open redirect via the post-login `next` parameter or the language switch), and uploaded documents are read from a private temporary folder and deleted immediately after the check, never written anywhere public or permanent.

## Feasibility and Viability

The entire platform runs on free and open source tools (Flask, SQLite, Tesseract) with no dependency on a paid API for its core functionality, which keeps it inexpensive to run and easy to scale. It is packaged with a Dockerfile, so it can be deployed on any standard cloud hosting service without manual server configuration. Because the eligibility and rejection logic are rule based rather than model based, the system's behaviour stays predictable and auditable, which matters for a tool meant to be trusted with government scheme guidance. The main technical dependency, Tesseract OCR, is a mature, actively maintained open source project with no licensing cost. Scheme details such as income limits and benefit amounts are indicative and based on publicly available guidelines; since schemes are revised periodically, the interface tells users to confirm final details on the official portal before applying.

## Impact and Benefits

- Reduces silent application rejections that happen due to preventable document mismatches, instead of a citizen finding out only after the fact.
- Saves citizens repeated trips to application centres caused by errors that could have been caught beforehand.
- Replaces a confusing, bureaucratic rejection notice with a plain language explanation of what actually went wrong.
- Gives citizens a guided path to formal grievance redressal through CPGRAMS, a real recourse that most citizens do not know exists or how to use.
- Directly reduces the fragmentation described in our problem statement by bringing scheme discovery, document readiness, and rejection recovery into one place instead of several disconnected government platforms.

## Project Structure


```
app.py                     Flask application and all routes
Dockerfile                 Production image definition for hosting
requirements.txt
models/
db.py                      SQLite connection and scheme data seeding
auth.py                    User registration and login (hashed passwords)
casefile_store.py          Persists the Case File for logged-in users
eligibility.py             Rule-based eligibility engine
document_check.py          OCR, fuzzy matching, readiness score, sequencing
chatbot.py                 Rule-based scheme assistant
rejection.py               Rejection decoder and grievance draft generator
data/
schemes_data.py            The 90-scheme dataset (80 central + 10 state-specific), plus validate_schemes() which checks it for consistency at build time
schemes.db                 SQLite database (generated by models/db.py; scheme catalogue only)
tests/
test_app.py                Regression tests: run with `python -m unittest tests.test_app -v`
templates/                 Jinja2 HTML templates
static/
css/style.css              Stylesheet
fonts/                     Self-hosted fonts
js/main.js                 Chatbot widget and questionnaire logic
js/voice.js                Web Speech API voice input
img/samples/               Fictional sample documents for demo use
generate_samples.py        Regenerates the sample documents
```

## Running Locally

1. Install Python 3.10 or later.

2. Install Tesseract OCR:
   - Windows: install from https://github.com/UB-Mannheim/tesseract/wiki, keeping the default install location
   - macOS: `brew install tesseract`
   - Linux: `sudo apt-get install tesseract-ocr`

3. Install the Python dependencies:
   ```
   pip install -r requirements.txt
   ```

4. (Optional) For persistent accounts across restarts, set `DATABASE_URL` to a PostgreSQL connection string before running the app (see "Persistent Accounts" below). If unset, accounts and case files use a local SQLite file instead, which is fine for local development.

5. Build the scheme catalogue:
   ```
   python models/db.py
   ```

6. Run the application:
   ```
   python app.py
   ```
   Visit http://127.0.0.1:5000

7. Run the regression tests (37 tests covering the security fixes, the eligibility engine, the document checker, the rejection decoder and the chatbot):
   ```
   python -m unittest tests.test_app -v
   ```

Note on Tesseract detection: the application automatically checks for the default Windows install path only when running on Windows. On Linux and macOS, Tesseract is expected to already be on the system PATH after installation through the package manager shown above, so no extra configuration is needed there, including when deployed.

## Persistent Accounts (PostgreSQL)

Render's free tier wipes the container's own disk on every redeploy or restart. Since the scheme catalogue is rebuilt from `data/schemes_data.py` at every startup anyway, that's harmless -- but user accounts and saved Case Files are not rebuildable, so they need a database that survives outside the container.

1. Create a free PostgreSQL database on [Neon](https://neon.tech) or [Supabase](https://supabase.com) and copy its connection string (starts with `postgresql://`).
2. Set it as the `DATABASE_URL` environment variable, both locally and on Render (see below). `psycopg2-binary` (already in `requirements.txt`) handles the connection.
3. That's it -- `models/db.py` detects `DATABASE_URL` automatically and creates the `users` and `case_files` tables on first use. No separate migration step is needed.

Without `DATABASE_URL`, the app still runs (falling back to local SQLite for accounts too), but registered users and their Case Files will disappear on the next redeploy. A startup log line states which one is active.

## Deploying to Render

This project includes a Dockerfile so that Tesseract, a system-level dependency, is installed correctly. Render's default Python environment does not include Tesseract, so deploying without Docker would cause the Document Consistency Checker to fail in production even though it works locally.

Steps:

1. Push this project to a GitHub repository.
2. On Render, select **New > Web Service** and connect that repository.
3. Render should automatically detect the `Dockerfile` and select Docker as the environment. If it does not, set the environment to Docker manually in the service settings.
4. Leave the build and start commands blank; both are defined inside the Dockerfile.
5. Under Environment Variables, add:
   - `SECRET_KEY` set to a long random string (used to sign session cookies -- generate one with `python -c "import secrets; print(secrets.token_hex(32))"`; the app will still run without this, falling back to a public default key and logging a warning, but that lets anyone forge login sessions, so set a real one before real users sign up)
   - `DATABASE_URL` set to your Neon/Supabase connection string (see "Persistent Accounts" above), so accounts and case files survive redeploys
6. Click **Create Web Service**. The first deploy will take a few minutes since it builds the Docker image and installs Tesseract.
7. Once deployed, Render provides a public URL such as `https://your-service-name.onrender.com`.

## Trying It Without Real Documents

On the Check My Documents page, use the sample-document dropdowns instead of uploading real files:

- Matching set: Aadhaar sample plus Income Certificate sample, all fields match
- Mismatch set: Aadhaar sample plus Scholarship Form sample, catches a name mismatch and a date-of-birth mismatch, with guidance to fix the Aadhaar record first

For the Rejection Decoder, example inputs to try:

- "Your application has been rejected as the name does not match your Aadhaar card" resolves to the document mismatch category
- "Application rejected: applicant already availed benefit under this scheme" resolves to the duplicate-claim category
- "Your income exceeds the prescribed limit for this scheme" resolves to the income category


## Future Scope

This prototype is intentionally scoped for the timeline of this hackathon. If taken further, the direction we would want to build toward is:

- A stronger, more capable chatbot with broader conversational ability, while keeping the same principle of never answering outside verified scheme data.
- The scheme database now covers 90 schemes: 80 central plus a first set of 10 state-specific schemes (Maharashtra, Uttar Pradesh, Rajasthan, Tamil Nadu). The next step is broadening state coverage -- especially more Maharashtra schemes, since SIH26129 was assigned by the Government of Maharashtra -- plus keeping pace with schemes as they are periodically revised (state scheme names, amounts and eligibility figures change more often than central ones).
- Multilingual chatbot support, extending past English and Hindi into more Indian languages.
- Hindi content shown in proper Devanagari script rather than the current transliterated form, across both the interface and the chatbot.
- Continued expansion of platform features as time and resources allow.

The underlying vision stays the same as what led to this project: reducing the number of separate government platforms a citizen has to deal with, by bringing scheme discovery, document readiness, and rejection recovery into one consolidated destination, which is the direct outcome our assigned problem statement asked for.
