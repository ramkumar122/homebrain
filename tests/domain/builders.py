"""Small builders for domain tests. Cases are built by running the real machine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homebrain.domain.case_machine import (
    Context,
    Rejection,
    Result,
    Transition,
    open_case,
    transition,
)
from homebrain.domain.events import BookingConfirmed, Cancel, Open, ProvidersFound, StepWorked
from homebrain.domain.model import (
    Actor,
    Case,
    CaseState,
    Citation,
    DiyLevel,
    ProviderOffer,
    Role,
    SlotOffer,
    Step,
)

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

VINAY = Actor("p_vinay", Role.ADULT, DiyLevel.CONFIDENT)
PRIYA = Actor("p_priya", Role.ADULT, DiyLevel.NONE)
RAM = Actor("p_ram", Role.OWNER, DiyLevel.BASIC)
KID = Actor("p_kid", Role.CHILD, DiyLevel.CONFIDENT)
GUEST = Actor(None, Role.GUEST, DiyLevel.NONE)


def cite(page: int = 1) -> Citation:
    return Citation("d_manual", "Dishwasher manual", "manual", page, "quote", "test_fixture")


def step(i: int, diy: DiyLevel = DiyLevel.BASIC, *, adult_only: bool = False) -> Step:
    return Step(f"s{i}", f"k{i}", i, f"Do thing {i}", diy, cite(i), adult_only=adult_only)


def ctx(actor: Actor = VINAY, now: datetime = NOW) -> Context:
    return Context(actor, now)


def slot(slot_id: str = "sl1", start: datetime = NOW + timedelta(days=3)) -> SlotOffer:
    return SlotOffer(slot_id, start, start + timedelta(hours=2), "Thu 9-11am")


def provider(provider_id: str = "p1", *slots: SlotOffer) -> ProviderOffer:
    return ProviderOffer(
        provider_id, f"Demo {provider_id}", "independent", True, 8900, slots or (slot(),)
    )


def ok(result: Result) -> Transition:
    assert isinstance(result, Transition), result
    return result


def rejected(result: Result) -> Rejection:
    assert isinstance(result, Rejection), result
    return result


def confirm(
    provider_id: str = "p1",
    slot_id: str = "sl1",
    *,
    grant: bool = False,
    available: bool = True,
    n: int = 1,
) -> BookingConfirmed:
    return BookingConfirmed(provider_id, slot_id, available, grant, f"b{n}", f"c{n}")


def opened(steps: tuple[Step, ...] = (step(1), step(2), step(3)), actor: Actor = VINAY) -> Case:
    event = Open("case1", "hh1", "a_dishwasher", "water in the bottom", "not_draining", steps)
    return open_case(event, ctx(actor)).case


def case_in(state: CaseState) -> Case:
    """A realistic case in the given state, reached through real transitions."""
    match state:
        case CaseState.TROUBLESHOOTING:
            return opened()
        case CaseState.NEEDS_SERVICE:
            return opened(steps=())
        case CaseState.PROVIDERS_PROPOSED:
            return ok(
                transition(case_in(CaseState.NEEDS_SERVICE), ProvidersFound((provider(),)), ctx())
            ).case
        case CaseState.PENDING_VERIFICATION:
            return ok(transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(), ctx())).case
        case CaseState.BOOKED:
            return ok(
                transition(case_in(CaseState.PROVIDERS_PROPOSED), confirm(grant=True), ctx())
            ).case
        case CaseState.RESOLVED:
            return ok(transition(opened(), StepWorked(), ctx())).case
        case CaseState.CANCELLED:
            return ok(transition(opened(), Cancel(), ctx())).case
