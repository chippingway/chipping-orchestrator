# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import content_hash as _content_hash, review_subjects as _review_subjects
from tests.support import agy_stream as stream
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakeUser,
    make_issue,
)
from tests.workflow import (
    agent_failure_values as _failures,
    approval_records as _approval_records,
    verified_approvals as _verified,
)

# --- Workflow labels this stage routes between --------------------------
from tests.workflow.fixtures import (
    _FAKE_WT,
    MEASURED_CANDIDATE_SHA,
    RecordsTheLaunch,
    _open_pr_for,
)
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting_support,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    _branch,
    _DocumentingWorkflowMixin,
)

PR_NUMBER = "pr_number"
DOCUMENTING = "workflow:documenting"
IN_REVIEW = "in_review"
VALIDATING = "workflow:validating"

# --- Dev agent identity pinned into per-issue state ---------------------
DEV_AGENT = "codex"
DEV_SESSION = "dev-sess"

# --- Worktree HEAD SHAs threaded through the docs / recovery flows ------
SHA_BEFORE = documenting_support.SHA_BEFORE
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

# --- Docs verdict values persisted on a successful pass -----------------
VERDICT_UPDATED = "updated"
VERDICT_NO_CHANGE = "no_change"

# --- Repo docs paths the agent edits / the dirty guard reports ----------
README = "README.md"
DOCS_ARCHITECTURE = "docs/architecture.md"

# --- Mock keys returned by `_PatchedWorkflowMixin._run` -----------------
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

UNCOMMITTED_CHANGE = "uncommitted change"
TRUSTED_AUTHOR = "alice"
USER_CONTENT_CHANGED = "issue body changed"
AUTHED_FETCH = "_authed_fetch"
ORIGINAL_BODY = "original body"
# The requirements revision the approval was given, which no reading of the
# thread as it stands reproduces: the body was edited since.
STALE_BODY_HASH = _approval_records.STALE_REQUIREMENTS
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


_CONTINUE = "/orchestrator continue"


def _continue_comment(body: str) -> FakeComment:
    return FakeComment(
        id=CONTINUE_COMMENT_ID,
        body=body,
        user=FakeUser("dave"),
    )


class _ContinueDocumentingFixture(_DocumentingWorkflowMixin):
    def _seed(self, number: int, *, park_reason, body="/orchestrator continue"):
        gh = FakeGitHubClient()
        issue = make_issue(number, label=DOCUMENTING, body="the requirements")
        issue.comments.append(_continue_comment(body))
        gh.add_issue(issue)
        # A bare continue does not shift the current content hash, so the
        # retry reruns documenting without taking the drift detour.
        gh.seed_state(
            number,
            pr_number=CONTINUE_PR_NUMBER,
            branch=_branch(number),
            awaiting_human=True,
            park_reason=park_reason,
            last_action_comment_id=CONTINUE_WATERMARK,
            dev_agent=DEV_AGENT,
            dev_session_id=DEV_SESSION,
            silent_park_count=1,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        _open_pr_for(
            gh, issue_number=number, pr_number=CONTINUE_PR_NUMBER,
        )
        _verified.verifies_the_approval(gh, issue)
        return gh, issue


# An issue whose Antigravity docs pass is stopped after it committed -- by a
# quota unless named otherwise: the requirements and the trusted guidance its
# thread carried before the pass.
QUOTA_ISSUE_NUMBER = 732
QUOTA_ISSUE_BODY = "Add the --dry-run flag and say what it skips."
EARLIER_GUIDANCE = "Mention --dry-run in the README's usage section."
_EARLIER_GUIDANCE_ID = 800
# The commit the stopped pass left on the branch, unpublished, and the
# conversation a continue opens in its place.
SHA_STOPPED = documenting_support.SHA_UNREFERENCED
FRESH_SESSION = "fresh-docs-conversation"
_CONFIRMED = replace(
    _failures.agy_responded("The preserved commit documents --dry-run.\nDOCS: NO_CHANGE"),
    session_id=FRESH_SESSION,
)
# What the checkout's head reads as across the stopped pass's tick: the head it
# began on, the commit it made, and the replacement a publication of that commit
# would amend it into -- so a pass that did publish it would push rather than
# park.
_COMMITTED = (SHA_BEFORE, SHA_STOPPED, SHA_DOCS)
# The pinned Antigravity command, in the issue's checkout, that every pass on
# the issue launches under.
PINNED_IN_CHECKOUT = (stream.BACKEND, _FAKE_WT, stream.ARGS)
_REPLY_GAP = 100


class _RefusedOnceSpawned:
    """The issues whose pinned-comment edits GitHub refuses, read as: this issue, once an agent spawned on it."""

    def __init__(self, gh) -> None:
        self._gh = gh
        self._spawned_before = self._spawns()

    def __contains__(self, issue_number) -> bool:
        return issue_number == QUOTA_ISSUE_NUMBER and self._spawns() > self._spawned_before

    def _spawns(self) -> int:
        return sum(event["event"] == "agent_spawn" for event in self._gh.recorded_events)


class _AgyContinueDocumentingFixture(_DocumentingWorkflowMixin):
    """One Antigravity docs issue whose fresh pass stops after it committed, ticked off one launch mock.

    The launch mock answers the stopped pass and then a successful
    `DOCS: NO_CHANGE` from the conversation `FRESH_SESSION` names, so every
    launch the issue's ticks make reads back off it in order.
    """

    def _stopped(self, held=None, *, stop=None, head_shas=_COMMITTED):
        """The issue once its stopped pass returned, and the launch mock every later tick shares.

        `stop` is what that pass returned, a quota stop unless named, and
        `held`, handed the client, the hold its tick runs under; without one
        GitHub takes every edit and the disposition reads the pass. The pass
        commits unless `head_shas` reads otherwise. The launch mock's side
        effect records the pinned comment as each launch was invoked over it.
        """
        gh = FakeGitHubClient()
        issue = make_issue(QUOTA_ISSUE_NUMBER, label=DOCUMENTING, body=QUOTA_ISSUE_BODY)
        issue.comments.append(
            FakeComment(id=_EARLIER_GUIDANCE_ID, body=EARLIER_GUIDANCE, user=FakeUser(TRUSTED_AUTHOR)),
        )
        gh.add_issue(issue)
        gh.seed_state(
            QUOTA_ISSUE_NUMBER,
            pr_number=CONTINUE_PR_NUMBER,
            branch=_branch(QUOTA_ISSUE_NUMBER),
            dev_agent=stream.SPEC,
            dev_session_id=stream.SESSION_ID,
            last_action_comment_id=PICKUP_COMMENT_ID,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        _open_pr_for(gh, issue_number=QUOTA_ISSUE_NUMBER, pr_number=CONTINUE_PR_NUMBER)
        _verified.verifies_the_approval(gh, issue)
        run_agent = MagicMock(side_effect=RecordsTheLaunch(
            gh, QUOTA_ISSUE_NUMBER, (stop or _failures.agy_quota_stop(), _CONFIRMED),
        ))
        with (held or self._edits_taken)(gh):
            self._run_documenting(
                gh,
                issue,
                run_agent=run_agent,
                head_shas=head_shas,
                branch_ahead_behind=(0, 0),
            )
        return gh, issue, run_agent

    def _paused_meanwhile(self, gh):
        """An operator's pause the fresh issue read after the run finds."""
        view = make_issue(QUOTA_ISSUE_NUMBER, label=DOCUMENTING)
        view.labels.append(FakeLabel(PAUSED_LABEL))
        return patch.object(gh, "get_issue", return_value=view)

    def _retirement_refused(self, gh):
        """GitHub refusing every pinned-comment edit once the agent has spawned, so a quota's retirement does not land.

        The record the launch lands ahead of the run is taken; only what the
        run's return writes is refused.
        """
        return patch.object(gh.pinned_failures, "refused", _RefusedOnceSpawned(gh))

    def _edits_taken(self, gh):
        """The ordinary world, where GitHub takes every pinned-comment edit."""
        return patch.object(gh.pinned_failures, "refused", set())

    def _tick(self, gh, issue, run_agent, *, head_shas=(SHA_STOPPED, SHA_DOCS), ahead=1):
        """One later tick over the checkout the stopped pass left `ahead` commits ahead of its pull request.

        Unless named, its head reads find the stopped pass's commit and then
        the replacement a publication of it would amend it into.
        """
        return self._run_documenting(
            gh, issue, run_agent=run_agent, head_shas=head_shas, branch_ahead_behind=(ahead, 0),
        )

    def _continue(self, gh, issue) -> None:
        """A trusted bare continue above everything the thread and the park's watermark already hold."""
        thread = [posted.id for posted in issue.comments]
        newest = max([gh.pinned_data(issue.number)[LAST_ACTION_COMMENT_ID], *thread])
        issue.comments.append(
            FakeComment(id=newest + _REPLY_GAP, body=_CONTINUE, user=FakeUser(TRUSTED_AUTHOR)),
        )

    def _configured_elsewhere(self):
        """A configured developer command other than the Antigravity one the issue pinned."""
        return patch.multiple(config, DEV_AGENT_SPEC=DEV_AGENT, DEV_AGENT=DEV_AGENT, DEV_AGENT_ARGS=())


class _ParkedDocumentingFixture(_DocumentingWorkflowMixin):
    issue_number = 601
    pr_number = 61

    def _seeded(self, *, comments=(), **state):
        gh = FakeGitHubClient()
        issue = make_issue(self.issue_number, label=DOCUMENTING)
        issue.comments.extend(comments)
        gh.add_issue(issue)
        defaults = {
            PR_NUMBER: self.pr_number,
            "branch": _branch(self.issue_number),
            "dev_agent": DEV_AGENT,
            "dev_session_id": DEV_SESSION,
            "awaiting_human": True,
            "last_action_comment_id": PARKED_FIXTURE_WATERMARK,
            # The seeded baseline keeps first-encounter drift persistence
            # out of tests that assert an already-parked tick writes nothing.
            "user_content_hash": _content_hash._compute_user_content_hash(
                issue,
                set(),
            ),
        }
        defaults.update(state)
        gh.seed_state(self.issue_number, **defaults)
        if defaults[PR_NUMBER] not in gh.pulls:
            _open_pr_for(
                gh,
                issue_number=self.issue_number,
                pr_number=defaults[PR_NUMBER],
            )
        if _review_subjects.APPROVED_SUBJECT not in defaults:
            _verified.verifies_the_approval(gh, issue)
        return gh, issue


class _DocumentingDriftFixture(_DocumentingWorkflowMixin):
    issue_number = 701
    pr_number = 71

    def _seeded(self, *, comments=(), **state):
        gh = FakeGitHubClient()
        issue = make_issue(
            self.issue_number,
            label=DOCUMENTING,
            body=ORIGINAL_BODY,
        )
        issue.comments.extend(comments)
        gh.add_issue(issue)
        defaults = {
            PR_NUMBER: self.pr_number,
            "branch": _branch(self.issue_number),
            "dev_agent": DEV_AGENT,
            "dev_session_id": DEV_SESSION,
            "user_content_hash": STALE_BODY_HASH,
            "review_round": 2,
        }
        defaults.update(state)
        gh.seed_state(self.issue_number, **defaults)
        if defaults[PR_NUMBER] not in gh.pulls:
            _open_pr_for(
                gh,
                issue_number=self.issue_number,
                pr_number=defaults[PR_NUMBER],
            )
        if _review_subjects.APPROVED_SUBJECT not in defaults:
            _verified.verifies_the_approval(gh, issue)
        return gh, issue


class _FinalDocsFixture(_DocumentingWorkflowMixin):
    issue_number = 707
    pr_number = 71
    branch_name = _branch(issue_number)

    def _seeded(self, *, comments=(), **state):
        gh = FakeGitHubClient()
        issue = make_issue(self.issue_number, label=DOCUMENTING)
        issue.comments.extend(comments)
        gh.add_issue(issue)
        defaults = {
            PR_NUMBER: self.pr_number,
            "branch": self.branch_name,
            "dev_agent": DEV_AGENT,
            "dev_session_id": DEV_SESSION,
            "review_round": 2,
            "pr_last_comment_id": FINAL_DOCS_PR_WATERMARK,
        }
        defaults.update(state)
        gh.seed_state(self.issue_number, **defaults)
        if defaults[PR_NUMBER] not in gh.pulls:
            _open_pr_for(
                gh,
                issue_number=self.issue_number,
                pr_number=defaults[PR_NUMBER],
            )
        if _review_subjects.APPROVED_SUBJECT not in defaults:
            _verified.verifies_the_approval(gh, issue)
        return gh, issue
