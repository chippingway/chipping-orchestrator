# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a candidate may publish on where a rewrite permit is the only licence.

The crash recovery is the one caller that reaches this gate finishing a
publication rather than deciding one: the push it was leased for is already
owed. Every other answer the gate can give is about something else -- the
cumulative reading measures a commit that is already leased, and the records
that skip a reading say a candidate may publish without saying a human's
verdict may move onto it, which is what the write past the push turns on.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_gate as _gate,
    late_gate_models as _late_gate_models,
    late_gate_permission as _late_gate_permission,
    late_transfer as _transfer,
    late_verdict as _verdict_owner,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    MEASURED_CANDIDATE_SHA,
)
from tests.workflow.stages.implementing.late_gate_test_support import (
    GATE_ISSUE_NUMBER,
)

_CARRIED = "carries the exemption"


class PermitOnlyGateTest(unittest.TestCase):
    """One question, no fallbacks, and the caller owns a refusal."""

    def setUp(self) -> None:
        self.gate = _late_gate_models._Gate(
            gh=FakeGitHubClient(),
            spec=_TEST_SPEC,
            issue=make_issue(GATE_ISSUE_NUMBER),
            state=PinnedState(data={}),
            worktree=_FAKE_WT,
            permit_only=True,
            candidate=MEASURED_CANDIDATE_SHA,
        )

    def test_a_refused_permit_measures_nothing(self) -> None:
        with patch.object(
            _transfer, "_carried_over", return_value="",
        ), patch.object(_late_gate_permission, "_needs_no_measuring") as never:
            verdict = self._decides()

            never.assert_not_called()

        self.assertIs(verdict, _late_gate_models._REFUSED)
        self.assertTrue(verdict.held)

    def test_a_granted_permit_publishes_on_it_alone(self) -> None:
        with patch.object(
            _transfer, "_carried_over", return_value=_CARRIED,
        ), patch.object(_verdict_owner, "_unmeasured_verdict") as admitted:
            self._decides()

            # The commit the permit proved out for travels apart from the one
            # that may publish, because the write past the push turns on it.
            entered = admitted.call_args.args[2]

        self.assertEqual(entered.permitted_sha, MEASURED_CANDIDATE_SHA)
        self.assertEqual(entered.candidate_sha, MEASURED_CANDIDATE_SHA)

    def _decides(self) -> _late_gate_models._GateVerdict:
        return _gate._decided(
            self.gate, LateGeneration(), MEASURED_CANDIDATE_SHA,
        )


if __name__ == "__main__":
    unittest.main()
