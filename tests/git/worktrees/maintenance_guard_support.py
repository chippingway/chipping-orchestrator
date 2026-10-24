# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claim and continuation answers at a maintenance pass boundary."""
from __future__ import annotations

from tests.support import writer_claims as _writer_claims


def _never_claimed(_repo_slug: str, _issue_number: int) -> bool:
    """The guard a host with nothing running for this issue answers with."""
    return False


def _always_claimed(_repo_slug: str, _issue_number: int) -> bool:
    """The guard a host that is mid-run for this issue answers with."""
    return True


def _unanswerable_claim(_repo_slug: str, _issue_number: int) -> bool:
    """A guard that fails the way one reaching into a live scheduler can."""
    raise RuntimeError("the scheduler could not be asked")


def _going_on() -> bool:
    """The continuation a process that is not stopping answers with."""
    return True


def _stopping() -> bool:
    """The continuation a process whose run has been stopped answers with."""
    return False


def _unanswerable_continuation() -> bool:
    """A continuation that fails the way one reaching into a live run can."""
    raise RuntimeError("the run could not be asked whether it goes on")


class ClaimProbe:
    """One step of a pass, recording whether a second writer could take an issue's claim as it runs.

    `key` is the repository id and the issue number the claim is keyed on.

    Wrapped around a read or a mutation the pass makes, so a case can say the
    claim was held at that very moment: a second writer is refused here
    exactly when some holder -- the pass among them -- has the issue.
    """

    def __init__(self, step, key: tuple[int, int], seen: list[bool]) -> None:
        self._step = step
        self._key = key
        self._seen = seen

    def __call__(self, *args, **options):
        self._seen.append(_writer_claims.claimable(*self._key))
        return self._step(*args, **options)
