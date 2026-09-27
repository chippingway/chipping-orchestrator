# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted before anything is done with it.

A reviewer's verdict is acted on in steps that each ask GitHub for something:
its verification evidence is published, or the evidence it reused is proved
still current, and only then is the approval or the change request carried
out. Any of those can be refused or interrupted, and the next tick has to
finish them from what the reviewer said rather than from a second reviewer --
which would spend another run, fold its usage again, and could say something
else about the same subject. So the verdict is written onto the pinned comment
in the write the returned reviewer makes, before the evidence is published or
the verdict disposed of, and every disposition drops it in the write it makes.

`review_returned_verdict` holds the round the reviewer ran as, its verdict,
the subject it was handed exactly as `review_subjects` records one, the
feedback a change request hands the developer, and the evidence the verdict
relies on: the receipt, revision, and evidence digest of the transaction the
reviewer's own commands were recorded as (`published`), or of the current
evidence it named instead of running anything (`reused`), with whether every
command it lists exited 0. A declaration that earned no evidence leaves
`evidence` `null`.

The record is additive and fail-closed: an issue without it has no verdict
waiting, and one in any shape this reader refuses is dropped rather than acted
on, so a fresh reviewer is handed the subject as it stands. It is measured
before it is staged -- a change request's feedback is the reviewer's own words
and has no bound -- and a comment with no room for it goes without the record
rather than past what GitHub accepts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    review_subjects as _review_subjects,
    verification_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The verdict a returned reviewer left and no disposition has dropped yet.
RETURNED_VERDICT = "review_returned_verdict"

# The two verdicts a returned reviewer's record is written for; a reviewer
# that named neither parks where it returns.
APPROVED = "approved"

CHANGES_REQUESTED = "changes_requested"

_ROUND = "round"

_VERDICT = "verdict"

_SUBJECT = "subject"

_FEEDBACK = "feedback"

_EVIDENCE = "evidence"

_USE = "use"

_RECEIPT = "receipt"

_REVISION = "revision"

_DIGEST = "digest"

_PASSED = "passed"

_VERDICT_MEMBERS = frozenset((_ROUND, _VERDICT, _SUBJECT, _FEEDBACK, _EVIDENCE))

_CLAIM_MEMBERS = frozenset((_USE, _RECEIPT, _REVISION, _DIGEST, _PASSED))


class EvidenceUse(StrEnum):
    """How a verdict relies on verification evidence.

    PUBLISHED is a transaction recording the commands the reviewer ran, owed
    to the pull request until it settles. REUSED is the current evidence the
    reviewer was handed and named instead of running anything.
    """

    PUBLISHED = "published"
    REUSED = "reused"


@dataclass(frozen=True)
class EvidenceClaim:
    """The one piece of evidence a verdict relies on, named exactly.

    `digest` is the evidence digest a reviewer names, and `passed` whether at
    least one command ran and every one exited 0.
    """

    use: EvidenceUse
    receipt: str
    revision: int
    digest: str
    passed: bool

    def recorded(self) -> dict:
        """The pinned object this claim is written as."""
        return {
            _USE: self.use.value,
            _RECEIPT: self.receipt,
            _REVISION: self.revision,
            _DIGEST: self.digest,
            _PASSED: self.passed,
        }

    @classmethod
    def read(cls, recorded: object) -> EvidenceClaim | None:
        """The claim a recorded object names, read whole, or None."""
        if not isinstance(recorded, dict) or set(recorded) != _CLAIM_MEMBERS:
            return None
        claim = cls(
            use=_payloads.as_member(EvidenceUse, recorded[_USE]),
            receipt=recorded[_RECEIPT],
            revision=_record_values.as_recorded_number(recorded[_REVISION]),
            digest=_payloads.as_hex(recorded[_DIGEST], _formats.DIGEST_LENGTHS),
            passed=recorded[_PASSED],
        )
        read_whole = (
            claim.use is not None,
            claim.revision is not None
            and isinstance(claim.receipt, str)
            and _records.PendingEvidence.receipt_names(claim.receipt, claim.revision),
            claim.digest is not None,
            isinstance(claim.passed, bool),
        )
        return claim if all(read_whole) else None


@dataclass(frozen=True)
class ReturnedVerdict:
    """What one returned reviewer decided, and the evidence its verdict relies on.

    `subject` is the review subject exactly as `review_subjects` records it.
    """

    round_n: int
    verdict: str
    subject: dict
    feedback: str = ""
    evidence: EvidenceClaim | None = None

    def recorded(self) -> dict:
        """The pinned object this verdict is written as."""
        return {
            _ROUND: self.round_n,
            _VERDICT: self.verdict,
            _SUBJECT: self.subject,
            _FEEDBACK: self.feedback,
            _EVIDENCE: None if self.evidence is None else self.evidence.recorded(),
        }

    @classmethod
    def read(cls, recorded: object) -> ReturnedVerdict | None:
        """The verdict a recorded object names, read whole, or None."""
        if not isinstance(recorded, dict) or set(recorded) != _VERDICT_MEMBERS:
            return None
        claimed = recorded[_EVIDENCE]
        evidence = None if claimed is None else EvidenceClaim.read(claimed)
        returned = cls(
            round_n=_payloads.as_count(recorded[_ROUND]),
            verdict=recorded[_VERDICT],
            subject=recorded[_SUBJECT],
            feedback=recorded[_FEEDBACK],
            evidence=evidence,
        )
        read_whole = (
            returned.round_n is not None,
            returned.verdict in (APPROVED, CHANGES_REQUESTED),
            _review_subjects.ReviewSubject.identity_recorded_in(returned.subject) is not None,
            isinstance(returned.feedback, str),
            evidence is not None or claimed is None,
        )
        return returned if all(read_whole) else None


def read_returned_verdict(state: PinnedState) -> ReturnedVerdict | None:
    """The verdict this issue has waiting, or None for none readable."""
    return ReturnedVerdict.read(state.get(RETURNED_VERDICT))


def records_the_verdict(state: PinnedState, returned: ReturnedVerdict) -> bool:
    """Stage `returned` where the comment has room for it; False, untouched, where not.

    The caller writes.
    """
    staged = {**state.data, RETURNED_VERDICT: returned.recorded()}
    if not _report_record_state.fits_the_comment(staged):
        return False
    state.set(RETURNED_VERDICT, returned.recorded())
    return True


def drops_the_verdict(state: PinnedState) -> None:
    """Stage the end of the verdict this issue had waiting, where it has one.

    Only where the key is present, so an issue that never carried one is not
    given it. The caller writes.
    """
    if state.carries(RETURNED_VERDICT):
        state.set(RETURNED_VERDICT, None)
