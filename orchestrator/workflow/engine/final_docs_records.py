# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a final-documentation completion records about the head it completed on, apart from the approval it followed.

An approval is of one review subject: the pull request, the commit the
reviewer was handed, the requirements, and the developer report. The final
docs pass behind it may leave the pull request on another head -- the
approval's own squash moves it before the pass is entered, and a docs commit
moves it again -- and nothing about that pass may be written into the records
of the review it followed: the approved subject, the evidence claim it rests
on, and the settled report with its source commit stay exactly as the
approval and its squash left them, so no record says the reviewer was handed
the docs commit or the report was written about it.

So the pass is recorded beside them, in one record of its own
(`docs_final_provenance`), naming five things:

- `approved` -- the approved review subject, spelled exactly as
  `review_approved_subject` spells it. Its report revision and digest are the
  implementation report the approval covers, and its head the commit that
  report and review are about.
- `entry_head` -- the head the pull request stood on as the pass was entered:
  that approved commit, or the commit the approval's squash published over it,
  which only that squash's own carry can link to it (`report_squash_lineage`).
- `final_head` -- the head the pass completed on: the entry head where it
  published nothing, its docs commit where it published one.
- `verification` -- how that final head is verified, one of three:
  RETAINED, the entry head unchanged and verified by the evidence the
  approval rests on, kept exactly as it settled with its own provenance --
  a squash's carry still naming the approved commit as the one tested;
  EXECUTED, a changed head verified by a run of the configured
  `VERIFY_COMMANDS` on exactly that head, which this orchestrator executed
  and bound as evidence of its own (`stages/documenting/final_verification.py`);
  and UNCONFIGURED, a changed head under an empty `VERIFY_COMMANDS`, which
  requires no check, ran none, and is no evidence that any passed.
- `evidence` -- the transaction that verification rests on, by its receipt
  and revision: the approval's own evidence for RETAINED, the run's for
  EXECUTED, and `null` for UNCONFIGURED, which rests on none.

The record is read whole or not at all (`FinalDocs.read`): exactly those
members; an approved subject that reads as a recorded one on a pull request
with a report; both heads whole commit ids, equal exactly where the
verification is RETAINED; a verification this build names; and evidence
spelled as a transaction's receipt for its own revision wherever the
verification rests on one, and `null` where it does not. Anything else is a
truncation or a hand edit, and read as a completion it would stand behind a
head nobody can say was documented or verified.

Every docs pass that finishes records one, in the completion that hands the
issue straight to `in_review` (`stages/documenting/final_completion.py`), and
the documenting stage reads it back to finish a relabel that completion's
write landed ahead of (`stages/documenting/owed_completion.py`); the base
refresh holds the branch still while the transaction it names is still owed
(`git/base_sync/frozen.py`), which spells the record's keys itself.
Reading it proves nothing beyond its own shape: whether the head, the
approval, the report, the lineage, and the evidence it names are still what
it says is the final-documentation proof's (`final_docs_proof`). The in_review
ready ping reads it to qualify the head it names and to take that proof in
place of the ordinary readiness proof, and decides its own writes on it
(`stages/in_review/completion.py`, `ready_ping`). The other reader is the
evidence proof's review-subject rule
(`verification_subject`), which holds evidence to a subject about the head it
answers for: an EXECUTED record is what licenses an orchestrator-executed run
of its final head, bound to exactly what such a run answers for
(`FinalDocs.final_target`), to answer for the approved subject instead
(`answers_for`), on the pinned comment alone and nowhere else -- so the dispatcher's existing
reconciliation publishes and settles that run, and the guarded writes it
makes are decided on this record as on every other bound record
(`verification_durable`). The record is additive: an issue carrying none has
no final-documentation completion.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    report_settlement_state as _report_settlement,
    verification_records as _records,
)
from orchestrator.workflow.engine.review_subjects import APPROVED_SUBJECT, ReviewSubject
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The final-documentation completion this issue recorded, absent for none.
FINAL_DOCS = "docs_final_provenance"

_APPROVED = "approved"

_ENTRY_HEAD = "entry_head"

_FINAL_HEAD = "final_head"

_VERIFICATION = "verification"

_EVIDENCE = "evidence"

_RECEIPT = "receipt"

_REVISION = "revision"

_MEMBERS = frozenset((_APPROVED, _ENTRY_HEAD, _FINAL_HEAD, _VERIFICATION, _EVIDENCE))

# The pull request this issue records as its own.
_PR_NUMBER = "pr_number"

_EVIDENCE_MEMBERS = frozenset((_RECEIPT, _REVISION))


class FinalVerification(StrEnum):
    """How the head a final docs pass completed on is verified."""

    RETAINED = "retained"
    EXECUTED = "executed"
    UNCONFIGURED = "unconfigured"


# Every verification spelled as the record writes it, as a tuple so a value
# nothing hashes -- a hand edit's list or object -- is compared rather than hashed.
_VERIFICATIONS = tuple(member.value for member in FinalVerification)


@dataclass(frozen=True)
class FinalEvidence:
    """The transaction a final head's verification rests on, by its receipt and revision."""

    receipt: str
    revision: int

    @classmethod
    def read(cls, recorded: object) -> FinalEvidence | None:
        """The transaction `recorded` names, or None unless it is spelled as its revision's receipt."""
        if not isinstance(recorded, dict) or set(recorded) != _EVIDENCE_MEMBERS:
            return None
        receipt = recorded[_RECEIPT]
        revision = _record_values.as_recorded_number(recorded[_REVISION])
        if not isinstance(receipt, str) or revision is None:
            return None
        if not _records.PendingEvidence.receipt_names(receipt, revision):
            return None
        return cls(receipt=receipt, revision=revision)

    def names(self, record: _records.CurrentEvidence | _records.HistoricalEvidence | None) -> bool:
        """Whether `record` is this transaction: the same receipt and revision."""
        if record is None:
            return False
        return (record.receipt, record.revision) == (self.receipt, self.revision)


@dataclass(frozen=True)
class FinalDocs:
    """One final-documentation completion, every member read as its writer spells it."""

    approved: dict
    entry_head: str
    final_head: str
    verification: FinalVerification
    evidence: FinalEvidence | None = None

    @property
    def approved_commit(self) -> str | None:
        """The commit the approved subject is about, or None where it will not read."""
        return ReviewSubject.commit_recorded_in(self.approved)

    def follows(self, state: PinnedState) -> bool:
        """Whether `state` still records the approval this completion followed, on the pull request it pins.

        The approval `state` records is read whole first (`_approval_in`).
        """
        if self.approved != _approval_in(state):
            return False
        pinned = _payloads.as_identity(state.get(_PR_NUMBER))
        identity = ReviewSubject.identity_recorded_in(self.approved) or (None,)
        return pinned is not None and pinned == identity[0]

    def final_target(self, state: PinnedState) -> _records.EvidenceTarget | None:
        """What evidence of the final head answers for, or None where `state` settled no report to bind it to.

        The approved review, on the settled report's publication -- its
        repository, pull request, and branch -- moved to the final head and
        the requirements that review was given.
        """
        settled = _report_settlement.read_current_report(state)
        requirements = ReviewSubject.requirements_recorded_in(self.approved)
        if settled is None or requirements is None:
            return None
        publication = replace(settled.subject, source_sha=self.final_head, requirements_revision=requirements)
        return _records.EvidenceTarget(publication, self.approved)

    def entry_target(self, state: PinnedState) -> _records.EvidenceTarget | None:
        """What the evidence the approval rests on answers for, or None where `state` settled no report.

        The same approved review on the same publication as `final_target`,
        at the head the pass was entered on: the approved commit, or the
        squash an approval's carry answers for.
        """
        target = self.final_target(state)
        if target is None:
            return None
        return replace(target, publication=replace(target.publication, source_sha=self.entry_head))

    def recorded(self) -> dict:
        """The pinned object this completion is written as."""
        evidence = None
        if self.evidence is not None:
            evidence = {_RECEIPT: self.evidence.receipt, _REVISION: self.evidence.revision}
        return {
            _APPROVED: dict(self.approved),
            _ENTRY_HEAD: self.entry_head,
            _FINAL_HEAD: self.final_head,
            _VERIFICATION: self.verification.value,
            _EVIDENCE: evidence,
        }

    @classmethod
    def read(cls, recorded: object) -> FinalDocs | None:
        """The completion `recorded` holds, read whole, or None.

        The approved subject has to read as one on a pull request with a
        report -- an approval nothing identifies is no approval a completion
        follows -- both heads whole commit ids, and the evidence present
        exactly where the verification rests on some.
        """
        if not isinstance(recorded, dict) or set(recorded) != _MEMBERS:
            return None
        approved = recorded[_APPROVED]
        identity = ReviewSubject.identity_recorded_in(approved)
        verification = recorded[_VERIFICATION]
        if identity is None or None in identity or verification not in _VERIFICATIONS:
            return None
        final = cls(
            approved=dict(approved),
            entry_head=_payloads.as_hex(recorded[_ENTRY_HEAD], _formats.COMMIT_LENGTHS) or "",
            final_head=_payloads.as_hex(recorded[_FINAL_HEAD], _formats.COMMIT_LENGTHS) or "",
            verification=FinalVerification(verification),
            evidence=FinalEvidence.read(recorded[_EVIDENCE]),
        )
        return final if final._whole(recorded[_EVIDENCE]) else None

    def _whole(self, evidence: object) -> bool:
        """Whether the heads read, are equal exactly for RETAINED, and `evidence` is named exactly where it is owed."""
        unconfigured = self.verification is FinalVerification.UNCONFIGURED
        named = evidence is None if unconfigured else self.evidence is not None
        retained = self.verification is FinalVerification.RETAINED
        return bool(self.entry_head and self.final_head) and named and (
            (self.entry_head == self.final_head) is retained
        )


def read_final_docs(state: PinnedState) -> FinalDocs | None:
    """The final-documentation completion `state` records, or None for none readable."""
    return FinalDocs.read(state.get(FINAL_DOCS))


def record_final_docs(state: PinnedState, final: FinalDocs) -> bool:
    """Stage `final` on `state`; False, with `state` untouched, where it would not read back whole.

    The caller writes, through a guarded commit owning `FINAL_DOCS`.
    """
    recorded = final.recorded()
    if FinalDocs.read(recorded) != final:
        return False
    state.set(FINAL_DOCS, recorded)
    return True


def answers_for(state: PinnedState, binding: _records.EvidenceBinding) -> bool:
    """Whether the completion `state` records licenses `binding` to answer for the approved subject at its final head.

    Only an EXECUTED completion, only for a run this orchestrator executed
    on exactly the final head it records -- tested there, and bound to
    exactly what a run of that head answers for (`FinalDocs.final_target`):
    the approved review on the settled report's repository, pull request, and
    branch at the final head, under the requirements that review was given,
    so a run moved onto another publication licenses nothing -- and only over
    the approved subject it records, which has to still be the approval this
    issue records, read whole. Read off the pinned comment alone.
    """
    final = read_final_docs(state)
    if final is None or final.verification is not FinalVerification.EXECUTED:
        return False
    return (
        binding.source is EvidenceSource.ORCHESTRATOR_EXECUTED
        and binding.tested_sha == final.final_head
        and binding.target == final.final_target(state)
        and final.approved == _approval_in(state)
    )


def _approval_in(state: PinnedState) -> dict | None:
    """The approved subject `state` records, or None where it does not read whole.

    Read before it is compared: `==` takes a hand edit's `true` for a
    revision of `1`, and `1.0` for it too, and an approval its own reader
    refuses is one no completion follows.
    """
    recorded = state.get(APPROVED_SUBJECT)
    return None if ReviewSubject.identity_recorded_in(recorded) is None else recorded
