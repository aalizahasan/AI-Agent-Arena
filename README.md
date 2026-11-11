# 🐾 Meow Meow — AI Veterinary Front Desk

**AI Agents Arena 2.0 · Operation Front Desk**  
An n8n-orchestrated AI front desk that uses an LLM to interpret pet-owner requests, enforces deterministic clinic rules, checks **real Google Calendar events**, and writes audit-ready records to **Google Sheets**.

> **Deployment status:** This repository contains a tested implementation and an n8n workflow export. Unit tests run without external credentials; Google OAuth, provider calendars, n8n import/activation, and live API tests must be completed with the team's accounts. Do not claim it is live before those steps succeed.

## What it does

| Capability | Implementation |
|---|---|
| Booking | Free-text LLM interpretation, exact-time validation, provider mapping, Google Calendar event, ACTIVE Sheets row |
| Cancellation | Reference + case-insensitive owner email, real event deletion, existing row marked CANCELED |
| E1 · Alternatives | Up to three valid starts through the next two clinic working days, live Calendar checks |
| E2 · Rescheduling | Same reference/event/row, self-conflict excluded, Calendar rollback on Sheets failure |
| E3 · Replay protection | Same successful `request_id`/payload returns previous result without a duplicate event |
| E4 · Config adaptation | Fetch Config from Google Sheets for every request; changed duration applies to future bookings |
| Safety | Staff handoff for urgent/medical queries, generic verification failures, prompt-injection defenses |
| Reliability | Error logging, creation compensation, explicit reconciliation statuses, no fabricated success |
| Demo surface | Accessible web chat, n8n webhook, live Google Calendar and Sheets evidence |

## Architecture

```text
Judge / Customer
     │ browser, curl, or POST
     ▼
   n8n Webhook ──→ Normalize input ──→ HTTP Request /api/requests
                                            │
                                      FastAPI Agent
                                      ├─ OpenAI LLM: intent + entity extraction
                                      ├─ Guardrails + deterministic rules
                                      ├─ Google Sheets: live Config + audit + appointments
                                      ├─ Google Calendar: live events, create/delete/patch
                                      └─ Tools: recovery, idempotence, alternative search
                                            │
   n8n Respond to Webhook ◀──────────────────┘
     │
   Verified customer response
```

The workflow is **executed through n8n**, not through the local browser alone. The FastAPI service is a permitted code/API step that performs the agent's bounded tool orchestration and makes local testing feasible. Judges can view all webhook executions in n8n. The UI's `/submit` route forwards to n8n, never directly to the business API. A Calendar or Sheets operation only executes after the agent and policy layer authorize it.

## Clinic facts (official challenge specification)

- **Clinic timezone:** `America/Phoenix` (UTC−07:00, all local appointment time).
- **Fixed business clock:** 2026-11-11 09:00 Phoenix. *Real wall-clock is only for execution logs.*
- **Clinic:** Mon–Fri 09:00–17:00, closed on 19 November 2026.
- **Mr Saanp:** Mon–Fri, lunch 12:00–13:00; S1/S2, 30 minutes for dogs/cats.
- **Miss Loomri:** Mon/Wed/Fri, lunch 12:00–13:00; S3, 45 minutes for rabbits/birds.
- **Rules:** One pet/request; complete owner name, email, pet, species, service, exact date/time; at least 60-minute lead; 15-minute grid; final date Nov 25 inclusive; full interval must fit; all overlapping events busy; back-to-back allowed.

## Run on Windows (with Docker Desktop)

### 1. Requirements

- Git and Python 3.12 (for the one-time Google bootstrap and automated tests).
- Docker Desktop with Docker Compose (WSL2 backend recommended on Windows).
- A Google account, a **Google Cloud Desktop OAuth** client, and Google **Calendar**, **Sheets**, **Drive** APIs enabled in that Cloud project.
- A usable OpenAI API key for an LLM; default model `gpt-4o-mini`. **ChatGPT subscription alone is not an API credential.**
- The judge's email address (for required sharing).

> IMPORTANT: Google Cloud may require adding the Google account as an OAuth test user on the consent-screen configuration, depending on the project's publishing state. Authorization must allow the Calendar, Sheets, and Drive scopes requested by the bootstrap script.

### 2. Configure secrets

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force secrets | Out-Null
```

Fill in `.env` with real `OPENAI_API_KEY`, `INTERNAL_API_KEY`, `N8N_ENCRYPTION_KEY`, and `JUDGE_EMAIL`. Use unique high-entropy values for the latter two; PowerShell generation examples:

```powershell
python -c "import secrets;print(secrets.token_urlsafe(48))"
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Put your downloaded Google **Desktop application OAuth JSON** at `secrets/client_secret.json` (the actual file must not be committed). Never share this file in a public repository or in competition exports.

### 3. Create the required calendars and Google Sheet

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.bootstrap_google
```

A Google sign-in browser window will appear. Use the same Google account intended to own the test resources. The script creates:

- `MMVH - Mr Saanp` and `MMVH - Miss Loomri` calendars.
- `MMVH — AI Agents Arena 2.0` spreadsheet with `Config`, `Appointments`, and `CallLog` tabs.
- Event-safe Calendar IDs in the Config rows.
- `secrets/token.json` and `secrets/runtime.json` locally, never in Git.

If `JUDGE_EMAIL` was set before running bootstrap, the script attempts to grant calendar **writer** access and spreadsheet **reader** access. **Verify these permissions in Google's Share UI before judging.** If sharing failed or the email was not set, do the sharing manually.

Running the script again reuses previously created resources saved in `secrets/runtime.json`.

### 4. Start Docker containers

```powershell
docker compose up -d --build
docker compose ps
```

Local access:

- **n8n editor:** http://localhost:5678
- **Customer web interface:** http://localhost:8000
- **Technical health:** http://localhost:8000/health

Health is only an application-process check; it does not prove external credentials are connected.

### 5. Import and activate the n8n workflow

1. Open n8n at http://localhost:5678 and create its owner login if needed.
2. Create/import a workflow using `workflows/mmvh-front-desk.json` (Import from File).
3. Confirm there are four connected nodes: `Judge Webhook`, `Normalize Judge Submission`, `Execute AI Front Desk Tools`, `Respond to Judge`.
4. Verify the HTTP Request URL is `http://app:8000/api/requests`. This is a **Docker-internal** hostname, not `localhost`.
5. Confirm `X-Internal-Key` expression is `{{ $env.INTERNAL_API_KEY }}` and that n8n's environment-access setting permits it. Do not paste the secret into the exported workflow.
6. Save and **activate/publish** the workflow. The live endpoint should be `http://localhost:5678/webhook/mmvh-front-desk`.
7. Submit a fresh request and inspect n8n execution history.

n8n has separate test and production webhook URLs. The `/submit` UI uses the **production** URL, so a saved and activated/published workflow is mandatory.

### 6. Run an end-to-end judge test

From PowerShell:

```powershell
$body = @{
  request_id = 'DEMO-01'
  message = 'Book a wellness exam for my dog Milo on 16 November 2026 at 10:00.'
  owner_name = 'Alex Khan'
  email = 'judge-test@example.com'
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri 'http://localhost:5678/webhook/mmvh-front-desk' `
  -ContentType 'application/json' `
  -Body $body
```

Use only synthetic owner details and the **judge-provided test email**, not genuine customer data. A real BOOKED result must correspond to the provider Calendar event and an ACTIVE Appointments row with its returned event ID. If any API fails, the status must be ERROR or NEEDS_ATTENTION, never BOOKED.

### 7. Share the web interface with judges

For **in-person evaluation**, open http://localhost:8000 on the laptop and let judges submit fresh requests.

For **remote evaluation**, optionally expose the web UI through a trusted HTTPS tunnel whose public URL forwards to port **8000**. The UI routes requests internally to n8n; opening the n8n administrative UI to the internet is unnecessary and unsafe. Do not publish Google credentials or the n8n admin interface.

## API input/output

Minimum payload:

```json
{"request_id":"DEMO-02","message":"Book a wellness exam for my dog Milo on 16 November 2026 at 10:00.","owner_name":"Alex Khan","email":"judge-test@example.com"}
```

Optional: `pet_name`, `species`, `service_id`, `requested_date` (YYYY-MM-DD), `requested_time` (24-hour HH:MM), `reference`.

Supported result statuses: `BOOKED`, `CANCELED`, `RESCHEDULED`, `NEEDS_INFO`, `UNAVAILABLE`, `HANDOFF`, `VERIFICATION_FAILED`, `ERROR`, `NEEDS_ATTENTION`. The exact format is documented in `docs/architecture.md`.

## Automated tests

```powershell
python -m pytest -q
```

Tests use a fake LLM, Calendar and Sheets adapters to verify deterministic logic and failure compensation. **They do not substitute for live OAuth and n8n testing**. The project also has a GitHub Actions CI job for these tests and workflow JSON structure.

## Competition demonstration

Follow [`docs/judge-demo.md`](docs/judge-demo.md) for a safe evidence-driven script and [`docs/test-matrix.md`](docs/test-matrix.md) for verification status and live test gaps.

## Safety and limitations

- This is a fictional exercise. No medical triage or diagnosis is performed.
- The app accepts synthetic data only; the judge-facing UI is not a production privacy/security service.
- Sequential replay protection is implemented; concurrent idempotency is not required by the PDF.
- Google Calendar does not offer an atomic "check and insert" transaction, so simultaneous competing booking requests could race. The arena explicitly does not require concurrent replay defense; use a workflow queue or distributed lock for a real clinic deployment.
- A Calendar/Sheets split-brain failure returns NEEDS_ATTENTION with reconciliation evidence.
- OAuth and provider integrations must be configured externally; do not commit credentials.
- Email confirmations, persistent multi-turn memory, voice, and multiple agents are intentionally omitted because they are optional and not automatically rewarded.