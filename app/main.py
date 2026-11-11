from __future__ import annotations
import json
import hmac
import logging
import os
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from .models import CustomerRequest
from .interpreter import OpenAIInterpreter
from .agent import FrontDeskAgent
from .configuration import load_config

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
app=FastAPI(title='Meow Meow AI Front Desk',version='1.0.0')
BASE=Path(__file__).resolve().parent.parent

def runtime() -> dict:
    path=Path(os.getenv('MMVH_RUNTIME_CONFIG','/app/secrets/runtime.json'))
    if path.exists(): return json.loads(path.read_text())
    return {}

def get_agent() -> FrontDeskAgent:
    from .adapters import get_google_credentials, SheetsStore, GoogleCalendar
    cfg=runtime()
    sid=os.getenv('GOOGLE_SHEET_ID') or cfg.get('spreadsheet_id')
    if not sid: raise RuntimeError('Missing GOOGLE_SHEET_ID or bootstrap-generated secrets/runtime.json')
    google_creds=get_google_credentials(os.getenv('GOOGLE_TOKEN_FILE','/app/secrets/token.json'))
    store=SheetsStore(google_creds,sid)
    calendar=GoogleCalendar(google_creds)
    interpreter=OpenAIInterpreter(os.getenv('OPENAI_API_KEY',''),os.getenv('OPENAI_MODEL','gpt-4o-mini'))
    return FrontDeskAgent(store,calendar,interpreter)

@app.get('/health')
def health():
    return {'status':'ok','service':'mmvh-agent','integrations':'not verified by this endpoint'}

@app.get('/')
def index():
    return FileResponse(BASE/'static'/'index.html')

@app.get('/api/catalog')
def catalog():
    from .adapters import get_google_credentials, SheetsStore
    try:
        cfg=runtime()
        sid=os.getenv('GOOGLE_SHEET_ID') or cfg.get('spreadsheet_id')
        if not sid: raise RuntimeError('Google Sheets is not configured')
        store=SheetsStore(get_google_credentials(os.getenv('GOOGLE_TOKEN_FILE','/app/secrets/token.json')),sid)
        actual=load_config(store.load_config())
        return {'services':[{'id':s.id,'name':s.name,'duration_minutes':s.minutes,'provider':s.provider,
                  'species':sorted(s.species)} for s in actual.services.values()]}
    except Exception:
        logging.exception('Cannot load public service catalog')
        raise HTTPException(status_code=503,detail='Service catalog unavailable')

@app.post('/submit')
def submit_via_n8n(request: CustomerRequest):
    """The UI MUST execute the n8n workflow, not bypass it."""
    import httpx
    endpoint=os.getenv('N8N_WEBHOOK_URL','http://n8n:5678/webhook/mmvh-front-desk')
    try:
        response=httpx.post(endpoint,json=request.model_dump(exclude_none=True),timeout=60)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        logging.exception('n8n webhook unavailable')
        return {'status':'ERROR','message':'The n8n automation workflow could not be reached. No booking is confirmed.'}

@app.post('/api/requests')
def request_handler(request: CustomerRequest, x_internal_key: str | None = Header(None)):
    required=os.getenv('INTERNAL_API_KEY','')
    if not required or not x_internal_key or not hmac.compare_digest(x_internal_key,required):
        raise HTTPException(status_code=401,detail='Unauthorized workflow call')
    try:
        agent=get_agent()
        return agent.handle(request)
    except Exception:
        logging.exception('Agent initialization failed')
        return {'status':'ERROR','message':'The front-desk integrations are not configured or available. Please contact staff; no booking was made.'}
