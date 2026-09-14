# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one publication is bound to, from the push to the checkout it hands on.

Three requests stand between the decision and the handoff -- the push, the
pull-request lookup, and the open -- and the worktree is writable while every
one of them runs. So the commit is decided once, before any of them, and
everything past that line is named against it: the push carries it, the record
the handoff leaves says it, and the proof taken once the pull request is open
asks the checkout for it. A checkout that moved in between is a checkout no
stage past the handoff may read.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from tests.workflow.fixtures import (
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)
from tests.workflow.stages.implementing import late_gate_test_support as support

_DECOMPOSE = "DECOMPOSE"
_CANDIDATE_MOVED = "late_candidate_moved"
_KEY_APPROVED_SHA = "late_approved_sha"
_KEY_PUBLISHED_SHA = "implementing_published_sha"
_VALIDATING = (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING)
# What a descendant the timeout cleanup raced leaves the checkout on.
_DESCENDANT = "e" * SHA_LENGTH
# Three readings of one checkout: the gate's, the proof taken before the push,
# and the proof taken once the pull request is open. Only the last has moved,
# which is the window the pre-push proof cannot cover.
_MOVES_AFTER_THE_PUSH = (
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(sha=_DESCENDANT),
)

# The same move one reading earlier, for the road where the gate proves
# nothing and the checkout itself names what is about to be pushed: the intent
# is read before the push, and the proof past the pull request finds the
# descendant.
_MOVES_AFTER_A_NAMELESS_PUSH = (
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(sha=_DESCENDANT),
)

# A checkout whose head establishes nothing at all -- the reading the
# switch-off road has nothing else to fall back on.
_UNREADABLE_HEAD = FrozenCommit(
    failure=MeasurementFailure.CANDIDATE_UNREADABLE,
)


class PublicationIntentTest(support._GateCase, unittest.TestCase):
    """The commit a publication decides on, and when it becomes durable."""

    def test_a_refused_push_keeps_the_intent(self) -> None:
        # The receipt window: between the decision and the handoff the branch
        # goes to the remote and a pull request opens over it, and a tick that
        # died in there would leave an issue whose branch is published and
        # whose record says nothing was owed. Read where the push itself
        # fails, since a record written after the push cannot survive one that
        # never returned.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate(push_branch=False)

        self._assert_unmeasured(mocks)
        self.assertEqual(self.github.opened_prs, [])
        self.assertEqual(
            self._pinned()[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )

    def test_the_receipt_names_what_went_out(self) -> None:
        # The intent is decided once and the receipt is that same commit, not
        # a second reading of a checkout that has moved since: recorded from a
        # re-read, the issue would claim to have published a commit no push
        # ever carried.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate(
                candidate_commit=_MOVES_AFTER_A_NAMELESS_PUSH,
            )

        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(
            self._pinned()[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA,
        )


class UnprovableHeadTest(support._GateCase, unittest.TestCase):
    """A checkout that cannot say what it is on publishes nothing.

    The road the switch opens: with `DECOMPOSE=off` the gate proves no commit
    for a new candidate, so the checkout has to name what is about to be
    pushed. When it cannot -- a head that will not resolve, or one that
    resolves to an object this host cannot peel -- there is no name to give
    the push, the receipt, or either proof taken around them, and a push that
    names nothing sends whatever the branch has become by the time git runs
    it.
    """

    def setUp(self) -> None:
        super().setUp()
        with patch.object(config, _DECOMPOSE, False):
            self.mocks = self._run_gate(candidate_commit=_UNREADABLE_HEAD)

    def test_nothing_is_published(self) -> None:
        self._assert_unmeasured(self.mocks)
        self._assert_held(self.mocks)

    def test_the_handoff_never_happens(self) -> None:
        # The label is what hands the checkout to review, and review takes no
        # reading of its own -- so a branch published under no commit reaches
        # a squash and a merge with nothing having named it.
        self.assertNotIn(_VALIDATING, self.github.label_history)

    def test_it_parks_rather_than_falling_back(self) -> None:
        # Falling back to the branch as git resolves it is the whole defect:
        # nothing refuses it afterwards, because every later proof compares
        # against a commit that was never recorded.
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertIsNone(pinned.get(_KEY_PUBLISHED_SHA))

    def test_the_refusal_names_what_failed(self) -> None:
        # What an operator has to clear is a repository rather than a commit,
        # so the park says which step could not be completed.
        self.assertIn(
            MeasurementFailure.CANDIDATE_UNREADABLE,
            self.github.posted_comments[-1][1],
        )


class MovedAfterThePushTest(support._GateCase, unittest.TestCase):
    """A checkout that left the published commit is not handed to review.

    What went out is exactly the commit that was named, so the branch and its
    pull request are right. What is wrong is the CHECKOUT, and the checkout is
    what every stage past the handoff works from: the reviewer reads a head
    ahead of the pushed branch as unpushed work, the squash rewrites what is
    on it, and the docs pass commits on top -- so a worktree left on a
    descendant nobody measured reaches a merge one force-push later.
    """

    def test_the_handoff_stops(self) -> None:
        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVES_AFTER_THE_PUSH,
        )

        self._assert_published(mocks)
        self.assertNotIn(_VALIDATING, self.github.label_history)
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)

    def test_the_park_names_both_commits(self) -> None:
        # The one the checkout has to go back to, and the one it is on: the
        # operator answering this is choosing between them.
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVES_AFTER_THE_PUSH,
        )

        notice = self.github.posted_comments[-1][1]
        self.assertIn(MEASURED_CANDIDATE_SHA, notice)
        self.assertIn(_DESCENDANT, notice)

    def test_the_publication_is_not_taken_back(self) -> None:
        # The commit is on the remote and its pull request carries it, so the
        # next tick has to recognize it rather than re-decide it -- and the
        # park records what the checkout must come back to, which is what
        # republishes it with nothing re-run.
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVES_AFTER_THE_PUSH,
        )

        pinned = self._pinned()
        self.assertEqual(pinned[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def test_a_restored_checkout_finishes_the_handoff(self) -> None:
        # And the way out is the checkout coming back: no reply, no guidance,
        # and no second developer over work already published.
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVES_AFTER_THE_PUSH,
        )

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self.assertIn(_VALIDATING, self.github.label_history)


if __name__ == "__main__":
    unittest.main()
