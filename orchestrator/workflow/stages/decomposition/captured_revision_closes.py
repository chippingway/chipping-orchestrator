# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The closes a captured late revision's recovery reads, kept until the cycle they end reads cancelled.

A close a poll observed while a worker held the issue is latched process-wide
(`engine/observations`), and every barrier of a late cycle asks that latch,
since GitHub would answer a reopening differently. The recovery's own fetches
of the issue can read it closed too -- the admission's, the dispatcher's
first and every one a strict edit asks again, and the owner read behind the
handoff -- and the admission answers such a close only as the effect it
proves, a retirement or a hold: forgotten there, a reopening the next fetch
shows would hand the capture on for a cycle a close ended.

So the dispatcher decides a late revision's capture over a client that keeps
any close a fetch of the issue reads (`engine/completion_closes`), and hands a
close its admission read here (`closed`) in place of what it decided. A
capture admitted with none read carries that client on (`seeing`), the
recovery asks a poll's latch before anything else (`stops`), and finishes the
capture inside `rereading`: every strict edit there asks last, behind the
question's every request, whether the issue was closed for the revision's
cycle either way (`unlatched`), and a close either way ends the cycle as the
block is left, however it is left. Wherever a close is read, the cancellation
is written over the comment read again -- past the write a hold kept out of
the recovery's own -- and confirmed there. Where it is not -- the comment would
not read, reads as another record, or refused the write -- the close is
handed to the process's latch, scoped to the cycle the recovery admitted, so
every later barrier and dispatch of this process reads that cycle ended, a
reopening included, until the cleanup pass the latch routes the issue to
settles it.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from dataclasses import replace
from functools import partial

from orchestrator.github import client as _client
from orchestrator.workflow.engine import (
    completion_closes as _completion_closes,
    completion_recovery_models as _recovery_models,
    observations as _observations,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_owner as _late_owner,
    late_owner_reading as _late_owner_reading,
    late_owner_settlement as _late_owner_settlement,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import captured_rereads as _rereads

log = logging.getLogger("orchestrator.workflow")


def seeing(admitted: _recovery_models.AdmittedCompletion) -> _recovery_models.AdmittedCompletion:
    """`admitted` over a client that keeps any close a fetch of its issue reads, for `unlatched` to answer.

    The one the dispatcher admitted it through, where it was
    (`engine/completion_closes.watching`), so a close kept there is not
    forgotten by a fresh client.
    """
    if isinstance(admitted.gh, _completion_closes.SeesItsCloses):
        return admitted
    return replace(admitted, gh=_completion_closes.SeesItsCloses(admitted.gh, admitted.issue.number))


def closed(gh: _client.GitHubClient, spec, issue, state) -> bool:
    """End the cycle `state` names, a fetch of `issue` having read it closed, or keep that close latched for it; True.

    The dispatcher's recovery hands this a late revision's capture whose
    admission read its issue closed at any of its fetches, in place of what
    it decided (`engine/completion_closes.CLOSE_OWNERS`), and this recovery
    asks it as it ends behind a close (`_ends_behind`). Nothing of the
    capture is finished, retired, or handed on: the cycle is cancelled over
    the pinned comment read again (`_ended_again`), and where that reading
    does not confirm it, the close is latched for the cycle in this
    process's close latch, for every later barrier and dispatch to end it on.

    Only the cycle and the comment's identity are taken off `state`: the
    recovery's own state may already stage a cancellation a hold kept out of
    its write, so whether the cycle reads ended is the comment's to say.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return True
    admitted = _LateContext(gh=gh, spec=spec, issue=issue, state=state, generation=generation)
    if _ended_again(admitted):
        return True
    log.warning(
        "issue=#%d its captured late revision's recovery read a close of cycle %d it could not record as ended; "
        "latching that close for every later barrier of this process to end the cycle on",
        issue.number, generation.cycle_id,
    )
    _observations.observe_close(spec.slug, issue.number, fresh=True)
    _observations.scope_close(spec.slug, issue.number, generation.cycle_id)
    return True


def stops(context: _LateContext) -> bool:
    """Whether a close a poll latched ends the revision's cycle before the recovery finishes anything of it.

    Asked first, ahead of every reading the recovery takes, as each late
    barrier asks it (`late_owner._latch_stops`): the cancellation is written
    there, and nothing of the run is finished.
    """
    return _late_owner._latch_stops(context) is not None


@contextlib.contextmanager
def rereading(admitted: _recovery_models.AdmittedCompletion, recovered: _LateContext) -> Iterator[None]:
    """Finish `admitted` inside its rereads, each strict edit asked last of a close; the cycle ended behind one.

    Every strict edit made inside the block is held to the admission read
    again (`implementing/captured_rereads`, `every_edit`) and, last, to
    `unlatched`; and as the block is left, by a return or by anything it
    raised, a close observed behind its reads ends the cycle, or stays
    latched for it (`_ends_behind`).
    """
    try:
        with _rereads.rereads(admitted, every_edit=True, also=partial(unlatched, admitted, recovered)):
            yield
    finally:
        _ends_behind(admitted, recovered)


def unlatched(admitted: _recovery_models.AdmittedCompletion, context: _LateContext) -> bool:
    """Whether the issue reads closed for the revision's cycle to nothing: no poll's latch, and no fetch `seeing` kept.

    A close the recovery's own fetch read -- the admission's, asked again
    behind a strict edit's walk, among them -- outranks every later reading,
    as a poll's latch does: a reopening a later fetch shows is no answer to
    it, so every edit behind it is held and the cycle ends (`_ends_behind`).
    """
    seen = isinstance(admitted.gh, _completion_closes.SeesItsCloses) and admitted.gh.closed
    return not (seen or _late_owner_reading._latched_close(context))


def _ends_behind(admitted: _recovery_models.AdmittedCompletion, recovered: _LateContext) -> None:
    """End the cycle a close observed behind the recovery's reads, if one was, and keep that close until it is.

    One was where the issue reads closed for the cycle (`unlatched`), or
    where `recovered` ended the cycle in a state a hold then withheld. Such a
    close ends the cycle whatever controls the issue carries and whatever a
    later fetch shows, written over a fresh reading of the same comment as
    the latch asked at the top of the recovery writes it, or kept latched
    where that reading does not confirm it (`closed`).
    """
    withheld = recovered.generation.cancelled and recovered.state.withheld
    if withheld or not unlatched(admitted, recovered):
        closed(admitted.gh, admitted.spec, admitted.issue, admitted.state)


def _ended_again(admitted: _LateContext) -> bool:
    """Cancel `admitted`'s cycle over the pinned comment read again; whether that comment now holds it ended.

    `admitted` is the cycle as the dispatch read it. Ended where the comment
    reads it cancelled, or carries no live cycle by its id -- one a restart's
    projection or a retirement took off, which no close ends twice. Not where
    the comment would not read, reads as another record than the one the
    dispatch read, or refused the cancellation's write.
    """
    try:
        fresh = admitted.gh.read_pinned_state(admitted.issue)
    except Exception:
        log.warning("issue=#%d could not read again the cycle a close ended", admitted.issue.number, exc_info=True)
        return False
    if not fresh.supported or fresh.comment_id != admitted.state.comment_id:
        return False
    context = _LateContext(
        gh=admitted.gh, spec=admitted.spec, issue=admitted.issue, state=fresh,
        generation=_late_state.read_late_generation(fresh),
    )
    live = context.generation.is_present and context.generation.cycle_id == admitted.generation.cycle_id
    if not live or context.generation.cancelled:
        return True
    try:
        _late_owner_settlement._cancelled(context)
    except Exception:
        log.warning("issue=#%d could not record the cycle a close ended", admitted.issue.number, exc_info=True)
        return False
    return True
