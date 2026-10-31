# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured fix of a reviewer's change request the dispatcher's recovery admitted, with no developer run.

The owner the recovery hands an applicable capture on the change request's road
to (`completion_recovery.ROUTE_OWNERS`). Either half of that round runs under
`workflow:fixing`, so either is this stage's to finish, and the handoff each
froze says which it was. The direct round -- the developer the request's
handoff launched -- froze the request itself, which still stands handed beside
the capture, and is finished by the round's own finish
(`validating/captured_fix`). The resume a reply or a `/orchestrator continue`
bought on the far side of a park that round took froze the park it answered
(`resume_road`), and is finished here, as the resume's own tick would have
finished it.

That resume returned while a live hold, a lost write, or a restart kept the
tick from disposing it, and everything that tick would have written past the
run's charge and accounting was withheld. Its admission held the settled
report and evidence it was launched over to their frozen spellings, which
says nothing of whether that report still reads where it settled, so the
report is re-read there first and the issue, the checkout, and the pull
request's head read again behind that read
(`validating/captured_fix.subject_stands`): a report gone or edited retires
the capture, and one nobody could read, or a control applied or a push
meanwhile, holds it, before anything of the park or the input is touched. Then it is written,
from the capture alone and never from a second reading of the thread: the session as
the run's own tick would have settled it (`implementing/captured_completion`);
the park the resume answered taken down; the requirements baseline moved to
the fingerprint the run was handed, which its report is stamped with; and the
batch it delivered left to the pairs its road froze, which ride the report and
are applied by the write that settles it, so nothing later on the thread reads
as delivered. The park comes down only in the commit that hands the report on,
which is decided on the park's flags as this tick read them
(`reporting._PARK_FLAGS`): a park an operator or another road recorded while
the subject was read -- a spent run ledger's among them -- refuses that
commit, so it stands, and the capture waits with nothing written. The run is then answered on the resume's own roads
(`resume._finishes_the_run`), on a result rebuilt from the capture with no
usage of its own: its report handed to the delivery, its commit through the
size gate and the exact-revision, leased publication, the round settled once,
and the issue handed back for review. No developer or reviewer runs, no run is
charged, and no verdict, evidence, or approval is inferred.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.workflow.engine import completion_recovery_models as _recovery_models, usage as _usage
from orchestrator.workflow.stages.fixing import (
    models as _models,
    reporting as _reporting,
    resume as _resume,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    captured_completion as _captured_completion,
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.stages.validating import captured_fix as _captured_fix, review_verdicts as _verdicts

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

_LAST_AGENT_ACTION = "last_agent_action_at"

_REQUIREMENTS = "user_content_hash"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Finish the admitted capture on the half of the round it was taken on; True, since this tick is its."""
    if _verdicts.RETURNED_VERDICT in dict(admitted.capture.handoff.frozen):
        return _captured_fix.recovers(admitted)
    context = _context(admitted)
    if context is None or not _captured_fix.subject_stands(admitted):
        return True
    capture, state = admitted.capture, admitted.state
    rebuilt = _captured_completion._rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured resume of agent invocation %d/%s its reviewer's change request's "
        "round parked for; no developer is launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce,
    )
    _captured_completion._settles_the_session(state, capture, rebuilt)
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    state.set(_REQUIREMENTS, capture.handoff.requirements_revision)
    _resume._finishes_the_run(
        context,
        _models._FixingResumeRun(
            worktree=Path(capture.run.worktree),
            dev_result=rebuilt,
            paused=False,
            before_sha=capture.run.before_sha,
            after_sha=capture.run.source_sha,
            reported=True,
            requirements_revision=capture.handoff.requirements_revision,
        ),
        capture.handoff.watermarks,
        _owed(admitted.capture.handoff.spends),
        routed=False,
    )
    return True


def _context(admitted: _recovery_models.AdmittedCompletion) -> _models._FixingContext | None:
    """The fixing tick's handles over the admitted reading, its pull request fetched; None where it would not read."""
    try:
        pull_request = admitted.gh.get_pr(int(admitted.state.get(_PR_NUMBER)))
    except Exception:  # noqa: BLE001 - a pull request nobody could fetch holds the capture, never invalidates it
        log.warning(
            "issue=#%d could not fetch the pull request its captured resume is finished on; holding the tick",
            admitted.issue.number,
        )
        return None
    return _models._FixingContext(admitted.gh, admitted.spec, admitted.issue, admitted.state, pull_request)


def _owed(spends: tuple) -> _late_gate_models._Spends:
    """The round settlement the size gate closes, as the resume froze it: the road's own, the mark it rides aside."""
    return _late_gate_models._Spends(fields=tuple(
        pair for pair in spends if pair not in _reporting._SETTLES_THE_ROUND
    ))
