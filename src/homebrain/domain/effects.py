"""Side effects a transition asks for. The application layer carries them out.

Returning effects as data (instead of performing them) keeps the case machine
pure, so every branch can be tested without a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from homebrain.domain.model import Booking


class ReminderKind(StrEnum):
    BOOKING_EVE = "booking_eve"
    POST_VISIT = "post_visit"


class NoticeKind(StrEnum):
    BOOKING_TOMORROW = "booking_tomorrow"
    POST_VISIT_CHECK = "post_visit_check"
    CASE_UPDATE = "case_update"


@dataclass(frozen=True, slots=True)
class CreateCheckoutSession:
    """Hold the slot with the provider (UCP: create checkout session)."""

    booking: Booking


@dataclass(frozen=True, slots=True)
class CompleteCheckoutSession:
    booking: Booking


@dataclass(frozen=True, slots=True)
class CancelCheckoutSession:
    booking: Booking


@dataclass(frozen=True, slots=True)
class IssueChallenge:
    challenge_id: str
    person_id: str
    case_id: str
    action_digest: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DeliverChallenge:
    challenge_id: str
    person_id: str


@dataclass(frozen=True, slots=True)
class RevokeChallenge:
    challenge_id: str


@dataclass(frozen=True, slots=True)
class ScheduleReminder:
    case_id: str
    kind: ReminderKind
    fire_at: datetime


@dataclass(frozen=True, slots=True)
class CancelReminders:
    case_id: str


@dataclass(frozen=True, slots=True)
class EmitNotice:
    """A household-wide notice, heard once by each member on their next turn."""

    case_id: str
    kind: NoticeKind


Effect = (
    CreateCheckoutSession
    | CompleteCheckoutSession
    | CancelCheckoutSession
    | IssueChallenge
    | DeliverChallenge
    | RevokeChallenge
    | ScheduleReminder
    | CancelReminders
    | EmitNotice
)
