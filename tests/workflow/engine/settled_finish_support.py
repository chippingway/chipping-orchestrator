# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dormant settled-evidence policy's evidence phase, asked directly over a finish built from fresh readings.

No production road selects the policy (`rewrite_finish_models.LandedFinish.proves_settled`),
so a case builds the finish itself -- over the pinned comment read afresh and
the candidate git reads out of the checkout -- and asks the evidence phase
(`rewrite_finish_settlement.resolves`), or another of the policy's steps
(`SettledRunCase.asks_dormant`), directly, with nothing behind it to
announce, relabel, park, or retire the attempt. `SettledRunCase` holds the
push transport and the agent runner to the case's recorders for the whole
test, so a push or a launch the phase made is counted as one a refresh made
would be. Beside it, `records_a_newer_run` races a settlement as another road
would, and `charges` leaves the run ledger another road's launch charged on
the comment for a case to read back exactly as left (`assert_charged_as_left`).
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    rewrite_finish_settlement as _settlement_step,
    run_ledger_values as _run_ledger,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from tests.workflow.engine import (
    rewrite_finish_git_support as _git_support,
    rewrite_finish_readings as _readings,
    rewrite_verification_recovery_support as _support,
)

# The run ledger another road's launch left on the comment: the runs spent on
# it and on the legacy usage meter beside it, and a launch reserved and
# started under its fingerprint, at the count it was owed at.
_CHARGED = MappingProxyType({
    _run_ledger.AGENT_RUNS_USED: 5,
    "issue_agent_runs": 4,
    _run_ledger.AGENT_RUN_RESERVATION: "started",
    _run_ledger.AGENT_RUN_FINGERPRINT: "developer:issue-7:round-3",
    _run_ledger.AGENT_RUN_OWED_STARTED: 4,
})


def dormant(finish: LandedFinish) -> LandedFinish:
    """`finish` held to the dormant settled-evidence policy."""
    return replace(finish, proves_settled=True)


def _handed_dormant(step, finish: LandedFinish):
    """What `step` answers handed `finish` held to the policy (`dormant`)."""
    return step(dormant(finish))


def charges(case) -> None:
    """Leave the run ledger another road's launch charged (`_CHARGED`) on `case`'s comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    for key, charged in _CHARGED.items():
        state.set(key, charged)
    case.gh.write_pinned_state(case.issue, state)


def assert_charged_as_left(case) -> None:
    """`case`'s run ledger exactly as `charges` left it: nothing spent, reserved, or released since."""
    pinned = case.gh.pinned_data(case.issue.number)
    ledger = {key: pinned.get(key) for key in _CHARGED}
    case.assertEqual(ledger, dict(_CHARGED))


def records_a_newer_run(case, *, settles: bool = False):
    """Record a newer transaction beside `case`'s settled run, carrying its binding, as another road would; it.

    Its transcript is the configured command passing, as the settled run's own
    reads, and it raises the revision floor past that run. `settles` posts its
    artifact and settles it over that run in the same write, which supersedes
    the run under a receipt of its own.
    """
    state = case.gh.read_pinned_state(case.issue)
    command = config.VERIFY_COMMANDS[0]
    passed = (VerifiedCommand(command=command, exit_status=0, output=_git_support.CHECKED),)
    newer = _record_state.mint_pending_evidence(
        state, _git_support.ISSUE, _readings.pinned_records(case)[1].binding, passed,
    )
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    if settles:
        posted = case.gh.publish_verification_artifact(case.pull_request, newer.artifact)
        state = _settlement.settled_state(state, newer, posted.landed_id, _git_support.REVIEWING)
    case.gh.write_pinned_state(case.issue, state)
    return newer


class SettledRunCase(_support.CapturedRunCase):
    """The real-git captured-run case whose evidence phase a test asks directly under the settled-evidence policy."""

    def setUp(self) -> None:
        _support.CapturedRunCase.setUp(self)
        self.enterContext(patch.object(branch_transport, "_push_branch", self.pushes))
        self.enterContext(patch.object(_agent_runner, "run_agent", self.developer))

    def resolves(self, head: str) -> FinishOutcome | None:
        """The evidence phase of a recovery's finish of `head` (`asks_dormant`)."""
        return self.asks_dormant(_settlement_step.resolves, head)

    def asks_dormant(self, step, head: str):
        """What `step` answers for a recovery's finish of `head` held to the policy, over the comment read now."""
        return self.finishes(head, FinishRoad.RECOVERY, asks=partial(_handed_dormant, step))

    def assert_phase_left(self, *heads: str) -> None:
        """The attempt standing on its anchor, announced once for each of `heads` and never relabelled; run once.

        Nothing pushed or launched, and the run ledger as charged.
        """
        self.assertEqual(_support.announced(self), list(heads))
        self.assertEqual(len(_readings.notices(self)), len(heads))
        self.assertEqual(_readings.relabels(self), ())
        self.assertEqual(_readings.pinned(self)[_readings.KEY_PENDING_PUSH], self.anchor)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))
        assert_charged_as_left(self)
