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
in the write that records the returned reviewer's run (`review_disposition`),
before the evidence is published or the verdict disposed of, and every
disposition drops it in the write it makes.

`review_returned_verdict` holds the round the reviewer ran as, its verdict,
the subject it was handed exactly as `review_subjects` records one, the
feedback a change request hands the developer, and the evidence the verdict
relies on: the receipt, revision, and evidence digest of the transaction the
reviewer's own commands were recorded as (`published`), or of the current
evidence it named instead of running anything (`reused`), with whether every
command it lists exited 0 and whether those commands cover every configured
verification command. A declaration that earned no evidence leaves
`evidence` `null`. `handed` is `null` until a change request is handed to
`workflow:fixing`, and then the lifetime agent-run count as that handoff was
written: the handoff goes down before the relabel and the developer launch, so
a tick that finds the record with no launch charged past that count -- or one
charged and never started, or a charge another road took -- still owes the
developer the feedback, and hands it over instead of a fresh reviewer taking the
round (`review_resume`, `review_handoffs`). An approval is never handed and hands
nobody words, so a record saying it was, or carrying feedback, does not read.

The record is additive and fail-closed: an issue without it has no verdict
waiting, and one in any shape this reader refuses is dropped rather than acted
on, so a fresh reviewer is handed the subject as it stands. It is measured
before it is staged -- a change request's feedback is the reviewer's own words
and has no bound -- and a comment with no room for it goes without the record
rather than past what GitHub accepts. It is measured at the widest write it is
ever part of: a change request is written again as handed, beside the anchor
of the feedback it posted and that comment's ledger entry, and stays pinned
through the developer launch's own charge of the run ledger, so the handoff
and that charge are reserved here, and the transaction the verdict claims is
measured beside the reservation rather than beside the narrower record.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    review_subjects as _review_subjects,
    run_ledger as _run_ledger,
    run_ledger_values as _run_ledger_values,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.validating import review_records as _review_records

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

_COVERS = "covers"

_HANDED = "handed"

# The replay anchor a change request's handoff records beside it.
_FEEDBACK_ANCHOR = "pending_fix_reviewer_comment_id"

_VERDICT_MEMBERS = frozenset((_ROUND, _VERDICT, _SUBJECT, _FEEDBACK, _EVIDENCE, _HANDED))

_CLAIM_MEMBERS = frozenset((_USE, _RECEIPT, _REVISION, _DIGEST, _PASSED, _COVERS))


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

    `digest` is the evidence digest a reviewer names, `passed` whether at
    least one command ran and every one exited 0, and `covers` whether every
    configured `VERIFY_COMMANDS` command is among them, exactly as configured,
    exiting 0 -- which an approval requires, and nothing else asks.
    """

    use: EvidenceUse
    receipt: str
    revision: int
    digest: str
    passed: bool
    covers: bool = False

    def recorded(self) -> dict:
        """The pinned object this claim is written as."""
        return {
            _USE: self.use.value,
            _RECEIPT: self.receipt,
            _REVISION: self.revision,
            _DIGEST: self.digest,
            _PASSED: self.passed,
            _COVERS: self.covers,
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
            covers=recorded[_COVERS],
        )
        read_whole = (
            claim.use is not None,
            claim.revision is not None
            and isinstance(claim.receipt, str)
            and _records.PendingEvidence.receipt_names(claim.receipt, claim.revision),
            claim.digest is not None,
            isinstance(claim.passed, bool),
            isinstance(claim.covers, bool),
        )
        return claim if all(read_whole) else None


@dataclass(frozen=True)
class ReturnedVerdict:
    """What one returned reviewer decided, and the evidence its verdict relies on.

    `subject` is the review subject exactly as `review_subjects` records it,
    and `handed` the agent-run count a change request was handed on, or None.
    """

    round_n: int
    verdict: str
    subject: dict
    feedback: str = ""
    evidence: EvidenceClaim | None = None
    handed: int | None = None

    def recorded(self) -> dict:
        """The pinned object this verdict is written as."""
        return {
            _ROUND: self.round_n,
            _VERDICT: self.verdict,
            _SUBJECT: self.subject,
            _FEEDBACK: self.feedback,
            _EVIDENCE: None if self.evidence is None else self.evidence.recorded(),
            _HANDED: self.handed,
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
            handed=_payloads.as_count(recorded[_HANDED]),
        )
        read_whole = (
            returned.round_n is not None,
            returned.handed is not None or recorded[_HANDED] is None,
            # Only a change request is ever handed to a developer, or hands
            # it words: an approval's feedback is written empty.
            recorded[_HANDED] is None or returned.verdict == CHANGES_REQUESTED,
            returned.verdict == CHANGES_REQUESTED or returned.feedback == "",
            returned.verdict in (APPROVED, CHANGES_REQUESTED),
            _review_subjects.ReviewSubject.identity_recorded_in(returned.subject) is not None,
            isinstance(returned.feedback, str),
            evidence is not None or claimed is None,
        )
        return returned if all(read_whole) else None

    def at_its_handoff(self, state: PinnedState) -> PinnedState:
        """A copy of `state` carrying this verdict as the widest write it is part of; never written.

        A change request goes down again as handed -- at an agent-run count,
        beside the anchor of the feedback it posted, which the comment's ledger
        records too -- and is still pinned when the developer's launch charges
        the run ledger, composed over that very comment, so each is reserved at
        the widest a recorded number or fingerprint is spelled, the charge
        through the ledger's own writer as a reviewer round's is. An approval
        is never handed, and is measured as it is.
        """
        reserved = PinnedState(comment_id=state.comment_id, state_data=dict(state.data))
        written = self
        if self.verdict == CHANGES_REQUESTED:
            widest = _record_values.MAX_RECORDED_NUMBER
            written = replace(self, handed=widest)
            reserved.set(_FEEDBACK_ANCHOR, widest)
            _comments._reserve_comment_slot(reserved, widest)
            # The charge adds one to the count it finds.
            reserved.set(_run_ledger_values.AGENT_RUNS_USED, widest - 1)
            _run_ledger._reserve_run(reserved, _review_records._WIDEST_FINGERPRINT)
        reserved.set(RETURNED_VERDICT, written.recorded())
        return reserved


def read_returned_verdict(state: PinnedState) -> ReturnedVerdict | None:
    """The verdict this issue has waiting, or None for none readable."""
    return ReturnedVerdict.read(state.get(RETURNED_VERDICT))


def records_the_verdict(
    state: PinnedState,
    returned: ReturnedVerdict,
    pending: _records.PendingEvidence | None = None,
) -> bool:
    """Stage `returned` and the transaction `pending` it claims where they fit; False, untouched, where not.

    Measured at the verdict's handoff (`ReturnedVerdict.at_its_handoff`), and
    the transaction over that -- its own record and the write that settles it
    (`verification_record_state`) -- so neither the settlement nor the handoff
    is the write GitHub refuses. The caller writes.
    """
    reserved = returned.at_its_handoff(state)
    if pending is None:
        fits = _report_record_state.fits_the_comment(reserved.data)
    else:
        fits = _record_state.record_pending_evidence(reserved, pending)
    if not fits or (pending is not None and not _record_state.record_pending_evidence(state, pending)):
        return False
    state.set(RETURNED_VERDICT, returned.recorded())
    return True


def hands_off(state: PinnedState, runs_used: int) -> None:
    """Stage the waiting verdict as handed to `workflow:fixing` at `runs_used`, where it waits.

    Written by the handoff's own write, ahead of the relabel, and kept past
    both, so the developer launch that write precedes is the only thing that
    can retire it. The caller writes.
    """
    waiting = read_returned_verdict(state)
    if waiting is not None:
        state.set(RETURNED_VERDICT, replace(waiting, handed=runs_used).recorded())


def drops_the_verdict(state: PinnedState) -> None:
    """Stage the end of the verdict this issue had waiting, where it has one.

    Only where the key is present, so an issue that never carried one is not
    given it. The caller writes.
    """
    if state.carries(RETURNED_VERDICT):
        state.set(RETURNED_VERDICT, None)
