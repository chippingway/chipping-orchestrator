# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks a returned reviewer's verdict takes when it may not be acted on.

Two refusals stop a verdict of a subject that still stands, and both are the
reviewer's round to redo rather than a developer's to answer. An approval that
relies on no evidence that passed and is current (`unverified_approvals`)
parks under `reviewer_unverified` before the verify gate, the approval record,
or the squash. A verdict the pinned comment has no room to persist, with the
evidence transaction its commands were minted as, parks under
`reviewer_unrecorded` before anything is published or acted on: a disposition
nothing durable backs would be answered again by a second reviewer the moment
the tick died, which is the rerun the persisted verdict exists to prevent.

Neither retries itself. A bare `/orchestrator continue` buys a fresh reviewer
(`awaiting._reviewer_retry_awaiting_action`), and a reply with words in it is
requirements the report never saw, which reach the developer first as on every
reviewer-side park. Each park drops the verdict it refuses in its own write.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_verdicts as _verdicts,
    state as _state,
)

_RETRY = "reply `/orchestrator continue` to run a fresh reviewer."

_UNRECORDED = (
    "the reviewer's verdict, or the verification evidence it reported, could "
    "not be recorded on the pinned comment, which has no room for it, so "
    f"neither was acted on. Free room on the pinned comment, then {_RETRY}"
)

_LAST_REVIEW_SESSION_ID = "last_review_session_id"


def parks_unverified(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    refusal: str,
) -> None:
    """Park an approval that relies on no valid evidence, dropping the verdict it left."""
    words = (
        "the reviewer approved without the verification evidence an approval "
        f"requires: {refusal}. The approval was not acted on; {_RETRY}"
    )
    _parks(gh, issue, state, run, (_state._REASON_REVIEWER_UNVERIFIED, words))


def parks_unrecorded(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
) -> None:
    """Park a verdict the pinned comment has no room to persist, acting on nothing."""
    _parks(gh, issue, state, run, (_state._REASON_REVIEWER_UNRECORDED, _UNRECORDED))


def _parks(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple[str, str],
) -> None:
    """File one reviewer-side park under `park`'s reason and words, in one write."""
    reason, words = park
    _verdicts.drops_the_verdict(state)
    _guards._park_awaiting_human(
        gh,
        issue,
        state,
        f"{config.HITL_MENTIONS} {words}",
        reason=reason,
        agent_role="reviewer",
        session_id=state.get(_LAST_REVIEW_SESSION_ID),
        review_round=run.round_n,
        retry_count=_guards._safe_int(state.get("retry_count")),
        pr_number=_guards._safe_int(run.pr_number),
        bounded=True,
    )
    # Re-set behind the guard, which clears whatever reason it found: the
    # awaiting-human branch reads it to hand the retry to a fresh reviewer.
    state.set(_state._PARK_REASON, reason)
    gh.write_pinned_state(issue, state)
