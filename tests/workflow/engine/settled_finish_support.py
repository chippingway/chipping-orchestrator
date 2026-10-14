# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dormant settled-evidence finish policy, selected for every finish a case hands the coordinator in a scope.

No production road builds a finish that selects it
(`rewrite_finish_models.LandedFinish.proves_settled`), so a case driving the
policy selects it itself. `selected` holds every finish the coordinator
(`rewrite_finish.finalizes`) is handed in its scope to the policy: one a case
builds and hands it directly -- over a fresh pinned reading and the real
checkout (`RealGitFinishCase.finishes`), or over the in-memory world
(`FinishWorld.finalizes`) -- and one a whole per-tick base refresh reaches
through the publication or the recovery of a push already landed. Nothing else
about those roads changes, so a case reads back exactly what the policy made
of each finish; outside the scope every finish keeps the policy its road hands
over. A real-git case selecting it for every test is a `SettledRunCase`, and
one whose every refresh takes the git owner's guarded abort as well is a
`SettledGuardedCase`; both hold the push transport and the agent runner to the
case's own recorders for the whole test (`_counts_side_effects`), so a push or
a launch a direct finish made is counted as one a refresh made would be.
Beside them, a case racing a finish's settlement records a newer run beside
the one settled (`records_a_newer_run`) or settles a captured run as another
finish would, dying before its announcement or at its relabel
(`settles_elsewhere`).
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    rewrite_finish as _finish,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from tests.workflow.engine import (
    guarded_recovery_support as _guarded,
    rewrite_finish_git_support as _git_support,
    rewrite_finish_readings as _readings,
    rewrite_handoff_test_support as _handoff,
    rewrite_verification_recovery_support as _support,
)

# The coordinator, read before any case patches it.
_FINALIZES = _finish.finalizes


def _holds_to_the_policy(finish: LandedFinish) -> FinishOutcome:
    """Hand the coordinator `finish` held to the settled-evidence policy."""
    return _FINALIZES(replace(finish, proves_settled=True))


def selected():
    """Hold every finish the coordinator is handed in scope to the settled-evidence policy."""
    return patch.object(_finish, "finalizes", _holds_to_the_policy)


def _counts_side_effects(case) -> None:
    """Hold `case`'s push transport and agent runner to its own recorders until the test ends.

    A whole refresh installs them around itself (`CapturedRunCase.recovers`);
    a finish a case hands over directly reaches neither patch, so a push or a
    launch it made would go out for real and never be counted.
    """
    case.enterContext(patch.object(branch_transport, "_push_branch", case.pushes))
    case.enterContext(patch.object(_agent_runner, "run_agent", case.developer))


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


def settles_elsewhere(
    case, head: str, written: str, raced: list, died: _handoff.Boundary = _handoff.BEFORE_THE_ANNOUNCEMENT,
) -> None:
    """Put the issue back as `written` and settle `head`'s captured run as another finish would, once; into `raced`.

    That finish dies at `died`: before its announcement, so the attempt
    stands as it was read, or announced, before its relabel, its mark and the
    record of its event put down on the attempt for `head`.
    """
    if raced:
        return
    raced.append(head)
    case.issue.body = written
    finishing = partial(case.finishes, head, FinishRoad.RECOVERY)
    _handoff.dies_at(case.gh, died, finishing)


class SettledRunCase(_support.CapturedRunCase):
    """The real-git captured-run case whose every finish, direct or reached by a refresh, selects the policy."""

    def setUp(self) -> None:
        _support.CapturedRunCase.setUp(self)
        self.enterContext(selected())
        _counts_side_effects(self)


class SettledGuardedCase(_guarded.GuardedRecoveryCase):
    """`SettledRunCase` over refreshes that take the git owner's guarded abort (`GuardedRecoveryCase`)."""

    def setUp(self) -> None:
        _guarded.GuardedRecoveryCase.setUp(self)
        self.enterContext(selected())
        _counts_side_effects(self)

    def assert_routed(self, head: str, current=None) -> None:
        """`head` announced once and routed, its attempt retired, `current` current with nothing pending; run once."""
        announced = (_support.announced(self), len(_readings.notices(self)))
        self.assertEqual(announced, ([head], 1))
        self.assertEqual(_readings.relabels(self), _readings.ROUTED)
        self.assertEqual(_readings.attempt(_readings.pinned(self)), _readings.RETIRED)
        self.assertEqual(_readings.pinned_records(self)[:2], (None, current))
        self.assert_made_once()

    def assert_invalidated_then_routed(self, head: str, settled) -> None:
        """`settled` invalidated whole, its revision and binding kept, and `head` routed once, nothing parked.

        The route's relabel files one stage-entry event, and another poll
        leaves the comment exactly as it is, with nothing said, relabelled,
        run, pushed, or launched again.
        """
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        whole = (entry.receipt, entry.retired.value, entry.revision, entry.binding)
        self.assertEqual(whole, (settled.receipt, _readings.INVALIDATED, settled.revision, settled.binding))
        self.assertFalse(_readings.pinned(self).get(_guarded.AWAITING))
        self.assert_routed(head)
        self.assertEqual(_handoff.stage_entries(self.gh, _git_support.ISSUE), ["validating"])
        routed = _readings.pinned(self)
        self.recovers()
        self.assertEqual(_readings.pinned(self), routed)
        self.assert_routed(head)
