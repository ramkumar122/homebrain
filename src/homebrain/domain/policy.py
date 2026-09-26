"""Who may do what (DESIGN.md §4.4).

Roles come from Tier 2 identity, which is only a best guess. So anything that
spends money or changes access also needs Tier 3: a fresh passkey step-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from homebrain.domain.model import Role


class Action(StrEnum):
    VIEW_ASSETS = "view_assets"
    VIEW_COVERAGE = "view_coverage"
    VIEW_CASE = "view_case"
    OPEN_CASE = "open_case"
    ADVANCE_CASE = "advance_case"
    FIND_PROVIDERS = "find_providers"
    BOOK_SERVICE = "book_service"
    MANAGE_MEMBERS = "manage_members"


class DenialCode(StrEnum):
    FORBIDDEN_FOR_GUEST = "FORBIDDEN_FOR_GUEST"
    FORBIDDEN_FOR_ROLE = "FORBIDDEN_FOR_ROLE"


READ_ACTIONS = frozenset({Action.VIEW_ASSETS, Action.VIEW_COVERAGE, Action.VIEW_CASE})
REPORT_ACTIONS = frozenset({Action.OPEN_CASE, Action.ADVANCE_CASE, Action.FIND_PROVIDERS})
STEP_UP_ACTIONS = frozenset({Action.BOOK_SERVICE, Action.MANAGE_MEMBERS})

_ALLOWED_ROLES: dict[Action, frozenset[Role]] = {
    Action.BOOK_SERVICE: frozenset({Role.OWNER, Role.ADULT}),
    Action.MANAGE_MEMBERS: frozenset({Role.OWNER}),
}


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    requires_step_up: bool = False
    denial: DenialCode | None = None
    reason: str | None = None


def authorize(action: Action, role: Role, *, guest_can_report: bool) -> Decision:
    if action in READ_ACTIONS:
        return Decision(allowed=True)

    if action in REPORT_ACTIONS:
        if role is Role.GUEST and not guest_can_report:
            return _deny(
                DenialCode.FORBIDDEN_FOR_GUEST,
                "This household only lets members report problems.",
            )
        return Decision(allowed=True)

    if role not in _ALLOWED_ROLES[action]:
        if role is Role.GUEST:
            return _deny(DenialCode.FORBIDDEN_FOR_GUEST, "Guests can't do this.")
        return _deny(DenialCode.FORBIDDEN_FOR_ROLE, f"A household {role.value} can't do this.")
    return Decision(allowed=True, requires_step_up=action in STEP_UP_ACTIONS)


def _deny(code: DenialCode, reason: str) -> Decision:
    return Decision(allowed=False, denial=code, reason=reason)
