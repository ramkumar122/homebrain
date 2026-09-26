"""Events the case machine accepts.

Tools translate what people say into these; the machine never sees free text.
Facts the machine can't look up itself (is the slot free? does the person hold
a valid verification grant?) are gathered by the application layer and carried
on the event, which keeps the machine pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from homebrain.domain.model import ProviderOffer, Step


@dataclass(frozen=True, slots=True)
class Open:
    event_type: ClassVar[str] = "OPEN"
    case_id: str
    household_id: str
    asset_id: str
    problem: str
    symptom_key: str | None
    candidate_steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class StepWorked:
    event_type: ClassVar[str] = "STEP_WORKED"
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class StepFailed:
    event_type: ClassVar[str] = "STEP_FAILED"
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class StepSkipped:
    event_type: ClassVar[str] = "STEP_SKIPPED"
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class CannotDo:
    event_type: ClassVar[str] = "CANNOT_DO"
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class WantProfessional:
    event_type: ClassVar[str] = "WANT_PROFESSIONAL"


@dataclass(frozen=True, slots=True)
class ProvidersFound:
    event_type: ClassVar[str] = "PROVIDERS_FOUND"
    providers: tuple[ProviderOffer, ...]


@dataclass(frozen=True, slots=True)
class BookingConfirmed:
    """The person said yes to a specific provider and slot."""

    event_type: ClassVar[str] = "BOOKING_CONFIRMED"
    provider_id: str
    slot_id: str
    slot_available: bool
    grant_valid: bool
    booking_ref: str
    challenge_id: str


@dataclass(frozen=True, slots=True)
class Verified:
    event_type: ClassVar[str] = "VERIFIED"
    challenge_id: str
    action_digest: str
    hold_valid: bool


@dataclass(frozen=True, slots=True)
class VerificationFailed:
    event_type: ClassVar[str] = "VERIFICATION_FAILED"
    challenge_id: str


@dataclass(frozen=True, slots=True)
class VerificationExpired:
    event_type: ClassVar[str] = "VERIFICATION_EXPIRED"
    challenge_id: str


@dataclass(frozen=True, slots=True)
class TechFixed:
    event_type: ClassVar[str] = "TECH_FIXED"


@dataclass(frozen=True, slots=True)
class TechNotFixed:
    event_type: ClassVar[str] = "TECH_NOT_FIXED"


@dataclass(frozen=True, slots=True)
class Cancel:
    event_type: ClassVar[str] = "CANCEL"
    reason: str | None = None


StepEvent = StepWorked | StepFailed | StepSkipped | CannotDo
VerificationEvent = Verified | VerificationFailed | VerificationExpired
CaseEvent = (
    StepEvent
    | WantProfessional
    | ProvidersFound
    | BookingConfirmed
    | VerificationEvent
    | TechFixed
    | TechNotFixed
    | Cancel
)
