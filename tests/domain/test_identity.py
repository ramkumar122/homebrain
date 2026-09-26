"""Tier 2 identity resolution (DESIGN.md §4.3)."""

from __future__ import annotations

import pytest

from homebrain.domain.identity import (
    AmbiguousPerson,
    Confidence,
    DefaultPersonPolicy,
    Member,
    Resolution,
    ResolvedPerson,
    Roster,
    normalize_name,
    resolve_person,
)
from homebrain.domain.model import Actor, DiyLevel, Role

RAM = Member("p_ram", "Ram Kumar", Role.OWNER, DiyLevel.BASIC)
VINAY = Member("p_vinay", "Vinay", Role.ADULT, DiyLevel.CONFIDENT, aliases=("V", "Vin"))
PRIYA = Member("p_priya", "Priya", Role.ADULT, DiyLevel.NONE)
ROSTER = Roster((RAM, VINAY, PRIYA), owner_person_id="p_ram")


def resolved(r: ResolvedPerson | AmbiguousPerson) -> ResolvedPerson:
    assert isinstance(r, ResolvedPerson), r
    return r


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Vinay", "vinay"),
        ("This is Vinay", "vinay"),
        ("Hi, it's Priya here", "priya"),
        ("I\N{RIGHT SINGLE QUOTATION MARK}m Ram!", "ram"),
        ("hey this is Ram Kumar speaking", "ram kumar"),
        ("my name is  PRIYA.", "priya"),
        ("   ", ""),
        ("this is", ""),
        ("hello", ""),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_member_answers_to_full_name_first_name_and_aliases():
    assert RAM.names() == {"ram kumar", "ram"}
    assert VINAY.names() == {"vinay", "v", "vin"}
    assert Member("x", "!!!", Role.ADULT, DiyLevel.NONE).names() == frozenset()


def test_explicit_person_id_wins():
    r = resolved(resolve_person(ROSTER, speaker_hint="Priya", explicit_person_id="p_vinay"))
    assert (r.person_id, r.resolution, r.confidence) == (
        "p_vinay",
        Resolution.EXPLICIT,
        Confidence.HIGH,
    )


def test_unknown_explicit_id_is_ignored():
    r = resolved(resolve_person(ROSTER, speaker_hint=None, explicit_person_id="p_nobody"))
    assert r.resolution is Resolution.ACCOUNT_OWNER_ASSUMED


@pytest.mark.parametrize("hint", ["Priya", "this is priya", "PRIYA here"])
def test_speaker_hint_exact_match(hint):
    r = resolved(resolve_person(ROSTER, speaker_hint=hint))
    assert (r.person_id, r.resolution, r.confidence) == (
        "p_priya",
        Resolution.SPEAKER_HINT,
        Confidence.MEDIUM,
    )
    assert r.name_heard == "priya"
    assert r.actor == Actor("p_priya", Role.ADULT, DiyLevel.NONE)


@pytest.mark.parametrize(("hint", "person"), [("Vin", "p_vinay"), ("Ram", "p_ram")])
def test_speaker_hint_matches_alias_and_first_name(hint, person):
    assert resolved(resolve_person(ROSTER, speaker_hint=hint)).person_id == person


def test_speaker_hint_fuzzy_match_has_low_confidence():
    r = resolved(resolve_person(ROSTER, speaker_hint="Vinnay"))
    assert (r.person_id, r.confidence) == ("p_vinay", Confidence.LOW)


def test_exact_match_on_two_members_is_ambiguous():
    sam1 = Member("p_s1", "Samantha", Role.ADULT, DiyLevel.BASIC, aliases=("Sam",))
    sam2 = Member("p_s2", "Samuel", Role.CHILD, DiyLevel.BASIC, aliases=("Sam",))
    r = resolve_person(Roster((sam1, sam2), "p_s1"), speaker_hint="Sam")
    assert isinstance(r, AmbiguousPerson)
    assert {m.person_id for m in r.candidates} == {"p_s1", "p_s2"}
    assert r.name_heard == "sam"


def test_fuzzy_match_on_two_members_is_ambiguous():
    a = Member("p_a", "Christina", Role.ADULT, DiyLevel.BASIC)
    b = Member("p_b", "Christine", Role.ADULT, DiyLevel.BASIC)
    r = resolve_person(Roster((a, b), "p_a"), speaker_hint="Christin")
    assert isinstance(r, AmbiguousPerson)
    assert len(r.candidates) == 2


def test_unknown_name_is_a_guest():
    r = resolved(resolve_person(ROSTER, speaker_hint="This is Bob"))
    assert (r.person_id, r.role, r.resolution, r.name_heard) == (
        None,
        Role.GUEST,
        Resolution.GUEST,
        "bob",
    )
    assert r.diy_tolerance is DiyLevel.NONE
    assert r.confidence is Confidence.NONE


def test_member_without_usable_names_never_matches():
    nameless = Member("p_x", "???", Role.ADULT, DiyLevel.BASIC)
    r = resolved(resolve_person(Roster((nameless,), "p_x"), speaker_hint="Bob"))
    assert r.resolution is Resolution.GUEST


@pytest.mark.parametrize("hint", [None, "", "  ", "?!", "this is"])
def test_no_usable_hint_assumes_the_account_owner(hint):
    r = resolved(resolve_person(ROSTER, speaker_hint=hint))
    assert (r.person_id, r.resolution, r.confidence) == (
        "p_ram",
        Resolution.ACCOUNT_OWNER_ASSUMED,
        Confidence.LOW,
    )


def test_shared_device_household_defaults_to_guest():
    roster = Roster(ROSTER.members, "p_ram", DefaultPersonPolicy.GUEST)
    assert resolved(resolve_person(roster, speaker_hint=None)).resolution is Resolution.GUEST


def test_missing_owner_falls_back_to_guest():
    roster = Roster((VINAY,), owner_person_id="p_gone")
    assert resolved(resolve_person(roster, speaker_hint=None)).resolution is Resolution.GUEST
