# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reviewer round an operator's reply bought, handed its subject and settled on return.

Driven through the validating owners that do it live, so the subject evidence
answers for is the one a reviewer is really handed. The issue parks on the
review cap and the operator answers with a bare grant: a control that still
counts as thread content, so the round it buys is due the thread through it,
past the baseline the settled report was written against. The reader hands
that round its subject over the report as it stands, the launch and the return
record it, and the return settles the reply -- moving the baseline onto the
requirements the reviewer read, past the report.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import prompt_context as _prompt_context, review_subjects as _review_subjects
from orchestrator.workflow.stages.validating import (
    awaiting as _awaiting,
    models as _models,
    review_records as _review_records,
    review_report as _review_report,
    reviewer as _reviewer,
    state as _state,
)
from tests.support.github.models import FakeComment, FakeUser
from tests.workflow.fixtures import _TEST_SPEC

# The bare operator reply that buys a round past the review cap.
GRANT = "/orchestrator add-review-rounds 1"

# What the review-cap road hands the tick on to once a grant buys the round.
_SPAWN_REVIEWER = "spawn_reviewer"


def settles_a_granted_round(case) -> _review_subjects.ReviewSubject:
    """Buy, hand, and settle one reviewer round for `case`; the subject its reviewer read."""
    parked = _grants_a_round(case)
    delivered = _prompt_context._delivered_thread(case.gh, case.issue, case.state)
    handed = _review_report._resolves_the_subject(
        case.gh, case.issue, case.state, case.pull_request.number, delivered,
    )
    if handed is None:
        raise AssertionError("the reader refused the round the grant bought")
    _review_records._records_the_launch(case.state, handed.subject)
    _review_records._records_the_return(case.state, None, None, handed.subject)
    _reviewer._settles_what_bought_the_round(case.state, parked, _models._ReviewerRun(
        wt=case.world.path,
        round_n=0,
        pr_number=case.pull_request.number,
        agent_result=AgentResult(None, "", 0, timed_out=False, stdout="", stderr=""),
        delivery=delivered,
        subject=handed.subject,
        resolved_over=handed.resolved_over,
    ))
    case.gh.write_pinned_state(case.issue, case.state)
    return handed.subject


def _grants_a_round(case) -> _models._AwaitingValidation:
    """Park `case` on the review cap and answer it with a bare grant, as the operator does."""
    case.state.set(_state._PARK_REASON, _state._REASON_REVIEW_CAP)
    case.state.set("awaiting_human", True)
    case.state.set(_state._REVIEW_ROUND, config.MAX_REVIEW_ROUNDS)
    case.gh.write_pinned_state(case.issue, case.state)
    author = FakeUser(case.issue.user.login)
    case.issue.comments.append(
        FakeComment(id=case.gh._next_comment_id(case.issue), body=GRANT, user=author),
    )
    parked = _models._AwaitingValidation.build(case.gh, _TEST_SPEC, case.issue, case.state)
    if _awaiting._review_cap_awaiting_action(parked) != _SPAWN_REVIEWER:
        raise AssertionError("the grant bought no reviewer round")
    case.gh.write_pinned_state(case.issue, case.state)
    return parked
