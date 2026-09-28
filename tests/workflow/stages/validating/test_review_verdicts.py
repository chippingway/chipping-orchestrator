# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a returned reviewer's verdict waits in, read back fail-closed.

What goes down is what the next tick finishes a verdict from without asking a
reviewer again, so it reads back exactly as written or not at all: a record
short of a member, carrying one nothing writes, or holding a value in a shape
its writer never spells is no verdict anybody may act on. It is staged only
where the comment has room for it at the widest write it is part of -- its
handoff, the developer launch's charge, and the transaction it claims settling
beside them -- and dropped only where it stands.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github import verification_evidence as _evidence
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    run_ledger as _run_ledger,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.engine import verification_record_test_support as _record_support

RECEIPT = "issue-7-verification-3-00000000000000000000000000000000"

DIGEST = "d" * len(_record_support.REQUIREMENTS)

# A digest cut short, which names no evidence.
SHORT_DIGEST = DIGEST[: len(_record_support.TESTED_SHA)]

# More than one pinned comment carries.
_PAST_THE_CEILING = "x" * (MAX_PINNED_BODY + 1)

# A reuse of the current evidence a reviewer was handed, which stages no
# transaction beside the verdict claiming it.
CLAIM = _verdicts.EvidenceClaim(
    use=_verdicts.EvidenceUse.REUSED,
    receipt=RECEIPT,
    revision=3,
    digest=DIGEST,
    passed=True,
)

# The lifetime agent-run count a change request was handed to `fixing` on.
HANDED_AT = 4

RETURNED = _verdicts.ReturnedVerdict(
    round_n=0,
    verdict=_verdicts.CHANGES_REQUESTED,
    subject=_record_support.SUBJECT.recorded(),
    feedback="1. Handle the empty configuration.",
    evidence=CLAIM,
)


APPROVED = replace(RETURNED, verdict=_verdicts.APPROVED, feedback="")

# The transaction a reviewer's own commands are minted as on an issue that has
# spent no revision, and a change request claiming it.
PENDING = _record_support.minted(
    PinnedState(comment_id=1, state_data={}),
    _record_support.binding(source=_evidence.EvidenceSource.REVIEWER_REPORTED),
)

CLAIMING = replace(RETURNED, evidence=replace(
    CLAIM,
    use=_verdicts.EvidenceUse.PUBLISHED,
    receipt=PENDING.receipt,
    revision=PENDING.revision,
    digest=PENDING.content_revision,
))

# Another transaction minted from the same run past the first one's revision:
# another receipt, another revision.
OTHER_PENDING = _record_support.minted(
    PinnedState(comment_id=1, state_data={_records.REVISION_FLOOR: PENDING.revision}), PENDING.binding,
)

FILLER = "operator_notes"

# Words a reviewer's JSON decodes into a `str` UTF-8 cannot carry.
LONE_SURROGATE = "1. Handle \ud800 too."

# What a change request's handoff and its developer's launch write, at widths
# GitHub and the ledger spell them in practice: the feedback comment's id, the
# lifetime count the request is handed at, and the launch's fingerprint.
POSTED_ID = 3_456_789_012

RUNS_USED = 41

LAUNCH = "0123456789abcdef" * 4

# How far short of the comment's last character a sweep starts: past all the
# handoff, the launch's charge, and a claimed transaction's settlement add
# beside the records first written.
SWEEP = 1_000


def _filled_to(
    returned: _verdicts.ReturnedVerdict,
    pending: _records.PendingEvidence | None = None,
    short: int = 0,
    *,
    recorded: bool = False,
) -> PinnedState:
    """A comment filled so `returned` and `pending`, as first written, end `short` characters before its last.

    `recorded` leaves `pending` on the comment already, as an earlier attempt
    at the same write recorded it before the comment filled.
    """
    staged = PinnedState(comment_id=1, state_data={FILLER: ""})
    if pending is not None:
        _record_state.record_pending_evidence(staged, pending)
    kept = dict(staged.data) if recorded else {}
    staged.set(_verdicts.RETURNED_VERDICT, returned.recorded())
    filled = "x" * (MAX_PINNED_BODY - len(pinned_state_body(staged.data)) - short)
    return PinnedState(comment_id=1, state_data={**kept, FILLER: filled})


def _handed_and_charged(state: PinnedState, pending: _records.PendingEvidence | None = None) -> bool:
    """Whether the comment still fits once the request is handed over, its launch charged, and `pending` settled.

    All are written while the verdict stands: the handoff by its own write,
    the charge composed over the comment that write left, and the claimed
    transaction's settlement on whichever tick its publication lands.
    """
    _verdicts.hands_off(state, RUNS_USED)
    state.set("pending_fix_reviewer_comment_id", POSTED_ID)
    _comments._track_orchestrator_comment(state, POSTED_ID)
    state.set("agent_runs_used", RUNS_USED)
    _run_ledger._reserve_run(state, LAUNCH)
    if not _report_record_state.fits_the_comment(state.data):
        return False
    if pending is None:
        return True
    settled = _record_state.settled_payload(state, pending)
    return settled is not None and _report_record_state.fits_the_comment(settled)


def _swept(
    returned: _verdicts.ReturnedVerdict, pending: _records.PendingEvidence | None = None, recorded: bool = False,
) -> tuple[list[int], list[int]]:
    """Every sweep step `returned` and `pending` are accepted at, and those with no room left to hand them over.

    `recorded` sweeps comments already carrying `pending`, as `_filled_to` leaves them.
    """
    accepted, overflowing = [], []
    for short in range(SWEEP):
        state = _filled_to(returned, pending, short, recorded=recorded)
        if not _verdicts.records_the_verdict(state, returned, pending):
            continue
        accepted.append(short)
        if not _handed_and_charged(state, pending):
            overflowing.append(short)
    return accepted, overflowing


def _with(record: dict, **members) -> dict:
    """`record` with `members` replaced, or removed where given as `...`."""
    edited = {**record, **members}
    return {key: member for key, member in edited.items() if member is not ...}


class ReturnedVerdictRecordTest(unittest.TestCase):
    """What the record reads back as."""

    def test_every_shape_its_writer_spells_reads_back(self) -> None:
        for returned in (
            RETURNED,
            _verdicts.ReturnedVerdict(0, _verdicts.APPROVED, RETURNED.subject),
            replace(RETURNED, handed=HANDED_AT),
            CLAIMING,
            _verdicts.ReturnedVerdict(
                2, _verdicts.APPROVED, RETURNED.subject,
                evidence=replace(CLAIMING.evidence, passed=False),
            ),
        ):
            with self.subTest(returned=returned):
                state = _record_support.reread(PinnedState(
                    comment_id=1, state_data={_verdicts.RETURNED_VERDICT: returned.recorded()},
                ))
                self.assertEqual(_verdicts.read_returned_verdict(state), returned)

    def test_anything_else_reads_as_no_verdict(self) -> None:
        recorded = RETURNED.recorded()
        claim = CLAIM.recorded()
        for name, damaged in (
            ("null", None),
            ("a member missing", _with(recorded, feedback=...)),
            ("a member nothing writes", _with(recorded, session="rev-sess")),
            ("a verdict nobody acts on", _with(recorded, verdict="unknown")),
            ("a round below zero", _with(recorded, round=-1)),
            ("a round that is a flag", _with(recorded, round=True)),
            ("a handoff below zero", _with(recorded, handed=-1)),
            ("an approval handed to a developer", _with(recorded, verdict="approved", feedback="", handed=HANDED_AT)),
            ("an approval carrying feedback", _with(recorded, verdict="approved")),
            ("a subject short of its head", _with(recorded, subject=_with(RETURNED.subject, sha=...))),
            ("feedback that is no text", _with(recorded, feedback=["1."])),
            ("feedback UTF-8 cannot carry", _with(recorded, feedback=LONE_SURROGATE)),
            ("a handoff wider than its room", _with(recorded, handed=_record_values.MAX_RECORDED_NUMBER + 1)),
            ("a claim of another revision", _with(recorded, evidence=_with(claim, revision=4))),
            ("a claim with a short digest", _with(recorded, evidence=_with(claim, digest=SHORT_DIGEST))),
            ("a claim nobody spells", _with(recorded, evidence=_with(claim, use="carried"))),
            ("a claim passing as text", _with(recorded, evidence=_with(claim, passed="yes"))),
            ("a coverage that is no flag", _with(recorded, evidence=_with(claim, covers=1))),
            ("a claim short of a member", _with(recorded, evidence=_with(claim, passed=...))),
        ):
            with self.subTest(name):
                state = PinnedState(comment_id=1, state_data={_verdicts.RETURNED_VERDICT: damaged})
                self.assertIsNone(_verdicts.read_returned_verdict(state))

    def test_a_handoff_marks_the_waiting_one(self) -> None:
        carried = PinnedState(
            comment_id=1, state_data={_verdicts.RETURNED_VERDICT: RETURNED.recorded()},
        )
        untouched = PinnedState(comment_id=1, state_data={})

        _verdicts.hands_off(carried, HANDED_AT)
        _verdicts.hands_off(untouched, HANDED_AT)

        self.assertEqual(
            (_verdicts.read_returned_verdict(carried), untouched.data),
            (replace(RETURNED, handed=HANDED_AT), {}),
        )

    def test_a_drop_touches_only_a_carried_one(self) -> None:
        carried = PinnedState(
            comment_id=1, state_data={_verdicts.RETURNED_VERDICT: RETURNED.recorded()},
        )
        untouched = PinnedState(comment_id=1, state_data={})

        self.assertEqual(
            (_verdicts.drops_the_verdict(carried), _verdicts.drops_the_verdict(untouched)),
            (True, False),
        )
        self.assertEqual(carried.data, {_verdicts.RETURNED_VERDICT: None})
        self.assertEqual(untouched.data, {})

    def test_a_named_drop_touches_only_the_one_held(self) -> None:
        # One another road put in its place, or already cleared, stays exactly
        # as that road left it.
        for name, carried, dropped in (
            ("the one held", RETURNED.recorded(), True),
            ("another in its place", APPROVED.recorded(), False),
            ("one already cleared", None, False),
        ):
            with self.subTest(name):
                state = PinnedState(comment_id=1, state_data={_verdicts.RETURNED_VERDICT: carried})

                self.assertEqual(
                    (_verdicts.drops_the_verdict(state, only=RETURNED), state.data),
                    (dropped, {_verdicts.RETURNED_VERDICT: None if dropped else carried}),
                )


class ReturnedVerdictRoomTest(unittest.TestCase):
    """Where the record is staged, measured at the widest write it is part of."""

    def test_staged_only_where_there_is_room(self) -> None:
        roomy = PinnedState(comment_id=1, state_data={})
        self.assertTrue(_verdicts.records_the_verdict(roomy, RETURNED))
        self.assertEqual(roomy.get(_verdicts.RETURNED_VERDICT), RETURNED.recorded())

        full = PinnedState(comment_id=1, state_data={"filler": _PAST_THE_CEILING})
        self.assertFalse(_verdicts.records_the_verdict(full, RETURNED))
        self.assertFalse(full.carries(_verdicts.RETURNED_VERDICT))

    def test_a_change_request_reserves_its_handoff(self) -> None:
        # Where the record as first written is the comment's last character, a
        # change request is refused -- its handoff writes the handed count,
        # the feedback's anchor, and that comment's ledger entry beside it --
        # and an approval, never handed, is not.
        for returned, accepted in ((RETURNED, False), (APPROVED, True)):
            with self.subTest(verdict=returned.verdict):
                state = _filled_to(returned)

                self.assertEqual(
                    (_verdicts.records_the_verdict(state, returned), state.carries(_verdicts.RETURNED_VERDICT)),
                    (accepted, accepted),
                )

    def test_accepted_records_leave_the_launch_room(self) -> None:
        # Every comment a change request is accepted into, up to its last
        # character, still carries the request handed over and the developer
        # launch's charge of the run ledger behind it -- and the transaction
        # it claims settling beside them, a retry of the one the comment
        # already carries included.
        for name, swept in (
            ("no transaction", (RETURNED,)),
            ("its transaction", (CLAIMING, PENDING)),
            ("its transaction already recorded", (CLAIMING, PENDING, True)),
        ):
            with self.subTest(name):
                accepted, overflowing = _swept(*swept)

                self.assertTrue(accepted, "the sweep reached no comment the records fit")
                self.assertEqual(overflowing, [], "characters short of the comment's last")

    def test_nothing_it_cannot_finish_is_staged(self) -> None:
        # A record its own reader refuses is no verdict a later tick can
        # finish. A published claim staged without its transaction, or beside
        # one it does not name whole, relies on evidence nothing will settle;
        # a reuse, or no claim at all, relies on no transaction.
        for name, returned, pending in (
            ("a round below zero", replace(RETURNED, round_n=-1), None),
            ("a handoff wider than its room", replace(RETURNED, handed=_record_values.MAX_RECORDED_NUMBER + 1), None),
            ("an approval carrying feedback", replace(APPROVED, feedback=RETURNED.feedback), None),
            ("feedback UTF-8 cannot carry", replace(RETURNED, feedback=LONE_SURROGATE), None),
            ("a published claim without its transaction", CLAIMING, None),
            ("a published claim beside another transaction", CLAIMING, OTHER_PENDING),
            ("a published claim failing where its transaction passed", replace(
                CLAIMING, evidence=replace(CLAIMING.evidence, passed=False),
            ), PENDING),
            ("a reuse beside a transaction", RETURNED, PENDING),
            ("no claim beside a transaction", replace(RETURNED, evidence=None), PENDING),
        ):
            with self.subTest(name):
                state = PinnedState(comment_id=1, state_data={})

                self.assertFalse(_verdicts.records_the_verdict(state, returned, pending))
                self.assertEqual(state.data, {})

    def test_its_transaction_goes_with_it_or_neither(self) -> None:
        roomy = PinnedState(comment_id=1, state_data={})
        self.assertTrue(_verdicts.records_the_verdict(roomy, CLAIMING, PENDING))
        self.assertEqual(
            (_verdicts.read_returned_verdict(roomy), _record_state.read_pending_evidence(roomy)),
            (CLAIMING, PENDING),
        )

        # A comment with room for a verdict of the same width claiming no
        # transaction, and one whose floor has spent the transaction's
        # revision already, take neither record.
        for name, state in (
            ("no room for the transaction", _filled_to(CLAIMING, short=SWEEP)),
            ("a revision already spent", PinnedState(
                comment_id=1, state_data={_records.REVISION_FLOOR: PENDING.revision},
            )),
        ):
            with self.subTest(name):
                before = dict(state.data)

                self.assertTrue(_verdicts.records_the_verdict(PinnedState(state_data=dict(before)), RETURNED))
                self.assertFalse(_verdicts.records_the_verdict(state, CLAIMING, PENDING))
                self.assertEqual(state.data, before)

        # An identical retry of the transaction the comment already carries is
        # measured beside the verdict all the same.
        retried = _filled_to(CLAIMING, PENDING, recorded=True)
        before = dict(retried.data)

        self.assertFalse(_verdicts.records_the_verdict(retried, CLAIMING, PENDING))
        self.assertEqual(retried.data, before)


if __name__ == "__main__":
    unittest.main()
