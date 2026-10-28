# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A squash this issue began, or finished short of its relabel, over a record pinning the flat branch.

Both recoveries act on the issue's branch: the unfinished one parks, resets,
recommits, or publishes on it, and the settled one hands it to the docs pass.
So the branch is admitted before either acts (`naming.BranchRefused`): an
unbacked squash takes no park, a settled handoff is neither spent on the move
to `workflow:documenting` nor dropped, and the comment, the label, and the
pull request's thread stay as they were for the repair a human makes. The
dispatcher asks the unbacked squash first, ahead of every handler, and holds
the tick on the same refusal with nothing parked -- save on an issue a human
closed, which it lets on to the stage terminal.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import dispatch_guards as _dispatch_guards, review_subjects as _review_subjects
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _RefusesTheCollapse,
    _RefusesTheRelabel,
    _SquashApprovalFixtureMixin,
)

# The branch an earlier layout pinned, which no live work may stand on.
_FLAT_BRANCH = f"orchestrator/issue-{_support.APPROVAL_ISSUE}"


class SquashBranchRefusalTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """Each squash recovery, refused on the flat branch its record pins."""

    def test_an_unbacked_squash_parks_nothing(self) -> None:
        # A recorded squash with no approval standing behind it parks on any
        # other branch.
        github, issue = self._unbacked()

        self._refused(github, issue)

    def test_the_dispatcher_parks_no_unbacked_squash(self) -> None:
        # The same unbacked squash, asked by the dispatcher's guard on the
        # validating label: the tick is held with nothing parked or posted,
        # and once a human has closed the issue it is let on, still with
        # nothing parked, for the stage terminal to answer.
        for closed in (False, True):
            with self.subTest(closed=closed):
                github, issue = self._unbacked()
                self._pins(github, "branch", _FLAT_BRANCH)
                issue.closed = closed
                before = self._reading(github)

                held = _dispatch_guards._record_stops_the_tick(
                    github, _TEST_SPEC, issue, github.workflow_label(issue), github.read_pinned_state(issue),
                )

                self.assertEqual((held, self._reading(github)), (not closed, before))

    def test_a_settled_handoff_is_not_spent(self) -> None:
        # The squash landed and its relabel did not, leaving the handoff the
        # next tick would spend on the move to `workflow:documenting`.
        github, issue = self._approved_issue()
        with patch.object(github, _support.SET_LABEL, _RefusesTheRelabel()):
            self._lands_a_collapse(github, issue)
        self.assertIn(_support.HANDOFF_KEY, self._reading(github)[0])

        self._refused(github, issue)

    def _unbacked(self) -> tuple:
        """An approved issue recording a squash whose approval has since been written null; its client and issue."""
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._pins(github, _review_subjects.APPROVED_SUBJECT, None)
        return github, issue

    def _refused(self, github, issue) -> None:
        """Pin the flat branch, then one tick refuses it with the comment, label, and thread as they were."""
        self._pins(github, "branch", _FLAT_BRANCH)
        before = self._reading(github)

        with self.assertRaises(_naming.BranchRefused):
            self._run_squash_approval(github, issue, _RefusesTheCollapse())

        self.assertEqual(self._reading(github), before)

    def _reading(self, github) -> tuple:
        """The pinned comment, the label history, and the posted comments, as one reading."""
        labels = list(github.label_history)
        return github.pinned_data(_support.APPROVAL_ISSUE), labels, list(github.posted_comments)


if __name__ == "__main__":
    unittest.main()
