# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close a poll read on an issue whose writer claim another poller holds.

The contender writes nothing, so all it can keep is its own latch, and what
these cases read is that latch: whether the close is held, and which cycle it
was tied to. The poll's closed reading is older than any read the contender
takes, so a cycle is tied to it only where the record is read first and the
issue behind it still reads closed -- or where the holder noted on its claim
that it is retiring the cycle the record says was dropped. Every other reading
is held unresolved, and one whose record names no cycle leaves whatever an
earlier reading kept.

Called directly, so each reading can be staged exactly; the dispatch suites
reach the same owner through a refused writer claim.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import contended_closes as _contended_closes, observations as _observations
from orchestrator.workflow.late_split import endings as _endings, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_close_reading as _late_close_reading,
    umbrella_terminal as _umbrella_terminal,
)
from tests.support.fakes import FakeGitHubClient
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
    late_generation,
    seed_late_issue,
)

_SLUG = _TEST_SPEC.slug

_WORKFLOW_LOG = "orchestrator.workflow"

# The cycle an operator authorizes once the one the close ended is settled.
_RESTARTED_CYCLE = CYCLE_ID + 1

# Records naming no cycle a close could end: one already marked over, and none.
_NO_CYCLE = (
    ("cancelled", late_generation(cancelled=True)),
    ("none", LateGeneration()),
)


class _ReopenedBehindTheRecord:
    """An issue read that finds the owner open again, as a human reopening it does."""

    def __init__(self, github: FakeGitHubClient) -> None:
        self._read = github.get_issue

    def __call__(self, number: int):
        """Reopen the owner, then answer the read."""
        issue = self._read(number)
        issue.closed = False
        return issue


class _RestartedBeforeTheRecord:
    """A record read the holder restarts the owner's cycle ahead of.

    The holder settles the cycle the close ended and an operator authorizes a
    fresh one, between the poll and the contender's first read: the record
    names the fresh cycle, on an issue open again.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._github = github
        self._reading = github.read_pinned_state

    def __call__(self, issue):
        """Restart the cycle, then read the record."""
        state = self._reading(issue)
        _late_state.write_late_generation(state, late_generation(cycle_id=_RESTARTED_CYCLE))
        self._github.write_pinned_state(issue, state)
        self._github.get_issue(LATE_ISSUE_NUMBER).closed = False
        return self._reading(issue)


class _ContendedCase(ObservedCloseCase):
    """A closed late-split owner whose writer claim this process was refused."""

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.owner = seed_late_issue(self.github, late_generation())
        self.owner.closed = True

    def _kept(self) -> None:
        """What a poll refused the owner's writer claim keeps of the close it read."""
        _contended_closes._kept_contended_close(self.github, _TEST_SPEC, self.owner)

    def _recorded(self, generation: LateGeneration) -> None:
        """Put this generation on the owner's record."""
        state = self.github.read_pinned_state(self.owner)
        _late_state.write_late_generation(state, generation)
        self.github.write_pinned_state(self.owner, state)

    def _retired(self) -> None:
        """The owner's record past the write that retires its cycle."""
        state = self.github.read_pinned_state(self.owner)
        _umbrella_terminal._retired_cycle(state)
        self.github.write_pinned_state(self.owner, state)
        self.assertEqual(_endings.read_retired_cycle(self.github.read_pinned_state(self.owner)), CYCLE_ID)

    def _written(self) -> tuple:
        """Everything a contender could leave on GitHub."""
        return (
            list(self.github.posted_comments),
            list(self.github.label_history),
            self.github.pinned_data(LATE_ISSUE_NUMBER),
        )


class ContendedCloseTest(_ContendedCase, unittest.TestCase):
    """What a refused poll keeps of the close it read, and nothing it writes."""

    def test_a_confirmed_close_is_tied_to_its_cycle(self) -> None:
        before = self._written()

        self._kept()

        self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
        self.assertEqual(_observations.close_scope(_SLUG, LATE_ISSUE_NUMBER), CYCLE_ID)
        self.assertTrue(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID))
        self.assertFalse(
            _observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _RESTARTED_CYCLE),
            "a scoped close ends no other cycle",
        )
        self.assertEqual(self._written(), before, "the contender writes nothing")

    def test_an_unconfirmed_close_is_held_unresolved(self) -> None:
        # Open again behind the record, restarted before it, or never read at
        # all: the close is kept for a pass under the claim, and tied to no
        # cycle, since the one the record names may have started after it.
        unconfirmed = (
            ("reopened", "get_issue", _ReopenedBehindTheRecord(self.github)),
            ("restarted", "read_pinned_state", _RestartedBeforeTheRecord(self.github)),
            ("unreadable", "read_pinned_state", ConnectionError("github unreachable")),
        )
        for case, read, answered in unconfirmed:
            with self.subTest(case=case):
                self._fresh_process()
                self.owner.closed = True
                with patch.object(self.github, read, side_effect=answered), self.assertLogs(_WORKFLOW_LOG):
                    self._kept()

                self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
                self.assertIsNone(_observations.close_scope(_SLUG, LATE_ISSUE_NUMBER))
                self.assertFalse(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID))
                self.assertFalse(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _RESTARTED_CYCLE))

    def test_no_cycle_keeps_what_was_owed(self) -> None:
        # A cycle already marked over, or none at all, is nothing this reading
        # can end -- and no reason to drop a close an earlier reading tied to
        # the cycle it did end.
        for case, generation in _NO_CYCLE:
            with self.subTest(case=case):
                self._fresh_process()
                self._recorded(generation)
                self._kept()
                self.assertEqual(self._observed(_SLUG), frozenset(), "a fresh reading keeps nothing")

                self._latch_close(_SLUG, LATE_ISSUE_NUMBER)
                _observations.scope_close(_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID)
                self._kept()
                self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
                self.assertEqual(_observations.close_scope(_SLUG, LATE_ISSUE_NUMBER), CYCLE_ID)

class NotedRetirementTest(_ContendedCase, unittest.TestCase):
    """An owner another poller retired the cycle off, read while that poller holds it."""

    def test_a_noted_retirement_names_its_cycle(self) -> None:
        # The holder retires the cycle off the record a write before its own
        # barrier, which reads only its own process's latches -- so a close
        # read while its note stands is kept against that cycle, and the
        # record's reader answers it as owed rather than ending nothing.
        self._retired()

        with held_elsewhere(self.github.repo_id, LATE_ISSUE_NUMBER, retiring=CYCLE_ID):
            self._kept()

        self.assertEqual(_observations.close_scope(_SLUG, LATE_ISSUE_NUMBER), CYCLE_ID)
        state = self.github.read_pinned_state(self.owner)
        self.assertEqual(_late_close_reading._ending_cycle(_TEST_SPEC, LATE_ISSUE_NUMBER, state), CYCLE_ID)

    def test_a_retirement_nobody_noted_keeps_nothing(self) -> None:
        # The retired correlation outlives every retirement, so on its own --
        # or beside a note of some other cycle -- it is no proof the close
        # landed inside one.
        self._retired()
        for retiring in (None, _RESTARTED_CYCLE):
            with self.subTest(retiring=retiring):
                with held_elsewhere(self.github.repo_id, LATE_ISSUE_NUMBER, retiring=retiring):
                    self._kept()
                self.assertEqual(self._observed(_SLUG), frozenset())



if __name__ == "__main__":
    unittest.main()
