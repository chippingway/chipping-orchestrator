# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The durable half of an observation, and the threads that race it.

A poll that can hand a close to no worker writes the reading down as a marked
comment, because the latch beside it is memory. Asking whether the thread
already carries one and getting one onto it are two operations, and both of
the other parties are inside that gap: the worker running the pass that
settles the reading, and a second poll making the same attempt.

So the attempt is claimed, and the claim carries the GENERATION of the reading
it was taken for. What these cases pin is what each interleaving leaves for
the observation AFTER it -- a memo belongs to one reading, and a close nobody
wrote down is one a restart takes away entirely.
"""
from __future__ import annotations

import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator.workflow.engine import (
    observation_receipts as _observation_receipts,
    observations as _observations,
    retiring_cycles as _retiring_cycles,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_cancellation as _late_cancellation,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase, receipt_for
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
    late_generation,
    seed_late_issue,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_TEST_SLUG = _TEST_SPEC.slug

# The client method a receipt is posted through, held so a case can decide
# what else happens while one is in flight.
_COMMENT = "comment"

# The cycle an operator authorizes by taking `rejected` off, which is the
# reading the memo of an ended one may not suppress.
_NEXT_CYCLE = CYCLE_ID + 1

# Long enough that a machine under load still hands the parked thread back,
# short enough that a case which deadlocks fails rather than hangs.
_TIMEOUT = 10


class _HeldPost:
    """A receipt post the second poll is let into the gap of.

    The first caller is parked between the claim and the comment and stays
    there until the case releases it; anything arriving behind it runs
    straight through, which is exactly the interleaving that would have two
    polls walk the same receipt-less thread and post one apiece.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._posting = github.comment
        self.entered = threading.Event()
        self.released = threading.Event()
        self._holding: list[str] = []

    def __call__(self, issue, body: str):
        if not self._holding:
            self._holding.append(body)
            self.entered.set()
            self.released.wait(_TIMEOUT)
        return self._posting(issue, body)

    def raced(self, poll) -> bool:
        """Run one more poll inside the gap the first one is parked in.

        Answers whether the park was actually reached, so a case does not
        read "one receipt" off a race that never happened.
        """
        parked = threading.Thread(target=poll)
        parked.start()
        reached = self.entered.wait(_TIMEOUT)
        poll()
        self.released.set()
        parked.join(_TIMEOUT)
        return reached


class _SettlingPost:
    """The worker's pass finishing inside the post the poll is making.

    A cleanup that RAN drops the latch and the memo together, so a receipt
    landing on either side of that call belongs to a reading nobody holds any
    more -- and a memo written from it would suppress the next one.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._posting = github.comment

    def __call__(self, issue, body: str):
        posted = self._posting(issue, body)
        _observations.settle_close(_TEST_SLUG, LATE_ISSUE_NUMBER)
        return posted


class _ReceiptCase(ObservedCloseCase):
    """One owner carrying a live cycle, and the poll that observes it."""

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        seed_late_issue(self.github, late_generation())
        self._latch_close(_TEST_SLUG, LATE_ISSUE_NUMBER)

    def _recorded(self) -> None:
        """One poll's attempt at the durable half of its observation."""
        _late_cancellation._record_observed_close(
            self.github, _TEST_SPEC, LATE_ISSUE_NUMBER,
        )

    def _receipts(self, cycle_id: int) -> list[str]:
        """Every receipt on the thread for one cycle's observed close."""
        marker = receipt_for(LATE_ISSUE_NUMBER, cycle_id)
        return [
            body
            for number, body in self.github.posted_comments
            if number == LATE_ISSUE_NUMBER and marker in body
        ]

    def _restarted(self, cycle_id: int) -> None:
        """The fresh cycle an operator authorizes by taking `rejected` off."""
        issue = self.github.get_issue(LATE_ISSUE_NUMBER)
        state = self.github.read_pinned_state(issue)
        _late_state.write_late_generation(state, replace(
            _late_state.read_late_generation(state), cycle_id=cycle_id,
        ))
        self.github.seed_state(LATE_ISSUE_NUMBER, **state.data)
        self._latch_close(_TEST_SLUG, LATE_ISSUE_NUMBER)


class SettledMidPostTest(_ReceiptCase, unittest.TestCase):
    """A cleanup that finishes while the poll is still writing the receipt.

    The memo says one READING has its durable half, and the settlement that
    lands mid-post is what ends that reading. Recording it afterwards would
    hand the next close a suppression it never earned.
    """

    def test_the_next_reading_writes_its_own(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._settling():
            self._recorded()

        self._restarted(_NEXT_CYCLE)
        with self.assertLogs(_WORKFLOW_LOG):
            self._recorded()

        self.assertEqual(len(self._receipts(CYCLE_ID)), 1)
        self.assertEqual(len(self._receipts(_NEXT_CYCLE)), 1)

    def test_a_post_nothing_settled_bounds_the_next(self) -> None:
        # The other side of the same memo, and the reason it exists: a
        # reading whose receipt is durable is one no later poll writes again.
        with self.assertLogs(_WORKFLOW_LOG):
            self._recorded()
        self._recorded()

        self.assertEqual(len(self._receipts(CYCLE_ID)), 1)

    def _settling(self):
        """Settle the observation inside the post that records it."""
        return patch.object(
            self.github, _COMMENT, _SettlingPost(self.github),
        )


class TwoPollsInThePostTest(_ReceiptCase, unittest.TestCase):
    """The check and the post are two operations, and both polls are in them.

    A worker's failed pass and the following tick's enumeration both owe this
    observation its receipt, so the thread either poll walks carries none yet
    -- and the right to attempt the post is what makes it one post.
    """

    def test_only_one_receipt_lands(self) -> None:
        held = _HeldPost(self.github)
        with self.assertLogs(_WORKFLOW_LOG), patch.object(
            self.github, _COMMENT, held,
        ):
            raced = held.raced(self._recorded)

        self.assertTrue(raced)
        self.assertEqual(len(self._receipts(CYCLE_ID)), 1)


class RetirementHandoffTest(ObservedCloseCase, unittest.TestCase):
    """What the retirement window observed is decided as it CLOSES.

    A barrier the worker takes before the exit leaves an interval -- however
    short -- in which a poll can still latch a close and post a receipt
    against the cycle the window is advertising, and the worker would pass on
    having seen neither. Deciding it at the exit leaves no such interval.

    Nothing here needs a remote: what is under test is the handoff itself.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_a_close_before_the_exit_is_reported(self) -> None:
        window = _retiring_cycles.retiring(
            _TEST_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID,
        )

        with window.held():
            self._latch_close(_TEST_SLUG, LATE_ISSUE_NUMBER)

        self.assertTrue(window.observed)

    def test_a_close_latched_after_it_is_not(self) -> None:
        # The other side of the same instant: past the exit the record has no
        # cycle and no window, so the reading is one the poll drops rather
        # than one this worker owes anything.
        window = _retiring_cycles.retiring(
            _TEST_SLUG, LATE_ISSUE_NUMBER, CYCLE_ID,
        )

        with window.held():
            self.assertIsNotNone(self._advertised())
        self._latch_close(_TEST_SLUG, LATE_ISSUE_NUMBER)

        self.assertFalse(window.observed)
        self.assertIsNone(self._advertised())

    def test_a_window_over_no_cycle_says_nothing(self) -> None:
        # An umbrella the initial decomposer made retires nothing, and
        # advertising an identity that is not there would have a poll keep a
        # reading against a cycle nothing could correlate it to.
        window = _retiring_cycles.retiring(_TEST_SLUG, LATE_ISSUE_NUMBER, 0)

        with window.held():
            self._latch_close(_TEST_SLUG, LATE_ISSUE_NUMBER)
            self.assertIsNone(self._advertised())

        self.assertFalse(window.observed)

    def _advertised(self):
        """The cycle a retirement is advertising on this owner right now."""
        return _retiring_cycles.cycle_being_retired(
            _TEST_SLUG, LATE_ISSUE_NUMBER,
        )


class ReopenedScanClaimTest(_ReceiptCase, unittest.TestCase):
    """A receipt that lands after the one thread walk this process owed.

    The walk is claimed once per owner per process because what it recovers
    is an observation a DEAD process was holding -- but a claim taken when
    there was nothing to find proved nothing about a receipt posted since,
    and every later pass would read straight past it.
    """

    def test_a_landed_receipt_owes_the_walk_again(self) -> None:
        self._already_walked()

        with self.assertLogs(_WORKFLOW_LOG):
            self._recorded()

        with _observation_receipts.scanning_receipt(
            _TEST_SLUG, LATE_ISSUE_NUMBER,
        ) as claimed:
            self.assertTrue(claimed)

    def test_a_walk_nothing_landed_on_stays_claimed(self) -> None:
        # The bound that keeps it once: a thread this process walked and
        # nothing has been added to is not walked again every tick.
        self._already_walked()

        with _observation_receipts.scanning_receipt(
            _TEST_SLUG, LATE_ISSUE_NUMBER,
        ) as claimed:
            self.assertFalse(claimed)

    def _already_walked(self) -> None:
        """Take the one walk this process owes, finding nothing on it."""
        with _observation_receipts.scanning_receipt(
            _TEST_SLUG, LATE_ISSUE_NUMBER,
        ) as claimed:
            self.assertTrue(claimed)


if __name__ == "__main__":
    unittest.main()
