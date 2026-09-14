# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reconcile issue-content drift and route trusted replies over a frozen candidate.

A first reading establishes the baseline. Drift parks without discarding
the candidate, while guidance, certification, and the standing park decide
which answer or developer revision the next reading is allowed to apply.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.stages.decomposition import (
    late_answers as _late_answers,
    late_content as _late_content,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContentSettlement,
    _LateContentSignal,
    _LateContext,
    _LateDisposition,
)

log = logging.getLogger("orchestrator.workflow")

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_DRIFT_PARK = (
    "the requirements changed after this issue's oversized committed "
    "candidate was frozen, so its adjudication is on hold. Nothing was "
    "discarded -- the frozen commit, the late session, the recorded "
    "generation, and any hold on its pull request all stand. Reply "
    "`/orchestrator continue` if the committed work still answers the "
    "updated issue, or with the change to make and the developer is resumed "
    "against it."
)


def _reconcile_late_content(
    context: _LateContext,
) -> _LateContentSettlement:
    """Settle what the humans have said about this frozen candidate.

    A settlement with no disposition is the only answer that lets adjudication
    carry on. Every other one is the whole of what the tick did.

    A generation with no baseline yet is taking one: the content as it stands
    is what the candidate was frozen against, so it is recorded and nothing is
    drift. Only once a baseline exists is there anything to compare.
    """
    signal = _late_content._read_content_signal(
        context.issue, context.state, context.generation,
    )
    if not signal.baselined:
        return _baselined(context, signal)
    if signal.drifted:
        return _drifted(context, signal)
    return _undrifted(context, signal)


def _baselined(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Record the requirements this candidate was frozen against."""
    context.generation = _late_content._rebaselined(
        context.generation, signal.fingerprint,
    )
    _late_park_state._persist(context)
    return _LateContentSettlement(persisted=True)


def _drifted(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer a candidate whose requirements moved out from under it.

    The park comes first and consumes nothing, so an answer that arrived in
    the same window is still unread when the human comes back to it. Only once
    the park stands does a reply resolve it, and which reply it is decides
    whether the frozen candidate is certified or the developer is resumed.
    """
    if _standing_park(context) != _late_park_state.PARK_CONTENT_DRIFT:
        return _parked_drift(context)
    if signal.guidance:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.bare_continue:
        return _late_answers._certified(context, signal)
    return _LateContentSettlement(disposition=_LateDisposition.PARKED)


def _undrifted(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer a candidate whose requirements are the ones it was frozen on.

    What the issue is waiting on decides what a fresh trusted comment means. A
    drift park has been answered by the edit going back, though guidance that
    came with it is still guidance; a revision park is settled by re-reading
    the checkout; and a categorized question by the answer to it.

    An issue waiting on nothing is the case with no park to read, and guidance
    means there what it means everywhere else: the work has to change, so the
    developer is resumed against it. Folding it into the baseline instead
    would consume a human's instruction without acting on it -- and with a
    verdict already recorded, leave that verdict standing over work the human
    just asked to be different. A bare continue is the one reply that lands
    here with nothing to do: no park is waiting on it and no candidate needs
    certifying, so it is consumed and the tick carries on.
    """
    answers = _late_answers._park_answer(_standing_park(context))
    if answers is not None:
        return answers(context, signal)
    if signal.guidance:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.bare_continue:
        return _late_answers._consumed(context, signal)
    return _LateContentSettlement()


def _parked_drift(context: _LateContext) -> _LateContentSettlement:
    """Hold the candidate while a human says what the edit meant."""
    log.info(
        "issue=#%d the requirements moved under frozen candidate %s; "
        "parking without discarding it",
        context.issue.number, context.generation.candidate_sha,
    )
    _late_parks._park(
        context, _DRIFT_PARK, reason=_late_park_state.PARK_CONTENT_DRIFT,
    )
    return _LateContentSettlement(
        disposition=_LateDisposition.PARKED, persisted=True,
    )


def _standing_park(context: _LateContext) -> str | None:
    """The reason this issue is parked on right now, or None if it is not.

    Read off what the tick FOUND rather than off what it has staged: the
    coordinator retires the parks a fresh attempt supersedes before this owner
    runs, and none of the parks answered here is one of those.
    """
    if not context.state.get(_AWAITING_HUMAN):
        return None
    standing = context.state.get(_PARK_REASON)
    return standing if isinstance(standing, str) else None
