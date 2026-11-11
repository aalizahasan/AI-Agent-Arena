# Testing and verification matrix

## Automated logic tests (mock Google/LLM adapters)

Run `python -m pytest -q`. Coverage includes:

- S1, S2, S3 booking and provider/duration mapping.
- Fixed Phoenix business clock, 60-minute lead, 15-minute grid and final booking horizon.
- Closed weekdays/weekends, holiday, provider days, full-hour and lunch boundaries.
- Staff meetings and all-day events, legitimate back-to-back appointments.
- Missing information, conflicting message/form fields, unsupported pets and services.
- Medical symptom HANDOFF, private-record prompt-injection protection.
- E1 alternatives ordered after requested time.
- E2 same-reference rescheduling and failure rollback preserving original appointment.
- E3 sequential replay without duplicate event and changed-payload rejection.
- E4 new Config duration applied to future slots, existing duration retained.
- Case-insensitive email verification and identical wrong-email/unknown-reference failure.
- Calendar and Sheets error paths with compensation/NEEDS_ATTENTION.

## Live integration checklist

| Scenario | Required real-world evidence |
|---|---|
| n8n webhook | Real fresh submission and recorded workflow execution |
| LLM | Actual free-text extraction with model call |
| Calendar | Real created event ID in assigned provider calendar |
| Conflict | Manually added meeting/all-day busy blocks an overlap |
| Sheets | Real Config, Appointments and CallLog rows |
| Cancellation | Calendar delete and same Appointments row marked CANCELED |
| E1 | Alternatives match actual Calendar availability |
| E2 | Same event ID/reference/row after move |
| E3 | Two identical submissions, one event and one appointment row |
| E4 | Dynamic duration change affects next booking without code changes |
| Judge sharing | Edit access to two calendars and read access to spreadsheet |
| API failures | Honest ERROR or NEEDS_ATTENTION with execution evidence |

**Live integration remains unverified until authorized Google/n8n/LLM accounts are configured.** Mock tests do not prove Google writes.
