# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reconcile issue-content drift and route trusted replies over a frozen candidate.

A first reading establishes the baseline. Drift parks without discarding
the candidate, while guidance, certification, and the standing park decide
which answer or developer revision the next reading is allowed to apply.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_answers as _late_answers,
    late_content as _late_content,
    late_issue_baseline as _late_issue_baseline,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSettlement, _LateContentSignal
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition

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

    A generation with no baseline yet is taking one -- over the part of the
    content the issue-wide baseline already covers (`late_issue_baseline`) --
    and one baselined over the whole thread before its baselines were bounded
    by that one gives up what it counts first, drifted or not, since it may
    count comments no stage consumed. Only once a baseline stands is there
    anything to compare. Drift over the baseline a first reading parked on is
    compared once more against that issue-wide one, since a revert is what
    only that comparison can see.
    """
    signal = _late_content._read_content_signal(
        context.issue, context.state, context.generation,
    )
    retaken = _late_issue_baseline._retaken(
        context.state, context.generation, signal,
    )
    if retaken is not None:
        context.generation = retaken
        signal = _late_content._signal_of(
            signal.text, list(signal.read), context.state, retaken,
        )
    if not signal.baselined:
        return _baselined(context, signal)
    if not signal.drifted:
        return _undrifted(context, signal)
    reconciled = _late_issue_baseline._reconciled(
        context.state, context.generation, signal,
    )
    if reconciled is None:
        return _drifted(context, signal)
    return _settled_on(context, reconciled, signal)


def _baselined(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Record the requirements this candidate was frozen against.

    What the issue-wide baseline covers is what the candidate was written
    against, so that is what the late one is taken over. Anything past it --
    a comment the developer's last run never saw, one a park's notice has
    since put under the reply floor -- is left uncounted and read the way any
    uncounted conversation is, on this same reading: guidance resumes the
    developer with it quoted whole rather than being folded into a baseline
    nothing read. A reading no prefix of which reproduces the issue-wide
    baseline is one whose title, body, or covered comments moved since, and
    that is drift: it parks, and the candidate is not adjudicated over it. It
    parks on a baseline that counts no comment, so the thread's trusted
    comments -- one written under the park's notice included -- are withheld
    guidance the answer to that park hands the developer whole.
    """
    covered = _late_issue_baseline._covered(
        context.state, context.generation, signal,
    )
    if covered is None:
        context.generation = _late_issue_baseline._unreconciled(
            context.state, context.generation, signal,
        )
        return _drifted(context, _late_content._signal_of(
            signal.text, list(signal.read), context.state, context.generation,
        ))
    return _settled_on(context, covered, signal)


def _settled_on(
    context: _LateContext, baseline: LateGeneration, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer one reading against the baseline this tick took over it.

    The reading is judged again against that baseline rather than the one it
    was read under, so what lies past the covered prefix is guidance -- fresh,
    or withheld under a park's notice -- and a standing drift park meets the
    content it was taken over as the revert it is. The baseline is written
    even where nothing else is, so the next tick compares rather than taking
    it again.
    """
    context.generation = baseline
    settled = _undrifted(context, _late_content._signal_of(
        signal.text, list(signal.read), context.state, baseline,
    ))
    if settled.disposition is not None or settled.persisted:
        return settled
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

    Words that arrived in that window under the park's own notice are
    withheld: they answer nothing, but a certificate answering the park does
    not answer them either. So a certificate over withheld guidance resumes
    the developer with it quoted, rather than certifying and spending it on
    an adjudication that may never get past its spawn gates.
    """
    if _standing_park(context) != _late_park_state.PARK_CONTENT_DRIFT:
        return _parked_drift(context)
    if signal.guidance or (signal.bare_continue and signal.withheld):
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
    developer is resumed against it. That includes guidance a park's notice
    withheld once the park that withheld it is gone: the boundary kept those
    words from answering it, and with nothing left for them to answer they
    are an instruction nobody has read. Folding it into the baseline instead
    would consume a human's instruction without acting on it -- and with a
    verdict already recorded, leave that verdict standing over work the human
    just asked to be different. A bare continue is the one reply that lands
    here with nothing to do: no park is waiting on it and no candidate needs
    certifying, so it is consumed and the tick carries on.

    With nothing to answer at all the adjudication carries on over this
    reading, consuming none of it; an issue with no recorded baseline has it
    recorded as observed, which is what the next stage's drift check compares
    against (`late_issue_baseline._observed`).
    """
    answers = _late_answers._park_answer(_standing_park(context))
    if answers is not None:
        return answers(context, signal)
    if signal.guidance or signal.withheld:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.bare_continue:
        return _late_answers._consumed(context, signal)
    _late_issue_baseline._observed(context.state, signal)
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
