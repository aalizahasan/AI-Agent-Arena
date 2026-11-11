from __future__ import annotations
from copy import deepcopy
import pytest
from app.agent import FrontDeskAgent
from app.configuration import initial_rows
from app.models import CustomerRequest, Interpretation

CALENDARS={'Mr Saanp':'test-saanp@group.calendar.google.com',
           'Miss Loomri':'test-loomri@group.calendar.google.com'}

class FakeStore:
    def __init__(self):
        self.config=initial_rows(CALENDARS)
        self.appointments=[]
        self.calllog=[]
        self.create_fail=False
        self.update_fail=False
        self.log_fail=False
        self.config_fail=False
        self.find_fail=False
    def load_config(self):
        if self.config_fail:raise RuntimeError('Google Sheets config unavailable')
        return deepcopy(self.config)
    def create_appointment(self,row):
        if self.create_fail:raise RuntimeError('Google Sheets append failed')
        self.appointments.append(deepcopy(row))
    def find_appointment(self,reference):
        if self.find_fail:raise RuntimeError('Google Sheets lookup failed')
        for row in self.appointments:
            if row['reference'].upper()==reference.upper():return deepcopy(row)
        return None
    def update_appointment(self,reference,changes):
        if self.update_fail:raise RuntimeError('Google Sheets update failed')
        for row in self.appointments:
            if row['reference'].upper()==reference.upper():row.update(changes);return
        raise RuntimeError('missing row')
    def log(self,*,request_id,message,intent,status,response,fingerprint):
        if self.log_fail:raise RuntimeError('CallLog unavailable')
        self.calllog.append({'request_id':request_id,'message':message,'intent':intent,
                             'status':status,'response':deepcopy(response),'fingerprint':fingerprint})
    def find_processed(self,request_id):
        for row in reversed(self.calllog):
            if row['request_id']==request_id and row['status'] in ('BOOKED','RESCHEDULED','CANCELED'):
                return {'fingerprint':row['fingerprint'],'response':deepcopy(row['response'])}
        for row in reversed(self.appointments):
            if row['request_id']==request_id and row['status']=='ACTIVE':
                return {'fingerprint':row['fingerprint'],
                        'response':{'status':'BOOKED','reference':row['reference'],
                        'message':'An existing booking is already recorded.'}}
        return None

class FakeCalendar:
    def __init__(self):
        self.events={}
        self.created=[]
        self.deleted=[]
        self.moved=[]
        self.fail_busy=False
        self.fail_create=False
        self.fail_delete=False
        self.fail_move=False
        self.id=0
    def block(self,calendar_id,start,end,all_day=False):
        self.id+=1
        event_id='manual-'+str(self.id)
        self.events[event_id]={'calendar':calendar_id,'start':start,'end':end,'all_day':all_day}
        return event_id
    def busy(self,calendar_id,start,end,exclude_id=None):
        if self.fail_busy:raise RuntimeError('Google Calendar unavailable')
        return [{'id':k, 'start':v['start'],'end':v['end']}
                for k,v in self.events.items() if v['calendar']==calendar_id
                and k!=exclude_id and v['start']<end and v['end']>start]
    def create(self,calendar_id,*,reference,pet,service,owner,start,end):
        if self.fail_create:raise RuntimeError('Google Calendar insert failed')
        self.id+=1
        event_id='created-'+str(self.id)
        self.events[event_id]={'calendar':calendar_id,'start':start,'end':end,
                               'reference':reference,'pet':pet}
        self.created.append(event_id)
        return event_id
    def delete(self,calendar_id,event_id):
        if self.fail_delete:raise RuntimeError('Google Calendar delete failed')
        if event_id not in self.events:raise RuntimeError('Google Calendar event missing')
        del self.events[event_id]
        self.deleted.append(event_id)
    def move(self,calendar_id,event_id,start,end):
        if self.fail_move:raise RuntimeError('Google Calendar patch failed')
        self.events[event_id].update(start=start,end=end)
        self.moved.append((event_id,start,end))

class FakeInterpreter:
    def __init__(self,decision=None):
        self.decision=decision or Interpretation(intent='BOOK')
        self.calls=0
        self.fail=False
    def interpret(self,request):
        self.calls+=1
        if self.fail:raise RuntimeError('LLM unavailable')
        return self.decision

@pytest.fixture
def system():
    store=FakeStore();cal=FakeCalendar();llm=FakeInterpreter()
    return FrontDeskAgent(store,cal,llm),store,cal,llm

@pytest.fixture
def booking():
    return CustomerRequest(request_id='TEST-01',message='Book a wellness exam for my dog Milo on 16 November 2026 at 10:00.',
       owner_name='Alex Khan',email='alex@example.com',pet_name='Milo',species='dog',
       service_id='S1',requested_date='2026-11-16',requested_time='10:00')

def canceled_or_rescheduled(intent,ref,email='alex@example.com',day=None,clock=None,id='CANCEL-01'):
    return CustomerRequest(request_id=id,message=f'{intent} {ref} for {email}'+
        (f' to {day} {clock}' if day else ''),reference=ref,email=email,
        requested_date=day,requested_time=clock)
