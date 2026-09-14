# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a conflict-stage replay records about the commit it replaced.

The two facts a rebase destroys: the head the branch was standing on, and the
fork point that head's contribution was read over. Neither survives the replay,
so the one caller that runs one reads them while the branch still has them and
carries them across. No other caller may build this record, because no other
knows what the commit it is publishing is -- which is why what a crash leaves
recoverable is the permission the rebase persists, not a reading of the branch.

Handed to the size gate they are what lets a change a human already adjudicated
be recognized in the object that replaced it. Handed in PARTIAL they would be
evidence no later reader could check, so an end nothing could name is answered
with no evidence at all rather than with a claim that has a hole in it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import rewrite_values as _rewrite_values
from orchestrator.workflow.stages.conflicts import (
    evidence as _evidence,
    models as _models,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import (
    _FAKE_WT,
    _TEST_SPEC,
    FORK_POINT_SHA,
    REPLAYED_FORK_POINT_SHA,
)
from tests.workflow.stages.conflicts.replay_test_support import (
    ADJUDICATED_HEAD,
    CONFLICT_PR,
    REPLAY_FORK_POINTS,
    REPLAYED_HEAD,
)

FORK_POINT = "_fork_point"

# Every reading one replay's evidence rests on, with a single end unread.
_UNNAMEABLE_ENDS = MappingProxyType({
    "a head nothing could read": {"head": ""},
    "a fork point the replay left behind": {
        "forks": {REPLAYED_HEAD: REPLAYED_FORK_POINT_SHA},
    },
    "a fork point the replay landed on": {
        "forks": {ADJUDICATED_HEAD: FORK_POINT_SHA},
    },
    "a replayed commit nothing could read": {"rebased": ""},
    "a pull request that is no identity": {"pr_number": 0},
})


class ReplayProvenanceTest(unittest.TestCase):
    """What a clean rebase tells the gate about the commit it replaced."""

    def test_the_replayed_head_is_also_the_lease(self) -> None:
        # This stage publishes only from a checkout proved in sync with its
        # remote, or ahead of a pull-request head it read and validated, so
        # the commit being replayed IS the commit the force-push replaces.
        # The squash seam is where those two really part.
        rewritten = self._rewritten()

        self.assertEqual(rewritten.from_sha, ADJUDICATED_HEAD)
        self.assertEqual(rewritten.lease, ADJUDICATED_HEAD)
        self.assertEqual(rewritten.to_sha, REPLAYED_HEAD)

    def test_two_contributions_over_two_bases(self) -> None:
        # The one thing a rebase changes about a contribution: which commit
        # the diff a reviewer would be handed is taken from. Read over a
        # single base, one of the two ends would be compared against a fork
        # point its branch has already left.
        rewritten = self._rewritten()

        self.assertEqual(rewritten.from_base_sha, FORK_POINT_SHA)
        self.assertEqual(rewritten.to_base_sha, REPLAYED_FORK_POINT_SHA)

    def test_the_publication_scopes_the_claim(self) -> None:
        rewritten = self._rewritten()

        self.assertEqual(rewritten.kind, _rewrite_values.LateRewriteKind.CONFLICT_REBASE)
        self.assertEqual(rewritten.pr_number, CONFLICT_PR)
        self.assertEqual(
            rewritten.source_stage, WorkflowLabel.RESOLVING_CONFLICT,
        )

    def test_an_end_nothing_named_presents_nothing(self) -> None:
        # A permit is granted on the whole of this record and refused the
        # moment one field cannot be checked, so a partial claim would spend
        # two fingerprints to reach the answer already known here -- and
        # would hide the record a crashed grant left, which is what a caller
        # with no evidence of its own is answered from instead.
        for case, unread in _UNNAMEABLE_ENDS.items():
            with self.subTest(case=case):
                self.assertIsNone(self._rewritten(**unread))

    def _rewritten(
        self,
        *,
        head: str = ADJUDICATED_HEAD,
        forks=REPLAY_FORK_POINTS,
        rebased: str = REPLAYED_HEAD,
        pr_number: int = CONFLICT_PR,
    ):
        """The evidence one replay hands in, over the fork points it read."""
        context = _models._ConflictContext(
            None, _TEST_SPEC, None, PinnedState(state_data={}),
        )
        with seam_patch(
            FORK_POINT,
            lambda spec, worktree, revision: forks.get(revision, ""),
        ):
            return _evidence._rewritten(
                context, _FAKE_WT,
                _evidence._replayed(_TEST_SPEC, _FAKE_WT, head),
                rebased, pr_number,
            )


if __name__ == "__main__":
    unittest.main()
