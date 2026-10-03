# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issues another poller on this host is writing, driven through whole ticks.

The other poller holds its claims through `tests/support/writer_claims.py`.
Everything below the tick is real except the stage handler, which stands in
for one that runs, publishes, and records.
"""
from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterable
from unittest.mock import Mock, patch

from orchestrator import config
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.skills import catalog
from orchestrator.workflow.engine import stage_targets as _stage_targets, tick as _tick
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.dispatch_scheduler_test_support import (
    _SchedulerWorkflowTest,
    patch_base_refresh,
)
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_IMPLEMENTING

# What a pass that ran leaves behind, so a pass that did not is visible.
RAN_COMMENT = "stand-in handler ran"

RUNS_KEY = "stand_in_runs"

# One open fan-out, one closed fan-out, and one family issue another poller
# holds, and one of each it does not. The closed pair is the ordinary pass
# that carries a closed reading, which is held across a pass of its own.
HELD_FANOUT = 7
FREE_FANOUT = 8
HELD_FAMILY = 9
FREE_FAMILY = 10
HELD_CLOSED = 11
FREE_CLOSED = 12

HELD_ISSUES = frozenset((HELD_FANOUT, HELD_FAMILY, HELD_CLOSED))
FREE_ISSUES = frozenset((FREE_FANOUT, FREE_FAMILY, FREE_CLOSED))

_HANDLED_LABELS = (LABEL_IMPLEMENTING, LABEL_DECOMPOSING)


class StandInHandler:
    """A stage handler that runs, publishes, and records its run."""

    def __init__(self, failing: Iterable[int] = ()) -> None:
        self.ran: list[int] = []
        self._failing = frozenset(failing)
        self._lock = threading.Lock()

    def __call__(self, gh, spec, issue) -> None:
        with self._lock:
            self.ran.append(int(issue.number))
        if issue.number in self._failing:
            raise RuntimeError("the handler failed")
        gh.comment(issue, RAN_COMMENT)
        state = gh.read_pinned_state(issue)
        state.data[RUNS_KEY] = state.data.get(RUNS_KEY, 0) + 1
        gh.write_pinned_state(issue, state)


class WriterClaimDispatchCase(_SchedulerWorkflowTest):
    """Three held and three free issues, and the ticks over them."""

    def seeded(self) -> None:
        """A fresh repository carrying the six issues, with nothing recorded."""
        self.github = FakeGitHubClient()
        for issue_number, label in (
            (HELD_FANOUT, LABEL_IMPLEMENTING),
            (FREE_FANOUT, LABEL_IMPLEMENTING),
            (HELD_FAMILY, LABEL_DECOMPOSING),
            (FREE_FAMILY, LABEL_DECOMPOSING),
        ):
            self.github.add_issue(make_issue(issue_number, label=label))
        for closed_number in (HELD_CLOSED, FREE_CLOSED):
            self.github.add_issue(make_issue(
                closed_number, label=LABEL_IMPLEMENTING, closed=True,
            ))
        self.evaluated = Mock()

    def evaluated_issues(self) -> set[int]:
        """The issues a stage evaluation was recorded for."""
        return {call.kwargs["issue"] for call in self.evaluated.call_args_list}

    def written_issues(self) -> set[int]:
        """The issues anything was published or recorded on."""
        commented = {number for number, _body in self.github.posted_comments}
        recorded = {
            number for number in HELD_ISSUES | FREE_ISSUES
            if self.github.pinned_data(number)
        }
        relabelled = {entry[0] for entry in self.github.label_history}
        return commented | recorded | relabelled

    def ticked(self, stand_in: StandInHandler, *, limit: int, scheduled: bool) -> None:
        """One whole tick, through the dispatch mode the arguments name.

        A scheduled tick is drained before this returns, so what it read back
        is everything the tick's workers did.
        """
        scheduler = self._scheduler() if scheduled else None
        with self._patched(stand_in):
            _tick.tick(self.github, self._spec(parallel_limit=limit), scheduler=scheduler)
            if scheduler is not None:
                self._wait_idle(scheduler)
                scheduler.shutdown(wait=True)

    @contextlib.contextmanager
    def _patched(self, stand_in: StandInHandler):
        """Every collaborator a tick reaches that this case stands in for.

        The closed sweep runs on every tick here, so a retry reaches the
        closed pair as the first tick did.
        """
        with contextlib.ExitStack() as patched:
            patched.enter_context(patch_base_refresh())
            patched.enter_context(patch.object(config, "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS", 1))
            patched.enter_context(patch.object(catalog, "_emit_repo_skill_catalog", Mock()))
            patched.enter_context(patch.object(
                _recording_events, "record_stage_evaluation", self.evaluated,
            ))
            for label in _HANDLED_LABELS:
                owner, name = _stage_targets._STAGE_HANDLER_TARGETS[label]
                patched.enter_context(patch(f"{owner}.{name}", stand_in))
            yield
