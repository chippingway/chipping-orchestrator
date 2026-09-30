# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, as it is persisted before anything is done with it.

A reviewer's verdict is acted on in steps that each ask GitHub for something:
its verification evidence is published, or the evidence it reused is proved
still current, and only then is the approval or the change request carried
out. Any of those can be refused or interrupted, and the next tick has to
finish them from what the reviewer said rather than from a second reviewer --
which would spend another run, fold its usage again, and could say something
else about the same subject. So the verdict is to be written onto the pinned
comment in the write that records the returned reviewer's run, before the
evidence is published or the verdict disposed of, and dropped by whichever
write disposes of it. Only the dormant disposition service writes it
(`review_disposition`), with the change-request handoff it hands a ready
request to (`review_handoffs`), and no live reviewer round calls either yet:
the round keeps acting on its verdict in the tick it returns, and this owner is
the record alone -- its shape, its reader, its measurement, and its writers.

`review_returned_verdict` holds the round the reviewer ran as, its verdict,
the subject it was handed exactly as `review_subjects` records one, the
feedback a change request hands the developer, and the evidence the verdict
relies on (`review_claims`): the receipt, revision, and evidence digest of the
transaction the reviewer's own commands were minted as (`published`), or of
the current evidence it named instead of running anything (`reused`), with
whether every command it lists exited 0 and whether those commands cover every
configured verification command. A declaration that earned no evidence leaves
`evidence` `null`. `handed` is `null` until a change request is handed to
`workflow:fixing`, and then the lifetime agent-run count as that handoff was
written: the handoff goes down before the relabel and the developer launch,
and that launch's start records this very count in the run ledger
(`run_ledger_values.AGENT_RUN_OWED_STARTED`), which is the only thing that can
say the developer it owes was launched -- the count itself moves past it with
any other run charged meanwhile, a reviewer's say, and proves nothing.
`anchor` is the id of the feedback comment the request was handed over with,
written by that same write: the pinned feedback anchor a failed run's
`/orchestrator continue` replays has to name that comment for the launch the
handoff owes to be made, since another comment there would be replayed to the
developer as this reviewer's feedback. A record carries `anchor` only while
it is handed, so a verdict waiting to be handed is spelled in the six members
every writer of the record has spelled, and reads the same to each. A handed
record without one is the shape a handoff wrote before it anchored its post,
and still reads -- handed, beside no post anything can vouch for, so the
launch it owes is held rather than made (`review_handoffs`). An approval is
never handed and hands nobody words, so a record saying it was, or carrying
feedback, does not read.

The record is additive and fail-closed: an issue without it has no verdict
waiting, and one in any shape this reader refuses is no verdict anybody may
act on, so a fresh reviewer is handed the subject as it stands -- which is why
nothing the reader would refuse is staged in the first place. It is measured
before it is staged -- a change request's feedback is the reviewer's own words
and has no bound -- and a comment with no room for it goes without the record
rather than past what GitHub accepts. It is measured at the widest write it is
ever part of: a change request is written again as handed, beside the anchor
of the feedback it posted and that comment's ledger entry, and stays pinned
through the developer launch's own charge of the run ledger and its start, so
the handoff, that charge, and the start are reserved here, and the transaction
the verdict claims is measured beside the reservation rather than beside the
narrower record. It is staged only with exactly that transaction, and a
verdict claiming none only without one: a published claim persisted apart from
the transaction it names relies on evidence nothing will ever settle.
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

_ANCHOR = "anchor"

# The replay anchor a change request's handoff records beside it.
_FEEDBACK_ANCHOR = "pending_fix_reviewer_comment_id"

_VERDICT_MEMBERS = frozenset((_ROUND, _VERDICT, _SUBJECT, _FEEDBACK, _EVIDENCE, _HANDED))

# A handed verdict's, which name the feedback post it was handed over with too.
_HANDED_MEMBERS = _VERDICT_MEMBERS | {_ANCHOR}

# What `drops_the_verdict` drops where its caller names no verdict it holds.
_WHICHEVER = object()

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
    `handed` the agent-run count a change request was handed on, or None, and
    `anchor` the id of the feedback comment it was handed over with, or None
    -- on a handoff recorded before it anchored its post as much as on a
    verdict never handed.
    """

    round_n: int
    verdict: str
    subject: dict
    feedback: str = ""
    evidence: EvidenceClaim | None = None
    handed: int | None = None
    anchor: int | None = None

    def recorded(self) -> dict:
        """The pinned object this verdict is written as; `anchor` only where it names a post."""
        recorded = {
            _ROUND: self.round_n,
            _VERDICT: self.verdict,
            _SUBJECT: self.subject,
            _FEEDBACK: self.feedback,
            _EVIDENCE: None if self.evidence is None else self.evidence.recorded(),
            _HANDED: self.handed,
        }
        if self.anchor is not None:
            recorded[_ANCHOR] = self.anchor
        return recorded

    @classmethod
    def read(cls, recorded: object) -> ReturnedVerdict | None:
        """The verdict a recorded object names, read whole, or None."""
        if not isinstance(recorded, dict) or set(recorded) not in (_VERDICT_MEMBERS, _HANDED_MEMBERS):
            return None
        claimed = recorded[_EVIDENCE]
        evidence = None if claimed is None else EvidenceClaim.read(claimed)
        handed = _payloads.as_count(recorded[_HANDED])
        returned = cls(
            round_n=_payloads.as_count(recorded[_ROUND]),
            verdict=recorded[_VERDICT],
            subject=recorded[_SUBJECT],
            feedback=recorded[_FEEDBACK],
            evidence=evidence,
            handed=handed,
            anchor=_record_values.as_recorded_number(recorded.get(_ANCHOR)),
        )
        read_whole = (
            returned.round_n is not None,
            # Never wider than the count the handoff's room is reserved at.
            recorded[_HANDED] is None or (handed is not None and handed <= _record_values.MAX_RECORDED_NUMBER),
            # An anchor only beside a handoff, naming a comment by an id no
            # wider than the one the handoff's room is reserved at. A handoff
            # beside none is one recorded before handoffs anchored their post.
            _ANCHOR not in recorded or recorded[_HANDED] is not None,
            _ANCHOR not in recorded or returned.anchor is not None,
            # Only a change request is ever handed to a developer, or hands
            # it words: an approval's feedback is written empty.
            recorded[_HANDED] is None or returned.verdict == CHANGES_REQUESTED,
            returned.verdict == CHANGES_REQUESTED or returned.feedback == "",
            returned.verdict in (APPROVED, CHANGES_REQUESTED),
            _review_subjects.ReviewSubject.identity_recorded_in(returned.subject) is not None,
            # The feedback is posted as a comment and hashed nowhere else, so
            # words UTF-8 cannot carry would raise on the post it is kept for.
            isinstance(returned.feedback, str) and _record_values.carries_utf8(returned.feedback),
            evidence is not None or claimed is None,
        )
        return returned if all(read_whole) else None

    def said(self) -> tuple:
        """What its reviewer said -- round, verdict, subject, and feedback -- apart from any claim or handoff."""
        return (self.round_n, self.verdict, self.subject, self.feedback)

    def reads_back(self) -> bool:
        """Whether this verdict, written, reads back as exactly itself.

        What the record holds is the reviewer's own -- its words above all --
        and a verdict whose record its reader refuses, words UTF-8 cannot carry
        say, is no verdict a later tick can finish, however much room the
        comment has for it.
        """
        return ReturnedVerdict.read(self.recorded()) == self

    def claims_exactly(self, pending: _records.PendingEvidence | None) -> bool:
        """Whether `pending` is exactly the transaction this verdict relies on, or None where it relies on none.

        A published claim names one transaction by every member that
        transaction carries -- receipt, revision, evidence digest, and pass
        flag -- and only that transaction can settle it: persisted without it,
        or beside another, the verdict would rely on evidence nothing will ever
        publish. No claim, and a reuse, claim no transaction, so one staged
        beside them is evidence no verdict relies on.
        """
        claim = self.evidence
        if claim is None or claim.use is not EvidenceUse.PUBLISHED:
            return pending is None
        return pending is not None and (
            pending.receipt, pending.revision, pending.content_revision, pending.passed,
        ) == (claim.receipt, claim.revision, claim.digest, claim.passed)

    def fits_beside(self, state: PinnedState, pending: _records.PendingEvidence | None) -> bool:
        """Whether `state` has room for this verdict at its handoff, and for `pending` recorded and settled beside it.

        The transaction is measured here whichever way its record is accepted:
        an identical retry of the one `state` already carries is accepted
        without being measured again, and the comment may have filled since.
        """
        reserved = self.at_its_handoff(state)
        if pending is None:
            return _report_record_state.fits_the_comment(reserved.data)
        if not _record_state.record_pending_evidence(reserved, pending):
            return False
        settled = _record_state.settled_payload(reserved, pending)
        if settled is None:
            return False
        return _report_record_state.fits_the_comment(reserved.data) and _report_record_state.fits_the_comment(settled)

    def at_its_handoff(self, state: PinnedState) -> PinnedState:
        """A copy of `state` carrying this verdict as the widest write it is part of; never written.

        A change request goes down again as handed -- at an agent-run count,
        beside the anchor of the feedback it posted, which the comment's ledger
        records too -- and is still pinned when the developer's launch charges
        the run ledger and then starts, composed over that very comment, the
        start recording the count the launch is owed at. So each is reserved at
        the widest a recorded number or fingerprint is spelled, the charge and
        its start through the ledger's own writers, the very ones the run
        circuit writes them with; the started write, carrying that count, is
        wider than the reserved one it replaces. An approval is never handed,
        and is measured as it is.
        """
        reserved = PinnedState(comment_id=state.comment_id, state_data=dict(state.data))
        written = self
        if self.verdict == CHANGES_REQUESTED:
            widest = _record_values.MAX_RECORDED_NUMBER
            written = replace(self, handed=widest, anchor=widest)
            reserved.set(_FEEDBACK_ANCHOR, widest)
            _comments._reserve_comment_slot(reserved, widest)
            # The charge adds one to the count it finds.
            reserved.set(_run_ledger_values.AGENT_RUNS_USED, widest - 1)
            _run_ledger._reserve_run(reserved, _review_records._WIDEST_FINGERPRINT)
            _run_ledger._start_reserved_run(reserved, widest)
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

    Refused outright unless the record reads back as `returned` exactly
    (`ReturnedVerdict.reads_back`) and unless `pending` is exactly what the
    verdict claims
    (`ReturnedVerdict.claims_exactly`) -- and where it is a handoff beside no
    post, which reads only as a handoff wrote it before it anchored its post
    and whose launch is held for good. Measured at the verdict's handoff,
    and the transaction over that -- its own record and the write that
    settles it (`ReturnedVerdict.fits_beside`) -- so neither the settlement
    nor the handoff is the write GitHub refuses. The caller writes.
    """
    staged = returned.reads_back() and returned.claims_exactly(pending)
    staged = staged and (returned.handed is None or returned.anchor is not None)
    if not (staged and returned.fits_beside(state, pending)):
        return False
    if pending is not None and not _record_state.record_pending_evidence(state, pending):
        return False
    state.set(RETURNED_VERDICT, returned.recorded())
    return True


def hands_off(state: PinnedState, runs_used: int, anchor: int) -> None:
    """Stage the waiting verdict as handed to `workflow:fixing` at `runs_used`, behind the feedback posted as `anchor`.

    Written by the handoff's own write, ahead of the relabel, and kept past
    both, so the developer launch that write precedes is the only thing that
    can retire it. The pinned replay anchor is staged naming that same post,
    in that same write and nowhere before it. The caller writes.
    """
    waiting = read_returned_verdict(state)
    if waiting is not None:
        state.set(RETURNED_VERDICT, replace(waiting, handed=runs_used, anchor=anchor).recorded())
        state.set(_FEEDBACK_ANCHOR, anchor)


def drops_the_verdict(state: PinnedState, *, only: object = _WHICHEVER) -> bool:
    """Stage the end of the verdict this issue had waiting, where it has one; whether it did.

    Only where the key is present, so an issue that never carried one is not
    given it. `only`, where given, is the verdict the caller holds, and the
    waiting one is dropped only where it reads as exactly that: a verdict
    another road put in its place since, carried onto `state` by a reading of
    the comment, is that road's to finish, not the caller's to drop. None
    holds no verdict and drops nothing -- not even a record no reader can
    take, which reads as none too, but is another road's all the same, or a
    hand edit's, and is left exactly as it stands. The caller writes.
    """
    if not state.carries(RETURNED_VERDICT) or only is None:
        return False
    if only is not _WHICHEVER and read_returned_verdict(state) != only:
        return False
    state.set(RETURNED_VERDICT, None)
    return True
