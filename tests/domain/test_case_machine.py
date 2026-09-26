"""Table-driven tests for the case state machine (DESIGN.md §3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from homebrain.domain.case_machine import (
    ALLOWED_OUTCOMES,
    CHALLENGE_TTL,
    POST_VISIT_DELAY,
    RejectionCode,
    booking_digest,
    event_for_outcome,
    transition,
)
from homebrain.domain.effects import (
    CancelCheckoutSession,
    CancelReminders,
    CompleteCheckoutSession,
    CreateCheckoutSession,
    DeliverChallenge,
    EmitNotice,
    IssueChallenge,
    NoticeKind,
    ReminderKind,
    RevokeChallenge,
    ScheduleReminder,
)
from homebrain.domain.events import (
    Cancel,
    CannotDo,
    CaseEvent,
    ProvidersFound,
    StepFailed,
    StepSkipped,
    StepWorked,
    TechFixed,
    TechNotFixed,
    VerificationExpired,
    VerificationFailed,
    Verified,
    WantProfessional,
)
from homebrain.domain.model import (
    Booking,
    CaseState,
    DiyLevel,
    Outcome,
    Role,
    StepStatus,
)
from tests.domain.builders import (
    GUEST,
    KID,
    NOW,
    PRIYA,
    RAM,
    VINAY,
    case_in,
    confirm,
    ctx,
    ok,
    opened,
    provider,
    rejected,
    slot,
    step,
)

# ------------------------------------------------------------------ the full matrix

ALL_EVENTS: dict[str, CaseEvent] = {
    "STEP_WORKED": StepWorked(),
    "STEP_FAILED": StepFailed(),
    "STEP_SKIPPED": StepSkipped(),
    "CANNOT_DO": CannotDo(),
    "WANT_PROFESSIONAL": WantProfessional(),
    "PROVIDERS_FOUND": ProvidersFound((provider(),)),
    # A different offer from the one used to build BOOKED / PENDING, so it is never a duplicate.
    "BOOKING_CONFIRMED": confirm("p9", "sl9", n=9),
    "VERIFIED": Verified("c1", "digest", hold_valid=True),
    "VERIFICATION_FAILED": VerificationFailed("c1"),
    "VERIFICATION_EXPIRED": VerificationExpired("c1"),
    "TECH_FIXED": TechFixed(),
    "TECH_NOT_FIXED": TechNotFixed(),
    "CANCEL": Cancel(),
}

STEP = {"STEP_WORKED", "STEP_FAILED", "STEP_SKIPPED", "CANNOT_DO"}
VALID: dict[CaseState, set[str]] = {
    CaseState.TROUBLESHOOTING: STEP | {"WANT_PROFESSIONAL", "CANCEL"},
    CaseState.NEEDS_SERVICE: {"PROVIDERS_FOUND", "CANCEL"},
    CaseState.PROVIDERS_PROPOSED: {"PROVIDERS_FOUND", "BOOKING_CONFIRMED", "CANCEL"},
    CaseState.PENDING_VERIFICATION: {
        "BOOKING_CONFIRMED",
        "VERIFIED",
        "VERIFICATION_FAILED",
        "VERIFICATION_EXPIRED",
        "CANCEL",
    },
    CaseState.BOOKED: {"TECH_FIXED", "TECH_NOT_FIXED", "CANCEL"},
    CaseState.RESOLVED: set(),
    CaseState.CANCELLED: set(),
}

INVALID_CELLS = [
    (state, name) for state in CaseState for name in ALL_EVENTS if name not in VALID[state]
]


@pytest.mark.parametrize(("state", "name"), INVALID_CELLS, ids=lambda v: str(v))
def test_every_invalid_cell_is_rejected(state, name):
    case = case_in(state)
    r = rejected(transition(case, ALL_EVENTS[name], ctx()))
    assert r.code is RejectionCode.INVALID_TRANSITION
    assert r.allowed_outcomes == ALLOWED_OUTCOMES[state]
    assert name in r.message


def test_matrix_covers_every_state_and_event():
    assert len(INVALID_CELLS) + sum(map(len, VALID.values())) == len(CaseState) * len(ALL_EVENTS)


def test_terminal_states_allow_no_outcomes():
    assert ALLOWED_OUTCOMES[CaseState.RESOLVED] == ()
    assert ALLOWED_OUTCOMES[CaseState.CANCELLED] == ()
    assert not CaseState.RESOLVED.is_active
    assert CaseState.BOOKED.is_active


# ------------------------------------------------------------------ outcome mapping


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (Outcome.WORKED, StepWorked("s1")),
        (Outcome.DID_NOT_WORK, StepFailed("s1")),
        (Outcome.SKIPPED, StepSkipped("s1")),
        (Outcome.CANNOT_DO, CannotDo("s1")),
        (Outcome.WANT_PROFESSIONAL, WantProfessional()),
        (Outcome.TECHNICIAN_FIXED_IT, TechFixed()),
        (Outcome.TECHNICIAN_DID_NOT_FIX, TechNotFixed()),
        (Outcome.CANCEL, Cancel()),
    ],
)
def test_event_for_outcome(outcome, expected):
    assert event_for_outcome(outcome, "s1") == expected


# ------------------------------------------------------------------ opening


def test_open_makes_first_eligible_step_current_in_order():
    shuffled = (step(3), step(1), replace(step(2), status=StepStatus.FAILED))
    t_case = opened(steps=shuffled)
    assert t_case.state is CaseState.TROUBLESHOOTING
    assert [s.step_id for s in t_case.steps] == ["s1", "s2", "s3"]
    assert [s.status for s in t_case.steps] == [
        StepStatus.CURRENT,
        StepStatus.PENDING,  # copied steps always start fresh
        StepStatus.PENDING,
    ]
    assert t_case.version == 1
    assert t_case.opened_by == VINAY.person_id
    assert t_case.opened_at == t_case.updated_at == NOW


def test_open_with_no_steps_needs_service():
    assert opened(steps=()).state is CaseState.NEEDS_SERVICE


def test_open_for_person_who_wants_no_diy_goes_straight_to_service():
    c = opened(steps=(step(1, DiyLevel.BASIC),), actor=PRIYA)
    assert c.state is CaseState.NEEDS_SERVICE
    assert c.current_step is None


def test_open_skips_adult_only_steps_for_a_child():
    c = opened(steps=(step(1, adult_only=True), step(2)), actor=KID)
    assert c.current_step is not None
    assert c.current_step.step_id == "s2"


# ------------------------------------------------------------------ troubleshooting


@pytest.mark.parametrize(
    ("event", "status"),
    [
        (StepFailed(), StepStatus.FAILED),
        (StepSkipped(), StepStatus.SKIPPED),
        (CannotDo(), StepStatus.CANNOT_DO),
    ],
)
def test_unresolved_step_moves_to_next(event, status):
    later = NOW + timedelta(minutes=5)
    t = ok(transition(opened(), event, ctx(RAM, later)))
    first, second = t.case.steps[0], t.case.steps[1]
    assert (first.status, first.outcome_by, first.outcome_at) == (status, RAM.person_id, later)
    assert second.status is StepStatus.CURRENT
    assert t.case.state is CaseState.TROUBLESHOOTING
    assert (t.from_state, t.to_state, t.event_type) == (
        CaseState.TROUBLESHOOTING,
        CaseState.TROUBLESHOOTING,
        event.event_type,
    )
    assert t.case.version == 2
    assert t.case.updated_at == later
    assert t.effects == ()


def test_last_failed_step_hands_over_to_a_professional():
    c = opened(steps=(step(1),))
    t = ok(transition(c, StepFailed(), ctx()))
    assert t.case.state is CaseState.NEEDS_SERVICE
    assert t.case.current_step is None


def test_step_that_works_resolves_the_case():
    t = ok(transition(opened(), StepWorked("s1"), ctx()))
    assert t.case.state is CaseState.RESOLVED
    assert t.case.steps[0].status is StepStatus.WORKED


def test_next_step_is_chosen_for_whoever_is_speaking_now():
    # Vinay (confident) opened it; Ram (basic) reports s1 failed, so s2 (confident) is skipped.
    c = opened(steps=(step(1), step(2, DiyLevel.CONFIDENT), step(3)), actor=VINAY)
    t = ok(transition(c, StepFailed(), ctx(RAM)))
    assert t.case.current_step is not None
    assert t.case.current_step.step_id == "s3"
    assert t.case.steps[1].status is StepStatus.PENDING


def test_repeated_outcome_for_an_answered_step_is_a_duplicate():
    once = ok(transition(opened(), StepFailed("s1"), ctx())).case
    again = ok(transition(once, StepFailed("s1"), ctx()))
    assert again.duplicate
    assert again.case is once
    assert again.effects == ()


@pytest.mark.parametrize("step_id", ["s3", "nope"])
def test_outcome_for_a_step_that_is_not_current_is_rejected(step_id):
    r = rejected(transition(opened(), StepFailed(step_id), ctx()))
    assert r.code is RejectionCode.STEP_MISMATCH
    assert "s1" in r.message


def test_different_outcome_for_an_answered_step_is_rejected():
    once = ok(transition(opened(), StepFailed("s1"), ctx())).case
    r = rejected(transition(once, StepWorked("s1"), ctx()))
    assert r.code is RejectionCode.STEP_MISMATCH


def test_troubleshooting_without_a_current_step_is_rejected():
    broken = replace(opened(), steps=(step(1),))
    assert (
        rejected(transition(broken, StepFailed(), ctx())).code is RejectionCode.INVALID_TRANSITION
    )


def test_want_professional_puts_the_untried_step_back():
    t = ok(transition(opened(), WantProfessional(), ctx()))
    assert t.case.state is CaseState.NEEDS_SERVICE
    assert all(s.status is StepStatus.PENDING for s in t.case.steps)


# ------------------------------------------------------------------ providers


@pytest.mark.parametrize(
    ("start", "found", "expected"),
    [
        (CaseState.NEEDS_SERVICE, (provider(),), CaseState.PROVIDERS_PROPOSED),
        (CaseState.NEEDS_SERVICE, (), CaseState.NEEDS_SERVICE),
        (CaseState.PROVIDERS_PROPOSED, (provider("p2"),), CaseState.PROVIDERS_PROPOSED),
        (CaseState.PROVIDERS_PROPOSED, (), CaseState.NEEDS_SERVICE),
    ],
)
def test_providers_found(start, found, expected):
    t = ok(transition(case_in(start), ProvidersFound(found), ctx()))
    assert t.case.state is expected
    assert t.case.providers == found


# ------------------------------------------------------------------ booking


def test_confirm_without_grant_holds_slot_and_issues_challenge():
    c = case_in(CaseState.PROVIDERS_PROPOSED)
    t = ok(transition(c, confirm(), ctx()))
    b = t.case.pending_booking
    assert t.case.state is CaseState.PENDING_VERIFICATION
    assert b is not None
    assert (b.booking_ref, b.provider_id, b.slot_id, b.price_cents, b.requested_by) == (
        "b1",
        "p1",
        "sl1",
        8900,
        VINAY.person_id,
    )
    assert t.case.challenge_id == "c1"
    assert t.effects == (
        CreateCheckoutSession(b),
        IssueChallenge("c1", VINAY.person_id, "case1", booking_digest(c, b), NOW + CHALLENGE_TTL),
        DeliverChallenge("c1", VINAY.person_id),
    )


def test_confirm_with_valid_grant_books_directly():
    t = ok(transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(grant=True), ctx()))
    b = t.case.booking
    assert t.case.state is CaseState.BOOKED
    assert b is not None
    assert t.case.pending_booking is None
    assert t.case.challenge_id is None
    assert t.effects == (
        CreateCheckoutSession(b),
        CompleteCheckoutSession(b),
        ScheduleReminder("case1", ReminderKind.BOOKING_EVE, b.slot_start - timedelta(days=1)),
        ScheduleReminder("case1", ReminderKind.POST_VISIT, b.slot_end + POST_VISIT_DELAY),
        EmitNotice("case1", NoticeKind.CASE_UPDATE),
    )


def test_no_eve_reminder_when_the_slot_is_less_than_a_day_away():
    soon = case_in(CaseState.NEEDS_SERVICE)
    soon = ok(
        transition(
            soon, ProvidersFound((provider("p1", slot("sl1", NOW + timedelta(hours=5))),)), ctx()
        )
    ).case
    t = ok(transition(soon, confirm(grant=True), ctx()))
    kinds = [e.kind for e in t.effects if isinstance(e, ScheduleReminder)]
    assert kinds == [ReminderKind.POST_VISIT]


@pytest.mark.parametrize(("provider_id", "slot_id"), [("p9", "sl1"), ("p1", "sl9")])
def test_confirm_unknown_offer_is_rejected(provider_id, slot_id):
    r = rejected(
        transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(provider_id, slot_id), ctx())
    )
    assert r.code is RejectionCode.UNKNOWN_OFFER


def test_confirm_taken_slot_is_rejected():
    r = rejected(transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(available=False), ctx()))
    assert r.code is RejectionCode.SLOT_UNAVAILABLE


def test_guest_cannot_confirm_a_booking():
    r = rejected(transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(), ctx(GUEST)))
    assert r.code is RejectionCode.IDENTITY_REQUIRED


@pytest.mark.parametrize("state", [CaseState.PENDING_VERIFICATION, CaseState.BOOKED])
def test_confirming_the_same_offer_again_is_a_duplicate(state):
    c = case_in(state)
    t = ok(transition(c, confirm(), ctx()))
    assert t.duplicate
    assert t.case is c


def _two_slot_pending():
    c = ok(
        transition(
            case_in(CaseState.NEEDS_SERVICE),
            ProvidersFound((provider("p1", slot("sl1"), slot("sl2", NOW + timedelta(days=4))),)),
            ctx(),
        )
    ).case
    return ok(transition(c, confirm(), ctx())).case


def test_switching_slot_while_pending_releases_the_old_hold():
    c = _two_slot_pending()
    old = c.pending_booking
    t = ok(transition(c, confirm("p1", "sl2", n=2), ctx()))
    assert t.case.state is CaseState.PENDING_VERIFICATION
    assert t.case.challenge_id == "c2"
    assert t.effects[:2] == (CancelCheckoutSession(old), RevokeChallenge("c1"))
    assert isinstance(t.effects[2], CreateCheckoutSession)


def test_switching_slot_with_a_valid_grant_books_the_new_slot():
    c = _two_slot_pending()
    t = ok(transition(c, confirm("p1", "sl2", grant=True, n=2), ctx()))
    assert t.case.state is CaseState.BOOKED
    assert t.case.booking is not None
    assert t.case.booking.slot_id == "sl2"
    assert RevokeChallenge("c1") in t.effects


# ------------------------------------------------------------------ verification


def _verified(c, *, hold=True, digest=None, challenge="c1"):
    assert c.pending_booking is not None
    return Verified(challenge, digest or booking_digest(c, c.pending_booking), hold_valid=hold)


def test_verified_books_the_held_slot():
    c = case_in(CaseState.PENDING_VERIFICATION)
    b = c.pending_booking
    t = ok(transition(c, _verified(c), ctx(PRIYA)))
    assert t.case.state is CaseState.BOOKED
    assert t.case.booking == b
    assert (t.case.pending_booking, t.case.challenge_id) == (None, None)
    assert t.effects[0] == CompleteCheckoutSession(b)
    assert not any(isinstance(e, CreateCheckoutSession) for e in t.effects)


def test_verified_after_the_hold_was_lost_goes_back_to_providers():
    c = case_in(CaseState.PENDING_VERIFICATION)
    t = ok(transition(c, _verified(c, hold=False), ctx()))
    assert t.case.state is CaseState.PROVIDERS_PROPOSED
    assert t.effects == (CancelCheckoutSession(c.pending_booking),)


@pytest.mark.parametrize("event", [VerificationFailed("c1"), VerificationExpired("c1")])
def test_failed_or_expired_verification_releases_the_hold(event):
    c = case_in(CaseState.PENDING_VERIFICATION)
    t = ok(transition(c, event, ctx()))
    assert t.case.state is CaseState.PROVIDERS_PROPOSED
    assert (t.case.pending_booking, t.case.challenge_id) == (None, None)
    assert t.effects == (CancelCheckoutSession(c.pending_booking),)


@pytest.mark.parametrize(
    "make",
    [
        lambda c: _verified(c, challenge="other"),
        lambda c: _verified(c, digest="0" * 64),
        lambda c: VerificationFailed("other"),
    ],
    ids=["wrong-challenge", "wrong-digest", "failed-wrong-challenge"],
)
def test_verification_for_another_booking_is_rejected(make):
    c = case_in(CaseState.PENDING_VERIFICATION)
    assert rejected(transition(c, make(c), ctx())).code is RejectionCode.CHALLENGE_MISMATCH


def test_pending_verification_without_a_booking_is_rejected():
    broken = replace(case_in(CaseState.PENDING_VERIFICATION), pending_booking=None)
    r = rejected(transition(broken, VerificationFailed("c1"), ctx()))
    assert r.code is RejectionCode.INVALID_TRANSITION


def test_digest_binds_the_exact_booking():
    c = case_in(CaseState.PENDING_VERIFICATION)
    b = c.pending_booking
    assert isinstance(b, Booking)
    assert booking_digest(c, b) == booking_digest(c, b)
    assert booking_digest(c, b) != booking_digest(c, replace(b, slot_id="sl2"))
    assert booking_digest(c, b) != booking_digest(c, replace(b, price_cents=1))


# ------------------------------------------------------------------ after the visit


def test_technician_fixed_it_resolves_and_cancels_leftover_reminders():
    t = ok(transition(case_in(CaseState.BOOKED), TechFixed(), ctx()))
    assert t.case.state is CaseState.RESOLVED
    assert t.effects == (CancelReminders("case1"),)


def test_technician_did_not_fix_it_needs_service_again():
    t = ok(transition(case_in(CaseState.BOOKED), TechNotFixed(), ctx()))
    assert t.case.state is CaseState.NEEDS_SERVICE
    assert (t.case.booking, t.case.providers) == (None, ())
    assert t.effects == (CancelReminders("case1"),)


# ------------------------------------------------------------------ cancel


def test_cancel_while_troubleshooting_puts_the_step_back():
    t = ok(transition(opened(), Cancel("changed my mind"), ctx()))
    assert t.case.state is CaseState.CANCELLED
    assert t.case.current_step is None
    assert t.effects == ()


def test_cancel_while_pending_releases_hold_and_challenge():
    c = case_in(CaseState.PENDING_VERIFICATION)
    t = ok(transition(c, Cancel(), ctx()))
    assert t.effects == (CancelCheckoutSession(c.pending_booking), RevokeChallenge("c1"))
    assert (t.case.pending_booking, t.case.challenge_id) == (None, None)


def test_cancel_while_booked_cancels_booking_and_reminders():
    c = case_in(CaseState.BOOKED)
    t = ok(transition(c, Cancel(), ctx()))
    assert t.effects == (CancelCheckoutSession(c.booking), CancelReminders("case1"))


@pytest.mark.parametrize("state", [CaseState.NEEDS_SERVICE, CaseState.PROVIDERS_PROPOSED])
def test_cancel_with_nothing_held_has_no_effects(state):
    t = ok(transition(case_in(state), Cancel(), ctx()))
    assert t.case.state is CaseState.CANCELLED
    assert t.effects == ()


# ------------------------------------------------------------------ model helpers


def test_actor_can_attempt():
    s = step(1, DiyLevel.BASIC, adult_only=True)
    assert VINAY.can_attempt(s)
    assert not PRIYA.can_attempt(s)
    assert not KID.can_attempt(s)
    assert Role.OWNER.is_adult
    assert not Role.GUEST.is_adult
