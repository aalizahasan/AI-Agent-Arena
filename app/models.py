from __future__ import annotations
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field, field_validator

TZ = ZoneInfo('America/Phoenix')
DEFAULT_ARENA_NOW = datetime(2026, 11, 11, 9, 0, tzinfo=TZ)

class CustomerRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=4000)
    owner_name: Optional[str] = None
    email: Optional[str] = None
    pet_name: Optional[str] = None
    species: Optional[str] = None
    service_id: Optional[str] = None
    requested_date: Optional[str] = None
    requested_time: Optional[str] = None
    reference: Optional[str] = None
    @field_validator('request_id')
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(c.isalnum() or c in '-_.' for c in value):
            raise ValueError('request_id must contain only letters, numbers, hyphen, underscore or period')
        return value

class Interpretation(BaseModel):
    intent: str
    owner_name: Optional[str] = None
    email: Optional[str] = None
    pet_name: Optional[str] = None
    species: Optional[str] = None
    service_id: Optional[str] = None
    requested_date: Optional[str] = None
    requested_time: Optional[str] = None
    reference: Optional[str] = None
    handoff_reason: Optional[str] = None
    multiple_appointments: bool = False

@dataclass(frozen=True)
class Provider:
    name: str
    days: set[int]
    opening: time
    closing: time
    lunch_start: time
    lunch_end: time
    calendar_id: str

@dataclass(frozen=True)
class Service:
    id: str
    name: str
    species: set[str]
    provider: str
    minutes: int

@dataclass(frozen=True)
class ClinicConfig:
    timezone: ZoneInfo
    arena_now: datetime
    opening: time
    closing: time
    clinic_days: set[int]
    holiday: set[date]
    min_lead_minutes: int
    final_date: date
    grid_minutes: int
    providers: dict[str, Provider]
    services: dict[str, Service]

    def local_datetime(self, day: date, clock: time) -> datetime:
        return datetime.combine(day, clock, self.timezone)

    def valid_slot(self, service: Service, start: datetime) -> tuple[bool, str]:
        if start.tzinfo is None:
            return False, 'Please provide a clinic-local appointment time.'
        start = start.astimezone(self.timezone)
        if start.second or start.microsecond or start.minute % self.grid_minutes:
            return False, f'Start times must use {self.grid_minutes}-minute increments.'
        if start < self.arena_now + timedelta(minutes=self.min_lead_minutes):
            return False, 'Appointments must be at least 60 minutes after the clinic reference time.'
        if start.date() > self.final_date:
            return False, f'Appointments are available only through {self.final_date.isoformat()}.'
        if start.date() in self.holiday:
            return False, 'The clinic is closed for a holiday on that date.'
        if start.weekday() not in self.clinic_days:
            return False, 'The clinic is closed on this day.'
        provider = self.providers[service.provider]
        if start.weekday() not in provider.days:
            return False, f'{provider.name} is not available on this day.'
        end = start + timedelta(minutes=service.minutes)
        clinic_open = self.local_datetime(start.date(), self.opening)
        clinic_close = self.local_datetime(start.date(), self.closing)
        provider_open = self.local_datetime(start.date(), provider.opening)
        provider_close = self.local_datetime(start.date(), provider.closing)
        lunch_start = self.local_datetime(start.date(), provider.lunch_start)
        lunch_end = self.local_datetime(start.date(), provider.lunch_end)
        if start < clinic_open or end > clinic_close or start < provider_open or end > provider_close:
            return False, 'The full appointment must fit within the clinic and provider hours.'
        if start < lunch_end and end > lunch_start:
            return False, 'The requested appointment would overlap the provider lunch break.'
        return True, ''
