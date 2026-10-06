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

Where a verdict the park outlived waits, the tick settles in one guarded
commit that drops it. Another road putting its own verdict in that one's
place, or unparsing the comment, right ahead of that commit refuses it with
nothing written over that road's write; a run another road charged there is
kept beside it; and one GitHub took and lost the response to is settled once.
The reviewer the reply bought runs once whichever way.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import report_hold as _report_hold, review_verdicts as _verdicts
from tests.workflow.fixtures import _agent
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    resumed_verdict_test_support as _resumed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

_REVIEW_CAP = "review_cap"

# Each park a reply clears into a fresh round, and the reply that does.
_REPLIES = (
    (_REVIEW_CAP, "/orchestrator add-review-rounds 1"),
    ("reviewer_unrecorded", _resumed.CONTINUE),
)

# A fresh reviewer that returns no verdict, so its round parks and nothing else runs.
_UNDECIDED_REVIEWER = _agent(session_id="fresh-reviewer", last_message="Looked it over.")

# The run count another road charges up to right ahead of a settlement.
_CHARGED = 9


def _replaces_the_verdict(case) -> None:
    """Another road's newer verdict, of a later round, in place of the one `case` had waiting."""
    state = case.github.read_pinned_state(case.issue)
    waited = _verdicts.read_returned_verdict(state)
    newer = replace(waited, round_n=waited.round_n + 1)
    state.set(_world.RETURNED_VERDICT, newer.recorded())
    case.github.write_pinned_state(case.issue, state)


# Another road's write right ahead of the commit settling a bought round over
# a waiting verdict: its own verdict in that one's place, or the comment
# unparsed. Each refuses the settlement.
_AHEAD_OF_THE_SETTLEMENT = (
    ("another round's verdict", _replaces_the_verdict),
    ("an unparsed comment", _roads.unparses),
)


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


class SettledRoundTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """The tick a reply bought a round on settles a waiting verdict in one guarded commit, or writes nothing.

    Every case's road goes ahead of the first guarded commit the tick makes,
    which on these ticks is the settlement's own.
    """

    def test_a_write_ahead_of_the_settlement(self) -> None:
        # Another road writes right ahead of the commit settling the round:
        # the commit is refused, no reviewer runs, and the comment stays
        # exactly as that road left it.
        for name, road in _AHEAD_OF_THE_SETTLEMENT:
            with self.subTest(name):
                self.setUp()
                self._parks_beside_a_verdict()
                ahead = _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road))

                with ahead.patched():
                    ran = self.validates(**_disposed.ON_THE_HEAD)

                self.assertEqual((ran.call_count, self.pinned()), (0, self.left_behind))

    def test_another_roads_run_is_kept(self) -> None:
        # Another road charges a run right ahead of the commit settling the
        # round: the park is cleared and the verdict dropped beside it, its
        # run count kept, and the next tick runs the one reviewer the reply
        # bought.
        self._parks_beside_a_verdict()
        charges = _roads.Writes({_world.AGENT_RUNS_USED: _CHARGED})
        with _roads.AnotherRoadAhead(self, bool, charges).patched():
            settled = self.validates(**_disposed.ON_THE_HEAD).call_count
        charged = self.pinned()[_world.AGENT_RUNS_USED]
        left = (settled, self.parked()[:2], charged)

        ran = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]})

        self.assertEqual(
            (left, ran.call_count),
            ((0, ((None, False), None), _CHARGED), 1),
        )

    def test_a_lost_settlement_runs_one_round(self) -> None:
        # GitHub takes the commit settling the round and loses its response:
        # the park stands cleared and the verdict dropped, so the next tick
        # runs the one reviewer the reply bought, and the tick after runs none.
        self._parks_beside_a_verdict()
        with _roads.AnotherRoadAhead(self, bool, _roads.loses_the_responses).patched():
            settled = self.validates(**_disposed.ON_THE_HEAD).call_count
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        left = (settled, self.parked()[:2])

        reviewed = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]}).call_count
        again = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]}).call_count

        self.assertEqual(
            (left, reviewed, again),
            ((0, ((None, False), None)), 1, 0),
        )

    def _parks_beside_a_verdict(self) -> None:
        """An approval relying on no evidence left waiting beside a park a trusted `/orchestrator continue` answers."""
        _read.seeds_a_verdict(self, None)
        state = self.github.read_pinned_state(self.issue)
        state.set("awaiting_human", True)
        state.set("park_reason", "reviewer_unrecorded")
        self.github.write_pinned_state(self.issue, state)
        self.asks_to_continue(_resumed.CONTINUE)


if __name__ == "__main__":
    unittest.main()
