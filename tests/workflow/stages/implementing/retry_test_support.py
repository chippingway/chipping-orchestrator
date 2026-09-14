# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for implementing retry tests."""

from __future__ import annotations

from types import MappingProxyType
from unittest import mock

from orchestrator.agents import runner as _agent_runner
from orchestrator.config import settings as config
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.workflow.engine import (
    retry_budget as _retry_budget,
)
from orchestrator.workflow.stages.implementing import (
    resume as _implementing_resume,
    retry_cap as _implementing_retry_cap,
)
from tests.support import fakes
from tests.workflow import fixtures
from tests.workflow.stages import implementing_fixing_test_cases

MagicMock = mock.MagicMock
patch = mock.patch

FakeComment = fakes.FakeComment
FakeGitHubClient = fakes.FakeGitHubClient
FakeLabel = fakes.FakeLabel
FakePR = fakes.FakePR
FakeUser = fakes.FakeUser
make_issue = fakes.make_issue
IssueScenario = implementing_fixing_test_cases.IssueScenario

BACKEND_CLAUDE = fixtures.BACKEND_CLAUDE
BACKEND_CODEX = fixtures.BACKEND_CODEX
LABEL_DOCUMENTING = fixtures.LABEL_DOCUMENTING
LABEL_DONE = fixtures.LABEL_DONE
LABEL_IMPLEMENTING = fixtures.LABEL_IMPLEMENTING
LABEL_RESOLVING_CONFLICT = fixtures.LABEL_RESOLVING_CONFLICT
LABEL_VALIDATING = fixtures.LABEL_VALIDATING
REVIEW_APPROVED_MESSAGE = fixtures.REVIEW_APPROVED_MESSAGE
_FAKE_WT = fixtures._FAKE_WT
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_issue_branch = fixtures._issue_branch
_iso_hours_ago = fixtures._iso_hours_ago

KEY_AWAITING_HUMAN = "awaiting_human"
KEY_CODEX_SESSION_ID = "codex_session_id"
KEY_DEV_AGENT = "dev_agent"
KEY_DEV_RESUME_COUNT = "dev_resume_count"
KEY_DEV_SESSION_ID = "dev_session_id"
KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"
KEY_PARK_REASON = "park_reason"
KEY_RETRY_CAP_CONTINUED = "retry_cap_continued"
KEY_RETRY_CAP_NOTICE = "retry_cap_notice"
KEY_RETRY_CAP_STAGE = "retry_cap_stage"
KEY_RETRY_COUNT = "retry_count"
KEY_SILENT_PARK_COUNT = "silent_park_count"

COMMENTS_AFTER = "comments_after"
ENSURE_WORKTREE = "_ensure_worktree"
RUN_AGENT = "run_agent"

# The owners the checkout and the spawn answer on, so a sibling module patches
# the module the stage calls.
agent_runner = _agent_runner
worktree_creation = _worktree_creation
# The park handler the stage answers a spent budget with.
retry_cap = _implementing_retry_cap
RESUME_SESSION_ID = "resume_session_id"

POISONED_SESSION = "poisoned-sess"
FRESH_SESSION = "fresh-sess"
LIVE_SESSION = "live-sess"
LEGACY_SESSION = "sess-legacy"

IMPLEMENT_PROMPT_FRAGMENT = "implement the thing"
FIX_PROMPT_FRAGMENT = "fix it"
RESUME_PROMPT_FRAGMENT = "resuming work on GitHub issue"
PROMPT_TOO_LONG_MESSAGE = "Prompt is too long"
STALE_SESSION_STDERR = "Error: No conversation found with session ID: poisoned-sess\n"
DEFAULT_SESSION = "sess-1"
DEV_SESSION = "dev-sess"
DONE_MESSAGE = "done"
OK_MESSAGE = "ok"
RESUME_TEXT = "go"

SILENT_SESSION_ISSUE = 950
LEGACY_FRESH_SESSION_ISSUE = 951
STALE_SESSION_ISSUE = 960
OVERFLOW_SESSION_ISSUE = 961
PROACTIVE_SESSION_ISSUE = 962
PREAMBLE_ISSUE = 963
MISSING_SESSION_ISSUE = 964
EMPTY_SESSION_RESULT_ISSUE = 965
FRESH_BACKEND_ISSUE = 20
REVIEW_BACKEND_ISSUE = 21
DEV_FIX_BACKEND_ISSUE = 22
LEGACY_BACKEND_ISSUE = 23
HUMAN_REPLY_ID = 1100
ACTION_COMMENT_ID = 900
EXPIRED_WINDOW_HOURS = 25
HIGH_RESUME_COUNT = 99
RETRY_CAP_PARK_ISSUE = 10
RETRY_CAP_TICKS = 3

# The audit phases one retry-cap park reports, in the spellings a record
# carries them under.
RETRY_CAP_EVENT = "retry_cap"
PHASE_CONTINUED = "continued"
PHASE_DELIVERED = "delivered"
PHASE_RECONCILED = "reconciled"
PHASE_STANDING = "standing"

PARK_RETRY_CAP = "retry_cap"
STAGE_IMPLEMENTING = "implementing"
CONTINUE_COMMAND = "/orchestrator continue"
GUIDANCE_REPLY = "use sqlite for the cache"
TRUSTED_AUTHOR = "geserdugarov"
OUTSIDE_AUTHOR = "stranger"
ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"
# The two replies these scenarios are written out of: the operator's command,
# and words that are not one.
TRUSTED_COMMAND = (CONTINUE_COMMAND, TRUSTED_AUTHOR)
TRUSTED_GUIDANCE = (GUIDANCE_REPLY, TRUSTED_AUTHOR)
RETRY_CAP_CONTINUE_ISSUE = 11
# The two control labels that park an issue outside the state machine, so none
# of this stage's handlers runs while one of them is on.
HARD_SKIP_LABELS = (BACKLOG_LABEL, PAUSED_LABEL)
CONTINUE_PR_NUMBER = 4711
PARKED_WATERMARK = 9000
FIRST_REPLY_ID = 9100
GRANTED_ATTEMPTS = 1
# The sentence a park took and an unreadable thread left unsaid.
OWED_NOTICE = "hit retry cap (3/day) for implementing; manual intervention"
STALE_CONTENT_HASH = "stale-hash"
STUCK_MESSAGE = "still stuck"
# What the fake reports for a pull request a human already merged.
PR_CLOSED = "closed"
DRIFT_RESUME_NOTICE = "issue body changed; resuming dev session"

# Records this park may not spend: the commit an approval still owes a push
# for, the pull request the work already has, and a live generation.
UNTOUCHED_RECORDS = MappingProxyType({
    "pr_number": CONTINUE_PR_NUMBER,
    "late_approved_sha": "candidate-sha",
    "late_cycle_id": 3,
    "late_generation": 2,
    "late_phase": "measuring",
})


class _RetryCapFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, **state):
        gh = FakeGitHubClient()
        issue = make_issue(8, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        if state:
            gh.seed_state(8, **state)
        return gh, issue


class _RetryCapParkMixin(_PatchedWorkflowMixin):
    """One issue whose budget is spent, and the ticks that refuse it."""

    def _exhausted(self):
        gh = FakeGitHubClient()
        issue = fakes.make_issue(
            RETRY_CAP_PARK_ISSUE, label=LABEL_IMPLEMENTING,
        )
        gh.add_issue(issue)
        gh.seed_state(
            RETRY_CAP_PARK_ISSUE,
            retry_count=RETRY_CAP_TICKS,
            retry_window_start=_iso_hours_ago(1),
        )
        return gh, issue

    def _refuse(
        self, gh, issue, *, persist: bool = True, cap: int = RETRY_CAP_TICKS,
    ) -> bool:
        """One tick's gate, read from and written back to durable state."""
        state = gh.read_pinned_state(issue)
        with patch.object(config, "MAX_RETRIES_PER_DAY", cap):
            allowed = _retry_budget._charge_or_park(
                gh, issue, state, stage=STAGE_IMPLEMENTING,
            )
        if persist:
            gh.write_pinned_state(issue, state)
        return allowed

    def _phases(self, gh) -> list:
        """The audit trail this park has left, in the order it left it."""
        return [
            record["phase"]
            for record in gh.recorded_events
            if record["event"] == RETRY_CAP_EVENT
        ]


class _RetryCapContinueMixin(_RetryCapParkMixin):
    """The same park one tick on: the replies a human writes on it.

    The park is seeded rather than reached through the gate, because what
    these cover is every tick AFTER the one that took it -- which is all of
    them until somebody answers -- and they read the same audit trail.
    """

    def _parked(self, *replies, window_hours: int = 1, **records):
        gh = FakeGitHubClient()
        issue = make_issue(RETRY_CAP_CONTINUE_ISSUE, label=LABEL_IMPLEMENTING)
        issue.comments.extend(
            FakeComment(
                id=FIRST_REPLY_ID + offset, body=body, user=FakeUser(author),
            )
            for offset, (body, author) in enumerate(replies)
        )
        gh.add_issue(issue)
        gh.add_pr(FakePR(
            number=CONTINUE_PR_NUMBER,
            head_branch=_issue_branch(RETRY_CAP_CONTINUE_ISSUE),
        ))
        gh.seed_state(RETRY_CAP_CONTINUE_ISSUE, **{
            "awaiting_human": True,
            "park_reason": PARK_RETRY_CAP,
            "retry_cap_stage": STAGE_IMPLEMENTING,
            "retry_count": RETRY_CAP_TICKS,
            "retry_window_start": _iso_hours_ago(window_hours),
            "last_action_comment_id": PARKED_WATERMARK,
        } | records)
        return gh, issue

    def _granted(self, **records):
        """The same issue after a restart, with the grant already durable.

        What a continuation left behind and nothing has spent: no park, one
        attempt owed, and a window opened at the grant.
        """
        return self._parked(
            awaiting_human=False,
            park_reason=None,
            retry_cap_stage=None,
            retry_cap_continued=GRANTED_ATTEMPTS,
            retry_count=0,
            **records,
        )

    def _pinned(self, gh) -> dict:
        return gh.pinned_data(RETRY_CAP_CONTINUE_ISSUE)

    def _only_trusted(self):
        """Narrow the allowlist, so an outsider's copy of a command is one."""
        return patch.object(config, ALLOWED_AUTHORS, (TRUSTED_AUTHOR,))

    def _decide(self, gh, issue) -> bool:
        """Whether one tick's answer to the park is that it still stands."""
        state = gh.read_pinned_state(issue)
        with self._only_trusted():
            return retry_cap._park_owns_the_tick(gh, issue, state)

    def _assert_fresh_run(self, mocks):
        """The one call this tick made, proved not to be a resume.

        A resume is the failure every grant-funded road is watched for: it
        runs an agent without passing the gate, so the counter it never
        touched and the grant it never spent would let the issue run again
        for free.
        """
        spawn = mocks[RUN_AGENT]
        spawn.assert_called_once()
        self.assertIsNone(spawn.call_args.kwargs.get(RESUME_SESSION_ID))
        return spawn


class _SilentSessionFixtureMixin(_PatchedWorkflowMixin):
    def _seeded_issue(self, *, silent_park_count: int):
        gh = FakeGitHubClient()
        issue = make_issue(SILENT_SESSION_ISSUE, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.seed_state(
            SILENT_SESSION_ISSUE,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=POISONED_SESSION,
            silent_park_count=silent_park_count,
        )
        return gh, issue


class _StaleSessionFixtureMixin(_PatchedWorkflowMixin):
    def _seeded_issue(self, *, dev_agent: str = BACKEND_CLAUDE):
        gh = FakeGitHubClient()
        issue = make_issue(STALE_SESSION_ISSUE, label=LABEL_RESOLVING_CONFLICT)
        gh.add_issue(issue)
        gh.seed_state(
            STALE_SESSION_ISSUE,
            dev_agent=dev_agent,
            dev_session_id=POISONED_SESSION,
            silent_park_count=0,
        )
        return gh, issue


class _OverflowSessionFixtureMixin(_PatchedWorkflowMixin):
    def _seeded_issue(self, *, dev_agent: str = BACKEND_CLAUDE):
        gh = FakeGitHubClient()
        issue = make_issue(OVERFLOW_SESSION_ISSUE, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.seed_state(
            OVERFLOW_SESSION_ISSUE,
            dev_agent=dev_agent,
            dev_session_id=POISONED_SESSION,
            silent_park_count=0,
        )
        return gh, issue


class _ProactiveSessionFixtureMixin(_PatchedWorkflowMixin):
    def _seeded_issue(
        self,
        *,
        resume_count: int = 0,
        dev_agent: str = BACKEND_CLAUDE,
        sid: str = LIVE_SESSION,
    ):
        gh = FakeGitHubClient()
        issue = make_issue(
            PROACTIVE_SESSION_ISSUE,
            label="in_review",
            body=IMPLEMENT_PROMPT_FRAGMENT,
        )
        gh.add_issue(issue)
        gh.seed_state(
            PROACTIVE_SESSION_ISSUE,
            dev_agent=dev_agent,
            dev_session_id=sid,
            silent_park_count=0,
            dev_resume_count=resume_count,
        )
        return gh, issue

    def _run_resume(self, gh, issue, *, fake_run, threshold):
        state = gh.read_pinned_state(issue)
        with (
            patch.object(config, "DEV_SESSION_MAX_RESUMES", threshold),
            patch.object(
                _worktree_creation, ENSURE_WORKTREE, return_value=_FAKE_WT,
            ),
            patch.object(_agent_runner, RUN_AGENT, fake_run),
        ):
            _, agent_result, _ = _implementing_resume._resume_dev_with_text(
                gh,
                _TEST_SPEC,
                issue,
                state,
                FIX_PROMPT_FRAGMENT,
            )
        return state, agent_result
