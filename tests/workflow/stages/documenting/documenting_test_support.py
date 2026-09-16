# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from orchestrator.workflow.stages.documenting import handler as _documenting
from tests.support.fakes import (
    DEFAULT_PR_HEAD_SHA,
    FakeGitHubClient,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    MEASURED_CANDIDATE_SHA,
    _open_pr_for,
    _PatchedWorkflowMixin,
)

# --- Workflow labels this stage routes between --------------------------
DOCUMENTING = "workflow:documenting"
IN_REVIEW = "in_review"
VALIDATING = "workflow:validating"

# --- Dev agent identity pinned into per-issue state ---------------------
DEV_AGENT = "codex"
DEV_SESSION = "dev-sess"

# --- Worktree HEAD SHAs threaded through the docs / recovery flows ------
# The head a docs pass begins on, which is the head its pull request is
# standing on: the branch is in sync with its publication when the round
# opens, since the reviewer just approved that head. It is what the pass names
# to the size gate, so a pull request somebody moved while the agent was out
# refuses the push rather than being overwritten.
SHA_BEFORE = DEFAULT_PR_HEAD_SHA
# The head a docs pass leaves the checkout on. Each IS the commit the size
# gate proves that checkout to, because in production they are one read of one
# worktree: the stage names the commit it means to publish and the gate
# refuses a checkout standing anywhere else, so a fixture that spelled them
# differently would be modelling the race rather than the tick.
SHA_AFTER = MEASURED_CANDIDATE_SHA
SHA_DOCS = MEASURED_CANDIDATE_SHA
SHA_RECOVERED = MEASURED_CANDIDATE_SHA
SHA_PR_HEAD = "pr-head-sha"

# --- Pinned-state field keys read back from `gh.pinned_data(...)` -------
DOCS_VERDICT = "docs_verdict"
DOCS_CHECKED_SHA = "docs_checked_sha"
REVIEW_ROUND = "review_round"
PARK_REASON = "park_reason"
AWAITING_HUMAN = "awaiting_human"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# --- Awaiting-human park reasons the docs handler writes ----------------
PARK_PUSH_FAILED = "push_failed"
PARK_AGENT_SILENT = "agent_silent"
PARK_AGENT_TIMEOUT = "agent_timeout"
PARK_DIVERGED = "diverged_branch"
PARK_FETCH_FAILED = "fetch_failed"
PARK_DIRTY = "dirty_worktree"
PARK_AGENT_QUESTION = "agent_question"
PARK_RESET_FAILED = "worktree_reset_failed"
# What a reading nobody could take earns, told apart from the branch that
# really is in sync: both answer zero and zero.
PARK_UNREADABLE_DIVERGENCE = "unreadable_divergence"

# --- Docs verdict values persisted on a successful pass -----------------
VERDICT_UPDATED = "updated"
VERDICT_NO_CHANGE = "no_change"

# --- Repo docs paths the agent edits / the dirty guard reports ----------
README = "README.md"
DOCS_ARCHITECTURE = "docs/architecture.md"

# --- Mock keys returned by `_PatchedWorkflowMixin._run` -----------------
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

# --- The reference a published docs commit's subject is amended to end in --
AMEND_COMMIT_MESSAGE = "_amend_commit_message"
COMMIT_MESSAGE = "_commit_message"
HEAD_SHA = "_head_sha"
COUNT_ADDED_LINES = "_count_added_lines"
# The keyword a gated push names the commit it publishes by.
REVISION = "revision"
PR_REF_IN_SUBJECT = "PR_REF_IN_SUBJECT"
SQUASH_ON_APPROVAL = "SQUASH_ON_APPROVAL"
PARK_SUBJECT_AMEND_FAILED = "subject_amend_failed"
SETTLED_DOCS_SHA = "docs_settled_sha"
# The commit a docs pass made before its subject was amended to name the pull
# request. What it is amended INTO is the head the size gate proves, so a
# fixture spells that one with the SHAs above.
SHA_UNREFERENCED = "d0c5" * 10

UNCOMMITTED_CHANGE = "uncommitted change"
TRUSTED_AUTHOR = "alice"
USER_CONTENT_CHANGED = "issue body changed"
AUTHED_FETCH = "_authed_fetch"
ORIGINAL_BODY = "original body"
UPDATED_BODY_AFTER_DOCS = "updated body after prior docs commit"
WORKTREE_PATH = "_worktree_path"
GIT_HARDENED = "_git_hardened"
GIT_REV_LIST = "rev-list"
GIT_RESET = "reset"
GIT_HARD_RESET = "--hard"
GIT_CLEAN = "clean"
GIT_CLEAN_FLAGS = "-fd"
DRIFT_UNWIND_PENDING = "docs_drift_unwind_pending"

MISSING_PR_ISSUE_NUMBER = 101
PARKED_MISSING_PR_ISSUE_NUMBER = 102
COMMIT_REPLY_ISSUE_NUMBER = 401
COMMIT_REPLY_PR_NUMBER = 41
COMMIT_REPLY_COMMENT_ID = 2100
COMMIT_REPLY_WATERMARK = 2000
NO_COMMIT_REPLY_ISSUE_NUMBER = 403
NO_COMMIT_REPLY_PR_NUMBER = 43
NO_COMMIT_REPLY_COMMENT_ID = 3100
NO_COMMIT_REPLY_WATERMARK = 3000
RECOVERED_REPLY_ISSUE_NUMBER = 404
RECOVERED_REPLY_PR_NUMBER = 44
RECOVERED_REPLY_COMMENT_ID = 4100
RECOVERED_REPLY_WATERMARK = 4000
FAILED_PUSH_REPLY_ISSUE_NUMBER = 405
FAILED_PUSH_REPLY_PR_NUMBER = 45
FAILED_PUSH_REPLY_COMMENT_ID = 5100
FAILED_PUSH_REPLY_WATERMARK = 5000
NO_NEW_COMMENT_ISSUE_NUMBER = 402
NO_NEW_COMMENT_PR_NUMBER = 42
NO_NEW_COMMENT_WATERMARK = 2500
FULL_PROMPT_REPLY_ISSUE_NUMBER = 406
FULL_PROMPT_REPLY_PR_NUMBER = 46
FULL_PROMPT_REPLY_COMMENT_ID = 6100
FULL_PROMPT_REPLY_WATERMARK = 6000
NO_CHANGE_REPLY_ISSUE_NUMBER = 407
NO_CHANGE_REPLY_PR_NUMBER = 47
NO_CHANGE_REPLY_COMMENT_ID = 7100
NO_CHANGE_REPLY_WATERMARK = 7000
CONTINUE_COMMENT_ID = 9000
CONTINUE_PR_NUMBER = 47
CONTINUE_WATERMARK = 8000
CONTINUE_ISSUE_NUMBER = 730
QUESTION_CONTINUE_ISSUE_NUMBER = 731
INTERRUPTED_ISSUE_NUMBER = 202
INTERRUPTED_PR_NUMBER = 21
INTERRUPTED_RESUME_ISSUE_NUMBER = 203
INTERRUPTED_RESUME_PR_NUMBER = 23
INTERRUPTED_RESUME_COMMENT_ID = 2100
INTERRUPTED_RESUME_WATERMARK = 2000
PARKED_FIXTURE_WATERMARK = 6000
GIT_FAILURE_EXIT_CODE = 128
PENDING_UNWIND_COMMENT_ID = 999
EXTERNAL_MERGE_ISSUE_NUMBER = 180
EXTERNAL_MERGE_PR_NUMBER = 18000
CLOSED_ISSUE_NUMBER = 181
CLOSED_PR_NUMBER = 18100
FINAL_DOCS_PR_WATERMARK = 999
FINAL_DOCS_REPLY_ID = 2000
WATERMARK_ISSUE_NUMBER = 709
WATERMARK_PR_NUMBER = 73
PICKUP_COMMENT_ID = 900
PARK_COMMENT_ID = 950
HUMAN_REPLY_ID = 1100


def _branch(issue_number: int) -> str:
    """The per-issue PR branch the docs handler anchors on."""
    return f"orchestrator/chippingway__orchestrator/issue-{issue_number}"


class _DocumentingWorkflowMixin(_PatchedWorkflowMixin):
    def _run_documenting(self, gh, issue, **run_options):
        return self._run(
            lambda: _documenting._handle_documenting(gh, _TEST_SPEC, issue),
            **run_options,
        )


class _BasicDocumentingFixture(_DocumentingWorkflowMixin):
    def _seeded(self, **state):
        gh = FakeGitHubClient()
        issue = make_issue(self.issue_number, label=DOCUMENTING)
        gh.add_issue(issue)
        defaults = {
            "pr_number": self.pr_number,
            "branch": _branch(self.issue_number),
            "dev_agent": DEV_AGENT,
            "dev_session_id": DEV_SESSION,
        }
        defaults.update(state)
        gh.seed_state(self.issue_number, **defaults)
        if defaults["pr_number"] not in gh.pulls:
            _open_pr_for(
                gh,
                issue_number=self.issue_number,
                pr_number=defaults["pr_number"],
            )
        return gh, issue


class _FreshDocumentingFixture(_BasicDocumentingFixture):
    issue_number = 201
    pr_number = 21
