# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the evidence reconciliation settles, and how every crash window replays.

The crash windows are the point of the transaction, so each is written as the
place a process can die: after GitHub accepted an artifact whose response never
came back, after the artifact landed and before the settling write, and after
the settlement landed with the record somehow still standing. Each is replayed
by running the reconciliation again over the comment the first run persisted,
and each has to end with one artifact on the thread, one current record, and
the transaction's receipt as the handoff.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_record_fields as _fields,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support

_GITHUB_LOG = "orchestrator.github"

_WARNING = "WARNING"

_LEVEL = "INFO"

_FAILED = 1

# The key another route's write fills the pinned comment with.
_FILLER = "filler"


def _history(case) -> list[tuple]:
    """Each retired record by receipt and why it was retired, oldest first."""
    return [
        (entry.receipt, entry.retired)
        for entry in _settlement.read_evidence_history(case.state)
    ]


# Every move after which a recorded transaction can never settle: its pull
# request ended; a later transaction was recorded past it and since dropped,
# which only the floor its record raised remembers; and a floor gone, so nobody
# can say which revisions were spent.
_NEVER_SETTLES = (
    ("the pull request ended", lambda case, _pending: setattr(case.pull_request, "state", "closed")),
    ("a later revision was spent", lambda case, pending: case.state.set(
        _records.REVISION_FLOOR, pending.revision + 1,
    )),
    ("the floor is gone", lambda case, _pending: case.state.data.pop(_records.REVISION_FLOOR)),
)


def _fills_the_comment(case, _landed) -> None:
    """Fill the pinned comment to its limit with a field of its own, as another road would."""
    filling = case.gh.read_pinned_state(case.issue)
    filling.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filling.data))
    filling.set(_FILLER, "y" * room)
    case.gh.write_pinned_state(case.issue, filling)


# What a human can do to a landed artifact before its settlement.
_CHANGED_MEANWHILE = (
    ("edited", lambda _case, landed: setattr(landed, "body", "Tests passed, trust me.")),
    ("deleted", lambda case, landed: case.pull_request.issue_comments.remove(landed)),
)


class SettledEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A proved transaction publishes once, becomes current, and keeps the earlier as history."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_a_proved_transaction_settles(self) -> None:
        pending = self.record()

        self.assertFalse(self.reconcile())

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(
            [(found.receipt, found.content_revision) for found in self.artifacts()],
            [(pending.receipt, current.content_revision)],
        )
        self.assertEqual(
            (current.binding, current.passed), (pending.binding, True),
        )
        self.assertEqual(
            _settlement.read_evidence_handoff(self.state),
            _records.EvidenceHandoff(
                receipt=pending.receipt,
                pr_number=support.PR_NUMBER,
                revision=pending.revision,
                target_head=support.TESTED_SHA,
                settled_under=support.LABEL_VALIDATING,
            ),
        )
        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        # Tracked as ours, so the artifact never reads back as a human's feedback.
        self.assertIn(current.comment_id, self.state.get(support.LEDGER))

    def test_a_settled_issue_owes_nothing(self) -> None:
        self.record()
        self.reconcile()
        writes = self.gh.write_state_calls

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(self.gh.write_state_calls, writes)

    def test_later_evidence_supersedes(self) -> None:
        # A reviewer's account of a failed command is evidence too, and stays
        # actionable as the current record; the passing run before it is
        # history, not relabelled.
        first = self.record()
        self.reconcile()
        second = self.record(
            self.binding(source=EvidenceSource.REVIEWER_REPORTED), exit_status=_FAILED,
        )

        self.reconcile()

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(
            [found.artifact_revision for found in self.artifacts()],
            [first.revision, second.revision],
        )
        self.assertEqual((current.receipt, current.passed), (second.receipt, False))
        self.assertEqual(
            _history(self), [(first.receipt, _records.Retirement.SUPERSEDED)],
        )


class ReplayedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Every window a process can die in replays to one artifact and one settlement."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.posts = self.gh._post_verification_artifact
        self.meanwhile = None

    def test_an_accepted_post_whose_response_was_lost(self) -> None:
        self.gh.report_failures.lost.add(support.PR_NUMBER)
        with self.assertLogs(_GITHUB_LOG, _WARNING):
            held = self.reconcile()
        self.gh.report_failures.lost.clear()

        replayed = self.reconcile()

        self.assertEqual((held, replayed), (True, False))
        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_current_evidence(self.state).receipt,
            self.pending.receipt,
        )

    def test_a_settling_write_that_never_landed(self) -> None:
        with patch.object(
            self.gh, "write_pinned_state", side_effect=RuntimeError("write lost"),
        ), self.assertRaises(RuntimeError):
            self.reconcile()

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_evidence_handoff(self.state).receipt,
            self.pending.receipt,
        )

    def test_a_record_its_own_handoff_settled(self) -> None:
        # The settlement landed; a record standing beside its own handoff is
        # dropped rather than published a second time or moved into history.
        self.reconcile()
        self.state.set(_records.PENDING_EVIDENCE, _fields.pending_object(self.pending))
        self.gh.write_pinned_state(self.issue, self.state)

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        self.assertEqual(_history(self), [])

    def test_a_comment_filled_during_the_post(self) -> None:
        # Another road fills the pinned comment with a field this settlement
        # does not own while the artifact is posted: nothing past the limit is
        # written, the transaction stays owed, and once the room is back the
        # replay finds the artifact by its receipt and settles it.
        self.meanwhile = _fills_the_comment
        with patch.object(
            self.gh, "_post_verification_artifact", self.posts_then,
        ), self.assertLogs(support.WORKFLOW_LOG, "ERROR"):
            self.assertFalse(self.reconcile())

        filled = self.gh.read_pinned_state(self.issue)
        self.assertLessEqual(len(pinned_state_body(filled.data)), MAX_PINNED_BODY)
        self.assertEqual(_record_state.read_pending_evidence(filled), self.pending)
        self.assertIsNone(_settlement.read_current_evidence(filled))

        filled.data.pop(_FILLER)
        self.gh.write_pinned_state(self.issue, filled)
        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_current_evidence(self.state).receipt, self.pending.receipt,
        )

    def test_an_artifact_changed_during_the_post(self) -> None:
        # Edited or deleted by a human after the post landed and before the
        # settlement: nothing is declared current over an artifact the pull
        # request no longer shows, and the transaction stays owed.
        for moved, moves in _CHANGED_MEANWHILE:
            with self.subTest(moved=moved):
                self.setUp()
                self.meanwhile = moves
                with patch.object(
                    self.gh, "_post_verification_artifact", self.posts_then,
                ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.reconcile())
                    self.assertIn(
                        "no longer the one this transaction posted", support.logged_refusal(logged),
                    )

                persisted = self.gh.read_pinned_state(self.issue)
                self.assertIsNone(_settlement.read_current_evidence(persisted))
                self.assertEqual(_record_state.read_pending_evidence(persisted), self.pending)

    def posts_then(self, pull_request, body: str):
        """Land the artifact, then let `meanwhile` move what it landed on before the settlement."""
        landed = self.posts(pull_request, body)
        self.meanwhile(self, landed)
        return landed


class RetiredEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What can never settle is retired, never published and never parked."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_what_can_never_settle_is_abandoned(self) -> None:
        for moved, moves in _NEVER_SETTLES:
            with self.subTest(moved=moved):
                self.setUp()
                pending = self.record()
                moves(self, pending)
                self.gh.write_pinned_state(self.issue, self.state)

                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
                    self.assertFalse(self.reconcile())

                self.assertEqual(
                    _history(self), [(pending.receipt, _records.Retirement.ABANDONED)],
                )
                self.assertEqual(self.artifacts(), [])
                self.assertFalse(_record_state.carries_pending_evidence(self.state))

    def test_an_unreadable_record_is_dropped(self) -> None:
        self.state.set(_records.PENDING_EVIDENCE, {"receipt": "issue-7-verification-1"})
        self.gh.write_pinned_state(self.issue, self.state)

        with self.assertLogs(support.WORKFLOW_LOG, "ERROR"):
            self.assertFalse(self.reconcile())

        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        self.assertFalse(self.state.get("awaiting_human"))
        self.assertEqual(self.artifacts(), [])

    def test_a_restored_record_is_dropped_once(self) -> None:
        # Recorded, then replaced by a later one that settled -- a restored
        # comment is the only way back to it. Publishing it would put an older
        # run over a newer one, and history already indexes it as abandoned:
        # a second entry at its revision is an index nobody can read.
        stale = self.record()
        restored = self.gh.pinned_data(support.ISSUE_NUMBER)[_records.PENDING_EVIDENCE]
        newer = self.record()
        self.reconcile()
        self.state.set(_records.PENDING_EVIDENCE, restored)
        self.gh.write_pinned_state(self.issue, self.state)

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
            self.assertFalse(self.reconcile())

        self.assertEqual(_history(self), [(stale.receipt, _records.Retirement.ABANDONED)])
        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        self.assertEqual(
            _settlement.read_current_evidence(self.state).receipt, newer.receipt,
        )
        self.assertEqual(len(self.artifacts()), 1)

    def test_a_refused_carry_takes_its_approval(self) -> None:
        # A transaction carrying the run onto a head it did not run on, owed
        # to a pull request that stands elsewhere: its proof refuses, and
        # nothing a later route does makes it answer again, so it is abandoned
        # and the approval it was recorded for retired with it -- its subject
        # written null. A pull request nobody could read holds it owed for
        # the retry; and a run on the head it answers for, refused the same
        # way, stays owed for the route that answers it.
        for name, binding, unread, abandoned in (
            ("a carry refused", self.binding().retargeted(support.SQUASHED_SHA), (), True),
            ("a carry unread", self.binding().retargeted(support.SQUASHED_SHA), (support.PR_NUMBER,), False),
            ("a fresh run refused", self.binding(), (), False),
        ):
            with self.subTest(name):
                self.setUp()
                self.state.set(_review_subjects.APPROVED_SUBJECT, self.subject.recorded())
                self.record(binding)
                self.moves_the_head(support.REBASED_SHA)
                for number in unread:
                    self.gh.pulls.pop(number)

                self.assertEqual(self.reconcile(), bool(unread))

                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(self.state) is None,
                        bool(_history(self)),
                        self.state.get(_review_subjects.APPROVED_SUBJECT) is None,
                    ),
                    (abandoned, abandoned, abandoned),
                )
                self.assertEqual(self.artifacts(), [])

    def test_a_retirement_the_comment_cannot_carry(self) -> None:
        # Another route filled the comment after the record was accepted: the
        # history entry does not fit, so nothing is written and it stays owed.
        pending = self.record()
        self.pull_request.state = "closed"
        self.state.set(_FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(self.state.data))
        self.state.set(_FILLER, "y" * room)
        self.gh.write_pinned_state(self.issue, self.state)
        writes = self.gh.write_state_calls

        with self.assertLogs(support.WORKFLOW_LOG, "ERROR") as logged:
            self.assertFalse(self.reconcile())
            self.assertIn("no room", support.logged_refusal(logged))

        self.assertEqual(self.gh.write_state_calls, writes)
        self.assertEqual(_record_state.read_pending_evidence(self.state), pending)


class RecordedMeanwhileTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A retirement never writes away a transaction another road recorded meanwhile."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.reads = self.gh.get_pr
        self.meanwhile: list[_records.PendingEvidence] = []

    def test_a_transaction_recorded_meanwhile_is_kept(self) -> None:
        # Recorded after this tick read the comment: while the pull request it
        # finds ended is read, or before the guard drops a record nobody can
        # read. The retirement is composed over the comment as it stands, so
        # it stands down rather than erase the newer record or lower the floor.
        windows = (self.records_during_the_pull_request_read, self.records_before_the_guard)
        for window in windows:
            with self.subTest(window=window.__name__):
                self.setUp()
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    window()
                    self.assertIn("moved since this tick read it", support.logged_refusal(logged))

                persisted = self.gh.read_pinned_state(self.issue)
                newer = self.meanwhile[0]
                self.assertEqual(_record_state.read_pending_evidence(persisted), newer)
                self.assertEqual(persisted.get(_records.REVISION_FLOOR), newer.revision)
                self.assertEqual(self.artifacts(), [])

    def records_during_the_pull_request_read(self) -> None:
        """Owe evidence to an ended pull request, and record newer evidence as it is read."""
        self.record()
        self.pull_request.state = "closed"
        with patch.object(self.gh, "get_pr", self.reads_then_records):
            self.assertFalse(self.reconcile())

    def records_before_the_guard(self) -> None:
        """Owe a record nobody can read, and record newer evidence once the tick read it."""
        self.state.set(_records.PENDING_EVIDENCE, {"receipt": "issue-7-verification-1"})
        self.state.set(_records.REVISION_FLOOR, 1)
        self.gh.write_pinned_state(self.issue, self.state)
        tick = self.gh.read_pinned_state(self.issue)
        self.records_elsewhere()
        self.assertFalse(self.reconcile(tick))

    def reads_then_records(self, number: int):
        """Read the pull request, then let another road record newer evidence."""
        found = self.reads(number)
        self.records_elsewhere()
        return found

    def records_elsewhere(self) -> None:
        """Record a transaction over another road's own reading of the comment."""
        elsewhere = self.gh.read_pinned_state(self.issue)
        self.meanwhile.append(self.record(onto=elsewhere))


class SubjectMovedMeanwhileTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A settlement is composed over the comment read behind its proof, never over the reading before it."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.rereads = self.gh.reread_report_location
        self.calls = 0
        self.moves = None

    def test_a_subject_moved_during_the_proof_is_kept(self) -> None:
        # While the settlement's proof re-reads the developer report -- the
        # second reading this tick, behind the one ahead of the post -- another
        # road removes the review subject the evidence answers for, or records
        # the approval evidence carried across a squash answers through. The
        # comment read behind the proof no longer carries what was proved: the
        # move is kept, nothing is declared current, and the transaction stays
        # owed for the next tick to prove over what the comment carries then.
        for record, moves in (
            (_review_subjects.REVIEW_SUBJECT, self.removes_the_review_subject),
            (_review_subjects.APPROVED_SUBJECT, self.records_an_approval),
        ):
            with self.subTest(record=record):
                self.setUp()
                self.moves = moves
                with patch.object(
                    self.gh, "reread_report_location", self.rereads_then_moves,
                ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.reconcile())
                    self.assertIn(f"{record} moved since this tick read it", support.logged_refusal(logged))

                persisted = self.gh.read_pinned_state(self.issue)
                self.assertEqual(persisted.carries(record), record == _review_subjects.APPROVED_SUBJECT)
                self.assertIsNone(_settlement.read_current_evidence(persisted))
                self.assertEqual(_record_state.read_pending_evidence(persisted), self.pending)
                self.assertEqual(len(self.artifacts()), 1)

    def removes_the_review_subject(self, state) -> None:
        """Another road's reading of the comment, the review subject gone from it."""
        state.data.pop(_review_subjects.REVIEW_SUBJECT)

    def records_an_approval(self, state) -> None:
        """Another road's reading of the comment, an approval of the subject recorded on it."""
        state.set(_review_subjects.APPROVED_SUBJECT, self.subject.recorded())

    def rereads_then_moves(self, *asked, **named):
        """Re-read the report, and on the settlement's reading let another road move a subject on the comment."""
        found = self.rereads(*asked, **named)
        self.calls += 1
        if self.calls == 2:
            elsewhere = self.gh.read_pinned_state(self.issue)
            self.moves(elsewhere)
            self.gh.write_pinned_state(self.issue, elsewhere)
        return found


if __name__ == "__main__":
    unittest.main()
