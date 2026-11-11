# Meow Meow — Technical architecture

## Components

- Customer: responsive FastAPI-served web interface, or direct n8n webhook submission.
- n8n: judge-visible workflow orchestration; Webhook → normalization → authenticated HTTP tool call → response.
- Python FastAPI agent: LLM free-text interpretation and bounded execution of deterministic business policies.
- Google Calendar: two dedicated provider calendars. All events (including manually added meetings and all-day events) occupy intervals.
- Google Sheets: Config, Appointments, CallLog. Records are persisted as separate columns; live Config loaded for each request.
- OpenAI: strict JSON extraction of request intent and explicitly provided fields; no booking-success authority.

## Data flow

```text
Owner → /submit or n8n Webhook → n8n Normalize → FastAPI /api/requests
                                              ↓
                     Replay check in CallLog/Appointments
                                              ↓
                     Load and validate live Config
                                              ↓
                   Safety checks and LLM interpretation
                                              ↓
                     Deterministic slot/policy validation
                                              ↓
                  Live provider Google Calendar check
                                              ↓
                   State-changing Calendar operation
                                              ↓
                    Appointments and CallLog writes
                                              ↓
                 n8n RespondToWebhook → customer
```

## Booking rules

Timezone: America/Phoenix; competition time: 2026-11-11 09:00. Start times must be on 15-minute grid, at least 60 minutes after fixed time, no later than 25 November 2026; entire appointment must fit clinic and provider hours and avoid lunch; closed 19 November and weekends. Config determines provider calendar ID and service durations.

Interval semantics: `[start, end)`; overlapping events block, back-to-back slots are permitted.

## Extensions

E1: scan from requested start through the next two clinic working days, using live Calendar busy intervals, returning up to three chronological starts; do not book without consent.

E2: verify reference/email, ignore the event's own ID in conflict checks, update same Calendar event and row, attempt Calendar rollback on Sheet failure.

E3: SHA-256 fingerprint of normalized request input, replay prior successful result for same request_id, reject changed payload; sequential guarantee only.

E4: read Config on each request, applying edited service duration to *new* bookings. For rescheduling, use original event's recorded duration.

## Recovery and safety

- Invalid or missing input → NEEDS_INFO/UNAVAILABLE/HANDOFF without side effects.
- Unsafe medical requests → HANDOFF, no diagnosis/dosing/booking.
- Calendar error → ERROR (never false BOOKED).
- Calendar succeeded but Sheets append failed → Calendar compensating deletion; if deletion also fails, NEEDS_ATTENTION with event ID for reconciliation.
- Calendar reschedule succeeded but Sheets update failed → rollback original time, or NEEDS_ATTENTION if rollback fails.
- Cancellation requires reference + case-insensitive matching email. Wrong email and unknown reference share one generic error.
- All customer content is untrusted; the model cannot bypass deterministic tool validations.

## Limitations

The demo workflow is a thin orchestrator calling a Python agent: n8n owns the externally visible workflow but does not implement calendar reads in separate n8n nodes. A stricter judge may prefer adaptive n8n-native agent/tool nodes. This design prioritizes correctness in the official three-hour window.

No services are considered live until credentials, n8n import/activation, judge sharing, and actual integration tests are completed.
