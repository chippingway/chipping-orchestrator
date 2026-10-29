# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A refresh rebase's anchor and a failed one's abort, held to a switched checkout, over a real clone.

A rebase onto a base that changed the same line stops on the conflict, and
the refresh reads the conflicted files and aborts it -- which switches the
tree back onto the branch the rebase was rewriting and discards whatever the
index holds. The checkout was proven before the rebase, but the rebase and
the conflict read are a window a tree can be switched in. So the abort asks
again: one switched onto the flat branch, with content of its own staged,
keeps its branch and that content -- on the pre-PR road, and on the PR road
with the attempt's anchor standing for the recovery that finds the checkout
restored. The issue's own checkout is still aborted back onto its branch.

The anchor itself is the head a recovery resets the branch back to, so it is
recorded only off a checkout proven the issue's own behind the head's read: a
tree switched onto the flat branch while that head is read anchors nothing,
and the refresh after the operator restores the issue's checkout anchors on
the issue's own head rather than resetting it onto the other branch's commit.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.base_sync import startup
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import refresh_anchor_support as _anchored

_FLAT_BRANCH = f"orchestrator/issue-{_anchored.ISSUE}"
_PLAN = "plan.md"
_STAGED = "operator staged content\n"
_ANCHOR = "pending_auto_base_rebase_push_sha"

# The read a failed rebase names its conflicted files by.
_CONFLICT_READ = ("diff", "--name-only", "--diff-filter=U")


def _switching_at_the_conflict_read(checkout, through):
    """`through`, switching `checkout` onto the flat branch with content staged behind the conflict read."""

    def wrapper(*args, **kwargs):
        answer = through(*args, **kwargs)
        if args == _CONFLICT_READ:
            _anchored._git(checkout, "checkout", "-q", "-f", "-b", _FLAT_BRANCH)
            (checkout / _PLAN).write_text(_STAGED)
            _anchored._git(checkout, "add", _PLAN)
        return answer
    return wrapper


def _rebase_context(world) -> _AutoRebaseContext:
    """The ordinary rebase's context over `world`'s issue, one commit behind its base, as the refresh enters it."""
    issue = world.gh.get_issue(_anchored.ISSUE)
    return _AutoRebaseContext(
        world.gh, world.spec, issue, world.gh.read_pinned_state(issue), world.checkout,
        _anchored.PR_NUMBER, 1, WorkflowLabel.VALIDATING, None,
    )


class RefreshAbortTest(unittest.TestCase):
    """A rebase of the issue's own branch that stops on a conflict with the base."""

    def setUp(self) -> None:
        self.world = _anchored.AnchoredCheckout(self)
        self.world.left_mid_rebase()
        _anchored._git(self.world.checkout, "rebase", "--abort")
        self.switching = _switching_at_the_conflict_read(self.world.checkout, commands._git_hardened)

    def test_the_issue_s_own_checkout_is_aborted(self) -> None:
        self._seeded_pre_pr()

        self.world.syncs()

        self.assertEqual(self._standing(), (self.world.branch, "the branch's line\n"))

    def test_a_pre_pr_switch_keeps_the_tree(self) -> None:
        self._seeded_pre_pr()

        with patch.object(commands, "_git_hardened", side_effect=self.switching):
            self.world.syncs()

        self.assertEqual(self._standing(), (_FLAT_BRANCH, _STAGED))

    def test_a_pr_switch_keeps_the_anchor(self) -> None:
        world = self.world
        world.gh.seed_state(_anchored.ISSUE, branch=world.branch, pr_number=_anchored.PR_NUMBER)
        world.gh.get_pr(_anchored.PR_NUMBER).head.sha = world.head()
        context = _rebase_context(world)

        with patch.object(commands, "_git_hardened", side_effect=self.switching):
            startup._start_auto_rebase(context, world.gh.get_pr(_anchored.PR_NUMBER), None)

        self.assertEqual(self._standing(), (_FLAT_BRANCH, _STAGED))
        self.assertIsNotNone(world.gh.pinned_data(_anchored.ISSUE).get(_ANCHOR))

    def _seeded_pre_pr(self) -> None:
        """Record the issue's branch with no pull request and no anchor, the pre-PR refresh's road."""
        self.world.gh.seed_state(_anchored.ISSUE, branch=self.world.branch)

    def _standing(self) -> tuple[str, str]:
        """The branch the checkout stands on and what its plan file holds."""
        checkout = self.world.checkout
        return _anchored._git(checkout, "symbolic-ref", "--short", "HEAD"), (checkout / _PLAN).read_text()



class AnchorCaptureTest(unittest.TestCase):
    """The head an ordinary rebase anchors on, read off the issue's own checkout one commit behind its base."""

    def setUp(self) -> None:
        self.world = _anchored.AnchoredCheckout(self)
        self.original = _anchored.behind_its_base(self.world)
        self._read = _probes._head_sha
        self._switched_at = None

    def test_a_switch_mid_head_read_anchors_nothing(self) -> None:
        world = self.world
        context = _rebase_context(world)
        with patch.object(_probes, "_head_sha", side_effect=self._switched_read):
            startup._start_auto_rebase(context, world.gh.get_pr(_anchored.PR_NUMBER), None)

        self.assertIsNone(world.gh.pinned_data(_anchored.ISSUE).get(_ANCHOR))

        # The operator restores the issue's checkout, and the next refresh --
        # its remote unreachable -- anchors on the issue's own head, never on
        # the commit the switched tree carried.
        _anchored._git(world.checkout, "checkout", "-q", world.branch)
        world.syncs()

        self.assertNotEqual(world.head(), self._switched_at)
        self.assertFalse((world.checkout / _anchored.FOREIGN_FILE).exists())
        recorded = world.gh.pinned_data(_anchored.ISSUE)
        self.assertEqual(recorded.get(_ANCHOR), self.original)

    def _switched_read(self, worktree):
        """Read the checkout's head, the checkout switched onto the flat branch first, the first time only."""
        if self._switched_at is None:
            self.world.switched_to_the_flat_branch()
            self._switched_at = self.world.head()
        return self._read(worktree)


if __name__ == "__main__":
    unittest.main()
