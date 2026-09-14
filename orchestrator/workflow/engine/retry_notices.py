# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deliver and reconcile daily retry-cap notices against the actual issue thread.

A bot-authored matching notice settles the owed sentence without repeating it.
An unreadable thread keeps it owed; successful delivery advances only the
watermark proved by the notice and emits the corresponding audit phase."""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    retry_park_state as _retry_park_state,
    retry_values as _retry_values,
)

log = logging.getLogger("orchestrator.workflow")



def _deliver_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Say what a standing park is for, if the thread has not been told.

    Idempotent by what it clears rather than by how often it is called: the
    obligation is dropped by the post that discharges it, so a notice reaches
    the thread once per park.

    The obligation is dropped between the post and the caller's write, which
    is the only order that fails the right way: a crash in that window leaves
    a sentence owed by a thread that already has it, which the reconciliation
    below settles, rather than dropping one nobody ever said.

    The mention and the watermark ratchet go through the shared park so this
    notice moves the response boundary every other park in this repository
    moves -- a comment written before it would otherwise read as an answer to
    it. That helper clears `park_reason` by contract, so the stable reason is
    re-stamped after it.
    """
    owed = _retry_park_state._owed_notice(state)
    if owed is None:
        return False
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} {owed}",
        reason=_retry_values.PARK_RETRY_CAP,
    )
    state.set(_retry_values._PARK_REASON, _retry_values.PARK_RETRY_CAP)
    _retry_park_state._settle_notice(state)
    _emit_phase(gh, issue, state, _retry_values.RetryCapPhase.DELIVERED)
    return True


def _reconcile_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _retry_values.NoticeReading:
    """Discharge an obligation the thread shows was already discharged.

    Asked before anything acts on the obligation, because a pinned write that
    failed after a post that landed claims the opposite of what the issue
    holds -- and the issue is the one of the two that cannot be wrong about
    what was said. Both halves that write was carrying are put back: the
    sentence is marked said, and the watermark is ratcheted to the comment
    that actually carried it.

    Nothing is posted and nothing is decided. A notice the thread does not
    carry is left exactly as it was, for the delivery to say -- and a thread
    that could not be read is reported as exactly that, since a caller told
    "not there" would say a sentence the issue may already carry.

    An obligation nobody holds reads as `SAID`: there is nothing owed, and
    nothing for the delivery below to do about it either.
    """
    owed = _retry_park_state._owed_notice(state)
    if owed is None:
        return _retry_values.NoticeReading.SAID
    delivered = _delivered_id(gh, issue, state, owed)
    if delivered is _retry_values._UNREADABLE_THREAD:
        return _retry_values.NoticeReading.UNREADABLE
    if delivered is None:
        return _retry_values.NoticeReading.UNSAID
    log.info(
        "issue=#%d already carries its retry-cap notice; recording it as "
        "said rather than saying it twice",
        issue.number,
    )
    _retry_park_state._settle_notice(state)
    prior = state.get(_retry_values._LAST_ACTION_COMMENT_ID)
    if not isinstance(prior, int) or delivered > prior:
        state.set(_retry_values._LAST_ACTION_COMMENT_ID, delivered)
    _emit_phase(gh, issue, state, _retry_values.RetryCapPhase.RECONCILED)
    return _retry_values.NoticeReading.SAID


def _emit_phase(
    gh: GitHubClient, issue: Issue, state: PinnedState, phase: _retry_values.RetryCapPhase,
) -> None:
    """Record which step of a retry-cap park this tick took.

    The stage is read off the park rather than off the label, because the
    budget is shared and the label an issue wears while parked is not always
    the stage whose spawn ran out. A park carrying no readable stage reports
    none at all, which the record builder drops -- a phase with no stage is
    still countable, and a guessed one is worse than a missing one.
    """
    gh.emit_event(
        _retry_values._RETRY_CAP_EVENT,
        issue_number=issue.number,
        stage=_retry_park_state._park_stage(state),
        phase=phase,
    )


def _delivered_id(
    gh: GitHubClient, issue: Issue, state: PinnedState, message: str,
) -> int | None | object:
    """The id of this notice's own comment on the thread, if it is there.

    The whole sentence is matched rather than a marker, because this notice
    carries none of its own and the mention prefixed to it is not part of what
    was recorded. The highest match is reported, so the watermark is repaired
    to the last thing said rather than the first.

    And the receipt has to be OURS. The sentence is plain text on a public
    thread, so anybody can write it -- and read from anybody, it would
    discharge an obligation nobody discharged: the park would stand with its
    notice marked said, the watermark would be dragged past whatever else was
    written under it, and the human the park was taken for would never be
    told. So the author is checked through the same owner every other receipt
    this repository reads off a thread goes through
    (`github.comments.authored_by_us`), and a client with no authenticated
    login of its own to compare against falls back to the text alone exactly
    as those do.

    A read that could not be taken answers `_UNREADABLE_THREAD`, which is a
    different thing from finding nothing: the notice stays owed either way,
    but only one of the two licenses a comment. Read as a miss, a request that
    failed inside the very window where the sentence is already on the thread
    would post it a second time.
    """
    try:
        thread = gh.comments_after(issue, state.get(_retry_values._LAST_ACTION_COMMENT_ID))
    except Exception:
        log.exception(
            "issue=#%d could not be read for a retry-cap notice already "
            "posted; leaving it owed and saying nothing this tick rather "
            "than repeating a sentence the thread may already carry",
            issue.number,
        )
        return _retry_values._UNREADABLE_THREAD
    bot_login = getattr(gh, "_bot_login", None)
    said = [
        issue_comment.id
        for issue_comment in thread
        if message in (issue_comment.body or "")
        and authored_by_us(issue_comment, bot_login=bot_login)
    ]
    return max(said) if said else None
