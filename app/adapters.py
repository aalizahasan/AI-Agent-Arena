from __future__ import annotations
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]
TZ = ZoneInfo('America/Phoenix')
APPOINTMENT_COLUMNS = ['reference','owner_name','email','pet_name','species','service_id','provider',
    'start_local','end_local','event_id','status','request_id','fingerprint','updated_at']
CALL_LOG_COLUMNS = ['request_id','timestamp','message','interpreted_intent','result_status',
    'response','reference','fingerprint','response_json']
CONFIG_COLUMNS = ['kind','key','name','value','days','open_time','close_time',
    'lunch_start','lunch_end','species','provider','duration_min','calendar_id']

def get_google_credentials(token_path: str):
    path = Path(token_path)
    if not path.exists():
        raise RuntimeError(f'Google OAuth token missing: {path}. Run scripts/bootstrap_google.py first.')
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            path.write_text(creds.to_json())
        else:
            raise RuntimeError('Google OAuth authorization has expired without a refresh token')
    return creds

class SheetsStore:
    def __init__(self, credentials: Credentials, spreadsheet_id: str):
        self.book = gspread.authorize(credentials).open_by_key(spreadsheet_id)
        self.config = self.book.worksheet('Config')
        self.appointments = self.book.worksheet('Appointments')
        self.calllog = self.book.worksheet('CallLog')

    def load_config(self) -> list[dict[str,Any]]:
        return self.config.get_all_records(default_blank='')

    def find_processed(self, request_id: str) -> dict[str,Any] | None:
        records = self.calllog.get_all_records(default_blank='')
        for row in reversed(records):
            if str(row.get('request_id', '')) == request_id and str(row.get('result_status','')) in ('BOOKED','CANCELED','RESCHEDULED'):
                data = str(row.get('response_json', '') or '')
                if data:
                    return {'fingerprint':str(row.get('fingerprint','')), 'response':json.loads(data)}
        for row in reversed(self.appointments.get_all_records(default_blank='')):
            if str(row.get('request_id','')) == request_id and str(row.get('status','')) == 'ACTIVE':
                return {'fingerprint':str(row.get('fingerprint','')),
                    'response':{'status':'BOOKED',
                        'message':f"Confirmed appointment for {row.get('pet_name','')} ({row.get('reference','')})",
                        'reference':row.get('reference',''),
                        'appointment':{'pet':row.get('pet_name',''), 'service_id':row.get('service_id',''),
                          'provider':row.get('provider',''), 'start_local':row.get('start_local',''),
                          'end_local':row.get('end_local',''), 'timezone':'America/Phoenix'}}}
        return None

    def create_appointment(self, row: dict[str,Any]) -> None:
        self.appointments.append_row([str(row.get(k,'') or '') for k in APPOINTMENT_COLUMNS], value_input_option='RAW')

    def find_appointment(self, reference: str) -> dict[str,Any] | None:
        for index, row in enumerate(self.appointments.get_all_records(default_blank=''), start=2):
            if str(row.get('reference','')).upper() == reference.upper():
                row['_row_index'] = index
                return row
        return None

    def update_appointment(self, reference: str, changes: dict[str,Any]) -> None:
        existing = self.find_appointment(reference)
        if not existing: raise RuntimeError('Appointment row missing during update')
        existing.update(changes)
        index = existing['_row_index']
        self.appointments.update(range_name=f'A{index}:N{index}',
            values=[[str(existing.get(k,'') or '') for k in APPOINTMENT_COLUMNS]],
            value_input_option='RAW')

    def log(self, *, request_id: str, message: str, intent: str, status: str,
            response: dict[str,Any], fingerprint: str) -> None:
        row = {'request_id':request_id, 'timestamp':datetime.now(TZ).isoformat(),
               'message':message, 'interpreted_intent':intent,
               'result_status':status,'response':response.get('message',''),
               'reference':response.get('reference',''), 'fingerprint':fingerprint,
               'response_json':json.dumps(response,ensure_ascii=False,separators=(',',':'))}
        self.calllog.append_row([str(row.get(k,'') or '') for k in CALL_LOG_COLUMNS], value_input_option='RAW')

class GoogleCalendar:
    def __init__(self, credentials: Credentials):
        self.api = build('calendar','v3',credentials=credentials,cache_discovery=False)

    @staticmethod
    def _when(part: dict[str,Any]) -> datetime:
        if 'dateTime' in part:
            value = datetime.fromisoformat(part['dateTime'].replace('Z','+00:00'))
            return value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)
        return datetime.combine(date.fromisoformat(part['date']),time.min,tzinfo=TZ)

    def busy(self, calendar_id: str, start: datetime, end: datetime, exclude_id: str | None = None) -> list[dict[str,Any]]:
        output=[]
        token=None
        while True:
            result = self.api.events().list(calendarId=calendar_id,
                timeMin=start.isoformat(),timeMax=end.isoformat(),singleEvents=True,
                maxResults=250, pageToken=token, showDeleted=False).execute()
            for event in result.get('items',[]):
                if event.get('status') == 'cancelled' or event.get('id') == exclude_id: continue
                if 'start' not in event or 'end' not in event: continue
                a,b = self._when(event['start']), self._when(event['end'])
                if a < end and b > start:
                    output.append({'start':a, 'end':b, 'id':event.get('id','')})
            token=result.get('nextPageToken')
            if not token: break
        return output

    def create(self, calendar_id: str, *, reference: str, pet: str, service: str,
               owner: str, start: datetime, end: datetime) -> str:
        body={'summary':f'{service} — {pet} ({reference})',
              'description':f'MMVH appointment reference: {reference}\nPet: {pet}\nOwner: {owner}',
              'start':{'dateTime':start.isoformat(),'timeZone':'America/Phoenix'},
              'end':{'dateTime':end.isoformat(),'timeZone':'America/Phoenix'},
              'extendedProperties':{'private':{'mmvh_reference':reference}}}
        result=self.api.events().insert(calendarId=calendar_id,body=body).execute()
        if not result.get('id'):
            raise RuntimeError('Calendar API did not return a usable event ID')
        return result['id']

    def delete(self, calendar_id: str, event_id: str) -> None:
        self.api.events().delete(calendarId=calendar_id,eventId=event_id).execute()

    def move(self, calendar_id: str, event_id: str, start: datetime, end: datetime) -> None:
        body={'start':{'dateTime':start.isoformat(),'timeZone':'America/Phoenix'},
              'end':{'dateTime':end.isoformat(),'timeZone':'America/Phoenix'}}
        self.api.events().patch(calendarId=calendar_id,eventId=event_id,body=body).execute()

    def get(self, calendar_id: str, event_id: str) -> dict[str,Any]:
        return self.api.events().get(calendarId=calendar_id,eventId=event_id).execute()
