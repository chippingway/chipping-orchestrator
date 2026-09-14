# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for fixing-stage tests."""

from __future__ import annotations

import dataclasses
import datetime as datetime_module
import pathlib
from unittest import mock

from orchestrator import config as _config
from orchestrator.git.worktrees import paths as _git_worktree_paths
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    continue_command as _continue_command,
)
from orchestrator.workflow.stages.validating import dev_fix as _dev_fix
from tests.support import fakes
from tests.workflow import fixtures
from tests.workflow.stages import implementing_fixing_test_cases

dataclass = dataclasses.dataclass
config = _config
datetime = datetime_module.datetime
timedelta = datetime_module.timedelta
timezone = datetime_module.timezone
Path = pathlib.Path
MagicMock = mock.MagicMock
patch = mock.patch
worktree_paths = _git_worktree_paths

FakeComment = fakes.FakeComment
FakeGitHubClient = fakes.FakeGitHubClient
FakeLabel = fakes.FakeLabel
FakePR = fakes.FakePR
FakePRRef = fakes.FakePRRef
FakePRRepo = fakes.FakePRRepo
FakePRReview = fakes.FakePRReview
FakeUser = fakes.FakeUser
make_issue = fakes.make_issue
IssueScenario = implementing_fixing_test_cases.IssueScenario
posted_comment_contains = implementing_fixing_test_cases.posted_comment_contains

EVENT_AGENT_SPAWN = fixtures.EVENT_AGENT_SPAWN
ROLE_DEVELOPER = fixtures.ROLE_DEVELOPER
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_agent = fixtures._agent

# The two final messages that are NOT the dev's own words, and the phrase each
# one's park comment is recognized by.
PROVIDER_OVERLOAD_MESSAGE = fixtures.PROVIDER_OVERLOAD_MESSAGE
PROVIDER_UNAVAILABLE_PHRASE = fixtures.PROVIDER_UNAVAILABLE_PHRASE
SESSION_LIMIT_MESSAGE = fixtures.SESSION_LIMIT_MESSAGE
SESSION_LIMIT_PHRASE = fixtures.SESSION_LIMIT_PHRASE

# The follow-up a recovered park posts is worded by a validating owner this
# stage's parked branch calls, so its text and the assertion over it come from
# the shared fixtures rather than from either stage's own support module.
RECOVERED_PREFIX = fixtures.RECOVERED_PREFIX
PUSH_RETRIED_DETAIL = fixtures.PUSH_RETRIED_DETAIL
TIMEOUT_PUSHED_DETAIL = fixtures.TIMEOUT_PUSHED_DETAIL
TIMEOUT_EMPTY_DETAIL = fixtures.TIMEOUT_EMPTY_DETAIL
_RecoveryFollowupAssertions = fixtures._RecoveryFollowupAssertions

# The dev-fix disposition is a validating owner the fixing resume imports
# directly, so a test that has to wrap it patches that owner.
dev_fix = _dev_fix

_clear_pending_fix_bookmarks = _bookmarks._clear_pending_fix_bookmarks
_pending_fix_id_set = _bookmarks._pending_fix_id_set
_reconstruct_pending_fix_batch = _continue_command._reconstruct_pending_fix_batch


def now_utc() -> datetime_module.datetime:
    """The tz-aware clock every comment age in this stage is measured from."""
    return datetime.now(timezone.utc)


def _branch(issue_number: int) -> str:
    """Return the per-issue PR branch used by the fixing handler."""
    return f"orchestrator/chippingway__orchestrator/issue-{issue_number}"


FIXING = "workflow:fixing"
STAGE_FIXING = "fixing"
VALIDATING = "workflow:validating"
DOCUMENTING = "workflow:documenting"
IN_REVIEW = "in_review"

ISSUE = 880
PR_NUMBER = 880
BRANCH = _branch(ISSUE)
# A whole git object id, because the size gate freezes the head its pull
# request stands on before it measures and reads a commit field at its exact
# length -- an abbreviation is no head at all there.
PR_HEAD_SHA = fixtures.DEFAULT_PR_HEAD_SHA

DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"
FRESH_SESSION = "fresh-sess"
POISONED_SESSION = "poisoned-sess"

# The head a fix run starts on and the head it leaves the checkout at. The
# second IS the commit the size gate proves that checkout to, because in
# production the two are one read of one worktree: the route names the commit
# it means to publish and the gate refuses a checkout standing anywhere else,
# so a fixture spelling them apart would model the race rather than the tick.
#
# The first is the head the pull request is standing on for the same reason:
# the branch is in sync with its publication when a fix round opens, since the
# reviewer just read that head. It is what the round names to the gate, so a
# pull request somebody moved while the agent was out refuses the push.
SHA_BEFORE = PR_HEAD_SHA
SHA_AFTER = fixtures.MEASURED_CANDIDATE_SHA
# The head a run that committed nothing never moved off, which is also the
# head a stranded publication sends: unmoved is still the commit the checkout
# stands on, so it is the one the gate proves it to.
SHA_SAME = SHA_AFTER

TRIGGER_ID = 2000
FOLLOWUP_ID = 2001
REVIEWER_FEEDBACK_ID = 2400
CONCURRENT_COMMENT_ID = 2500
PARKED_COMMENT_WATERMARK = 2500
HUMAN_REPLY_ID = 2600
TRANSIENT_PARK_WATERMARK = 5000
COMMAND_COMMENT_ID = 9000
INITIAL_PR_COMMENT_WATERMARK = 1999
PENDING_FIX_AT_TS = "2026-05-24T00:00:00+00:00"
EARLIER_PENDING_FIX_AT_TS = "2026-05-23T00:00:00+00:00"
INLINE_FEEDBACK_ID = 3000
REVIEW_SUMMARY_FEEDBACK_ID = 4000

ADVANCED_PR_COMMENT_WATERMARK = 8000
ADVANCED_REVIEW_COMMENT_WATERMARK = 50
ADVANCED_REVIEW_SUMMARY_WATERMARK = 10

BATCH_ISSUE_ID = 2050
BATCH_PR_CONVERSATION_ID = 2100
BATCH_INLINE_ID = 40
BATCH_INLINE_SECOND_ID = 41
BATCH_SUMMARY_ID = 7
BATCH_ISSUE_IDS = (BATCH_ISSUE_ID, BATCH_PR_CONVERSATION_ID)
BATCH_INLINE_IDS = (BATCH_INLINE_ID, BATCH_INLINE_SECOND_ID)
BATCH_SUMMARY_IDS = (BATCH_SUMMARY_ID,)
BATCH_LATER_ISSUE_ID = 9000
BATCH_ORCHESTRATOR_NOTE_ID = 2300
BATCH_INLINE_NOISE_ID = 99
BATCH_SUMMARY_NOISE_ID = 12
UNTRUSTED_ISSUE_ID = 2060
ORCHESTRATOR_PARK_COMMENT_ID = 2050
ALLOWLIST_FEEDBACK_ID = 3000

ALICE = "alice"
BOB = "bob"
CAROL = "carol"
DAVE = "dave"
ORCHESTRATOR = "orchestrator"

DEBOUNCE_SECONDS = 600

PARK_PUSH_FAILED = "push_failed"
PARK_AGENT_TIMEOUT = "agent_timeout"
PARK_AGENT_SILENT = "agent_silent"
PARK_AGENT_QUESTION = "agent_question"

AWAITING_HUMAN = "awaiting_human"

AGENT_RUN_CHARGE_WRITES = fixtures.AGENT_RUN_CHARGE_WRITES
PARK_REASON = "park_reason"
LAST_ACTION_COMMENT_ID = fixtures.LAST_ACTION_COMMENT_ID
REVIEW_ROUND = "review_round"
USER_CONTENT_HASH = "user_content_hash"
PRE_DEV_FIX_SHA = "pre_dev_fix_sha"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
PR_LAST_REVIEW_COMMENT_ID = "pr_last_review_comment_id"
PR_LAST_REVIEW_SUMMARY_ID = "pr_last_review_summary_id"
PENDING_FIX_AT = "pending_fix_at"
PENDING_FIX_ISSUE_MAX_ID = "pending_fix_issue_max_id"
PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
PENDING_FIX_REVIEW_MAX_ID = "pending_fix_review_max_id"
PENDING_FIX_REVIEW_IDS = "pending_fix_review_ids"
PENDING_FIX_REVIEW_SUMMARY_MAX_ID = "pending_fix_review_summary_max_id"
PENDING_FIX_REVIEW_SUMMARY_IDS = "pending_fix_review_summary_ids"
PENDING_FIX_REVIEWER_COMMENT_ID = "pending_fix_reviewer_comment_id"
ORCHESTRATOR_COMMENT_IDS = "orchestrator_comment_ids"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
WORKTREE_PATH = "_worktree_path"
AUTHED_FETCH = "_authed_fetch"

CONTINUE_COMMAND = "/orchestrator continue"
# The rule `_build_fresh_respawn_preamble` closes its re-grounding block with.
FRESH_SPAWN_DIVIDER = "----------------------------------------"
DEV_SESSION_ID = "dev_session_id"
CHECK_SUCCESS = "success"
DEBOUNCE_CONFIG = "IN_REVIEW_DEBOUNCE_SECONDS"
PUSHED_FIX_MESSAGE = "pushed fix"
PUSHED_MESSAGE = "pushed"
RESUME_SESSION_ID = "resume_session_id"
CONTINUE_WORD = "continue"
FIX_FEEDBACK = "please address the typo"
REVIEWER_FEEDBACK = ":eyes: review (round 1/3) requested changes"
CHANGES_REQUESTED = "CHANGES_REQUESTED"
STALE_PRE_COMMENT_HASH = "stale-hash-pre-comment"
# A head a run never moved off, which is the head its pull request is
# standing on: the branch is in sync with its publication when a round opens.
UNCHANGED_SHA = PR_HEAD_SHA
NOTHING_TO_DO_MESSAGE = "nothing to do"
ALLOWED_AUTHOR = "geserdugarov"
ALLOWED_AUTHORS_CONFIG = "ALLOWED_ISSUE_AUTHORS"
ID_LIST_KEY = "ids"
MAX_ID_KEY = "max"
NO_PRESERVED_MESSAGE = "no preserved"
ALLOWLIST_OUTSIDER = "mallory"
ALLOWLIST_MALICIOUS_URL = "https://example.invalid/malicious-patch.zip"
ALLOWLIST_BODY = "please tighten the integration test"
REVIEW_SUMMARY_SURFACE = "review_summary"
ALLOWLIST_SURFACES = (
    "issue_thread",
    "pr_conversation",
    "inline_review",
    REVIEW_SUMMARY_SURFACE,
)
PRESERVED_BATCH_BODIES = (
    "fix the null check",
    "handle the edge case",
    "rename the temp var",
    "please address the review",
)
TEMP_ROOT = Path("/tmp")
FRESH_COMMENT_DELAY_MINUTES = 30
HISTORICAL_COMMENT_ID = 500
MISSING_ANCHOR_ID = 999999
GUIDED_COMMENT_ID = 9001


def dev_task_section(prompt: str) -> str:
    """The half of a dev prompt that IS the task, below the fresh-spawn divider.

    Everything above it is re-grounding context: the issue body and a verbatim
    transcript of the thread, which legitimately records the operator typing
    `/orchestrator continue`. Below it is what the dev is being asked to
    implement, and a bare command reaching THAT is the defect -- so a test
    about what the replay feeds the dev asks this rather than searching the
    whole prompt. A plain resume carries no preamble, so the whole prompt is
    the task and the split is a no-op.
    """
    return prompt.rsplit(FRESH_SPAWN_DIVIDER, 1)[-1]


class _InjectCommentAfterCall:
    def __init__(self, callback, issue, comment):
        self.callback = callback
        self.issue = issue
        self.comment = comment

    def __call__(self, *args, **kwargs):
        fix_result = self.callback(*args, **kwargs)
        self.issue.comments.append(self.comment)
        return fix_result


@dataclass(frozen=True)
class _ContinueSeed:
    park_reason: str | None
    command_body: str = CONTINUE_COMMAND
    command_id: int = COMMAND_COMMENT_ID
    command_on_pr_conversation: bool = False
    extra_issue_comments: tuple = ()
    with_batch_ids: bool = True
    pending_fix_at: str | None = PENDING_FIX_AT_TS
    silent_park_count: int = 2


class _FixingFixtureMixin(_PatchedWorkflowMixin):
    """Provide the common fixing-stage issue, PR, and pinned state."""

    def _seed(
        self,
        *,
        issue_number: int = ISSUE,
        pr=None,
        issue_comments=(),
        with_pr_number: bool = True,
        extra_state=None,
    ):
        gh = FakeGitHubClient()
        issue = make_issue(issue_number, label=FIXING)
        for comment in issue_comments:
            issue.comments.append(comment)
        gh.add_issue(issue)
        if pr is not None:
            gh.add_pr(pr)
        state: dict = {
            "branch": BRANCH,
            "dev_agent": DEV_AGENT,
            DEV_SESSION_ID: DEV_SESSION,
            REVIEW_ROUND: 1,
            PR_LAST_COMMENT_ID: INITIAL_PR_COMMENT_WATERMARK,
            PR_LAST_REVIEW_COMMENT_ID: 0,
            PR_LAST_REVIEW_SUMMARY_ID: 0,
            PENDING_FIX_AT: PENDING_FIX_AT_TS,
            PENDING_FIX_ISSUE_MAX_ID: TRIGGER_ID,
        }
        if with_pr_number and pr is not None:
            state["pr_number"] = pr.number
        if extra_state:
            state.update(extra_state)
        gh.seed_state(issue_number, **state)
        return gh, issue

    def _open_pr(self, **kwargs):
        defaults = {
            "number": PR_NUMBER,
            "head_branch": BRANCH,
            "head": FakePRRef(sha=PR_HEAD_SHA),
            "mergeable": True,
            "check_state": CHECK_SUCCESS,
        }
        defaults.update(kwargs)
        return FakePR(**defaults)


class _StrandedFixingFixtureMixin(_FixingFixtureMixin):
    def _seed_stranded_bounce(self):
        """A validating-route `fixing` issue whose only unread PR comment is
        the reviewer feedback the orchestrator posted itself.

        The rescan drops that comment as the orchestrator's own, so the tick
        reaches the no-feedback exit with the reviewer round still unanswered
        -- the shape a dev run discarded by a live `paused` leaves behind. The
        route is spelled by `pending_fix_at` being unset, with the reviewer
        comment id as the round's only bookmark.
        """
        reviewer_feedback = FakeComment(
            id=REVIEWER_FEEDBACK_ID,
            body=REVIEWER_FEEDBACK,
            user=FakeUser(ORCHESTRATOR),
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        pr = self._open_pr()
        pr.issue_comments.append(reviewer_feedback)
        return self._seed(
            pr=pr,
            extra_state={
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                PENDING_FIX_REVIEWER_COMMENT_ID: REVIEWER_FEEDBACK_ID,
                ORCHESTRATOR_COMMENT_IDS: [REVIEWER_FEEDBACK_ID],
                REVIEW_ROUND: 2,
            },
        )

    def _run_stranded_bounce(self, gh, issue, worktree, **run_options):
        """One fixing tick with the worktree probe answering `worktree`.

        The path is patched rather than seeded because the handler reads it to
        decide whether there is a checkout to probe at all, and the default
        patch set leaves that read real.
        """
        with patch.object(worktree_paths, WORKTREE_PATH, return_value=worktree):
            return self._run_fixing(
                gh, issue, run_agent=_agent(), **run_options,
            )

    def _seed_stranded(self, *, reply_id: int = HUMAN_REPLY_ID):
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        reply = FakeComment(
            id=reply_id,
            body=CONTINUE_WORD,
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        return self._seed(
            pr=pr,
            issue_comments=[reply],
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: None,
                PR_LAST_COMMENT_ID: PARKED_COMMENT_WATERMARK,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 2,
            },
        )
