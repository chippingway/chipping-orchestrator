# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured rewritten-head report refresh the dispatcher's recovery admitted, with no developer run.

The report hold asks the developer for a fresh report of a head this
orchestrator rewrote (`report_refresh`), on the refresh's road
(`refresh_road`), and a return that finished on a fresh READY report of that
head -- no quota stopping it, the checkout left clean on the head -- is
captured as it comes back. A live hold, a capture never confirmed, or a lost
tick keeps that return from its disposition, and every later validating tick
would otherwise ask the developer for the same report again. The recovery
hands an applicable capture on that road here
(`completion_recovery.ROUTE_OWNERS`), ahead of the report hold, so it is
finished instead.

What the admission held it to is what the refresh was entered under: the debt
it answers still on the pinned pull request and the run's branch, naming as
its rewritten head the commit the run reported on, the pull request standing on
that very commit and the checkout on it, the requirements the run was handed
still the issue's, and every record its handoff froze -- the pull request, the
debt, the code-publication receipt, the settled report pair, and for a refresh
entered over a proved approval squash or final docs pass the evidence records
and the completion that lineage was proved from -- still spelled as the launch
read them. One moved where its own reader takes the new spelling has retired the
capture before this is asked, and one nobody can read holds it.

A refresh entered over such a lineage stood on more than those records, so it
is asked again here first, as the report hold asked it before the launch
(`_lineage_stands`): the lineage proved again
(`report_docs_lineage.refresh_verdict`), over this host's checkout and the
trees git reads in it, and the settled report of the approved commit re-read
where it settled, as the reviewer road reads it (`review_report._settled_report`).
A proof that refutes the lineage, and a report the thread moved out of reach --
removed, edited, untrusted, or out of step with its handoff -- prove the
capture stale, so it is retired by a guarded invalidation; a tree, a checkout,
or a location nobody could read proves nothing, and the tick holds with nothing
written. Those reads are requests of their own, so whatever they decide stands
only where the issue, the checkout, and the pull request's head read again
behind them as the admission read them (`completion_effect.admitted_again`),
and a retirement goes out only where they read so again behind its own reads
as well, the strict edit's walk to the comment last (`captured_rereads`).

Everything the refresh's own tick would have written past the run's charge and
accounting was withheld, so it is written now, from the capture alone: the
command that ran pinned and the conversation settled as that run's would be
(`implementing/captured_completion`), so a resumed one is charged one resume
and a retired one never restored, and the agent action stamped. The refresh
answered no park -- the report hold asks for it only on a tick no park holds,
or one whose park that tick's own reply cleared on its own road -- so whatever
park the comment carries now is not the refresh's to take down, and is left as
it stands. The run is then disposed through the refresh's own disposition
(`report_refresh_outcomes._disposes_the_refresh`), handed a result rebuilt from
the capture -- its outcome, the session it returned, and the invocation it came
from, with no usage of its own, since its exit was accounted as it returned --
under the debt the admission proved and the requirements the road froze. So the
checkout's tree is proved clean again on the head the capture names, the pull
request's head and the requirements are read again, and the report reaches the
delivery through the capture's transfer and is then bound to the receipt's
publication and settled, all exactly as on the refresh's own tick. That
disposition runs inside `implementing/captured_rereads.rereads`, so the capture
is handed on or withdrawn only once its admission reads again behind every
request it took, the strict edit's walk to the comment last.

No developer or reviewer is launched, no run charged, no round spent, and no
verification, approval, documentation pass, or readiness inferred. The debt
stays recorded: the next tick's report hold finds the settled report about the
head the pull request stands on and drops it (`report_refresh._pays_the_debt`)
before the reviewer runs.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_effect as _effect,
    completion_records as _records,
    completion_recovery_models as _recovery_models,
    report_docs_lineage as _docs_lineage,
    report_rewrite_debt as _rewrite_debt,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    captured_completion as _captured_completion,
    captured_rereads as _rereads,
)
from orchestrator.workflow.stages.validating import (
    refresh_road as _refresh_road,
    report_refresh_models as _models,
    report_refresh_outcomes as _outcomes,
    review_report as _review_report,
)

log = logging.getLogger("orchestrator.workflow")

_LAST_AGENT_ACTION = "last_agent_action_at"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Record and settle the admitted capture's report as the refresh's own tick would have; True, since it is its.

    The debt is the one the admission proved the capture's
    (`completion_prerequisites`), read off the very reading it admitted. A
    lineage the refresh was entered over that no longer stands ends the tick
    here, holding or retiring the capture (`_lineage_stands`).
    """
    if not _lineage_stands(admitted):
        return True
    capture, state = admitted.capture, admitted.state
    rebuilt = _captured_completion._rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured report refresh of agent invocation %d/%s; no developer is "
        "launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce,
    )
    _captured_completion._settles_the_session(state, capture, rebuilt)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    refresh = _models._ReportRefresh(
        admitted.gh, admitted.spec, admitted.issue, state, _rewrite_debt.read_rewrite_debt(state),
        requirements=capture.handoff.requirements_revision,
    )
    with _rereads.rereads(admitted):
        _outcomes._disposes_the_refresh(refresh, Path(capture.run.worktree), rebuilt)
    return True


def _lineage_stands(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Whether the lineage the refresh was entered over still stands, the issue read again behind it; else it ends.

    A refresh entered over no lineage stands on its frozen records alone,
    which its admission already held. Otherwise the lineage is asked again
    (`_lineage_reading`), and behind those reads the issue, the checkout,
    and the pull request's head as a handoff's effect reads them: a move
    meanwhile holds the capture with nothing written. A lineage nobody could
    read holds it too, and one proved gone retires it by a guarded
    invalidation, decided on the reading it was taken over and asked inside
    `captured_rereads.rereads`, so the admission reads again behind the
    retirement's own reads, the strict edit's walk to the comment last, and a
    move landing there holds the capture with nothing written. False wherever
    the tick ends here.
    """
    if not _refresh_road.entered_over_a_lineage(admitted.capture):
        return True
    stands = _lineage_reading(admitted)
    if stands is not None and _effect.admitted_again(admitted).standing is not _recovery_models.Standing.APPLICABLE:
        stands = None
    if stands is None:
        log.warning(
            "issue=#%d could not establish that the lineage its captured report refresh was entered over still "
            "stands, or the issue moved while it was read; holding the tick with nothing written",
            admitted.issue.number,
        )
        return False
    if stands:
        return True
    capture = admitted.capture
    with _rereads.rereads(admitted):
        retired = _checkpoint.retire(
            admitted.gh, admitted.issue, admitted.state, capture.invocation, _records.RetirementReason.INVALIDATED,
        )
    log.info(
        "issue=#%d the lineage its captured report refresh was entered over no longer stands; retiring the "
        "capture of agent invocation %d/%s came to %s",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce, retired.status.value,
    )
    return False


def _lineage_reading(admitted: _recovery_models.AdmittedCompletion) -> bool | None:
    """Whether the lineage proves and the approved report re-reads intact: False where refuted, None where unread.

    Asked as the report hold asked it before the launch
    (`report_refresh._refreshes_a_squashed_report`): the proof first, and
    the report re-read at its location only over a proof that holds.
    """
    state = admitted.state
    debt = _rewrite_debt.read_rewrite_debt(state)
    proof = _docs_lineage.refresh_verdict(admitted.spec, admitted.issue.number, state, debt)
    if not proof.proved:
        return None if proof.holds else False
    report, refusal = _review_report._settled_report(admitted.gh, state, _rewrite_debt.pinned_pull_request(state))
    if report is None:
        return False if refusal else None
    return True
