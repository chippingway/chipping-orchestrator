# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict a tick left waiting, finished by the later ticks that pick it up.

Evidence whose publication GitHub never confirmed stays owed across any number
of ticks, and the subject the verdict is about can move while it waits: the
verdict is held only while that subject stands, and dropped for a fresh
reviewer once it is proved to have moved. A change request already handed --
its feedback posted and anchored, and the write behind that down -- resumes
where its handoff stopped, the feedback never posted again: the relabel and
the launch a tick that died on the relabel left owed, or nothing at all where
the run ledger says the developer it was handed to was already launched.

The disposition itself, and the tick a verdict is returned on, are in
`test_review_disposition.py` beside this.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.stages.validating import (
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    test_review_disposition as _disposition,
)
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

# What moves a waiting approval's subject while its evidence is owed, and the
# verdict each leaves waiting: a push proves the subject moved, and a report
# nobody could read proves nothing either way.
_WHILE_OWED = (
    ("a push", _world.pushes, None),
    ("an unread report", lambda case: case.github.report_failures.unreadable.add(_world.PR), _disposition.APPROVED),
)

# Where a handed change request's handoff stopped, whether the developer it was
# handed to was launched before it did, and what the replay leaves: the
# developers it launches, every relabel, and the verdict waiting.
_HANDED = (
    ("on the relabel", False, (1, _disposition.HANDED_BACK, None)),
    ("past the launch", True, (0, (), None)),
)


class VerdictReplayTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A later tick finishes a waiting verdict only over what still stands, and hands a request over once."""

    def test_owed_evidence_waits_on_its_subject(self) -> None:
        # The publication's response is lost, so its evidence stays owed and
        # the approval waits. A push while it waits proves the verdict is about
        # work nobody is asking about: the replays drop it rather than wait on
        # evidence no settlement makes a review of the head there now, and the
        # transaction is left owed to the reconciliation. A report nobody
        # could read proves nothing, and the verdict keeps waiting.
        for move, road, waiting in _WHILE_OWED:
            with self.subTest(move):
                self.setUp()
                self.github.report_failures.lost.add(_world.PR)
                self.returns(_world.declared_run())
                road(self)

                self.finishes()
                self.finishes()

                pinned = self.pinned()
                self.assertEqual(
                    (
                        (pinned.get(_world.RETURNED_VERDICT) or {}).get(_disposition.VERDICT),
                        pinned.get(_world.PENDING_EVIDENCE) is not None,
                        pinned.get(_world.PARK_REASON),
                        self.github.label_history,
                    ),
                    (waiting, True, None, []),
                )

    def test_a_handed_request_resumes_its_handoff(self) -> None:
        # The relabel behind the write that handed the request over is
        # refused, so its feedback is posted and anchored and nothing launched.
        # The replay posts no feedback again: it relabels and launches the one
        # developer the request is owed -- or, where the run ledger was charged
        # past the count the request was handed at, launches nobody and
        # retires the verdict, that developer already having run.
        for stopped, launched, expected in _HANDED:
            with self.subTest(stopped):
                self.setUp()
                refused = patch.object(self.github, "set_workflow_label", side_effect=RuntimeError("label refused"))
                with refused, self.assertRaises(RuntimeError):
                    self.returns(_disposition.UNDECLARED_REQUEST)
                if launched:
                    self._charges_a_run()

                ran = self.finishes(_world.developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)

                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        tuple(self.github.label_history),
                        self.pinned().get(_world.RETURNED_VERDICT),
                    ),
                    expected,
                )
                self.assertEqual(len(_read.feedback_posts(self)), 1)

    def _charges_a_run(self) -> None:
        """The launch of the developer a handed request was owed, as its charge of the run ledger records it."""
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.AGENT_RUNS_USED, state.get(_world.AGENT_RUNS_USED) + 1)
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
