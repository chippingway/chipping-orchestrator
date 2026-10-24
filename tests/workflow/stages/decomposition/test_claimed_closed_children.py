# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parent's writes to its closed children, each under the child's own writer claim.

The finalize of a child an external merge closed writes its label, thread,
and record; the notice that a consumer's snapshot is gone writes its thread.
Another poller on this host may be dispatching either child, so each write
takes that child's claim first. A finalize is decided on the child read again
behind the claim, so a child that poller finalized since the parent's scan is
never finalized twice; a notice is a comment built to land beside this
process's own handler, so only another process's hold keeps it owed.

Both decide on the child's pinned record as the claim reads it, held to
admission: a child whose record admission refuses is said locally and left
exactly as it stands -- not finalized, closed, relabelled, told, or torn down
-- while a supported record, or none at all, is acted on as ever. The snapshot
delete those notices follow is `test_claimed_reclamation`'s.
"""
from __future__ import annotations

import unittest

from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import terminals as _terminals
from orchestrator.workflow.late_split import obligations as _obligations, phases as _late_phases
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
    late_consumer_release as _late_consumer_release,
    parents as _parents,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import _TEST_SPEC, KEY_AWAITING_HUMAN, LABEL_DONE, _agent, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import child_claim_test_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import PARENT_NUMBER, SNAPSHOT_REF, UMBRELLA
from tests.workflow.stages.decomposition.late_test_support import late_generation

# Two consumers cut from one ref, so a pass nothing holds back tells both.
_CONSUMERS = (911, 912)

_FIRST, _SECOND = _CONSUMERS

# What finalizing the merged child leaves in the label history.
_FINALIZED = ((_support.MERGED_CHILD, LABEL_DONE),)

# The teardown of the checkout and branches a finalize runs for the child it ended.
_TEARDOWN = "_cleanup_terminal_branch"

_WARNING = "WARNING"

# A version this build does not admit, as a human's edit could leave it.
_ANOTHER_VERSION = 2

_KEY_SCHEMA_VERSION = "schema_version"


class _MergedChildCase(_PatchedWorkflowMixin):
    """A `blocked` parent whose one child an external merge closed."""

    def setUp(self) -> None:
        github, parent = _support.blocked_on_a_merged_child()
        self.github = github
        self.parent = parent

    def _parked_on_children(self, scan=None) -> tuple:
        """Whether the parent parks on its children, and the scan it asked of.

        The hermetic seams the walk ran against are kept on `_mocks`, so a
        case can read whether the child's checkout was torn down.
        """
        scan = scan or _parents._read_child_labels(self.github, self.parent, [_support.MERGED_CHILD])
        answered = []
        state = self.github.read_pinned_state(self.parent)
        self._mocks = self._run(
            lambda: answered.append(
                _parents._parked_on_children(self.github, _TEST_SPEC, self.parent, state, scan),
            ),
            run_agent=_agent(),
        )
        return answered[0], scan

    def _refused_on_claim(self, number: int) -> None:
        """Leave the merged child's record one admission refuses, as a human's edit would; any other is left."""
        if number == _support.MERGED_CHILD:
            self.github.seed_state(number, raw=True, schema_version=_ANOTHER_VERSION, **_support.MERGED_RECORD)

    def _admitted_on_claim(self, number: int) -> None:
        """Leave the merged child's record the supported one it carried; any other is left."""
        if number == _support.MERGED_CHILD:
            self.github.seed_state(number, **_support.MERGED_RECORD)

    def _supported(self) -> bool:
        """Whether the merged child's record reads as one admission takes right now."""
        return self.github.read_pinned_state(self.github.get_issue(_support.MERGED_CHILD)).supported


class ClaimedMergeFinalizeTest(_MergedChildCase, unittest.TestCase):
    """The finalize, made under the merged child's own claim."""

    def test_a_held_merged_child_waits(self) -> None:
        # Neither finalized nor counted as closed by hand: the parent waits on
        # it rather than parking over it, and the next walk finalizes it.
        with held_elsewhere(self.github.repo_id, _support.MERGED_CHILD), self.assertLogs(_support.WORKFLOW_LOG):
            parked, _ = self._parked_on_children()

        self.assertFalse(parked)
        self.assertEqual(self.github.label_history, [], "the child is not finalized")
        self.assertNotIn("merged_at", self.github.pinned_data(_support.MERGED_CHILD))
        self.assertEqual(self.github.posted_comments, [], "nor the parent parked over it")

        parked, scan = self._parked_on_children()

        self.assertFalse(parked)
        self.assertEqual(self.github.label_history, list(_FINALIZED))
        self.assertEqual(scan.labels[_support.MERGED_CHILD], LABEL_DONE)

    def test_a_finalize_since_the_scan_stays(self) -> None:
        # The claim is granted, because the other poller let go -- but it
        # finalized the child after the parent's scan, so a finalize decided
        # on that scan would merge the child a second time.
        scan = _parents._read_child_labels(self.github, self.parent, [_support.MERGED_CHILD])
        with held_elsewhere(self.github.repo_id, _support.MERGED_CHILD):
            self._run(self._finalized_elsewhere, run_agent=_agent())

        parked, _ = self._parked_on_children(scan)

        merged = [event for event in self.github.recorded_events if event["event"] == "pr_merged"]
        self.assertEqual(len(merged), 1, "the child is merged once, by the poller that finalized it")
        self.assertEqual(self.github.label_history, list(_FINALIZED))
        self.assertEqual(scan.labels[_support.MERGED_CHILD], LABEL_DONE, "the parent reads it done")
        self.assertFalse(parked, "and does not park over it")

    def _finalized_elsewhere(self) -> None:
        """The other poller's own finalize of the merged child."""
        child = self.github.get_issue(_support.MERGED_CHILD)
        _terminals._finalize_if_pr_merged(self.github, _TEST_SPEC, child, self.github.read_pinned_state(child))


class AdmittedMergeFinalizeTest(_MergedChildCase, unittest.TestCase):
    """The finalize, decided on the merged child's record as its claim reads it."""

    def test_a_refused_merged_child_is_left_alone(self) -> None:
        # The finalize decides on the pull request the child's record names,
        # so a record admission refuses is one nothing is decided on: the
        # child keeps its record, thread, labels, close, checkout, and
        # branches, the parent neither counts it nor parks over it, and the
        # refusal is said only locally.
        for shape, version in _support.UNADMITTED.items():
            with self.subTest(child=shape):
                self.setUp()
                self.github.seed_state(_support.MERGED_CHILD, raw=True, **version, **_support.MERGED_RECORD)
                before = _support.standing(self.github, _support.MERGED_CHILD)

                with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
                    parked, _ = self._parked_on_children()
                    self.assertTrue(_support.said_refused(logged.output, _support.MERGED_CHILD))

                self.assertEqual(_support.standing(self.github, _support.MERGED_CHILD), before)
                self.assertEqual(self.github.label_history, [], "the child is not finalized")
                self.assertFalse(self._mocks[_TEARDOWN].called, "the child's checkout and branches stay")
                self.assertEqual(self.github.posted_comments, [], "nothing is said on either issue")
                self.assertIsNone(self.github.pinned_data(_support.MERGED_PARENT).get(KEY_AWAITING_HUMAN))
                self.assertFalse(parked)

    def test_a_refusal_at_its_claim_stays(self) -> None:
        # The walk begins over the supported record the merged child was
        # seeded with, and a human's edit landing as its claim is granted
        # leaves that record refused. The finalize decides on the reading
        # behind the claim, never on one taken before it: the child keeps the
        # record the edit left, its thread, labels, close, checkout, and
        # branches, and the parent neither counts it nor parks over it.
        self.assertTrue(self._supported(), "the walk begins over a supported record")
        before = _support.standing(self.github, _support.MERGED_CHILD)
        edited = {**before[0], _KEY_SCHEMA_VERSION: _ANOTHER_VERSION}

        with (
            _support.EditedOnClaim(self._refused_on_claim).installed(),
            self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged,
        ):
            parked, _ = self._parked_on_children()
            self.assertTrue(_support.said_refused(logged.output, _support.MERGED_CHILD))

        after = _support.standing(self.github, _support.MERGED_CHILD)
        self.assertEqual(after, (edited, *before[1:]), "the child keeps what the edit left it")
        self.assertEqual(self.github.label_history, [], "the child is not finalized")
        self.assertFalse(self._mocks[_TEARDOWN].called, "the child's checkout and branches stay")
        self.assertEqual(self.github.posted_comments, [], "nothing is said on either issue")
        self.assertFalse(parked)

    def test_an_admission_at_its_claim_finalizes(self) -> None:
        # The other way round: the record is refused when the walk begins,
        # and the edit landing as the claim is granted puts the supported one
        # back, so the finalize goes ahead on that reading.
        self._refused_on_claim(_support.MERGED_CHILD)
        self.assertFalse(self._supported(), "the walk begins over a refused record")

        with _support.EditedOnClaim(self._admitted_on_claim).installed():
            parked, _ = self._parked_on_children()

        self.assertEqual(self.github.label_history, list(_FINALIZED))
        self.assertTrue(self._mocks[_TEARDOWN].called, "the child's checkout and branches come down")
        self.assertFalse(parked)

    def test_a_fresh_closed_child_is_counted(self) -> None:
        # A child with no pinned record at all is admitted, as a fresh one
        # is, and refused nothing: no pull request is named for a merge to
        # explain, so it counts as closed by hand and parks the parent as ever.
        github, parent = _support.blocked_on_a_merged_child(recorded=False)
        self.github = github
        self.parent = parent

        with self.assertNoLogs(_support.WORKFLOW_LOG, level=_WARNING):
            parked, _ = self._parked_on_children()

        self.assertTrue(parked)
        self.assertTrue(self.github.pinned_data(_support.MERGED_PARENT).get(KEY_AWAITING_HUMAN))
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(self.github.pinned_data(_support.MERGED_CHILD), {})


class _ConsumerNoticeCase:
    """A reclaimed snapshot's two consumers, closed, neither carrying a pinned record."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.owner = make_issue(PARENT_NUMBER, label=UMBRELLA)
        self.github.add_issue(self.owner)
        for number in _CONSUMERS:
            self.github.add_issue(make_issue(number, closed=True))

    def _released(self) -> bool:
        """Deliver the ref's notices, and say whether every consumer was told."""
        scan = _parents._read_child_labels(self.github, self.owner, list(_CONSUMERS))
        walk = _late_cleanup_state._Pass(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.owner,
            state=self.github.read_pinned_state(self.owner),
            scan=scan,
        )
        generation = late_generation(
            threshold=None,
            additions=None,
            phase=_late_phases.LatePhase.CLEANING_UP,
            obligations=_obligations.LateObligations().with_consumers(_CONSUMERS),
        )
        _, told = _late_consumer_release._release_consumers(walk, generation, SNAPSHOT_REF, scan)
        return told

    def _told(self) -> list[int]:
        """The consumers a notice was posted on, in order."""
        return [number for number, _ in self.github.posted_comments]

    def _refused_on_claim(self, number: int) -> None:
        """Leave the second consumer's record one admission refuses, as a human's edit would; any other is left."""
        if number == _SECOND:
            self.github.seed_state(number, raw=True, schema_version=_ANOTHER_VERSION, parent_number=PARENT_NUMBER)

    def _admitted_on_claim(self, number: int) -> None:
        """Leave the second consumer's record a supported one; any other is left."""
        if number == _SECOND:
            self.github.seed_state(number, parent_number=PARENT_NUMBER)

    def _supported(self) -> bool:
        """Whether the second consumer's record reads as one admission takes right now."""
        return self.github.read_pinned_state(self.github.get_issue(_SECOND)).supported


class ClaimedConsumerNoticeTest(_ConsumerNoticeCase, unittest.TestCase):
    """A reclaimed snapshot's notice, posted on each consumer under its own claim."""

    def test_a_held_consumer_keeps_it_owed(self) -> None:
        with held_elsewhere(self.github.repo_id, _SECOND), self.assertLogs(_support.WORKFLOW_LOG):
            told = self._released()

        self.assertFalse(told, "the obligation stays outstanding")
        self.assertEqual(self._told(), [_FIRST])

        self.assertTrue(self._released())
        self.assertEqual(self._told(), list(_CONSUMERS), "each consumer is told once")

    def test_a_notice_lands_beside_our_writer(self) -> None:
        # The notice is a comment built to land beside the consumer's own
        # handler, so this process holding the consumer is no reason to wait.
        with _writer_claims.issue_writer(self.github.repo_id, _FIRST):
            told = self._released()

        self.assertTrue(told)
        self.assertEqual(self._told(), list(_CONSUMERS))


class AdmittedConsumerNoticeTest(_ConsumerNoticeCase, unittest.TestCase):
    """A reclaimed snapshot's notice, decided on each consumer's record as its claim reads it."""

    def test_a_refused_consumer_is_told_nothing(self) -> None:
        # The scan read no pinned record, so the one a notice decides on is
        # read under the consumer's claim. One admission refuses keeps its
        # thread, record, labels, and close exactly as they were and the
        # obligation owed, said only locally, while the fresh consumer beside
        # it -- no pinned record at all -- is told; a later pass over a record
        # admission takes tells it once.
        for shape, version in _support.UNADMITTED.items():
            with self.subTest(second=shape):
                self.setUp()
                self.github.seed_state(_SECOND, raw=True, **version)
                before = _support.standing(self.github, _SECOND)

                with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
                    self.assertFalse(self._released(), "the obligation stays outstanding")
                    self.assertTrue(_support.said_refused(logged.output, _SECOND))

                self.assertEqual(self._told(), [_FIRST])
                self.assertEqual(_support.standing(self.github, _SECOND), before)
                self._admitted_on_claim(_SECOND)
                self.assertTrue(self._released())
                self.assertEqual(self._told(), list(_CONSUMERS), "each consumer is told once")

    def test_a_refusal_at_its_claim_tells_nothing(self) -> None:
        # The second consumer carries a supported record when the pass
        # begins, and a human's edit landing as its claim is granted leaves it
        # refused. The notice decides on the reading behind the claim: that
        # consumer is told nothing and keeps the record the edit left, its
        # thread, labels, and close, and the obligation stays owed, while the
        # first is told.
        self._admitted_on_claim(_SECOND)
        self.assertTrue(self._supported(), "the pass begins over a supported record")
        before = _support.standing(self.github, _SECOND)
        edited = {**before[0], _KEY_SCHEMA_VERSION: _ANOTHER_VERSION}

        with (
            _support.EditedOnClaim(self._refused_on_claim).installed(),
            self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged,
        ):
            self.assertFalse(self._released(), "the obligation stays outstanding")
            self.assertTrue(_support.said_refused(logged.output, _SECOND))

        after = _support.standing(self.github, _SECOND)
        self.assertEqual(after, (edited, *before[1:]), "the consumer keeps what the edit left it")
        self.assertEqual(self._told(), [_FIRST])

    def test_an_admission_at_its_claim_tells_it(self) -> None:
        # The other way round: the record is refused when the pass begins,
        # and the edit landing as the claim is granted puts a supported one in
        # its place, so the consumer is told on that reading.
        self._refused_on_claim(_SECOND)
        self.assertFalse(self._supported(), "the pass begins over a refused record")

        with _support.EditedOnClaim(self._admitted_on_claim).installed():
            self.assertTrue(self._released())

        self.assertEqual(self._told(), list(_CONSUMERS))


if __name__ == "__main__":
    unittest.main()
