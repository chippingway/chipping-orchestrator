# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the current evidence record is still the evidence the pull request carries.

The record says what a settlement put on the pull request once; only a fresh
reading of the exact comment it recorded says the pull request still carries
it. So a reader about to rely on current evidence -- a reviewer handed it, a
readiness decision, a carry-forward -- asks three things beside the world the
evidence is about.

The record has to be the LATEST evidence this issue recorded: no revision past
it spent. Every record raises the revision floor in its own write
(`verification_record_state`), so a newer transaction is seen here whether or
not its artifact was posted, and whether it is still owed or was since dropped
or abandoned. An artifact on the thread supersedes every lower revision, so a
newer one posted and never settled -- a crash between the post and the
settlement, or a settlement standing down -- is what the pull request shows as
the latest result, whatever the record says; and where nobody can say what was
spent, nobody can say the record is the latest.

The HANDOFF has to describe the current record: the same receipt, pull
request, revision, and head. A settlement writes the two in one write, so a
current record the handoff does not describe is one of them replaced by
something other than a settlement, and neither says which evidence is the
latest.

The ARTIFACT has to be there: the comment the settlement recorded, read again
off the pull request's thread, has to be ours and re-render byte for byte as
an artifact, and that artifact has to be the one the record describes -- the
receipt and revision, every member of the binding the artifact encodes (the
repository, pull request, witness, tested commit and tree, target head, review
subject's head, and requirements and context revisions; not the branch or the
report revision and digest, which the proof holds instead), the digest of the
evidence it carries, and whether every command it carries exited 0, which is
what the record's pass flag claims. A comment deleted, edited out of shape, or
standing there as some other artifact is evidence nobody can be shown.

Every refusal DEFERS, since what answers it is newer evidence settling or
fresh evidence rather than a retry; a thread nobody could read HOLDS.

A carry of current evidence copies its artifact's transcript, and is owed
until it settles over that very record. So the reconciliation asks of the
SOURCE too, ahead of the carry's post and again ahead of its settlement
(`copied_source_verdict`): the record it copied still current, and its
artifact still the one that settled, carrying exactly what was copied. A
source edited or deleted while the carry was owed -- across a publication
retried over a lost response included -- refuses the carry rather than
letting its copy outlive what the pull request shows.

Evidence carried onto a head it did not run on answers for its review only
while that review stands (`carry_answers`), which the pinned comment alone
says: the approval squash's carry is bound to the approved review, so a
review returned since, or the record removed or replaced by hand, leaves it
answering for nothing.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
)


def publication_verdict(
    gh: GitHubClient,
    state: PinnedState,
    current: _records.CurrentEvidence,
    pull_request: Any,
) -> _evidence_models.ReportEvidence | None:
    """Refuse current evidence that is not the latest, or its handoff or artifact no longer vouches for, or None.

    `pull_request` is the one the caller proved open and standing on the head
    it is asking about, so the thread read is that pull request's.
    """
    return settled_artifact(gh, state, current, pull_request)[0]


def settled_artifact(
    gh: GitHubClient,
    state: PinnedState,
    current: _records.CurrentEvidence,
    pull_request: Any,
) -> tuple[_evidence_models.ReportEvidence | None, Any]:
    """`publication_verdict`'s answer, and the artifact it re-read where that answer is None.

    For a carry-forward, which publishes the transcript the settled artifact
    carries again: taken from the very reading that proved the artifact is
    still the one that settled, rather than from a second one that could
    find it edited.
    """
    if _outranked(state, current):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "verification evidence newer than the current record is recorded",
        ), None
    if not _handoff_describes(state, current):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the evidence handoff does not describe the current evidence",
        ), None
    presence, found = gh.reread_verification_artifact(pull_request, current.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the current evidence's artifact could not be re-read",
        ), None
    if presence is not ReportPresence.PRESENT or not _is_the_settled_artifact(found, current):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the current evidence's artifact is gone or no longer the one that settled",
        ), None
    return None, found


def copied_source_verdict(
    gh: GitHubClient,
    state: PinnedState,
    pending: _records.PendingEvidence,
    pull_request: Any,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a carry whose copied source no longer says what it copied, or None.

    None for a transaction that copied nothing. Otherwise the evidence it
    names has to still be the current record, and that record's artifact,
    re-read on the proved `pull_request`, has to still be the one that
    settled and carry exactly the commands the carry copied. Not asked
    whether it is the latest: the carry outranks it from the moment it is
    recorded.
    """
    if pending.copied_from is None:
        return None
    current = _settlement.read_current_evidence(state)
    if current is None or current.receipt != pending.copied_from:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the evidence the carry copied is no longer the current evidence",
        )
    presence, found = gh.reread_verification_artifact(pull_request, current.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the artifact the carry copied could not be re-read",
        )
    if presence is ReportPresence.PRESENT and _is_the_settled_artifact(found, current) and (
        found.commands == pending.commands
    ):
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the artifact the carry copied is gone or no longer carries what it copied",
    )


def carry_answers(state: PinnedState) -> bool:
    """Whether current evidence carried onto a head it did not run on still answers for the review it was carried for.

    True where nothing current is carried. A carry answers for its head only
    on the approval's word -- the approved review, about the commit that was
    tested -- so the review subject it is bound to has to stand as the
    evidence records accept one (`verification_subject.subject_verdict`): the
    pull request this issue records, no developer report owed, and the
    applicable record still that very review. Read off the pinned comment
    alone, so every reader about to move an approval on can ask it first.
    """
    current = _settlement.read_current_evidence(state)
    if current is None or current.binding.tested_sha == current.binding.target.target_head:
        return True
    return _subject.subject_verdict(state, current.binding) is None


def _outranked(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Whether this issue spent a revision past the current record's, or nobody can say."""
    latest = _record_state._latest_revision(state)
    return latest is None or latest > current.revision


def _handoff_describes(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Whether the recorded handoff is the one the current record's settlement wrote."""
    handoff = _settlement.read_evidence_handoff(state)
    return handoff is not None and (
        handoff.receipt,
        handoff.pr_number,
        handoff.revision,
        handoff.target_head,
    ) == (
        current.receipt,
        current.binding.target.publication.pr_number,
        current.revision,
        current.binding.target.target_head,
    )


def _is_the_settled_artifact(found: Any, current: _records.CurrentEvidence) -> bool:
    """Whether an artifact re-read is exactly the one `current` records.

    The record keeps no commands, so the transaction it settled from is rebuilt
    with the commands the artifact carries and held to all of it: that
    transaction's artifact has to BE the one found -- identity and commands --
    and its evidence digest and its pass flag have to be the ones recorded. A
    pinned `passed` saying true over an artifact carrying a failed command is
    a record that no longer describes what the pull request shows.
    """
    settled_from = _records.PendingEvidence(
        receipt=current.receipt,
        revision=current.revision,
        binding=current.binding,
        commands=found.commands,
    )
    return (
        settled_from.artifact == found
        and settled_from.content_revision == current.content_revision
        and settled_from.passed == current.passed
    )
