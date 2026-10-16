# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed head's announcement refused over records another road moved under its notice.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's run settled and proved ready, and while
the notice is posted another road repoints the issue at another pull request
and puts it back. The record of the `base_rebased` event, decided on that pull
request under the policy, is refused: movement read under the run, which is
invalidated there and then, before any proof reads the issue put back, and the
next direct finish routes the head with everything said once. Where another
road instead records a newer transaction beside the run and marks movement
under the run alone, the run is invalidated over that mark and the successor
left owed as written, unposted, for the next finish to answer.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import verification_records as _evidence_records
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
    settled_route_support as route,
)
from tests.workflow.interleaving import _RacesPastTheCall

_PR_NUMBER = "pr_number"

# The client's pull-request comment, the notice's post a case moves records under.
_PR_COMMENT = "pr_comment"

# Another pull request the issue is repointed at meanwhile.
_ANOTHER_PR = 43


class _Repointed:
    """Another road repointing issue #7 at `_ANOTHER_PR`, and putting it back before the issue is read again."""

    def __init__(self, case: route.SettledRouteCase) -> None:
        self._case = case
        self._recorded = None
        self.settled = None

    def moves(self) -> None:
        """Repoint the issue, keeping the run settled before it and the pull request it pointed at."""
        case = self._case
        self.settled = readings.pinned_records(case)[1]
        state = case.gh.read_pinned_state(case.issue)
        self._recorded = state.get(_PR_NUMBER)
        state.set(_PR_NUMBER, _ANOTHER_PR)
        case.gh.write_pinned_state(case.issue, state)

    def restores(self) -> None:
        """Put the pull request back, where the issue is still repointed."""
        if self._recorded is None:
            return
        state = self._case.gh.read_pinned_state(self._case.issue)
        state.set(_PR_NUMBER, self._recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)
        self._recorded = None

    def reads(self, live, *args, **kwargs):
        """`live`, the client's issue read, behind putting the pull request back."""
        self.restores()
        return live(*args, **kwargs)


class EventRecordMoveTest(route.SettledRouteCase, unittest.TestCase):
    """A refusal of the event's record over a moved publication invalidates the run it read moving."""

    def test_a_repointed_pr_invalidates_the_run(self) -> None:
        # The record is refused over the repointed pull request and the run
        # invalidated in that tick, nothing filed, the attempt standing; the
        # next direct finish routes the head with nothing current.
        head = self.lands_a_reviewed_rebase()
        settled.charges(self)
        repointed = _Repointed(self)
        posts = _RacesPastTheCall(self.gh.pr_comment, 1, repointed.moves)
        reads = partial(repointed.reads, self.gh.get_issue)
        with (
            patch.object(self.gh, _PR_COMMENT, posts),
            patch.object(self.gh, "get_issue", reads),
        ):
            self.assertEqual(self.finalizes(head, FinishRoad.PUBLICATION), FinishOutcome.REFUSED)
        repointed.restores()

        self.assert_retired_whole(repointed.settled)
        recorded = self.pinned_fields(readings.KEY_PENDING_PUSH, readings.KEY_ANNOUNCED_EVENT)
        self.assertEqual(recorded, (self.anchor, None))
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        self.assert_retired_whole(repointed.settled)
        self.assert_routed_once(head)
        settled.assert_charged_as_left(self)


class SuccessorUnderTheNoticeTest(route.SettledRouteCase, unittest.TestCase):
    """A successor another road records under the notice is left owed, whatever the run is invalidated over."""

    def test_the_successor_is_left_owed(self) -> None:
        # The finish before dies ahead of the announcement. While the next
        # one's notice is posted, another road records a newer transaction
        # beside the run and marks movement under the run's receipt alone.
        # The checkpoint is refused and the run invalidated over that mark,
        # but the successor, recorded behind the stop's writes, stands pending
        # as written and unposted: no last word is taken over it with the
        # run's movement. The finish behind it posts and settles that
        # successor and routes the head once, nothing run or charged again.
        head = self.lands_a_reviewed_rebase()
        settled.charges(self)
        run, successor = self._refused_beside_a_successor(head)

        self.assert_retired_whole(run, pending=successor)
        self.assertEqual(self.posted(successor), [])
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        answered = (readings.pinned_records(self)[1].receipt, self.posted(successor))
        self.assertEqual(answered, (successor.receipt, [successor.commands]))
        self.assert_routed_once(head)
        settled.assert_charged_as_left(self)

    def _refused_beside_a_successor(self, head: str) -> tuple:
        """Kill `head`'s finish ahead of its announcement and finish it again under the move; the run and successor.

        The second finish's notice is posted with the newer transaction
        recorded and the run's movement marked right behind it, and the
        checkpoint behind that notice is refused.
        """
        dies = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, dies)
        run = readings.pinned_records(self)[1]
        newer: list = []
        records = partial(self._records_beside, run, newer)
        with patch.object(self.gh, _PR_COMMENT, _RacesPastTheCall(self.gh.pr_comment, 1, records)):
            self.assertEqual(self.finalizes(head), FinishOutcome.REFUSED)
        return run, newer[0]

    def _records_beside(self, run, newer: list) -> None:
        """Record a newer transaction beside `run` into `newer`, then mark movement under `run`'s receipt alone."""
        newer.append(settled.records_a_newer_run(self))
        state = self.gh.read_pinned_state(self.issue)
        state.set(_evidence_records.EVIDENCE_HANDOFF, {"moved": run.receipt})
        self.gh.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
