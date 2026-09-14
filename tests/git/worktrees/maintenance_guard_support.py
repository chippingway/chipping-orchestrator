# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claim and continuation answers at a maintenance pass boundary."""
from __future__ import annotations


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
