# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Verification evidence this issue recorded and has not yet made current.

The record is durable and the publication behind it is not, so a tick that
dies in between leaves an issue whose pinned comment says an artifact is owed
and whose pull request may or may not carry it. The reconciliation is taken
here, ahead of the stage handler, in the report transaction's shape: prove the
world, post the artifact, settle the record, and let the stage run behind a
world that matches what the record says. It never completes on an absence.

It sits among the dispatch guards directly behind the developer-report
transaction, and that place is the point. A pause, a terminal, a live
adjudication, an outstanding size-gate publication and its lease, and a
standing auto-rebase anchor all outrank it, since each is a world in which the
pull request's head is not yet what anything downstream may believe -- and the
anchor is asked again here, so a transaction a landed rewrite's finish recorded
is left to the recovery that owes it while the attempt stands, whoever calls
this. The report transaction outranks it too: evidence answers for a review subject that
names the developer report, so a report still owed is a subject about to move,
and this proof defers to it. Behind them, it runs ahead of the reuse guard and
the handler, so a reviewer or a readiness decision behind it reads evidence
that is either settled or honestly still owed.

It also stands aside on its own for everything the dispatcher would hand it
that is not live work (`verification_live_work`): an issue closed, labelled
`done` or `rejected`, carrying a hard-skip control label, or carrying no
workflow label at all. Nothing is published or dropped on any of those, so a
reopen or a relabel finds the record exactly as it was -- and the settlement
asks the same again of the issue read afresh after the post.

Unlike the report transaction it never parks. Evidence is reproducible and
fails closed -- an issue with no current evidence is one every consumer asks
fresh evidence for -- so what nobody can act on is RETIRED rather than put in
front of a human: a record that will not read is dropped, and one that can
never settle -- its pull request ended, a later transaction recorded past it,
or revisions spent that nobody can read (`verification_record_state`) -- is
abandoned into history, where its receipt and revision stay recorded. A record
whose revision a settled or retired record already carries -- a replay the
handoff names, or one a restored comment brought back -- is dropped without a
second post or a second history entry, since an index naming one revision
twice is one its own reader refuses. A retirement the comment has no room for
writes nothing and leaves the record owed, and so does one whose pinned
comment, read afresh, no longer carries what the tick read: every retirement is
staged on that fresh reading and committed guarded by it
(`verification_durable`), so a transaction, an approval, or a floor another
road wrote meanwhile is never written away, and every field the retirement
does not own is kept as the comment carries it. One that went out and was
never confirmed holds the tick, and the next finds the record gone or retires
it again, with no second entry. Everything else short of proof either HOLDS
the tick over a reading nobody could take or STANDS DOWN with the transaction
still owed, for a push, a drift resume, a fresh reviewer, or fresher evidence
to answer.

Save a CARRY: a transaction carrying a run onto a head it did not run on,
which an approval's squash records onto the head it published and a landed
base rewrite's finish onto its rewritten head (`rewrite_finish_evidence`), and
which nothing later makes answer again once refused. Any refusal of it but a
reading nobody could take abandons it into history with the approval it was
recorded for -- the squash's own; a base rewrite's carry takes one only where
it is exactly the review of the rewritten head the carry answers for
(`verification_carries`) -- here, ahead of the post, and on the publication
and the settlement behind it (`verification_publishing`,
`verification_settling`) -- for a fresh reviewer to answer the head as it
stands. A bound record another road moved under the settlement is a refusal of
what the tick decided over, not of the carry, and leaves it owed for the next
tick to answer here over the comment as it reads then. A carry that copied settled
evidence's transcript is refused here too where that source no longer says
what it copied (`verification_current.copied_source_verdict`), and again
ahead of its settlement.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_publication_evidence as _publication,
    verification_durable as _durable,
    verification_live_work as _live_work,
    verification_proof as _proof,
    verification_publishing as _publishing,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.verification_carries import abandons_afresh, is_carry
from orchestrator.workflow.engine.verification_current import copied_source_verdict

log = logging.getLogger("orchestrator.workflow")


def _reconciles_pending_evidence(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """Finish an evidence transaction this issue recorded and never completed.

    True is a tick this owner holds over a reading nobody could take, or
    behind a standing auto-rebase anchor. False is every other tick: nothing
    owed, work that is not live, a transaction settled, retired, or still owed
    behind a structural refusal.

    The anchor is asked here as well as ahead of this guard: a transaction a
    landed rewrite's finish recorded is the recovery's to route or abandon
    while the attempt stands, and settled here behind its back it would
    outlive a movement the recovery read but could not yet record.
    """
    if not _record_state.carries_pending_evidence(state):
        return False
    if state.get(_base_sync_state._PENDING_PUSH_SHA):
        log.info(
            "issue=#%d leaves the verification evidence it owes to the recovery of its standing base rewrite",
            issue.number,
        )
        return True
    if _live_work.stands_aside(issue, label):
        log.info(
            "issue=#%d is not live work (label=%r); leaving the verification "
            "evidence it owes where it stands", issue.number, label,
        )
        return False
    pending = _record_state.read_pending_evidence(state)
    if pending is None:
        log.error(
            "issue=#%d records verification evidence this build cannot read; "
            "dropping it, since evidence nobody can read is evidence nobody has",
            issue.number,
        )
        return _retires(gh, issue, state, None)
    return _answers_what_is_owed(gh, spec, issue, state, pending)


def _answers_what_is_owed(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingEvidence,
) -> bool:
    """Answer one readable transaction: replayed, outdated, ended, unproved, or published.

    The two pinned questions come first, since they cost nothing and neither
    depends on the pull request. Then the pull request, which every other
    reading stands behind: an ENDED one retires the transaction ahead of
    anything else that could be said about it. The source a carry copied is
    read last, on the pull request the proof read.
    """
    if _already_recorded(state, pending):
        log.info(
            "issue=#%d already settled or retired verification evidence "
            "revision %d; dropping the record rather than repeating it",
            issue.number, pending.revision,
        )
        return _retires(gh, issue, state, pending, indexed=True)
    if _outdated(state, pending):
        log.info(
            "issue=#%d recorded verification evidence past revision %d, or "
            "cannot say what it spent; abandoning it", issue.number, pending.revision,
        )
        return _retires(gh, issue, state, pending)
    found = _publication.subject_verdict(gh, pending.binding.target.publication)
    if found.ended:
        log.info(
            "issue=#%d owes verification evidence to a pull request that is "
            "over; abandoning revision %d", issue.number, pending.revision,
        )
        return _retires(gh, issue, state, pending)
    reading = _proof.ProofReading(gh, spec, issue, state)
    evidence = _proof.rest_verdict(reading, pending.binding, found)
    if evidence.proved:
        evidence = copied_source_verdict(gh, state, pending, evidence.pull_request) or evidence
    if not evidence.proved:
        return _stands_down(reading, pending, evidence)
    return _publishing.publishes(reading, pending, evidence.pull_request)


def _stands_down(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    evidence: ReportEvidence,
) -> bool:
    """Answer a proof short of PROVED: hold an unread reading, abandon a refused carry, leave the rest owed.

    True where the tick is held. A carry is abandoned on every refusal but a
    reading nobody could take, since nothing a later route does makes it
    answer again; any other transaction stays owed for that route.
    """
    log.info(
        "issue=#%d cannot make verification evidence revision %d current "
        "yet: %s", reading.issue.number, pending.revision, evidence.refusal,
    )
    if evidence.holds or not is_carry(pending):
        return evidence.holds
    return _retires(reading.gh, reading.issue, reading.state, pending)


def _already_recorded(state: PinnedState, pending: _records.PendingEvidence) -> bool:
    """Whether a settled or retired record already carries this transaction's revision."""
    recorded = (
        _settlement.read_current_evidence(state),
        _settlement.read_evidence_handoff(state),
        *(_settlement.read_evidence_history(state) or ()),
    )
    return any(
        record is not None and record.revision == pending.revision
        for record in recorded
    )


def _outdated(state: PinnedState, pending: _records.PendingEvidence) -> bool:
    """Whether this issue spent a revision past this one, or nobody can say.

    Read off the revision floor every record raises in its own write, so a
    transaction recorded past this one and since dropped still counts: settling
    this would put an older run over an artifact that may already be newer.
    """
    latest = _record_state._latest_revision(state)
    return latest is None or latest > pending.revision


def _retires(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingEvidence | None,
    *,
    indexed: bool = False,
) -> bool:
    """Retire a transaction that will never settle, in one guarded commit over the comment as it stands; True holds.

    Staged on the pinned comment read afresh rather than the state the tick
    holds, which has to still carry every bound record exactly as that state
    does (`verification_durable`), and committed guarded by that reading:
    another road may have recorded a newer transaction since, and a
    retirement composed over the older state would erase it and lower the
    revision floor under it. A comment that will not read holds the tick; one
    where a record moved, before that reading or under the commit, stands
    down with nothing written, for the next tick to answer what it carries
    then. Every field the retirement does not own is kept as the comment
    carries it when it lands.

    `indexed` drops the record outright, for a revision a settled or retired
    record already carries, owning that record alone. Otherwise it is
    abandoned into history through its owner
    (`verification_carries.abandons_afresh`), and a retirement the comment
    could not carry leaves the record owed, which every consumer already
    fails closed on; a carry takes the approval it was recorded for with it,
    in the same commit -- where its entry has no room as well, since that only
    shrinks the comment. Nothing is sent where nothing changed, and a commit
    nobody confirmed holds: the next tick finds the record gone, or retires
    it again, with no second history entry. The write is this owner's, since
    a record left standing would be answered again on every poll.
    """
    if not indexed:
        return abandons_afresh(gh, issue, state, pending)
    durable, refused = _durable.durable_comment(gh, issue, state)
    if refused is None:
        guard = _durable.guarded(durable, (_records.PENDING_EVIDENCE,))
        durable.set(_records.PENDING_EVIDENCE, None)
        refused = _durable.lands(gh, issue, state, guard, durable)
    if refused is None:
        return False
    log.info(
        "issue=#%d is not dropping the verification evidence record it already "
        "settled or retired: %s", issue.number, refused.refusal,
    )
    return refused.holds
