"""Permissions table (DESIGN.md §4.4), tested cell by cell."""

from __future__ import annotations

import pytest

from homebrain.domain.model import Role
from homebrain.domain.policy import Action, DenialCode, authorize

A, R = Action, Role
ALLOW, STEP_UP = "allow", "step_up"
GUEST_NO, ROLE_NO = DenialCode.FORBIDDEN_FOR_GUEST, DenialCode.FORBIDDEN_FOR_ROLE

# (action, role) -> (guest_can_report=False, guest_can_report=True)
TABLE = {
    **{(a, r): (ALLOW, ALLOW) for a in (A.VIEW_ASSETS, A.VIEW_COVERAGE, A.VIEW_CASE) for r in R},
    **{
        (a, r): (ALLOW, ALLOW)
        for a in (A.OPEN_CASE, A.ADVANCE_CASE, A.FIND_PROVIDERS)
        for r in (R.OWNER, R.ADULT, R.CHILD)
    },
    **{(a, R.GUEST): (GUEST_NO, ALLOW) for a in (A.OPEN_CASE, A.ADVANCE_CASE, A.FIND_PROVIDERS)},
    (A.BOOK_SERVICE, R.OWNER): (STEP_UP, STEP_UP),
    (A.BOOK_SERVICE, R.ADULT): (STEP_UP, STEP_UP),
    (A.BOOK_SERVICE, R.CHILD): (ROLE_NO, ROLE_NO),
    (A.BOOK_SERVICE, R.GUEST): (GUEST_NO, GUEST_NO),
    (A.MANAGE_MEMBERS, R.OWNER): (STEP_UP, STEP_UP),
    (A.MANAGE_MEMBERS, R.ADULT): (ROLE_NO, ROLE_NO),
    (A.MANAGE_MEMBERS, R.CHILD): (ROLE_NO, ROLE_NO),
    (A.MANAGE_MEMBERS, R.GUEST): (GUEST_NO, GUEST_NO),
}


def test_table_is_complete():
    assert set(TABLE) == {(a, r) for a in Action for r in Role}


@pytest.mark.parametrize(
    ("action", "role", "guest_can_report", "expected"),
    [(a, r, g, TABLE[(a, r)][g]) for (a, r) in TABLE for g in (False, True)],
)
def test_authorize(action, role, guest_can_report, expected):
    d = authorize(action, role, guest_can_report=guest_can_report)
    if expected == ALLOW:
        assert (d.allowed, d.requires_step_up, d.denial) == (True, False, None)
    elif expected == STEP_UP:
        assert (d.allowed, d.requires_step_up, d.denial) == (True, True, None)
    else:
        assert (d.allowed, d.denial) == (False, expected)
        assert d.reason
