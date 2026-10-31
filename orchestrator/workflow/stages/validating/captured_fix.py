# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish the captured fix a reviewer's change request handed its developer, as the round's own tick would have.

The fixing stage hands the dispatcher's recovery of a change request's capture
here where the capture is the direct round's (`fixing/captured_fixes`): the
run the handoff launched (`review_handoffs`), whose return a live hold, a lost
write, or a restart kept from its disposition. Everything that tick would have
written past the launch's charge and the run's accounting was withheld -- the
report, the commit's publication, the round, and the request's retirement --
and the request still stands handed beside the capture, the obligation the run
answers. The fixing stage's own road would read that request as a launch that
may have run, and drop it or park it for `/orchestrator continue`, paying for
the work again; the recovery decides first, so neither happens.

What is finished is the request the capture froze, read off the very reading
that admitted it: its frozen records -- the request as handed, the pull
request, and the feedback anchor -- read as they did at the launch, so the
request, its round, and its subject are the run's own. That record is no proof
its subject still stands, so the subject is read again first, all of it but
the head the run itself was asked to move (`_request_stands`): the settled
report has to read beside the handoff its settlement wrote, as the very
revision the request was reviewed over, and still be carried where it
settled, and the evidence it claims still the settled evidence. A report
another road settled since, one gone or edited where it settled, and
evidence a later revision superseded leave a request nobody is asking about
any more, so the capture is retired by a guarded invalidation and the fixing
stage's own road drops the request on the next tick; a settled record nobody
can read, a settled pair that no longer agrees, a re-read nobody could take,
and evidence still owed prove nothing, so the tick holds with nothing
written.
Those reads are requests of their own, so whatever they decide stands only
where the issue, the checkout, and the pull request's head read again behind
them as the admission read them (`completion_effect.admitted_again`); a push
while they were taken holds the tick too, rather than leasing a publication
on a head the admission never read.
The session is settled from the capture alone, as the run's own tick would
have settled it (`implementing/captured_completion`): the command that ran pinned,
a resumed conversation charged one resume and a fresh one pinned as it
returned, so a retired conversation is never restored.

The run is then disposed through the round's own finish
(`requested_changes._finish_requested_fix`), on a result rebuilt from the
capture with no usage of its own, since its exit was accounted as it returned.
That finish records the report by handing the capture to the delivery
(`fix_reports`), the request retired in the very commit that does it, so the
request's retirement and the durable ownership of its answer land together or
not at all. That commit is decided on the subject read here as this tick read
it (`report_records.HandedRun.decided_on`), so a settled report pair or
evidence record another road moved, or an operator damaged, while the subject
was read refuses the transfer, and the tick holds with nothing written; a
commit goes through the size gate and the exact-revision, leased
publication as any round's does, and a report with no code in it onto the head
the pull request already carries, invalidating the approval of the report it
replaces. The round is spent once, by the publication or by the report's
settlement, exactly as the live round spends it, and the issue is handed back
to `workflow:validating`. No developer or reviewer is launched, no run charged,
no feedback posted again, and no verdict, verification evidence, or approval
inferred: review, verification, the final documentation pass, and the
readiness proof follow the handoff as ever.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.github import pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_effect as _effect,
    completion_records as _records,
    completion_recovery_models as _recovery_models,
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
    usage as _usage,
)
from orchestrator.workflow.engine.completion_frozen_reads import evidence_unread, settled_report_reads
from orchestrator.workflow.stages.implementing import captured_completion as _captured_completion
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_claims as _claims,
    review_verdicts as _verdicts,
)

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

_LAST_AGENT_ACTION = "last_agent_action_at"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Settle and dispose the admitted capture as the round's own tick would have; True, since this tick is its.

    Only a request that still reads as one handed, over a subject that still
    stands (`subject_stands`), is finished; every other answer ends the tick
    here as well, holding or retiring the capture.
    """
    handed = _verdicts.read_returned_verdict(admitted.state)
    if handed is None or handed.handed is None:
        log.warning(
            "issue=#%d carries a captured fix with no change request handed beside it; holding the "
            "tick with nothing written", admitted.issue.number,
        )
        return True
    if not subject_stands(admitted, handed):
        return True
    capture, state = admitted.capture, admitted.state
    rebuilt = _captured_completion._rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured fix of agent invocation %d/%s its reviewer's change request "
        "handed over; no developer is launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce,
    )
    _captured_completion._settles_the_session(state, capture, rebuilt)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    worktree = Path(capture.run.worktree)
    _requested_changes._finish_requested_fix(
        _models._RequestedChanges(
            admitted.gh, admitted.spec, admitted.issue, state,
            wt=worktree, round_n=handed.round_n, pr_number=state.get(_PR_NUMBER), feedback=handed.feedback,
        ),
        _models._AwaitingDevAttempt(_models._DevFixRun(worktree, rebuilt, capture.run.before_sha), paused=False),
        handed,
    )
    return True


def subject_stands(
    admitted: _recovery_models.AdmittedCompletion, handed: _verdicts.ReturnedVerdict | None = None,
) -> bool:
    """Whether the capture's reviewed subject still stands and the issue still reads as admitted; else the tick ends.

    `handed` is the request a direct round answers, whose subject the settled
    report has to be and whose evidence still settled (`_request_stands`);
    None is a parked round's resume, which froze the settled report and the
    evidence it was launched over, so its evidence has to read at all and its
    report be carried still where it settled. The reads that proves take are
    requests of their own, so everything a handoff's effect stands on is read
    again behind them, ahead of any effect (`_still_admitted`): a control
    applied, a label moved, a close, a requirements edit, a checkout moved,
    or a push to the pull request meanwhile holds the capture with nothing
    written, for the next dispatch's admission to decide on the issue as it
    then reads -- never a retirement or a publication over the head the
    admission read. A subject nobody could read
    holds it too, and one proved moved retires the capture by a guarded
    invalidation, decided on the reading it was taken over. False wherever
    the tick ends here.
    """
    if handed is None:
        stands = None if evidence_unread(admitted.state) else _report_carried(admitted.gh, admitted.state)
    else:
        stands = _request_stands(admitted, handed)
    if stands is not None and not _still_admitted(admitted):
        stands = None
    if stands is None:
        log.warning(
            "issue=#%d could not establish that the subject its captured fix answers still stands, or the "
            "issue moved while it was read; holding the tick with nothing written", admitted.issue.number,
        )
        return False
    if stands:
        return True
    capture = admitted.capture
    retired = _checkpoint.retire(
        admitted.gh, admitted.issue, admitted.state, capture.invocation, _records.RetirementReason.INVALIDATED,
    )
    log.info(
        "issue=#%d the subject its captured fix answers has moved since the review; retiring the capture of "
        "agent invocation %d/%s came to %s",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce, retired.status.value,
    )
    return False


def _request_stands(
    admitted: _recovery_models.AdmittedCompletion, handed: _verdicts.ReturnedVerdict,
) -> bool | None:
    """Whether the subject `handed` was reviewed over still stands, save its head; None where nobody could read it.

    The head is the one member left out: the run was asked to move it, and
    the pull request's head is held to the one it started or reported on by
    the capture's own admission. The settled report has to be the one the
    request was reviewed over (`_report_carried`), and the evidence it
    claims the settled evidence still. Evidence whose records nobody can read,
    current evidence beside no handoff that describes it included
    (`completion_frozen_reads.evidence_unread`), is asked about first and
    proves nothing either way -- a standing read over damage, settled or
    lost, is no proof of either -- and evidence still owed proves nothing too.
    """
    reviewed = _review_subjects.ReviewSubject.identity_recorded_in(handed.subject)
    stands = _report_carried(admitted.gh, admitted.state, reviewed)
    if not stands or handed.evidence is None:
        return stands
    if evidence_unread(admitted.state):
        return None
    standing = _claims.claim_standing(admitted.state, handed.evidence)
    if standing is _claims.ClaimStanding.SETTLED:
        return True
    return None if standing is _claims.ClaimStanding.OWED else False


def _still_admitted(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Whether the issue, its checkout, and its pull request, read again, still admit the capture as they did.

    The readings a handoff's effect is read again with
    (`completion_effect.admitted_again`), asked behind the subject's reads:
    the issue fetched afresh for its controls, label, state, and
    requirements, the checkout on the commit reported on, and the pull
    request at the very head the admission read. Whatever they answer
    otherwise -- a hold, an ending, requirements moved, a push -- ends this
    tick with nothing written.
    """
    return _effect.admitted_again(admitted).standing is _recovery_models.Standing.APPLICABLE


def _report_carried(gh: GitHubClient, state: PinnedState, reviewed: tuple | None = None) -> bool | None:
    """Whether the settled report is still carried where it settled -- and is the one `reviewed` names, if any.

    The settled pair is judged first, ahead of any comparison with the report
    reviewed (`completion_frozen_reads.settled_report_reads`): a record
    claimed in a shape nobody can read, or a current report beside no
    handoff that describes it, is damage, never a report settled since, and
    proves nothing -- None. Only over a pair that reads does a settled report
    prove anything: none settled at all, or one of another revision or
    content, or another pull request's, than `reviewed` names, is a report
    the pull request no longer carries or one settled since over the one
    reviewed -- either way False. The report is then re-read where it settled
    as a round re-reads it (`report_settled_reading.carried_text`): gone or
    edited there it is no longer the report reviewed, and a re-read nobody
    could take is a reading that did not return -- None.
    """
    if not settled_report_reads(state):
        return None
    current = _settlement.read_current_report(state)
    if current is None:
        return False
    named = (current.subject.pr_number, current.report_revision, current.content_revision)
    if reviewed is not None and named != reviewed:
        return False
    presence = _settled_reading.carried_text(gh, state, current)[0]
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return None
    return presence is _pr_reports.ReportPresence.PRESENT
