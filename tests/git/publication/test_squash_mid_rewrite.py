# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a HELD squash leaves on the branch, and who the commit belongs to.

The entry is asked before anything destructive happens precisely so a doomed
publication costs no rewrite -- but the reset and the commit run behind that
answer, and a human closing the pull request or somebody pushing to it in that
window is visible only to the gate's own second reading.

What the gate does there is REFUSE, which is not what it does to an oversized
candidate. Nothing is measured, nothing is pushed, and nothing owns the
squashed commit: left on the branch it is the one commit a retry finds, and a
one-commit branch takes the nothing-to-squash road and reports success without
measuring or publishing anything -- so reviewer-approved work reaches the
merge button neither counted nor on the remote. So the branch goes back.

Three holds do NOT go back, and each has a different owner for the commit: a
push that LANDED and only held the handoff, an ADJUDICATION the record now
names it under, and a checkout something committed over. The routed and
moved-checkout halves are pinned down in `test_squash_gate.py` beside this;
what is here is the refusal it has to be told apart from, and the landed push
whose receipt is the only thing saying the remote already carries the squash.
A branch goes back only from a checkout proven the issue's own: one switched
onto the flat branch at the squash in the same window is refused instead.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.measurement import additions as _additions
from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    MeasurementFailure,
)
from orchestrator.git.publication import rewrite as _rewrite
from orchestrator.git.worktrees import evidence as _evidence, naming as _naming, paths as _worktree_paths
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.stages.implementing import (
    late_reconcile as _reconcile,
)
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_gate_support import (
    MOVED_HEAD,
    SQUASH_LABEL,
    SQUASH_PR_NUMBER,
    TRACKED_EDIT,
    TRACKED_FILE,
    PublicationSeed,
    _squash_gate,
)

CLOSED = "closed"
OPEN = "open"

# What the fixture's topic branch adds over the base: one line per commit,
# three commits, collapsed by the squash into one.
APPROVED_COMMITS = 3
UNDER_THE_CEILING = APPROVED_COMMITS + 1
MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The receipt a landed push leaves, which is what says the remote is standing
# on the squash whatever the handoff then did with it.
KEY_RECEIPT_SHA = "implementing_published_sha"

_COUNT_HELPER = "_count_added_lines"
_WORKTREE_HELPER = "_worktree_path"

# The flat spelling of the squashed issue's branch, which no live work stands on.
_FLAT_BRANCH = f"orchestrator/issue-{squash_support.SQUASH_ISSUE_NUMBER}"

# The commit a frozen pair names, and the keyword a gated push names its own.
KEY_CANDIDATE_SHA = "late_candidate_sha"
REVISION = "revision"


class _MidRewriteSquashMixin:
    """The gate every case here runs under, and the squash it drives."""

    def _gate_subject(self):
        """The gate this squash runs under, kept so a case reads it back."""
        return _squash_gate(self, PublicationSeed())

    def _squashes(self, squashed, **run_options):
        """One squash under a case's own gate, at a ceiling it passes."""
        return self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
            **run_options,
        )


class SquashRefusedMidRewriteRealGitTest(
    _MidRewriteSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A publication that stops being publishable while the rewrite runs."""

    def test_a_settled_publication_is_put_back(self) -> None:
        squashed = self._gate_subject()

        squash_run = self._interrupted(squashed, state=CLOSED)

        self.assertTrue(squash_run.held)
        self.assertFalse(squash_run.success)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(len(self._commits_on_branch()), APPROVED_COMMITS)

    def test_a_moved_publication_is_put_back(self) -> None:
        # The same window one field over, and neither reading substitutes for
        # the other: a lease cannot catch a close, and a close is not what a
        # push leaves behind.
        squashed = self._gate_subject()

        squash_run = self._interrupted(squashed, head=MOVED_HEAD)

        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(len(self._commits_on_branch()), APPROVED_COMMITS)

    def test_the_retry_squashes_and_publishes_it(self) -> None:
        # What the restore buys, and the whole point of it: the retry has the
        # approved commits to squash again, so the candidate is measured
        # against the base and pushed rather than reported as a success
        # nobody counted and nothing published.
        squashed = self._gate_subject()
        settled = squashed.gh.get_pr(SQUASH_PR_NUMBER)
        self._interrupted(squashed, state=CLOSED)
        settled.state = OPEN

        squash_run = self._squashes(squashed)

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, APPROVED_COMMITS)
        squash_run.push_mock.assert_called_once()

    def test_work_written_mid_rewrite_survives(self) -> None:
        # The gate's FIRST refusal is a tree that is not provably clean, and
        # something writing to a tracked file between the squash commit and
        # that reading is how it is earned. The branch still has to go back --
        # nothing measured, published, or recorded the squash -- but a reset
        # that took the worktree with it would destroy work nobody here can
        # account for, which is the one thing this domain never does.
        squashed = self._gate_subject()

        squash_run = self._interrupted(squashed, writes=TRACKED_EDIT)

        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(len(self._commits_on_branch()), APPROVED_COMMITS)
        self.assertEqual((self.work / TRACKED_FILE).read_text(), TRACKED_EDIT)
        # And it survives as the UNCOMMITTED change it was, so the retry
        # refuses on the same tree rather than collapsing somebody's edit into
        # a squash nobody asked it to carry.
        self.assertIsNotNone(self._squashes(squashed).error)

    def test_a_flat_switch_is_never_put_back(self) -> None:
        # The pull request is closed while the squash commit is made, so the
        # gate's reading behind the commit refuses and the branch would go
        # back -- but the tree is switched onto the flat branch at the squash
        # during that reading, after every proof ahead of it, and the reset
        # that puts a branch back moves whatever HEAD names. Proven the
        # issue's own first, it is refused, and the flat branch keeps the squash.
        squashed = self._gate_subject()
        self._pull_request = squashed.gh.get_pr(SQUASH_PR_NUMBER)
        self._commit = _rewrite._create_squash_commit
        self._read = squashed.gh.get_pr
        self._committed = False
        self._switched = False

        with (
            patch.object(_rewrite, "_create_squash_commit", side_effect=self._closing_commit),
            patch.object(squashed.gh, "get_pr", side_effect=self._switched_read),
        ):
            self.assertRaises(_naming.BranchRefused, self._squashes, squashed)

        self.assertTrue(self._switched)
        self.assertEqual(len(self._commits_on_branch()), 1)

    def _closing_commit(self, worktree, message):
        """Make the squash commit, and close the pull request behind it."""
        made = self._commit(worktree, message)
        self._pull_request.state = CLOSED
        self._committed = True
        return made

    def _switched_read(self, number: int):
        """Read pull request `number`, switching the checkout onto the flat branch on the first read past the commit."""
        if self._committed and not self._switched:
            squash_support.run_git("checkout", "-q", "-B", _FLAT_BRANCH, cwd=self.work)
            _evidence._checkout_identity.return_value = ProbeAnswer.REFUTED
            self._switched = True
        return self._read(number)


class SquashLandedHoldRealGitTest(
    _MidRewriteSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The hold on the far side of a push that actually went out."""

    def test_a_tree_dirtied_by_the_push_keeps_it(self) -> None:
        # The other side of the same boundary, and the one a restore would be
        # catastrophic on: the push LANDED and only the handoff is held. The
        # checkout is still standing on the squash and nothing was routed, so
        # the RECEIPT is the only thing saying the remote already carries it
        # -- and putting the branch back would take it off a commit the pull
        # request has.
        squashed = self._gate_subject()

        squash_run = self._squashes(
            squashed, push_result=self._dirties_while_pushing,
        )

        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_called_once()
        self.assertEqual(
            squashed.state.get(KEY_RECEIPT_SHA), self.pushed_head,
        )
        self.assertEqual(len(self._commits_on_branch()), 1)

    def _dirties_while_pushing(self, *_called, **_options) -> bool:
        """A push that lands onto a worktree an edit arrives in as it runs."""
        self.pushed_head = self._head_sha()
        (self.work / "unstaged.txt").write_text("written mid-push\n")
        return True


class SquashUnmeasuredRealGitTest(
    _MidRewriteSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A squash whose diff nobody could count, and the retry that counts it.

    The freeze is durable and the count is not, so a reading that fails leaves
    a live generation naming the SQUASH with no number on it -- and the
    reconciliation ahead of the next handler answers that pair by measuring
    the checkout it was frozen on. Put the branch back instead and the record
    names a commit the branch no longer has: every later tick refuses it as a
    candidate that moved, and the measurement is never retried.
    """

    def test_a_failed_measurement_keeps_the_squash(self) -> None:
        squashed = self._gate_subject()

        squash_run = self._unmeasured(squashed)

        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(len(self._commits_on_branch()), 1)
        self.assertEqual(
            squashed.gh.pinned_data(squashed.issue.number)[KEY_CANDIDATE_SHA],
            self._head_sha(),
        )

    def test_the_reconciliation_measures_it_next_tick(self) -> None:
        # The retry, and the whole reason the squash is kept: the pair is
        # answered where it was frozen, so the commit is counted and pushed
        # rather than refused forever as a candidate that moved.
        squashed = self._gate_subject()
        self._unmeasured(squashed)

        pushed = self._reconciles(squashed)

        pushed.assert_called_once()
        self.assertEqual(pushed.call_args.kwargs[REVISION], self._head_sha())

    def _unmeasured(self, squashed):
        """One squash whose diff nobody could count."""
        with patch.object(
            _additions,
            _COUNT_HELPER,
            MagicMock(return_value=AdditionMeasurement(
                failure=MeasurementFailure.DIFF_FAILED,
            )),
        ):
            return self._squashes(squashed)

    def _reconciles(self, squashed):
        """The reading the next tick takes ahead of its own handler."""
        pushed = MagicMock(return_value=True)
        self.enterContext(patch.object(
            branch_transport, squash_support.PUSH_BRANCH_HELPER, pushed,
        ))
        self.enterContext(patch.object(
            _worktree_paths, _WORKTREE_HELPER,
            MagicMock(return_value=self.work),
        ))
        _reconcile._reconciles_published_work(
            squashed.gh,
            squashed.spec,
            squashed.issue,
            SQUASH_LABEL,
            squashed.gh.read_pinned_state(squashed.issue),
        )
        return pushed


if __name__ == "__main__":
    unittest.main()
