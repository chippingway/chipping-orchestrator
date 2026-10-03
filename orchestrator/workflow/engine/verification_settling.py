# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle a published verification artifact in the one write that makes it current.

The settlement proves the whole binding once more before it declares anything
current, because a post is long enough for any of it to move: another road can
settle a later report or record another review subject on the pinned comment
meanwhile, and a human can close, pause, or end the issue. So the issue is read
afresh and has to be live work still (`verification_live_work`) -- where it is
not, nothing at all is written -- and the pinned comment is read afresh and has
to carry every bound record exactly as the state in hand does
(`verification_durable`), and the whole proof -- pull request, checkout and
trees, context, recorded review subject, settled report at its location,
requirements -- is taken again over them. Last, the artifact itself is read
again at the comment it landed as, on the pull request just proved, and has to
be exactly the one this transaction publishes: the post is long enough for a
human to edit or delete it, and evidence declared current over an artifact
the pull request no longer shows is evidence nobody can be shown. A carry that
copied settled evidence's transcript is held to that source the same way: the
evidence it copied still current, its artifact still saying what was copied
(`verification_current.copied_source_verdict`). The settling
label is read off that same issue. Those readings are requests too, so the
comment is read once more behind them and has to still carry every bound
record as the proof read it -- a review subject removed or replaced meanwhile,
the approval a carried binding answers through among them, is kept and
refuses the settlement. Then ONE write, composed over that last reading rather
than over the state in hand, installs it: the evidence that was current goes into
history as superseded, this one becomes current, the handoff names its
receipt, and the pending record is dropped. A settlement replayed after a
crash in front of that write finds the artifact by its receipt and makes the
same write again. A refusal short of a reading nobody could take leaves any
other transaction owed, but abandons a carry, with the approval it was
recorded for, in the write that records the artifact's ledger entry
(`verification_carries`).

Every write here is measured against what GitHub accepts first, over the
comment as it stands. The room was proved before the post
(`verification_publishing`), but the post is long enough for another road to
fill the comment with fields this settlement does not own; a write past the
limit would be refused with the transaction still owed, so it is not attempted.
The settlement then stands down with the artifact on the thread and the record
owed, for a later tick to find by its receipt once the room is back.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import labels as _labels, pull_request_reports as _pr_reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_evidence_models as _evidence_models,
    report_record_state as _report_record_state,
    verification_durable as _durable,
    verification_live_work as _live_work,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.verification_carries import abandons, is_carry
from orchestrator.workflow.engine.verification_current import copied_source_verdict
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def settles(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> bool:
    """Declare one published transaction current, in one write, or leave it owed.

    Composed over the pinned comment as it stands NOW rather than the state in
    hand, and only once the whole binding is proved over it again.
    """
    durable, fresh, refused = _fresh_world(reading, pending, comment_id)
    if refused is not None:
        log.info(
            "issue=#%d is not settling verification evidence revision %d: %s; "
            "leaving it owed", reading.issue.number, pending.revision, refused.refusal,
        )
        if durable is not None:
            # The artifact is on the thread and its comment id is tracked on
            # the comment as it stands; persisted now, over whatever moved,
            # since the tick that next proves the world may defer before it
            # ever reads the thread again. A carry refused on anything but a
            # reading nobody could take goes into history in that write, with
            # the approval it was recorded for.
            if not refused.holds and is_carry(pending):
                abandons(durable, pending)
            _writes(reading, durable)
        return refused.holds
    composed = _settlement.settled_state(durable, pending, comment_id, _label_of(fresh))
    if composed is None:
        log.error(
            "issue=#%d published verification evidence revision %d and settles "
            "into a record this build will not store; holding the tick",
            reading.issue.number, pending.revision,
        )
        return True
    if not _writes(reading, composed):
        log.error(
            "issue=#%d published verification evidence revision %d and its "
            "pinned comment filled while it was posted; leaving it owed",
            reading.issue.number, pending.revision,
        )
        _writes(reading, durable)
        return False
    log.info(
        "issue=#%d settled verification evidence revision %d on PR #%d",
        reading.issue.number, pending.revision,
        pending.binding.target.publication.pr_number,
    )
    return False


def _fresh_world(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> tuple[PinnedState | None, Issue | None, _evidence_models.ReportEvidence | None]:
    """The comment and issue read afresh, and the refusal the binding earns over them.

    The comment has to carry every bound record as the state in hand does
    (`verification_durable`); the artifact's comment id is tracked on it, and
    then the whole proof is taken again over it and the fresh issue -- the pull
    request, the checkout and trees, the context, the recorded review subject,
    the settled report re-read at its location, and the requirements -- and the
    artifact re-read on the pull request that proof read. Those are requests
    of their own, so the comment any write is composed over is the one read
    behind them (`_read_behind_the_proof`).
    """
    try:
        fresh = reading.gh.get_issue(reading.issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read before settling its verification "
            "evidence", reading.issue.number,
        )
        return None, None, _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue could not be re-read before the settlement",
        )
    aside = _liveness_refusal(fresh)
    if aside is not None:
        return None, fresh, aside
    durable, moved = _durable.durable_comment(reading.gh, fresh, reading.state)
    if durable is not None:
        _comments._track_orchestrator_comment(durable, comment_id)
    if moved is not None:
        return durable, fresh, moved
    proved = _proof.binding_verdict(
        _proof.ProofReading(reading.gh, reading.spec, fresh, durable), pending.binding,
    )
    if proved.proved:
        proved = _artifact_refusal(reading, pending, proved.pull_request, comment_id)
    durable, moved = _read_behind_the_proof(reading, fresh, durable, comment_id)
    return durable, fresh, moved or proved


def _read_behind_the_proof(
    reading: _proof.ProofReading,
    fresh: Issue,
    proved_over: PinnedState,
    comment_id: int,
) -> tuple[PinnedState | None, _evidence_models.ReportEvidence | None]:
    """The comment read once more behind the proof, the artifact's entry tracked on it, and the refusal it earns.

    The proof's requests are long enough for another road to write the
    comment: a review subject recorded, replaced, or removed -- the approval
    record a carried binding answers through among them -- or a report
    settled. A write composed over the reading the proof was taken over would
    put each of those back, and declare evidence current for a subject the
    comment no longer carries. So every write here is composed over this
    reading instead, which has to still carry every bound record exactly as
    the proof read them (`verification_durable`): one that moved refuses the
    settlement with the transaction owed, and one that will not read holds
    with nothing written.
    """
    latest, moved = _durable.durable_comment(reading.gh, fresh, proved_over)
    if latest is not None:
        _comments._track_orchestrator_comment(latest, comment_id)
    return latest, moved


def _artifact_refusal(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    pull_request: Any,
    comment_id: int,
) -> _evidence_models.ReportEvidence | None:
    """Refuse an artifact that is no longer exactly this transaction's at `comment_id`, or None.

    A thread nobody could read holds; an artifact gone, edited, or any other
    defers with the transaction owed, for the next publication lookup to find
    it again by its receipt -- or post it again where it is gone. Behind it,
    the source a carry copied its transcript from is read again on the same
    pull request (`verification_current.copied_source_verdict`): the post is
    long enough for a human to edit or delete that one too.
    """
    presence, found = reading.gh.reread_verification_artifact(pull_request, comment_id)
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the published artifact could not be re-read before the settlement",
        )
    if presence is _pr_reports.ReportPresence.PRESENT and found == pending.artifact:
        return copied_source_verdict(reading.gh, reading.state, pending, pull_request)
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the published artifact is gone or no longer the one this transaction posted",
    )


def _liveness_refusal(fresh: Issue) -> _evidence_models.ReportEvidence | None:
    """Refuse an issue read afresh that is no longer live work, or None.

    Asked before the pinned comment is read, and a refusal comes back with no
    comment at all, so nothing -- not even the artifact's ledger entry -- is
    written onto an issue somebody has closed, paused, or ended meanwhile.
    """
    try:
        aside = _live_work.stands_aside(fresh, _labels.workflow_label(fresh))
    except Exception:
        log.exception(
            "issue=#%d could not be read again for its labels and state before "
            "settling its verification evidence", fresh.number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue's labels and state could not be re-read before the settlement",
        )
    if not aside:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the issue stopped being live work while the artifact was posted",
    )


def _label_of(fresh: Issue) -> WorkflowLabel | None:
    """The workflow label `fresh` carries, or None where it will not read.

    Fail-closed: a settlement raising out of a lazy label read would leave the
    artifact published and the transaction still owed.
    """
    try:
        return _labels.workflow_label(fresh)
    except Exception:
        log.exception(
            "issue=#%d could not read the label its verification evidence "
            "settled under; recording the settlement without one", fresh.number,
        )
        return None


def _writes(reading: _proof.ProofReading, composed: PinnedState) -> bool:
    """Install `composed` as the state in hand and write it, where the comment can carry it.

    False, writing nothing and leaving the state in hand as it was, where it
    cannot: the artifact's ledger entry included, which is dropped then rather
    than written past the limit, and read back off the thread by the retry.
    """
    if not _report_record_state.fits_the_comment(composed.data):
        return False
    reading.state.data = composed.data
    reading.gh.write_pinned_state(reading.issue, reading.state)
    return True
