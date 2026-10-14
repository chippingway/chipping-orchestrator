# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed head's announcement whose event record is refused over a pull request repointed under it.

Every finish held to the dormant settled-evidence policy (`settled_finish_support`):
issue #7's run settled and proved ready, and while the notice is posted
another road repoints the issue at another pull request and puts it back.
The record of the `base_rebased` event, decided on that pull request, is
refused: movement read under the run, which is invalidated there and then,
and the next poll routes the head with everything said once.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall

_PR_NUMBER = "pr_number"

# Another pull request the issue is repointed at meanwhile.
_ANOTHER_PR = 43


class _Repointed:
    """Another road repointing issue #7 at `_ANOTHER_PR`, and putting it back before the issue is read again."""

    def __init__(self, case: support.CapturedRunCase) -> None:
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


class EventRecordMoveTest(settled.SettledRunCase, unittest.TestCase):
    """A refusal of the event's record over a moved publication invalidates the run it read moving."""

    def test_a_repointed_pr_invalidates_the_run(self) -> None:
        # The record is refused over the repointed pull request, and the run
        # is invalidated in that tick, before any proof would read the issue
        # put back; the next poll routes the head with nothing current.
        head = self.lands_a_reviewed_rebase()
        repointed = _Repointed(self)
        posts = _RacesPastTheCall(self.gh.pr_comment, 1, repointed.moves)
        reads = partial(repointed.reads, self.gh.get_issue)
        with (
            patch.object(self.gh, "pr_comment", posts),
            patch.object(self.gh, "get_issue", reads),
        ):
            self.finishes(head)
        repointed.restores()

        self._assert_invalidated(repointed.settled)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        self.recovers()

        self._assert_invalidated(repointed.settled)
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence and nothing current, its command run once."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual((self.runs(), self.developer.call_count), (1, 0))


if __name__ == "__main__":
    unittest.main()
