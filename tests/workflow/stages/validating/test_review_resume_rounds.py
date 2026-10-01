# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A round a reply bought is run, whatever comment another road posts while the report hold stops it.

Through `review_resume.settles_a_bought_round` on the `workflow:validating`
tick the report hold stops: a grant of rounds on the review cap, or a
`/orchestrator continue` on a reviewer-side park, during whose tick another
road posts a comment of its own. One naming nobody is no park, and the
reply's clear lands in that tick. One naming the human a park waits on cannot
be told from a park's notice, so that tick writes nothing, the park standing,
and the next answers the reply again. Either way the next tick runs the
reviewer the reply bought, and the issue is never left waiting on the park the
reply answered.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import report_hold as _report_hold
from tests.workflow.fixtures import _agent
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    resumed_verdict_test_support as _resumed,
    review_verdict_test_support as _world,
)

_REVIEW_CAP = "review_cap"

# Each park a reply clears into a fresh round, and the reply that does.
_REPLIES = (
    (_REVIEW_CAP, "/orchestrator add-review-rounds 1"),
    ("reviewer_unrecorded", _resumed.CONTINUE),
)

# A fresh reviewer that returns no verdict, so its round parks and nothing else runs.
_UNDECIDED_REVIEWER = _agent(session_id="fresh-reviewer", last_message="Looked it over.")


class BoughtRoundTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """The reviewer a reply bought runs by the next tick, however another road's comment reads."""

    def test_a_reply_outlives_another_roads_comment(self) -> None:
        # The comment names nobody: the tick the hold stops lands the clear,
        # and the next runs the reviewer. It names the human a park waits on,
        # as a park's notice does: that tick writes nothing, the park still
        # standing, and the next answers the reply again -- the grant made
        # again, or the continue -- and runs the reviewer.
        for (reason, reply), addressed in product(_REPLIES, (False, True)):
            with self.subTest(reason, addressed=addressed):
                self.setUp()
                self._parks(reason, reply)

                with patch.object(
                    _report_hold,
                    "_report_holds_the_review",
                    side_effect=partial(self._holds_behind_a_comment, addressed),
                ):
                    ran = self.validates(**_disposed.ON_THE_HEAD)
                held = (ran.call_count, self.parked()[0][1])

                ran = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]})

                self.assertEqual((held, ran.call_count), ((0, addressed), 1))

    def _parks(self, reason: str, reply: str) -> None:
        """A park for `reason` with no verdict waiting, and the trusted `reply` that clears it into a round."""
        state = self.github.read_pinned_state(self.issue)
        state.set("awaiting_human", True)
        state.set("park_reason", reason)
        if reason == _REVIEW_CAP:
            state.set("review_round", config.MAX_REVIEW_ROUNDS)
        self.github.write_pinned_state(self.issue, state)
        self.asks_to_continue(reply)

    def _holds_behind_a_comment(self, addressed: bool, *_asked) -> bool:
        """The report hold stopping the round, behind which another road posts a comment of its own.

        One naming the human a park waits on where `addressed` says so, as a
        park's notice does, and one naming nobody otherwise.
        """
        state = self.github.read_pinned_state(self.issue)
        words = "the pull request is still open."
        _comments._post_issue_comment(
            self.github, self.issue, state, f"{config.HITL_MENTIONS} {words}" if addressed else words,
        )
        self.github.write_pinned_state(self.issue, state)
        return True


if __name__ == "__main__":
    unittest.main()
