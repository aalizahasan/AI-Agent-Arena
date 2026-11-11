from app.interpreter import enforce_explicit_details
from app.models import Interpretation

def interpret(message,**kwargs):
    return enforce_explicit_details(message,Interpretation(intent='BOOK',**kwargs))

def test_tomorrow_uses_fixed_clinic_date():
    assert interpret('Book my dog tomorrow at 10 AM',requested_date='2026-11-13').requested_date=='2026-11-12'

def test_morning_not_exact_time():
    assert interpret('Book tomorrow morning',requested_time='10:00').requested_time is None

def test_explicit_10_am_preserved():
    assert interpret('Tomorrow morning at 10 AM',requested_time='10:00').requested_time=='10:00'

def test_ambiguous_numeric_date_rejected():
    assert interpret('Please book 11/12 at 10 AM',requested_date='2026-11-12').requested_date is None

def test_species_plural_normalized():
    assert interpret('Book an exam for my dogs',species='dogs').species=='dog'


def test_model_cannot_invent_exact_time_when_no_time_was_given():
    assert interpret('Please book a wellness exam on November 16 for Milo',requested_time='10:00').requested_time is None
