# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one finish of a landed automatic PR base rewrite, whichever road reached it.

A rebase whose lease-pinned push landed still owes its issue the rest of the
route: the report debt the landed head leaves, the notice on the pull request
and the `base_rebased` event, the round reset, the route back to review, and
the retirement of the attempt -- with a human's retry spent where a reply
brought the attempt back. The tick that published its own rebase owes that,
and so does a later tick finishing a landing an interrupted one left, whether
it pushed again or found the push already standing, and whether or not the
interrupted finish got as far as announcing it. All of them are inputs to this
one policy (`finalizes`), handed over as the typed landing the git layer
reports (`rewrite_handoffs._LandedRewrite`) beside the issue it finishes
(`rewrite_finish_models.LandedFinish`).

The policy is one order every finish keeps, and each step lands through a
guarded commit (`rewrite_finish_writes`) captured over the reading the tick
last confirmed, so a write refused -- a record it is decided on reading
otherwise, which inside the writer claim no write of this finish's made -- or
sent and never confirmed stops the finish there with nothing that depends on
it made:

- A landing the pinned record does not account for is finished by nobody: one
  the remote was not shown standing on, a rewrite that moved nothing -- its
  head still the one it replaced, which a no-op answers with the label and
  round left as they are -- a publication a guard refused for anything but
  the remote already standing on it, one with no attempt anchored to the head
  it replaced, one made for another pull request than the issue pins, one the
  attempt's record of its replay does not leave its own (`_vouched`), and one
  beside a mark naming another head -- which cannot say whether this head was
  announced. A finish that already retired its attempt left no anchor behind,
  so a repeated one does nothing. Nor is a landing whose lag against its base
  could not be counted: neither its notice nor its route can be decided, so
  the attempt stays for the caller's unreadable-checkout road. A transaction
  an earlier finish captured beside an attempt still standing is proved again
  whole there, and abandoned where anything it rests on moved.
- The debt is staged and measured on the complete write that announces it
  (`rewrite_finish_debt`), first on the comment as the tick holds it, ahead of
  anything decided for the head, and again on the comment as the evidence
  left it. A proved debt with no room parks `auto_base_rebase_unrecorded_debt`
  with the push kept and the attempt standing, and nothing is run, recorded,
  announced, or routed; a reply once room is made brings the recovery back to
  finish it. The park is prepared before its notice, so one the comment
  would refuse -- the round the announcement resets included -- posts
  nothing.
- The evidence a head the base has not advanced past is routed with is
  resolved before anything announces it (`_resolves`,
  `rewrite_finish_settlement.resolves`): the current evidence the rewrite
  moved past invalidated into history and a fresh or carried result recorded
  as a pending transaction, in a guarded commit (`rewrite_finish_evidence`),
  that transaction then published and settled with the anchor still standing,
  its proof held to the base and its writes to the attempt as well, or
  retired where anything refuses it -- or nothing recorded, the fresh
  reviewer owing the evidence, a failed run's notice recorded and put on the
  pull request once. A decision nobody could take, an invalidation with no
  room, an evidence write that did not land, a failure notice nobody could
  confirm published, or a transaction whose post or settlement did not
  resolve holds the route with nothing announced, the round as it was, and
  the attempt standing. The finish that completes it runs the commands again
  only where no run was captured, takes what this one recorded only once it
  proves again -- a captured transaction something moved under since, the
  base included, is abandoned, with nothing run again then or after -- finds
  an artifact this one posted under its receipt rather than posting it again,
  and settles nothing this one already settled while the records agree that
  is the last word on the head. Every evidence decision is held to the base
  tip the replay was recorded as made onto once its requests are behind it,
  so a base that moved meanwhile holds the route too. Nothing reads the base
  or the landing again behind the announcement's own requests, so a base that
  advances while the notice is posted, the event filed, or the relabel made
  is routed over.
- Only then is the landing announced: both of its writes prepared over the
  fresh comment first -- the checkpoint whole, the record of its event
  included, and that record's own write ahead of the event -- its notice's
  ledger entry reserved over the ledger that comment carries, so a comment
  that would refuse either posts nothing; then the notice and the event
  go out once each (`rewrite_finish_notices.announces`) -- the notice found
  on the pull request rather than posted again, where an earlier finish said
  it ahead of a checkpoint that never landed, and the event filed only where
  the event stream does not already carry it, recorded on the attempt ahead
  of it (`rewrite_finish_events`) -- and the checkpoint lands the debt, the
  reset round, and the mark while the anchor still stands. A conversation or
  an event stream nobody could read holds the finish there with the attempt
  standing, nothing filed, and no mark. The checkpoint is decided on the
  evidence records too, so an evidence record that no longer reads as the
  finish resolved it refuses it before anything is posted, and the attempt
  stands for the next finish to read. A finish whose mark already names this
  head repeats neither: it lands only a debt that is new beside it -- one an
  earlier build's mark never carried -- before its route. A head the base has
  advanced past again is announced and not routed: a transaction an earlier
  finish recorded for it is abandoned ahead of that announcement -- an
  abandonment that does not land holds the continuation with nothing
  announced, and so does a record left unresolved beside the evidence this
  landing already resolved -- its retirement lands, and the caller's ordinary
  rebase goes on from it, the refresh's selection asked again first: a report
  recorded and unsettled holds that rebase until it is settled on the head it
  is about, as an uninterrupted journey's does.
- The write that retires the attempt is prepared before the relabel to
  `workflow:validating`, then lands behind it -- the anchor is what brings a
  tick lost between them back, to the mark this finish left and the evidence
  it settled. The retirement is decided on every record the evidence is
  bound through, so a report or review record that no longer reads as the
  evidence was decided or settled over refuses the route rather than riding
  it. An issue already on `workflow:validating` under its own mark is not
  relabelled again.

A tick lost anywhere in that tail -- behind the evidence it settled, retired,
or left to the fresh reviewer and before the announcement, between the
notice, the event, and the checkpoint, behind the checkpoint and before the
relabel, or behind the relabel and before the retirement -- leaves the
attempt standing, so the anchor holds every handler until a later finish
discharges what it still owes. That finish takes the evidence up where the
records leave it and reads the rest off the mark, the pull request, the event
stream, and the label: a head the mark already names gets no second notice,
`base_rebased` event, or round reset, a notice found on the pull request or
an event found on the stream with no mark beside them is not said again, and
an issue already relabelled under the mark gets no second relabel or
stage-entry event. Evidence it settled and left current is routed as it
stands behind the last word over the landing and the base; the reviewer the
route hands it to proves it ready before relying on it
(`verification_proof.current_evidence_verdict`).

Run under the issue writer claim the caller already holds -- the base refresh
(`base_refresh`) takes it before the issue is read and keeps it through the
route -- and asks for none of its own, since that very hold would refuse it.
The claim is what lets every write here be decided over the tick's own last
confirmed reading: what changed before the claim was taken is read as input,
and nothing here adopts or repairs a record another orchestrator writer moved
inside it.

Every landing is finished here and nowhere else. The ordinary publication of a
clean rebase (`rewrite_publication`) hands its landing over on the
PUBLICATION road; the recovery hands over, on the RECOVERY road
(`finishes_the_recovery`), both the retry of a replay an interrupted tick
never published (`rewrite_retry`) and a push the interrupted tick already
landed (`rewrite_landed`) -- observed where the remote stands, or proved there
by the leased no-op that settles an outstanding transfer. So all three share
one post-push policy and one evidence decision, and a finish one tick could
not complete -- a write refused or unconfirmed, an evidence decision held, a
process that died behind the push, before its commands ran or before their
result was recorded -- is completed by the recovery of a push already landed,
from what the pinned record says it made.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    replay_evidence as _replay_evidence,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_rewrite_debt as _rewrite_debt,
    rewrite_finish_captured as _captured,
    rewrite_finish_debt as _debt,
    rewrite_finish_notices as _notices,
    rewrite_finish_settlement as _settlement,
    rewrite_finish_writes as _writes,
)
from orchestrator.workflow.engine.rewrite_finish_events import method, prepares_the_record
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def finalizes(finish: LandedFinish) -> FinishOutcome:
    """Finish the route behind `finish`'s landing, at most once; what it came to.

    ROUTED and CONTINUED retired the attempt; every other outcome left it
    standing, and made nothing that depends on a write that did not land. A
    landing the record does not account for leaves the attempt standing
    beside a transaction an earlier finish captured for its head, so that
    transaction is proved again whole first and abandoned where anything it
    rests on moved (`rewrite_finish_captured.stands_before_the_route`):
    putting what moved back before a later finish revives nothing.
    """
    if not _finishable(finish):
        return _captured.stands_before_the_route(finish, behind=FinishOutcome.UNFINISHABLE, whole=True)
    announced = _attempts._already_announced(finish.state, finish.head)
    stopped = _resolves(finish, announced=announced)
    if stopped is not None:
        return stopped
    headed = FinishOutcome.CONTINUED if finish.behind else FinishOutcome.ROUTED
    return _routes(finish, headed, announced=announced)


def finishes_the_recovery(context: _AutoRebaseRecoveryContext, landing: _LandedRewrite) -> bool:
    """Finish a landing a recovery made or found on the RECOVERY road; whether the recovery owns the tick.

    Attributed to the label the issue wears, which the notice and the event
    name and an announced finish already on `workflow:validating` is not
    relabelled from, and handed the human reply that brought the attempt
    back, which the finish spends. Only a finish that found the base advanced
    past the landed head again leaves the tick to the caller: it retired the
    attempt without routing, and the rebase the tick goes on with is what
    moves that head along. Every other outcome -- a route, a park, a write
    that did not land, a landing nothing accounts for -- owns it.
    """
    finished = finalizes(LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=landing,
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY,
        retry=context.unparking_consumed_max,
    ))
    return finished is not FinishOutcome.CONTINUED


def _finishable(finish: LandedFinish) -> bool:
    """Whether the pinned record accounts for `finish`'s landing as the attempt it finishes; logged where not."""
    state = finish.state
    refusals = (
        (not finish.landed.landed, "the remote was not shown standing on it"),
        (not finish.moved, "the rewrite moved nothing"),
        (finish.refused, "a guard refused its publication"),
        (
            not finish.anchor or state.get(_base_sync_state._PENDING_PUSH_SHA) != finish.anchor,
            "no attempt anchored to the head it replaced is pinned",
        ),
        (
            _rewrite_debt.pinned_pull_request(state) != finish.pr_number,
            "the issue pins another pull request than the attempt was made for",
        ),
        (not _vouched(finish), "the attempt's record of its replay does not name it"),
        (_attempts._foreign_mark(state, finish.head), "a finish recorded announcing another head"),
        (finish.behind is None, "the base its head is counted against could not be read"),
    )
    refusal = next((reason for refused, reason in refusals if refused), None)
    if refusal is None:
        return True
    log.warning(
        "issue=#%d not finishing the base rewrite that published %.8s on PR #%d: %s",
        finish.issue.number, finish.head, finish.pr_number, refusal,
    )
    return False


def _vouched(finish: LandedFinish) -> bool:
    """Whether the attempt's own record of its replay leaves the landed head its own.

    The landing proves where the remote stands, not whose push put it there:
    the record is what the attempt wrote about the replay it made, so a record
    naming another head, made for another pull request or stage than the
    landing's attempt, damaged, or never written at all, says this is no
    landing of this attempt's. A record whose terms stand and that names no
    head yet is the window between `git rebase` returning and the write that
    records what it produced -- not a contradiction, and vouching for the
    landing there (the transfer permission that licensed its push) is the
    recovery's, ahead of handing it over.

    A record whose terms do not read vouches for nothing, a record never
    written included: no attempt this build makes leaves its anchor without
    the terms, and the recovery parks one that does before any push
    (`rewrite_recovery.recovers`), so no landing is finished on it.
    """
    recorded = _attempt_records._pending_rewrite(finish.state)
    attempt = finish.landed.candidate.attempt
    if not recorded.is_declared:
        return False
    terms = (recorded.pr_number, recorded.stage) == (attempt.pr_number, attempt.stage)
    return terms and recorded.sha in {"", finish.head}


def _checkpoints(finish: LandedFinish, *, announced: bool) -> FinishOutcome | None:
    """Make the debt durable, and announce the landing where nothing has yet; None to go on to the route.

    Asked once the landed head's evidence is resolved (`_resolves`), so a
    notice, an event, and a round reset are never made for a head whose
    evidence is still owed to its pull request. Measured on the announcement
    the debt rides (`rewrite_finish_debt.announcement`), or -- where the mark
    already names this head -- on the comment as it stands, and landed there
    only where it is a claim the comment does not carry yet. An announcement is
    prepared over the fresh comment before its notice is posted, the entry
    the notice adds to the ledger reserved over the ledger the candidate
    carries -- the fresh comment's, the tick's own entries merged in
    (`report_commits.ReportCommit.prepares`). Both of the announcement's writes are prepared before its notice: the
    checkpoint whole -- the record of its event staged on it too -- and the
    write that lands that record on its own ahead of the event
    (`rewrite_finish_events.prepares_the_record`), over the round as the tick
    read it, which only the checkpoint resets. So a comment whose wide round
    leaves room for the checkpoint and none for the record beside it posts and
    files nothing. The notice and the event are each said once
    (`rewrite_finish_notices.announces`), and what stopped either -- a
    conversation or event stream that would not read, or the event's own
    record that did not land -- stops the checkpoint with the attempt standing.
    """
    staged = _writes.staging(finish)
    measured = _debt.announcement(staged, finish.head, announced=announced)
    if not _debt.stages(finish, staged, measured):
        return _writes.parks(finish)
    if announced:
        carried = _commit_models.spelled(finish.state.data, _rewrite_debt.REWRITE_DEBT)
        if _commit_models.spelled(staged.data, _rewrite_debt.REWRITE_DEBT) == carried:
            return None
        return _writes.lands(finish, staged, _writes.CHECKPOINT)
    staged.set(_base_sync_state._PENDING_ANNOUNCED_EVENT, finish.head)
    staged.set(_base_sync_state._REVIEW_ROUND, 0)
    staged.set(_base_sync_state._PENDING_ANNOUNCED_SHA, finish.head)
    stopped = _writes.prepares(finish, staged, _writes.CHECKPOINT, ledger_entry=True)
    if stopped is None:
        stopped = prepares_the_record(finish)
    if stopped is None:
        stopped = _notices.announces(finish, staged)
    if stopped is not None:
        return stopped
    log.info(
        "issue=#%d announced the base rewrite PR #%d landed on %.8s (%s)",
        finish.issue.number, finish.pr_number, finish.head, method(finish),
    )
    return _writes.lands(finish, staged, _writes.CHECKPOINT)


def _resolves(finish: LandedFinish, *, announced: bool) -> FinishOutcome | None:
    """Resolve the landed head's evidence, then make the debt durable and announce; None to go on to the route.

    The evidence comes first (`rewrite_finish_settlement.resolves`): a head
    the base has not advanced past is announced, its round reset, and its
    mark written only once the evidence it is routed with is settled, retired,
    or the fresh reviewer's to owe -- a decision, write, publication, or
    settlement that stopped short of that is the outcome instead, with
    nothing announced. A head the base advanced past again decides no
    evidence, but a transaction an earlier finish recorded for it is
    abandoned before its continuation is announced
    (`rewrite_finish_evidence.continues`), and an abandonment that did not
    land holds it the same way, as does a record left unresolved beside the
    evidence this landing already resolved. A debt the comment has no room for
    runs and records nothing ahead of the park it takes
    (`rewrite_finish_debt.fits`). A checkpoint that did not land, or the park,
    stops the route behind the last word over a transaction still recorded
    for the head (`rewrite_finish_captured.stands_before_the_route`).
    """
    if _debt.fits(finish, announced=announced):
        stopped = _settlement.resolves(finish)
        if stopped is not None:
            return stopped
    stopped = _checkpoints(finish, announced=announced)
    if stopped is None:
        return None
    return _captured.stands_before_the_route(finish, behind=stopped)


def _routes(finish: LandedFinish, headed: FinishOutcome, *, announced: bool) -> FinishOutcome:
    """Retire the attempt and take the route `headed` names; `headed`, or where the write behind it stopped.

    The retirement is prepared before the relabel and lands behind it, so a
    relabel is made only for a write that would follow it, and the anchor
    stands until the route is behind it. Nothing recorded for the head is
    left owed by then: the evidence step settled or retired whatever it
    recorded (`rewrite_finish_settlement`), so no transaction rides the route
    for the anchor's retirement to hand to the dispatcher. A retirement the
    comment refuses -- a review or report record that no longer reads as the
    evidence was decided or settled over among the reasons -- stops the route
    with the attempt standing, for the recovery of the push already landed to
    route the head on a later tick over evidence it settles nothing for again.
    A routed head is relabelled to `workflow:validating` unless the mark the
    tick read already names it and the issue already wears that label: a
    finish lost between the relabel and the retirement is not relabelled, nor
    its stage-entry event filed, a second time. The label write lands ahead
    of its stage-entry event (`github/issues.set_workflow_label`), so a finish
    lost between the two reads the relabel made and files no stage-entry event
    for its route at all, where an uninterrupted one files one; so does one
    lost between the checkpoint and the relabel on an issue that already wore
    that label before its rebase. Nothing on the comment or the label tells
    that relabel unmade from one made.
    """
    stopped = _writes.prepares(finish, _writes.retirement(finish), _writes.FINISH)
    if stopped is not None:
        return stopped
    relabelled = announced and finish.label == WorkflowLabel.VALIDATING
    if headed is FinishOutcome.ROUTED and not relabelled:
        finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING)
    stopped = _writes.lands(finish, _writes.retirement(finish), _writes.FINISH)
    if stopped is not None:
        return stopped
    log.info(
        "issue=#%d finished the base rewrite PR #%d landed on %.8s: %s",
        finish.issue.number, finish.pr_number, finish.head, headed.value,
    )
    return headed
