# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a pending captured completion's effect stands on, read again behind the issue's last fetch before it.

Each case lands a capture, makes a move while the dispatch's readings are
taken -- behind a pinned reading the decision took, or behind the issue's
first fetch -- and dispatches the issue whole, the stage handler stood in
for. A retirement is held to the whole pinned reading that proved it and to
the issue, checkout, or pull request reading that did; a handoff to the
issue, the checkout, and the pull request, each read again behind that
fetch. A move there holds the capture with nothing written, handed on, or
run, for the next dispatch to decide afresh.
"""
from __future__ import annotations

import itertools
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.github.models import FakeLabel
from tests.workflow.engine import (
    completion_dispatch_support as _dispatch,
    completion_recovery_support as _support,
    completion_turn_support as _turns,
)

Turn = _turns.Turn
_Reason = _models.Reason
_Standing = _models.Standing
_PENDING = _records.CaptureStage.PENDING

_ON_VALIDATING = WorkflowLabel.VALIDATING

# A drift resume read on `validating`, which stands on its pull request.
_DRIFT = _support.road(_routes.CompletionRoute.REQUIREMENTS_DRIFT, _ON_VALIDATING)

# The pinned readings a dispatch takes up to its retirement commit's own: the
# dispatcher's, the capture's read-back, the retirement's, and its commit's.
_COMMIT_READING = 4

# The operator control applied while a decision's readings are taken, and the issue's labels once it is.
_PAUSED = "paused"
_CONTROLLED = (FakeLabel(str(WorkflowLabel.IMPLEMENTING)), FakeLabel(_PAUSED))
_PAUSED_LABELS = MappingProxyType({"labels": _CONTROLLED})

# What a control lands behind: readings proving the capture stale, and readings admitting it.
_BEHIND_THE_PROOF = MappingProxyType({
    "a proof of staleness": Turn(comment="Also cover the edge case."),
    "an admission": Turn(),
})

# What the issue's last fetch finds moved behind the readings its decision
# took: an admitted issue closed or its body edited, and one proved closed
# reopened.
_ISSUE_MOVED = MappingProxyType({
    "closed behind an admission": (Turn(), MappingProxyType({"closed": True})),
    "edited behind an admission": (Turn(), MappingProxyType({"body": "Also require a second behavior."})),
    "reopened behind a proof of its end": (Turn(closed=True), MappingProxyType({"closed": False})),
})

_PULL_REQUEST_ELSEWHERE = Turn(pull_request=MappingProxyType({"sha": _support.ELSEWHERE}))

# Each source a proof of staleness was read off, moved before the dispatch
# and put back behind the issue's first fetch: whether the record names a
# pull request, the move, and the move putting it back.
_PUT_BACK = MappingProxyType({
    "checkout": (False, Turn(head=_support.ELSEWHERE), Turn(head=_support.SOURCE)),
    "pull request head": (
        True, _PULL_REQUEST_ELSEWHERE, Turn(pull_request=MappingProxyType({"sha": _support.BEFORE})),
    ),
    "pull request reopened": (
        True, Turn(pull_request=MappingProxyType({"state": "closed"})),
        Turn(pull_request=MappingProxyType({"state": "open"})),
    ),
})

# Each source an admission was read off, moved behind the issue's first fetch.
_MOVED_SOURCE = MappingProxyType({
    "checkout": (False, Turn(), Turn(head=_support.ELSEWHERE)),
    "pull request head": (True, Turn(), _PULL_REQUEST_ELSEWHERE),
})


class _MovedBehind:
    """A fetch of the issue that makes `turn`'s moves just before its second answer -- the effect's own -- once."""

    def __init__(self, world: _support.CapturedWorld, turn: Turn) -> None:
        self._world = world
        self._turn = turn
        self._answered = 0

    def __call__(self, _number: int):
        """The issue as it stands, `turn`'s moves made first where this is the fetch they land behind."""
        self._answered += 1
        if self._answered == 2:
            _turns.turned(self._world, self._turn)
        return self._world.issue


class _HoldingCase(unittest.TestCase):
    """A case that reads back whether a dispatch held the capture."""

    def _kept(self, seen: _dispatch.Observed, reason: _Reason) -> None:
        """The dispatch held the capture as uncertain for `reason`, with nothing written, handed on, or run."""
        self.assertTrue(seen.says(reason, _Standing.UNCERTAIN), seen.said)
        self.assertEqual(_support.read_capture(seen.after).stage, _PENDING)
        self.assertEqual(seen.writes, 0)
        self.assertEqual((seen.ran, seen.handed), ((), ()))


class IssueRecheckTest(_HoldingCase):
    """What a decision read off the comment or the issue is read once more behind its effect."""

    def test_a_restored_prerequisite_keeps_it(self) -> None:
        # The road's pull request is gone when the dispatch reads the comment,
        # and somebody puts it back while the retirement's own commit reads it
        # again: the commit is held to the whole reading the proof was taken
        # over, a field it lacked included, so nothing is written or run, and
        # the next dispatch hands the capture on.
        world = _support.CapturedWorld(_ON_VALIDATING, pull_request=True)
        captured = world.captured(_DRIFT)
        world.hand_edit(pr_number=_support.DROPPED)
        restored = _support.RepairedBehind(world, _COMMIT_READING, pr_number=_support.PR_NUMBER)

        with patch.object(world.github, "read_pinned_state", side_effect=restored):
            held = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual(_support.read_capture(held.after), captured)
        self.assertEqual(held.writes, 0, "nothing is written over the capture")
        self.assertEqual((held.ran, held.handed), ((), ()))
        again = _dispatch.observed(world, _dispatch.RoadOwner())
        self.assertEqual(len(again.handed), 1)

    def test_a_control_behind_the_proof_keeps_it(self) -> None:
        # `paused` lands while the readings behind a decision are taken -- one
        # proving the capture stale, and one admitting it: the issue fetched
        # again right before the effect holds both, with nothing written,
        # handed on, or run.
        for name, turn in _BEHIND_THE_PROOF.items():
            with self.subTest(name):
                seen = self._fetched_behind(turn, _PAUSED_LABELS)

                self._kept(seen, _Reason.ISSUE_UNREAD)

    def test_an_issue_moved_behind_keeps_it(self) -> None:
        # Closed, or edited to ask for something else, behind an admission's
        # readings, the issue the owner would be handed is not the one they
        # admitted; reopened behind a proof that its work ended, it is not
        # the one the retirement was proved on.
        for name, (turn, moved) in _ISSUE_MOVED.items():
            with self.subTest(name):
                seen = self._fetched_behind(turn, moved)

                self._kept(seen, _Reason.MOVED_BEHIND)

    def _fetched_behind(self, turn: Turn, moved) -> _dispatch.Observed:
        """A dispatch after `turn`, the issue fetched with `moved` behind the first fetch its admission takes."""
        world = _support.CapturedWorld()
        world.captured()
        refetched = replace(world.issue, **moved)
        fetched = itertools.chain((world.issue,), itertools.repeat(refetched))
        with patch.object(world.github, "get_issue", side_effect=fetched):
            return _dispatch.observed(world, _dispatch.RoadOwner(), turn)


class SourceRecheckTest(_HoldingCase):
    """What a decision read off the checkout or the pull request is read once more behind its effect."""

    def test_a_source_put_back_keeps_it(self) -> None:
        # The checkout reset off the commit reported on, or the pull request
        # pushed over or closed, proves the capture stale; somebody puts it
        # back while the issue is fetched behind that proof, so the source is
        # the run's again when the retirement would land. The capture is kept,
        # and the next dispatch hands it on.
        for name, case in _PUT_BACK.items():
            with self.subTest(name):
                world, seen = self._sourced_behind(case)

                self._kept(seen, _Reason.MOVED_BEHIND)
                again = _dispatch.observed(world, _dispatch.RoadOwner())
                self.assertEqual(len(again.handed), 1)

    def test_a_source_moved_behind_holds_it(self) -> None:
        # The checkout reset, or the pull request pushed over, behind an
        # admission's readings: the source the owner would be handed is not
        # the one admitted, so nothing is handed on.
        for name, case in _MOVED_SOURCE.items():
            with self.subTest(name):
                _world, seen = self._sourced_behind(case)

                self._kept(seen, _Reason.MOVED_BEHIND)

    def _sourced_behind(self, case: tuple) -> tuple[_support.CapturedWorld, _dispatch.Observed]:
        """A dispatch after `case`'s first move, its second made behind the issue's first fetch; and its world."""
        pull_request, turn, behind = case
        world = _support.CapturedWorld(pull_request=pull_request)
        world.captured()
        fetched = _MovedBehind(world, behind)
        with patch.object(world.github, "get_issue", side_effect=fetched):
            return world, _dispatch.observed(world, _dispatch.RoadOwner(), turn)


if __name__ == "__main__":
    unittest.main()
