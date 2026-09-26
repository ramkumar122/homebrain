"""Domain values. Immutable; every change produces a new object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum


class CaseState(StrEnum):
    TROUBLESHOOTING = "TROUBLESHOOTING"
    NEEDS_SERVICE = "NEEDS_SERVICE"
    PROVIDERS_PROPOSED = "PROVIDERS_PROPOSED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    BOOKED = "BOOKED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"

    @property
    def is_active(self) -> bool:
        return self not in TERMINAL_STATES


TERMINAL_STATES = frozenset({CaseState.RESOLVED, CaseState.CANCELLED})


class DiyLevel(IntEnum):
    """How much DIY a person will attempt. Ordered: NONE < BASIC < CONFIDENT."""

    NONE = 0
    BASIC = 1
    CONFIDENT = 2


class Role(StrEnum):
    OWNER = "owner"
    ADULT = "adult"
    CHILD = "child"
    GUEST = "guest"

    @property
    def is_adult(self) -> bool:
        return self in (Role.OWNER, Role.ADULT)


class StepStatus(StrEnum):
    PENDING = "pending"
    CURRENT = "current"
    WORKED = "worked"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANNOT_DO = "cannot_do"


class Outcome(StrEnum):
    """What a person can report through advance_case."""

    WORKED = "worked"
    DID_NOT_WORK = "did_not_work"
    SKIPPED = "skipped"
    CANNOT_DO = "cannot_do"
    WANT_PROFESSIONAL = "want_professional"
    TECHNICIAN_FIXED_IT = "technician_fixed_it"
    TECHNICIAN_DID_NOT_FIX = "technician_did_not_fix"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class Citation:
    document_id: str
    document_title: str
    document_type: str
    page: int
    quote: str
    extracted_by: str


@dataclass(frozen=True, slots=True)
class Step:
    step_id: str
    step_key: str
    order: int
    instruction: str
    diy_level: DiyLevel
    citation: Citation
    status: StepStatus = StepStatus.PENDING
    adult_only: bool = False
    safety_warning: str | None = None
    outcome_by: str | None = None
    outcome_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Actor:
    """The person the case machine acts for. Resolved before the machine runs."""

    person_id: str | None
    role: Role
    diy_tolerance: DiyLevel

    def can_attempt(self, step: Step) -> bool:
        if step.adult_only and not self.role.is_adult:
            return False
        return step.diy_level <= self.diy_tolerance


@dataclass(frozen=True, slots=True)
class SlotOffer:
    slot_id: str
    start: datetime
    end: datetime
    label: str


@dataclass(frozen=True, slots=True)
class ProviderOffer:
    provider_id: str
    name: str
    kind: str
    covered_by_warranty: bool
    price_cents: int
    slots: tuple[SlotOffer, ...]


@dataclass(frozen=True, slots=True)
class Booking:
    booking_ref: str
    provider_id: str
    provider_name: str
    slot_id: str
    slot_start: datetime
    slot_end: datetime
    price_cents: int
    covered_by_warranty: bool
    requested_by: str

    def same_offer(self, provider_id: str, slot_id: str) -> bool:
        return self.provider_id == provider_id and self.slot_id == slot_id


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    household_id: str
    asset_id: str
    problem: str
    symptom_key: str | None
    state: CaseState
    steps: tuple[Step, ...]
    opened_by: str | None
    opened_at: datetime
    updated_at: datetime
    version: int
    providers: tuple[ProviderOffer, ...] = ()
    pending_booking: Booking | None = None
    booking: Booking | None = None
    challenge_id: str | None = None

    @property
    def current_step(self) -> Step | None:
        return next((s for s in self.steps if s.status is StepStatus.CURRENT), None)
