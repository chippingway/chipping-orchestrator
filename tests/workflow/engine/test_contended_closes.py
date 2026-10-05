# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close a poll read on an issue whose writer claim another poller holds.

The contender writes nothing, so all it can keep is its own latch, and what
these cases read is that latch: whether the close is held, and which cycle it
was tied to. The poll's closed reading is older than any read the contender
takes, so a cycle is tied to it only where the record is read first and the
issue behind it still reads closed, with the record read again behind that
naming the same cycle -- or where the holder noted on its claim that it is
retiring the cycle the record says was dropped. Every other reading is held
unresolved, and one whose record names no cycle leaves whatever an earlier
reading kept.

Called directly, so each reading can be staged exactly; the dispatch suites
reach the same owner through a refused writer claim.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    contended_closes as _contended_closes,
    observations as _observations,
    publication_holds as _publication_holds,
)
from orchestrator.workflow.late_split import endings as _endings, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_close_observation as _late_close_observation,
    late_close_reading as _late_close_reading,
    umbrella_terminal as _umbrella_terminal,
)
from tests.support.fakes import FakeGitHubClient
from tests.support.writer_claims import held_elsewhere, signed_by_another_poller
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

# What every contender case asserts of the comments and labels it leaves.
_WRITES_NOTHING = "the contender's reads write nothing"

# The client reads that answer the owner's record, and the owner itself.
_RECORD_READ = "read_pinned_state"
_ISSUE_READ = "get_issue"

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


class _RestartedBehindTheRecord:
    """A record read the holder restarts the owner's cycle behind, and a human closes the fresh one.

    Each read answers the record as it stood and then moves it on, up to
    `restarts` cycles past the one the case seeded -- one, for a holder that
    restarts once; more than a contender reads, for a record never still.
    """

    def __init__(self, github: FakeGitHubClient, restarts: int = 1) -> None:
        self._github = github
        self._reading = github.read_pinned_state
        self._last = CYCLE_ID + restarts

    def __call__(self, issue):
        """Read the record, then restart its cycle and close the fresh one."""
        state = self._reading(issue)
        cycle_id = _late_state.read_late_generation(state).cycle_id
        if cycle_id < self._last:
            restarted = self._reading(issue)
            _late_state.write_late_generation(restarted, late_generation(cycle_id=cycle_id + 1))
            self._github.write_pinned_state(issue, restarted)
            self._github.get_issue(LATE_ISSUE_NUMBER).closed = True
        return state


class _HolderDuring:
    """A read the owner's retiring holder acts during, the first time it is asked.

    It notes its retirement of the cycle on the claim before the read answers
    -- letting go over that note there, where `released` -- and runs `retire`,
    where given, behind the answer, as the retirement write that follows it.
    """

    def __init__(self, github: FakeGitHubClient, read: str, *, released: bool = True, retire=None) -> None:
        self._github = github
        self._read = getattr(github, read)
        self._released = released
        self._retire = retire
        self._acted = False

    def __call__(self, *asked):
        """Sign the claim as the holder does, answer the read, then retire behind it."""
        acting = not self._acted
        self._acted = True
        if acting:
            signed_by_another_poller(
                self._github.repo_id, LATE_ISSUE_NUMBER, retiring=CYCLE_ID, released=self._released,
            )
        answered = self._read(*asked)
        if acting and self._retire is not None:
            self._retire()
        return answered


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

    def _scope(self) -> int | None:
        """The cycle the close this process holds was tied to, if any."""
        return _observations.close_scope(_SLUG, LATE_ISSUE_NUMBER)

    def _said(self) -> tuple:
        """The comments and labels a contender could leave, which a holder writing the record leaves alone."""
        return list(self.github.posted_comments), list(self.github.label_history)

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
        self.assertEqual(self._scope(), CYCLE_ID)
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
            ("reopened", _ISSUE_READ, _ReopenedBehindTheRecord(self.github)),
            ("restarted", _RECORD_READ, _RestartedBeforeTheRecord(self.github)),
            ("unreadable", _RECORD_READ, ConnectionError("github unreachable")),
        )
        for case, read, answered in unconfirmed:
            with self.subTest(case=case):
                self._fresh_process()
                self.owner.closed = True
                with patch.object(self.github, read, side_effect=answered), self.assertLogs(_WORKFLOW_LOG):
                    self._kept()

                self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
                self.assertIsNone(self._scope())
                self.assertFalse(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID))
                self.assertFalse(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _RESTARTED_CYCLE))

    def test_a_close_behind_a_restart_ends_its_cycle(self) -> None:
        # The first record read names the cycle the close ended, still live or
        # already marked over; the holder restarts it before the issue is read,
        # and the issue reads closed again. The record read behind the issue
        # names the fresh cycle, so the close is confirmed against that one.
        for generation in (late_generation(), late_generation(cancelled=True)):
            with self.subTest(cancelled=generation.cancelled):
                self._fresh_process()
                self._recorded(generation)
                said = self._said()
                with patch.object(self.github, _RECORD_READ, _RestartedBehindTheRecord(self.github)):
                    self._kept()

                self.assertEqual(self._scope(), _RESTARTED_CYCLE)
                self.assertTrue(_observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _RESTARTED_CYCLE))
                self.assertEqual(self._said(), said, _WRITES_NOTHING)

    def test_a_record_never_still_holds_it_unresolved(self) -> None:
        # Restarted behind every read the contender takes: no read confirms
        # the close against any one cycle, so it is kept tied to none.
        restarting = _RestartedBehindTheRecord(self.github, restarts=_contended_closes._CONFIRMING_READS + 1)
        with patch.object(self.github, _RECORD_READ, restarting), self.assertLogs(_WORKFLOW_LOG):
            self._kept()

        self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
        self.assertIsNone(self._scope())
        self.assertEqual(self._said(), ([], []), "nor do they once the record gives up")

    def test_it_outlives_a_postponed_settlement(self) -> None:
        # This process's worker let the claim go and the hold behind it is
        # still postponing that worker's drop: the contender's close is a
        # fresh reading, which that drop was never about.
        _publication_holds.claim_publication(_SLUG, LATE_ISSUE_NUMBER)
        self._latch_close(_SLUG, LATE_ISSUE_NUMBER)
        _observations.settle_close(_SLUG, LATE_ISSUE_NUMBER)
        self._kept()
        _publication_holds.release_publication(_SLUG, LATE_ISSUE_NUMBER)

        self.assertEqual(self._scope(), CYCLE_ID)

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
                self.assertEqual(self._scope(), CYCLE_ID)

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

        self.assertEqual(self._scope(), CYCLE_ID)
        state = self.github.read_pinned_state(self.owner)
        self.assertEqual(_late_close_reading._ending_cycle(_TEST_SPEC, LATE_ISSUE_NUMBER, state), CYCLE_ID)

    def test_the_pass_under_the_claim_adopts_it(self) -> None:
        # Once the holder lets go, the pass that takes the claim puts the
        # retired cycle back cancelled on the strength of that scope alone:
        # the thread carries no receipt, and is not walked for one.
        self._retired()
        with held_elsewhere(self.github.repo_id, LATE_ISSUE_NUMBER, retiring=CYCLE_ID):
            self._kept()

        state = self.github.read_pinned_state(self.owner)
        with (
            self._under_the_claim(self.github.repo_id, LATE_ISSUE_NUMBER),
            patch.object(self.github, "comments_after") as walked,
            self.assertLogs(_WORKFLOW_LOG),
        ):
            adopted = _late_close_observation._retired_close_adopted(self.github, _TEST_SPEC, self.owner, state)
            walked.assert_not_called()

        self.assertEqual((adopted.cycle_id, adopted.cancelled), (CYCLE_ID, True))
        self.assertTrue(_late_state.read_late_generation(self.github.read_pinned_state(self.owner)).cancelled)

    def test_a_note_outlives_its_holder_letting_go(self) -> None:
        # The holder lets go while the contender reads, and its release stamp
        # ends the note on the claim -- so the note the refusal found, before
        # either read, is what ties the close to the retired cycle.
        for read in (_RECORD_READ, _ISSUE_READ):
            with self.subTest(released_during=read):
                self.setUp()
                self._retired()
                signed_by_another_poller(self.github.repo_id, LATE_ISSUE_NUMBER, retiring=CYCLE_ID, released=False)
                with patch.object(self.github, read, _HolderDuring(self.github, read)):
                    self._kept()

                self.assertEqual(self._scope(), CYCLE_ID)

    def test_a_note_found_between_the_reads_is_kept(self) -> None:
        # The refusal found no note: the holder noted its retirement before
        # the first record read and let go during the issue read, its release
        # stamp ending the note before the record was read again. The note the
        # first read found is what ties the close to the retired cycle.
        self._retired()
        written = self._written()
        with (
            patch.object(self.github, _RECORD_READ, _HolderDuring(self.github, _RECORD_READ, released=False)),
            patch.object(self.github, _ISSUE_READ, _HolderDuring(self.github, _ISSUE_READ)),
        ):
            self._kept()

        self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
        self.assertEqual(self._scope(), CYCLE_ID)
        self.assertEqual(self._written(), written, _WRITES_NOTHING)

    def test_a_note_seen_past_a_live_record_is_kept(self) -> None:
        # The first record read names the live cycle; the holder has noted its
        # retirement by the time that read answers, retires the cycle behind
        # it, and lets go during the issue read. The note seen after the live
        # read is what ties the close to the cycle the record then dropped.
        said = self._said()
        with (
            patch.object(self.github, _RECORD_READ, _HolderDuring(
                self.github, _RECORD_READ, released=False, retire=self._retired,
            )),
            patch.object(self.github, _ISSUE_READ, _HolderDuring(self.github, _ISSUE_READ)),
        ):
            self._kept()

        self.assertEqual(self._scope(), CYCLE_ID)
        self.assertEqual(self._said(), said, _WRITES_NOTHING)

    def test_a_cycle_the_record_dropped_stays_owed(self) -> None:
        # Noted, retired, and let go all inside the issue read, so no read of
        # the claim ever sees the note: the record named the cycle and then
        # none, and the close is held unresolved rather than dropped.
        said = self._said()
        with (
            patch.object(self.github, _ISSUE_READ, _HolderDuring(self.github, _ISSUE_READ, retire=self._retired)),
            self.assertLogs(_WORKFLOW_LOG),
        ):
            self._kept()

        self.assertEqual(self._observed(_SLUG), frozenset((LATE_ISSUE_NUMBER,)))
        self.assertIsNone(self._scope())
        self.assertEqual(self._said(), said, _WRITES_NOTHING)

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
