# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a returned reviewer's verdict waits in, read back fail-closed.

What goes down is what the next tick finishes a verdict from without asking a
reviewer again, so it reads back exactly as written or not at all: a record
short of a member, carrying one nothing writes, or holding a value in a shape
its writer never spells is no verdict anybody may act on. It is staged only
where the comment has room for it, and dropped only where it stands.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.engine import verification_record_test_support as _record_support

RECEIPT = "issue-7-verification-3-00000000000000000000000000000000"

DIGEST = "d" * len(_record_support.REQUIREMENTS)

# A digest cut short, which names no evidence.
SHORT_DIGEST = DIGEST[: len(_record_support.TESTED_SHA)]

# More than one pinned comment carries.
_PAST_THE_CEILING = "x" * (MAX_PINNED_BODY + 1)

CLAIM = _verdicts.EvidenceClaim(
    use=_verdicts.EvidenceUse.PUBLISHED,
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
            _verdicts.ReturnedVerdict(
                2, _verdicts.APPROVED, RETURNED.subject,
                evidence=_verdicts.EvidenceClaim(
                    _verdicts.EvidenceUse.REUSED, RECEIPT, 3, DIGEST, passed=False,
                ),
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
            ("an approval handed to a developer", _with(recorded, verdict="approved", handed=HANDED_AT)),
            ("a subject short of its head", _with(recorded, subject=_with(RETURNED.subject, sha=...))),
            ("feedback that is no text", _with(recorded, feedback=["1."])),
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

    def test_staged_only_where_there_is_room(self) -> None:
        roomy = PinnedState(comment_id=1, state_data={})
        self.assertTrue(_verdicts.records_the_verdict(roomy, RETURNED))
        self.assertEqual(roomy.get(_verdicts.RETURNED_VERDICT), RETURNED.recorded())

        full = PinnedState(comment_id=1, state_data={"filler": _PAST_THE_CEILING})
        self.assertFalse(_verdicts.records_the_verdict(full, RETURNED))
        self.assertFalse(full.carries(_verdicts.RETURNED_VERDICT))

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

        _verdicts.drops_the_verdict(carried)
        _verdicts.drops_the_verdict(untouched)

        self.assertEqual(carried.data, {_verdicts.RETURNED_VERDICT: None})
        self.assertEqual(untouched.data, {})


if __name__ == "__main__":
    unittest.main()
