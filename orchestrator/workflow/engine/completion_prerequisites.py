# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a pending capture's road still has to stand on, and whether its run's accounting read back.

The label a capture reported under and the records its road froze say which
road it was; they cannot say whether that road is still there to finish. Each
stands on records another owner keeps, and a capture is handed on only while
they stand (`road_refusal`):

- a report under a stage only a pull request reaches -- `validating`,
  `in_review`, `fixing`, `resolving_conflict` -- is owed to the pull request
  the record names, so a record naming none has nothing to hand it to;
- a rewritten-head refresh answers the report debt that rewrite left
  (`report_rewrite_debt`), standing on the pull request the record pins and
  the run's branch, and naming as its rewritten head the very commit the run
  reported on -- the refresh's own road takes a report only from a checkout
  still on that head (`report_refresh_outcomes._checkout_refusal`), and
  `completion_sources` holds the pull request to it too: a debt paid, gone,
  carried onto another head, or another pull request's or branch's is a
  refresh nobody owes now, a replacement pull request on the same head and a
  run that left the rewritten head included;
- a late revision answers a live adjudication
  (`stages/decomposition/late_relabel._adjudicating`, asked when called, as the
  engine reaches every stage owner), and one that ended leaves the revision
  nothing to be measured by -- but a late record claiming a reading the
  comment cannot produce (`stages/implementing/late_claims._claims_a_reading`)
  answers that question for nobody, since its damage reads as no live
  adjudication too.

- a handoff frozen over records (`completion_frozen`) answers them as they
  were spelled at the launch, so one another road has moved since is no
  longer the one the run answered -- asked behind the road's own records, and
  only where the record moved still reads: a moved record whose own reader
  takes its new spelling as nothing it can describe (the rewrite debt, the
  pinned pull request, a returned reviewer verdict, the records a change
  request's round freezes beside it and a pull request's feedback round
  beside its stamp, whose readers `completion_frozen_reads` keeps -- the
  feedback anchor, the in_review route's stamp, the code-publication receipt,
  the settled report and the verification evidence, the bookmarked batch's id
  lists, and the pull request's readers, and the rounds and claims a
  requirements-drift resume freezes -- and the late records the
  late-claims owner judges field by
  field -- the measurement evidence, the publication group, a hold's route
  bookkeeping) is damage, not a move, and holds the capture. So does a moved
  record no reader is registered for, since nothing here can tell its move
  from its damage: a road that freezes a record registers its reader here,
  with `completion_frozen_reads`, or with that owner for a late one.

An auto-rebase anchor beside the capture is asked here as well
(`anchor_refusal`): one that reads as a commit is a rewrite of the branch no
recovery has finished, and one that does not is evidence nobody can read.

A record saying a prerequisite is gone proves the capture stale; one claiming
it in a shape nobody can read holds the capture.

A run whose usage checkpoint was refused or never confirmed is captured
`unresolved`, and an accounting checkpoint that neither landed nor read back
permits that run's accounting alone. So such a capture is handed on only
once the record reads its invocation's receipt back beside counters its
writers would write (`accounting_refusal`), and is held otherwise; nothing here
accounts it again, since the capture keeps no usage to account.

Only the record the dispatcher admitted is read, and nothing is written.
"""
from __future__ import annotations

import importlib
from types import MappingProxyType

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
    report_rewrite_debt as _rewrite_debt,
    stage_targets as _stage_targets,
    usage_counters as _usage_counters,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.engine.completion_frozen_reads import READS as _ROAD_READS
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.state import WorkflowLabel

_PR_NUMBER = "pr_number"

# The returned reviewer verdict a change request is handed over, as its
# owner spells it, and that owner, resolved when asked.
_RETURNED_VERDICT = "review_returned_verdict"
_VERDICTS_OWNER = _stage_targets._VALIDATING_REVIEW_VERDICTS_OWNER

# The anchor an auto rebase pins before git runs, spelled by the base sync.
_ANCHOR = _base_sync_state._PENDING_PUSH_SHA

# The stages only a pull request reaches, so a report under one is owed to the pull request the record names.
_PULL_REQUEST_STAGES = frozenset((
    WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW, WorkflowLabel.FIXING, WorkflowLabel.RESOLVING_CONFLICT,
))

_GONE = _models.Decision(_models.Standing.INVALID, _models.Reason.PREREQUISITE_GONE)

_UNREAD = _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.PREREQUISITE_UNREAD)

# Whether a state's spelling of each record a frozen handoff may name reads,
# by the record's name: absent reads as gone, and anything else has to be
# what the record's own reader takes. The stage owners among those readers
# are resolved when asked, the late records' by the late-claims owner's own
# table of the fields its claims judge (`late_claims._FIELD_READS`), asked
# beside these.
_READS = MappingProxyType({
    _rewrite_debt.REWRITE_DEBT: lambda state: (
        not _rewrite_debt.carries_rewrite_debt(state) or _rewrite_debt.read_rewrite_debt(state) is not None
    ),
    _PR_NUMBER: lambda state: (
        state.get(_PR_NUMBER) is None or _rewrite_debt.pinned_pull_request(state) is not None
    ),
    _RETURNED_VERDICT: lambda state: (
        state.get(_RETURNED_VERDICT) is None
        or importlib.import_module(_VERDICTS_OWNER).ReturnedVerdict.read(state.get(_RETURNED_VERDICT)) is not None
    ),
})


def road_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """Why the records the road `capture` was taken on stands on refuse it, over `state`; or None."""
    for refusal in (_pull_request_refusal, _debt_refusal, _adjudication_refusal, _frozen_refusal):
        refused = refusal(state, capture)
        if refused is not None:
            return refused
    return None


def accounting_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """Why `capture`'s run's accounting has not read back over `state`, where it was captured unresolved; or None."""
    if capture.accounting is not _records.CaptureAccounting.UNRESOLVED:
        return None
    receipts = _usage_receipts.read(state)
    counted = receipts is not None and not _usage_counters.miscounted(state.state_data)
    if counted and receipts.covers(capture.invocation):
        return None
    return _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.ACCOUNTING_UNRESOLVED)


def _pull_request_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """A report under a pull-request stage on a record naming no pull request: gone; naming one nobody reads: held."""
    if state.get(_PR_NUMBER) is None:
        return _GONE if capture.handoff.origin in _PULL_REQUEST_STAGES else None
    return _UNREAD if _rewrite_debt.pinned_pull_request(state) is None else None


def _debt_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """A rewritten-head refresh beside no debt, or another publication's, is gone; beside one nobody can read, held.

    The debt has to be the pinned pull request's, on the run's branch, and
    name as its rewritten head the commit the run reported on: a run asked
    for a report of that head and nothing else, which committed onto it or
    ended anywhere else, answers a debt nobody owes it.
    """
    if capture.handoff.route is not _routes.CompletionRoute.REPORT_REFRESH:
        return None
    if not _rewrite_debt.carries_rewrite_debt(state):
        return _GONE
    debt = _rewrite_debt.read_rewrite_debt(state)
    if debt is None:
        return _UNREAD
    pinned = (_rewrite_debt.pinned_pull_request(state), capture.run.branch, capture.run.source_sha)
    return None if (debt.pr_number, debt.branch, debt.rewritten_head) == pinned else _GONE


def anchor_refusal(state: PinnedState) -> _models.Decision | None:
    """Why an auto rebase begun over the capture's branch, and not yet recovered, refuses it; or None.

    The anchor's recovery resets the checkout onto the anchor or pushes the
    replay whenever it cannot prove the attempt, so the commit the report is
    about is no longer the branch's to hand on: no road publishes over a
    rewrite no recovery has finished. Decided ahead of that recovery, so the
    capture is retired before the checkout is touched, and never left for the
    anchor and the capture to wait on each other. Only an anchor that reads
    as a commit proves that rewrite: one that does not is evidence nobody can
    read, and holds the capture. Only an absent or null field is no anchor,
    since every step that ends an attempt blanks it to null
    (`git/base_sync/attempts._clears_the_attempt`): any other spelling --
    `false` or an empty string among them -- is a claim nobody can read too,
    never taken for an absence. Asked behind the road's own answers, so a
    capture waiting through a dependency hold, the `ready` decision, or an
    unlabeled issue is left captured: none of those labels is one the base
    refresh drives, and the anchor's own hold answers the anchor there by a
    clear or a park that leaves the checkout where it stands.
    """
    anchor = state.get(_ANCHOR)
    if anchor is None:
        return None
    if _payloads.as_hex(anchor, _formats.COMMIT_LENGTHS) is None:
        return _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.ANCHOR_UNREAD)
    return _models.Decision(_models.Standing.INVALID, _models.Reason.ANCHORED)


def _adjudication_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """A late revision beside a late record nobody can read: held; beside no live adjudication: gone."""
    if capture.handoff.route is not _routes.CompletionRoute.LATE_REVISION:
        return None
    if importlib.import_module(_stage_targets._LATE_CLAIMS_OWNER)._claims_a_reading(state):
        return _UNREAD
    late_relabel = importlib.import_module(_stage_targets._LATE_RELABEL_OWNER)
    return None if late_relabel._adjudicating(state) else _GONE


def _frozen_refusal(state: PinnedState, capture: _records.CompletionCapture) -> _models.Decision | None:
    """A record the road's handoff was frozen over, moved since: proved stale where its reader reads it, held where not.

    A moved record no reader is registered for holds too: nothing here can
    tell another road's move of it from damage -- a late record no claim of
    the late-claims owner judges among them.
    """
    moved = _frozen.moved_since(state, capture.handoff.frozen)
    if not moved:
        return None
    reads = {**importlib.import_module(_stage_targets._LATE_CLAIMS_OWNER)._FIELD_READS, **_ROAD_READS, **_READS}
    for field in moved:
        reader = reads.get(field)
        if reader is None or not reader(state):
            return _UNREAD
    return _models.Decision(_models.Standing.INVALID, _models.Reason.HANDOFF_MOVED)
