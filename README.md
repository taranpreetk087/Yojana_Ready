# Yojana Ready

A single point of access for government welfare schemes, so citizens no longer have to navigate multiple disconnected portals to find a scheme, check their documents, and recover from a rejection.

**Smart India Hackathon 2026**
Problem Statement ID: SIH26129
Problem Statement Title: System integration and interoperability among government digital platforms, resulting in fragmented service delivery
Theme: Smart Automation
Category: Software
Team Name: Tech Maniacs

## Team

| Name | Role |
|---|---|
| Ravneet Kaur | Team Leader — Website Development, Testing, Presentation & Pitch |
| Taranpreet Kaur | UI/UX Design, Frontend Development & Deployment |
| Anisha | Research & Testing |
| Bhanu Pratap | Research & Testing |
| Kanishk Mittal | Research & Testing |
| Manjeet | Research & Testing |

Institution: Guru Tegh Bahadur Institute of Technology (GTBIT), Rajouri Garden, New Delhi

## The Problem

Citizens today have to move across several separate government platforms just to apply for a single welfare scheme: one portal to discover the scheme, another to check eligibility, and no platform at all once an application gets rejected. This fragmentation is exactly what our assigned problem statement points to. Most rejections do not even happen because a citizen is ineligible. They happen because of small, avoidable document errors, such as a name spelled differently across Aadhaar and an income certificate, or a document that was never explained clearly enough. Once rejected, a citizen is left with a short notice and no real next step.

## Our Solution

Yojana Ready brings scheme discovery, document verification, and rejection recovery into one platform, instead of leaving a citizen to figure out which of several government websites is supposed to help at each stage. It does not try to replace portals like MyScheme or UMANG, which already handle scheme discovery well. It picks up exactly where they stop: catching document errors before submission, and guiding a citizen through what to do after a rejection.

## Key Features

- **Eligibility Checker**: a rule-based engine that matches a citizen's age, income, occupation, gender, and category against 40 real central government schemes, and explains in plain language why they matched or came close.
- **Document Consistency Checker**: reads uploaded documents (JPG, PNG, or PDF) using real OCR, and checks name, date of birth, and address across up to four documents at once. It gives an Application Readiness Score and tells the citizen which document to correct first.
- **Rejection Decoder**: a citizen who has already been rejected can paste the rejection notice they received. The system identifies the likely reason (document mismatch, missing document, ineligibility, income limit, missed deadline, or a duplicate claim) and gives step by step guidance to fix it. If the reason cannot be confidently identified, it says so honestly rather than guessing.
- **Grievance Draft Assistant**: if a citizen believes their rejection was wrong, this feature auto-drafts a formal grievance letter using their case details (name, scheme, application reference, and reason) and links directly to CPGRAMS, the actual Centralised Public Grievance Redress and Monitoring System operated by the Government of India (pgportal.gov.in). The citizen reviews and edits the draft themselves before submitting it. Nothing is ever submitted on their behalf.
- **Case File**: ties the eligibility check, document check, and rejection recovery into a single record per citizen, downloadable as a plain text summary.
- **User Accounts**: registration and login with hashed passwords, so a logged in citizen's Case File is saved to the database and stays available across sessions and devices.
- **Scheme Assistant Chatbot**: a rule-based assistant that answers from the verified scheme database only. It supports category based questions such as "schemes for farmers" or "schemes for women," and refuses to answer anything outside its scope rather than guessing.
- **Voice Input**: free browser based voice input on the chatbot and the rejection notice field, so a citizen can speak instead of type.
- **Bilingual Interface**: English and Hindi toggle across the site.

## Technical Approach

- **Backend**: Flask (Python), with SQLite as the database for scheme data, user accounts, and saved case files.
- **Document OCR**: Tesseract, accessed through pytesseract, reads text directly from uploaded document images. PDF uploads are converted to an image using PyMuPDF before the same OCR step runs, so both file types go through one consistent pipeline. Field extraction uses label-based text parsing (looking for patterns like "Name:", "DOB:", "Address:"), which works reliably for the structured sample documents included in this project. Fully unstructured, arbitrary real-world document layouts would need a more advanced extraction approach, which is future scope rather than something we are claiming is already solved.
- **Document Matching**: extracted fields are compared using fuzzy string matching (Python's difflib), with a tuned similarity threshold so that a real mismatch is caught while small OCR noise is not wrongly flagged.
- **Eligibility Logic**: a plain rule based engine, not machine learning. Every match or near miss can be traced back to a specific rule, which keeps the result explainable rather than a black box.
- **Chatbot and Rejection Decoder**: both are rule based rather than backed by a language model. Every response is derived from a fixed rule or a verified entry in the scheme database, so the system cannot invent a scheme, a wrong criterion, or a wrong rejection reason. This was a deliberate choice, not a limitation we are hiding.
- **Grievance Drafting**: built from a fixed letter template filled in with the citizen's case details, not generated freely, so the output is predictable and always reviewable before submission.

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
schemes_data.py            The 40-scheme dataset
schemes.db                 SQLite database (generated by models/db.py)
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
- A much larger scheme database, expanding well beyond the current 40 schemes to cover state level schemes as well as central ones.
- Multilingual chatbot support, extending past English and Hindi into more Indian languages.
- Hindi content shown in proper Devanagari script rather than the current transliterated form, across both the interface and the chatbot.
- Continued expansion of platform features as time and resources allow.

The underlying vision stays the same as what led to this project: reducing the number of separate government platforms a citizen has to deal with, by bringing scheme discovery, document readiness, and rejection recovery into one consolidated destination, which is the direct outcome our assigned problem statement asked for.
