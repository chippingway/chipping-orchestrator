# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured implementing completion the dispatcher's recovery admitted, as its own tick would have.

The owner the recovery hands an applicable capture of the first
implementation or of an implementing resume to (`completion_recovery.ROUTE_OWNERS`).
Its run returned while a live hold, a lost write, or a restart kept the tick
from disposing it, and everything that tick would have written past the
run's charge and accounting was withheld. So this owner writes it now, from
the capture alone and never from a second reading of the thread: the command
that ran is pinned; the session settles as that run's would -- a fresh
conversation pins the id it returned, where it returned one the record does
not retire, and a resumed one is charged one resume -- so a retired
conversation is never restored; the park the run answered comes down; the
input the road delivered is settled as frozen -- the thread stretch the first
implementation quoted, the edit it answered, the reply batch or the commands
a resume consumed -- and nothing later on the thread is read as delivered.

The run's report is then disposed through the stage's own disposition
(`disposition._dispose_agent_result`), handed a result rebuilt from the
capture: the run's outcome, the session it returned, and the invocation it
came from, with no usage of its own, since the run's exit was accounted as it
returned. That disposition hands the capture to the report delivery where it
records the report (`captured_report`), so the report reaches the existing
transaction once and keeps the requirements and source commit the run had,
and the commit goes through the size gate and the exact-revision, leased
publication as any run's does. A run that committed nothing parks as its own
tick would have, withdrawing the capture. That disposition runs inside
`captured_rereads.rereads`, so the capture is handed on or withdrawn only once
its admission reads again behind every request the disposition and the write
took, the strict edit's walk to the comment last: a control applied, a
relabel, a close, an edit, or a push landing during them -- on a resume that
answers a requirements-drift park's reply or continue as on any other --
holds the capture with nothing written. No developer is launched, no run
charged, and no synthetic commit or undeliverable-report park stands in for
a return that was merely held; review, verification, the final
documentation pass, and the readiness proof follow the handoff as ever.

The rebuilt result and the session's settlement are read by the recovery of a
reviewer's change request's capture, of a pull request feedback round's, and
of a requirements-drift resume's too (`validating/captured_fix`,
`fixing/captured_fixes`, `captured_drift`), which settles its run's session
exactly so.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_recovery_models as _recovery_models,
    completion_routes as _routes,
    report_consumed_values as _consumed,
    report_outcome_models as _outcome_models,
    thread_delivery as _thread_delivery,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    captured_rereads as _rereads,
    disposition as _disposition,
    models as _models,
    session as _session,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_LAST_AGENT_ACTION = "last_agent_action_at"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Settle and dispose the admitted capture as its own tick would have; True, since this tick is its.

    The disposition writes the issue's state behind it, so nothing else runs
    on the readings it acted on.
    """
    capture, state = admitted.capture, admitted.state
    rebuilt = _rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured completion of agent invocation %d/%s on the %s road; no "
        "developer is launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce, capture.handoff.route,
    )
    _settles_the_session(state, capture, rebuilt)
    _settles_the_input(state, capture)
    with _rereads.rereads(admitted):
        _disposition._dispose_agent_result(
            admitted.gh, admitted.spec, admitted.issue, state,
            _models._PreparedDevRun(rebuilt, capture.run.before_sha, False, Path(capture.run.worktree)),
        )
    return True


def _settles_the_session(
    state: PinnedState, capture: _records.CompletionCapture, rebuilt: AgentResult,
) -> None:
    """Pin the command that ran, and settle the conversation as the run's own tick would have.

    A fresh conversation drops the pin only where its launch did -- a grant,
    a rotation, or a poisoned resume retired it, which the capture records as
    nothing left pinned when the attempt returned -- and pins the id it
    returned where the record does not retire it; a resumed one is charged
    one resume, at the count the record kept, while it is still the
    conversation pinned. Asked only over a record that settled none of the
    run, since whatever settles it lands with the capture's handoff.
    """
    run = capture.run
    _session._pin_dev_command(state, run.command)
    fresh = run.resumed is None
    if fresh and run.pinned is None:
        _session._drop_poisoned_dev_session(state)
    _session._persist_dev_session_after_run(
        state,
        rebuilt,
        fresh_spawn=fresh,
        resume_count=int(state.get(_state._DEV_RESUME_COUNT) or 0),
        resumed_session_id=run.resumed,
    )


def _settles_the_input(state: PinnedState, capture: _records.CompletionCapture) -> None:
    """Settle what the road delivered, take down the park the run answered, and stamp the branch it ran on.

    A resume answers the park it resumed, as its own tick does whatever the
    flag read. The first implementation runs on an unparked tick, so a park
    standing beside it is the one the edit it answered cleared before the
    spawn, and that comes down whole; with none, nothing is written for it.
    """
    handoff = capture.handoff
    if handoff.delivered:
        _thread_delivery.records_delivery(state, _thread_delivery.DeliveredThread(*handoff.delivered))
    _consumed.advance_consumed(state, handoff.watermarks)
    resumed = handoff.route is _routes.CompletionRoute.RESUME
    if state.get(_state._AWAITING_HUMAN) and not resumed:
        state.set(_state._PARK_REASON, None)
    if resumed or state.get(_state._AWAITING_HUMAN):
        state.set(_state._AWAITING_HUMAN, False)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    state.set(_state._BRANCH, capture.run.branch)


def _rebuilt_result(capture: _records.CompletionCapture) -> AgentResult:
    """The run's result as its disposition reads it, rebuilt from the capture: completed, on its own outcome."""
    return AgentResult(
        session_id=capture.session_id,
        last_message=_contract_text(capture.outcome),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
        invocation=capture.invocation,
    )


def _contract_text(outcome: _routes.CapturedOutcome) -> str:
    """The closing lines the outcome owner reads `outcome` back from."""
    if isinstance(outcome, _outcome_models._ReadyReport):
        return f"{_outcome_models._REPORT_READY_MARKER}\n{outcome.report}\n{_outcome_models._REPORT_END_MARKER}"
    location = outcome.location
    anchor = "" if location.comment_id is None else f"#issuecomment-{location.comment_id}"
    return (
        f"{_outcome_models._REPORT_VERIFIED_MARKER} https://github.com/{location.slug}/pull/"
        f"{location.pull_number}{anchor} {_outcome_models._REVISION_PREFIX}{outcome.revision}"
    )
