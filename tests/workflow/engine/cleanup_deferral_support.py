# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One closed snapshot owner, driven through whole polling ticks.

The subject is a race between two threads and two ticks, so nothing here is
called directly: a case seeds the owner, says which ticks a worker holds it
for, and reads what the ticks left. Everything below the tick is real -- the
partition, the scheduler, the route, and the sweep the route reaches.
"""
from __future__ import annotations

import importlib
from unittest.mock import Mock, patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.skills import catalog
from orchestrator.workflow.engine import stage_targets as _stage_targets, tick as _tick
from orchestrator.workflow.late_split import obligations as _obligations, phases as _late_phases, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.dispatch_scheduler_test_support import (
    REPO_SLUG,
    _SchedulerWorkflowTest,
    patch_base_refresh,
)
from tests.workflow.fixtures import LABEL_UMBRELLA
from tests.workflow.observation_support import ObservedCloseCase, receipt_for

OWNER_NUMBER = 7

WORKFLOW_LOG = "orchestrator.workflow"

CYCLE_ID = 4

GENERATION = 1

CANDIDATE_SHA = "c0ffee0000000000000000000000000000000007"

OWNER_REF = "refs/orchestrator/late-split/issue-7/cycle-4/gen-1"

CANCELLED = "late_cancelled"

# The receipt a poll leaves on the thread for a close it could hand to no
# worker, built through the production spelling so a test that looks for one
# looks for exactly what a later process reads back.
RECEIPT_MARKER = receipt_for(OWNER_NUMBER, CYCLE_ID)

# The sentence the dispatcher says instead of dropping an observation.
DEFERRED = "holding the observation"

# The three reasons it says one out loud for.
HELD_BY_A_WORKER = "a worker is already running it"
PASS_FAILED = "the pass that took it failed"
ENDING_UNFINISHED = "owed under no label the sweep asks for"

# What the ledger says about an obligation this pass settled, and about one
# the remote would not let it settle.
RECONCILED = "reconciled"

FAILED = "failed"

# And what it says about one no pass has reached yet.
RETAINED = "retained"

# What the fake answers with when the request behind a read fails outright,
# and what a post GitHub declines looks like from here.
_OUTAGE = ConnectionError("github unreachable")
_REFUSED = RuntimeError("comment rejected")

# The handler an OPEN issue on this label reaches, and the one the whole
# deferral exists to keep a cancelled cycle away from.
UMBRELLA_TARGET = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_UMBRELLA]


class DeferralCase(ObservedCloseCase, _SchedulerWorkflowTest):
    """A closed umbrella, a worker holding it, and the ticks around that."""

    def setUp(self) -> None:
        self.github = _owner_holding_a_ref()
        self.stage = Mock()
        self._fresh_process()

    def _fresh_process(self) -> None:
        """Every registry a new process starts on, and its poll count too.

        A restarted process mints its own client, so the cadences counted on
        that client's enumeration start again from their first, due, poll.
        """
        super()._fresh_process()
        self.github._pollable_calls = 0

    def _cancelled(self) -> bool:
        """Whether the owner's own record now says the cycle ended."""
        return bool(self.github.pinned_data(OWNER_NUMBER).get(CANCELLED))

    def _reopened(self) -> None:
        """What a human does between two ticks, and nothing else reads."""
        self.github.get_issue(OWNER_NUMBER).closed = False

    def _tick_a_worker_held(self, scheduler) -> list[str]:
        """The tick that observes the close and can hand it to nobody."""
        with scheduler.track_active(REPO_SLUG, OWNER_NUMBER) as claimed:
            self.assertTrue(claimed)
            with self.assertLogs(WORKFLOW_LOG) as logged:
                self._ticked(scheduler, held=True)
                return list(logged.output)

    def _tick_the_pass_failed(self, scheduler) -> list[str]:
        """The tick whose cleanup was admitted and then broke on its refetch.

        The worker mints its own client and refetches the issue against it
        before anything routes, so the first thing this pass costs is a
        GitHub read -- and a read that fails marks nothing at all.
        """
        with self.assertLogs(WORKFLOW_LOG) as logged:
            with patch.object(self.github, "get_issue", side_effect=_OUTAGE):
                self._ticked(scheduler)
            return list(logged.output)

    def _ticked(
        self,
        scheduler,
        *,
        held: bool = False,
        remote=None,
        drained: bool = False,
    ) -> None:
        """One polling tick, run all the way into whatever handler it picks.

        `held` says the test itself is holding the issue, so no worker takes
        it and there is nothing to wait for. Otherwise the wait is on the
        issue key: a cleanup submit is cap-exempt, and an exempt worker is
        tracked rather than counted.

        `drained` waits on the SCHEDULER instead, which is what a tick whose
        issue reaches the family bucket needs: that submit reserves the
        bucket's own sentinel and claims the issue only once the drain gets
        to it, so a wait on the issue key can return before the worker has
        started.
        """
        stage_owner, stage_name = UMBRELLA_TARGET
        with (
            patch_base_refresh(),
            patch.object(catalog, "_emit_repo_skill_catalog", Mock()),
            patch.object(
                _snapshot_refs, "delete_snapshot_ref", remote or _taken(),
            ),
            patch.object(
                importlib.import_module(stage_owner), stage_name, self.stage,
            ),
        ):
            _tick.tick(self.github, self._spec(), scheduler=scheduler)
            if drained:
                scheduler.shutdown(wait=True)
            elif not held:
                self._wait_issue_idle(scheduler, OWNER_NUMBER)


def receipts_on(github) -> list[str]:
    """The durable close receipts this owner's thread carries."""
    return [
        body
        for number, body in github.posted_comments
        if number == OWNER_NUMBER and RECEIPT_MARKER in body
    ]


def tick_with_refused_receipt(case, scheduler) -> None:
    """The tick whose observation GitHub would not let it write down."""
    with patch.object(case.github, "comment", side_effect=_REFUSED):
        case._tick_a_worker_held(scheduler)


def ticked_directly(case, limit: int, *, failing: bool = False) -> None:
    """One tick with NO scheduler, on the path `parallel_limit` chooses.

    The two supported direct modes, which are the same cleanup route reached
    without the scheduler's own submit: `limit == 1` streams the enumeration
    on the polling thread, and anything above it fans out across a bounded
    pool. Both have to hold a cleanup's observation the way the scheduler's
    wrapper does, because neither has that wrapper.

    `failing` refuses the refetch a cleanup opens with, which is the first
    thing such a pass spends and the likeliest thing to break.
    """
    stage_owner, stage_name = UMBRELLA_TARGET
    reading = case.github.get_issue
    with (
        patch_base_refresh(),
        patch.object(catalog, "_emit_repo_skill_catalog", Mock()),
        patch.object(_snapshot_refs, "delete_snapshot_ref", _taken()),
        patch.object(
            importlib.import_module(stage_owner), stage_name, case.stage,
        ),
        patch.object(
            case.github, "get_issue", side_effect=_Refusing(reading, failing),
        ),
    ):
        _tick.tick(case.github, case._spec(parallel_limit=limit))


class _Refusing:
    """Answer a refetch the way one case says GitHub would."""

    def __init__(self, reading, failing: bool) -> None:
        self._reading = reading
        self._failing = failing

    def __call__(self, number: int):
        """Answer one read, or refuse it the way an outage does."""
        if self._failing:
            raise _OUTAGE
        return self._reading(number)


def _taken() -> Mock:
    """A remote that drops whatever ref it is handed."""
    return Mock(return_value=_snapshot_refs.SnapshotOutcome.DELETED)


def _owner_holding_a_ref() -> FakeGitHubClient:
    """A closed umbrella whose ledger still holds one snapshot ref."""
    github = FakeGitHubClient()
    github.add_issue(make_issue(
        OWNER_NUMBER, label=LABEL_UMBRELLA, closed=True,
    ))
    state = github.read_pinned_state(github.get_issue(OWNER_NUMBER))
    _late_state.write_late_generation(state, LateGeneration(
        cycle_id=CYCLE_ID,
        generation=GENERATION,
        root_issue=OWNER_NUMBER,
        current_issue=OWNER_NUMBER,
        candidate_sha=CANDIDATE_SHA,
        phase=_late_phases.LatePhase.SNAPSHOTTING,
        obligations=_obligations.LateObligations().with_resource(_obligations.LateResource(
            kind=_obligations.LateResourceKind.SNAPSHOT_REF,
            target=OWNER_REF,
            resource_state=_obligations.LateResourceState.RETAINED,
        )),
    ))
    # The flag the split writes before its first child, which is what says
    # this parent has no implementation of its own to go back to.
    github.seed_state(OWNER_NUMBER, umbrella=True, **state.data)
    return github
