# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict through the windows its disposition can die in.

A change request is handed to `workflow:fixing` by a relabel written before the
developer is launched, and the verdict rides that write as handed: a process
that stops between the two leaves `fixing` the feedback to hand the developer,
with nothing posted twice and no second reviewer, while a launch the ledger
says got past its charge is not run again. A verdict the pinned comment has no
room to persist is acted on not at all -- nothing durable would back it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.workflow.fixtures import (
    LABEL_FIXING,
    LABEL_VALIDATING,
    ROLE_DEVELOPER,
    ROLE_REVIEWER,
    _agent,
    _reported,
)
from tests.workflow.stages.validating import (
    review_evidence_readings as _read,
    review_evidence_test_support as _world,
)
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

REQUESTED = "1. The suite fails on the empty configuration; handle it."

# A reviewer asking for that change, with nothing declared beside it.
REQUESTING = f"{REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

RESERVATION = "agent_run_reservation"

UNRECORDED = "reviewer_unrecorded"

# A change request's feedback longer than most of what the pinned comment
# holds, and filler that leaves the round's own records room and it none.
LONG_REQUEST = REQUESTED * 1000

FILLER = "operator_notes"

FILLED = "x" * (MAX_PINNED_BODY - len(LONG_REQUEST))


def _spawned(case) -> tuple:
    """How many reviewers and developers the issue has spawned."""
    return (_read.spawns(case, ROLE_REVIEWER), _read.spawns(case, ROLE_DEVELOPER))


class HandedChangeRequestTest(_world.ReviewEvidenceWorld, unittest.TestCase):
    """A change request relabelled to `fixing` stays owed to the developer until one is launched."""

    def test_fixing_launches_the_one_developer(self) -> None:
        # The process stops between the relabel's write and the developer's
        # launch. The verdict rode that write as handed over, so the `fixing`
        # tick hands its feedback to the developer rather than bouncing the
        # issue to a second reviewer -- and posts nothing twice.
        self._handed_and_stopped()
        self.assertEqual(
            (
                self.github.workflow_label(self.issue),
                self.pinned()[_world.RETURNED_VERDICT]["handed"],
                _spawned(self),
            ),
            (LABEL_FIXING, self.pinned()[_world.AGENT_RUNS_USED], (1, 0)),
        )

        fixed = self._run_fixing(
            self.github, self.issue,
            run_agent=[_agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed"))],
            dirty_files=(),
            head_shas=FIX_HEAD_SHAS,
        )

        self.assertEqual(
            (
                _spawned(self),
                REQUESTED in fixed[_world.RUN_AGENT].call_args.args[1],
                len(_read.pr_comments(self, "requested changes")),
                self.pinned()[_world.RETURNED_VERDICT],
                self.github.label_history[-1],
            ),
            ((1, 1), True, 1, None, (_world.ISSUE, LABEL_VALIDATING)),
        )

    def test_a_launched_developer_is_not_rerun(self) -> None:
        # The ledger says a developer launch got past its charge after the
        # handoff: the run the verdict owed happened, so the verdict is
        # dropped and the stage's own road answers what that run left.
        self._handed_and_stopped()
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.AGENT_RUNS_USED, state.get(_world.AGENT_RUNS_USED) + 1)
        state.set(RESERVATION, "started")
        self.github.write_pinned_state(self.issue, state)

        self._run_fixing(self.github, self.issue, run_agent=[], dirty_files=())

        self.assertEqual(
            (_spawned(self), self.pinned()[_world.RETURNED_VERDICT]),
            ((1, 0), None),
        )

    def _handed_and_stopped(self) -> None:
        """A change request handed to `fixing`, and a tick that stopped before the launch."""
        with patch.object(self.github, "read_pinned_state", _world.RefusesTheLaunchRead(self)):
            self.dispatched(self.reviewer(REQUESTING))


class UnrecordedVerdictTest(_world.ReviewEvidenceWorld, unittest.TestCase):
    """A verdict the pinned comment has no room to persist is not acted on."""

    def test_a_full_comment_parks_the_verdict(self) -> None:
        # Nothing durable would back the change request, so it is neither
        # posted nor handed to a developer: it parks, and a retry buys a fresh
        # reviewer once there is room.
        state = self.github.read_pinned_state(self.issue)
        state.set(FILLER, FILLED)
        self.github.write_pinned_state(self.issue, state)

        self.dispatched(self.reviewer(f"{LONG_REQUEST}\n\nVERDICT: CHANGES_REQUESTED"))

        pinned = self.pinned()
        self.assertEqual(
            (
                pinned[_world.AWAITING_HUMAN],
                pinned[_world.PARK_REASON],
                pinned.get(_world.RETURNED_VERDICT),
                _spawned(self),
                _read.pr_comments(self, "requested changes"),
                self.github.label_history,
            ),
            (True, UNRECORDED, None, (1, 0), [], []),
        )


if __name__ == "__main__":
    unittest.main()
