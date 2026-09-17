# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The tree a publication has to prove, at every boundary that reads it.

`HEAD` answers half of what "this checkout" is. The other half is what sits
around the commit, and it can change with the head never moving -- a
descendant the timeout cleanup raced, a second process, an operator -- so
every proof taken about the commit passes while the checkout stops being the
thing that was measured. Nothing downstream reads it again: the reviewer
treats loose work as work to publish, the squash rewrites it, and the docs
pass commits over it.

So the tree is proved three times, and proved rather than inferred: the list
form of the status read maps its own failure to "no paths", which is what a
clean tree reports too, and a push may not rest on a probe that never ran.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.fixtures import LABEL_VALIDATING, MEASURED_CANDIDATE_SHA
from tests.workflow.stages.implementing import late_gate_test_support as support

_VALIDATING = (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING)
_CANDIDATE_MOVED = "late_candidate_moved"
_KEY_APPROVED_SHA = "late_approved_sha"
_KEY_PUBLISHED_SHA = "implementing_published_sha"
_DECOMPOSE = "DECOMPOSE"
_DEV_SESSION = "sess-1"
_EVENT_PARK = "park_awaiting_human"

# The three readings a tree can give, in the order a publication asks for
# them: nothing loose, something loose, and a read that never happened.
_CLEAN = _WorktreeStatus(readable=True)
_LOOSE_PATH = "half-written.py"
_DIRTY = _WorktreeStatus(readable=True, paths=(_LOOSE_PATH,))
_UNREADABLE = _WorktreeStatus(readable=False)
# The one reading that is both at once: an index entry git was told to stop
# comparing is a path to refuse on AND a reason the rest cannot be trusted.
_SUPPRESSED = _WorktreeStatus(readable=False, paths=(_LOOSE_PATH,))


class UnprovableTreeTest(support._GateCase, unittest.TestCase):
    """What the disposition does with a tree it could not call clean.

    The seam every committed candidate publishes through, which is where the
    size gate sits -- so a reading that failed here must stop the tick rather
    than measure a candidate nobody can say is the one a push would send.
    """

    def test_an_unreadable_tree_is_not_a_clean_one(self) -> None:
        # `git status` failing establishes nothing, and the list form of that
        # read reports it as no paths -- the same answer a clean tree gives.
        # Read as "nothing to refuse on", it publishes and hands review a
        # checkout nobody proved matched the work.
        mocks = self._run_gate(tree_states=(_UNREADABLE,))

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertNotIn(_VALIDATING, self.github.label_history)
        self._assert_parked_for_the_tree()
        self.assertIn("git status", self.github.posted_comments[-1][1])

    def test_a_suppressed_index_entry_is_named(self) -> None:
        # The reading that is a refusal on both counts. What an operator has
        # to clear is a bit on a named entry, so the path is quoted rather
        # than the whole of it being reported as unreadable.
        mocks = self._run_gate(tree_states=(_SUPPRESSED,))

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(_LOOSE_PATH, self.github.posted_comments[-1][1])

    def test_the_refusal_has_its_own_reason(self) -> None:
        # A tree nothing could read is a repository to look at; dirty files
        # are a list to clear. An operator reading the stream has to be able
        # to tell them apart.
        self._run_gate(tree_states=(_UNREADABLE,))

        self.assertEqual(
            [record["reason"] for record in self._records(_EVENT_PARK)],
            ["unreadable_worktree"],
        )

    def _assert_parked_for_the_tree(self) -> None:
        """Parked awaiting the human, with nothing stale to auto-recover on."""
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertIsNone(pinned[support.PARK_REASON])


class DirtiedBeforeThePushTest(support._GateCase, unittest.TestCase):
    """A tree that stops being clean between the measurement and the push.

    `HEAD` never moves in any of these, so every proof about the commit
    passes: what is refused is the CHECKOUT, which is what the handoff passes
    on and what no stage past it measures again.
    """

    def test_loose_work_after_measuring_is_refused(self) -> None:
        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            tree_states=(_CLEAN, _DIRTY),
        )

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertNotIn(_VALIDATING, self.github.label_history)
        self.assertIn(_LOOSE_PATH, self.github.posted_comments[-1][1])

    def test_the_refusal_names_the_commit_owed(self) -> None:
        # Nothing else on the issue names it by then -- the generation was
        # retired ahead of the effects it licensed -- so without this the park
        # names a SHA in prose and the operator who cleans the tree gets no
        # acknowledgement for it.
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            tree_states=(_CLEAN, _DIRTY),
        )

        pinned = self._pinned()
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def test_an_unreadable_tree_before_the_push(self) -> None:
        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            tree_states=(_CLEAN, _UNREADABLE),
        )

        self._assert_held(mocks)
        self.assertIn("git status", self.github.posted_comments[-1][1])

    def test_the_switch_off_refuses_it_too(self) -> None:
        # `DECOMPOSE=off` keeps a new candidate out of the MEASUREMENT. It
        # says nothing about whether the checkout is publishable, and the
        # push it bypasses into is the same push.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate(tree_states=(_CLEAN, _DIRTY))

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertNotIn(_VALIDATING, self.github.label_history)


class DirtiedAroundThePushTest(support._GateCase, unittest.TestCase):
    """A tree that stops being clean while the push and the PR go out.

    The window the pre-push reading cannot cover: three requests long, with
    the worktree writable for all of them. What went out is right, so the
    publication stands and the HANDOFF is what stops.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            tree_states=(_CLEAN, _CLEAN, _DIRTY),
        )

    def test_the_publication_stands_not_the_handoff(self) -> None:
        self._assert_published(self.mocks)
        self.assertEqual(len(self.github.opened_prs), 1)
        self.assertNotIn(_VALIDATING, self.github.label_history)
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        # Both commits survive the refusal: what the branch carries, so the
        # next tick recognizes a published branch rather than re-deciding it;
        # and what a handoff is still owed, so the quiet republication has
        # something to watch for.
        self.assertEqual(pinned[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)


class CleanedTreeRecoveryTest(support._GateCase, unittest.TestCase):
    """The park a tree answers, on the same terms a moved checkout does.

    Neither is a refusal a human can talk their way out of, and both are
    settled by the checkout itself -- so they share the reason, the quiet
    per-tick question, and the republication that costs no reading and no run.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _CANDIDATE_MOVED,
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            "dev_agent": "codex",
            "dev_session_id": _DEV_SESSION,
        })

    def test_a_cleaned_tree_publishes_itself(self) -> None:
        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            MEASURED_CANDIDATE_SHA,
        )
        self.assertIn(_VALIDATING, self.github.label_history)

    def test_a_tree_still_loose_stays_quiet(self) -> None:
        # The question is asked every tick, which is what lets the checkout
        # coming back be enough on its own -- so an operator who has not
        # cleared it yet must not be told the same thing once a poll, and the
        # publication must not be walked back into the refusal it took.
        mocks = self._run_gate(tree_states=(_DIRTY,))

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self.assertEqual(self.github.posted_comments, [])
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])

    def test_a_tree_nobody_could_read_stays_quiet_too(self) -> None:
        mocks = self._run_gate(tree_states=(_UNREADABLE,))

        self._assert_held(mocks)
        self.assertEqual(self.github.posted_comments, [])


if __name__ == "__main__":
    unittest.main()
