from datetime import datetime
import pytest
from app.models import Interpretation
from .conftest import canceled_or_rescheduled,CALENDARS
from .test_booking import local

def setup_booked(system,booking):
    agent,store,cal,llm=system
    result=agent.handle(booking)
    assert result['status']=='BOOKED'
    return result['reference']

def test_cancel_securely_deletes_and_retains_row(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='CANCEL')
    req=canceled_or_rescheduled('cancel',ref,email='ALEX@EXAMPLE.COM')
    result=agent.handle(req)
    assert result['status']=='CANCELED'
    assert store.appointments[0]['status']=='CANCELED'
    assert not cal.events and len(cal.deleted)==1 and len(store.calllog)==2

def test_same_verification_failure_for_wrong_email_and_unknown_ref(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='CANCEL')
    wrong=agent.handle(canceled_or_rescheduled('cancel',ref,email='hacker@example.com',id='CANCEL-WRONG'))
    unknown=agent.handle(canceled_or_rescheduled('cancel','MMVH-NOTFOUND',id='CANCEL-NOTFOUND'))
    assert wrong['status']=='VERIFICATION_FAILED'
    assert wrong['message']==unknown['message']
    assert not cal.deleted and store.appointments[0]['status']=='ACTIVE'

def test_cancel_missing_reference(system,booking):
    agent,store,cal,llm=system
    llm.decision=Interpretation(intent='CANCEL')
    assert agent.handle(canceled_or_rescheduled('cancel',None))['status']=='NEEDS_INFO'

def test_cancel_calendar_failure_no_confirmation(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='CANCEL')
    cal.fail_delete=True
    assert agent.handle(canceled_or_rescheduled('cancel',ref))['status']=='ERROR'
    assert store.appointments[0]['status']=='ACTIVE'

def test_cancel_sheet_failure_needs_reconciliation(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='CANCEL')
    store.update_fail=True
    assert agent.handle(canceled_or_rescheduled('cancel',ref))['status']=='NEEDS_ATTENTION'
    assert not cal.events

def test_reschedule_same_reference_and_row(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    event_id=store.appointments[0]['event_id']
    llm.decision=Interpretation(intent='RESCHEDULE')
    result=agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-18',clock='10:15',id='MOVE-1'))
    assert result['status']=='RESCHEDULED' and result['reference']==ref
    assert len(store.appointments)==1 and store.appointments[0]['event_id']==event_id
    assert cal.events[event_id]['start'].day==18 and cal.events[event_id]['start'].minute==15

def test_reschedule_ignores_own_event(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='RESCHEDULE')
    assert agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-16',clock='10:00',id='MOVE-SAME'))['status']=='RESCHEDULED'

def test_reschedule_detects_other_manual_meeting(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    old=store.appointments[0]['start_local']
    cal.block(CALENDARS['Mr Saanp'],local('2026-11-18',11),local('2026-11-18',11,30))
    llm.decision=Interpretation(intent='RESCHEDULE')
    result=agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-18',clock='11:15',id='MOVE-CONFLICT'))
    assert result['status']=='UNAVAILABLE' and store.appointments[0]['start_local']==old and cal.moved==[]

def test_reschedule_calendar_failure_preserves_original(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    old=store.appointments[0]['start_local']
    cal.fail_move=True
    llm.decision=Interpretation(intent='RESCHEDULE')
    assert agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-18',clock='10:00',id='MOVE-FAIL'))['status']=='ERROR'
    assert store.appointments[0]['start_local']==old

def test_reschedule_sheets_failure_rolls_back_calendar(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    old=store.appointments[0]['start_local']
    event_id=store.appointments[0]['event_id']
    store.update_fail=True
    llm.decision=Interpretation(intent='RESCHEDULE')
    assert agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-18',clock='10:00',id='MOVE-ROLLBACK'))['status']=='ERROR'
    assert store.appointments[0]['start_local']==old
    assert cal.events[event_id]['start'].isoformat()==old
    assert len(cal.moved)==2

def test_reschedule_existing_duration_kept_after_config_change(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    for row in store.config:
        if row.get('key')=='S1':row['duration_min']='45'
    llm.decision=Interpretation(intent='RESCHEDULE')
    assert agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-18',clock='10:00',id='MOVE-E4'))['status']=='RESCHEDULED'
    a=store.appointments[0]
    assert (datetime.fromisoformat(a['end_local'])-datetime.fromisoformat(a['start_local'])).total_seconds()==30*60

def test_reschedule_new_time_lead_invalid(system,booking):
    agent,store,cal,llm=system
    ref=setup_booked(system,booking)
    llm.decision=Interpretation(intent='RESCHEDULE')
    assert agent.handle(canceled_or_rescheduled('reschedule',ref,day='2026-11-11',clock='09:45',id='MOVE-LEAD'))['status']=='UNAVAILABLE'
