# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The notice a base rewrite's recovery park says, said once however often the park is made again.

Every recovery park posts its notice and files its `park_awaiting_human`
event before it records the park (`rewrite_recovery_parks.lands_a_park`), so
a tick lost between the two, or a record that did not land, leaves the
attempt standing for the next tick's recovery to park again -- over a notice
already said. Posted afresh, that notice and its event would be said twice.

So the conversation past the watermark is read first for this very notice of
ours (`parks_awaiting_human`). One found is taken in as a post of it would
be: the issue marked awaiting a human, the watermark moved to it, and the
comment entered in the ledger, so the park lands over it with nothing posted
again. Its event is filed only where the event stream carries none naming
that notice, which every recovery park's event does (`notice_id`); a stream
that would not read files nothing, so nothing is filed twice. With no audit
log the stream is this process's tail alone, so the notice said is taken as
its event filed -- once at most, never twice: a process lost between the
notice and its event files none, while one whose post raised still owes it
(`owed_events`). A conversation that would not read raises, as a post
that raised does, and nothing is parked.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github import events as _github_events
from orchestrator.github.comments import authored_by_us
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    owed_events as _owed_events,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The event a park files.
_PARKED = "park_awaiting_human"


def parks_awaiting_human(context: _AutoRebaseRecoveryContext, message: str, reason: str) -> None:
    """Mark `context`'s issue awaiting a human over `message`: posted, or taken in where it is already said.

    Staged on the tick's state as every park stages it
    (`guards._park_awaiting_human`), the post's event naming the notice, so a
    later park of the same attempt finds both. Where the conversation past
    the watermark already carries this notice of ours, it is taken in instead
    and its event filed only where the stream lacks it. Raises where the
    conversation would not read.
    """
    state = context.state
    said = _said(context, message)
    if said is None:
        _guards._park_awaiting_human(context.gh, context.issue, state, message, reason=reason, names_the_notice=True)
        return
    state.set(_base_sync_state._AWAITING_HUMAN, True)
    state.set(_base_sync_state._PARK_REASON, None)
    state.set(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, said)
    _comments._track_orchestrator_comment(state, said)
    _files_the_event(context, said, reason)


def _said(context: _AutoRebaseRecoveryContext, message: str) -> int | None:
    """The id of `message`, a notice of ours the conversation carries past the watermark, the newest; None for none."""
    watermark = context.state.get(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID) or 0
    thread = context.gh.comments_after(context.issue, watermark, state_comment_id=context.state.comment_id)
    bot = getattr(context.gh, "_bot_login", None)
    ours = [comment for comment in thread if authored_by_us(comment, bot_login=bot)]
    said = [comment.id for comment in ours if message in (comment.body or "")]
    return said[-1] if said else None


def _files_the_event(context: _AutoRebaseRecoveryContext, notice: int, reason: str) -> None:
    """File the `park_awaiting_human` event of the park whose notice `notice` was said, where the stream lacks it.

    With no audit log the notice said is taken as its event filed, save one
    this process owes (`owed_events.unfiled`): once at most, never twice.
    """
    issue_number = context.issue.number
    named = {"reason": reason, "notice_id": notice}
    found = _github_events.filed(context.gh, _PARKED, issue_number=issue_number, **named)
    if found is None:
        log.warning(
            "issue=#%d could not read the event stream back for its recovery park's notice %d; "
            "filing nothing again",
            issue_number, notice,
        )
        return
    if found or not _owed_events.unfiled(context.gh, _PARKED, issue_number=issue_number, **named):
        log.info(
            "issue=#%d recovery park notice %d already said, its event filed or, with no audit log, taken as filed; "
            "posting nothing", issue_number, notice,
        )
        return
    stage = stage_name(context.gh.workflow_label(context.issue))
    context.gh.emit_event(_PARKED, issue_number=issue_number, stage=stage, **named)
    _owed_events.pays(context.gh, _PARKED, issue_number=issue_number, **named)
