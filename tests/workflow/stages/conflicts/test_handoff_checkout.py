# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a counted conflict round hands to `validating`, proven the issue's own at the label, over a real clone.

The publication proves its checkout through the push, but the round's own
writes -- the report debt and the count with the head it hands on -- come
after that proof, and a tree switched onto the flat branch at the published
commit passes every reading of that commit and tree. So the label is moved
only once the checkout is proven again: switched during the count's write,
the round keeps its label, its receipt, and the claim it was written with,
and the owed move a later tick makes from that claim is refused the same way
over a checkout still switched. A rebase that moved nothing counts its round
and hands on with no push at all, so that flip proves the checkout too: one
switched while the head the rebase left is read, or while the round's audit
event is written, counts nothing.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import naming
from orchestrator.workflow.stages.conflicts import handoff, publication
from orchestrator.workflow.stages.conflicts.models import _ConflictContext, _Replayed, _WorktreeSync
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 300
PR_NUMBER = 42
RESOLVING = "workflow:resolving_conflict"
VALIDATING = "workflow:validating"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_CLAIM = "conflict_handed_sha"
_RECEIPT = "implementing_published_sha"
# The round a conflict episode counts: its pinned field and its audit event alike.
_ROUND = "conflict_round"


def _switching_ahead_of(worktree, through):
    """`through`, with `worktree` switched onto the flat branch ahead of its first call."""

    def wrapper(*args, **kwargs):
        if not _run_git("branch", "--list", _FLAT_BRANCH, cwd=worktree).strip():
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)
        return through(*args, **kwargs)
    return wrapper


class _HandoffCheckoutCase(unittest.TestCase):
    """The planted commit's issue on `resolving_conflict`, its pull request on the amended head."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=RESOLVING)
        self.gh.add_issue(self.issue)
        amended = FakePRRef(sha=self.repo.amended)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch, head=amended))
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER)
        self._write = self.gh.write_pinned_state
        self._emit = self.gh.emit_event
        self.enterContext(patch.object(config, "DECOMPOSE", False))
        self.enterContext(patch.object(branch_transport, "_push_branch", return_value=True))

    def _context(self) -> _ConflictContext:
        """The conflict stage's context over the record as it stands."""
        state = self.gh.read_pinned_state(self.issue)
        return _ConflictContext(self.gh, self.repo.spec, self.issue, state)


class ConflictHandoffCheckoutTest(_HandoffCheckoutCase):
    """A clean rebase's publication of the planted commit, handed on to review."""

    def test_the_issue_s_own_checkout_is_handed_on(self) -> None:
        self._publishes()

        self.assertEqual(self.gh.workflow_label(self.issue), VALIDATING)

    def test_a_switch_at_the_count_holds_the_move(self) -> None:
        with patch.object(self.gh, "write_pinned_state", side_effect=self._switched_write):
            self.assertRaises(naming.BranchRefused, self._publishes)

        recorded = self.gh.pinned_data(ISSUE)
        self.assertEqual(self.gh.workflow_label(self.issue), RESOLVING)
        self.assertEqual(recorded.get(_CLAIM), self.repo.published)
        self.assertEqual(recorded.get(_RECEIPT), self.repo.published)

        # The tick after finds the claim and the branch in sync on its head,
        # and the checkout still switched: the owed move is refused too.
        worktree = self.repo.worktree
        in_sync = _WorktreeSync(worktree=worktree, branch=self.branch, ahead=0, behind=0)
        context = self._context()
        self.assertRaises(naming.BranchRefused, handoff._makes_the_owed_move, context, in_sync)
        recorded = self.gh.pinned_data(ISSUE)
        self.assertEqual(self.gh.workflow_label(self.issue), RESOLVING)
        self.assertEqual(recorded.get(_CLAIM), self.repo.published)

    def _publishes(self) -> None:
        """Publish the clean rebase that left the planted commit, as the stage disposes of one."""
        replayed = _Replayed(head=self.repo.amended)
        context = self._context()
        publication._publish_clean_rebase(context, self.repo.worktree, replayed, 0, PR_NUMBER)

    def _switched_write(self, issue, state):
        """Land the write, switching the checkout onto the flat branch behind the one carrying the round's claim."""
        written = self._write(issue, state)
        worktree = self.repo.worktree
        switched = _run_git("branch", "--list", _FLAT_BRANCH, cwd=worktree).strip()
        if state.get(_CLAIM) and not switched:
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)
        return written


class NoOpFlipCheckoutTest(_HandoffCheckoutCase):
    """A rebase that moved nothing, counted and handed on to review with no push behind it."""

    def test_a_no_op_switched_mid_head_read_holds(self) -> None:
        # The rebase moved nothing, so the round is counted and handed on with
        # no push behind it -- and the tree is switched while the head the
        # rebase left is read. The flip proves the checkout first: nothing is
        # counted, and the label stays.
        read = _switching_ahead_of(self.repo.worktree, _probes._head_sha)

        with patch.object(_probes, "_head_sha", side_effect=read):
            self._refuses_the_flip()

        self.assertEqual(self.gh.workflow_label(self.issue), RESOLVING)
        self.assertIsNone(self.gh.pinned_data(ISSUE).get(_ROUND))

    def test_a_switch_at_the_audit_event_holds(self) -> None:
        # Past the flip's first proof, the tree is switched while the round's
        # audit event is written. The label is proven again behind it: the
        # event went out, and nothing is counted or handed on.
        with patch.object(self.gh, "emit_event", side_effect=self._switched_event):
            self._refuses_the_flip()

        events = [record["event"] for record in self.gh.recorded_events]
        self.assertIn(_ROUND, events)
        self.assertEqual(self.gh.workflow_label(self.issue), RESOLVING)
        self.assertIsNone(self.gh.pinned_data(ISSUE).get(_ROUND))

    def _refuses_the_flip(self) -> None:
        """Dispose of the clean rebase that left the published head where it stood, refused."""
        replayed = _Replayed(head=self.repo.published)
        context = self._context()
        self.assertRaises(
            naming.BranchRefused,
            publication._publish_clean_rebase, context, self.repo.worktree, replayed, 0, PR_NUMBER,
        )

    def _switched_event(self, event, **payload):
        """Send the event, switching the checkout onto the flat branch behind the one counting the round."""
        sent = self._emit(event, **payload)
        if event == _ROUND:
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=self.repo.worktree)
        return sent


if __name__ == "__main__":
    unittest.main()
