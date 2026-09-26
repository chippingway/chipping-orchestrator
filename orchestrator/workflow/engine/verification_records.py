# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one workflow verification-evidence transaction is recorded as.

Evidence is a run's commands and results bound to everything that says what
they are evidence ABOUT. The run is bound at the moment it is recorded,
because every member of that binding is something a later tick could read for
itself and get a different answer from: the pull request, the branch and the
head it stands on, the requirements the issue carries, the developer report
and the review subject that report settled into, the commit and full tree the
commands ran on, and the verification context they ran under. Frozen here, a
moved head, an edited issue, a new report, or a changed `VERIFY_COMMANDS` is a
disagreement the reconciliation can see rather than a publication it makes
anyway.

Four records rather than one, mirroring the developer report's, because they
answer different questions and live for different lengths of time. PENDING is
the transaction: the run and its binding, written before any artifact is
posted and dropped by the write that settles it. CURRENT is the evidence the
pull request carries now, and nothing but a proved settlement may write it.
HISTORY is every earlier record in the order it was retired -- superseded by a
later settlement, invalidated by a reader that proved the world moved past it,
or abandoned before it ever settled -- so older evidence is kept as history
rather than relabelled as a run on something newer. HANDOFF is the receipt
that one transaction finished, and it is what turns a replay into a no-op.

The binding EXTENDS the report records rather than forking them. What the
evidence is written for is the report domain's own `ReportSubject`: the
repository, the pull request, the branch, the head the evidence is written
for, and the requirements revision -- read and proved by the same owners a
report transaction is. The review subject is the validating stage's own
recorded object (`review_subjects`), carried exactly as it is written there,
so the report revision and digest it names are the ones the approval readers
compare. What the run adds is the tested commit and tree, the context
revision, and who witnessed it.

Every record is additive. An issue carrying none of these keys has no pending
transaction, no current evidence, no history, and no handoff, which is what
every issue that predates them says without a migration having reached it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from orchestrator.github import developer_reports as _reports, verification_evidence as _evidence
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.workflow.engine import report_records as _report_records, review_subjects as _review_subjects
from orchestrator.workflow.state import WorkflowLabel

# The transaction this issue has outstanding, `null` once it has settled.
PENDING_EVIDENCE = "verification_evidence_pending"

# The evidence the pull request carries now, `null` once it was invalidated.
CURRENT_EVIDENCE = "verification_evidence_current"

# Every earlier record, oldest first, bounded by `verification_settlement_state`.
EVIDENCE_HISTORY = "verification_evidence_history"

# The receipt that one transaction finished.
EVIDENCE_HANDOFF = "verification_evidence_handoff"


class Retirement(StrEnum):
    """Why a record left the place it held and became history.

    SUPERSEDED is current evidence a later settlement replaced. INVALIDATED is
    current evidence a reader proved the world has moved past -- a head, a
    tree, a context, requirements, or a report -- with nothing yet to replace
    it. ABANDONED is a transaction that never settled: replaced by a later one,
    left behind by a pull request that ended, or older than evidence that
    already settled. An abandoned transaction may still have posted its
    artifact, which stays on the pull request as history too.
    """

    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class EvidenceTarget:
    """What one piece of evidence answers for.

    `publication` names the repository, the pull request, the branch, the head
    the evidence is written for, and the requirements revision, in the report
    domain's own shape, so both transactions are proved against a pull request
    by the same readers. Its `source_sha` is that head -- the commit the pull
    request has to be STANDING on for the evidence to be current, which is not
    necessarily the one the commands ran on.

    `subject` is the review subject exactly as `review_subjects` records it:
    the pull request, a head, a requirements revision, and the developer
    report's revision and digest. It is never mutated.
    """

    publication: _report_records.ReportSubject
    subject: dict[str, Any]

    @property
    def target_head(self) -> str:
        """The head the pull request has to stand on for this evidence to be current."""
        return self.publication.source_sha

    @property
    def subject_commit(self) -> str | None:
        """The head the review subject names, or None where the subject will not read."""
        return _review_subjects.ReviewSubject.commit_recorded_in(self.subject)

    @property
    def subject_identity(self) -> tuple | None:
        """The pull request and report revision the subject names, or None."""
        return _review_subjects.ReviewSubject.identity_recorded_in(self.subject)

    @property
    def subject_requirements(self) -> str | None:
        """The requirements revision the subject names, or None."""
        return _review_subjects.ReviewSubject.requirements_recorded_in(self.subject)


@dataclass(frozen=True)
class EvidenceBinding:
    """A run bound to what it is evidence about and who witnessed it.

    `tested_sha` and `tested_tree` are the commit the commands ran on and its
    full tree identity. They equal the target head and its tree for a fresh
    run; for evidence carried forward they stay the commit that was actually
    tested, and only the target moves -- a run is never relabelled as one on a
    commit it did not run on. `context_revision` is the verification context
    the commands ran under (`verification_proof.configured_context_revision`).
    """

    target: EvidenceTarget
    source: _evidence.EvidenceSource
    tested_sha: str
    tested_tree: str
    context_revision: str

    def retargeted(self, target_head: str) -> EvidenceBinding:
        """This binding answering for another head, the tested run unchanged."""
        publication = replace(self.target.publication, source_sha=target_head)
        return replace(self, target=replace(self.target, publication=publication))


@dataclass(frozen=True)
class PendingEvidence:
    """One transaction, recorded before its artifact is posted.

    `receipt` names the transaction: a retry carries it and finds whatever an
    earlier attempt landed, including a post whose response was lost.
    `revision` orders artifacts on one pull request. `commands` are the run's
    own transcript, in the order the commands ran, and nothing is counted or
    inferred from them beyond whether every one of them exited 0.
    """

    receipt: str
    revision: int
    binding: EvidenceBinding
    commands: tuple[_evidence.VerifiedCommand, ...]

    @property
    def passed(self) -> bool:
        """Whether at least one command ran and every one that ran exited 0."""
        return bool(self.commands) and all(
            ran.exit_status == 0 for ran in self.commands
        )

    @property
    def content_revision(self) -> str:
        """The digest the published artifact names its evidence by."""
        return _reports.content_digest(_evidence.render_commands(self.commands))

    @property
    def artifact(self) -> VerificationArtifact:
        """The artifact this transaction publishes; `ArtifactRefusedError` if none."""
        binding = self.binding
        publication = binding.target.publication
        return VerificationArtifact(
            repository=publication.repo_slug,
            pr_number=publication.pr_number,
            source=binding.source,
            tested_sha=binding.tested_sha,
            tested_tree=binding.tested_tree,
            target_head=publication.source_sha,
            review_subject=binding.target.subject_commit or "",
            requirements_revision=publication.requirements_revision,
            context_revision=binding.context_revision,
            artifact_revision=self.revision,
            receipt=self.receipt,
            commands=self.commands,
        )


@dataclass(frozen=True)
class CurrentEvidence:
    """The evidence the pull request carries now.

    Carries no commands: the artifact on the pull request holds them, at
    `comment_id`, under `content_revision` -- which is also the revision a
    reviewer names when it reuses this evidence rather than running anything.
    """

    receipt: str
    revision: int
    binding: EvidenceBinding
    content_revision: str
    comment_id: int
    passed: bool


@dataclass(frozen=True)
class HistoricalEvidence:
    """One earlier record, kept as what it was and why it stopped being it.

    `comment_id` is None for a transaction abandoned before any post was
    confirmed; its artifact may still be on the pull request under `receipt`.
    """

    receipt: str
    revision: int
    tested_sha: str
    tested_tree: str
    target_head: str
    context_revision: str
    content_revision: str
    passed: bool
    retired: Retirement
    comment_id: int | None = None

    @classmethod
    def of(
        cls, record: PendingEvidence | CurrentEvidence, retired: Retirement,
    ) -> HistoricalEvidence:
        """The history entry one pending or current record leaves when retired."""
        binding = record.binding
        return cls(
            receipt=record.receipt,
            revision=record.revision,
            tested_sha=binding.tested_sha,
            tested_tree=binding.tested_tree,
            target_head=binding.target.target_head,
            context_revision=binding.context_revision,
            content_revision=record.content_revision,
            passed=record.passed,
            retired=retired,
            comment_id=getattr(record, "comment_id", None),
        )


@dataclass(frozen=True)
class EvidenceHandoff:
    """The receipt one finished transaction leaves behind.

    `settled_under` is the workflow label the issue carried as the settlement
    landed, read off the issue afresh; None where it could not be read.
    """

    receipt: str
    pr_number: int
    revision: int
    target_head: str
    settled_under: WorkflowLabel | None = None
