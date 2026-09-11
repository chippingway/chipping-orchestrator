# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The tick that runs once the read-only relabel guard has said yes.

Accepting the relabel hands this stage a branch it did not build: a discussion
may be held on the branch its PR is open against, so the dev run starts on
commits that are already ahead of base. Everything here is a consequence of
that one fact -- what the checkout is restored from, what counts as work this
run produced, and how durable the acceptance has to be before the agent is
ever spawned.

The guard's own screening decisions are covered in `test_read_only_relabel.py`.
"""

from __future__ import annotations

import unittest

from tests.support.fakes import FakePR
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.implementing import read_only_relabel_test_support as _support
from tests.workflow.stages.implementing.read_only_relabel_test_support import _ReadOnlyRelabelMixin

# Both ends of the comparison a disposition attributes work by, each seeded
# unread in turn. The third reading is the disposition's own; the second is
# the tip the spawn path records as this run's starting point.
_UNREADABLE_ENDS = (
    (
        "the tip the run started at",
        (_support.HEAD_BEFORE_ROUND, "", _support.HEAD_AFTER_COMMIT),
    ),
    (
        "the tip the run ended on",
        (_support.HEAD_BEFORE_ROUND, _support.HEAD_BEFORE_ROUND, ""),
    ),
)

_ANSWERED_ISSUE_NUMBER = 995
_INTERRUPTED_ISSUE_NUMBER = 996
_PR_HANDOFF_ISSUE_NUMBER = 997
_PUBLISHED_ISSUE_NUMBER = 998
_UNREADABLE_ISSUE_NUMBER = 999
_HANDOFF_PR_NUMBER = 5150
_IMPLEMENTED = "implemented"


class ReadOnlyHandoffTest(
    unittest.TestCase, _PatchedWorkflowMixin, _ReadOnlyRelabelMixin,
):

    def test_an_answer_over_inherited_commits_parks(self) -> None:
        # The dev ran on the certified branch and came back with a question
        # instead of an implementation, leaving HEAD exactly where it found
        # it. The commits under it are the ones the issue arrived with, so
        # ahead-of-base is still true and reading only that would push them,
        # open a PR over them, and route the issue to review -- publishing the
        # design's predecessor as the answer to the question just asked.
        gh, issue = _support._seed_relabeled_discussion(
            _ANSWERED_ISSUE_NUMBER, _support.PARK_DISCUSSION_RESPONSE,
        )

        mocks = self._run_implementing_on_worktree(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            run_agent=_agent(session_id=_support.DEV_SESSION, last_message="which store?"),
            has_new_commits=True,
            branch_tip_sha=_support.HEAD_BEFORE_ROUND,
            head_shas=(_support.HEAD_BEFORE_ROUND,) * 3,
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        mocks[_support.PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        self.assertEqual(gh.label_history, [])
        pinned_data = gh.pinned_data(issue.number)
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        self.assertIn("which store?", gh.posted_comments[-1][1])

    def test_an_unread_end_over_inherited_work_parks(self) -> None:
        # The same shape one probe worse, and the probe is what decides it.
        # Both dispositions tell a run's own work from what the branch already
        # carried by COMPARING the tip it started at with the tip it ended on,
        # and `_head_sha` reports its own failure as "" -- so an end nobody
        # read differs from every commit there is. Read as a difference, the
        # inherited commits are published as this run's, which is exactly what
        # the certified branch makes reachable: ahead-of-base is true of it
        # before the agent ever starts.
        for unread, heads in _UNREADABLE_ENDS:
            with self.subTest(unread=unread):
                gh, issue = _support._seed_relabeled_discussion(
                    _UNREADABLE_ISSUE_NUMBER, _support.PARK_DISCUSSION_RESPONSE,
                )

                mocks = self._run_implementing_on_worktree(
                    gh,
                    issue,
                    unpushed_branch=_issue_branch(issue.number),
                    run_agent=_agent(
                        session_id=_support.DEV_SESSION, last_message=_IMPLEMENTED,
                    ),
                    has_new_commits=True,
                    branch_tip_sha=_support.HEAD_BEFORE_ROUND,
                    head_shas=heads,
                )

                mocks[_support.RUN_AGENT].assert_called_once()
                mocks[_support.PUSH_BRANCH].assert_not_called()
                mocks[_support.COUNT_ADDED_LINES].assert_not_called()
                self.assertEqual(gh.opened_prs, [])
                self.assertEqual(gh.label_history, [])
                self.assertTrue(
                    gh.pinned_data(issue.number)[KEY_AWAITING_HUMAN],
                )

    def test_an_interrupted_dev_keeps_the_handoff(self) -> None:
        # The relabel was accepted and the dev committed, then the run was cut
        # short -- a shutdown sweep here, a mid-run pause in the sibling case.
        # Those endings drop every staged mutation by design, so the handoff
        # has to already be durable: read back, a surviving park plus anchor
        # would meet the dev's own commit sitting past that anchor and convict
        # it as a read-only violation, with a reset that discards the work.
        gh, issue = _support._seed_relabeled_discussion(
            _INTERRUPTED_ISSUE_NUMBER, _support.PARK_DISCUSSION_RESPONSE,
        )

        mocks = self._run_implementing_on_worktree(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            run_agent=_agent(interrupted=True, last_message="cut short"),
            has_new_commits=True,
            branch_tip_sha=_support.HEAD_BEFORE_ROUND,
            head_shas=(_support.HEAD_BEFORE_ROUND, _support.HEAD_BEFORE_ROUND, _support.HEAD_AFTER_COMMIT),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        # Nothing published: the interrupted result is not trustworthy.
        mocks[_support.PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        # But the accepted handoff survived the dropped tick.
        pinned_data = gh.pinned_data(issue.number)
        self.assertFalse(pinned_data.get(KEY_AWAITING_HUMAN))
        self.assertIsNone(pinned_data.get(KEY_PARK_REASON))
        self.assertIsNone(pinned_data.get(_support.KEY_ROUND_SHA))
        self.assertEqual(
            pinned_data.get(_support.KEY_READ_ONLY_BASELINE), _support.HEAD_BEFORE_ROUND,
        )

    def test_publishing_retires_the_baseline(self) -> None:
        # The baseline freezes this branch out of the base refresh while it
        # stands, so it has to end with the stage that needs it. Once the dev
        # has committed there is work to publish either way, and a baseline
        # left in pinned state would keep the branch frozen through review and
        # beyond -- long after anything reads it.
        gh, issue = _support._seed_relabeled_discussion(
            _PUBLISHED_ISSUE_NUMBER, _support.PARK_DISCUSSION_RESPONSE,
        )

        mocks = self._run_implementing_on_worktree(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            run_agent=_agent(session_id=_support.DEV_SESSION, last_message=_IMPLEMENTED),
            has_new_commits=True,
            branch_tip_sha=_support.HEAD_BEFORE_ROUND,
            head_shas=(_support.HEAD_BEFORE_ROUND, _support.HEAD_BEFORE_ROUND, _support.HEAD_AFTER_COMMIT),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assertEqual(len(gh.opened_prs), 1)
        self.assertIsNone(
            gh.pinned_data(issue.number).get(_support.KEY_READ_ONLY_BASELINE),
        )

    def test_a_pr_backed_handoff_restores_from_the_pr(self) -> None:
        # The discussion's preserved worktree and local ref were both removed
        # between ticks, so the guard sees no hazard and the dev run has to
        # rebuild the checkout. Rebuilding a PR-backed branch from
        # `<remote>/<base>` would hand the dev an empty tree, and publication
        # would then force-push that over the commits the PR is open against.
        gh, issue = _support._seed_relabeled_discussion(
            _PR_HANDOFF_ISSUE_NUMBER,
            _support.PARK_DISCUSSION_RESPONSE,
            branch=_issue_branch(_PR_HANDOFF_ISSUE_NUMBER),
            pr_number=_HANDOFF_PR_NUMBER,
        )
        gh.add_pr(FakePR(
            number=_HANDOFF_PR_NUMBER,
            head_branch=_issue_branch(issue.number),
        ))

        mocks = self._run_implementing_on_worktree(
            gh,
            issue,
            unpushed_branch=None,
            run_agent=_agent(session_id=_support.DEV_SESSION, last_message=_IMPLEMENTED),
            has_new_commits=[False, True],
            branch_tip_sha=_support.HEAD_BEFORE_ROUND,
            head_shas=(_support.HEAD_BEFORE_ROUND, _support.HEAD_BEFORE_ROUND, _support.HEAD_AFTER_COMMIT),
        )

        mocks[_support.ENSURE_PR_WORKTREE].assert_called_once_with(
            _TEST_SPEC, issue.number, branch=_issue_branch(issue.number),
        )
        mocks[_support.ENSURE_WORKTREE].assert_not_called()
        mocks[_support.RUN_AGENT].assert_called_once()


if __name__ == "__main__":
    unittest.main()
