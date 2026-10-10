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

The policy is the order every finish has always kept, and each step lands
through a guarded commit (`rewrite_finish_writes`), so a write another road's
move refuses stops the finish there with nothing behind it made:

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
  the attempt stays for the caller's unreadable-checkout road.
- The debt is staged and measured on the complete write that announces it
  (`rewrite_finish_debt`). A proved debt with no room parks
  `auto_base_rebase_unrecorded_debt` with the push kept and the attempt
  standing, and nothing is announced or routed; a reply once room is made
  brings the recovery back to finish it. The park is prepared before its
  notice, so one whose room another road changed meanwhile -- the round the
  announcement resets included -- posts nothing.
- An announcement is prepared over the fresh comment first, its notice's
  ledger entry reserved over the ledger that comment carries, so a comment
  that would refuse it posts nothing. Then the notice and the event go out
  (`rewrite_finish_notices`), and the checkpoint lands the debt, the reset
  round, and the mark while the anchor still stands. A finish whose mark
  already names this head repeats neither: it lands only a debt that is new
  beside it -- one an earlier build's mark never carried -- before its route.
- The route is decided (`_decides_the_route`). A head the base has advanced
  past again is not routed: a transaction an earlier finish recorded for it
  is abandoned, its retirement lands, and the caller's ordinary rebase goes
  on from it. Any other head's evidence is decided and made durable first
  (`rewrite_finish_evidence`): the current evidence the rewrite moved past
  invalidated into history, and a fresh or carried result recorded as a
  pending transaction, in a guarded commit that lands before anything routes
  -- or nothing recorded, the fresh reviewer owing the evidence, a failed
  run's notice recorded and put on the pull request once. A decision nobody
  could take, an invalidation with no room, an evidence write that did not
  land, or a failure notice nobody could confirm published holds the route
  with the attempt standing. The finish that completes it runs the commands
  again only where no run was captured, and takes what this one recorded
  only once it proves again: a captured transaction something moved under
  since is abandoned, with nothing run again.
- The write that retires the attempt is prepared before the relabel to
  `workflow:validating`, then lands behind it -- the anchor is what brings a
  tick lost between them back, to the mark this finish left and the evidence
  it recorded. An issue already on `workflow:validating` under its own mark
  is not relabelled again.

Run under the issue writer claim the caller already holds -- the base refresh
(`base_refresh`) takes it before the issue is read and keeps it through the
route -- and asks for none of its own, since that very hold would refuse it.

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
    rewrite_finish_debt as _debt,
    rewrite_finish_evidence as _evidence,
    rewrite_finish_notices as _notices,
    rewrite_finish_writes as _writes,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The routes a decided head is taken on; any other decision is where the finish stopped.
_HEADED = frozenset((FinishOutcome.ROUTED, FinishOutcome.CONTINUED))


def finalizes(finish: LandedFinish) -> FinishOutcome:
    """Finish the route behind `finish`'s landing, at most once; what it came to.

    ROUTED and CONTINUED retired the attempt; every other outcome left it
    standing, and made nothing that depends on a write that did not land.
    """
    if not _finishable(finish):
        return FinishOutcome.UNFINISHABLE
    announced = _attempts._already_announced(finish.state, finish.head)
    stopped = _checkpoints(finish, announced=announced)
    if stopped is not None:
        return stopped
    headed = _decides_the_route(finish)
    if headed not in _HEADED:
        return headed
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

    One record never written is vouched for all the same: an attempt from
    before the record existed, whose replay the recovery retried on the counts
    alone -- a strictly-ahead checkout, pushed under the anchor's lease. The
    push this tick made and saw land is that retry's own. A landing it only
    found standing is still nobody's, since nothing says whose push that was.
    """
    recorded = _attempt_records._pending_rewrite(finish.state)
    attempt = finish.landed.candidate.attempt
    if not recorded.is_declared:
        unwritten = not recorded.left_a_replay
        return unwritten and finish.road is FinishRoad.RECOVERY and finish.pushed
    terms = (recorded.pr_number, recorded.stage) == (attempt.pr_number, attempt.stage)
    return terms and recorded.sha in {"", finish.head}


def _checkpoints(finish: LandedFinish, *, announced: bool) -> FinishOutcome | None:
    """Make the debt durable, and announce the landing where nothing has yet; None to go on to the route.

    Measured on the announcement the debt rides, or -- where the mark already
    names this head -- on the comment as it stands, and landed there only
    where it is a claim the comment does not carry yet. An announcement is
    prepared over the fresh comment before its notice is posted, the entry
    the notice adds to the ledger reserved over the one that comment carries
    rather than over the tick's: an id the tick's ledger lacks may be one
    another road has recorded since, and reserved there it is no room at all.
    """
    staged = _writes.staging(finish)
    measured = _writes.staging(finish) if announced else _debt.announcement(staged, finish.head)
    if not _debt.stages(finish, staged, measured):
        return _writes.parks(finish)
    if announced:
        carried = _commit_models.spelled(finish.state.data, _rewrite_debt.REWRITE_DEBT)
        if _commit_models.spelled(staged.data, _rewrite_debt.REWRITE_DEBT) == carried:
            return None
        return _writes.lands(finish, staged, _writes.CHECKPOINT)
    staged.set(_base_sync_state._REVIEW_ROUND, 0)
    staged.set(_base_sync_state._PENDING_ANNOUNCED_SHA, finish.head)
    stopped = _writes.prepares(finish, staged, _writes.CHECKPOINT, ledger_entry=True)
    if stopped is not None:
        return stopped
    _notices.announces(finish, staged)
    log.info(
        "issue=#%d announced the base rewrite PR #%d landed on %.8s (%s)",
        finish.issue.number, finish.pr_number, finish.head, _notices.method(finish),
    )
    return _writes.lands(finish, staged, _writes.CHECKPOINT)


def _decides_the_route(finish: LandedFinish) -> FinishOutcome:
    """Where the landed head goes once its checkpoint is durable: ROUTED, CONTINUED, or where its evidence stopped it.

    The post-push, pre-route step, and the one place the evidence a landed
    head is routed with is decided: asked once the push has landed and the
    debt and announcement are durable, and before anything moves the label or
    retires the attempt. A head the base has advanced past is CONTINUED to the
    caller's next rebase with no evidence decided, since that rebase replaces
    it and the head it lands is decided then -- a transaction an earlier
    finish recorded for it abandoned first (`rewrite_finish_evidence.continues`).
    Every other head is ROUTED to `workflow:validating` only once the evidence
    it is routed with is durable (`rewrite_finish_evidence.settles`); a
    decision or write that stopped short of that is the outcome instead, and
    nothing routes.
    """
    if finish.behind:
        return _evidence.continues(finish) or FinishOutcome.CONTINUED
    return _evidence.settles(finish) or FinishOutcome.ROUTED


def _routes(finish: LandedFinish, headed: FinishOutcome, *, announced: bool) -> FinishOutcome:
    """Retire the attempt and take the route `headed` names; `headed`, or where the write behind it stopped.

    The retirement is prepared before the relabel and lands behind it, so a
    relabel is made only for a write that would follow it, and the anchor
    stands until the route is behind it.
    """
    staged = _writes.retirement(finish)
    stopped = _writes.prepares(finish, staged, _writes.FINISH)
    if stopped is not None:
        return stopped
    relabels = headed is FinishOutcome.ROUTED and not (
        announced and finish.label == WorkflowLabel.VALIDATING
    )
    if relabels:
        finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING)
    stopped = _writes.lands(finish, staged, _writes.FINISH)
    if stopped is not None:
        return stopped
    log.info(
        "issue=#%d finished the base rewrite PR #%d landed on %.8s: %s",
        finish.issue.number, finish.pr_number, finish.head, headed.value,
    )
    return headed
