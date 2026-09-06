# Yojana Ready

Document Readiness and Rejection Risk Checker for Government Welfare Schemes

Smart India Hackathon 2026
Problem Statement ID: SIH26129
Problem Statement Title: System integration and interoperability among government digital platforms, resulting in fragmented service delivery
Theme: Smart Automation
Category: Software
Team Name: Tech Maniacs

## Team

| Name | Role |
|---|---|
| Ravneet Kaur | Team Leader |
| Taranpreet Kaur | Member |
| Anisha | Member |
| Bhanu Pratap | Member |
| Kanishk Mittal | Member |
| Manjeet | Member |

Institution: Guru Tegh Bahadur Institute of Technology (GTBIT), Rajouri Garden, New Delhi

## The Problem

Government portals such as MyScheme and UMANG already help citizens discover welfare schemes and check basic eligibility. What they do not cover is what happens on either side of that step. Most rejections do not happen because a citizen is ineligible. They happen because of avoidable document errors such as a name spelled differently across Aadhaar and an income certificate, a missing document, or an incomplete form. Once a rejection happens, a citizen is generally left with a short notice and no clear next step.

## What Yojana Ready Does

Yojana Ready is built around the two gaps that existing scheme portals do not address:

1. **Document Consistency Checker**: reads uploaded documents using real OCR (Tesseract), compares name, date of birth, and address across up to four documents at once, and flags mismatches before a citizen submits an application.
2. **Post-Rejection Recovery**: a citizen who has already been rejected can paste the rejection notice and receive a plain-language explanation of the likely reason, a step-by-step fix, and an auto-drafted grievance letter for the official CPGRAMS portal.

Alongside these two, the platform also includes a rule-based Eligibility Checker across 40 real central government schemes, a scheme assistant chatbot, voice input, a bilingual English and Hindi interface, and user accounts so a citizen's progress is saved across visits.

The eligibility checker and chatbot are supporting features. The document checker and rejection recovery flow are the part that does not exist anywhere else today, and are what should be demonstrated first.

## Why the Design Choices Are Deliberately Rule-Based

Both the chatbot and the rejection decoder are rule-based rather than backed by a large language model. This is intentional. Every response is derived from a fixed, inspectable rule or a verified entry in the scheme database, so the system cannot invent a wrong eligibility criterion, a fake scheme, or an incorrect rejection reason. The trade-off is that both are scoped rather than open-ended, which is disclosed openly rather than hidden.

Other honesty notes worth stating directly in a demo or to a judge:

- Document field extraction uses label-based text parsing tuned to the structured sample documents included with this project. Arbitrary, fully unstructured real-world document layouts would need a more advanced extraction approach, which is noted as future scope rather than presented as already solved.
- Scheme details such as income limits and benefit amounts are indicative and based on publicly available guidelines. Government schemes are revised periodically, and the interface tells users to confirm final details on the official portal before applying.
- All sample documents bundled with this project (see `static/img/samples/`) are entirely fictional, generated for testing. Real identity documents should never be used with this or any prototype.
- The Grievance Draft Assistant produces a letter for the citizen to review and edit. It is never submitted on anyone's behalf.

## Feature Summary

- Eligibility Checker across 40 real central government schemes (Agriculture, Health, Education, Women and Maternity, Pension, Housing, Financial Inclusion, Insurance, Entrepreneurship, Skill Development, Food Security, and Social Security)
- Document Consistency Checker supporting 2 to 4 documents per check, with an Application Readiness Score and document-fix sequencing guidance
- Rejection Decoder covering document mismatch, missing document, ineligibility, income limit, missed deadline, and duplicate-claim categories, with an honest fallback when a reason cannot be identified
- Grievance Draft Assistant linked to the real CPGRAMS portal (pgportal.gov.in)
- Case File that ties the eligibility check, document check, and rejection recovery into one record per user, downloadable as a plain-text summary
- User accounts with hashed passwords; a logged-in user's Case File is stored in the database and persists across sessions and devices
- Rule-based scheme assistant chatbot with category-based discovery (for example, "schemes for farmers")
- Free browser-based voice input on the chatbot and the rejection notice field
- English and Hindi interface toggle
- Basic accessibility support: skip-to-content link, screen-reader labels, visible keyboard focus states, and reduced-motion support

## Project Structure

```
app.py                     Flask application and all routes
Dockerfile                 Production image definition for hosting
requirements.txt
models/
  db.py                    SQLite connection and scheme data seeding
  auth.py                  User registration and login (hashed passwords)
  casefile_store.py        Persists the Case File for logged-in users
  eligibility.py           Rule-based eligibility engine
  document_check.py        OCR, fuzzy matching, readiness score, sequencing
  chatbot.py               Rule-based scheme assistant
  rejection.py             Rejection decoder and grievance draft generator
data/
  schemes_data.py          The 40-scheme dataset
  schemes.db               SQLite database (generated by models/db.py)
templates/                 Jinja2 HTML templates
static/
  css/style.css            Stylesheet
  fonts/                   Self-hosted fonts
  js/main.js               Chatbot widget and questionnaire logic
  js/voice.js              Web Speech API voice input
  img/samples/              Fictional sample documents for demo use
generate_samples.py         Regenerates the sample documents
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

4. Build the database (creates the scheme data, users, and case file tables):
   ```
   python models/db.py
   ```

5. Run the application:
   ```
   python app.py
   ```
   Visit http://127.0.0.1:5000

Note on Tesseract detection: the application automatically checks for the default Windows install path only when running on Windows. On Linux and macOS, Tesseract is expected to already be on the system PATH after installation through the package manager shown above, so no extra configuration is needed there, including when deployed.

## Deploying to Render

This project includes a Dockerfile so that Tesseract, a system-level dependency, is installed correctly. Render's default Python environment does not include Tesseract, so deploying without Docker would cause the Document Consistency Checker to fail in production even though it works locally.

Steps:

1. Push this project to a GitHub repository.
2. On Render, select **New > Web Service** and connect that repository.
3. Render should automatically detect the `Dockerfile` and select Docker as the environment. If it does not, set the environment to Docker manually in the service settings.
4. Leave the build and start commands blank; both are defined inside the Dockerfile.
5. Under Environment Variables, add:
   - `SECRET_KEY` set to a long random string (used to sign session cookies; do not reuse the default development value in production)
6. Click **Create Web Service**. The first deploy will take a few minutes since it builds the Docker image and installs Tesseract.
7. Once deployed, Render provides a public URL such as `https://your-service-name.onrender.com`.

Important limitation to know before relying on this for a live demo: Render's free tier uses an ephemeral filesystem, meaning the SQLite database (`data/schemes.db`) is reset on every redeploy and on periodic instance restarts. Scheme data will always be recreated automatically on startup, but registered user accounts and any saved Case Files will not persist across a redeploy on the free tier. For a persistent database across redeploys, Render's paid plans support attaching a persistent disk, or the project can be pointed at an external database service instead of local SQLite.

## Trying It Without Real Documents

On the Check My Documents page, use the sample-document dropdowns instead of uploading real files:

- Matching set: Aadhaar sample plus Income Certificate sample, all fields match
- Mismatch set: Aadhaar sample plus Scholarship Form sample, catches a name mismatch and a date-of-birth mismatch, with guidance to fix the Aadhaar record first

For the Rejection Decoder, example inputs to try:

- "Your application has been rejected as the name does not match your Aadhaar card" resolves to the document mismatch category
- "Application rejected: applicant already availed benefit under this scheme" resolves to the duplicate-claim category
- "Your income exceeds the prescribed limit for this scheme" resolves to the income category

## Suggested Demo Order for the Internal Round

1. Open with the Document Checker or the Rejection Decoder, not the Eligibility Checker
2. Show a mismatch being caught live using the bundled sample documents
3. Show the Rejection Decoder explaining a pasted notice, followed by the generated grievance draft
4. Show the Case File tying the above steps together into one record
5. Mention the Eligibility Checker and chatbot as supporting features that round out the platform

## Extending the Scheme Database

Add a new scheme by appending an entry to the `SCHEMES` list in `data/schemes_data.py`, following the structure of the existing entries, then rebuild the database with:
```
python models/db.py
```
