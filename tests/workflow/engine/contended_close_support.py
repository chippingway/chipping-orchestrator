# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The closed owner's close, kept while another poller on this host holds it.

What that poller writes while it holds the owner is written onto the record
as it would leave it; everything else is the real tick, through whichever
dispatch mode a case names.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from orchestrator.workflow.late_split import restart as _restart, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from tests.support.fakes import FakeGitHubClient
from tests.support.writer_claims import claimable, signed_by_another_poller
from tests.workflow.engine import cleanup_deferral_support as _deferral


def ticked_on(case: _deferral.DeferralCase, limit: int, *, scheduled: bool) -> None:
    """One tick over the closed owner, through the mode the arguments name."""
    if scheduled:
        case._ticked(case._scheduler())
        return
    _deferral.ticked_directly(case, limit)


def restarted_elsewhere(github: FakeGitHubClient, *, signed: bool = True) -> None:
    """What another poller leaves on the closed owner while it holds it.

    It ends the cycle the close ended and settles everything that cycle owed,
    and an operator then authorizes a fresh attempt: the issue is open again,
    and its record carries the live cycle the restart projects, which owes
    nothing yet. All of it under that poller's claim, which it signs as it
    lets go -- or, `signed` False, by this process's own worker, unrecorded.
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
    if signed:
        signed_by_another_poller(github.repo_id, _deferral.OWNER_NUMBER)


class ClosedOwnerCase(_deferral.DeferralCase):
    """The closed owner, seeded afresh for each mode a case ticks it through."""

    def _seeded_owner(self) -> None:
        """The closed owner afresh, in a process that has observed nothing."""
        self.github = _deferral.owner_holding_a_ref()
        self._fresh_process()
        self.stage.reset_mock()

    def _ended_over(self) -> None:
        """The owner's record with its cycle already ended, before any restart."""
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        state = self.github.read_pinned_state(owner)
        _late_state.write_late_generation(state, replace(self._generation(), cancelled=True))
        self.github.write_pinned_state(owner, state)

    def _generation(self) -> LateGeneration:
        """The late cycle the owner's record carries right now."""
        return _late_state.read_late_generation(
            self.github.read_pinned_state(self.github.get_issue(_deferral.OWNER_NUMBER)),
        )

    def _assert_restarted_cycle_spared(self, before: tuple) -> None:
        """The retry left the fresh cycle live and let the settled close go."""
        restarted = self._generation()
        self.assertGreater(restarted.cycle_id, _deferral.CYCLE_ID)
        self.assertFalse(restarted.cancelled, "the fresh cycle is not ended by the old close")
        self.assertEqual(written(self.github), before, "nothing is posted, relabelled, or recorded")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset(), "the settled close is let go")
        self.stage.assert_not_called()


def written(github: FakeGitHubClient) -> tuple:
    """Everything a pass could leave on the owner: comments, labels, and its record."""
    return (
        list(github.posted_comments),
        list(github.label_history),
        github.pinned_data(_deferral.OWNER_NUMBER),
    )


class RestartedAfter:
    """One step of the poll that, once it returns, finds the owner restarted elsewhere.

    `found` has another thread of this process take the owner's claim and let
    go right behind the restart, as a worker or a partition of this process
    can: that claim finds the restart's hold before the pass carrying the
    poll's reading does. `found_by` keeps whether each such claim was granted.
    """

    def __init__(self, github: FakeGitHubClient, step, *, found: bool = False, signed: bool = True) -> None:
        self._github = github
        self._step = step
        self._found = found
        self._signed = signed
        self.found_by: list[bool] = []

    def __call__(self, *asked):
        """Take the step, then restart the owner's cycle the first time."""
        answered = self._step(*asked)
        owner = self._github.get_issue(_deferral.OWNER_NUMBER)
        if not _late_state.read_late_generation(self._github.read_pinned_state(owner)).restart_predecessor:
            restarted_elsewhere(self._github, signed=self._signed)
            if self._found:
                with ThreadPoolExecutor(max_workers=1) as another_thread:
                    claiming = another_thread.submit(claimable, self._github.repo_id, _deferral.OWNER_NUMBER)
                    self.found_by.append(claiming.result())
        return answered


class RestartedBeforeTheRead:
    """A record read the holder restarts the closed owner's cycle ahead of.

    What the contender's read finds when the other poller settles the cycle
    the close ended, and an operator restarts it, between the poll and that
    read: the fresh cycle, on an issue open again.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._github = github
        self._reading = github.read_pinned_state
        self._restarted = False

    def __call__(self, issue):
        """Restart the cycle the first time the record is asked for, then read it."""
        if not self._restarted:
            self._restarted = True
            with patch.object(self._github, "read_pinned_state", self._reading):
                restarted_elsewhere(self._github)
        return self._reading(issue)


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
