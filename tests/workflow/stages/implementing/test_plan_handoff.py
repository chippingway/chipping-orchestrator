# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The handoff from a published plan, which arrives with a PR attached.

An issue relabeled here out of `discussion` can carry a PR that says what to
build rather than a build, and the humans agree to that design by merging it --
which is precisely when they relabel. So a merged recorded PR has to be read for
what it is, not for the fact that it merged: closing the issue as `done` on a
design document ends it before a developer has run.

Which record answers changes at one point: the durable handoff. Until it lands,
nothing here has pushed, so the plan-path record answers whatever the PR's head
is now. After it, the recorded commit answers against GitHub rather than against
a record this stage promises to clear, because a tick that pushes the dev's
commits onto that same PR and dies before persisting anything has already made
it an implementation, and the merge that follows has to finalize.

The handoff is therefore where the two have to meet, and `AmendedPlanHandoffTest`
is about the case that makes them: between the publication and the relabel the
humans have the design on a PR and may move its head -- a correction to the
Markdown, the base merged in to make it mergeable. That head is what the
developer must build on, and what has to stand in for the path record being
retired, or the next tick reads their own edit as an implementation.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.fixtures import (
    BASE_TIP_SHA,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    LABEL_DONE,
    _agent,
    _issue_branch,
)
from tests.workflow.stages.implementing import (
    plan_handoff_test_support as _support,
    read_only_relabel_test_support as _stage_support,
)
from tests.workflow.stages.implementing.plan_handoff_test_support import _HandoffTickMixin

_MERGED_PLAN_ISSUE_NUMBER = 1001
_PUSHED_PLAN_ISSUE_NUMBER = 1002
_FLAKY_FETCH_ISSUE_NUMBER = 1003
_AMENDED_PLAN_ISSUE_NUMBER = 1006
_UNMOVED_PLAN_ISSUE_NUMBER = 1007
_UNREACHED_HEAD_ISSUE_NUMBER = 1008
_INTERRUPTED_HANDOFF_ISSUE_NUMBER = 1009
_UNREADABLE_PR_ISSUE_NUMBER = 1010
_DELETED_BRANCH_ISSUE_NUMBER = 1011
_MERGED_BRANCH_ISSUE_NUMBER = 1012
_CRASHED_ROUND_MERGE_ISSUE_NUMBER = 1013
_CRASHED_PUBLISH_MERGE_ISSUE_NUMBER = 1014
_CRASHED_ANCHOR_ISSUE_NUMBER = 1015

# Where a plan branch the remote no longer has sends the checkout: the base, as
# the anchor reports landing there.
_BASE_TIP = "the-commit-the-base-branch-is-at"
_FETCH_FAILURE = "502 while reading the pull request"

# The two heads a merged plan PR can be sitting on while its record still
# stands, and neither is this stage's work: the commit publication put there,
# and the one the humans left when they edited the design before agreeing to it.
_LIVE_PLAN_HEADS = (
    (_MERGED_PLAN_ISSUE_NUMBER, _support.PLAN_COMMIT),
    (_AMENDED_PLAN_ISSUE_NUMBER, _support.AMENDED_PLAN_COMMIT),
)

# The two records a `discussion` tick that never reported leaves standing, and
# neither depends on `awaiting_human`: an opening round leaves the issue
# unparked by design, and a publication's marker is written from the
# disposition of one. Both are seeded with no plan record beside them, which is
# what a crash before that write really leaves.
_UNREPORTED_ROUNDS = (
    (_CRASHED_ROUND_MERGE_ISSUE_NUMBER, _stage_support.KEY_ROUND_OPEN, True),
    (_CRASHED_PUBLISH_MERGE_ISSUE_NUMBER, _stage_support.KEY_PUBLISHING_SHA, _stage_support.HEAD_AFTER_COMMIT),
)


class _FetchFailsOnce:
    """A `get_pr` that fails its first call and answers every one after.

    The shape a rate limit or a dropped connection takes, planted where the
    plan question is asked -- so a stage that asks it twice gets a different
    answer the second time.
    """

    def __init__(self, get_pr) -> None:
        self.get_pr = get_pr
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(_FETCH_FAILURE)
        return self.get_pr(*args, **kwargs)


class PlanHandoffTest(unittest.TestCase, _HandoffTickMixin):
    """What this stage makes of the plan PR an issue arrives carrying."""

    def test_a_published_plan_record_is_retired(self) -> None:
        # The discussion stage's records all end here. The plan PR record is
        # what stops that stage acting while the design is with the humans on
        # it, and this relabel is them deciding; the round flag is what tells it
        # which commits are its own, and one outliving the relabel would have it
        # claim the commit the dev is about to make. (The publication marker is
        # not seeded beside them because it cannot be: the write that records a
        # published plan retires it.)
        gh, issue = _stage_support._seed_relabeled_discussion(
            _support.PLAN_ISSUE_NUMBER,
            _stage_support.PARK_DISCUSSION_PLAN_PUBLISHED,
            **{_stage_support.KEY_PLAN_PATH: _support.PLAN_PATH, _stage_support.KEY_ROUND_OPEN: True},
        )

        mocks = self._run_handoff_tick(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            has_new_commits=True,
            branch_tip_sha=_stage_support.HEAD_BEFORE_ROUND,
            head_shas=(
                _stage_support.HEAD_BEFORE_ROUND,
                _stage_support.HEAD_BEFORE_ROUND,
                _stage_support.HEAD_AFTER_COMMIT,
            ),
        )

        mocks[_stage_support.RUN_AGENT].assert_called_once()
        pinned_data = gh.pinned_data(issue.number)
        for retired in (_stage_support.KEY_PLAN_PATH, _stage_support.KEY_ROUND_OPEN):
            with self.subTest(key=retired):
                self.assertIsNone(pinned_data.get(retired))

    def test_a_merged_plan_pr_is_not_the_work(self) -> None:
        # The humans agreed to the design by merging the plan and moved the
        # issue on to be built. Read as an implementation, that merge closes
        # the issue as `done` before a developer has run -- on the strength of
        # a document whose whole content is work still to do. Editing the plan
        # before merging it is part of agreeing to it, so a head that has moved
        # off the published commit is the same answer while the record stands:
        # nothing here has pushed yet, and the mismatch is theirs, not ours.
        for issue_number, head_sha in _LIVE_PLAN_HEADS:
            with self.subTest(head=head_sha):
                self._assert_built_not_finalized(issue_number, head_sha)

    def test_a_pushed_over_plan_pr_is_the_work(self) -> None:
        # The crash window: with the handoff already durable, this stage pushed
        # the dev's commits onto the still open plan PR and died before
        # persisting that the PR had stopped being a plan. The plan commit is
        # still recorded -- but the PR's head moved when we pushed, and that is
        # what the guard reads, so the merge that followed finalizes instead of
        # being ignored and the dev is not run over the same work again.
        gh, issue = _support._seed_accepted_handoff(
            _PUSHED_PLAN_ISSUE_NUMBER, head_sha=_stage_support.HEAD_AFTER_COMMIT,
        )

        # The branch is where that push left it, which is the durable half of
        # what happened: a tip past the baseline the handoff recorded is a
        # developer's commit whatever pinned state never got written.
        mocks = self._run_handoff_tick(
            gh, issue, branch_tip_sha=_stage_support.HEAD_AFTER_COMMIT,
        )

        mocks[_stage_support.RUN_AGENT].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        self.assertIn((issue.number, LABEL_DONE), gh.label_history)

    def test_a_failed_pr_read_defers_the_tick(self) -> None:
        # The read that tells a plan from an implementation failed. Answered
        # "not the plan", it fell through to the merged-PR terminal, which
        # asked GitHub the same thing again -- and the retry that succeeded
        # finalized the merged plan as the work. So the failure ends the tick
        # where it happened, writing nothing, and the next one asks again.
        gh, issue = _support._seed_accepted_handoff(
            _FLAKY_FETCH_ISSUE_NUMBER, head_sha=_support.PLAN_COMMIT,
        )
        flaky_fetch = _FetchFailsOnce(gh.get_pr)
        writes_before = gh.write_state_calls

        with patch.object(gh, "get_pr", flaky_fetch):
            mocks = self._run_handoff_tick(gh, issue)

        self.assertEqual(flaky_fetch.calls, 1)
        mocks[_stage_support.RUN_AGENT].assert_not_called()
        self.assertNotIn((issue.number, LABEL_DONE), gh.label_history)
        self.assertEqual(gh.write_state_calls, writes_before)
        # The record the next tick asks with is still there to ask with.
        self.assertEqual(
            gh.pinned_data(issue.number)[_stage_support.KEY_PLAN_SHA], _support.PLAN_COMMIT,
        )

    def test_an_unreported_round_outranks_the_merge(self) -> None:
        # The other way a merge reaches an issue this stage may not finalize:
        # the conversation crashed mid-round, so no plan record was ever
        # written, and the `pr_number` the terminal reads is whatever the issue
        # arrived carrying -- a previous cycle's implementation, or an earlier
        # discussion's plan PR. Merged, and read before the crash records are,
        # it closes the issue as `done` and cleans up the branch the plan is
        # sitting on: the artifact goes, its own pull request is orphaned, and
        # the marker is left standing on an issue nothing comes back for.
        for issue_number, marker, recorded in _UNREPORTED_ROUNDS:
            with self.subTest(marker=marker):
                self._assert_refused_over_the_merge(
                    issue_number, marker, recorded,
                )

    def test_a_crash_after_the_base_anchor_hands_over(self) -> None:
        # The merged handoff moves the branch to the base and records where it
        # landed in the write after it, so a tick that dies in between leaves a
        # branch on a tip no record names. Matched only against the anchor and
        # the PR head, the base itself reads as unreviewed work -- and the
        # refusal tells the operator to reset BACKWARDS off the commit the
        # merge produced. A branch carrying nothing beyond base carries nothing
        # of anybody's, and the move is idempotent, so the next tick simply
        # makes it again.
        gh, crashed_issue = _support._seed_published_plan(
            _CRASHED_ANCHOR_ISSUE_NUMBER, head_sha=_support.PLAN_COMMIT,
        )

        mocks = self._run_handoff_tick(
            gh,
            crashed_issue,
            run_agent=_agent(interrupted=True),
            branch_tip_sha=BASE_TIP_SHA,
            head_shas=(BASE_TIP_SHA,) * 3,
            has_new_commits=False,
        )

        self._assert_dev_ran(mocks)
        pinned_data = gh.pinned_data(crashed_issue.number)
        self.assertNotEqual(
            pinned_data[KEY_PARK_REASON], _stage_support.PARK_DISCUSSION_UNSAFE_RELABEL,
        )
        # The handoff completes on the second attempt exactly as it would have
        # on the first: records retired, and the base recorded as the baseline.
        self.assertIsNone(pinned_data[_stage_support.KEY_PLAN_PATH])
        self.assertEqual(pinned_data[_stage_support.KEY_READ_ONLY_BASELINE], BASE_TIP_SHA)

    def _assert_refused_over_the_merge(
        self, issue_number: int, marker: str, recorded,
    ) -> None:
        """The tick holds: nothing runs, nothing merges, the record stands."""
        gh, issue = _stage_support._seed_relabeled_discussion(
            issue_number,
            None,
            **{marker: recorded, _stage_support.KEY_PR_NUMBER: _support.HANDOFF_PR_NUMBER},
        )
        _support._add_plan_pr(gh, issue, head_sha=_support.PLAN_COMMIT, merged=True)

        mocks = self._run_handoff_tick(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            has_new_commits=True,
            branch_tip_sha=_stage_support.HEAD_AFTER_COMMIT,
            head_shas=(_stage_support.HEAD_AFTER_COMMIT,),
        )

        self._assert_nothing_ran(mocks)
        self.assertNotIn((issue_number, LABEL_DONE), gh.label_history)
        pinned_data = gh.pinned_data(issue_number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _stage_support.PARK_DISCUSSION_UNSAFE_RELABEL,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        # The record outlives a merge that had nothing to do with it, because
        # the stage that owns it is still the one that can finish it.
        self.assertEqual(pinned_data[marker], recorded)

class AmendedPlanHandoffTest(unittest.TestCase, _HandoffTickMixin):
    """A plan PR whose head the humans moved before handing the issue over."""

    def test_the_amended_head_is_inherited(self) -> None:
        # The design its reviewers approved is on the remote and the PR is
        # still open; the checkout is still on the commit this orchestrator
        # published. The developer has to build on theirs -- a push from the
        # older tip would take their edit back out -- and the head has to
        # replace the path record being retired, or the next tick reads it as
        # an implementation and finalizes.
        _gh, issue, mocks, pinned = self._run_published_handoff(
            _AMENDED_PLAN_ISSUE_NUMBER,
            head_sha=_support.AMENDED_PLAN_COMMIT,
            merged=False,
            run_agent=_agent(interrupted=True),
        )

        anchored = mocks[_stage_support.ANCHOR_PR_WORKTREE].call_args
        self.assertEqual(anchored.args[1], issue.number)
        self.assertEqual(anchored.kwargs["branch"], _issue_branch(issue.number))
        self.assertEqual(anchored.kwargs["head_sha"], _support.AMENDED_PLAN_COMMIT)
        self.assertEqual(pinned[_stage_support.KEY_PLAN_SHA], _support.AMENDED_PLAN_COMMIT)
        self.assertEqual(pinned[_stage_support.KEY_READ_ONLY_BASELINE], _support.AMENDED_PLAN_COMMIT)

    def test_an_unmoved_head_costs_no_anchor(self) -> None:
        # The ordinary handoff: the PR is still on the commit publication put
        # there, so there is nothing to fetch and nothing to move, and the
        # baseline stays the tip the guard certified.
        _gh, _issue, mocks, pinned = self._run_published_handoff(
            _UNMOVED_PLAN_ISSUE_NUMBER,
            head_sha=_support.PLAN_COMMIT,
            merged=False,
            run_agent=_agent(interrupted=True),
        )

        mocks[_stage_support.ANCHOR_PR_WORKTREE].assert_not_called()
        self.assertEqual(pinned[_stage_support.KEY_READ_ONLY_BASELINE], _support.PLAN_COMMIT)

    def test_a_merged_plan_hands_over_at_base(self) -> None:
        # The design landed, and the checkout is retained on the commit that
        # merged -- which the anchor matches, so nothing would move. But the
        # base carries that plan now along with everything else that has landed
        # since, and the branch the PR was open against may be deleted: left
        # there, the developer builds behind the branch they are building for
        # and base sync cannot catch up, since the handoff's own baseline
        # freezes it until the dev commits. So the move is asked for with no
        # head at all, which is how the anchor is told to use the base.
        _gh, _issue, mocks, pinned = self._run_published_handoff(
            _MERGED_BRANCH_ISSUE_NUMBER,
            head_sha=_support.PLAN_COMMIT,
            run_agent=_agent(interrupted=True),
        )

        anchored = mocks[_stage_support.ANCHOR_PR_WORKTREE].call_args
        self.assertEqual(anchored.kwargs["head_sha"], "")
        self.assertEqual(pinned[_stage_support.KEY_READ_ONLY_BASELINE], BASE_TIP_SHA)

    def test_an_unreachable_head_holds_the_handoff(self) -> None:
        # The reviewed head could not be put on the branch -- a fetch that
        # failed while the branch is still live on the remote. Taking the
        # handoff anyway spawns the developer on the commit its reviewers moved
        # past, and the ordinary push that follows reads THEIR head off the
        # remote as its own lease and overwrites it. So the tick ends: no agent,
        # no push, nothing written, and the plan record still standing for the
        # next tick to try again.
        gh, issue = _support._seed_published_plan(
            _UNREACHED_HEAD_ISSUE_NUMBER, head_sha=_support.AMENDED_PLAN_COMMIT,
        )
        writes_before = gh.write_state_calls

        mocks = self._run_handoff_tick(gh, issue, anchor_pr_head=None)

        self._assert_nothing_ran(mocks)
        self.assertEqual(gh.write_state_calls, writes_before)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[_stage_support.KEY_PLAN_PATH], _support.PLAN_PATH)
        self.assertEqual(pinned_data[_stage_support.KEY_PLAN_SHA], _support.PLAN_COMMIT)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _stage_support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])

    def test_an_unmerged_deleted_branch_holds(self) -> None:
        # The plan PR is still open -- or was closed without merging -- and its
        # branch has been deleted, so its head cannot be fetched and what it
        # carried is nowhere in the base. Handed over at base anyway, the plan
        # records are retired and the implementer starts from a tree the design
        # was never in. So the anchor establishes nothing, and the tick holds
        # with everything the next one needs still standing.
        gh, deleted_issue = _support._seed_published_plan(
            _DELETED_BRANCH_ISSUE_NUMBER,
            head_sha=_support.AMENDED_PLAN_COMMIT,
            merged=False,
        )

        mocks = self._run_handoff_tick(gh, deleted_issue, anchor_pr_head=None)

        self._assert_nothing_ran(mocks)
        pinned_data = gh.pinned_data(deleted_issue.number)
        self.assertEqual(pinned_data[_stage_support.KEY_PLAN_PATH], _support.PLAN_PATH)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _stage_support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )

    def test_an_interrupted_handoff_keeps_the_plan(self) -> None:
        # The first tick accepts the handoff and its dev run is interrupted, so
        # nothing after the handoff's own write is persisted -- no push, no
        # commit, no relabel. The second tick has no path record left, and what
        # stops it reading the humans' amended head as an implementation and
        # closing the issue as `done` is the head the handoff recorded in its
        # place.
        gh, issue, _first, _pinned = self._run_published_handoff(
            _INTERRUPTED_HANDOFF_ISSUE_NUMBER,
            head_sha=_support.AMENDED_PLAN_COMMIT,
            run_agent=_agent(interrupted=True),
        )

        mocks = self._run_handoff_tick(gh, issue)

        mocks[_stage_support.RUN_AGENT].assert_called_once()
        self.assertNotIn((issue.number, LABEL_DONE), gh.label_history)

    def test_an_unreadable_plan_pr_defers_the_handoff(self) -> None:
        # What that PR carries decides both what the developer inherits and
        # what replaces the path record, so a read that failed has nothing to
        # decide with. The tick ends where it happened, writing nothing, and
        # the park it arrived with is still there for the next one to answer.
        gh, issue = _support._seed_published_plan(
            _UNREADABLE_PR_ISSUE_NUMBER, head_sha=_support.AMENDED_PLAN_COMMIT,
        )
        writes_before = gh.write_state_calls

        with patch.object(gh, "get_pr", side_effect=RuntimeError(_FETCH_FAILURE)):
            mocks = self._run_handoff_tick(gh, issue)

        mocks[_stage_support.RUN_AGENT].assert_not_called()
        mocks[_stage_support.ANCHOR_PR_WORKTREE].assert_not_called()
        self.assertEqual(gh.write_state_calls, writes_before)
        self.assertEqual(
            gh.pinned_data(issue.number)[_stage_support.KEY_PLAN_PATH], _support.PLAN_PATH,
        )


if __name__ == "__main__":
    unittest.main()
