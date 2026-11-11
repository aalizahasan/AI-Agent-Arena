"""Read-only preflight checks for the competition's Google integrations and local services."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def check(name, operation, errors):
    try:
        detail = operation()
        print(f"PASS {name}: {detail or 'OK'}")
    except Exception as exc:
        errors.append((name, str(exc)))
        print(f"FAIL {name}: {exc}")


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only MMVH deployment and integration preflight')
    parser.add_argument('--skip-http', action='store_true', help='Skip local FastAPI/n8n reachability')
    args = parser.parse_args(argv)
    load_dotenv(ROOT / '.env')
    try:
        import httpx
        from app.adapters import APPOINTMENT_COLUMNS, CALL_LOG_COLUMNS, CONFIG_COLUMNS, SheetsStore, GoogleCalendar, get_google_credentials
        from app.configuration import load_config
    except ImportError as exc:
        print(f'FAIL Dependencies: {exc}. Install with pip install -r requirements.txt')
        return 1

    errors = []
    provider=os.getenv('LLM_PROVIDER','gemini').strip().lower()
    key_name='GEMINI_API_KEY' if provider == 'gemini' else 'OPENAI_API_KEY'
    keys = (key_name, 'INTERNAL_API_KEY', 'N8N_ENCRYPTION_KEY')
    missing = [key for key in keys if not os.getenv(key) or os.environ[key].startswith('replace-with')]
    if missing:
        print('FAIL Environment: configure ' + ', '.join(missing))
        errors.append(('Environment', 'Missing values'))
    else:
        print(f'PASS Environment: required variables supplied for {provider} (values not displayed)')

    runtime_path = ROOT / 'secrets' / 'runtime.json'
    token_path = ROOT / 'secrets' / 'token.json'
    if not runtime_path.exists():
        print('FAIL Bootstrap: secrets/runtime.json missing. Run python -m scripts.bootstrap_google')
        return 1
    runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
    sheet_id = os.getenv('GOOGLE_SHEET_ID') or runtime.get('spreadsheet_id')
    if not sheet_id:
        print('FAIL Bootstrap: Google spreadsheet ID missing')
        return 1
    try:
        creds = get_google_credentials(str(token_path))
        store = SheetsStore(creds, sheet_id)
        calendar = GoogleCalendar(creds)
        cfg = load_config(store.load_config())
        print('PASS Google OAuth, Sheets read access, and live Config: three official services loaded')
    except Exception as exc:
        print(f'FAIL Google integrations: {exc}')
        return 1

    for tab, cols in [('Config', CONFIG_COLUMNS), ('Appointments', APPOINTMENT_COLUMNS), ('CallLog', CALL_LOG_COLUMNS)]:
        def inspect_tab(tab=tab, cols=cols):
            headers = store.book.worksheet(tab).row_values(1)
            missing_headers = [name for name in cols if name not in headers]
            if missing_headers:
                raise RuntimeError('Missing columns: ' + ', '.join(missing_headers))
            return f'{len(headers)} columns present'
        check('Sheet ' + tab, inspect_tab, errors)

    for doctor, provider in cfg.providers.items():
        def inspect_calendar(provider=provider):
            data = calendar.api.calendars().get(calendarId=provider.calendar_id).execute()
            if data.get('timeZone') != 'America/Phoenix':
                raise RuntimeError('Incorrect calendar timezone')
            return data.get('summary', provider.calendar_id)
        check('Calendar ' + doctor, inspect_calendar, errors)

    if not args.skip_http:
        def check_fastapi():
            response = httpx.get('http://localhost:8000/health', timeout=6)
            response.raise_for_status()
            if response.json().get('status') != 'ok':
                raise RuntimeError('Unexpected health status')
            return 'FastAPI is reachable (live bookings not verified)'
        check('FastAPI', check_fastapi, errors)

        def check_n8n():
            response = httpx.get('http://localhost:5678/healthz', timeout=6)
            response.raise_for_status()
            return 'n8n is reachable (workflow activation not verified)'
        check('n8n', check_n8n, errors)

    print(f'Preflight: {len(errors)} issue(s). No appointments were changed.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
