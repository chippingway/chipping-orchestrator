# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval reaches the approval arc only over current, settled, passing evidence covering the configuration.

A waiting approval is handed to its proof the way the disposition service will
hand it (`approval_proof_test_support`), and the claim proved is the one its
own record names: a record naming none is refused beside evidence that would
have passed, and a run whose approval no longer waits has nothing to prove.
Evidence that did not pass, misses a
configured command, never settled, is not the current evidence, or no longer
proves current refuses the approval with the words its park would carry -- and
nothing is verified, posted, or written, since parking is the disposition's to
do. A proof nobody could read is no refusal: the approval holds, untouched, for
a later tick that proves it. A proof whose records moved on the pinned comment
while it was taken refuses too, and one behind which the comment would not
read holds.

The races the approval arc meets once the proof hands it on are in
`test_approval_races.py`.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    approval_proof_test_support as _proof,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

VERIFY = "_run_verify_commands"

# The claim an approval is recorded beside, once the arc takes it.
APPROVED_EVIDENCE = "review_approved_evidence"

ARTIFACT_REREAD = "reread_verification_artifact"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

# An evidence digest nothing in the world names.
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# What a proof that refused leaves: the gate unrun, nothing posted, nothing relabeled.
_UNTOUCHED = (0, [], [])


def _settled(case, *, declares: bool = True, **run):
    """A claim on one run the case settles as its current evidence, as `run` spells it -- None, where not `declares`."""
    claim = _proof.claim_on(_read.settles_evidence(case, **run))
    return claim if declares else None


def _owed(case):
    """A claim on one run whose publication GitHub took without answering, so it is still owed."""
    case.github.report_failures.lost.add(_world.PR)
    settled = _read.settles_evidence(case)
    case.github.report_failures.lost.discard(_world.PR)
    return _proof.claim_on(settled)


# What a refusal says where the evidence a claim names is not, or no longer
# proves to be, this issue's current evidence.
_NOT_CURRENT = "no longer this issue's current evidence"

# What a refusal says where the comment moved while the proof was taken.
_MOVED_RECORDS = "moved while it was proved"

# What a refusal says where the run's approval no longer waits.
_NOT_WAITING = "no approval of its round and subject waiting"

# Each claim a waiting approval relies on that refuses it, and a phrase the
# refusal says. The claim's own flags refuse it before anything is read; the
# evidence it names is held to what the pull request shows, however the claim
# describes it.
_REFUSED = (
    ("nothing declared", lambda _case: None, "nothing it declared earned"),
    ("nothing declared beside passing evidence", partial(_settled, declares=False), "nothing it declared earned"),
    ("a claim that failed", lambda case: replace(_settled(case), passed=False), "did not exit 0"),
    (
        "a claim missing a command",
        lambda case: replace(_settled(case), covers=False),
        f"every command `VERIFY_COMMANDS` requires: `{_world.SUITE}`",
    ),
    ("evidence that failed", partial(_settled, exit_status=1), "did not exit 0"),
    ("evidence of another command", partial(_settled, command="uv run ruff check"), "`VERIFY_COMMANDS` requires"),
    ("other evidence", lambda case: replace(_settled(case), digest=OTHER_DIGEST), _NOT_CURRENT),
    ("evidence still owed", _owed, "could not be published on the pull request"),
)


def _stops_reading(case) -> None:
    """`case`'s pinned comment stops answering its readers for the rest of the case."""
    case.enterContext(patch.object(case.github, "read_pinned_state", side_effect=RuntimeError("unanswered")))


def _replaces(case) -> None:
    """Another road putting a later round's approval in place of the one waiting."""
    later = dict(case.pinned()[_world.RETURNED_VERDICT], round=1)
    _parked.replaces_the_verdict(case, later)


def _touched(case, ran) -> tuple:
    """How often the tick ran the verify gate, what it posted on the thread, and every relabel."""
    github = case.github
    return (ran[VERIFY].call_count, github.posted_comments, github.label_history)


# What a proof cannot read, which holds the approval rather than refusing it.
_UNREAD = (
    ("the pull request", lambda case: patch.object(case.github.report_failures, "unreadable", {_world.PR})),
    ("the artifact's thread", lambda case: patch.object(case.github, "_verification_thread", side_effect=OSError)),
)

# What another road does behind the approval's last read of its artifact, and a
# phrase the refusal says -- None where the approval holds instead.
_BEHIND_THE_PROOF = (
    ("an evidence settlement", _read.settles_evidence, _MOVED_RECORDS),
    ("a repoint", _parked.repoints, _MOVED_RECORDS),
    ("a replaced verdict", _replaces, _MOVED_RECORDS),
    ("an unread comment", _stops_reading, None),
)


class ApprovalProofTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """A waiting approval is proved or refused -- and only a proved one reaches the arc."""

    def test_valid_evidence_reaches_the_arc(self) -> None:
        # Published or reused, the claim names the current evidence exactly
        # and that evidence passed, covers the suite, and proves current: the
        # arc runs the gate, records the approval beside the very claim its
        # waiting record named, retires the verdict in the write it makes,
        # and hands the issue to `documenting`.
        for reused in (False, True):
            with self.subTest(reused=reused):
                self.setUp()
                claim = _settled(self)
                if reused:
                    claim = replace(claim, use=_verdicts.EvidenceUse.REUSED)
                self.waits(claim)

                ran = self.approves()

                self.assertEqual(
                    (
                        self.answered,
                        ran[VERIFY].call_count,
                        self.github.label_history,
                        self.waiting(),
                        self.pinned().get("review_approved_subject") == self.run.subject.recorded(),
                    ),
                    ("", 1, [DOCUMENTING], None, True),
                )
                self.assertEqual(self.pinned().get(APPROVED_EVIDENCE), claim.recorded())

    def test_a_refusal_says_why_and_acts_on_nothing(self) -> None:
        for name, claimed, says in _REFUSED:
            with self.subTest(name):
                self.setUp()
                self.waits(claimed(self))
                before = self.pinned()

                ran = self.approves()

                self.assertIn(says, self.answered or "")
                self.assertEqual(_touched(self, ran), _UNTOUCHED)
                self.assertEqual(self.pinned(), before)

    def test_a_replaced_approval_is_not_proved(self) -> None:
        # Another road put a later round's approval in the place of the one
        # this run returned: that record is not this run's to prove or act
        # on, however valid the evidence it names, so the run is refused.
        self.waits(_settled(self))
        _replaces(self)
        before = self.pinned()

        ran = self.approves()

        self.assertIn(_NOT_WAITING, self.answered or "")
        self.assertEqual(_touched(self, ran), _UNTOUCHED)
        self.assertEqual(self.pinned(), before)

    def test_a_push_since_it_settled_refuses(self) -> None:
        # The claim names the current evidence exactly and it passed, but the
        # pull request has since moved to a head it says nothing about: the
        # evidence no longer proves current.
        self.waits(_settled(self))
        _world.pushes(self)
        before = self.pinned()

        ran = self.approves()

        self.assertIn(_NOT_CURRENT, self.answered or "")
        self.assertEqual(_touched(self, ran), _UNTOUCHED)
        self.assertEqual(self.pinned(), before)


class HeldProofTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """A proof nobody could read holds the approval, and one whose records moved while it was taken refuses it."""

    def test_an_unread_proof_holds_the_approval(self) -> None:
        # The pull request, or the thread the artifact is on, cannot be read:
        # that is no refusal, so nothing is verified, posted, or written, and
        # the verdict waits for a later tick, which proves it and hands the
        # issue on.
        for name, stops in _UNREAD:
            with self.subTest(name):
                self.setUp()
                self.waits(_settled(self))
                before = self.pinned()

                with stops(self):
                    ran = self.approves()

                self.assertEqual((self.answered, _touched(self, ran)), (None, _UNTOUCHED))
                self.assertEqual(self.pinned(), before)
                self.approves()
                self.assertEqual((self.answered, self.github.label_history), ("", [DOCUMENTING]))

    def test_records_moved_behind_the_proof_refuse_it(self) -> None:
        # Behind the approval's last read of its artifact another road settles
        # a later revision, repoints the issue, or puts another verdict in
        # place: the approval no longer rests on what the proof was taken
        # over, so it is refused, and nothing is verified, posted, or
        # relabeled. A comment that will not read behind it proves nothing,
        # and holds the approval instead.
        for name, road, says in _BEHIND_THE_PROOF:
            with self.subTest(name):
                self.setUp()
                self.waits(_settled(self))
                behind = _proof.behind_the_proof(self, road)

                with patch.object(self.github, ARTIFACT_REREAD, behind):
                    ran = self.approves()

                self.assertTrue(self._refused_with(says), self.answered)
                self.assertEqual(_touched(self, ran), _UNTOUCHED)

    def _refused_with(self, says: str | None) -> bool:
        """Whether the last proof refused saying `says`, or -- where `says` is None -- held instead."""
        if says is None:
            return self.answered is None
        return says in (self.answered or "")


if __name__ == "__main__":
    unittest.main()
