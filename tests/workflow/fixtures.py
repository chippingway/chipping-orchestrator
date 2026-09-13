# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures shared across the workflow tests, re-exported explicitly.

Each name below is defined by the leaf beside it -- the event names, the two
label vocabularies, the repo spec and backend values, the pinned-state keys and
role names, the verdict messages, the provider-failure messages, the
recovery-follow-up wording, the pinned fields an authorized settlement leaves,
the value builders, and the hermetic patch context a stage handler runs
inside. This module is the one import site the tests that
span several of those leaves reach them through.
"""
from __future__ import annotations

from tests.workflow import (
    agent_failure_values as _agent_failure_values,
    authorized_exemption as _authorized_exemption_values,
    other_labels as _other_labels,
    patch_models as _patch_models,
    patch_runner as _patch_runner,
    recovery_followup as _recovery_followup,
    repo_values as _repo_values,
    stage_labels as _stage_labels,
    stage_names as _stage_names,
    state_values as _state_values,
    value_helpers as _value_helpers,
    verdict_values as _verdict_values,
)
from tests.workflow.engine import event_values as _event_values

EVENT_AGENT_EXIT = _event_values.EVENT_AGENT_EXIT
EVENT_AGENT_SPAWN = _event_values.EVENT_AGENT_SPAWN
EVENT_AGENT_TRAJECTORY = _event_values.EVENT_AGENT_TRAJECTORY
EVENT_PR_CLOSED_WITHOUT_MERGE = _event_values.EVENT_PR_CLOSED_WITHOUT_MERGE
EVENT_PR_MERGED = _event_values.EVENT_PR_MERGED
EVENT_SKILL_TRIGGERED = _event_values.EVENT_SKILL_TRIGGERED
EVENT_STAGE_ENTER = _event_values.EVENT_STAGE_ENTER
EVENT_STAGE_EVALUATION = _event_values.EVENT_STAGE_EVALUATION

LABEL_BLOCKED = _other_labels.LABEL_BLOCKED
LABEL_DONE = _other_labels.LABEL_DONE
LABEL_READY = _other_labels.LABEL_READY
LABEL_REJECTED = _other_labels.LABEL_REJECTED
LABEL_RESOLVING_CONFLICT = _other_labels.LABEL_RESOLVING_CONFLICT
LABEL_UMBRELLA = _other_labels.LABEL_UMBRELLA

LABEL_DECOMPOSING = _stage_labels.LABEL_DECOMPOSING
LABEL_DISCUSSION = _stage_labels.LABEL_DISCUSSION
LABEL_DOCUMENTING = _stage_labels.LABEL_DOCUMENTING
LABEL_FIXING = _stage_labels.LABEL_FIXING
LABEL_IMPLEMENTING = _stage_labels.LABEL_IMPLEMENTING
LABEL_IN_REVIEW = _stage_labels.LABEL_IN_REVIEW
LABEL_QUESTION = _stage_labels.LABEL_QUESTION
LABEL_VALIDATING = _stage_labels.LABEL_VALIDATING

STAGE_DECOMPOSING = _stage_names.STAGE_DECOMPOSING
STAGE_DISCUSSION = _stage_names.STAGE_DISCUSSION
STAGE_DOCUMENTING = _stage_names.STAGE_DOCUMENTING
STAGE_FIXING = _stage_names.STAGE_FIXING
STAGE_IMPLEMENTING = _stage_names.STAGE_IMPLEMENTING
STAGE_IN_REVIEW = _stage_names.STAGE_IN_REVIEW
STAGE_QUESTION = _stage_names.STAGE_QUESTION
STAGE_RESOLVING_CONFLICT = _stage_names.STAGE_RESOLVING_CONFLICT
STAGE_VALIDATING = _stage_names.STAGE_VALIDATING

BACKEND_CLAUDE = _repo_values.BACKEND_CLAUDE
BASE_TIP_SHA = _repo_values.BASE_TIP_SHA
BACKEND_CODEX = _repo_values.BACKEND_CODEX
MEASURED_BASE_SHA = _repo_values.MEASURED_BASE_SHA
SHA_LENGTH = _repo_values.SHA_LENGTH
DEFAULT_PR_HEAD_SHA = _patch_models.DEFAULT_PR_HEAD_SHA
MEASURED_CANDIDATE_SHA = _repo_values.MEASURED_CANDIDATE_SHA
STATE_CLOSED = _repo_values.STATE_CLOSED
STATE_OPEN = _repo_values.STATE_OPEN
TEST_BASE_BRANCH = _repo_values.TEST_BASE_BRANCH
TEST_REPO_SLUG = _repo_values.TEST_REPO_SLUG
_FAKE_WT = _repo_values._FAKE_WT
_TEST_SPEC = _repo_values._TEST_SPEC

AGENT_RUN_CHARGE_WRITES = _state_values.AGENT_RUN_CHARGE_WRITES
KEY_AWAITING_HUMAN = _state_values.KEY_AWAITING_HUMAN
KEY_ISSUE_AGENT_RUNS = _state_values.KEY_ISSUE_AGENT_RUNS
KEY_ISSUE_TOTAL_TOKENS = _state_values.KEY_ISSUE_TOTAL_TOKENS
KEY_LAST_ACTION_COMMENT_ID = _state_values.KEY_LAST_ACTION_COMMENT_ID
KEY_PARENT_NUMBER = _state_values.KEY_PARENT_NUMBER
KEY_PARK_REASON = _state_values.KEY_PARK_REASON
ROLE_DEVELOPER = _state_values.ROLE_DEVELOPER
ROLE_REVIEWER = _state_values.ROLE_REVIEWER

AGENT_TIMEOUT_PARK = _recovery_followup.AGENT_TIMEOUT
LAST_ACTION_COMMENT_ID = _recovery_followup.LAST_ACTION_COMMENT_ID
NO_ACTION_LINE = _recovery_followup.NO_ACTION_LINE
OUTCOME_CLEARED = _recovery_followup.OUTCOME_CLEARED
OUTCOME_PUSHED = _recovery_followup.OUTCOME_PUSHED
PUSH_FAILED_PARK = _recovery_followup.PUSH_FAILED
PUSH_RETRIED_DETAIL = _recovery_followup.PUSH_RETRIED_DETAIL
RECOVERED_PREFIX = _recovery_followup.RECOVERED_PREFIX
REVIEWER_FAILED_PARK = _recovery_followup.REVIEWER_FAILED
REVIEWER_RESPAWN_DETAIL = _recovery_followup.REVIEWER_RESPAWN_DETAIL
REVIEWER_TIMEOUT_PARK = _recovery_followup.REVIEWER_TIMEOUT
TIMEOUT_EMPTY_DETAIL = _recovery_followup.TIMEOUT_EMPTY_DETAIL
TIMEOUT_PUSHED_DETAIL = _recovery_followup.TIMEOUT_PUSHED_DETAIL
_RecoveryFollowupAssertions = _recovery_followup._RecoveryFollowupAssertions
_WriteFailingAfter = _recovery_followup._WriteFailingAfter

PROVIDER_OVERLOAD_MENTION = _agent_failure_values.PROVIDER_OVERLOAD_MENTION
PROVIDER_OVERLOAD_MESSAGE = _agent_failure_values.PROVIDER_OVERLOAD_MESSAGE
PROVIDER_UNAVAILABLE_PHRASE = _agent_failure_values.PROVIDER_UNAVAILABLE_PHRASE
SESSION_LIMIT_MESSAGE = _agent_failure_values.SESSION_LIMIT_MESSAGE
SESSION_LIMIT_PHRASE = _agent_failure_values.SESSION_LIMIT_PHRASE

REVIEW_APPROVED_MESSAGE = _verdict_values.REVIEW_APPROVED_MESSAGE
REVIEW_CHANGES_REQUESTED_MESSAGE = _verdict_values.REVIEW_CHANGES_REQUESTED_MESSAGE
VERDICT_APPROVED = _verdict_values.VERDICT_APPROVED
VERDICT_CHANGES_REQUESTED = _verdict_values.VERDICT_CHANGES_REQUESTED
VERDICT_UNKNOWN = _verdict_values.VERDICT_UNKNOWN

_analytics_records = _value_helpers._analytics_records
_fake_worktree = _value_helpers._fake_worktree
_iso_hours_ago = _value_helpers._iso_hours_ago
_issue_branch = _value_helpers._issue_branch
_manifest = _value_helpers._manifest
_open_pr_for = _value_helpers._open_pr_for
_state_with_pr_number = _value_helpers._state_with_pr_number

_authorize_command = _authorized_exemption_values._authorize_command
_authorized_exemption = _authorized_exemption_values._authorized_exemption
_damaged_authorization = _authorized_exemption_values._damaged_authorization
_fabricated_authorization = _authorized_exemption_values._fabricated_authorization
_legacy_exemption = _authorized_exemption_values._legacy_exemption

_agent = _patch_models._agent
_PatchedWorkflowMixin = _patch_runner._PatchedWorkflowMixin
