# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt a park over a manifest correction ends on, and the park a later tick owes without saying it twice.

Every park taken over an attempt -- the correction's own answer parked, or an
attempt armed with no launch granted and given up behind the ordinary park --
ends on a hidden receipt naming the issue and the source invocation's random
nonce (`receipted`), which no agent answer can know to forge. Each of those
parks lands before the attempt is resolved (`correction_settlement`), and a
park whose write was lost leaves its notice on the thread with nothing
recording it. The tick that finds that attempt owed a park it does not stand
on (`correction_reconcile`) asks the thread past the reply boundary for the
receipt first (`parks_once`): where a comment of ours carries it, the park is
recorded over that notice -- the boundary standing on it, so a reply below it
was written before its question and one above it is its answer -- and nothing
is said again; otherwise the notice is posted, receipt and all. A thread
nobody could read says nothing and records nothing, and the next tick asks
again.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    ready_readings as _ready_readings,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RECEIPT = "<!--orchestrator-decomposer-correction:issue={issue}:source={nonce}-->"


def receipted(message: str, attempt: _records.CorrectionAttempt | None) -> str:
    """`message` ending on `attempt`'s receipt, or as it is where the park is over no attempt."""
    if attempt is None:
        return message
    return f"{message}\n\n{_receipt(attempt)}"


def parks_once(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt, message: str,
) -> bool:
    """Park on `message` for `attempt`, or record the park a notice of ours already said; False where unread.

    The park is written whole either way. Only a park this call posts is
    announced on the event stream: one recorded over an earlier notice was
    announced as that notice went out.
    """
    try:
        thread = list(
            gh.comments_after(issue, state.get(_state._LAST_ACTION_COMMENT_ID), state_comment_id=state.comment_id),
        )
    except Exception:
        log.exception("issue=#%d could not be read for its manifest correction's park; holding it", issue.number)
        return False
    said = _ready_readings.found(gh, state, thread, _receipt(attempt))
    if said is None:
        _guards._park_awaiting_human(
            gh, issue, state, receipted(message, attempt),
            reason="decomposer_invalid_manifest",
            agent_role="decomposer",
            session_id=attempt.source.session,
            retry_count=_guards._safe_int(state.get("retry_count")),
        )
    else:
        state.set(_state._AWAITING_HUMAN, True)
        state.set(_state._PARK_REASON, None)
        state.set(_state._LAST_ACTION_COMMENT_ID, said)
    gh.write_pinned_state(issue, state)
    return True


def _receipt(attempt: _records.CorrectionAttempt) -> str:
    """The hidden receipt a park over `attempt` ends on."""
    source = attempt.source.invocation
    return _RECEIPT.format(issue=source.issue, nonce=source.nonce)
