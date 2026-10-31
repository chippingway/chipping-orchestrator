# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured fix round the dispatcher's recovery admitted, with no developer run.

The owner the recovery hands an applicable capture on a reviewer's change
request's road, or on a pull request's feedback road, to
(`completion_recovery.ROUTE_OWNERS`). Every one of those rounds runs under
`workflow:fixing`, so each is this stage's to finish, and the handoff each
froze says which it was. The direct round -- the developer the request's
handoff launched -- froze the request itself, which still stands handed beside
the capture, and is finished by the round's own finish
(`validating/captured_fix`). The resume a reply or a `/orchestrator continue`
bought on the far side of a park that round took froze the park it answered
(`resume_road`), and is finished here, as the resume's own tick would have
finished it. So is the resume a human's comment on an approved pull request
bought on the in_review route (`feedback_road`), whose road names it.

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

A pull request's feedback round answers the human's batch rather than a
review, so it re-reads no reviewed subject: its admission already held the
route's stamp, the batch's id lists, the pull request, the code-publication
receipt, and the pull request's readers to their frozen spellings, the
requirements to the fingerprint the run was handed, the checkout to the
commit reported on, and the pull request to the head the run started or
reported on. The pull request this owner fetches for the fixing tick's handles
is a request of its own behind those readings, though, so a feedback round has
every reading a handoff's effect stands on taken again behind that fetch
(`completion_effect.admitted_again`): a control applied, a label moved, a
close, an edit, a checkout moved, or a push while it ran holds the capture with
nothing staged or written, for the next dispatch to decide afresh -- the one
recheck a parked round's resume makes behind its subject's reads too. It is
written exactly as the resume above is, from the capture
alone and never from a rescan, so the batch its prompt quoted -- each surface
to the id its road froze, the shared cursor no further than the scan's reads
proved complete -- is the one recorded as delivered, beside the route's own
round settlement: the bookmarks cleared and `review_round` reset, since the
round before it was approved. A comment that landed while the run was out or
while the recovery reads stays above those readers for the next in_review
scan, and a reply on the issue thread meanwhile is a requirements edit the
admission retires the capture over, never one restamped onto its report. The
report goes onto the head the pull request already carries where the run made
no commit, its settlement superseding the report the approval was given, so
that approval covers it no longer and the issue goes back for a fresh review.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.workflow.engine import (
    completion_effect as _effect,
    completion_recovery_models as _recovery_models,
    completion_routes as _routes,
    usage as _usage,
)
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
    """Finish the admitted capture on the round it was taken on; True, since this tick is its.

    The direct round of a change request is the round's own finish to make;
    a resume of its parked round, or a pull request feedback round, is
    finished here once the round still stands behind the pull request this
    owner fetches (`_still_stands`).
    """
    handoff = admitted.capture.handoff
    if _verdicts.RETURNED_VERDICT in dict(handoff.frozen):
        return _captured_fix.recovers(admitted)
    feedback_round = handoff.route is _routes.CompletionRoute.PR_FEEDBACK
    context = _context(admitted)
    if context is None or not _still_stands(admitted, feedback_round=feedback_round):
        return True
    _resume._finishes_the_run(
        context, _settled_run(admitted), handoff.watermarks, _owed(handoff.spends), routed=feedback_round,
    )
    return True


def _still_stands(admitted: _recovery_models.AdmittedCompletion, *, feedback_round: bool) -> bool:
    """Whether the round the capture answers still stands, read behind this owner's own fetch; else the tick ends.

    A parked round's resume re-reads its reviewed subject, which takes the
    issue, the checkout, and the pull request's head again behind those
    reads (`validating/captured_fix.subject_stands`). A feedback round has no
    subject, so those readings are taken again here
    (`completion_effect.admitted_again`), behind the pull request `_context`
    fetched: anything but APPLICABLE -- a control applied, a label moved, a
    close, an edit, a checkout moved, or a push while that fetch ran --
    holds the capture with nothing staged or written, never retiring it on
    a reading the next dispatch's admission has yet to take.
    """
    if not feedback_round:
        return _captured_fix.subject_stands(admitted)
    again = _effect.admitted_again(admitted)
    if again.standing is _recovery_models.Standing.APPLICABLE:
        return True
    log.warning(
        "issue=#%d moved while its captured feedback round's pull request was fetched (%s: %s); holding "
        "the tick with nothing written",
        admitted.issue.number, again.standing, again.reason,
    )
    return False


def _settled_run(admitted: _recovery_models.AdmittedCompletion) -> _models._FixingResumeRun:
    """The run the resume's roads are handed, rebuilt from the capture, beside what its own tick settled around it.

    Staged on the admitted reading, for the write that hands the report on:
    the session settled as the run's own tick would have, the park it
    answered taken down, and the baseline moved to the fingerprint it was
    handed.
    """
    capture, state = admitted.capture, admitted.state
    rebuilt = _captured_completion._rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured resume of agent invocation %d/%s on the %s road; no developer "
        "is launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce, capture.handoff.route,
    )
    _captured_completion._settles_the_session(state, capture, rebuilt)
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    state.set(_REQUIREMENTS, capture.handoff.requirements_revision)
    return _models._FixingResumeRun(
        worktree=Path(capture.run.worktree),
        dev_result=rebuilt,
        paused=False,
        before_sha=capture.run.before_sha,
        after_sha=capture.run.source_sha,
        reported=True,
        requirements_revision=capture.handoff.requirements_revision,
    )


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
