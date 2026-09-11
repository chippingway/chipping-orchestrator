# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer and reviewer roads that reach a process, and how each is run.

The charge is taken at one boundary, so what is left to prove per road is that
the road GOES through that boundary carrying the issue it is spending. Nothing
about the circuit alone shows it: a stage that named some other budget would
still spawn and still charge something, and only driving the real handler says
whose count moved. So this table is the coverage -- a developer road added to
the tree and not to it is a road nothing holds to the meter.

Each entry is the world its stage spawns in plus the call that runs one tick
of it, and every driver takes the result the process comes back with, so the
same road answers for a run that finished, one the shutdown sweep killed, and
one an operator paused mid-flight.

The three roles that talk rather than deliver -- the decomposer, the question
stage, and the discussion stage -- are the sibling table in
`charged_conversation_roads.py`, on the same seeded ledger.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import AgentResult
from orchestrator.workflow.stages.documenting import handler as _documenting
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow import fixtures as _support
from tests.workflow.engine.charged_run_test_support import (
    DEV_SESSION,
    SHA_AFTER,
    SHA_BEFORE,
    ChargedRoad,
    Driven,
    human_reply,
    seed_issue,
)
from tests.workflow.git_owners import seam_patch

IMPLEMENTING_FRESH_ISSUE = 1570
IMPLEMENTING_RESUME_ISSUE = 1571
FIXING_ISSUE = 1572
DOCUMENTING_ISSUE = 1573
IN_REVIEW_ISSUE = 1574
CONFLICT_ISSUE = 1575
VALIDATING_ISSUE = 1576

_FIXING_PR = 72
_DOCUMENTING_PR = 73
_IN_REVIEW_PR = 74
_CONFLICT_PR = 75
_VALIDATING_PR = 76

_ACTION_COMMENT_ID = 900

_DEBOUNCE_SECONDS = 600

_DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"

_CONFLICT_FILE = "a.py"

_CHECKS_PASSED = "success"

# The pinned-state fields the seeds below share. Wire strings on live issues,
# so they are spelled once here rather than retyped per road.
_KEY_BRANCH = "branch"
_KEY_DEV_AGENT = "dev_agent"
_KEY_DEV_SESSION_ID = "dev_session_id"
_KEY_PR_NUMBER = "pr_number"
_KEY_REVIEW_ROUND = "review_round"

# A baseline that no longer describes the issue body, which is the drift the
# in_review stage resumes the developer on.
_STALE_CONTENT_HASH = "stale-hash"


def _drive_implementing_fresh(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        IMPLEMENTING_FRESH_ISSUE, label=_support.LABEL_IMPLEMENTING, **state,
    )
    mocks = case._run_implementing(
        github,
        issue,
        run_agent=agent_result,
        # The first reading decides there is no interrupted publication to
        # recover; the second is the commit this run made.
        has_new_commits=[False, True],
        push_branch=True,
    )
    return Driven(github, mocks, IMPLEMENTING_FRESH_ISSUE)


def _drive_implementing_resume(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        IMPLEMENTING_RESUME_ISSUE,
        label=_support.LABEL_IMPLEMENTING,
        comments=[human_reply()],
        stage={
            "awaiting_human": True,
            "last_action_comment_id": _ACTION_COMMENT_ID,
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
            _KEY_BRANCH: _support._issue_branch(IMPLEMENTING_RESUME_ISSUE),
        },
        **state,
    )
    mocks = case._run_implementing(
        github,
        issue,
        run_agent=agent_result,
        has_new_commits=[True],
        push_branch=True,
    )
    return Driven(github, mocks, IMPLEMENTING_RESUME_ISSUE)


def _drive_fixing(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        FIXING_ISSUE,
        label=_support.LABEL_FIXING,
        comments=[human_reply("please fix the docstring")],
        stage={
            _KEY_PR_NUMBER: _FIXING_PR,
            _KEY_BRANCH: _support._issue_branch(FIXING_ISSUE),
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
            _KEY_REVIEW_ROUND: 1,
            "pr_last_comment_id": 0,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
        },
        **state,
    )
    _support._open_pr_for(github, issue_number=FIXING_ISSUE, pr_number=_FIXING_PR)
    with patch.object(config, _DEBOUNCE_SETTING, _DEBOUNCE_SECONDS):
        mocks = case._run_fixing(
            github,
            issue,
            run_agent=agent_result,
            head_shas=(SHA_BEFORE, SHA_AFTER),
            push_branch=True,
        )
    return Driven(github, mocks, FIXING_ISSUE)


def _drive_documenting(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        DOCUMENTING_ISSUE,
        label=_support.LABEL_DOCUMENTING,
        stage={
            _KEY_PR_NUMBER: _DOCUMENTING_PR,
            _KEY_BRANCH: _support._issue_branch(DOCUMENTING_ISSUE),
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
        },
        **state,
    )
    _support._open_pr_for(
        github, issue_number=DOCUMENTING_ISSUE, pr_number=_DOCUMENTING_PR,
    )
    # Driven through the shared patch context directly: documenting is the one
    # road here whose handler no stage-family adapter already names.
    mocks = case._run(
        lambda: _documenting._handle_documenting(github, _support._TEST_SPEC, issue),
        run_agent=agent_result,
        head_shas=[SHA_BEFORE, SHA_AFTER],
        branch_ahead_behind=(0, 0),
        push_branch=True,
    )
    return Driven(github, mocks, DOCUMENTING_ISSUE)


def _drive_in_review(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        IN_REVIEW_ISSUE,
        label=_support.LABEL_IN_REVIEW,
        stage={
            _KEY_PR_NUMBER: _IN_REVIEW_PR,
            _KEY_BRANCH: _support._issue_branch(IN_REVIEW_ISSUE),
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
            _KEY_REVIEW_ROUND: 2,
            "pr_last_comment_id": 0,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
            "user_content_hash": _STALE_CONTENT_HASH,
        },
        **state,
    )
    _support._open_pr_for(github, issue_number=IN_REVIEW_ISSUE, pr_number=_IN_REVIEW_PR)
    mocks = case._run_in_review(
        github,
        issue,
        run_agent=agent_result,
        has_new_commits=True,
        push_branch=True,
        head_shas=[SHA_BEFORE, SHA_AFTER],
    )
    return Driven(github, mocks, IN_REVIEW_ISSUE)


def _drive_conflict(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        CONFLICT_ISSUE,
        label=_support.LABEL_RESOLVING_CONFLICT,
        stage={
            _KEY_PR_NUMBER: _CONFLICT_PR,
            _KEY_BRANCH: _support._issue_branch(CONFLICT_ISSUE),
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
            _KEY_REVIEW_ROUND: 2,
            "conflict_round": 0,
        },
        **state,
    )
    github.add_pr(FakePR(
        number=_CONFLICT_PR,
        head_branch=_support._issue_branch(CONFLICT_ISSUE),
        head=FakePRRef(sha=SHA_BEFORE),
        mergeable=False,
        check_state=_CHECKS_PASSED,
    ))
    fetched = MagicMock(returncode=0, stdout="0\n", stderr="")
    with (
        seam_patch("_rebase_base_into_worktree", MagicMock(
            return_value=(False, [_CONFLICT_FILE]),
        )),
        seam_patch("_git", MagicMock(return_value=fetched)),
        seam_patch("_git_hardened", MagicMock(return_value=fetched)),
    ):
        mocks = case._run_resolving_conflict(
            github,
            issue,
            run_agent=agent_result,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            push_branch=True,
            fetched_branch_tip=SHA_BEFORE,
        )
    return Driven(github, mocks, CONFLICT_ISSUE)


def _drive_validating(case, agent_result: AgentResult, **state) -> Driven:
    github, issue = seed_issue(
        VALIDATING_ISSUE,
        label=_support.LABEL_VALIDATING,
        stage={
            _KEY_PR_NUMBER: _VALIDATING_PR,
            _KEY_BRANCH: _support._issue_branch(VALIDATING_ISSUE),
            _KEY_DEV_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DEV_SESSION_ID: DEV_SESSION,
            _KEY_REVIEW_ROUND: 0,
        },
        **state,
    )
    _support._open_pr_for(
        github, issue_number=VALIDATING_ISSUE, pr_number=_VALIDATING_PR,
    )
    mocks = case._run_validating(github, issue, run_agent=agent_result)
    return Driven(github, mocks, VALIDATING_ISSUE)


IMPLEMENTING_FRESH = ChargedRoad(
    role="implementing-fresh",
    number=IMPLEMENTING_FRESH_ISSUE,
    label=_support.LABEL_IMPLEMENTING,
    drive=_drive_implementing_fresh,
    agent_result=_support._agent(session_id="sess-fresh", last_message="implemented"),
)

# The road a poisoned session is recovered on, and so the one launch here
# whose retry is a SECOND process inside the same tick.
IMPLEMENTING_RESUME = ChargedRoad(
    role="implementing-resume",
    number=IMPLEMENTING_RESUME_ISSUE,
    label=_support.LABEL_IMPLEMENTING,
    drive=_drive_implementing_resume,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="carried on"),
)

FIXING = ChargedRoad(
    role="fixing",
    number=FIXING_ISSUE,
    label=_support.LABEL_FIXING,
    drive=_drive_fixing,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="fixed"),
)

DOCUMENTING = ChargedRoad(
    role="documenting",
    number=DOCUMENTING_ISSUE,
    label=_support.LABEL_DOCUMENTING,
    drive=_drive_documenting,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="docs: updated"),
)

IN_REVIEW = ChargedRoad(
    role="in-review",
    number=IN_REVIEW_ISSUE,
    label=_support.LABEL_IN_REVIEW,
    drive=_drive_in_review,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="addressed"),
)

CONFLICT = ChargedRoad(
    role="resolving-conflict",
    number=CONFLICT_ISSUE,
    label=_support.LABEL_RESOLVING_CONFLICT,
    drive=_drive_conflict,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="resolved"),
)

VALIDATING = ChargedRoad(
    role="validating",
    number=VALIDATING_ISSUE,
    label=_support.LABEL_VALIDATING,
    drive=_drive_validating,
    agent_result=_support._agent(
        session_id="rev-sess", last_message=_support.REVIEW_APPROVED_MESSAGE,
    ),
)

# Every road a developer or a reviewer is reached through. The developer's
# fresh spawn, the resume each of the five stages that owns one makes, and the
# reviewer's fresh round.
ROADS = (
    IMPLEMENTING_FRESH,
    IMPLEMENTING_RESUME,
    FIXING,
    DOCUMENTING,
    IN_REVIEW,
    CONFLICT,
    VALIDATING,
)
