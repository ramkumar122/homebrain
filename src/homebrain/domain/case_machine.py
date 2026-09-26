"""The repair-case state machine (DESIGN.md §3).

Two pure functions, `open_case` and `transition`. No I/O, no clock, no ids:
the caller passes the time and actor in `Context`, puts any facts it looked
up on the event, and carries out the returned effects.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import assert_never

from homebrain.domain.effects import (
    CancelCheckoutSession,
    CancelReminders,
    CompleteCheckoutSession,
    CreateCheckoutSession,
    DeliverChallenge,
    Effect,
    EmitNotice,
    IssueChallenge,
    NoticeKind,
    ReminderKind,
    RevokeChallenge,
    ScheduleReminder,
)
from homebrain.domain.events import (
    BookingConfirmed,
    Cancel,
    CannotDo,
    CaseEvent,
    Open,
    ProvidersFound,
    StepEvent,
    StepFailed,
    StepSkipped,
    StepWorked,
    TechFixed,
    TechNotFixed,
    VerificationEvent,
    VerificationExpired,
    VerificationFailed,
    Verified,
    WantProfessional,
)
from homebrain.domain.model import (
    Actor,
    Booking,
    Case,
    CaseState,
    Outcome,
    Step,
    StepStatus,
)

CHALLENGE_TTL = timedelta(minutes=5)
BOOKING_EVE_LEAD = timedelta(days=1)
POST_VISIT_DELAY = timedelta(hours=2)

ALLOWED_OUTCOMES: dict[CaseState, tuple[Outcome, ...]] = {
    CaseState.TROUBLESHOOTING: (
        Outcome.WORKED,
        Outcome.DID_NOT_WORK,
        Outcome.SKIPPED,
        Outcome.CANNOT_DO,
        Outcome.WANT_PROFESSIONAL,
        Outcome.CANCEL,
    ),
    CaseState.NEEDS_SERVICE: (Outcome.CANCEL,),
    CaseState.PROVIDERS_PROPOSED: (Outcome.CANCEL,),
    CaseState.PENDING_VERIFICATION: (Outcome.CANCEL,),
    CaseState.BOOKED: (Outcome.TECHNICIAN_FIXED_IT, Outcome.TECHNICIAN_DID_NOT_FIX, Outcome.CANCEL),
    CaseState.RESOLVED: (),
    CaseState.CANCELLED: (),
}


class RejectionCode(StrEnum):
    INVALID_TRANSITION = "INVALID_TRANSITION"
    STEP_MISMATCH = "STEP_MISMATCH"
    UNKNOWN_OFFER = "UNKNOWN_OFFER"
    SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
    CHALLENGE_MISMATCH = "CHALLENGE_MISMATCH"
    IDENTITY_REQUIRED = "IDENTITY_REQUIRED"


@dataclass(frozen=True, slots=True)
class Context:
    actor: Actor
    now: datetime


@dataclass(frozen=True, slots=True)
class Transition:
    case: Case
    event_type: str
    from_state: CaseState | None
    effects: tuple[Effect, ...] = ()
    duplicate: bool = False

    @property
    def to_state(self) -> CaseState:
        return self.case.state


@dataclass(frozen=True, slots=True)
class Rejection:
    code: RejectionCode
    message: str
    allowed_outcomes: tuple[Outcome, ...]


Result = Transition | Rejection


# ------------------------------------------------------------------ public API


def event_for_outcome(outcome: Outcome, step_id: str | None = None) -> CaseEvent:
    """Map an advance_case outcome to the event it stands for."""
    match outcome:
        case Outcome.WORKED:
            return StepWorked(step_id)
        case Outcome.DID_NOT_WORK:
            return StepFailed(step_id)
        case Outcome.SKIPPED:
            return StepSkipped(step_id)
        case Outcome.CANNOT_DO:
            return CannotDo(step_id)
        case Outcome.WANT_PROFESSIONAL:
            return WantProfessional()
        case Outcome.TECHNICIAN_FIXED_IT:
            return TechFixed()
        case Outcome.TECHNICIAN_DID_NOT_FIX:
            return TechNotFixed()
        case Outcome.CANCEL:
            return Cancel()
        case _:  # pragma: no cover
            assert_never(outcome)


def booking_digest(case: Case, booking: Booking) -> str:
    """Binds a verification to one exact booking, so it can't be replayed onto another."""
    parts = (
        case.household_id,
        booking.requested_by,
        case.case_id,
        booking.provider_id,
        booking.slot_id,
        str(booking.price_cents),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def open_case(event: Open, ctx: Context) -> Transition:
    steps = tuple(
        replace(s, status=StepStatus.PENDING, outcome_by=None, outcome_at=None)
        for s in sorted(event.candidate_steps, key=lambda s: s.order)
    )
    steps, state = _choose_next_step(steps, ctx.actor)
    case = Case(
        case_id=event.case_id,
        household_id=event.household_id,
        asset_id=event.asset_id,
        problem=event.problem,
        symptom_key=event.symptom_key,
        state=state,
        steps=steps,
        opened_by=ctx.actor.person_id,
        opened_at=ctx.now,
        updated_at=ctx.now,
        version=1,
    )
    return Transition(case, Open.event_type, None)


def transition(case: Case, event: CaseEvent, ctx: Context) -> Result:
    if not case.state.is_active:
        return _invalid(case, event.event_type)
    match event:
        case StepWorked() | StepFailed() | StepSkipped() | CannotDo():
            return _on_step(case, event, ctx)
        case WantProfessional():
            return _on_want_professional(case, ctx)
        case ProvidersFound():
            return _on_providers_found(case, event, ctx)
        case BookingConfirmed():
            return _on_booking_confirmed(case, event, ctx)
        case Verified() | VerificationFailed() | VerificationExpired():
            return _on_verification(case, event, ctx)
        case TechFixed() | TechNotFixed():
            return _on_visit_outcome(case, event, ctx)
        case Cancel():
            return _on_cancel(case, ctx)
        case _:  # pragma: no cover
            assert_never(event)


# ------------------------------------------------------------------ handlers


def _on_step(case: Case, event: StepEvent, ctx: Context) -> Result:
    current = case.current_step
    if case.state is not CaseState.TROUBLESHOOTING or current is None:
        return _invalid(case, event.event_type)
    status = _step_status(event)
    if event.step_id is not None and event.step_id != current.step_id:
        answered = next((s for s in case.steps if s.step_id == event.step_id), None)
        if answered is not None and answered.status is status:
            return Transition(case, event.event_type, case.state, duplicate=True)
        return Rejection(
            RejectionCode.STEP_MISMATCH,
            f"Step {event.step_id} is not the current step; the current step is {current.step_id}.",
            ALLOWED_OUTCOMES[case.state],
        )
    steps = _set_step(case.steps, current.step_id, status, ctx)
    if status is StepStatus.WORKED:
        return _move(
            case, replace(case, state=CaseState.RESOLVED, steps=steps), event.event_type, ctx
        )
    steps, state = _choose_next_step(steps, ctx.actor)
    return _move(case, replace(case, state=state, steps=steps), event.event_type, ctx)


def _on_want_professional(case: Case, ctx: Context) -> Result:
    if case.state is not CaseState.TROUBLESHOOTING:
        return _invalid(case, WantProfessional.event_type)
    after = replace(case, state=CaseState.NEEDS_SERVICE, steps=_clear_current(case.steps))
    return _move(case, after, WantProfessional.event_type, ctx)


def _on_providers_found(case: Case, event: ProvidersFound, ctx: Context) -> Result:
    if case.state not in (CaseState.NEEDS_SERVICE, CaseState.PROVIDERS_PROPOSED):
        return _invalid(case, event.event_type)
    state = CaseState.PROVIDERS_PROPOSED if event.providers else CaseState.NEEDS_SERVICE
    return _move(case, replace(case, state=state, providers=event.providers), event.event_type, ctx)


def _on_booking_confirmed(case: Case, event: BookingConfirmed, ctx: Context) -> Result:
    already = case.booking or case.pending_booking
    if already is not None and already.same_offer(event.provider_id, event.slot_id):
        return Transition(case, event.event_type, case.state, duplicate=True)
    if case.state not in (CaseState.PROVIDERS_PROPOSED, CaseState.PENDING_VERIFICATION):
        return _invalid(case, event.event_type)
    if ctx.actor.person_id is None:
        return Rejection(
            RejectionCode.IDENTITY_REQUIRED,
            "Booking needs a known household member.",
            ALLOWED_OUTCOMES[case.state],
        )
    offer = next((p for p in case.providers if p.provider_id == event.provider_id), None)
    slots = () if offer is None else offer.slots
    slot = next((s for s in slots if s.slot_id == event.slot_id), None)
    if offer is None or slot is None:
        return Rejection(
            RejectionCode.UNKNOWN_OFFER,
            f"Provider {event.provider_id} has no slot {event.slot_id} on this case.",
            ALLOWED_OUTCOMES[case.state],
        )
    if not event.slot_available:
        return Rejection(
            RejectionCode.SLOT_UNAVAILABLE,
            f"Slot {event.slot_id} is no longer available.",
            ALLOWED_OUTCOMES[case.state],
        )
    booking = Booking(
        booking_ref=event.booking_ref,
        provider_id=offer.provider_id,
        provider_name=offer.name,
        slot_id=slot.slot_id,
        slot_start=slot.start,
        slot_end=slot.end,
        price_cents=offer.price_cents,
        covered_by_warranty=offer.covered_by_warranty,
        requested_by=ctx.actor.person_id,
    )
    effects = (*_release_pending(case), CreateCheckoutSession(booking))
    if event.grant_valid:
        return _book(case, event.event_type, booking, effects, ctx)
    challenge = IssueChallenge(
        challenge_id=event.challenge_id,
        person_id=booking.requested_by,
        case_id=case.case_id,
        action_digest=booking_digest(case, booking),
        expires_at=ctx.now + CHALLENGE_TTL,
    )
    after = replace(
        case,
        state=CaseState.PENDING_VERIFICATION,
        pending_booking=booking,
        challenge_id=event.challenge_id,
    )
    return _move(
        case,
        after,
        event.event_type,
        ctx,
        (*effects, challenge, DeliverChallenge(event.challenge_id, booking.requested_by)),
    )


def _on_verification(case: Case, event: VerificationEvent, ctx: Context) -> Result:
    pending = case.pending_booking
    if case.state is not CaseState.PENDING_VERIFICATION or pending is None:
        return _invalid(case, event.event_type)
    if event.challenge_id != case.challenge_id or (
        isinstance(event, Verified) and event.action_digest != booking_digest(case, pending)
    ):
        return Rejection(
            RejectionCode.CHALLENGE_MISMATCH,
            "This verification does not match the booking waiting on this case.",
            ALLOWED_OUTCOMES[case.state],
        )
    if isinstance(event, Verified) and event.hold_valid:
        return _book(case, event.event_type, pending, (), ctx)
    after = replace(
        case, state=CaseState.PROVIDERS_PROPOSED, pending_booking=None, challenge_id=None
    )
    return _move(case, after, event.event_type, ctx, (CancelCheckoutSession(pending),))


def _on_visit_outcome(case: Case, event: TechFixed | TechNotFixed, ctx: Context) -> Result:
    if case.state is not CaseState.BOOKED:
        return _invalid(case, event.event_type)
    effects = (CancelReminders(case.case_id),)
    if isinstance(event, TechFixed):
        return _move(case, replace(case, state=CaseState.RESOLVED), event.event_type, ctx, effects)
    after = replace(case, state=CaseState.NEEDS_SERVICE, booking=None, providers=())
    return _move(case, after, event.event_type, ctx, effects)


def _on_cancel(case: Case, ctx: Context) -> Result:
    effects: tuple[Effect, ...] = _release_pending(case)
    if case.booking is not None:
        effects = (*effects, CancelCheckoutSession(case.booking), CancelReminders(case.case_id))
    after = replace(
        case,
        state=CaseState.CANCELLED,
        steps=_clear_current(case.steps),
        pending_booking=None,
        challenge_id=None,
    )
    return _move(case, after, Cancel.event_type, ctx, effects)


# ------------------------------------------------------------------ helpers


def _book(
    case: Case,
    event_type: str,
    booking: Booking,
    effects: tuple[Effect, ...],
    ctx: Context,
) -> Transition:
    reminders: tuple[Effect, ...] = ()
    eve = booking.slot_start - BOOKING_EVE_LEAD
    if eve > ctx.now:
        reminders = (ScheduleReminder(case.case_id, ReminderKind.BOOKING_EVE, eve),)
    after = replace(
        case, state=CaseState.BOOKED, booking=booking, pending_booking=None, challenge_id=None
    )
    post_visit = booking.slot_end + POST_VISIT_DELAY
    return _move(
        case,
        after,
        event_type,
        ctx,
        (
            *effects,
            CompleteCheckoutSession(booking),
            *reminders,
            ScheduleReminder(case.case_id, ReminderKind.POST_VISIT, post_visit),
            EmitNotice(case.case_id, NoticeKind.CASE_UPDATE),
        ),
    )


def _release_pending(case: Case) -> tuple[Effect, ...]:
    effects: tuple[Effect, ...] = ()
    if case.pending_booking is not None:
        effects = (CancelCheckoutSession(case.pending_booking),)
    if case.challenge_id is not None:
        effects = (*effects, RevokeChallenge(case.challenge_id))
    return effects


def _move(
    before: Case,
    after: Case,
    event_type: str,
    ctx: Context,
    effects: tuple[Effect, ...] = (),
) -> Transition:
    stamped = replace(after, updated_at=ctx.now, version=before.version + 1)
    return Transition(stamped, event_type, before.state, effects)


def _choose_next_step(steps: tuple[Step, ...], actor: Actor) -> tuple[tuple[Step, ...], CaseState]:
    """Make the first step this actor can attempt current, or hand over to a professional."""
    nxt = next(
        (s for s in steps if s.status is StepStatus.PENDING and actor.can_attempt(s)),
        None,
    )
    if nxt is None:
        return steps, CaseState.NEEDS_SERVICE
    return tuple(
        replace(s, status=StepStatus.CURRENT) if s.step_id == nxt.step_id else s for s in steps
    ), CaseState.TROUBLESHOOTING


def _set_step(
    steps: tuple[Step, ...], step_id: str, status: StepStatus, ctx: Context
) -> tuple[Step, ...]:
    return tuple(
        replace(s, status=status, outcome_by=ctx.actor.person_id, outcome_at=ctx.now)
        if s.step_id == step_id
        else s
        for s in steps
    )


def _clear_current(steps: tuple[Step, ...]) -> tuple[Step, ...]:
    """The current step wasn't tried, so it goes back to pending."""
    return tuple(
        replace(s, status=StepStatus.PENDING) if s.status is StepStatus.CURRENT else s
        for s in steps
    )


def _step_status(event: StepEvent) -> StepStatus:
    match event:
        case StepWorked():
            return StepStatus.WORKED
        case StepFailed():
            return StepStatus.FAILED
        case StepSkipped():
            return StepStatus.SKIPPED
        case CannotDo():
            return StepStatus.CANNOT_DO
        case _:  # pragma: no cover
            assert_never(event)


def _invalid(case: Case, event_type: str) -> Rejection:
    return Rejection(
        RejectionCode.INVALID_TRANSITION,
        f"{event_type} is not possible while the case is {case.state.value}.",
        ALLOWED_OUTCOMES[case.state],
    )
