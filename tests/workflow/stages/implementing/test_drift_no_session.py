# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing drift no session behavior."""

from __future__ import annotations

import unittest

from tests.workflow.stages.implementing import drift_test_support as support

AWAITING_BODY_DRIFT_ISSUE = support.AWAITING_BODY_DRIFT_ISSUE
EDITED_BODY = support.EDITED_BODY
AWAITING_COMMENT_DRIFT_ISSUE = support.AWAITING_COMMENT_DRIFT_ISSUE
AWAITING_HUMAN = support.AWAITING_HUMAN
FRESH_SESSION = support.FRESH_SESSION
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakeUser = support.FakeUser
HUMAN_COMMENT_ID = support.HUMAN_COMMENT_ID
IMPLEMENTED_MESSAGE = support.IMPLEMENTED_MESSAGE
IMPLEMENTER_PROMPT_FRAGMENT = support.IMPLEMENTER_PROMPT_FRAGMENT
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
LABEL_VALIDATING = support.LABEL_VALIDATING
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
NO_SESSION_FRESH_ISSUE = support.NO_SESSION_FRESH_ISSUE
NO_SESSION_RECOVERED_ISSUE = support.NO_SESSION_RECOVERED_ISSUE
PARK_REASON = support.PARK_REASON
PICKUP_COMMENT_ID = support.PICKUP_COMMENT_ID
RUN_AGENT = support.RUN_AGENT
STALE_CONTENT_HASH = support.STALE_CONTENT_HASH
STALE_RECOVERED_WORK = support.STALE_RECOVERED_WORK
TRUSTED_AUTHOR = support.TRUSTED_AUTHOR
USER_CONTENT_HASH = support.USER_CONTENT_HASH
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_agent = support._agent
_issue_branch = support._issue_branch
make_issue = support.make_issue

# The park an unrelated refusal is already standing on when the edit lands,
# and the words a human answers the stale-work refusal with.
AGENT_TIMEOUT_PARK = "agent_timeout"
DECIDED = "discard them and start over"
REFUSAL_WORDS = "never saw the edited requirements"


def _refused_world(**pinned):
    """An issue whose branch carries commits no session on it explains."""
    github = FakeGitHubClient()
    issue = make_issue(
        NO_SESSION_RECOVERED_ISSUE,
        label=LABEL_IMPLEMENTING,
        body=EDITED_BODY,
    )
    github.add_issue(issue)
    # No `dev_session_id` recorded: legacy/recovered state. Pre-seed
    # `user_content_hash` so the drift detection fires (vs. silently
    # initializing the baseline on first encounter).
    github.seed_state(
        NO_SESSION_RECOVERED_ISSUE,
        user_content_hash=STALE_CONTENT_HASH,
        branch=_issue_branch(NO_SESSION_RECOVERED_ISSUE),
        **pinned,
    )
    return github, issue


class NoSessionRecoveredCommitsDriftTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """Reviewer point 1: when implementing drift fires with NO recorded
    dev session AND the worktree carries recovered unpushed commits, the
    handler must refuse to push those commits and open a PR -- no agent
    has seen the edited issue body. Park awaiting human and let the
    operator decide whether to discard the recovered work or accept it."""

    def test_recovered_commits_without_session_park(
        self,
    ) -> None:
        gh, issue = _refused_world()

        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(),
            # Recovered worktree has unpushed commits ahead of base.
            has_new_commits=True,
            push_branch=True,
        )

        # Crucial: must NOT push or open a PR against commits the dev
        # never authored against the edited body.
        mocks["_push_branch"].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        self.assertNotIn((NO_SESSION_RECOVERED_ISSUE, LABEL_VALIDATING), gh.label_history)
        # Parked so the operator can adjudicate.
        state = gh.pinned_data(NO_SESSION_RECOVERED_ISSUE)
        self.assertTrue(state.get(AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn(REFUSAL_WORDS, last_comment)
        # Written down as its own refusal, which is how the next tick tells
        # this sentence from one it still owes.
        self.assertEqual(state.get(PARK_REASON), STALE_RECOVERED_WORK)
        # The refusal read nobody's words to anybody, so the baseline it
        # compares against does not move: the edit is still owed, and the
        # spawn that finally answers it is what records the revision.
        self.assertEqual(state.get(USER_CONTENT_HASH), STALE_CONTENT_HASH)

    def test_the_refusal_is_said_once(self) -> None:
        # The edit stands until the operator deals with the commits, so the
        # refusal is re-decided on every poll. What it may not do is repeat
        # itself: the tick recognizes the park as its own and says nothing.
        gh, issue = _refused_world()
        self._run_implementing(
            gh, issue, run_agent=_agent(), has_new_commits=True, push_branch=True,
        )
        said, wrote = len(gh.posted_comments), gh.write_state_calls

        mocks = self._run_implementing(
            gh, issue, run_agent=_agent(), has_new_commits=True, push_branch=True,
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(len(gh.posted_comments), said)
        self.assertEqual(gh.write_state_calls, wrote)
        self.assertEqual(
            gh.pinned_data(NO_SESSION_RECOVERED_ISSUE).get(USER_CONTENT_HASH),
            STALE_CONTENT_HASH,
        )

    def test_an_unrelated_park_still_hears_it(self) -> None:
        # A park for something else is not this refusal: the commits are news
        # the operator has not been told, and what the issue waits on now is
        # their decision about them, so the refusal supersedes that park.
        gh, issue = _refused_world(
            awaiting_human=True, park_reason=AGENT_TIMEOUT_PARK,
        )

        mocks = self._run_implementing(
            gh, issue, run_agent=_agent(), has_new_commits=True, push_branch=True,
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn(REFUSAL_WORDS, gh.posted_comments[-1][1])
        state = gh.pinned_data(NO_SESSION_RECOVERED_ISSUE)
        self.assertEqual(state.get(PARK_REASON), STALE_RECOVERED_WORK)
        self.assertEqual(state.get(USER_CONTENT_HASH), STALE_CONTENT_HASH)

    def test_a_standing_refusal_hears_a_reply(self) -> None:
        # What the refusal asked for is a human's decision, so the tick that
        # carries one may not end at the refusal: the edit is still an edit
        # every poll, and a road that owned the tick for it would swallow the
        # answer. The reply reaches the park's own resume, and that delivery
        # is what records both the words and the revision.
        gh, issue = _refused_world()
        self._run_implementing(
            gh, issue, run_agent=_agent(), has_new_commits=True, push_branch=True,
        )
        decided = gh.next_reply_id(issue)
        issue.comments.append(
            FakeComment(decided, DECIDED, user=FakeUser(TRUSTED_AUTHOR)),
        )

        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=FRESH_SESSION),
            has_new_commits=True,
            push_branch=True,
            head_shas=["standing", "standing"],
        )

        mocks[RUN_AGENT].assert_called_once()
        self.assertIn(DECIDED, mocks[RUN_AGENT].call_args[0][1])
        state = gh.pinned_data(NO_SESSION_RECOVERED_ISSUE)
        self.assertGreaterEqual(state.get(LAST_ACTION_COMMENT_ID), decided)
        self.assertNotEqual(state.get(USER_CONTENT_HASH), STALE_CONTENT_HASH)

    def test_no_session_or_commits_falls_through(
        self,
    ) -> None:
        # The fall-through path is still correct when there are NO
        # recovered commits: a fresh spawn picks up the new body via
        # `_build_implement_prompt`.
        gh = FakeGitHubClient()
        issue = make_issue(NO_SESSION_FRESH_ISSUE, label=LABEL_IMPLEMENTING, body="new body")
        gh.add_issue(issue)
        gh.seed_state(
            NO_SESSION_FRESH_ISSUE,
            user_content_hash=STALE_CONTENT_HASH,
            pickup_comment_id=PICKUP_COMMENT_ID,
        )

        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message=IMPLEMENTED_MESSAGE,
            ),
            # Three `_has_new_commits` calls: (1) drift-no-session park
            # check returns False -> fall through; (2) recovered-worktree
            # check in the regular path returns False; (3) post-agent
            # check returns True -> push + open PR.
            has_new_commits=[False, False, True],
            push_branch=True,
        )

        # Fresh implement prompt ran (not the drift resume prompt).
        prompt = mocks[RUN_AGENT].call_args[0][1]
        self.assertIn(IMPLEMENTER_PROMPT_FRAGMENT, prompt)
        # PR opened from the fresh spawn.
        self.assertEqual(len(gh.opened_prs), 1)


class AwaitingHumanNoSessionDriftTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """Reviewer point: implementing drift with no recorded `dev_session_id`
    can still be `awaiting_human=True` (manual relabel, drift on a
    freshly-picked-up issue parked before its first spawn, etc.).
    Without the fix:
      * body-edit-only: falls through to `_resume_developer_on_human_reply`,
        finds no new comments, returns -- and the new hash is never
        written, so the drift loops every tick.
      * with new comment: fresh-spawns via `_resume_dev_with_text` with
        ONLY the new-comment text as the prompt, never quoting the
        updated body that triggered the drift.
    Fix: clear the park flags so the fresh-spawn path below fires with
    the full implement prompt (which quotes `issue.body` and the
    conversation via `_recent_comments_text`)."""

    def test_body_edit_clears_park_and_spawns_fresh(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            AWAITING_BODY_DRIFT_ISSUE,
            label=LABEL_IMPLEMENTING,
            body=EDITED_BODY,
        )
        # No prior dev session, but parked. Pre-seed `user_content_hash`
        # to a stale value so the drift detection fires (auto-seeding on
        # first encounter would hide the bug).
        gh.seed_state(
            AWAITING_BODY_DRIFT_ISSUE,
            user_content_hash=STALE_CONTENT_HASH,
            awaiting_human=True,
            park_reason=None,
            last_action_comment_id=100,
        )

        self._mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message=IMPLEMENTED_MESSAGE,
            ),
            # Three `_has_new_commits` calls: (1) the drift-no-session
            # park-on-recovered-commits check returns False; (2) the
            # else-branch recovered-worktree check returns False;
            # (3) the post-agent commit detection returns True.
            has_new_commits=[False, False, True],
            push_branch=True,
        )

        state = gh.pinned_data(AWAITING_BODY_DRIFT_ISSUE)
        # The new hash is durably persisted -- the drift does NOT loop.
        self.assertNotEqual(state.get(USER_CONTENT_HASH), STALE_CONTENT_HASH)
        # Park flags cleared so the fresh-spawn branch fired.
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertIsNone(state.get("park_reason"))
        # The fresh implement prompt was used (NOT the resume-with-just-
        # comments prompt), so the dev sees the updated body.
        self._mocks[RUN_AGENT].assert_called_once()
        self._agent_args = self._mocks[RUN_AGENT].call_args[0]
        prompt = self._agent_args[1]
        self.assertIn(IMPLEMENTER_PROMPT_FRAGMENT, prompt)
        self.assertIn(EDITED_BODY, prompt)
        # PR opened from the fresh spawn.
        self.assertEqual(len(gh.opened_prs), 1)

    def test_new_comment_body_edit_uses_full_prompt(
        self,
    ) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            AWAITING_COMMENT_DRIFT_ISSUE,
            label=LABEL_IMPLEMENTING,
            body="updated body",
        )
        # New human comment that triggers comment-driven resume in the
        # legacy code path -- the bug there fresh-spawns with ONLY the
        # comment text, missing the body context.
        human = FakeComment(
            id=HUMAN_COMMENT_ID,
            body="here's more detail",
            user=FakeUser("alice"),
        )
        issue.comments.append(human)
        gh.add_issue(issue)
        gh.seed_state(
            AWAITING_COMMENT_DRIFT_ISSUE,
            user_content_hash=STALE_CONTENT_HASH,
            awaiting_human=True,
            last_action_comment_id=100,
        )

        self._mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message=IMPLEMENTED_MESSAGE,
            ),
            has_new_commits=[False, False, True],
            push_branch=True,
        )

        # Fresh implement prompt with the updated body AND the new
        # comment quoted via `_recent_comments_text`.
        self._agent_args = self._mocks[RUN_AGENT].call_args[0]
        prompt = self._agent_args[1]
        self.assertIn(IMPLEMENTER_PROMPT_FRAGMENT, prompt)
        self.assertIn("updated body", prompt)
        self.assertIn("here's more detail", prompt)
        # Comment marked consumed so the validating->in_review handoff
        # later won't classify it as fresh PR feedback.
        state = gh.pinned_data(AWAITING_COMMENT_DRIFT_ISSUE)
        self.assertGreaterEqual(
            int(state.get(LAST_ACTION_COMMENT_ID)),
            HUMAN_COMMENT_ID,
        )
