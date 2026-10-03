# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The closed owner's close, kept while another poller on this host holds it.

What that poller writes while it holds the owner is written onto the record
as it would leave it; everything else is the real tick, through whichever
dispatch mode a case names.
"""
from __future__ import annotations

from orchestrator.workflow.late_split import restart as _restart, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import cleanup_deferral_support as _deferral


def ticked_on(case: _deferral.DeferralCase, limit: int, *, scheduled: bool) -> None:
    """One tick over the closed owner, through the mode the arguments name."""
    if scheduled:
        case._ticked(case._scheduler())
        return
    _deferral.ticked_directly(case, limit)


def restarted_elsewhere(github: FakeGitHubClient) -> None:
    """What another poller leaves on the closed owner while it holds it.

    It ends the cycle the close ended and settles everything that cycle owed,
    and an operator then authorizes a fresh attempt: the issue is open again,
    and its record carries the live cycle the restart projects, which owes
    nothing yet.
    """
    owner = github.get_issue(_deferral.OWNER_NUMBER)
    state = github.read_pinned_state(owner)
    _late_state.write_late_generation(state, _restart.retire_restart(LateGeneration(
        cycle_id=_deferral.CYCLE_ID,
        root_issue=_deferral.OWNER_NUMBER,
        current_issue=_deferral.OWNER_NUMBER,
        cancelled=True,
    )))
    github.write_pinned_state(owner, state)
    owner.closed = False


class FirstReadFails:
    """A read that fails the first time it is asked, and answers after."""

    def __init__(self, reading) -> None:
        self._reading = reading
        self._asked = False

    def __call__(self, *asked):
        """Refuse the first read the way an outage does, and answer the rest."""
        if not self._asked:
            self._asked = True
            raise ConnectionError("github unreachable")
        return self._reading(*asked)
