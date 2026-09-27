# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether current evidence may be carried to another head, and for which review of it.

A rewrite -- a squash, a one-commit subject rewrite, a documentation pass that
changed nothing -- leaves a new head behind evidence recorded for the old one.
That evidence may answer for the new head only when two things are PROVED:
the new head's full tree is the very tree the commands ran on, read from this
repository, and the verification context configured now is the one they ran
under. Nothing else can substitute for either. A matching patch id, an
unchanged contribution fingerprint or topic diff, or a rewrite that calls
itself a rebase says nothing about what the base contributes, and a rebase
onto another base changes the tree whatever its patches say.

More has to hold before those proofs license anything. The new head has to BE
new: the head the evidence already answers for is no carry, and publishing the
same binding again would put the same run on the thread under a new revision.
The evidence being carried has to still be what the pull request carries: the
latest this issue recorded, its handoff describing it, and its artifact,
re-read at the comment it settled at, still exactly that artifact
(`verification_current`) -- a transcript a newer artifact superseded, or whose
artifact was deleted or edited away, is evidence nobody can be shown, and
carrying it would publish it again under a new receipt. That artifact is read
off the pull request proved open and standing on the new head. And the new head
has to have a review subject of its own: the applicable record
(`verification_subject.applicable_subject`) naming that very head, since the
validating reader builds its subject from the head the pull request stands on,
and evidence answering for a review of the old head answers for a subject no
reviewer can be handed any more. Until a report about the new head settles and
a reviewer is handed it, nothing is carried.

The decision licenses exactly one thing: recording a new transaction whose
binding is the current one answering for the new head and its subject
(`CarryForward.binding`). The tested commit and tree stay the ones that were
actually tested, so the artifact that transaction publishes names the earlier
commit as the one that ran and the new head as the equivalent-tree target.
Everything else -- the report that subject names, re-read and not stale, the
requirements, the pull request still standing there -- is proved by the
reconciliation before that transaction is published or becomes current,
exactly as for fresh evidence.

Anything short of all of it is no decision, and says why in the log.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_publication_evidence as _publication,
    review_subjects as _review_subjects,
    verification_current as _current,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
    verification_world as _world,
)
from orchestrator.workflow.late_split import formats as _formats

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class CarryForward:
    """Current evidence proved to answer for `target_head` as well.

    `target_tree` is the tree read for that head, equal to the tested tree.
    `subject` is the review subject recorded about that head, exactly as its
    record spells it.
    """

    source: _records.CurrentEvidence
    target_head: str
    target_tree: str
    subject: dict[str, Any]

    @property
    def binding(self) -> _records.EvidenceBinding:
        """The current run answering for the new head and its review, its tested run unchanged."""
        carried = self.source.binding.retargeted(self.target_head)
        publication = replace(
            carried.target.publication,
            requirements_revision=_review_subjects.ReviewSubject.requirements_recorded_in(self.subject),
        )
        return replace(carried, target=_records.EvidenceTarget(publication, self.subject))


def carry_forward_decision(
    reading: _proof.ProofReading, target_head: str,
) -> CarryForward | None:
    """The carry-forward the current evidence earns onto `target_head`, or None.

    The pinned questions first, then the trees, then the pull request and the
    artifact, each of which is a request. The source's own tree is read again
    too, so a record whose tested commit no longer reads as the tree it claims
    carries nothing anywhere.
    """
    current = _settlement.read_current_evidence(reading.state)
    refusal = _refusal(reading, current, target_head)
    if not refusal:
        refusal = _tree_refusal(reading, current, target_head) or _publication_refusal(
            reading, current, target_head,
        )
    if refusal:
        log.info(
            "issue=#%d carries no verification evidence to %s: %s",
            reading.issue.number, target_head, refusal,
        )
        return None
    return CarryForward(
        source=current,
        target_head=target_head,
        target_tree=current.binding.tested_tree,
        subject=_subject.applicable_subject(reading.state, current.binding.source)[1],
    )


def _refusal(
    reading: _proof.ProofReading,
    current: _records.CurrentEvidence | None,
    target_head: str,
) -> str:
    """What stops a decision before any object is read, or "" for nothing."""
    if current is None:
        return "there is no current evidence to carry"
    if current.binding.context_revision != _proof.configured_context_revision():
        return "the verification context moved since the evidence was recorded"
    refusal = _head_refusal(current, target_head)
    if refusal:
        return refusal
    applicable, subject = _subject.applicable_subject(reading.state, current.binding.source)
    if not _reviews_the_head(subject, current, target_head):
        return f"no {applicable} about the target head and its report is recorded"
    return ""


def _head_refusal(current: _records.CurrentEvidence, target_head: str) -> str:
    """What makes `target_head` nowhere to carry `current` to, or "".

    The head the evidence already answers for is no carry at all: the binding
    would be the one already current, and publishing it again would put the
    same run on the thread under a new revision.
    """
    if not _formats.is_hex_of(target_head, _formats.COMMIT_LENGTHS):
        return "the target head is not a whole commit id"
    if target_head == current.binding.target.target_head:
        return "the evidence already answers for the target head"
    return ""


def _reviews_the_head(
    subject: object, current: _records.CurrentEvidence, target_head: str,
) -> bool:
    """Whether a recorded subject reviews `target_head` on the source's pull request, report named.

    A carried binding holds it whole, so it has to read as one the evidence
    records accept: the same pull request, a developer report named, and a
    requirements revision.
    """
    reads = _review_subjects.ReviewSubject
    identity = reads.identity_recorded_in(subject)
    if identity is None or None in identity or not reads.requirements_recorded_in(subject):
        return False
    pr_number = current.binding.target.publication.pr_number
    return identity[0] == pr_number and reads.commit_recorded_in(subject) == target_head


def _tree_refusal(
    reading: _proof.ProofReading,
    current: _records.CurrentEvidence,
    target_head: str,
) -> str:
    """What the checkout says against carrying `current` onto `target_head`, or ""."""
    worktree = _worktree_paths._worktree_path(reading.spec, reading.issue.number)
    if not worktree.exists():
        return "the checkout is not on this host"
    tested = current.binding.tested_tree
    trees = (
        _world.tree_of(worktree, current.binding.tested_sha),
        _world.tree_of(worktree, target_head),
    )
    if trees != (tested, tested):
        return "the target head's tree is not proved to be the tested tree"
    return ""


def _publication_refusal(
    reading: _proof.ProofReading,
    current: _records.CurrentEvidence,
    target_head: str,
) -> str:
    """What the pull request says against carrying `current`, or "".

    The pull request has to be open and standing on the new head, and the
    source's handoff and artifact, re-read on it, still the ones that settled.
    """
    found = _publication.subject_verdict(
        reading.gh, current.binding.retargeted(target_head).target.publication,
    )
    if not found.proved:
        return found.refusal
    unpublished = _current.publication_verdict(
        reading.gh, reading.state, current, found.pull_request,
    )
    return "" if unpublished is None else unpublished.refusal
