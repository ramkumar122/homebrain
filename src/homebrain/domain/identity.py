"""Tier 2 identity: who is probably speaking (DESIGN.md §4.3).

HomeBrain does not recognise voices. It combines what it is given: an explicit
person id if a client ever sends one, else the name the speaker said
("this is Priya"), else the household's default. The result always says which
rule decided it, so the assistant can phrase itself honestly.

This tier personalises answers. It never grants permission for a sensitive
action; only Tier 3 (passkey step-up) does that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from homebrain.domain.model import Actor, DiyLevel, Role

FUZZY_THRESHOLD = 0.85

_FILLERS = (
    "hi ",
    "hey ",
    "hello ",
    "this is ",
    "it's ",
    "it is ",
    "i'm ",
    "i am ",
    "my name is ",
)
_SUFFIXES = (" here", " speaking")


class Resolution(StrEnum):
    EXPLICIT = "explicit"
    SPEAKER_HINT = "speaker_hint"
    ACCOUNT_OWNER_ASSUMED = "account_owner_assumed"
    GUEST = "guest"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class DefaultPersonPolicy(StrEnum):
    OWNER = "owner"
    GUEST = "guest"


@dataclass(frozen=True, slots=True)
class Member:
    person_id: str
    display_name: str
    role: Role
    diy_tolerance: DiyLevel
    aliases: tuple[str, ...] = ()

    def names(self) -> frozenset[str]:
        """Normalised names this member answers to, including their first name."""
        full = normalize_name(self.display_name)
        first = full.split(" ")[0] if full else ""
        return frozenset(n for n in (full, first, *map(normalize_name, self.aliases)) if n)


@dataclass(frozen=True, slots=True)
class Roster:
    members: tuple[Member, ...]
    owner_person_id: str
    default_person_policy: DefaultPersonPolicy = DefaultPersonPolicy.OWNER

    def member(self, person_id: str) -> Member | None:
        return next((m for m in self.members if m.person_id == person_id), None)


@dataclass(frozen=True, slots=True)
class ResolvedPerson:
    person_id: str | None
    display_name: str
    role: Role
    diy_tolerance: DiyLevel
    resolution: Resolution
    confidence: Confidence
    name_heard: str | None = None

    @property
    def actor(self) -> Actor:
        return Actor(self.person_id, self.role, self.diy_tolerance)


@dataclass(frozen=True, slots=True)
class AmbiguousPerson:
    """More than one member matches what was heard. Ask which one."""

    name_heard: str
    candidates: tuple[Member, ...]


def normalize_name(text: str) -> str:
    s = text.casefold().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    s = " ".join(re.sub(r"[^\w\s']", " ", s).split())
    stripped = True
    while stripped:
        stripped = False
        for filler in _FILLERS:
            if s.startswith(filler):
                s, stripped = s[len(filler) :], True
    for suffix in _SUFFIXES:
        s = s.removesuffix(suffix)
    s = s.strip()
    return "" if f"{s} " in _FILLERS else s


def resolve_person(
    roster: Roster,
    *,
    speaker_hint: str | None,
    explicit_person_id: str | None = None,
) -> ResolvedPerson | AmbiguousPerson:
    if explicit_person_id is not None:
        member = roster.member(explicit_person_id)
        if member is not None:
            return _as_member(member, Resolution.EXPLICIT, Confidence.HIGH)

    heard = normalize_name(speaker_hint or "")
    if heard:
        return _match_hint(roster, heard)

    if roster.default_person_policy is DefaultPersonPolicy.OWNER:
        owner = roster.member(roster.owner_person_id)
        if owner is not None:
            return _as_member(owner, Resolution.ACCOUNT_OWNER_ASSUMED, Confidence.LOW)
    return guest()


def guest(name_heard: str | None = None) -> ResolvedPerson:
    return ResolvedPerson(
        person_id=None,
        display_name="Guest",
        role=Role.GUEST,
        diy_tolerance=DiyLevel.NONE,
        resolution=Resolution.GUEST,
        confidence=Confidence.NONE,
        name_heard=name_heard,
    )


def _match_hint(roster: Roster, heard: str) -> ResolvedPerson | AmbiguousPerson:
    exact = tuple(m for m in roster.members if heard in m.names())
    if len(exact) == 1:
        return _as_member(exact[0], Resolution.SPEAKER_HINT, Confidence.MEDIUM, heard)
    if exact:
        return AmbiguousPerson(heard, exact)

    fuzzy = tuple(
        m
        for m in roster.members
        if max((SequenceMatcher(None, heard, n).ratio() for n in m.names()), default=0.0)
        >= FUZZY_THRESHOLD
    )
    if len(fuzzy) == 1:
        return _as_member(fuzzy[0], Resolution.SPEAKER_HINT, Confidence.LOW, heard)
    if fuzzy:
        return AmbiguousPerson(heard, fuzzy)
    return guest(name_heard=heard)


def _as_member(
    member: Member,
    resolution: Resolution,
    confidence: Confidence,
    name_heard: str | None = None,
) -> ResolvedPerson:
    return ResolvedPerson(
        person_id=member.person_id,
        display_name=member.display_name,
        role=member.role,
        diy_tolerance=member.diy_tolerance,
        resolution=resolution,
        confidence=confidence,
        name_heard=name_heard,
    )
