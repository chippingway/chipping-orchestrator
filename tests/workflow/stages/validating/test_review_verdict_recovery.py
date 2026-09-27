# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted verdict that may not be acted on, and the road it takes back to a reviewer.

A refused approval parks only while the subject it approved still stands: a
push since the verdict's write drops it for a fresh reviewer instead of
waiting on a human. Either park a verdict takes -- `reviewer_unverified` or
`reviewer_unrecorded` -- is answered by a bare `/orchestrator continue` with a
fresh reviewer and no developer. And a waiting verdict whose evidence can
never settle is dropped rather than waited on forever.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.workflow.fixtures import _agent
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world

VERIFY = "_run_verify_commands"

AWAITING_HUMAN = "awaiting_human"

CONTINUE = "/orchestrator continue"

# A change request longer than most of what the pinned comment holds.
_LONG = "12 passed, 1 failed " * 1000

# Each park a returned verdict takes, what the reviewer returned to earn it,
# and the operator notes that leave the comment no room for that verdict.
_PARKS = (
    ("reviewer_unverified", "LGTM\n\nVERDICT: APPROVED", 0),
    ("reviewer_unrecorded", f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG)),
)

# A configuration the recorded evidence was never run under.
_MOVED_CONFIGURATION = (_world.SUITE, "uv run ruff check")


def _undecided():
    """A reviewer run that decides nothing a case here asks about."""
    return _agent(session_id="rev-2", last_message="Reading.\n\nVERDICT: UNKNOWN")


class VerdictRecoveryTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """Every road a verdict that may not be acted on takes leads to a fresh reviewer."""

    def test_a_moved_subject_drops_a_refused_approval(self) -> None:
        # The head moves behind the reused approval's write, so the evidence
        # no longer proves current -- but the approval is of a head nobody is
        # asking about, which a fresh reviewer answers without a reply.
        digest = _read.settles_evidence(self).content_revision
        behind = _world.AnotherRoadBehind(
            self,
            "write_pinned_state",
            lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            _world.pushes,
        )

        ran = behind.returning(f"Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED")

        pinned = self.pinned()
        self.assertEqual(
            (
                bool(pinned.get(AWAITING_HUMAN)),
                pinned.get(_world.PARK_REASON),
                pinned[_world.RETURNED_VERDICT],
                ran[VERIFY].call_count,
                self.github.label_history,
            ),
            (False, None, None, 0, []),
        )

    def test_a_bare_continue_buys_a_fresh_reviewer(self) -> None:
        for reason, message, filled in _PARKS:
            with self.subTest(reason):
                self.setUp()
                self._notes("x" * filled)
                self.returns(message)
                self.assertEqual(self.pinned()[_world.PARK_REASON], reason)
                # The room the unrecorded park asks for, freed as it says.
                self._notes("")
                _world.replies(self, CONTINUE)

                ran = self.dispatched(_undecided())

                self.assertEqual(
                    (ran[_world.RUN_AGENT].call_count, _read.spawned_roles(self)),
                    (1, ["reviewer"]),
                )

    def test_a_lost_claim_drops_its_waiting_verdict(self) -> None:
        # The approval waits on its published evidence, and the configuration
        # moves before that evidence settles: it never can, so the verdict is
        # dropped and the next tick's reviewer reviews under what stands.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run())
        self.github.report_failures.lost.discard(_world.PR)
        self.assertIsNotNone(self.pinned()[_world.RETURNED_VERDICT])

        with patch.object(config, "VERIFY_COMMANDS", _MOVED_CONFIGURATION):
            dropped = self.dispatched()
            waiting = self.pinned()[_world.RETURNED_VERDICT]
            reviewed = self.dispatched(_undecided())

        self.assertEqual(
            (
                dropped[_world.RUN_AGENT].call_count,
                waiting,
                self.github.label_history,
                reviewed[_world.RUN_AGENT].call_count,
                _read.spawned_roles(self),
            ),
            (0, None, [], 1, ["reviewer"]),
        )

    def _notes(self, text: str) -> None:
        """Put `text` down as the operator's notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", text)
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
