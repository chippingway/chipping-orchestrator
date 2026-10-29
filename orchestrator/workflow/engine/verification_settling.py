# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle a published verification artifact in the one guarded commit that makes it current.

The settlement proves the whole binding once more before it declares anything
current, because a post is long enough for any of it to move: another road can
settle a later report or record another review subject on the pinned comment
meanwhile, and a human can close, pause, or end the issue. So the issue is read
afresh and has to be live work still (`verification_live_work`) -- where it is
not, nothing at all is written -- and the label the settlement is recorded
under is read off that same issue. The pinned comment is read afresh and has
to carry every bound record exactly as the state in hand does
(`verification_durable`) -- and every record the reading rests on beside them
(`verification_proof.ProofReading.rests_on`), a standing auto-rebase attempt
among them -- and then the whole proof is taken again over them. The pull
request comes first, and right behind it the artifact itself is read again at
the comment it landed as and has to be exactly the one this transaction
publishes: the post is long enough for a human to edit or delete it, and
evidence declared current over an artifact the pull request no longer shows is
evidence nobody can be shown. A carry that copied settled evidence's
transcript is held to that source the same way: the evidence it copied still
current, its artifact still saying what was copied
(`verification_current.copied_source_verdict`). Those re-reads are requests,
so every other reading of the proof is taken behind them -- the checkout and
trees, context, recorded review subject, settled report at its location,
requirements, and the landing and base a standing auto-rebase anchor holds the head to
(`verification_proof.ProofReading.anchored`) -- and a requirement edited or a
base advanced while the artifact was re-read refuses the settlement. Those
readings are requests too, so the comment is read once more behind them and
has to still carry every bound record as the proof read it -- a review subject
removed or replaced meanwhile, the approval a carried binding answers through
among them, is kept and refuses the settlement. Every one of those requests
-- the settled report's re-read above all -- is long enough for a human to
edit or delete the artifact too, so behind them it is re-read once more and
has to still be exactly this transaction's. The readings no guarded commit
holds are taken last of all, behind that, in the order that leaves none of
them in front of a request (`verification_unguarded`): the anchor's landing and
base asked again, then the issue fetched once more -- still live work, and its
requirements hashed over that very reading rather than one taken before the
anchor's requests -- and the configuration read once more last, so an edit, an
advance, or a command configured otherwise while those requests were answered
refuses it too. Every
refusal of the binding read along the way, a bound record read moved among
them, is kept the moment it is read for a caller that collects them
(`verification_proof.ProofReading.observed`), whatever a reading behind it --
one nobody could take among them -- comes to.

Then ONE guarded commit (`pinned_commit.commit`) installs it, composed over
that last reading and guarded by it: the evidence that was current goes into
history as superseded, this one becomes current, the handoff names its
receipt, the pending record is dropped, the revision floor stays where the
transaction's own record raised it, and the artifact's comment id enters the
ledger. The commit reads the comment once more and lays exactly those fields
over it only where every bound record still reads as the proof read it,
keeping every other field -- a usage total, a watermark, another domain's
record -- as it finds it, and merging the ledger entry into whatever ledger it
finds (`verification_comments.MERGED_LEDGER`). The whole candidate is measured
against what one comment holds before anything goes out. The room was proved
before the post (`verification_publishing`), but the post is long enough for
another road to fill the comment with fields this settlement does not own;
such a commit is refused before anything goes out, with the transaction owed
for a later tick to find by its receipt once the room is back.

A settlement replayed after a crash in front of the commit finds the artifact
by its receipt and makes the same commit again; one whose commit went out and
was never confirmed holds, and the next tick finds either nothing owed or the
same transaction to settle, over the same artifact. Neither posts a second
artifact or writes a second history entry.

Wherever the settlement does not land over a comment that still reads -- the
binding refused over it, or the commit refused for a record that moved, a
comment that moved under the edit, or a lack of room -- the artifact's ledger
entry is committed alone (`verification_comments.records_the_artifact`), since
the tick that next proves the world may defer before it ever reads the thread
again; where that entry finds the comment unreadable, replaced, or no longer
parsing, or goes out unconfirmed, the tick holds, since nothing behind the
reconciliation may act on a record nobody can say. A refusal of the binding
short of a reading nobody could take abandons a carry instead, with the
approval it was recorded for, in one guarded commit that records that entry
too, staged on and guarded by the comment read behind the proof
(`verification_carries`) -- and only while that comment still carries every
bound record as the tick read it, since a record another road moved ahead of
the proof or during it refuses what the tick decided over rather than the
binding. Where that abandonment is not made, or does not land over a comment
that still reads, the carry stays owed and the entry is committed alone. A
transaction a landed base rewrite's finish settles while its anchor stands is
abandoned on the same terms as a carry
(`verification_carries.abandons_on_refusal`). A settlement commit that did not
land never abandons one, since nothing refused the binding.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import labels as _labels, pull_request_reports as _pr_reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit as _commit,
    verification_comments as _verification_comments,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_records as _records,
    verification_unguarded as _unguarded,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.verification_carries import ABANDONS, abandons, abandons_on_refusal
from orchestrator.workflow.engine.verification_current import copied_source_verdict
from orchestrator.workflow.engine.verification_settlement_state import settled_state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# What a settlement may write: this domain's four records, the revision floor
# beside them -- left as the transaction's own record raised it, and held to
# that as a bound record -- and the ledger entry its artifact takes. The
# publication prepares the same commit ahead of the post.
SETTLES = (
    _records.PENDING_EVIDENCE,
    _records.CURRENT_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _records.EVIDENCE_HANDOFF,
    _records.REVISION_FLOOR,
    *_verification_comments.MERGED_LEDGER,
)

# What abandoning a carry whose binding was refused may write: the
# abandonment's own fields, and the ledger entry its artifact takes.
ABANDONS_RECORDING = (*ABANDONS, *_verification_comments.MERGED_LEDGER)


def settles(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> bool:
    """Declare one published transaction current, in one guarded commit, or leave it owed; True holds the tick.

    Composed over the pinned comment as it stands behind the whole proof
    rather than the state in hand, and committed only over a comment still
    carrying every bound record as that reading did.
    """
    fresh = _unguarded.live_issue(reading)
    if isinstance(fresh, ReportEvidence):
        latest, refused = None, fresh
    else:
        latest, refused = _proof_refusal(reading, fresh, pending, comment_id)
        if refused is None:
            return _commits(reading, latest, _label_of(fresh), pending, comment_id)
    log.info(
        "issue=#%d is not settling verification evidence revision %d: %s; "
        "leaving it owed", reading.issue.number, pending.revision, refused.refusal,
    )
    if latest is None:
        return refused.holds
    return _leaves_it_owed(reading, latest, pending, comment_id, refused)


def _proof_refusal(
    reading: _proof.ProofReading,
    fresh: Issue,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> tuple[PinnedState | None, ReportEvidence | None]:
    """The comment read behind the whole proof, and the refusal the binding earns over it.

    The comment has to carry every bound record as the state in hand does
    (`verification_durable`), and then the whole proof is taken again over it
    and the fresh issue: the pull request, the artifact re-read on it right
    behind that reading, and then everything else -- the checkout and trees,
    the context, the recorded review subject, the settled report re-read at
    its location, the requirements, and the landing and base a standing anchor holds the
    head to -- so the re-read of the artifact is a request every one of those
    readings lies behind. Those are requests of their own, long enough for
    another road to record, replace, or remove a review subject -- the
    approval record a carried binding answers through among them -- or settle
    a report, so the comment is read once more behind them and has to still
    carry every bound record exactly as the proof read them. Behind that
    (`_behind_the_proof`) the artifact is re-read once more, since every one of
    those requests is long enough to edit it too, and then come the readings
    the settlement's guarded commit does not hold
    (`verification_unguarded.unguarded_refusal`): the anchor's landing and
    base, then the issue fetched again and its requirements hashed over that
    reading, and the configuration last -- the commit behind them is the only
    request left. That last comment reading is the one the
    settlement is composed over and guarded by, and the one a refusal leaves
    anything on; None where it will not read, and where the issue read last is
    no longer live work, which leaves nothing written. Every comment reading is
    held to the records the reading rests on as well (`ProofReading.rests_on`).
    """
    durable, refused = _durable.durable_comment(reading.gh, fresh, reading.state, reading.rests_on)
    reading.observes(refused)
    if refused is not None:
        return durable, refused
    proved = _proof.binding_verdict(
        _proof.ProofReading(reading.gh, reading.spec, fresh, durable, reading.anchored, reading.rests_on),
        pending.binding,
        lambda pull_request: _artifact_refusal(reading, pending, pull_request, comment_id),
    )
    refused = None if proved.proved else proved
    reading.observes(refused)
    durable, moved = _durable.durable_comment(reading.gh, fresh, durable, reading.rests_on)
    reading.observes(moved)
    if moved is not None or refused is not None:
        return durable, moved or refused
    return _behind_the_proof(reading, durable, pending, proved.pull_request, comment_id)


def _behind_the_proof(
    reading: _proof.ProofReading,
    durable: PinnedState,
    pending: _records.PendingEvidence,
    pull_request: Any,
    comment_id: int,
) -> tuple[PinnedState | None, ReportEvidence | None]:
    """What the readings behind the whole proof and the comment's re-read refuse, over `durable`; or None.

    The artifact is read once more first (`_artifact_refusal`): the proof's
    own requests -- the settled report's re-read among them -- and the
    comment's are long enough for a human to edit or delete it, and the
    earlier re-read, ahead of them, saw none of that. Then the readings the
    settlement's guarded commit does not hold
    (`verification_unguarded.unguarded_refusal`), so an issue edited or a
    command configured otherwise while the artifact was read again refuses it
    too. The comment is None where the issue read last would not read or is
    no longer live work, which leaves nothing written.
    """
    edited = _artifact_refusal(reading, pending, pull_request, comment_id)
    reading.observes(edited)
    if edited is not None:
        return durable, edited
    behind, refused = _unguarded.unguarded_refusal(reading, durable, pending)
    return (None if behind is None else durable), refused


def _artifact_refusal(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    pull_request: Any,
    comment_id: int,
) -> ReportEvidence | None:
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
        return ReportEvidence(
            ReportEvidenceVerdict.HOLD,
            "the published artifact could not be re-read before the settlement",
        )
    if presence is _pr_reports.ReportPresence.PRESENT and found == pending.artifact:
        return copied_source_verdict(reading.gh, reading.state, pending, pull_request)
    return ReportEvidence(
        ReportEvidenceVerdict.DEFER,
        "the published artifact is gone or no longer the one this transaction posted",
    )


def _commits(
    reading: _proof.ProofReading,
    latest: PinnedState,
    label: WorkflowLabel | None,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> bool:
    """Make `pending` current in one guarded commit composed over `latest`; True where the tick holds.

    Where it lands, the reading it landed as becomes the state in hand, for
    the stage behind the reconciliation to read, and the reading that state is
    synced with (`pinned_commit.takes_in`), so a guarded commit behind it counts
    none of it as the tick's own move. Where it does not, the
    transaction stays owed and the artifact's ledger entry is committed
    alone; a carry is never abandoned for a commit that did not land, since
    nothing refused its binding. One that went out and was never confirmed
    holds, since the comment may read either way, and so does a ledger entry
    that meets a comment nobody can read as the one this tick read.
    """
    composed = settled_state(latest, pending, comment_id, label)
    if composed is None:
        log.error(
            "issue=#%d published verification evidence revision %d and settles "
            "into a record this build will not store; holding the tick",
            reading.issue.number, pending.revision,
        )
        return True
    _comments._track_orchestrator_comment(composed, comment_id)
    outcome = _commit.commit(
        reading.gh, reading.issue, _durable.guarded(latest, SETTLES, reading.rests_on), composed.state_data,
        _verification_comments.MERGED_LEDGER,
    )
    refused = _durable.refusal_of(outcome)
    if refused is None:
        reading.state.state_data = outcome.reading.state_data
        _commit.takes_in(reading.state, outcome.reading.state_data)
        log.info(
            "issue=#%d settled verification evidence revision %d on PR #%d",
            reading.issue.number, pending.revision,
            pending.binding.target.publication.pr_number,
        )
        return False
    log.error(
        "issue=#%d published verification evidence revision %d and did not "
        "settle it: %s; leaving it owed", reading.issue.number, pending.revision,
        refused.refusal,
    )
    if refused.holds:
        return True
    if outcome.fields:
        reading.observes(refused)
    return _verification_comments.records_the_artifact(reading.gh, reading.issue, reading.state, comment_id)


def _leaves_it_owed(
    reading: _proof.ProofReading,
    latest: PinnedState,
    pending: _records.PendingEvidence,
    comment_id: int,
    refused: ReportEvidence,
) -> bool:
    """Leave on the comment what a refused binding owes it, the artifact's entry or a carry's abandonment; True holds.

    The artifact is on the thread whatever was refused, so its ledger entry
    is committed over the comment as it stands
    (`verification_comments.records_the_artifact`); a comment that entry
    finds nobody can read as the one this tick read holds the tick, whatever
    the binding was refused for. A carry whose binding was refused on
    anything but a reading nobody could take -- or a transaction settled under
    a standing auto-rebase anchor (`verification_carries.abandons_on_refusal`)
    -- goes into history instead, with
    the approval it was recorded for and that ledger entry, in one guarded
    commit staged on `latest`, the comment read behind the proof, and guarded
    by it (`ABANDONS_RECORDING`, `verification_carries`): a record another
    road moved after that reading refuses it, every field it does not own is
    kept as the comment carries it, and the ledger entry is merged into
    whatever ledger it finds. Only where `latest` still carries every bound
    record as the tick read it, though: a record another road moved ahead of
    the proof or during it is a refusal of what the tick decided over, not of
    the binding, so the carry stays owed for the next tick to decide over
    what the comment carries then, with the ledger entry committed alone --
    as it is wherever the abandonment does not land over a comment that still
    reads. Where it lands, the reading it landed as becomes the state in
    hand, and the reading that state is synced with (`pinned_commit.takes_in`).
    """
    moved = _durable.guarded(reading.state, (), reading.rests_on).moved(latest.state_data)
    if refused.holds or moved or not abandons_on_refusal(pending, anchored=reading.anchored is not None):
        held = _verification_comments.records_the_artifact(reading.gh, reading.issue, reading.state, comment_id)
        return held or refused.holds
    guard = _durable.guarded(latest, ABANDONS_RECORDING, reading.rests_on)
    _comments._track_orchestrator_comment(latest, comment_id)
    abandons(latest, pending)
    outcome = _commit.commit(
        reading.gh, reading.issue, guard, latest.state_data, _verification_comments.MERGED_LEDGER,
    )
    abandoned = _durable.refusal_of(outcome)
    if abandoned is None:
        reading.state.state_data = outcome.reading.state_data
        _commit.takes_in(reading.state, outcome.reading.state_data)
        return False
    log.info(
        "issue=#%d is not abandoning the refused carry of verification evidence "
        "revision %d: %s; leaving it owed", reading.issue.number, pending.revision,
        abandoned.refusal,
    )
    if abandoned.holds:
        return True
    return _verification_comments.records_the_artifact(reading.gh, reading.issue, reading.state, comment_id)


def _label_of(fresh: Issue) -> WorkflowLabel | None:
    """The workflow label `fresh` carries, which the settlement is recorded under, or None where it will not read.

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
