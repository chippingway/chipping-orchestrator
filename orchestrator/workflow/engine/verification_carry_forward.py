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
off the pull request proved open and standing on the new head, and the
transcript it carries is the one carried (`CarryForward.commands`).

And the carried evidence has to answer for a review that still stands, which
it does in one of two ways. Either the new head has a review subject of its
own: the applicable record (`verification_subject.applicable_subject`) naming
that very head, since the validating reader builds its subject from the head
the pull request stands on. Or the review the evidence already answers for is
UNCHANGED and is the one an approval was given over: the applicable record
still names exactly the subject the evidence is bound to, about the commit
that was tested, and the approval record (`review_approved_subject`) names it
too. That is the approval squash's case (`stages/validating/squash_evidence.py`):
the rewrite of an approved head that the approval's own handoff publishes,
past which no reviewer is handed the new head at all and every road that acts
on the approval holds it to that subject. The squash asks for that way alone
(`approved`): a review recorded about the new head since is a later round --
its report and requirements among what moved -- that the approval never
covered, and its carry is refused rather than answering for it. Evidence about a review of the old
head that no approval was given over answers for a subject nobody can hand a
reviewer any more, and is not carried: until a report about the new head
settles and a reviewer is handed it, nothing is.

A local verify run is carried the same way (`local_run_decision`): the run
the approval's gate made on the head the reviewer approved, bound there as
orchestrator-executed evidence (`verification_local_runs`), proved over the
same context, head, approved review, trees, and pull request -- everything
but an artifact, which a run never published has none of to re-read.

The dormant evidence policy of a landed automatic base rewrite
(`rewrite_evidence`) asks the generic decision and takes only its first way:
a review recorded about the rewritten head. An approval of the head the
rebase replaced is never carried across it, since the rewritten head's report
refresh is what a reviewer of it is handed.

The decision licenses exactly one thing: recording a new transaction whose
binding is the current one answering for the new head and the review it
carries (`CarryForward.binding`). The tested commit and tree stay the ones that
were actually tested, so the artifact that transaction publishes names the
earlier commit as the one that ran and the new head as the equivalent-tree
target. Everything else -- the report that subject names, re-read and not
stale, the requirements, the pull request still standing there -- is proved by
the reconciliation before that transaction is published or becomes current,
exactly as for fresh evidence. So is the artifact a carry of current evidence
copied its transcript from: the transaction names it (`copied_from`), and
until it settles that evidence has to still be current and its artifact still
carry exactly what was copied (`verification_current.copied_source_verdict`),
or the copy is refused -- a publication retried over a lost response
included.

Anything short of all of it is no decision, and says why in the log. What
comes back in its place is the refusal as the proof's own verdicts spell one
(`report_evidence_models`): a pull request or an artifact nobody could read
HOLDS, since the same question asked again may well be answered, and every
other refusal -- an unreadable tree among them -- DEFERS, or ENDS where the
pull request is over.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github import verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
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
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.late_split import formats as _formats

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class CarryForward:
    """A run proved to answer for `target_head` as well.

    `source` is the binding the run is bound to where it ran: the current
    evidence's, or a local verify run's bound to the head it tested.
    `target_tree` is the tree read for `target_head`, equal to the tested tree.
    `subject` is the review subject the carried evidence answers for, exactly
    as its record spells it: a review recorded about that head, or the
    approved review the source already answers for, unchanged. `commands` is
    the run's own transcript -- for current evidence, the one its artifact
    carries, read off the very reading that proved it is still the artifact
    that settled, and `copied_from` that evidence's receipt, which the
    transaction recorded for this carry names until it settles; None for a
    local run, which has no artifact to copy.
    """

    source: _records.EvidenceBinding
    target_head: str
    target_tree: str
    subject: dict[str, Any]
    commands: tuple[_evidence.VerifiedCommand, ...]
    copied_from: str | None = None

    @property
    def binding(self) -> _records.EvidenceBinding:
        """The run answering for the new head and its review, its tested run unchanged."""
        carried = self.source.retargeted(self.target_head)
        publication = replace(
            carried.target.publication,
            requirements_revision=_review_subjects.ReviewSubject.requirements_recorded_in(self.subject),
        )
        return replace(carried, target=_records.EvidenceTarget(publication, self.subject))


def carry_forward_decision(
    reading: _proof.ProofReading, target_head: str, *, approved: bool = False,
) -> CarryForward | ReportEvidence:
    """The carry-forward the current evidence earns onto `target_head`, or the verdict refusing it.

    The pinned questions first, then the trees, then the pull request and the
    artifact, each of which is a request. The source's own tree is read again
    too, so a record whose tested commit no longer reads as the tree it claims
    carries nothing anywhere. `approved` holds the carry to the approved
    review alone, unchanged (`_carried_subject`).
    """
    current = _settlement.read_current_evidence(reading.state)
    found = (
        ReportEvidence(ReportEvidenceVerdict.DEFER, "there is no current evidence to carry")
        if current is None else _proved(reading, current.binding, target_head, approved)
    )
    artifact = None
    if found.proved:
        unpublished, artifact = _current.settled_artifact(
            reading.gh, reading.state, current, found.pull_request,
        )
        found = unpublished or found
    if not found.proved:
        log.info(
            "issue=#%d carries no verification evidence to %s: %s",
            reading.issue.number, target_head, found.refusal,
        )
        return found
    return CarryForward(
        source=current.binding,
        target_head=target_head,
        target_tree=current.binding.tested_tree,
        subject=_carried_subject(reading.state, current.binding, target_head, approved),
        commands=artifact.commands,
        copied_from=current.receipt,
    )


def local_run_decision(
    reading: _proof.ProofReading,
    binding: _records.EvidenceBinding,
    commands: tuple[_evidence.VerifiedCommand, ...],
    target_head: str,
) -> CarryForward | ReportEvidence:
    """The carry-forward a local verify run earns onto `target_head`, or the verdict refusing it.

    `binding` and `commands` are what the run is evidence of on the head it
    tested (`verification_local_runs.local_run_evidence`). The same proofs as
    for current evidence -- context, a new whole head, the review it answers
    for, both trees, and the pull request standing on that head -- save the
    artifact, which a run never published has none of. The run is the one an
    approval's gate made, so it answers for the approved review alone,
    unchanged.
    """
    found = _proved(reading, binding, target_head, approved=True)
    if not found.proved:
        log.info(
            "issue=#%d carries no local verification run to %s: %s",
            reading.issue.number, target_head, found.refusal,
        )
        return found
    return CarryForward(
        source=binding,
        target_head=target_head,
        target_tree=binding.tested_tree,
        subject=_carried_subject(reading.state, binding, target_head, approved=True),
        commands=commands,
    )


def _proved(
    reading: _proof.ProofReading, binding: _records.EvidenceBinding, target_head: str, approved: bool,
) -> ReportEvidence:
    """Everything a carry of `binding` onto `target_head` proves short of an artifact: PROVED with the pull request.

    The pinned questions first, then the trees, then the pull request, which
    has to be open and standing on the new head.
    """
    refusal = _refusal(reading, binding, target_head, approved) or _tree_refusal(reading, binding, target_head)
    if refusal:
        return ReportEvidence(ReportEvidenceVerdict.DEFER, refusal)
    return _publication.subject_verdict(reading.gh, binding.retargeted(target_head).target.publication)


def _refusal(
    reading: _proof.ProofReading, binding: _records.EvidenceBinding, target_head: str, approved: bool,
) -> str:
    """What stops a decision before any object is read, or "" for nothing.

    The head the evidence already answers for is no carry at all: the binding
    would be the one already current, and publishing it again would put the
    same run on the thread under a new revision.
    """
    if binding.context_revision != _proof.configured_context_revision():
        return "the verification context moved since the evidence was recorded"
    if not _formats.is_hex_of(target_head, _formats.COMMIT_LENGTHS):
        return "the target head is not a whole commit id"
    if target_head == binding.target.target_head:
        return "the evidence already answers for the target head"
    if _carried_subject(reading.state, binding, target_head, approved) is None:
        applicable = _subject.applicable_subject(reading.state, binding.source)[0]
        later = "" if approved else f"no {applicable} about the target head and its report is recorded, and "
        return f"{later}the review the evidence answers for is not the approved {applicable}, unchanged"
    return ""


def _carried_subject(
    state: PinnedState, binding: _records.EvidenceBinding, target_head: str, approved: bool,
) -> dict[str, Any] | None:
    """The review subject a carry of `binding` onto `target_head` answers for, or None.

    The applicable record, which a carried binding holds whole, so it has to
    read as one the evidence records accept: the source's pull request, a
    developer report named, and a requirements revision. And it has to be a
    review of `target_head` -- or the review `binding` already answers for,
    unchanged, about the commit that was tested, and the one the recorded
    approval covers. An `approved` carry -- the approval squash's -- takes
    only that second: a review recorded about the new head since is a later
    round the approval never covered, and the subject, its report revision and
    digest, and its requirements are exactly the ones the approval was given.
    """
    recorded = _subject.applicable_subject(state, binding.source)[1]
    pr_number = binding.target.publication.pr_number
    identity = _review_subjects.ReviewSubject.identity_recorded_in(recorded) or (None,)
    if None in identity or identity[0] != pr_number:
        return None
    reviewed = _review_subjects.ReviewSubject.commit_recorded_in(recorded)
    unchanged = recorded == binding.target.subject == state.get(_review_subjects.APPROVED_SUBJECT)
    if not (unchanged and reviewed == binding.tested_sha) and (approved or reviewed != target_head):
        return None
    return recorded if _review_subjects.ReviewSubject.requirements_recorded_in(recorded) else None


def _tree_refusal(
    reading: _proof.ProofReading, binding: _records.EvidenceBinding, target_head: str,
) -> str:
    """What the checkout says against carrying `binding` onto `target_head`, or ""."""
    worktree = _worktree_paths._worktree_path(reading.spec, reading.issue.number)
    if not worktree.exists():
        return "the checkout is not on this host"
    tested = binding.tested_tree
    trees = (
        _world.tree_of(worktree, binding.tested_sha),
        _world.tree_of(worktree, target_head),
    )
    if trees != (tested, tested):
        return "the target head's tree is not proved to be the tested tree"
    return ""
