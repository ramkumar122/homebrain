"""Property tests: random event sequences never break the case invariants (DESIGN.md §3.8)."""

from __future__ import annotations

from datetime import timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import event as label
from hypothesis import strategies as st

from homebrain.domain.case_machine import (
    Context,
    Rejection,
    Transition,
    booking_digest,
    open_case,
    transition,
)
from homebrain.domain.events import (
    Cancel,
    CannotDo,
    CaseEvent,
    Open,
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
from homebrain.domain.model import Actor, Case, CaseState, DiyLevel, Role, StepStatus
from tests.domain.builders import GUEST, KID, NOW, PRIYA, RAM, VINAY, confirm, provider, slot, step

actors = st.sampled_from([VINAY, PRIYA, RAM, KID, GUEST])
diy = st.sampled_from(list(DiyLevel))
steps = st.lists(st.tuples(diy, st.booleans()), max_size=5).map(
    lambda xs: tuple(step(i + 1, d, adult_only=a) for i, (d, a) in enumerate(xs))
)
offers = st.lists(
    st.integers(min_value=1, max_value=2).map(
        lambda n: provider(f"p{n}", slot("sl1"), slot("sl2", NOW + timedelta(days=4)))
    ),
    min_size=0,
    max_size=2,
    unique_by=lambda p: p.provider_id,
).map(tuple)


@st.composite
def event_for(draw: st.DrawFn, case: Case) -> CaseEvent:
    """Any event, weighted so runs get deep: ids usually match, Cancel is rare."""
    step_ids = [s.step_id for s in case.steps] or ["s1"]
    step_id = draw(st.one_of(st.none(), st.sampled_from(step_ids)))
    known = [p.provider_id for p in case.providers] or ["p1"]
    provider_id = draw(st.sampled_from([*known, *known, *known, "p9"]))
    challenge = draw(st.sampled_from([case.challenge_id or "c1"] * 4 + ["c-other"]))
    pending = case.pending_booking
    digest = booking_digest(case, pending) if pending else "none"
    kind = draw(
        st.sampled_from(
            ["step"] * 4
            + ["professional", "providers", "providers"]
            + ["confirm"] * 4
            + ["verified"] * 3
            + ["failed", "expired", "fixed", "not_fixed", "cancel"]
        )
    )
    match kind:
        case "step":
            return draw(
                st.sampled_from(
                    [
                        StepWorked(step_id),
                        StepFailed(step_id),
                        StepSkipped(step_id),
                        CannotDo(step_id),
                    ]
                )
            )
        case "professional":
            return WantProfessional()
        case "providers":
            return ProvidersFound(draw(offers))
        case "confirm":
            return confirm(
                provider_id,
                draw(st.sampled_from(["sl1", "sl2"])),
                grant=draw(st.booleans()),
                available=draw(st.sampled_from([True, True, True, False])),
                n=draw(st.integers(min_value=1, max_value=50)),
            )
        case "verified":
            return Verified(
                challenge,
                draw(st.sampled_from([digest, digest, digest, "bad"])),
                hold_valid=draw(st.sampled_from([True, True, False])),
            )
        case "failed":
            return VerificationFailed(challenge)
        case "expired":
            return VerificationExpired(challenge)
        case "fixed":
            return TechFixed()
        case "not_fixed":
            return TechNotFixed()
        case _:
            return Cancel()


def check_invariants(case: Case) -> None:
    current = [s for s in case.steps if s.status is StepStatus.CURRENT]
    assert len(current) <= 1
    assert bool(current) == (case.state is CaseState.TROUBLESHOOTING)
    pending = case.state is CaseState.PENDING_VERIFICATION
    assert (case.pending_booking is not None) == pending
    assert (case.challenge_id is not None) == pending
    if case.state is CaseState.BOOKED:
        assert case.booking is not None
    if case.state is CaseState.PROVIDERS_PROPOSED:
        assert case.providers
    if case.pending_booking is not None:
        assert case.pending_booking.requested_by is not None
    for s in case.steps:
        tried = s.status not in (StepStatus.PENDING, StepStatus.CURRENT)
        assert (s.outcome_at is not None) == tried


@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(
    candidate_steps=steps,
    opener=actors.filter(lambda a: a.role is not Role.GUEST),
    data=st.data(),
)
def test_random_event_sequences_keep_invariants(
    candidate_steps: tuple, opener: Actor, data: st.DataObject
) -> None:
    now = NOW
    case = open_case(
        Open("case1", "hh1", "a1", "broken", None, candidate_steps), Context(opener, now)
    ).case
    check_invariants(case)
    for _ in range(data.draw(st.integers(min_value=1, max_value=25))):
        now += timedelta(minutes=data.draw(st.integers(min_value=1, max_value=600)))
        event = data.draw(event_for(case))
        result = transition(case, event, Context(data.draw(actors), now))
        if not case.state.is_active:
            assert isinstance(result, Rejection), "terminal states have no way out"
            continue
        if isinstance(result, Transition):
            assert result.from_state is case.state
            if result.duplicate:
                assert result.case is case
                assert result.effects == ()
            else:
                assert result.case.version == case.version + 1
                assert result.case.updated_at == now
                assert result.event_type == event.event_type
                case = result.case
                label(f"reached {case.state.value}")
        check_invariants(case)
