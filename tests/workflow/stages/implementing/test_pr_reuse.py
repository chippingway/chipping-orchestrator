# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing pr reuse behavior."""

from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import evidence as _worktree_evidence, naming as _naming
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.implementing import handler as _implementing
from tests.workflow.stages.implementing import pr_test_support as support

BRANCHLESS_ISSUE = support.BRANCHLESS_ISSUE
BRANCHLESS_REPLY_ID = support.BRANCHLESS_REPLY_ID
BRANCHLESS_WATERMARK = support.BRANCHLESS_WATERMARK
DEV_SESSION = support.DEV_SESSION
DONE_MESSAGE = support.DONE_MESSAGE
EXISTING_PR_NUMBER = support.EXISTING_PR_NUMBER
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakePR = support.FakePR
FakeUser = support.FakeUser
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_agent = support._agent
make_issue = support.make_issue
posted_comment_contains = support.posted_comment_contains

# The flat pre-namespacing spelling of issue 4's branch, which no live work
# stands on.
FLAT_BRANCH = "orchestrator/issue-4"

# The current-layout name of issue 4's branch, which an open pull request stands on.
CURRENT_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-4"

# The push seam, which a publication refused before it pushes leaves uncalled.
_PUSH = "_push_branch"

# Every seam a tick refused on its branch must leave uncalled: the launch, both
# checkout creators, and the push.
REFUSED_SEAMS = ("run_agent", "_ensure_worktree", "_ensure_pr_worktree", _PUSH)

# The commit a publication records it owes a push, in the write ahead of that push.
_INTENT = "late_approved_sha"


class OnCommitsPRReuseTest(unittest.TestCase, _PatchedWorkflowMixin):
    def test_existing_open_pr_is_reused(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(4, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        existing = FakePR(
            number=EXISTING_PR_NUMBER,
            head_branch="orchestrator/chippingway__chipping-orchestrator/issue-4",
            body=support._named_description(4, DEV_SESSION),
        )
        gh.add_pr(existing)
        gh.existing_open_pr["orchestrator/chippingway__chipping-orchestrator/issue-4"] = existing

        self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

        # No new PR opened, no sparkles comment posted.
        self.assertEqual(gh.opened_prs, [])
        self.assertFalse(
            posted_comment_contains(gh, ":sparkles: PR opened"),
        )
        self.assertIn((4, "workflow:validating"), gh.label_history)
        self.assertEqual(gh.pinned_data(4).get("pr_number"), EXISTING_PR_NUMBER)

    def test_a_foreign_checkout_is_never_published(self) -> None:
        # The publication proves the checkout it pushes from before it
        # records an intent or pushes anything. A tree at the issue's path
        # that is not the issue's own -- here one the ownership read refutes,
        # beside an open pull request on the current branch -- is refused
        # there: no push, no pull request, no relabel, whatever the run left
        # in it.
        gh = FakeGitHubClient()
        issue = make_issue(4, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        existing = FakePR(
            number=EXISTING_PR_NUMBER, head_branch=CURRENT_BRANCH,
            body=support._named_description(4, DEV_SESSION),
        )
        gh.add_pr(existing)
        gh.existing_open_pr[CURRENT_BRANCH] = existing

        mocks = self._run(
            partial(
                self.assertRaises, _naming.BranchRefused,
                _implementing._handle_implementing, gh, support._TEST_SPEC, issue,
            ),
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
            checkout_identity=ProbeAnswer.REFUTED,
        )

        mocks["_push_branch"].assert_not_called()
        self.assertEqual((gh.opened_prs, gh.label_history), ([], []))

    def test_a_flat_pinned_branch_is_refused(self) -> None:
        # A record pinning the flat `orchestrator/issue-<n>` names no branch
        # live work may stand on, even with an open PR whose head is that
        # ref. The tick refuses before it checks out, launches, looks up or
        # opens a PR, pushes, writes, or relabels anything, leaving the
        # branch and its PR for a human. The drift baseline is seeded as a
        # tick that saw the body before would have left it, so this one has
        # no first-sight snapshot to write either.
        gh = FakeGitHubClient()
        issue = make_issue(4, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.existing_open_pr[FLAT_BRANCH] = FakePR(
            number=EXISTING_PR_NUMBER, head_branch=FLAT_BRANCH,
            body=support._named_description(4, DEV_SESSION),
        )
        gh.add_pr(gh.existing_open_pr[FLAT_BRANCH])
        gh.seed_state(
            4,
            branch=FLAT_BRANCH,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        writes_before = gh.write_state_calls

        mocks = self._run(
            partial(
                self.assertRaises,
                _naming.BranchRefused,
                _implementing._handle_implementing,
                gh,
                support._TEST_SPEC,
                issue,
            ),
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

        self.assertEqual(
            {seam: mocks[seam].call_count for seam in REFUSED_SEAMS},
            dict.fromkeys(REFUSED_SEAMS, 0),
        )
        self.assertEqual(
            (gh.opened_prs, gh.posted_comments, gh.label_history, gh.write_state_calls),
            ([], [], [], writes_before),
        )
        self.assertEqual(gh.pinned_data(4).get("branch"), FLAT_BRANCH)

    def test_persists_branch_for_branchless_resume(self) -> None:
        # A state that lacks `branch` going into `_on_commits` (the
        # awaiting-human resume path skips the fresh-spawn
        # `state.set("branch", ...)` block) must still come out with the
        # pushed branch persisted beside `pr_number`. A `pr_number` with no
        # `branch` is a record the next tick's `_resolve_branch_name`
        # refuses, which would strand validation / base-sync / cleanup of
        # the live PR on the slug-namespaced ref this push just published.
        gh = FakeGitHubClient()
        issue = make_issue(BRANCHLESS_ISSUE, label=LABEL_IMPLEMENTING)
        # Pending human comment that triggers the awaiting-human resume.
        reply = FakeComment(
            id=BRANCHLESS_REPLY_ID,
            body="please retry",
            user=FakeUser("alice"),
        )
        issue.comments.append(reply)
        gh.add_issue(issue)
        # State carries `awaiting_human=True` and a dev session id but
        # NO `branch` -- the pre-existing shape for a relabel-from-
        # question or any park whose pre-spawn site never persisted
        # `branch`. `pr_number` is also absent because no PR exists
        # yet; the resume produces the first commit.
        gh.seed_state(
            BRANCHLESS_ISSUE,
            awaiting_human=True,
            dev_agent="claude",
            dev_session_id="dev-sess",
            last_action_comment_id=BRANCHLESS_WATERMARK,
        )

        self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id="dev-sess", last_message=DONE_MESSAGE),
            # Resume path: no recovered-worktree shortcut, post-agent
            # check sees the new commit.
            has_new_commits=[True],
            dirty_files=(),
            push_branch=True,
        )

        # A PR was opened and persisted to state.
        self.assertEqual(len(gh.opened_prs), 1)
        pinned_data = gh.pinned_data(BRANCHLESS_ISSUE)
        self.assertEqual(pinned_data.get("pr_number"), gh.opened_prs[0].number)
        # The branch was persisted alongside `pr_number`, so the next
        # tick's `_resolve_branch_name` answers the slug-namespaced form.
        self.assertEqual(
            pinned_data.get("branch"),
            "orchestrator/chippingway__chipping-orchestrator/issue-11",
        )


class SwitchedPublicationTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A publication over the issue's own checkout, which the ownership read refutes partway through.

    The publication proves the checkout before its intent, and again last
    before the push and before the pull request is opened: the intent's write,
    the barrier's readings, and the push itself all come after the first
    proof, and a tree switched onto the flat branch at the published commit
    passes every reading of that commit and tree. The size gate is off, so
    the commit the push is owed is the publication's own write rather than
    an approval the gate recorded ahead of the first proof.
    """

    def setUp(self) -> None:
        self.enterContext(patch.object(config, "DECOMPOSE", False))
        self.gh = FakeGitHubClient()
        self.issue = make_issue(4, label=LABEL_IMPLEMENTING)
        self.gh.add_issue(self.issue)
        existing = FakePR(
            number=EXISTING_PR_NUMBER, head_branch=CURRENT_BRANCH,
            body=support._named_description(4, DEV_SESSION),
        )
        self.gh.add_pr(existing)
        self.gh.existing_open_pr[CURRENT_BRANCH] = existing
        self._write = self.gh.write_pinned_state

    def test_a_switch_at_the_intent_pushes_nothing(self) -> None:
        with patch.object(self.gh, "write_pinned_state", side_effect=self._switched_at_the_intent):
            mocks = self._publishes(push_branch=True)

        mocks[_PUSH].assert_not_called()
        self.assertEqual((self.gh.opened_prs, self.gh.label_history), ([], []))
        self.assertTrue(self.gh.pinned_data(4).get(_INTENT))

    def test_a_switch_mid_push_opens_nothing(self) -> None:
        mocks = self._publishes(push_branch=self._switched_push)

        self.assertEqual(mocks[_PUSH].call_count, 1)
        self.assertEqual((self.gh.opened_prs, self.gh.label_history), ([], []))
        self.assertTrue(self.gh.pinned_data(4).get(_INTENT))

    def _publishes(self, *, push_branch) -> dict:
        """One implementing tick whose run committed on a clean tree, refused partway; the seams it used."""
        return self._run(
            partial(
                self.assertRaises, _naming.BranchRefused,
                _implementing._handle_implementing, self.gh, support._TEST_SPEC, self.issue,
            ),
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=push_branch,
        )

    def _switched_at_the_intent(self, issue, state, *args, **kwargs):
        """Write the record, refuting the checkout from the write that records the commit it owes a push."""
        if state.get(_INTENT):
            _worktree_evidence._checkout_identity.return_value = ProbeAnswer.REFUTED
        return self._write(issue, state, *args, **kwargs)

    def _switched_push(self, *_args, **_kwargs) -> bool:
        """A push that lands while the checkout is switched under it."""
        _worktree_evidence._checkout_identity.return_value = ProbeAnswer.REFUTED
        return True
