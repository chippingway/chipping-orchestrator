# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A park its correction's own malformed answer took, answered by a human's correction, end to end.

The park is said once and a quiet tick asks nothing of it. The human's reply
resumes the same session; that resume's own malformed answer earns a correction
of its own -- a run charged after the spent attempt, never the spent attempt
replenished -- whose park stops short of the replies written while those runs
were out, and the next resume delivers those replies alone.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from tests.support.fakes import FakeComment
from tests.workflow.fixtures import LABEL_READY
from tests.workflow.stages.decomposition import parked_decomposition_support as _parked

_FIELD = "decomposer_correction"

_CORRECTING = "every child needs its depends_on list; B needs A"

_CORRECTED_PARK = "after its one automatic correction"


class _LosesTheCorrectionsPark:
    """The whole-state writer, failing once on the park a runner's second launch -- its correction -- takes."""

    def __init__(self, write, runner: MagicMock) -> None:
        self._write = write
        self._runner = runner
        self.lost = False

    def __call__(self, issue, state):
        if not self.lost and self._runner.call_count == 2 and state.get("awaiting_human"):
            self.lost = True
            raise RuntimeError("502")
        return self._write(issue, state)


class CorrectedParkReplyTest(unittest.TestCase, _parked._ParkedDecompositionCase):
    """A failed correction's park, a quiet tick, a human's correction, and the replies written behind it."""

    def test_a_human_correction_resumes_its_session(self) -> None:
        spent = self._parked_quietly()
        reply = self._answered_by_a_correction(spent)
        runner = _parked.decomposer_run()

        self._tick(runner)

        prompt, session = _parked.launched(runner)
        self.assertEqual(session, _parked.PARKED_SESSION)
        self.assertIn(_parked.LATER_REPLY, prompt, "the replies written meanwhile are the next resume's")
        self.assertNotIn(reply.body, prompt, "the reply its correction answered is not delivered again")
        self.assertEqual(self.github.workflow_label(self.issue), LABEL_READY)

    def test_a_lost_park_keeps_the_session(self) -> None:
        # The second malformed answer's park posts its notice and loses its
        # write, with replies written while those runs were out: the next tick
        # records the park over that notice, bounded short of those replies,
        # and resumes the saved session on them rather than reading them as an
        # edit that retires it.
        reply = self._loses_the_second_park()
        recovery = _parked.decomposer_run()

        self._tick(recovery)

        prompt, session = _parked.launched(recovery)
        self.assertEqual(session, _parked.PARKED_SESSION)
        self.assertIn(_parked.LATER_REPLY, prompt)
        self.assertNotIn(reply.body, prompt)
        self.assertEqual(self._corrected_parks(), 2, "the lost park is not said again")
        drift_notices = [body for body in self._said() if _parked.DRIFT_NOTICE in body]
        self.assertEqual(drift_notices, [], "no reply is read as an edit")

    def _loses_the_second_park(self) -> FakeComment:
        """A human's correction whose resume and its correction answer malformed, their park losing its write."""
        self._park()
        reply = self._reply(_CORRECTING)
        answering = MagicMock(side_effect=_parked.AnsweredWhileOut(self._reply, _parked.INVALID_MANIFEST))
        parking = _LosesTheCorrectionsPark(self.github.write_pinned_state, answering)
        with patch.object(self.github, "write_pinned_state", side_effect=parking), self.assertRaises(RuntimeError):
            self._tick(answering)
        self.assertTrue(parking.lost)
        return reply

    def _parked_quietly(self) -> dict:
        """The park a correction's malformed answer took, and a quiet tick behind it: the spent attempt."""
        self._park()
        quiet = _parked.decomposer_run()
        self._tick(quiet)
        quiet.assert_not_called()
        self.assertEqual(self._corrected_parks(), 1)
        return self._pinned()[_FIELD]

    def _answered_by_a_correction(self, spent: dict) -> FakeComment:
        """A human's correction, resumed on the parked session, whose malformed answer earns a correction of its own.

        A reply is written while each of those runs is out; the park the
        second malformed answer takes stops short of them.
        """
        reply = self._reply(_CORRECTING)
        answering = MagicMock(side_effect=_parked.AnsweredWhileOut(self._reply, _parked.INVALID_MANIFEST))
        self._tick(answering)
        resumed, corrected = answering.call_args_list
        self.assertEqual(resumed.kwargs["options"].resume_session_id, _parked.PARKED_SESSION)
        self.assertEqual(corrected.kwargs["options"].resume_session_id, _parked.PARKED_SESSION)
        self.assertIn(reply.body, resumed.args[1])
        self.assertIn("> child 0 missing depends_on", corrected.args[1])
        self._assert_parked_short_of(reply, spent)
        return reply

    def _assert_parked_short_of(self, reply: FakeComment, spent: dict) -> None:
        """The second park stands on `reply`, over a fresh attempt charged above the spent one's floor, said once."""
        parked = self._pinned()
        attempt = parked[_FIELD]
        self.assertEqual(parked["last_action_comment_id"], reply.id)
        self.assertGreater(attempt["source"]["ordinal"], spent["floor"])
        self.assertEqual(attempt["stage"], "exhausted")
        self.assertEqual(self._corrected_parks(), 2)

    def _corrected_parks(self) -> int:
        """How many notices on the thread are parks a correction's own answer took."""
        return sum(_CORRECTED_PARK in body for body in self._said())


if __name__ == "__main__":
    unittest.main()
