# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order the approval handoff makes its durable moves in.

A squash that landed leaves a record of the collapse standing on the pinned
comment, because the count it holds is what the notice behind it is worded
from and nothing else on the issue has one. What ends that record is the write
this handoff makes -- and that write has to land BEFORE the relabel, since
past the label the issue belongs to `documenting`, a stage that never runs the
squash recovery and would carry a claim nothing there could ever answer.

The relabel is a second call, though, and it can fail on its own. So the write
does not leave the boundary empty: what it ends is the CLAIM, and what it
leaves in its place is the commit the move is owed over, which the route ahead
of the next reviewer reads to move the label instead of a second review being
run over a branch already approved, squashed, and published. That record is
dropped behind the label, in a write of its own.

The notice is the other end of the same rule. A post that was owed and did not
go out leaves the count still needed, so the record stays, the label stays,
and the next tick republishes the commit the remote already carries as the
leased no-op it is and words the notice again.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.support.fakes import LazyPullRequest
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _RefusesTheCollapse,
    _RefusesTheRelabel,
    _SquashApprovalFixtureMixin,
)
from tests.workflow.stages.validating.test_squash_route import HANDED_ON

# The notice a finished handoff owes the pull request.
SQUASH_NOTICE = ":package: squashed"

# The count key the notice is worded from, read back beside the head.
COUNT_KEY = "late_collapse_count"

# A head somebody else put on the pull request while the handoff was owed.
MOVED_HEAD = "movedaway01"

# The lazy attribute read a pull request's head is, named as the double takes
# it: past the lookup, which is where a guard around the lookup alone stops.
LAZY_HEAD = "head"

# A settled-handoff value that is not an object id at all -- a hand edit, or
# an older writer -- and the field an issue with no pull request answers with.
NOT_A_COMMIT = "not-a-sha"

PR_NUMBER_KEY = "pr_number"


class _RefusesTheNotice:
    """A pull request that takes every comment but the squash notice."""

    def __init__(self, github) -> None:
        self._posts = github.pr_comment

    def __call__(self, pr_number, body):
        if SQUASH_NOTICE in body:
            raise RuntimeError("pull request comment rejected")
        return self._posts(pr_number, body)


class _RecordsTheLabelAtEachWrite:
    """What the label history and the comment were at each durable write."""

    def __init__(self, github) -> None:
        self.writes: list[tuple[int, dict]] = []
        self._github = github
        self._writes = github.write_pinned_state

    def __call__(self, issue, state):
        moved = len(self._github.label_history)
        self.writes.append((moved, dict(state.data)))
        return self._writes(issue, state)

    def labels_when(self, key: str) -> list[int]:
        """How many labels had moved at each write that carried `key`."""
        return [moved for moved, written in self.writes if key in written]


class SquashHandoffTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """What the handoff behind a landed squash makes durable, and when."""

    def test_the_finished_handoff_drops_the_record(self) -> None:
        github, issue = self._approved_issue()

        self._lands_a_collapse(github, issue)

        self.assertNotIn(_support.COLLAPSE_KEY, github.pinned_data(_support.APPROVAL_ISSUE))
        self.assertIn(HANDED_ON, github.label_history)

    def test_the_record_is_dropped_before_the_relabel(self) -> None:
        # Past the label the issue belongs to `documenting`, which never runs
        # the squash recovery -- so a tick dying between the two writes would
        # strand a claim nothing there could answer, and lose the watermarks
        # the same write carries.
        github, issue = self._approved_issue()
        writes = _RecordsTheLabelAtEachWrite(github)

        with patch.object(github, _support.PINNED_WRITE, writes):
            self._lands_a_collapse(github, issue)

        self.assertTrue(writes.writes)
        self.assertEqual(writes.labels_when(_support.COLLAPSE_KEY), [])

    def test_the_handoff_outlives_that_write(self) -> None:
        # And the write that ends the claim does not leave the boundary empty:
        # the commit the move is owed over goes down while the label is still
        # `validating`, and is dropped only once the move has landed.
        github, issue = self._approved_issue()
        writes = _RecordsTheLabelAtEachWrite(github)

        with patch.object(github, _support.PINNED_WRITE, writes):
            self._lands_a_collapse(github, issue)

        self.assertEqual(writes.labels_when(_support.HANDOFF_KEY), [0])
        self.assertEqual(writes.writes[-1][0], 1)
        self.assertNotIn(_support.HANDOFF_KEY, github.pinned_data(_support.APPROVAL_ISSUE))

    def test_a_refused_notice_keeps_the_record(self) -> None:
        # The count the notice is worded from is on that record and nowhere
        # else, so dropping it would put the announcement beyond every later
        # tick. Kept, the recovery finishes the collapse again and retries --
        # and the label may not move while it stands, since `documenting`
        # never runs the recovery that would finish it.
        github, issue = self._approved_issue()

        with patch.object(github, _support.PR_COMMENT, _RefusesTheNotice(github)):
            self._lands_a_collapse(github, issue)

        pinned = github.pinned_data(_support.APPROVAL_ISSUE)
        self.assertEqual(pinned[_support.COLLAPSE_KEY], _support.COLLAPSED_HEAD)
        self.assertEqual(pinned[COUNT_KEY], _support.COLLAPSED_COMMITS)
        self.assertNotIn(HANDED_ON, github.label_history)


class RefusedRelabelTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """The move a finished handoff owed and did not make.

    Everything else that handoff owes is durable behind the call, so the
    record it leaves is the whole of what a later tick needs: an issue left on
    `validating` with the claim simply dropped is one the next tick runs a
    second reviewer on, over a branch already approved, squashed, and
    published.
    """

    def test_a_refused_relabel_keeps_the_handoff(self) -> None:
        github, issue = self._approved_issue()

        self._refuses_the_relabel(github, issue)

        pinned = github.pinned_data(_support.APPROVAL_ISSUE)
        self.assertEqual(pinned[_support.HANDOFF_KEY], _support.SQUASHED_SHA)
        self.assertNotIn(_support.COLLAPSE_KEY, pinned)
        self.assertNotIn(HANDED_ON, github.label_history)

    def test_the_next_tick_moves_the_label_alone(self) -> None:
        # And the tick after it costs nothing else: no reviewer, no squash,
        # and no second reading of work the pull request already carries.
        github, issue = self._approved_issue()
        self._refuses_the_relabel(github, issue)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_not_called()
        self.assertIn(HANDED_ON, github.label_history)
        self.assertNotIn(_support.HANDOFF_KEY, github.pinned_data(_support.APPROVAL_ISSUE))

    def test_a_moved_publication_drops_the_handoff(self) -> None:
        # A pull request standing somewhere else has moved past the round this
        # record was about -- a docs pass that pushed, a fix, a rebase -- so
        # the label it owed is not owed any more, and the branch goes to the
        # reviewer rather than on to `documenting` unread.
        github, issue, pr = self._setup()
        self._refuses_the_relabel(github, issue)
        pr.head.sha = MOVED_HEAD

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_called_once()

    def test_a_malformed_record_is_never_moved_over(self) -> None:
        # The record is spent on a comparison against the head the pull
        # request stands on, so a value that cannot name a commit is one no
        # comparison could be made over -- and an issue with no pull request
        # to read has nothing standing between such a value and a label moved
        # past the reviewer. It goes, and the round runs.
        github, issue = self._approved_issue()
        self._refuses_the_relabel(github, issue)
        self._pins(github, _support.HANDOFF_KEY, NOT_A_COMMIT)
        self._pins(github, PR_NUMBER_KEY, None)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assertNotIn(HANDED_ON, github.label_history)
        self.assertNotIn(_support.HANDOFF_KEY, github.pinned_data(_support.APPROVAL_ISSUE))

    def test_a_lazy_head_read_holds_the_handoff(self) -> None:
        # A fetched pull request asks GitHub nothing, so the request that can
        # fail is the attribute read behind it. Left outside the guard, the
        # one failure this reading is about escapes the route and takes the
        # tick with it -- and the record is answered by nobody.
        github, issue, pr = self._setup()
        self._refuses_the_relabel(github, issue)
        github.add_pr(LazyPullRequest(pr, failing=LAZY_HEAD))

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_not_called()
        self.assertEqual(
            github.pinned_data(_support.APPROVAL_ISSUE)[_support.HANDOFF_KEY], _support.SQUASHED_SHA,
        )
        self.assertNotIn(HANDED_ON, github.label_history)

    def _refuses_the_relabel(self, github, issue) -> None:
        """One handoff whose every durable move lands but the label."""
        with patch.object(github, _support.SET_LABEL, _RefusesTheRelabel()):
            self._lands_a_collapse(github, issue)


if __name__ == "__main__":
    unittest.main()
