# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for implementing drift tests."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.late_split import formats as _formats
from tests.support import fakes
from tests.workflow import fixtures
from tests.workflow.stages import implementing_fixing_test_cases

FakeComment = fakes.FakeComment
FakeGitHubClient = fakes.FakeGitHubClient
FakeLabel = fakes.FakeLabel
FakeUser = fakes.FakeUser
IssueScenario = implementing_fixing_test_cases.IssueScenario
posted_comment_contains = implementing_fixing_test_cases.posted_comment_contains
make_issue = fakes.make_issue
AGENT_RUN_CHARGE_WRITES = fixtures.AGENT_RUN_CHARGE_WRITES
LABEL_IMPLEMENTING = fixtures.LABEL_IMPLEMENTING
LABEL_VALIDATING = fixtures.LABEL_VALIDATING
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_iso_hours_ago = fixtures._iso_hours_ago
_reported = fixtures._reported
_issue_branch = fixtures._issue_branch

RUN_AGENT = "run_agent"
USER_CONTENT_HASH = "user_content_hash"
AWAITING_HUMAN = "awaiting_human"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
# A baseline that differs from the issue's current content, spelled the way
# the drift owner spells one: a whole SHA-256 digest. The shape matters
# because a report recorded on this road copies the baseline into its own
# record, which reads a requirements revision at exactly that width.
_DIGEST_WIDTH = max(_formats.DIGEST_LENGTHS)

STALE_CONTENT_HASH = "5" * _DIGEST_WIDTH
DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"
FRESH_SESSION = "new-sess"
IMPLEMENTED_MESSAGE = _reported()
UPDATED_REQUIREMENTS = "new requirements"
# The body a pre-session case is edited to, spelled once: three of those cases
# assert on the prompt it reaches, and one on the prompt it does not.
EDITED_BODY = "updated requirements"
IMPLEMENTER_PROMPT_FRAGMENT = "You are the implementer"
CONTINUE_COMMAND = "/orchestrator continue"
DRIFT_RESUME_ISSUE = 60
FRESH_DRIFT_ISSUE = 61
INTERRUPTED_DRIFT_ISSUE = 62
RECOVERED_COMMITS_ISSUE = 850
NO_SESSION_RECOVERED_ISSUE = 860
NO_SESSION_FRESH_ISSUE = 861
AWAITING_BODY_DRIFT_ISSUE = 1200
AWAITING_COMMENT_DRIFT_ISSUE = 1210
CONTINUE_RETRY_ISSUE = 730
CONTINUE_QUESTION_ISSUE = 731
CONTINUE_GUIDED_ISSUE = 732
HUMAN_COMMENT_ID = 500
PICKUP_COMMENT_ID = 900
COMMAND_COMMENT_ID = 9000
PRIOR_ACTION_WATERMARK = 8000

# The issue the settlement cases run on, and the words on its thread: the
# guidance an edit arrives with, the ACK and the question a commit-less resume
# can answer with, and a reply written while the agent is out.
SETTLEMENT_ISSUE = 63
TRUSTED_AUTHOR = "alice"
PARK_REASON = "park_reason"
PARK_RETRY_CAP = "retry_cap"
STALE_RECOVERED_WORK = "stale_recovered_work"
GUIDANCE = "and add a test for the retry"
ACK_REPLY = "ACK: the existing commits already cover it"
QUESTION_REPLY = "which of the two did you mean?"
LANDED_MID_RUN = "actually, hold on"

# A comment far past the 4000-character excerpt bound, ending in words a
# prompt can be searched for: what the bound keeps is the tail, so everything
# above it is dropped from the prompt and left unread by the mark.
_PAST_THE_BOUND = 5000
_BEYOND_THE_BOUND = "b" * _PAST_THE_BOUND
OVERSIZED_TAIL = "and the tail survives"
OVERSIZED_REPLY = f"{_BEYOND_THE_BOUND} {OVERSIZED_TAIL}"


def _paused_mid_run(github, paused: bool, number: int = SETTLEMENT_ISSUE):
    """The freshly fetched view a live-pause guard reads after a run returns.

    Nothing is patched for an unpaused case, so the guard reads the client the
    tick was given and answers as it does in production.
    """
    if not paused:
        return contextlib.nullcontext()
    view = make_issue(number, label=LABEL_IMPLEMENTING)
    view.labels.append(FakeLabel(PAUSED_LABEL))
    return patch.object(github, "get_issue", MagicMock(return_value=view))


def _seed_parked_implementing(
    number: int,
    *,
    park_reason,
    command_body=CONTINUE_COMMAND,
    drift_neutral=False,
):
    gh = FakeGitHubClient()
    issue = make_issue(number, label=LABEL_IMPLEMENTING, body="the requirements")
    command = FakeComment(
        id=COMMAND_COMMENT_ID,
        body=command_body,
        user=FakeUser("dave"),
    )
    issue.comments.append(command)
    gh.add_issue(issue)
    content_hash = _content_hash._compute_user_content_hash(issue, set()) if drift_neutral else STALE_CONTENT_HASH
    gh.seed_state(
        number,
        user_content_hash=content_hash,
        dev_agent=DEV_AGENT,
        dev_session_id=DEV_SESSION,
        awaiting_human=True,
        park_reason=park_reason,
        silent_park_count=1,
        last_action_comment_id=PRIOR_ACTION_WATERMARK,
        branch=_issue_branch(number),
    )
    return gh, issue
