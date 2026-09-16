# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer report this issue recorded and never finished publishing.

The record is durable and the publication that follows it is not, so a tick that
dies in between leaves an issue whose pinned comment says a report is owed and
whose pull request does not carry it. Nothing on the stage that recorded it would
go back for that on its own: the handler spawns a reviewer, resumes a developer,
or reads a pull request it believes is up to date, while the report the next
reviewer needs is sitting in the record nobody is reading.

So the reconciliation is taken HERE, ahead of the handler, and it is the same
shape the frozen-pair reconciliation beside it has: prove the world, make the
effect, settle the record, and let the stage run behind a world that matches what
the record said. What it never does is complete on an absence. Every refusal
short of proof either holds the tick or stands down, and neither writes a
handoff -- so an unpublished candidate is never presented as one that reached the
pull request.

Where it sits among the guards is deliberate. A pause, a terminal, and the
outstanding publication and adjudication guards all outrank it: an issue somebody
paused is not one to publish a report on, work that has ended needs no report,
and a candidate the size gate froze has to be settled before anything downstream
of the push can be believed -- this owner's own evidence asks whether the commit
reached the pull request, which is the very question that reconciliation answers.
Behind them, it runs ahead of the reuse guard and the stage handler, because both
of those are roads that would carry on over a report nobody published.

A record that CLAIMS a transaction and cannot produce one is refused ahead of all
of it. Every field is read fail-closed, so a damaged record reads as no record --
and read that way the guard would answer "nothing outstanding" and hand the stage
an issue whose report obligation nobody can describe. Asked for its presence
first, it parks instead, once, for a human to repair the comment.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    report_evidence as _evidence,
    report_evidence_models as _evidence_models,
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")

_PARK_REASON = "park_reason"

# What a record nobody can read is parked under. Durable, because the condition
# does not clear on its own: what it asks for is the pinned comment repaired,
# and the retry getting further is how that is answered.
_DAMAGED_RECORD = "report_record_damaged"

_DAMAGED_RECORD_PARK = (
    "{mentions} this issue records a developer report it still owes its pull "
    "request, and the record cannot be read -- a field is missing, or is not "
    "the shape this orchestrator writes. Nothing was published and nothing was "
    "discarded: the branch, the pull request, and every other record are "
    "exactly as they were. The workflow is held here rather than carried on, "
    "because a report obligation nobody can describe is one the next reviewer "
    "would be handed without. Repair the pinned comment -- or clear the "
    "`developer_report_pending` field to abandon the report -- and the next "
    "tick resumes on its own."
)


def _reconciles_pending_report(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Finish a report transaction this issue recorded and never completed.

    True is a tick this owner finished -- held over a reading nobody could
    take, or parked over a record nobody can read. False is every other issue
    on every other tick, and also the transaction this call just settled: the
    report is on the pull request, the handoff is recorded, and the handler
    below carries on with an issue whose report obligation is discharged.

    Presence is asked before meaning, and that order is the point: a damaged
    record and an issue with nothing outstanding are the same answer to the
    reader and opposite answers to this guard.

    A handoff already naming this receipt is the replay of a transaction that
    finished -- the report landed and the process died before the record was
    dropped -- so the record goes and nothing is published a second time.
    """
    if not _record_state.carries_pending_report(state):
        return False
    pending = _record_state.read_pending_report(state)
    if pending is None:
        return _parks_the_damage(gh, issue, state)
    handoff = _settlement.read_handoff(state)
    if handoff is not None and handoff.receipt == pending.receipt:
        log.info(
            "issue=#%d records a developer-report handoff that already "
            "finished; dropping the transaction rather than repeating it",
            issue.number,
        )
        return _drops(gh, issue, state)
    return _answers_the_transaction(gh, spec, issue, state, pending)


def _answers_the_transaction(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
) -> bool:
    """Prove the world this transaction named, then finish it or stand down.

    A pull request that has ended retires the transaction: a report posted onto
    a merged or closed thread is a comment nobody reads, and holding one for it
    forever would strand the issue on work that is over.

    Everything else short of proof refuses without writing anything. A reading
    nobody could take holds the tick, since the next one is as likely to
    succeed. Everything structural stands down, because what would clear it is
    a route behind this guard -- the publication gate that pushes the commit,
    the drift resume that answers an edited issue, the park a dirty tree earns.
    Either way no handoff is written, so the transaction is still owed.
    """
    evidence = _evidence.evidence_for(gh, spec, issue, state, pending)
    if evidence.verdict is _evidence_models.ReportEvidenceVerdict.ENDED:
        log.info(
            "issue=#%d owes a developer report to PR #%d, which is over (%s); "
            "dropping the transaction",
            issue.number, pending.subject.pr_number, evidence.refusal,
        )
        return _drops(gh, issue, state)
    if not evidence.proved:
        log.info(
            "issue=#%d cannot complete developer report revision %d yet: %s",
            issue.number, pending.report_revision, evidence.refusal,
        )
        return evidence.holds
    if pending.mode is _records.ReportMode.PUBLISH:
        return _publishing.publishes_the_report(
            gh, issue, state, pending, evidence.pull_request,
        )
    return _publishing.verifies_the_report(gh, issue, state, pending)


def _parks_the_damage(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Hold a tick whose report record nobody can read, and say so once.

    Announced once. The park is durable and the condition is not one that
    clears on its own, so a record that stays damaged would otherwise put a
    fresh notice on the thread every poll and bury the first one. A tick that
    finds the park already standing is held silently, and the moment the record
    reads again the ordinary reconciliation resumes.
    """
    if state.get(_PARK_REASON) == _DAMAGED_RECORD:
        log.warning(
            "issue=#%d still carries a developer-report record that cannot be "
            "read; holding the tick without a second notice", issue.number,
        )
        return True
    log.error(
        "issue=#%d records a developer report this build cannot read; "
        "refusing to run the stage over an obligation nobody can describe",
        issue.number,
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        _DAMAGED_RECORD_PARK.format(mentions=config.HITL_MENTIONS),
        reason=_DAMAGED_RECORD,
    )
    state.set(_PARK_REASON, _DAMAGED_RECORD)
    gh.write_pinned_state(issue, state)
    return True


def _drops(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Drop a transaction nothing is owed for, and let the tick carry on.

    The write is this owner's because no handler runs behind a drop that
    matters: a record left standing would be reconciled again on every poll,
    and the reading that retires it is one this tick already paid for.
    """
    _record_state.clear_pending_report(state)
    gh.write_pinned_state(issue, state)
    return False
