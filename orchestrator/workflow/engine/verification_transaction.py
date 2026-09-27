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
pull request's head is not yet what anything downstream may believe. The
report transaction outranks it too: evidence answers for a review subject that
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
composed over that fresh reading, so a transaction another road recorded
meanwhile is never written away. Everything else short of proof either HOLDS
the tick over a reading nobody could take or STANDS DOWN with the transaction
still owed, for a push, a drift resume, a fresh reviewer, or fresher evidence
to answer.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
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

log = logging.getLogger("orchestrator.workflow")


def _reconciles_pending_evidence(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """Finish an evidence transaction this issue recorded and never completed.

    True is a tick this owner holds over a reading nobody could take. False is
    every other tick: nothing owed, work that is not live, a transaction
    settled, retired, or still owed behind a structural refusal.
    """
    if not _record_state.carries_pending_evidence(state):
        return False
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
    anything else that could be said about it.
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
    if not evidence.proved:
        log.info(
            "issue=#%d cannot make verification evidence revision %d current "
            "yet: %s", issue.number, pending.revision, evidence.refusal,
        )
        return evidence.holds
    return _publishing.publishes(reading, pending, evidence.pull_request)


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
    """Retire a transaction that will never settle, over the comment as it stands.

    Composed over the pinned comment read afresh rather than the state the
    tick holds, which has to still carry every bound record exactly as that
    state does (`verification_durable`): another road may have recorded a
    newer transaction since, and a retirement composed over the older state
    would erase it and lower the revision floor under it. A comment that will
    not read holds the tick; one where a record moved stands down with nothing
    written, for the next tick to answer what it carries then.

    `indexed` drops the record outright, for a revision a settled or retired
    record already carries. Otherwise it is abandoned into history through its
    owner, and a retirement the comment could not carry writes nothing: the
    record stays owed, which every consumer already fails closed on. The write
    is this owner's, since a record left standing would be answered again on
    every poll.
    """
    durable, moved = _durable.durable_comment(gh, issue, state)
    if moved is not None:
        log.info(
            "issue=#%d is not retiring the verification evidence it owes: %s",
            issue.number, moved.refusal,
        )
        return moved.holds
    if indexed:
        durable.set(_records.PENDING_EVIDENCE, None)
    elif not _settlement.retire_pending_evidence(durable, pending):
        log.error(
            "issue=#%d has no room on its pinned comment to retire the "
            "verification evidence it owes; leaving it owed", issue.number,
        )
        return False
    state.data = durable.data
    gh.write_pinned_state(issue, state)
    return False
