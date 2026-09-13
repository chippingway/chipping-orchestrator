# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close that reaches a measured candidate before it is published.

The last thing the size gate does with a candidate it approved is retire the
record and hand the issue on -- a branch pushed, a pull request opened, and the
label moved to review. None of that may happen on an issue a human has closed,
and the poll that saw the close cannot always say so: the scheduler admits no
second worker for an issue one is already running, so the reading is latched
rather than handed over.

So the retirement is where the barrier goes, and it is asked twice. Once
before the write, for a close already latched. Once as the write CLOSES, for
the close that arrived inside it -- the window where the record has stopped
naming a cycle and the ending has nothing to be entered from, which is exactly
the interval a poll would otherwise drop its observation in.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import observations as _observations
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    _authorized_exemption,
)
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.implementing import late_gate_test_support as support

_WORKFLOW_LOG = "orchestrator.workflow"

_REPO_SLUG = _TEST_SPEC.slug

_VALIDATING = (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING)

# The field that says a cycle is still there to end. The retirement is the one
# pinned write a late tick makes that does not carry it.
_KEY_CYCLE_ID = "late_cycle_id"

_KEY_CANCELLED = "late_cancelled"

_KEY_CANCELLED_AT = "late_cancelled_at"

# The commit an approval records for the push it licenses. A cancelled cycle
# licenses none.
_KEY_APPROVED_SHA = "late_approved_sha"

# What the reinstatement says, so a case can tell the barrier that caught a
# close from the one that was already holding it.
_PUT_BACK = "putting it back"


class _CloseCase(ObservedCloseCase, support._GateCase):
    """A gate run whose issue a poll saw closed, and the state it leaves."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def _assert_cancelled(self) -> None:
        """The cycle ended, and durably: the ending is entered from this."""
        pinned = self._pinned()
        self.assertTrue(pinned[_KEY_CANCELLED])
        self.assertTrue(pinned[_KEY_CANCELLED_AT])
        self.assertEqual(pinned[_KEY_CYCLE_ID], 1)

    def _assert_nothing_shipped(self, mocks) -> None:
        """No branch, no pull request, and no handoff to review."""
        self._assert_held(mocks)
        self.assertNotIn(_VALIDATING, self.github.label_history)


class LatchedCloseHoldsThePublicationTest(_CloseCase, unittest.TestCase):
    """A close latched before the tick stops the candidate publishing."""

    def test_a_measured_candidate_publishes_nothing(self) -> None:
        # The issue itself reads OPEN throughout -- a human closed it and
        # reopened it inside this tick -- so nothing the gate could ask GitHub
        # would show the close. The latch is the only thing that knows, and
        # what it stops is a pull request nobody is going to review.
        self._latch_close(_REPO_SLUG, support.GATE_ISSUE_NUMBER)

        with self.assertLogs(_WORKFLOW_LOG):
            mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_nothing_shipped(mocks)
        self._assert_cancelled()

    def test_an_exempt_commit_stops_for_it_too(self) -> None:
        # The exemption is the other road into the retirement -- the commit an
        # adjudication accepted publishes without being measured again -- so
        # the barrier has to be on the retirement rather than beside the
        # count, or a `single` verdict would ship on a closed issue.
        self._seed(**{
            **support.recorded_generation(),
            **_authorized_exemption(),
        })
        self._latch_close(_REPO_SLUG, support.GATE_ISSUE_NUMBER)

        with self.assertLogs(_WORKFLOW_LOG):
            mocks = self._run_gate()

        self._assert_nothing_shipped(mocks)
        self._assert_cancelled()

    def test_a_cancelled_cycle_owes_no_publication(self) -> None:
        # The approval is recorded ahead of the barrier that catches the
        # close, so the cancellation has to take it back: a commit nobody is
        # going to push would freeze the branch out of the base refresh for
        # as long as the issue lives and park every later tick asking for a
        # checkout back for it.
        self._latch_close(_REPO_SLUG, support.GATE_ISSUE_NUMBER)

        with self.assertLogs(_WORKFLOW_LOG):
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertIsNone(self._pinned()[_KEY_APPROVED_SHA])

    def test_a_settled_latch_lets_it_through(self) -> None:
        # The other side of the barrier, so it is not merely "never publish":
        # a latch some pass has taken is gone, and the gate publishes exactly
        # as it always did.
        self._latch_close(_REPO_SLUG, support.GATE_ISSUE_NUMBER)
        self._settle_latches(_REPO_SLUG)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_published(mocks)
        self.assertIn(_VALIDATING, self.github.label_history)


class CloseInsideTheRetirementTest(_CloseCase, unittest.TestCase):
    """The window the retirement write itself opens, and what closes it.

    Retiring a cycle takes its identity OFF the record, and everything that
    decides what a close is worth reads that identity. A poll landing in that
    window finds an issue with nothing to end, drops the observation, and the
    worker -- having asked its barrier before the write -- goes on to push a
    branch, open a pull request, and hand a closed issue to review.
    """

    def test_the_publication_is_stopped(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG) as logged, self._closing():
            mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)
            reported = list(logged.output)

        self.assertTrue(
            any(_PUT_BACK in line for line in reported),
            "the close was caught before the window, not inside it",
        )
        self._assert_nothing_shipped(mocks)

    def test_the_cycle_is_put_back_to_be_ended(self) -> None:
        # The retirement had already landed when the reading arrived, so the
        # record says nothing is running -- and a cancellation over that is a
        # mark with no cycle under it, which the cleanup that settles a
        # cancelled cycle cannot act on. The generation goes back exactly as
        # it was, which costs nothing: the retirement runs ahead of every
        # effect it licenses, so there is nothing published to take back.
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_cancelled()
        self.assertEqual(
            self._pinned()[support.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )

    def _closing(self):
        """Latch a close inside the write that drops this issue's cycle."""
        return _ClosingRetirement(self.github).answering()


class _ClosingRetirement:
    """A poll that latches its close as the retirement write is landing.

    Keyed off a cycle this run has already recorded and no longer does, rather
    than off any write that carries no cycle: the gate writes pinned state
    before it mints a generation at all, and latching there would be the
    barrier ahead of the window rather than the window itself.

    The latch goes on the far side of the write, which is the last instant
    inside the retirement: the record has landed without the cycle, and the
    only thing that could still notice is the worker asking what its own
    window saw.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._writing = github.write_pinned_state
        self._recorded = False

    def __call__(self, issue, state, **written):
        named = state.data.get(_KEY_CYCLE_ID) is not None
        retiring = self._recorded and not named
        self._recorded = self._recorded or named
        answered = self._writing(issue, state, **written)
        if retiring:
            _observations.observe_close(
                _REPO_SLUG, support.GATE_ISSUE_NUMBER,
            )
        return answered

    def answering(self):
        """Put this in front of every pinned write the run makes."""
        return patch.object(
            self._github, "write_pinned_state", side_effect=self,
        )


if __name__ == "__main__":
    unittest.main()
