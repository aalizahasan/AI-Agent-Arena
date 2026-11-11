# FINAL COMPETITION DEMO — MEOW MEOW FRONT DESK

## One account, one machine

- **Google Calendar/Sheets owner:** `syedaalizahassannaqvi@gmail.com`
- **Judge/test email per organizers:** Same team email.
- **LLM:** Gemini API key from Google AI Studio (separate from Google OAuth).
- **Computer:** Windows with Docker Desktop, Python 3.12 and Git.
- **Repository:** `https://github.com/aalizahasan/AI-Agent-Arena.git`

### 1. Google Cloud (one-time) — complete this BEFORE startup

1. Open https://console.cloud.google.com/ and sign into **syedaalizahassannaqvi@gmail.com**.
2. Create/select a Google Cloud project (for example, `MMVH-Arena`).
3. In **APIs & Services → Library**, enable **Google Calendar API**, **Google Sheets API**, **Google Drive API**.
4. In **Google Auth Platform** (or **APIs & Services → OAuth consent screen**), configure the application, choose **External** if asked, provide an app name and your email, and add **syedaalizahassannaqvi@gmail.com** as a test user if the application is in Testing mode.
5. Under **Clients / Credentials → Create OAuth client ID**, select **Desktop application**, then download the JSON file.
6. Save that file at `AI-Agent-Arena\secrets\client_secret.json` (rename it exactly). **Do not upload or commit that file.**

The OAuth sign-in in step 3 must be the competition account. The bootstrap aborts if you accidentally sign into another Google account.

### 2. Get the code and enter your keys safely

In Windows PowerShell:

```powershell
git clone https://github.com/aalizahasan/AI-Agent-Arena.git
cd AI-Agent-Arena
Copy-Item .env.example .env
New-Item -ItemType Directory -Force secrets | Out-Null
notepad .env
```

Enter your Gemini API key in `GEMINI_API_KEY=`. Keep `LLM_PROVIDER=gemini`, `GEMINI_MODEL=gemini-3.8-flash`, `GOOGLE_OWNER_EMAIL` and `JUDGE_EMAIL` set as instructed. Generate two **different** values for `INTERNAL_API_KEY` and `N8N_ENCRYPTION_KEY`:

```powershell
python -c "import secrets;print(secrets.token_urlsafe(48))"
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Paste each generated value into its own `.env` field. **Never send your credentials through ChatGPT, screenshots, or GitHub commits.**

### 3. Start

With Docker Desktop running:

```powershell
.\scripts\start-demo.ps1
```

Google OAuth opens a browser. Sign in as `syedaalizahassannaqvi@gmail.com`. Accept the requested scopes; your Google account owns the created calendars and spreadsheet. The script runs automated tests, performs real Google setup, launches Docker and checks connectivity.

**If your Google account already has a token/resource file, the bootstrap reuses existing resources.**

### 4. Import n8n workflow — mandatory

1. Visit **http://localhost:5678**.
2. Create the n8n owner account if prompted.
3. Import **`workflows/mmvh-front-desk.json`**.
4. Confirm the four connected nodes are visible and the HTTP node points to `http://app:8000/api/requests`.
5. **Publish/activate the workflow**. An unactivated workflow does not receive production webhook requests.
6. The production webhook URL is `http://localhost:5678/webhook/mmvh-front-desk`.

### 5. Judge-facing live test (must actually pass)

Visit **http://localhost:8000**.

Use a fresh request ID and synthetic contact details. For a clean demo, book a **Wellness Exam for dog Milo at 10:00 AM on 16 November 2026** under the authorized test email. The system should return `BOOKED` and a reference, not just conversational assurance.

Now verify:

- The **MMVH - Mr Saanp** calendar contains the event.
- The **Appointments** tab has an `ACTIVE` row with a real `event_id`.
- The **CallLog** contains the corresponding request ID and `BOOKED` response.
- Reuse the *same exact JSON payload and request_id* in a second webhook submission: no new event or appointment row.
- Add a staff meeting to the provider calendar and verify an overlapping booking is rejected, with valid E1 suggestions.
- Reschedule an existing booking and confirm the same appointment reference and row.
- Change the **S1** duration in Config and verify a new booking uses the changed duration (existing events stay unchanged).
- Cancel with reference and matching email; confirm Calendar event deletion and a `CANCELED` row.
- Ask a medical/symptom question; expect a human handoff, no diagnosis or booking.

**Do not create appointments just from a screenshot or fake fixture; judges must see live Google writes.**

### 6. If the UI returns an error

- `http://localhost:8000/health` checks the API process, not Google access.
- In PowerShell run `docker compose ps` and `docker compose logs --tail=100 app n8n`.
- Run `.\.venv\Scripts\python.exe -m scripts.preflight` for read-only service/Google checks.
- If the n8n webhook returns 404, make sure the workflow was published.
- If the response says integrations unavailable, inspect OAuth token, runtime resource file and Gemini model/key.
- If Calendar or Sheets fails, do not claim the action succeeded. Fix the root cause, then repeat with a **new request_id**.

The source code and mock tests can be checked without external credentials, but **full competition readiness only follows real end-to-end verification**.
