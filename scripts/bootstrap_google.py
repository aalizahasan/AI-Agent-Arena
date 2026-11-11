#!/usr/bin/env python3
"""One-time authenticated setup: creates calendars and Sheets. Tokens never committed."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
from app.adapters import SCOPES, CONFIG_COLUMNS, APPOINTMENT_COLUMNS, CALL_LOG_COLUMNS
from app.configuration import initial_rows

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
SECRETS=ROOT/'secrets'
SECRETS.mkdir(exist_ok=True)
TOKEN=SECRETS/'token.json'
CLIENT=SECRETS/'client_secret.json'
RUNTIME=SECRETS/'runtime.json'

def auth():
    creds=None
    if TOKEN.exists(): creds=Credentials.from_authorized_user_file(str(TOKEN),SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT.exists():
                sys.exit('Missing secrets/client_secret.json: create Desktop OAuth credentials in Google Cloud.')
            flow=InstalledAppFlow.from_client_secrets_file(str(CLIENT),SCOPES)
            creds=flow.run_local_server(port=0,access_type='offline',prompt='consent')
        TOKEN.write_text(creds.to_json())
    return creds

def main():
    judge=os.getenv('JUDGE_EMAIL','').strip()
    if not judge: print('JUDGE_EMAIL missing. Share resources manually before judging.')
    creds=auth()
    cal=build('calendar','v3',credentials=creds,cache_discovery=False)
    sheets=build('sheets','v4',credentials=creds,cache_discovery=False)
    drive=build('drive','v3',credentials=creds,cache_discovery=False)
    runtime=json.loads(RUNTIME.read_text()) if RUNTIME.exists() else {}
    calendars=runtime.setdefault('calendars',{})
    for doctor in ('Mr Saanp','Miss Loomri'):
        if doctor not in calendars:
            resource=cal.calendars().insert(body={'summary':f'MMVH - {doctor}',
                'timeZone':'America/Phoenix'}).execute()
            calendars[doctor]=resource['id']
            RUNTIME.write_text(json.dumps(runtime,indent=2))
        print(doctor,':',calendars[doctor])
        if judge:
            try:
                cal.acl().insert(calendarId=calendars[doctor],
                    body={'role':'writer','scope':{'type':'user','value':judge}}).execute()
                print('Judge edit access granted for',doctor)
            except Exception as e: print('Share calendar manually if needed:',str(e)[:150])
    if 'spreadsheet_id' not in runtime:
        resource=sheets.spreadsheets().create(body={'properties':{
            'title':'MMVH — AI Agents Arena 2.0',
            'timeZone':'America/Phoenix'},
            'sheets':[{'properties':{'title':name}} for name in ('Config','Appointments','CallLog')]},
            fields='spreadsheetId').execute()
        runtime['spreadsheet_id']=resource['spreadsheetId']
        RUNTIME.write_text(json.dumps(runtime,indent=2))
        def values(columns,rows):
            return [columns]+[[str(row.get(k,'') or '') for k in columns] for row in rows]
        sheet_id=runtime['spreadsheet_id']
        input_data=[
            {'range':'Config!A1:M15','values':values(CONFIG_COLUMNS,initial_rows(calendars))},
            {'range':'Appointments!A1:N1','values':[APPOINTMENT_COLUMNS]},
            {'range':'CallLog!A1:I1','values':[CALL_LOG_COLUMNS]},
        ]
        sheets.spreadsheets().values().batchUpdate(spreadsheetId=sheet_id,
            body={'valueInputOption':'RAW','data':input_data}).execute()
    print('Spreadsheet:',runtime['spreadsheet_id'])
    if judge:
        try:
            drive.permissions().create(fileId=runtime['spreadsheet_id'],
                body={'type':'user','role':'reader','emailAddress':judge},
                sendNotificationEmail=False).execute()
            print('Judge view access granted for spreadsheet')
        except Exception as e: print('Share spreadsheet manually if needed:',str(e)[:150])
    print('Runtime saved:',RUNTIME)
    print('No secrets should be committed. OAuth tokens stay in secrets/.')

if __name__=='__main__': main()
