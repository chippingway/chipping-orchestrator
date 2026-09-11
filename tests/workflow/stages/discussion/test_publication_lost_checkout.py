# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A publication whose checkout and local branch are both gone.

The marker is written before the push and the PR number only after the PR is
open, so the widest crash window leaves an issue whose plan is on the remote
and whose PR is up, with nothing pinned pointing at either. Everything the next
tick needs is still recorded -- the marker names the commit, the anchor names
the branch -- but none of it is on this host any more once the worktree
directory and the local ref go with a restart, an operator's cleanup, or a
fresh clone.

What decides the outcome is where the checkout is rebuilt from. Anchored on
`<remote>/<base>` the branch comes back without the published commit, and the
publication is then refused for a tip it cannot find while the PR it opened
stays up unretired and the conversation is free to open another round over the
top of it. Anchored on `<remote>/<branch>` the pushed commit comes back with
it, and the tick finishes the publication it began.

`pr_number` cannot be what that choice is made on, because the crash this is
about is the one that happens before `pr_number` exists. The marker is, and the
remote is what says whether the push it precedes ever landed.

A push that REPORTED failure reaches the same state by the other door, and it
is the door nothing resumes on its own: that park is a request to an operator,
so the reply answering it is the only thing that ever carries the marker
forward. "The push failed" is a claim about the request rather than about the
remote, and by the time the reply arrives this host can have lost the checkout
and the ref along with it -- at which point every local reading says nothing
ever happened.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.fixtures import (
    BASE_TIP_SHA,
    EVENT_PR_CLOSED_WITHOUT_MERGE,
    KEY_PARK_REASON,
    LABEL_REJECTED,
    STATE_CLOSED,
    _agent,
)
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    _mark_in_flight,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_PUBLISHED_ISSUE_NUMBER = 1280
_UNPUSHED_ISSUE_NUMBER = 1281
_LOST_RETRY_ISSUE_NUMBER = 1282
_MERGED_LOST_ISSUE_NUMBER = 1283
_AMENDED_LOST_ISSUE_NUMBER = 1284
_CLOSED_LOST_ISSUE_NUMBER = 1285

_OPEN_PR_NUMBER = 8321
_MERGED_PR_NUMBER = 8322
_AMENDED_PR_NUMBER = 8323
_CLOSED_PR_NUMBER = 8324
# The stamp a rejection leaves, spelled here rather than imported from the
# terminal's own fixtures: it is a pinned-state wire key, and a test that
# reads it from the owner would agree with a rename instead of failing on
# one.
_KEY_CLOSED_WITHOUT_MERGE_AT = "closed_without_merge_at"
# What a reviewer's own push onto the plan's branch leaves as its head, and
# what a checkout rebuilt from that branch therefore comes back on.
_AMENDED_HEAD = "the-commit-a-reviewer-pushed-onto-the-plan-pr"
_INHERITING_ROUND = "a round that would inherit it"
# The tip is read once to judge the branch, and once more by the round that
# opens when there turns out to be nothing to publish.
_RESTORED_HEAD = (_support.HEAD_AFTER_COMMIT,) * 2
_UNPUBLISHED_HEAD = (_support.HEAD_BEFORE_ROUND,) * 3
# What the remote says about the issue branch: the pushed one is there, and the
# one whose push never landed is not.
_PUSHED_TIP = _support.HEAD_AFTER_COMMIT
_NO_SUCH_BRANCH = ""


def _seed_failed_push(issue_number: int):
    """The same publication, parked on the push that reported failure.

    Seeded through the park rather than beside it, because that reason is the
    whole reason this case exists: the interrupted-publication path at the top
    of a tick steps around it deliberately, so the marker only ever moves again
    on the reply -- which is seeded with it.
    """
    gh, issue = _seed_parked_discussion(
        issue_number,
        replies=(_reply(DISCUSSION_REPLY),),
        park_reason=_support.PARK_DISCUSSION_PUSH_FAILED,
    )
    _mark_in_flight(
        gh, issue.number, **{_support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT},
    )
    return gh, issue


def _seed_interrupted_publication(issue_number: int):
    """An issue whose publication died after the marker was written.

    Everything here is what that one durable write left: the tip being
    published, the round anchor, the base it was measured against, and the
    session it belongs to. What is deliberately absent is `pr_number` -- the
    crash this describes happens before there is one.
    """
    gh, issue = _support._seed_discussion(issue_number)
    gh.seed_state(
        issue_number,
        **{
            _support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT,
            _support.KEY_ROUND_BRANCH: _support._issue_branch(issue_number),
            _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
            _support.KEY_BASE_SHA: BASE_TIP_SHA,
            _support.KEY_DISCUSSION_SESSION_ID: _support.DISCUSSION_SESSION,
        },
    )
    return gh, issue


def _descends_from_the_plan(worktree, ancestor: str, revision: str) -> bool:
    """The ancestry a reviewer's push onto the plan's branch really leaves.

    Their commit contains the one this publication pushed; the published one
    does not contain theirs. A single answer for both directions would let the
    reading pass for the wrong reason.
    """
    return (ancestor, revision) == (_support.HEAD_AFTER_COMMIT, _AMENDED_HEAD)


class DiscussionLostCheckoutTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """Where a publication in flight rebuilds a checkout that is gone."""

    def test_a_pushed_plan_comes_back_remotely(self) -> None:
        # The crash: pushed, PR opened, dead before either was recorded. The
        # branch exists nowhere on this host now, so a base-anchored restore
        # would hand this tick a tree without the plan in it -- and the plan is
        # sitting on a pull request the whole time.
        gh, issue = _seed_interrupted_publication(_PUBLISHED_ISSUE_NUMBER)
        branch = _support._issue_branch(issue.number)
        gh.existing_open_pr[branch] = FakePR(
            number=_OPEN_PR_NUMBER, head_branch=branch,
        )

        mocks = self._run_over_missing_checkout(
            gh, issue, head_shas=_RESTORED_HEAD, remote_branch_tip=_PUSHED_TIP,
        )

        mocks[_support.ENSURE_PR_WORKTREE].assert_called_once()
        mocks[_support.ENSURE_WORKTREE].assert_not_called()
        # It is the ISSUE branch the remote is asked about, not the base.
        self.assertEqual(mocks[_support.REMOTE_BASE_TIP].call_args.args[2], branch)
        # The PR that is already open is adopted rather than duplicated, and
        # no round runs over the top of the design it carries.
        self.assertEqual(gh.opened_prs, [])
        mocks[_support.RUN_AGENT].assert_not_called()
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            (
                pinned_data[_support.KEY_PR_NUMBER],
                pinned_data[_support.KEY_PLAN_PATH],
                pinned_data[KEY_PARK_REASON],
            ),
            (
                _OPEN_PR_NUMBER,
                self.plan_path(issue.number),
                _support.PARK_DISCUSSION_PLAN_PUBLISHED,
            ),
        )
        # The marker is spent by the records that answer it.
        self.assertIsNone(pinned_data[_support.KEY_PUBLISHING_SHA])

    def test_an_unlanded_push_restores_from_base(self) -> None:
        # The same marker, and the remote says there is no such branch: the
        # push it precedes never landed, and the commit it named went with the
        # worktree. There is nothing to restore and nothing to publish, so the
        # marker is spent and the conversation carries on.
        gh, issue = _seed_interrupted_publication(_UNPUSHED_ISSUE_NUMBER)

        mocks = self._run_over_missing_checkout(
            gh,
            issue,
            head_shas=_UNPUBLISHED_HEAD,
            remote_branch_tip=_NO_SUCH_BRANCH,
        )

        # Twice: once for the reading that finds nothing to publish, and
        # once for the round that then opens on the restored tree.
        mocks[_support.ENSURE_WORKTREE].assert_called()
        mocks[_support.ENSURE_PR_WORKTREE].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        mocks[_support.RUN_AGENT].assert_called_once()
        pinned_data = gh.pinned_data(issue.number)
        self.assertIsNone(pinned_data[_support.KEY_PUBLISHING_SHA])
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)

    def test_a_failed_push_retries_from_the_remote(self) -> None:
        # The same lost host, reached by the door nothing opens on its own. The
        # push reported failure, so the tick parked asking an operator to fix
        # it, and the reply is what retries the publication. By then there is
        # no tree, no local ref, and an anchor nothing has moved off -- so
        # every local reading says this stage was never mid-anything. Read that
        # way the reply opens a round instead, and the write that opens one
        # retires the marker: the plan stays on the remote with no PR, no
        # record, and nothing left that knows to look for it.
        gh, issue = _seed_failed_push(_LOST_RETRY_ISSUE_NUMBER)

        mocks = self._run_over_missing_checkout(
            gh, issue, head_shas=_RESTORED_HEAD, remote_branch_tip=_PUSHED_TIP,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.ENSURE_PR_WORKTREE].assert_called_once()
        self.assertEqual(len(gh.opened_prs), 1)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            (
                pinned_data[KEY_PARK_REASON],
                pinned_data[_support.KEY_PLAN_PATH],
                pinned_data[_support.KEY_PUBLISHING_SHA],
            ),
            (
                _support.PARK_DISCUSSION_PLAN_PUBLISHED,
                self.plan_path(issue.number),
                None,
            ),
        )

    def test_a_merged_plan_is_recorded_from_base(self) -> None:
        # The widest version of the same crash, ended by a merge. The PR that
        # was opened is closed and its branch is gone with it, so the restore
        # has nowhere but the base to rebuild from -- and the tip it comes back
        # on is neither the commit the marker names nor the round's anchor.
        # Read only against those, it is a branch somebody moved: the issue
        # parks on that forever, with no `pr_number` and no plan path ever
        # written, while the plan it is parked about is sitting in the base.
        gh, merged_issue = _seed_interrupted_publication(
            _MERGED_LOST_ISSUE_NUMBER,
        )
        gh.add_pr(FakePR(
            number=_MERGED_PR_NUMBER,
            head_branch=_support._issue_branch(merged_issue.number),
            head=FakePRRef(sha=_support.HEAD_AFTER_COMMIT),
            merged=True,
            state=STATE_CLOSED,
        ))

        mocks = self._run_over_missing_checkout(
            gh,
            merged_issue,
            head_shas=(BASE_TIP_SHA,) * 2,
            remote_branch_tip=_NO_SUCH_BRANCH,
        )

        # Nothing is pushed, nothing is opened, and no round runs over a design
        # that is already in the base.
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        # Nothing is said to the humans either: they merged it, so a park
        # telling them to go and review it would answer a verdict they have
        # already given. The records go down on their own, and the terminal
        # reads them on the next tick.
        self.assertEqual(gh.posted_comments, [])
        pinned_data = gh.pinned_data(merged_issue.number)
        self.assertEqual(
            (
                pinned_data[_support.KEY_PR_NUMBER],
                pinned_data[_support.KEY_PLAN_PATH],
                pinned_data[_support.KEY_PUBLISHING_SHA],
            ),
            (
                _MERGED_PR_NUMBER,
                self.plan_path(merged_issue.number),
                None,
            ),
        )

    def test_an_amended_open_pr_is_adopted(self) -> None:
        # The same crash, with the humans having written on the pull request
        # before anything came back for it. The restore anchors on the remote
        # branch, so the checkout comes back on THEIR head -- neither the
        # commit the marker names nor the round's anchor. Judged against the
        # tip on disk, this asks whether their head descends from itself,
        # answers no, and parks `discussion_stale_publication` with no
        # `pr_number` and no plan path, while the plan is on a pull request the
        # humans are reading. The marker is what has to be judged instead.
        gh, amended_issue = _seed_interrupted_publication(
            _AMENDED_LOST_ISSUE_NUMBER,
        )
        gh.add_pr(FakePR(
            number=_AMENDED_PR_NUMBER,
            head_branch=_support._issue_branch(amended_issue.number),
            head=FakePRRef(sha=_AMENDED_HEAD),
            commit_shas=(_support.HEAD_AFTER_COMMIT,),
        ))

        mocks = self._run_over_missing_checkout(
            gh,
            amended_issue,
            head_shas=(_AMENDED_HEAD,) * 2,
            remote_branch_tip=_AMENDED_HEAD,
            commit_contains=_descends_from_the_plan,
        )

        # Their head already carries the plan, so there is nothing to push --
        # and the older SHA is exactly what a push would send over it.
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, mocks)
        pinned_data = gh.pinned_data(amended_issue.number)
        self.assertEqual(
            (
                pinned_data[_support.KEY_PR_NUMBER],
                pinned_data[_support.KEY_PLAN_PATH],
                pinned_data[KEY_PARK_REASON],
                pinned_data[_support.KEY_PUBLISHING_SHA],
            ),
            (
                _AMENDED_PR_NUMBER,
                self.plan_path(amended_issue.number),
                _support.PARK_DISCUSSION_PLAN_PUBLISHED,
                None,
            ),
        )

    def test_an_amended_closed_pr_is_recorded(self) -> None:
        # The same rebuild, ended the other way: the humans amended the plan on
        # its pull request and then closed it without merging. Their head still
        # carries the commit the marker names, so there is nothing left to
        # push -- but a close is not the reset the stale park asks for either,
        # and refused as one the issue parks forever with no `pr_number`, no
        # terminal label, no event, and no branch anything will reap, while the
        # verdict sits on a pull request nothing points at.
        gh, closed_issue = _seed_interrupted_publication(
            _CLOSED_LOST_ISSUE_NUMBER,
        )
        gh.add_pr(FakePR(
            number=_CLOSED_PR_NUMBER,
            head_branch=_support._issue_branch(closed_issue.number),
            head=FakePRRef(sha=_AMENDED_HEAD),
            commit_shas=(_support.HEAD_AFTER_COMMIT,),
            state=STATE_CLOSED,
        ))

        recorded = self._run_over_missing_checkout(
            gh,
            closed_issue,
            head_shas=(_AMENDED_HEAD,) * 2,
            remote_branch_tip=_AMENDED_HEAD,
            commit_contains=_descends_from_the_plan,
        )

        # Recorded rather than refused, and said to nobody: what the humans
        # decided needs no park telling them to go and review it.
        recorded[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, recorded)
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(
            gh.pinned_data(closed_issue.number)[_support.KEY_PR_NUMBER],
            _CLOSED_PR_NUMBER,
        )

        # And the tick after it is the ending they asked for.
        finalized = self._run_discussion(
            gh, closed_issue, run_agent=_agent(last_message=_INHERITING_ROUND),
        )

        self.assertEqual(
            gh.label_history, [(closed_issue.number, LABEL_REJECTED)],
        )
        self.assertIn(
            _KEY_CLOSED_WITHOUT_MERGE_AT,
            gh.pinned_data(closed_issue.number),
        )
        self.assertEqual(
            len([
                event for event in gh.recorded_events
                if event["event"] == EVENT_PR_CLOSED_WITHOUT_MERGE
            ]),
            1,
        )
        finalized[_support.CLEANUP_TERMINAL_BRANCH].assert_called_once()

    def _run_over_missing_checkout(self, gh, issue, **run_options):
        """One tick whose per-issue checkout is not on disk at all."""
        with tempfile.TemporaryDirectory() as parent:
            missing = Path(parent) / f"issue-{issue.number}"
            with seam_patch(_support.WORKTREE_PATH, MagicMock(return_value=missing)):
                return self._run_discussion(
                    gh,
                    issue,
                    run_agent=_agent(
                        session_id=_support.DISCUSSION_SESSION,
                        last_message=_INHERITING_ROUND,
                    ),
                    committed_paths=(self.plan_path(issue.number),),
                    **run_options,
                )


if __name__ == "__main__":
    unittest.main()
