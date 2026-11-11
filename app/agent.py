from __future__ import annotations
import hashlib
import json
import logging
import re
import secrets
from dataclasses import replace
from datetime import date, datetime, timedelta, time
from typing import Any
from .configuration import load_config
from .models import CustomerRequest, Interpretation, ClinicConfig, Service

log = logging.getLogger('mmvh')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
MEDICAL_RE = re.compile(r'\b(?:vomit\w*|sick|illness|injur\w*|bleed\w*|blood|fever|cough\w*|limp\w*|diarrh\w*|seizure\w*|unconscious|poison\w*|chok\w*|dying|collapsed?|not breathing|cannot breathe|emergen\w*|urgent|diagnos\w*|medicine|medication|dosage|dose|prescri\w*|pain|breath\w*|wound\w*|letharg\w*|treat\w*|symptom\w*|not eating|stopped eating)\b', re.I)
MULTI_RE = re.compile(r'\b(?:two|2|three|3|both|multiple|several)\b.{0,45}\b(?:pets?|dogs?|cats?|appointments?|visits?)\b', re.I)
PRIVACY_RE = re.compile(r'\b(?:all|other|another|every)\b.{0,35}\b(?:clients?|customers?|patients?|appointments?|emails?|records?)\b',re.I)
VERIFY_FAILURE = "We couldn't verify an active appointment using those details. Please check your reference and email."

def fingerprint(req: CustomerRequest) -> str:
    payload = req.model_dump(exclude_none=True)
    for key in ('email','species','service_id'):
        if key in payload and isinstance(payload[key],str): payload[key] = payload[key].strip().lower()
    payload['message'] = payload['message'].strip()
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalize(field: str, value: str | None) -> str | None:
    if not isinstance(value,str) or not value.strip(): return None
    value=value.strip()
    if field in {'email','species'}: return value.lower()
    if field in {'reference','service_id'}: return value.upper()
    if field == 'requested_time':
        try: return time.fromisoformat(value).strftime('%H:%M')
        except ValueError: return value.lower()
    if field == 'requested_date':
        try: return date.fromisoformat(value).isoformat()
        except ValueError: return value.lower()
    return ' '.join(value.split()).casefold()

def merge_fields(req: CustomerRequest, parsed: Interpretation, fields: list[str]) -> tuple[dict[str,str|None], list[str]]:
    merged={}
    conflicts=[]
    for field in fields:
        a=getattr(req,field,None)
        b=getattr(parsed,field,None)
        if a and b and normalize(field,a) != normalize(field,b): conflicts.append(field)
        merged[field]=(a or b)
    return merged,conflicts

def clock_display(value: datetime) -> str:
    return value.strftime('%-I:%M %p')

def overlap(busy: list[dict[str,Any]], start: datetime, end: datetime) -> bool:
    return any(item['start'] < end and item['end'] > start for item in busy)

class FrontDeskAgent:
    """LLM chooses actions, deterministic rules guard side effects, tools verify external results."""
    def __init__(self, store, calendar, interpreter):
        self.store=store
        self.calendar=calendar
        self.interpreter=interpreter

    @staticmethod
    def result(status: str, message: str, **fields) -> dict[str,Any]:
        return {'status':status,'message':message,**fields}

    def finish(self, req: CustomerRequest, intent: str, response: dict[str,Any], fp: str) -> dict[str,Any]:
        try:
            self.store.log(request_id=req.request_id,message=req.message,intent=intent,
                status=response['status'],response=response,fingerprint=fp)
        except Exception as exc:
            log.exception('Audit Sheets logging failed for request %s: %s', req.request_id,exc)
            return self.result('NEEDS_ATTENTION',
                'The requested operation could not be fully audited. Please contact staff before retrying.',
                reference=response.get('reference'), execution_request_id=req.request_id)
        return response

    def handle(self, req: CustomerRequest) -> dict[str,Any]:
        fp=fingerprint(req)
        intent='UNKNOWN'
        try:
            old=self.store.find_processed(req.request_id)
            if old:
                if old['fingerprint'] != fp:
                    return self.finish(req,'REPLAY',self.result('ERROR',
                        'This request_id has already been used with different details. Please submit a new request_id.'),fp)
                response=old['response']
                try:
                    self.store.log(request_id=req.request_id,message=req.message,intent='REPLAY',
                        status='REPLAY',response=response,fingerprint=fp)
                except Exception: log.exception('Unable to log duplicate request %s',req.request_id)
                return response
            config=load_config(self.store.load_config())
            if MEDICAL_RE.search(req.message):
                return self.finish(req,'HANDOFF',self.result('HANDOFF',
                    'This request needs a veterinary staff member. Please contact the clinic staff directly for help; I cannot provide medical advice or arrange an appointment from this message.',
                    handoff_reason='Medical, symptom, medication or urgent-help request'),fp)
            if PRIVACY_RE.search(req.message) and re.search(r'\b(?:list|show|give|send|reveal|export|view)\b',req.message,re.I):
                return self.finish(req,'UNSUPPORTED',self.result('HANDOFF',
                    'I cannot disclose private customer records. Please contact clinic staff for assistance.',
                    handoff_reason='Private-record access requested'),fp)
            parsed=self.interpreter.interpret(req)
            intent=parsed.intent
            if intent == 'HANDOFF':
                return self.finish(req,intent,self.result('HANDOFF',
                    'Please contact a clinic staff member directly for this request. I cannot provide medical assessments or medication advice.',
                    handoff_reason=parsed.handoff_reason or 'Staff assistance requested'),fp)
            if intent == 'UNSUPPORTED':
                return self.finish(req,intent,self.result('HANDOFF',
                    'This request is not supported by online scheduling. Please contact clinic staff for assistance.',
                    handoff_reason='Unsupported customer request'),fp)
            if intent in ('GENERAL_HELP','CLARIFY'):
                return self.finish(req,intent,self.result('NEEDS_INFO',
                    'I can book, cancel or reschedule veterinary appointments. We offer Wellness Exams and Routine Follow-ups for dogs and cats, and Exotic Exams for rabbits and birds. What would you like to do?'),fp)
            if intent == 'BOOK' and (parsed.multiple_appointments or MULTI_RE.search(req.message)):
                return self.finish(req,'BOOK',self.result('NEEDS_INFO',
                    'Please submit one pet and one appointment at a time. Which single pet would you like to book first?'),fp)
            if intent == 'BOOK': return self.book(req,parsed,config,fp)
            if intent == 'CANCEL': return self.cancel(req,parsed,config,fp)
            if intent == 'RESCHEDULE': return self.reschedule(req,parsed,config,fp)
            return self.finish(req,intent,self.result('NEEDS_INFO','Please specify whether you want to book, cancel, or reschedule an appointment.'),fp)
        except Exception as exc:
            log.exception('Request %s failed: %s',req.request_id,exc)
            return self.finish(req,intent,self.result('ERROR',
                'A technical problem prevented us from completing your request. No successful action can be confirmed. Please contact clinic staff or retry with a new request ID.',
                execution_request_id=req.request_id),fp)

    def _start(self, fields: dict[str,str|None], config: ClinicConfig) -> datetime | None:
        if not fields.get('requested_date') or not fields.get('requested_time'): return None
        try:
            day=date.fromisoformat(str(fields['requested_date']))
            requested_time=time.fromisoformat(str(fields['requested_time']))
            if requested_time.tzinfo is not None:
                raise ValueError('Time must be clinic local')
            return config.local_datetime(day,requested_time)
        except ValueError: return None

    def _service(self, config: ClinicConfig, value: str | None, species: str | None) -> tuple[Service | None,str]:
        if not value: return None, ''
        code=value.strip().upper()
        lookup={s.name.casefold():s for s in config.services.values()}
        service=config.services.get(code) or lookup.get(value.strip().casefold())
        if service is None: return None, 'That service is not supported by the clinic.'
        if not species or species.strip().lower() not in service.species:
            return None, 'The requested species and service combination is not supported.'
        return service,''

    def _missing(self, fields:dict, keys: list[str]) -> list[str]:
        return [k for k in keys if not fields.get(k)]

    def _validation(self, cfg: ClinicConfig, svc:Service, start:datetime):
        return cfg.valid_slot(svc,start)

    def _alternatives(self, cfg:ClinicConfig, svc:Service, requested:datetime) -> list[dict[str,str]]:
        if requested.date() > cfg.final_date: return []
        days=[]
        current=requested.date()
        requested_workday = (current.weekday() in cfg.clinic_days and current not in cfg.holiday)
        # Include requested workday, if open, and the next two clinic working days.
        max_days = 3 if requested_workday else 2
        while len(days) < max_days and current <= cfg.final_date:
            if current.weekday() in cfg.clinic_days and current not in cfg.holiday:
                days.append(current)
            current += timedelta(days=1)
        results=[]
        provider=cfg.providers[svc.provider]
        for day in days:
            if day.weekday() not in provider.days: continue
            start_day=cfg.local_datetime(day,cfg.opening)
            end_day=cfg.local_datetime(day,cfg.closing)
            events=self.calendar.busy(provider.calendar_id,start_day,end_day)
            candidate=start_day
            while candidate < end_day and len(results)<3:
                end=candidate+timedelta(minutes=svc.minutes)
                if candidate >= requested and cfg.valid_slot(svc,candidate)[0] and not overlap(events,candidate,end):
                    results.append({'start_local':candidate.isoformat(),'end_local':end.isoformat(),
                        'display':f'{candidate.strftime("%d %B %Y")} at {clock_display(candidate)}'})
                candidate += timedelta(minutes=cfg.grid_minutes)
            if len(results)>=3: break
        return results

    def book(self,req:CustomerRequest,parsed:Interpretation,cfg:ClinicConfig,fp:str) -> dict[str,Any]:
        fields,conflicts=merge_fields(req,parsed,['owner_name','email','pet_name','species','service_id','requested_date','requested_time'])
        if 'service_id' in conflicts:
            structured=req.service_id or ''
            extracted=parsed.service_id or ''
            codes={s.name.casefold():s.id for s in cfg.services.values()}
            a=codes.get(structured.casefold(),structured.upper())
            b=codes.get(extracted.casefold(),extracted.upper())
            if a==b:
                conflicts.remove('service_id')
                fields['service_id']=a
        if conflicts:
            return self.finish(req,'BOOK',self.result('NEEDS_INFO',
                'Your message and form contain different values for: '+', '.join(conflicts)+'. Please clarify which details are correct.'),fp)
        # Unsupported services are staff handoffs even if other fields are incomplete.
        if fields.get('service_id'):
            selected = fields['service_id'].strip().casefold()
            known_services = {s.id.casefold() for s in cfg.services.values()} | {s.name.casefold() for s in cfg.services.values()}
            if selected not in known_services:
                reason = 'This service is not offered by the online clinic schedule.'
                return self.finish(req,'BOOK',self.result('HANDOFF',
                    reason+' Please contact clinic staff for help.',handoff_reason=reason),fp)
        # Unsupported pet species need a staff handoff even if other fields are missing.
        known_species={species for service in cfg.services.values() for species in service.species}
        if fields.get('species') and fields['species'].strip().lower() not in known_species:
            reason='This pet species is not supported by the online appointment service.'
            return self.finish(req,'BOOK',self.result('HANDOFF',reason+' Please contact clinic staff for help.',handoff_reason=reason),fp)
        missing=self._missing(fields,['owner_name','email','pet_name','species','service_id','requested_date','requested_time'])
        if missing:
            return self.finish(req,'BOOK',self.result('NEEDS_INFO','Please provide: '+', '.join(missing).replace('_',' ')+'.',missing_fields=missing),fp)
        if not EMAIL_RE.fullmatch(fields['email'] or ''):
            return self.finish(req,'BOOK',self.result('NEEDS_INFO','Please provide a valid owner email address.'),fp)
        svc,reason=self._service(cfg,fields['service_id'],fields['species'])
        if not svc:
            return self.finish(req,'BOOK',self.result('HANDOFF',reason+' Please contact clinic staff for help.',handoff_reason=reason),fp)
        start=self._start(fields,cfg)
        if not start:
            return self.finish(req,'BOOK',self.result('NEEDS_INFO','Please provide a valid exact date (YYYY-MM-DD) and clinic-local time (HH:MM).'),fp)
        ok,reason=cfg.valid_slot(svc,start)
        if not ok:
            return self.finish(req,'BOOK',self.result('UNAVAILABLE',reason,alternatives=self._alternatives(cfg,svc,start)),fp)
        end=start+timedelta(minutes=svc.minutes)
        provider=cfg.providers[svc.provider]
        if overlap(self.calendar.busy(provider.calendar_id,start,end),start,end):
            return self.finish(req,'BOOK',self.result('UNAVAILABLE',
                'That slot overlaps an existing event on the veterinarian calendar. Please choose another time.',
                alternatives=self._alternatives(cfg,svc,start)),fp)
        reference='MMVH-'+secrets.token_hex(5).upper()
        event_id=self.calendar.create(provider.calendar_id,reference=reference,pet=fields['pet_name'],
            service=svc.name,owner=fields['owner_name'],start=start,end=end)
        record={'reference':reference,'owner_name':fields['owner_name'],'email':fields['email'].lower(),
            'pet_name':fields['pet_name'],'species':fields['species'].lower(),'service_id':svc.id,
            'provider':svc.provider,'start_local':start.isoformat(),'end_local':end.isoformat(),
            'event_id':event_id,'status':'ACTIVE','request_id':req.request_id,'fingerprint':fp,
            'updated_at':datetime.now(cfg.timezone).isoformat()}
        try:
            self.store.create_appointment(record)
        except Exception as exc:
            log.exception('Appointment row write failed; attempting Calendar compensation %s',reference)
            try:
                self.calendar.delete(provider.calendar_id,event_id)
                return self.finish(req,'BOOK',self.result('ERROR',
                    'The appointment could not be recorded, so the new Calendar event was removed. Please try again.'),fp)
            except Exception:
                log.exception('Calendar compensation failed event=%s',event_id)
                return self.finish(req,'BOOK',self.result('NEEDS_ATTENTION',
                    'A Calendar event exists but the appointment record could not be saved. Staff reconciliation is required.',
                    reference=reference,event_id=event_id),fp)
        response=self.result('BOOKED',
            f'Confirmed: {fields["pet_name"]} — {svc.name} with {svc.provider} on {start.strftime("%d %B %Y")} at {clock_display(start)} (America/Phoenix). Reference: {reference}.',
            reference=reference,appointment={'pet':fields['pet_name'],'service':svc.name,
            'service_id':svc.id,'provider':svc.provider,'start_local':start.isoformat(),
            'end_local':end.isoformat(),'timezone':'America/Phoenix'})
        return self.finish(req,'BOOK',response,fp)

    def _verify(self, reference: str | None, email: str | None) -> dict[str,Any] | None:
        if not reference or not email or not EMAIL_RE.fullmatch(email.strip()): return None
        row=self.store.find_appointment(reference.strip())
        if not row or str(row.get('status','')).upper() != 'ACTIVE': return None
        if str(row.get('email','')).strip().casefold()!=email.strip().casefold(): return None
        return row

    def cancel(self,req:CustomerRequest,parsed:Interpretation,cfg:ClinicConfig,fp:str) -> dict[str,Any]:
        fields,conflicts=merge_fields(req,parsed,['reference','email'])
        if conflicts:
            return self.finish(req,'CANCEL',self.result('NEEDS_INFO',
                'The message and form contain conflicting verification details. Please submit the correct reference and email.'),fp)
        if not fields.get('reference') or not fields.get('email'):
            return self.finish(req,'CANCEL',self.result('NEEDS_INFO','To cancel, please provide the appointment reference and owner email.'),fp)
        row=self._verify(fields['reference'],fields['email'])
        if not row:
            return self.finish(req,'CANCEL',self.result('VERIFICATION_FAILED',VERIFY_FAILURE),fp)
        calendar_id=cfg.providers[str(row['provider'])].calendar_id
        self.calendar.delete(calendar_id,str(row['event_id']))
        try:
            self.store.update_appointment(str(row['reference']),{
                'status':'CANCELED','updated_at':datetime.now(cfg.timezone).isoformat()})
        except Exception:
            log.exception('Cancellation succeeded in Calendar but Sheets update failed ref=%s',row['reference'])
            return self.finish(req,'CANCEL',self.result('NEEDS_ATTENTION',
                'The Calendar event was removed, but records need staff reconciliation.',reference=row['reference']),fp)
        return self.finish(req,'CANCEL',self.result('CANCELED',
            'Your appointment has been canceled successfully.',reference=row['reference']),fp)

    def reschedule(self,req:CustomerRequest,parsed:Interpretation,cfg:ClinicConfig,fp:str) -> dict[str,Any]:
        fields,conflicts=merge_fields(req,parsed,['reference','email','requested_date','requested_time'])
        if conflicts:
            return self.finish(req,'RESCHEDULE',self.result('NEEDS_INFO',
                'Your message and form disagree about: '+', '.join(conflicts)+'. Please confirm the correct values.'),fp)
        missing=self._missing(fields,['reference','email','requested_date','requested_time'])
        if missing:
            return self.finish(req,'RESCHEDULE',self.result('NEEDS_INFO','To reschedule, please provide: '+', '.join(missing).replace('_',' ')+'.'),fp)
        row=self._verify(fields['reference'],fields['email'])
        if not row:
            return self.finish(req,'RESCHEDULE',self.result('VERIFICATION_FAILED',VERIFY_FAILURE),fp)
        start=self._start(fields,cfg)
        if not start:
            return self.finish(req,'RESCHEDULE',self.result('NEEDS_INFO','Please specify an exact replacement date and time.'),fp)
        original_start=datetime.fromisoformat(str(row['start_local'])).astimezone(cfg.timezone)
        original_end=datetime.fromisoformat(str(row['end_local'])).astimezone(cfg.timezone)
        duration=int((original_end-original_start).total_seconds()/60)
        original_service=cfg.services[str(row['service_id'])]
        service=replace(original_service,minutes=duration)
        ok,reason=cfg.valid_slot(service,start)
        if not ok:
            return self.finish(req,'RESCHEDULE',self.result('UNAVAILABLE',reason,
                alternatives=self._alternatives(cfg,service,start)),fp)
        end=start+timedelta(minutes=duration)
        calendar_id=cfg.providers[str(row['provider'])].calendar_id
        if overlap(self.calendar.busy(calendar_id,start,end,exclude_id=str(row['event_id'])),start,end):
            return self.finish(req,'RESCHEDULE',self.result('UNAVAILABLE',
                'The replacement time conflicts with another event.',
                alternatives=self._alternatives(cfg,service,start)),fp)
        self.calendar.move(calendar_id,str(row['event_id']),start,end)
        try:
            self.store.update_appointment(str(row['reference']),{
                'start_local':start.isoformat(),'end_local':end.isoformat(),
                'updated_at':datetime.now(cfg.timezone).isoformat()})
        except Exception:
            log.exception('Sheets failed after reschedule; rolling Calendar back')
            try:
                self.calendar.move(calendar_id,str(row['event_id']),original_start,original_end)
                return self.finish(req,'RESCHEDULE',self.result('ERROR',
                    'Rescheduling could not be recorded; your original appointment time was restored.'),fp)
            except Exception:
                log.exception('Reschedule compensation failed ref=%s',row['reference'])
                return self.finish(req,'RESCHEDULE',self.result('NEEDS_ATTENTION',
                    'The Calendar time changed but the appointment record could not be synchronized. Staff must reconcile it.',
                    reference=row['reference'],event_id=row['event_id']),fp)
        return self.finish(req,'RESCHEDULE',self.result('RESCHEDULED',
            f'Your appointment {row["reference"]} has been moved to {start.strftime("%d %B %Y")} at {clock_display(start)} (America/Phoenix).',
            reference=row['reference'],appointment={'pet':row['pet_name'],
                'service':service.name,'provider':service.provider,'start_local':start.isoformat(),
                'end_local':end.isoformat(),'timezone':'America/Phoenix'}),fp)
