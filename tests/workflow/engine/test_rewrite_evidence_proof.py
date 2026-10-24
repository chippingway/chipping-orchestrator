# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's evidence proved again, its head held to the base it was replayed onto, and the last word.

The proof again reads the issue and pinned comment afresh, and a proof that
stopped at a reading nobody could take still answers with what the review and
report records say moved. The base is refused by where the head stands against
the tip its replay was recorded as made onto: gone elsewhere or unread holds,
and rewound under the head or never recorded defers. The last word reads the
landing only where it is asked to, and answers with the first movement and the
first hold side by side. None of them writes, runs, launches, or relabels
anything.
"""
from __future__ import annotations

import unittest

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine import rewrite_evidence_proof as _proof
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from tests.workflow.engine import (
    rewrite_captured_test_support as captured_support,
    rewrite_finish_moves as moves,
    verification_evidence_test_support as support,
)
from tests.workflow.observation_support import refuse_record

_HOLD = ReportEvidenceVerdict.HOLD

_DEFER = ReportEvidenceVerdict.DEFER

# The settled report re-read failing beside each of these, and what the proof
# answers: the unread report holds it, unless a record the comment carries
# moved, which defers it whatever went unread.
_BESIDE_AN_UNREAD_REPORT = (
    (moves.unmoved, _HOLD, "could not be re-read"),
    (moves.later_review, _DEFER, "another subject than the recorded review_subject"),
)

# Where the head stands against its recorded base tip, and what that refuses.
_STANDINGS = (
    (_BaseStanding.STANDING, None),
    (_BaseStanding.MOVED, (_HOLD, "the base moved after the rebased head was counted against it")),
    (_BaseStanding.UNREAD, (_HOLD, "the base the rebased head was counted against could not be read again")),
    (_BaseStanding.DROPPED, (_DEFER, "the base is no longer the tip the rebased head was replayed onto")),
    (_BaseStanding.UNPROVEN, (_DEFER, "the attempt recorded no base tip its replay was made onto")),
)

_EARLIER = ReportEvidence(_DEFER, "proved again and refused")

_UNREAD = "the issue or its pinned comment could not be read again to prove the evidence"


class ProofAgainTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """The binding proved again over what GitHub carries now."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)

    def test_an_unread_proof_still_hears_the_records(self) -> None:
        for moves_it, verdict, refusal in _BESIDE_AN_UNREAD_REPORT:
            with self.subTest(moved=moves_it.__name__):
                self.setUp()
                moves_it(self)
                self.gh.report_failures.unreadable.add(support.PR_NUMBER)

                found = self.asks(_proof.proves_again, self.landed(), self.captured.binding)

                self.assertEqual(found.verdict, verdict)
                self.assertIn(refusal, found.refusal)
                self.assert_dormant()


class BaseStandingTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """A landed head is held to the base tip its replay was recorded as made onto."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)

    def test_each_standing_earns_its_refusal(self) -> None:
        for standing, refused in _STANDINGS:
            with self.subTest(standing=standing):
                self.world.base = standing

                found = self.asks(_proof.standing_refusal, self.landed())

                answered = None if found is None else (found.verdict, found.refusal)
                self.assertEqual(answered, refused)
                self.assert_dormant()


class LastWordTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """The last word reads the landing only where asked, and answers with movement and a hold side by side."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)
        self.world.remote_answers = False
        self.world.checkout_head = support.SQUASHED_SHA

    def test_the_landing_is_read_where_asked(self) -> None:
        finish = self.landed()

        spared = self.asks(_proof.last_word, finish, landing=False)
        moved, held = self.asks(_proof.last_word, finish)

        self.assertEqual(spared, (None, None))
        self.assertEqual(
            (moved, held.refusal),
            (_proof.LEFT_THE_LANDING, "the remote branch the rebased head landed on could not be read again"),
        )
        self.assert_dormant()

    def test_an_earlier_verdict_is_read_first(self) -> None:
        finish = self.landed()
        binding = self.captured.binding

        moved, held = self.asks(_proof.last_word, finish, binding, earlier=_EARLIER)

        self.assertEqual((moved, held.holds), (_EARLIER, True))
        self.assert_dormant()


class RefusedReadingTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """A pinned comment a human's edit left refused is read again as one nobody could read.

    It reads back empty, so taken as a reading every record the binding rests
    on would have moved; refused, it proves nothing either way, and the route
    holds for a later tick, whose refresh refuses the issue before any route.
    """

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)
        self.world.base = _BaseStanding.STANDING

    def test_a_refused_record_holds(self) -> None:
        finish = self.landed()
        binding = self.captured.binding
        refuse_record(self.gh, self.issue.number)

        proved = self.asks(_proof.proves_again, finish, binding)
        moved, held = self.asks(_proof.last_word, finish, binding, landing=False)

        self.assertEqual((proved.verdict, proved.refusal), (_HOLD, _UNREAD))
        self.assertEqual((moved, held.refusal), (None, _UNREAD))
        self.assert_dormant()

if __name__ == "__main__":
    unittest.main()
