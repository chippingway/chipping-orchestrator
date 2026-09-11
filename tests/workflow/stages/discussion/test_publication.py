# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one thing this stage publishes, and everything it refuses to.

Publication is decided by the artifact rather than by the conversation: the
orchestrator cannot check that a human confirmed anything, so what it checks is
that the branch is the plan file and nothing besides. That makes the refusals
the load-bearing half -- a missing plan, a second one, a code change riding
along, or edits left loose beside the commit -- and each of them has to end
with the branch unpushed, nothing recorded, and the worktree exactly as the
round left it.

What a valid artifact earns is the plan on a PR and the conversation over. The
records that publication leaves are the handoff: the plan path and PR number
the gate reads to stop opening rounds, the branch a later checkout is restored
from, and the anchor moved onto the published tip so the relabel that has this
built is not refused for the commit this stage just published. The crash
windows around all of that are pinned beside this in
`test_publication_recovery.py`.
"""

from __future__ import annotations

import unittest

from tests.workflow.fixtures import (
    _TEST_SPEC,
    BASE_TIP_SHA,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    LABEL_IMPLEMENTING,
    TEST_BASE_BRANCH,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    _reply,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_PUBLISH_ISSUE_NUMBER = 1200
_INVALID_ISSUE_NUMBER = 1210
_DETACHED_RECOVERY_ISSUE_NUMBER = 1211
_PUSH_FAILED_ISSUE_NUMBER = 1220
_SESSIONLESS_ISSUE_NUMBER = 1230
_PUBLISHED_ISSUE_NUMBER = 1250
_INHERITED_PR_ISSUE_NUMBER = 1251

_PLAN_SUBJECT = "docs: write down the sink schema decision"
_CODE_PATH = "orchestrator/observability/analytics/sink.py"
_OTHER_PLAN = "plans/issue-4.md"
_INHERITED_PR_NUMBER = 4242
_EVENT_PR_OPENED = "pr_opened"
_STAGE_DISCUSSION = "discussion"
_CONFIRMED = "confirmed -- writing it up"
_REVISION = "revision"
_UNASKED_ROUND = "a round nobody asked for"
# The run option each refusal case varies, named once so the cases below
# read as the shapes they are rather than as repeated keyword spelling.
_COMMITTED = "committed_paths"


class _PublishedPlanCase(unittest.TestCase, _DiscussionWorkflowMixin):
    """One round that committed the agreed plan, published once per test.

    The publication runs in `setUp` because every assertion in the two classes
    below is about the same one: what was pushed, what was opened, what the
    humans are told, what is recorded, and what is deliberately not.
    """

    def setUp(self) -> None:
        gh, issue = _support._seed_discussion(_PUBLISH_ISSUE_NUMBER)
        self.gh = gh
        self.issue = issue
        self.branch = _support._issue_branch(issue.number)
        self.mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            first_commit_subject=_PLAN_SUBJECT,
        )


class DiscussionPlanPublicationTest(_PublishedPlanCase):
    """What the branch and the PR look like once the plan is out."""

    def test_the_plan_branch_is_pushed_and_opened(self) -> None:
        push_call = self.mocks[_support.PUSH_BRANCH].call_args
        self.mocks[_support.PUSH_BRANCH].assert_called_once()
        self.assertEqual(
            (push_call.args[0], push_call.args[2]), (_TEST_SPEC, self.branch),
        )
        # The commit that was validated is the commit that is published. The
        # reading and the push are separate git invocations, so a branch that
        # moves between them would otherwise put work no check ever saw on the
        # PR while the records named the one that passed.
        self.assertEqual(push_call.kwargs.get(_REVISION), _support.HEAD_AFTER_COMMIT)
        self.assertEqual(len(self.gh.opened_prs), 1)
        plan_pr = self.gh.opened_prs[0]
        self.assertEqual(
            (plan_pr.head_branch, plan_pr.base_branch, plan_pr.title),
            (self.branch, TEST_BASE_BRANCH, _PLAN_SUBJECT),
        )

    def test_one_commit_is_checked_and_published(self) -> None:
        # The tip is read once and named to every check that follows, so what
        # was validated and what was pushed cannot be two different commits.
        # Asked of `HEAD`, each `git` invocation would answer for whatever the
        # branch was on by the time it ran.
        diff_call = self.mocks[_support.COMMITTED_PATHS].call_args
        tree_call = self.mocks[_support.REVISION_CONTAINS_PATH].call_args
        push_call = self.mocks[_support.PUSH_BRANCH].call_args

        self.assertEqual(
            {
                diff_call.args[-1],
                tree_call.args[1],
                push_call.kwargs.get(_REVISION),
            },
            {_support.HEAD_AFTER_COMMIT},
        )

    def test_the_label_stays_and_the_worktree_stands(self) -> None:
        # The stage publishes and stops: no relabel to validating,
        # documenting, or in_review, and nothing tears the checkout down.
        self.assertEqual(self.gh.label_history, [])
        self.assert_worktree_preserved(self.mocks)


class DiscussionPlanHandoffTest(_PublishedPlanCase):
    """What the publication tells the humans and records for the next tick."""

    def test_the_pr_body_names_the_session(self) -> None:
        issue_number = self.issue.number
        body = self.gh.opened_prs[0].body
        self.assertIn(f"Plan for #{issue_number}", body)
        # Which conversation produced the plan, so a reviewer can find the
        # transcript behind it.
        self.assertIn(f"{_support.SPEC_BACKEND} session `{_support.DISCUSSION_SESSION}`", body)
        self.assertIn(self.plan_path(self.issue.number), body)

    def test_the_pr_body_says_what_deciding_it_does(self) -> None:
        # Neither button on this PR does what its diff suggests: merging
        # agrees the design and finishes the issue, and building it is a
        # relabel made first. The body is the only thing that says so to the
        # person about to press one.
        issue_number = self.issue.number
        body = self.gh.opened_prs[0].body
        self.assertIn(f"finishes #{issue_number} as `done`", body)
        self.assertIn("`rejected`", body)
        self.assertIn(str(LABEL_IMPLEMENTING), body)

    def test_the_pr_body_closes_nothing(self) -> None:
        # What a merge meant is the stage's own terminal to record, and the
        # keyword outlives the label: a relabel hands the developer this very
        # PR, where a closing keyword would let a merge of the plan alone
        # close the issue as finished work.
        body = self.gh.opened_prs[0].body
        self.assertNotIn("Resolves", body)
        self.assertNotIn("Closes #", body)

    def test_the_handoff_is_recorded(self) -> None:
        pinned_data = self.gh.pinned_data(self.issue.number)
        self.assertEqual(
            (
                pinned_data[_support.KEY_PLAN_PATH],
                pinned_data[_support.KEY_BRANCH],
                pinned_data[_support.KEY_PR_NUMBER],
                pinned_data[KEY_PARK_REASON],
            ),
            (
                self.plan_path(self.issue.number),
                self.branch,
                self.gh.opened_prs[0].number,
                _support.PARK_DISCUSSION_PLAN_PUBLISHED,
            ),
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        # The commit that PR carries is recorded beside its number, so the
        # implementing stage can ask GitHub whether the PR it inherits is
        # still that plan rather than trusting a record to be cleared.
        self.assertEqual(pinned_data[_support.KEY_PLAN_SHA], _support.HEAD_AFTER_COMMIT)
        # The marker that made the publication recoverable is spent by the
        # records that answer it.
        self.assertIsNone(pinned_data[_support.KEY_PUBLISHING_SHA])

    def test_the_anchor_moves_onto_the_published_tip(self) -> None:
        # Left at the tip the round opened on, the implementing relabel guard
        # would read the published commit as work nobody vouched for and tell
        # an operator to reset away the plan this PR is open against.
        pinned_data = self.gh.pinned_data(self.issue.number)
        self.assertEqual(
            (pinned_data[_support.KEY_ROUND_SHA], pinned_data[_support.KEY_ROUND_BRANCH]),
            (_support.HEAD_AFTER_COMMIT, self.branch),
        )

    def test_the_comment_says_what_to_do_next(self) -> None:
        pr_number = self.gh.opened_prs[0].number
        self.assertEqual(len(self.gh.posted_comments), 1)
        _, body = self.gh.posted_comments[0]
        self.assertIn(f"#{pr_number}", body)
        self.assertIn(self.plan_path(self.issue.number), body)
        self.assertIn(str(LABEL_IMPLEMENTING), body)

    def test_opening_the_pr_emits_a_stage_event(self) -> None:
        opened = [
            event for event in self.gh.recorded_events
            if event["event"] == _EVENT_PR_OPENED
        ]
        self.assertEqual(len(opened), 1)
        self.assertEqual(
            (
                opened[0]["stage"],
                opened[0]["pr_number"],
                opened[0]["branch"],
                opened[0]["sha"],
            ),
            (
                _STAGE_DISCUSSION,
                self.gh.opened_prs[0].number,
                self.branch,
                _support.HEAD_AFTER_COMMIT,
            ),
        )


class DiscussionUnpublishableCommitTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """Every shape of committed work that is not the agreed plan alone."""

    def test_each_invalid_artifact_is_refused(self) -> None:
        plan_path = self.plan_path(_INVALID_ISSUE_NUMBER)
        for case, overrides in (
            ("code beside the plan", {_COMMITTED: (plan_path, _CODE_PATH)}),
            ("a second plan", {_COMMITTED: (plan_path, _OTHER_PLAN)}),
            ("no plan at all", {_COMMITTED: (_CODE_PATH,)}),
            ("nothing committed", {_COMMITTED: ()}),
            ("a dirty tree", {"dirty_files": _support._dirty_files(2)}),
            # The diff cannot tell these two from a plan being written: a
            # deletion changes exactly the same path, and an unreadable tree
            # names no paths at all -- so each is asked of its own probe.
            ("a deleted plan", {"head_contains_path": False}),
            ("an unreadable worktree", {"tree_readable": False}),
            # And the one no reading of the COMMIT can catch: made on a
            # detached HEAD, it is the plan and nothing else, but the branch
            # the push would send it to is not on it.
            ("a detached HEAD", {"head_on_branch": False}),
        ):
            with self.subTest(case=case):
                self._assert_refused(**overrides)

    def test_a_detached_recovery_is_refused(self) -> None:
        # The other tick that can find such a commit: a round that never
        # reported, whose anchor a later tick compares the tree against. It
        # publishes exactly what the round would have -- so if the disposition
        # refuses a commit made off the branch, this has to as well, or the
        # crash window becomes the way one gets published.
        gh, issue = _support._seed_discussion(_DETACHED_RECOVERY_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_ROUND_BRANCH: _support._issue_branch(issue.number),
                _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_ROUND_OPEN: True,
                _support.KEY_BASE_SHA: BASE_TIP_SHA,
                _support.KEY_DISCUSSION_SESSION_ID: _support.DISCUSSION_SESSION,
            },
        )

        mocks = self._run_discussion_in_temp_checkout(
            gh,
            issue,
            run_agent=_agent(last_message=_UNASKED_ROUND),
            head_shas=(_support.HEAD_AFTER_COMMIT,) * 2,
            **{_COMMITTED: (self.plan_path(issue.number),)},
            head_on_branch=False,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, mocks)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)
        # The operator is told which ref HEAD is on, since every other fact the
        # refusal states reads exactly as a plan written the way it was asked.
        self.assertIn(
            f"HEAD is not `{_support._issue_branch(issue.number)}`",
            gh.posted_comments[0][1],
        )

    def _assert_refused(self, **run_options) -> None:
        # One client per case: each seeds, runs, and asserts on its own issue,
        # so a record leaked by one cannot make the next pass.
        gh, issue = _support._seed_discussion(_INVALID_ISSUE_NUMBER)
        run_options.setdefault(_COMMITTED, (self.plan_path(issue.number),))

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            **run_options,
        )

        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        # Nothing records a publication that did not happen, so the next tick
        # still runs the conversation rather than holding on a PR.
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)
        self.assertNotIn(_support.KEY_PR_NUMBER, pinned_data)
        # The reset target is the tip the round opened on, which is what keeps
        # commits the branch arrived with out of the remedy.
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)


class DiscussionUnattributedPlanTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """A plan whose round left no session to publish it under."""

    def test_a_sessionless_round_publishes_nothing(self) -> None:
        # The artifact passes every check the branch can answer; what it has
        # no answer for is which conversation produced it, which is the one
        # thing the PR body exists to say. A backend that hands back no id
        # leaves exactly that, and "session `?`" is not an answer a reviewer
        # can follow back to the discussion that agreed the design.
        gh, issue = _support._seed_discussion(_SESSIONLESS_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(session_id="", last_message=_CONFIRMED),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )

        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_UNATTRIBUTED,
        )
        # Nothing is recorded, so the tick after this one still has a
        # conversation to run rather than a PR to hold on.
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)
        self.assertNotIn(_support.KEY_PR_NUMBER, pinned_data)


class DiscussionPushFailureTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A valid plan the branch could not be pushed with is kept, not spent."""

    def test_a_failed_push_opens_nothing(self) -> None:
        gh, issue = _support._seed_discussion(_PUSH_FAILED_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            push_branch=False,
        )

        mocks[_support.PUSH_BRANCH].assert_called_once()
        # No PR, and nothing recorded pointing at one: a publication that
        # failed at the push must not leave a handoff the gate would read.
        self.assertEqual(gh.opened_prs, [])
        self.assertEqual(gh.label_history, [])
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PUSH_FAILED,
        )
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)
        self.assertNotIn(_support.KEY_PR_NUMBER, pinned_data)
        # The commit stays where it is, so the message offers the retry first
        # and the reset that would discard the agreed plan second.
        _, body = gh.posted_comments[0]
        self.assertIn(self.plan_path(issue.number), body)
        self.assertIn("reply here to retry", body)
        self.assert_worktree_preserved(mocks)


class DiscussionPublishedPlanHoldTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """Once the plan is on a PR, the stage stops acting on the issue."""

    def test_a_later_tick_runs_nothing(self) -> None:
        gh, issue = _support._seed_discussion(_PUBLISHED_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_PLAN_PATH: self.plan_path(issue.number),
                _support.KEY_PR_NUMBER: _INHERITED_PR_NUMBER,
                _support.KEY_BRANCH: _support._issue_branch(issue.number),
                KEY_AWAITING_HUMAN: True,
                KEY_PARK_REASON: _support.PARK_DISCUSSION_PLAN_PUBLISHED,
            },
        )
        issue.comments.append(_reply(DISCUSSION_REPLY))
        writes_before = gh.write_state_calls

        mocks = self._run_discussion(
            gh, issue, run_agent=_agent(last_message=_UNASKED_ROUND),
        )

        # Not even a human's reply reopens it: the design is being reviewed on
        # the PR now, and the way out is a relabel.
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.write_state_calls, writes_before)

    def test_an_inherited_pr_number_opens_a_round(self) -> None:
        # An issue relabeled here from a PR stage arrives carrying its dev's
        # `pr_number`. Reading that alone as a published plan would freeze a
        # discussion that has not had a single round yet.
        gh, issue = _support._seed_discussion(_INHERITED_PR_ISSUE_NUMBER)
        gh.seed_state(issue.number, **{_support.KEY_PR_NUMBER: _INHERITED_PR_NUMBER})

        mocks = self._run_discussion(
            gh, issue, run_agent=_agent(last_message="an opening analysis"),
        )

        mocks[_support.RUN_AGENT].assert_called_once()


if __name__ == "__main__":
    unittest.main()
