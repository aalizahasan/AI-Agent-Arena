from __future__ import annotations
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from .models import ClinicConfig, Provider, Service

HEADERS = ['kind','key','name','value','days','open_time','close_time','lunch_start','lunch_end','species','provider','duration_min','calendar_id']
DAY_NAMES = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6}

def dayset(value: str) -> set[int]:
    parts = [p.strip().lower()[:3] for p in value.replace(',', '|').split('|') if p.strip()]
    if not parts or any(p not in DAY_NAMES for p in parts):
        raise ValueError('Invalid working days: '+value)
    return {DAY_NAMES[p] for p in parts}

def clock(value: str) -> time:
    return time.fromisoformat(value)

def load_config(rows: list[dict[str, str]]) -> ClinicConfig:
    """Read and validate the LIVE Config tab; no durations are hard-coded in business logic."""
    settings: dict[str, str] = {}
    providers: dict[str,Provider] = {}
    services: dict[str,Service] = {}
    for row in rows:
        kind = str(row.get('kind', '')).strip().lower()
        key = str(row.get('key','')).strip()
        if not key:
            continue
        if kind == 'setting':
            settings[key] = str(row.get('value','')).strip()
        elif kind == 'provider':
            provider = Provider(
                name=key, days=dayset(row['days']), opening=clock(row['open_time']),
                closing=clock(row['close_time']), lunch_start=clock(row['lunch_start']),
                lunch_end=clock(row['lunch_end']), calendar_id=str(row['calendar_id']).strip())
            if not provider.calendar_id: raise ValueError('Provider calendar ID is missing: '+key)
            providers[key] = provider
        elif kind == 'service':
            value = Service(
                id=key, name=str(row['name']).strip(),
                species={v.strip().lower() for v in row['species'].split('|') if v.strip()},
                provider=str(row['provider']).strip(), minutes=int(row['duration_min']))
            if not value.name or not value.species or not (0 < value.minutes <= 480):
                raise ValueError('Invalid service definition: '+key)
            services[key] = value
    tz = ZoneInfo(settings['timezone'])
    if settings['timezone'] != 'America/Phoenix':
        raise ValueError('The competition requires America/Phoenix')
    arena_now = datetime.fromisoformat(settings['arena_now'])
    if arena_now.tzinfo is None: arena_now=arena_now.replace(tzinfo=tz)
    if arena_now.astimezone(tz).strftime('%Y-%m-%d %H:%M') != '2026-11-11 09:00':
        raise ValueError('ARENA_NOW must remain 2026-11-11 09:00 clinic time')
    if set(services) != {'S1','S2','S3'}:
        raise ValueError('Config must provide official S1, S2 and S3 services')
    for service in services.values():
        if service.provider not in providers: raise ValueError('Unknown service provider: '+service.provider)
    if set(providers) != {'Mr Saanp', 'Miss Loomri'}:
        raise ValueError('Config must contain the two official veterinarians')
    return ClinicConfig(timezone=tz, arena_now=arena_now.astimezone(tz),
        opening=clock(settings['clinic_open']), closing=clock(settings['clinic_close']),
        clinic_days=dayset(settings['clinic_days']),
        holiday={date.fromisoformat(x.strip()) for x in settings['holidays'].split('|') if x.strip()},
        min_lead_minutes=int(settings['min_lead_minutes']),
        final_date=date.fromisoformat(settings['final_date']),
        grid_minutes=int(settings['grid_minutes']), providers=providers, services=services)

def initial_rows(calendars: dict[str,str]) -> list[dict[str,str]]:
    def setting(k,v): return {'kind':'setting','key':k,'value':str(v)}
    def provider(k, days): return {'kind':'provider','key':k,'name':k,'days':days,
        'open_time':'09:00','close_time':'17:00','lunch_start':'12:00','lunch_end':'13:00',
        'calendar_id':calendars[k]}
    def service(k,n,species,doctor,minutes): return {'kind':'service','key':k,'name':n,
        'species':species,'provider':doctor,'duration_min':str(minutes)}
    return [setting('timezone','America/Phoenix'),setting('arena_now','2026-11-11T09:00:00-07:00'),
        setting('clinic_days','Mon|Tue|Wed|Thu|Fri'),setting('clinic_open','09:00'),
        setting('clinic_close','17:00'),setting('holidays','2026-11-19'),
        setting('min_lead_minutes',60),setting('grid_minutes',15),setting('final_date','2026-11-25'),
        provider('Mr Saanp','Mon|Tue|Wed|Thu|Fri'),provider('Miss Loomri','Mon|Wed|Fri'),
        service('S1','Wellness Exam','dog|cat','Mr Saanp',30),
        service('S2','Routine Follow-up','dog|cat','Mr Saanp',30),
        service('S3','Exotic Exam','rabbit|bird','Miss Loomri',45)]
