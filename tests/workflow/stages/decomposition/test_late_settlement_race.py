# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What ends between the reconciliation that read it and the push itself.

A settled `single` taken past publication pushes from the settlement, and that
push reaches the transport directly rather than through the gated call every
other publication goes through. So the barrier that call makes has to be made
here too -- and the window it covers is the widest on any road: the pull
request was last read by the reconciliation, and the exemption, the identity,
the debt, the park persist and both checkout probes all run between that
reading and the push.

Nothing about an ending moves the branch. A pull request somebody merged or
closed in that window still has its branch exactly where the adjudication left
it, so the lease SUCCEEDS and the force-push moves terminal work -- a merge
commit's branch walked back onto the commits it merged. A close a poll latched
is the same answer one field over, and the issue object this tick is holding
still reads open, so the latch is the only thing that can answer for it.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from orchestrator.workflow.stages.implementing import (
    late_accepted as _late_accepted,
    late_push as _late_push,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_settlement_support import (
    GuardedLateCase,
)
from tests.workflow.stages.decomposition.late_test_support import (
    PUBLISHED_PR_NUMBER,
)
from tests.workflow.stages.decomposition.test_late_settlement_published import (
    PR_CLOSED,
    _PublishedVerdictMixin,
)

# The step one ending is raced past, and the transport it must never reach.
# `_standing_on` is the last thing the settlement does before the barrier, so
# hanging the ending on it reproduces the tightest window still left.
_STANDING_ON = "_standing_on"
_PUSHED = "_pushed"

# Every way the world can end in that window, named by the thing a poll on
# another worker does. Resolved on the case, so each reads as the one line it
# is rather than as a lambda bound before the case exists.
_ENDINGS = (
    "_merges_the_pull_request",
    "_closes_the_pull_request",
    "_closes_the_issue",
)

# What a pull request reads as once somebody reopens the one this settlement
# was refused over, which is the poll the refusal exists to leave room for.
_PR_OPEN = "open"


class _PublishedRaceCase(
    ObservedCloseCase, GuardedLateCase, _PublishedVerdictMixin,
):
    """One post-publication verdict, settled while the world moves under it."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self._seed_published()

    def _settles_while(self, arrives):
        """Settle with the world ending the instant the checkout is proved."""
        with patch.object(
            _late_accepted,
            _STANDING_ON,
            _RacesPastTheStep(_late_accepted._standing_on, arrives),
        ):
            return self._settles_watched()

    def _settles_watched(self):
        """Settle with the transport watched rather than seeded.

        Watched because what these cases pin down is whether it was REACHED
        at all: a push refused by its own lease would leave the very same
        record behind as one the barrier never let happen.
        """
        with patch.object(
            _late_push, _PUSHED, side_effect=_late_push._pushed,
        ) as transport:
            return self._settle(), transport

    def _merges_the_pull_request(self) -> None:
        published = self.github.get_pr(PUBLISHED_PR_NUMBER)
        published.merged = True
        published.state = PR_CLOSED

    def _closes_the_pull_request(self) -> None:
        self.github.get_pr(PUBLISHED_PR_NUMBER).state = PR_CLOSED

    def _closes_the_issue(self) -> None:
        """What a poll on another worker leaves behind, and all it leaves.

        The issue object this tick is holding still reads open, so the latch
        is the only reading that can answer for the window at all.
        """
        self._latch_close(_TEST_SPEC.slug, self.issue.number)


class PublishedEndingRaceTest(_PublishedRaceCase, unittest.TestCase):
    """A settlement may not push onto work that ended while it was writing."""

    def test_an_ending_in_the_window_pushes_nothing(self) -> None:
        for ending in _ENDINGS:
            with self.subTest(ending=ending):
                self.setUp()

                outcome, transport = self._settles_while(
                    getattr(self, ending),
                )

                transport.assert_not_called()
                self._assert_unpublished(outcome)

    def test_nothing_ending_still_publishes(self) -> None:
        # The other side, so the barrier is about the ending rather than about
        # this road having stopped publishing: with the world where the
        # reconciliation left it, the same settlement pushes and hands on.
        self.assertEqual(self._settle().disposition, _LateDisposition.SETTLED)

    def test_a_second_poll_answers_the_same_way(self) -> None:
        # The verdict and the approval a refusal leaves are durable, so this
        # road is re-entered on every poll until something moves. With the
        # ending still there poll two answers exactly as poll one did and
        # leaves the same record behind -- nothing published, nothing handed
        # on, and no second mention for a park already standing.
        self._settles_while(self._closes_the_pull_request)
        recorded = dict(self._pinned())
        posted = list(self.github.posted_comments)

        outcome = self._settle()

        self._assert_unpublished(outcome)
        self.assertEqual(dict(self._pinned()), recorded)
        self.assertEqual(self.github.posted_comments, posted)

    def test_a_reopened_publication_is_pushed_onto(self) -> None:
        # And the recovery the refusal was preserving that verdict for: with
        # the pull request open again, the durable verdict and the approval
        # beside it are what the next poll publishes on. Nothing is decided a
        # second time -- a human read this diff once, and neither it nor the
        # commit carrying it moved while the world did.
        self._settles_while(self._closes_the_pull_request)
        self.github.get_pr(PUBLISHED_PR_NUMBER).state = _PR_OPEN

        outcome, transport = self._settles_watched()

        transport.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)


if __name__ == "__main__":
    unittest.main()
