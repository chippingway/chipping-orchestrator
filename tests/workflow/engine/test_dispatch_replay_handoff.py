# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pending auto-rebase replay beside the live adjudication of it, answered ahead of the anchor hold.

Issue #7 is on `workflow:decomposing` with the attempt an auto rebase pinned
and the live generation the size gate froze over that attempt's replay. The
dispatcher holds every handler behind a standing anchor, and under this label
its answer is the stranded park -- one a human cannot act on by relabelling,
since the adjudication's own guard puts the label straight back. So a pair
whose two records describe one replay is handed over first, whatever left it
standing, and the adjudication's handler runs on the same tick; anything else
is held with a park that says what a human has to reconcile instead, and an
operator's hard-skip has nothing handed over at all.
"""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import issue_processing as _issue_processing, stage_targets as _stage_targets
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.engine import rewrite_takeover_test_support as support
from tests.workflow.fixtures import _TEST_SPEC

# The attempt as a handoff leaves it: every member blanked rather than removed.
_RETIRED = dict.fromkeys(support.ATTEMPT_KEYS)

# The operator's control label that keeps everything but a recorded close off
# an issue.
PAUSED_LABEL = "paused"

# What the stranded park asks for beside an adjudication, and the instruction
# it may not give there.
_RECONCILE = "the adjudication keeps its label"
_PUT_BACK = "Put the issue back on the stage"


class _HandoffDispatchCase(unittest.TestCase):
    """One dispatch of issue #7, its `decomposing` handler watched and its checkout on disk."""

    def setUp(self) -> None:
        self.checkout = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-replay-handoff-")))

    def _dispatches(self, world: support.TakeoverWorld) -> MagicMock:
        """Route issue #7 the way a tick does; the handler it reached, as a mock."""
        owner_name, named = _stage_targets._STAGE_HANDLER_TARGETS[WorkflowLabel.DECOMPOSING]
        dispatched = MagicMock()
        with patch.object(importlib.import_module(owner_name), named, dispatched), patch.object(
            _worktree_paths, "_worktree_path", MagicMock(return_value=self.checkout),
        ):
            _issue_processing._route_issue_to_handler(
                world.github, _TEST_SPEC, world.issue, world.github.workflow_label(world.issue),
            )
        return dispatched


class StrandedPairTest(_HandoffDispatchCase):
    """A pair an earlier build stranded is handed over, and its adjudication runs."""

    def test_the_adjudication_runs_past_the_handoff(self) -> None:
        # The attempt and the park it left go together, nothing is said again,
        # and the round and the watermark are where the rebase left them.
        world = support.TakeoverWorld.seeded(**support.STRANDED, **support.STANDING)

        self._dispatches(world).assert_called_once()

        durable = world.pinned()
        self.assertEqual(world.standing(support.ATTEMPT_KEYS), _RETIRED)
        self.assertEqual(world.standing(support.UNPARKED), dict(support.UNPARKED))
        self.assertEqual(world.standing(support.STANDING), dict(support.STANDING))
        self.assertEqual(durable[support.KEY_REPLAY], support.REPLAY)
        self.assertEqual(world.github.posted_comments, [])

    def test_an_unlanded_handoff_holds_the_tick(self) -> None:
        # The write went out and its answer was lost: nothing runs over a
        # comment nobody can vouch for, and the next tick finds the handoff
        # landed and dispatches the adjudication.
        world = support.TakeoverWorld.seeded(**support.STRANDED)
        world.github.pinned_failures.lost.add(support.ISSUE)

        self._dispatches(world).assert_not_called()
        world.github.pinned_failures.lost.discard(support.ISSUE)
        self._dispatches(world).assert_called_once()

        self.assertEqual(world.standing(support.ATTEMPT_KEYS), _RETIRED)
        self.assertEqual(world.github.posted_comments, [])


class HeldPairTest(_HandoffDispatchCase):
    """What the dispatcher does not hand over."""

    def test_a_hard_skip_hands_nothing_over(self) -> None:
        # An operator's `paused` keeps everything but a recorded close off the
        # issue, the handoff's write included, and the hold releases for it.
        world = support.TakeoverWorld.seeded(**support.STRANDED)
        world.issue.labels.append(FakeLabel(PAUSED_LABEL))
        seeded = world.pinned()

        self._dispatches(world).assert_not_called()

        self.assertEqual((world.pinned(), world.github.write_state_calls), (seeded, 0))

    def test_the_park_asks_for_the_record(self) -> None:
        # Records that describe different work are held, with a route a human
        # can take: the park asks for the record, not for the label back.
        world = support.TakeoverWorld.seeded(late_source_stage="workflow:validating")

        self._dispatches(world).assert_not_called()

        durable = world.pinned()
        notices = [body for number, body in world.github.posted_comments if number == support.ISSUE]
        self.assertEqual(durable[support.KEY_PENDING_PUSH], support.ANCHOR)
        self.assertIsNone(durable.get(support.KEY_REPLAY))
        self.assertEqual(world.standing(support.STRANDED), dict(support.STRANDED))
        self.assertEqual(len(notices), 1)
        self.assertIn(_RECONCILE, notices[0])
        self.assertNotIn(_PUT_BACK, notices[0])


if __name__ == "__main__":
    unittest.main()
