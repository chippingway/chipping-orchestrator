# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issues another poller on this host is writing, driven through whole ticks.

Everything below the tick is real except the stage handler, which stands in
for one that runs, publishes, and records.
"""
from __future__ import annotations

import contextlib
import threading
from unittest.mock import Mock, patch

from orchestrator import config
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.skills import catalog
from orchestrator.workflow.engine import stage_targets as _stage_targets, tick as _tick
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.dispatch_scheduler_test_support import (
    REPO_SLUG,
    _SchedulerWorkflowTest,
    patch_base_refresh,
)
from tests.workflow.fixtures import LABEL_BLOCKED, LABEL_DECOMPOSING, LABEL_DONE, LABEL_IMPLEMENTING
from tests.workflow.observation_support import ObservedCloseCase

# Each way a tick can execute its issues, as (name, `parallel_limit`, whether
# the scheduler takes the dispatch over): the sequential loop, the bounded
# in-tick pool, and the scheduler's fan-out submits and family bucket.
DISPATCH_MODES = (
    ("sequential", 1, False),
    ("pool", 2, False),
    ("scheduler", 4, True),
)

# What a pass that ran leaves behind, so a pass that did not is visible.
RAN_COMMENT = "stand-in handler ran"

# The name GitHub answers for the repository, where the spec is configured
# under an old one: a claim keyed on the configuration would meet no holder.
CANONICAL_SLUG = "Acme/Widget-Renamed"

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
ALL_ISSUES = HELD_ISSUES | FREE_ISSUES

# A blocked parent whose second child waits only on its done first one, so the
# parent's walk releases that child on a tick unless something holds it back.
FAMILY_PARENT = 33
DONE_CHILD = 331
WAITING_CHILD = 332

_HANDLED_LABELS = (LABEL_IMPLEMENTING, LABEL_DECOMPOSING)


class StandInHandler:
    """A stage handler that runs, publishes, and records its run.

    `ran_on` keeps the label each run was handed its issue under, which is
    the label the dispatcher chose the handler by.
    """

    def __init__(self, *failing: int) -> None:
        self.ran: list[int] = []
        self.ran_on: list[tuple[int, str | None]] = []
        self._failing = frozenset(failing)
        self._lock = threading.Lock()

    def __call__(self, gh, spec, issue) -> None:
        with self._lock:
            self.ran.append(int(issue.number))
            self.ran_on.append((int(issue.number), gh.workflow_label(issue)))
        if issue.number in self._failing:
            raise RuntimeError("the handler failed")
        gh.comment(issue, RAN_COMMENT)
        state = gh.read_pinned_state(issue)
        state.data[RUNS_KEY] = state.data.get(RUNS_KEY, 0) + 1
        gh.write_pinned_state(issue, state)


class WriterClaimDispatchCase(ObservedCloseCase, _SchedulerWorkflowTest):
    """Three held and three free issues, and the ticks over them."""

    def seeded(self) -> None:
        """A fresh repository carrying the six issues, in a fresh process."""
        self.fresh_repository()
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

    def seeded_family(self) -> None:
        """A fresh repository carrying only the blocked parent and its two children."""
        self.fresh_repository()
        for issue_number, label in (
            (FAMILY_PARENT, LABEL_BLOCKED), (DONE_CHILD, LABEL_DONE), (WAITING_CHILD, LABEL_BLOCKED),
        ):
            self.github.add_issue(make_issue(issue_number, label=label))
        for child in (DONE_CHILD, WAITING_CHILD):
            self.github.seed_state(child, parent_number=FAMILY_PARENT)
        self.github.seed_state(
            FAMILY_PARENT, children=[DONE_CHILD, WAITING_CHILD], dep_graph={"1": [0]},
        )

    def fresh_repository(self) -> None:
        """An empty repository named canonically, with nothing observed or recorded."""
        self._fresh_process()
        self.github = FakeGitHubClient(repo_slug=CANONICAL_SLUG)
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

    def ticked(
        self,
        stand_in: StandInHandler,
        *,
        limit: int,
        scheduled: bool,
        labels: tuple[str, ...] = _HANDLED_LABELS,
    ) -> None:
        """One whole tick, through the dispatch mode the arguments name.

        `stand_in` answers for the handler of every label in `labels`. A
        scheduled tick is drained before this returns, so what it read back is
        everything the tick's workers did.
        """
        scheduler = self._scheduler() if scheduled else None
        with self._patched(stand_in, labels):
            _tick.tick(self.github, self._spec(parallel_limit=limit), scheduler=scheduler)
            if scheduler is not None:
                self._wait_idle(scheduler)
                scheduler.shutdown(wait=True)

    @contextlib.contextmanager
    def _patched(self, stand_in: StandInHandler, labels: tuple[str, ...]):
        """Every collaborator a tick reaches that this case stands in for.

        The closed sweep and the dependency walk run on every tick here, so
        a retry reaches the closed pair and a family parent as the first tick
        did.
        """
        with contextlib.ExitStack() as patched:
            patched.enter_context(patch_base_refresh())
            patched.enter_context(patch.object(config, "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS", 1))
            patched.enter_context(patch.object(config, "DEPENDENCY_POLL_EVERY_N_TICKS", 1))
            patched.enter_context(patch.object(catalog, "_emit_repo_skill_catalog", Mock()))
            patched.enter_context(patch.object(
                _recording_events, "record_stage_evaluation", self.evaluated,
            ))
            for label in labels:
                owner, name = _stage_targets._STAGE_HANDLER_TARGETS[label]
                patched.enter_context(patch(f"{owner}.{name}", stand_in))
            yield


class HeldIssuesCase(WriterClaimDispatchCase):
    """The six seeded issues, ticked while the held three are held and after."""

    def ticked_while_held(
        self, holding: contextlib.AbstractContextManager, *, limit: int, scheduled: bool,
    ) -> None:
        """A tick over the seeded issues while `holding` holds the held ones."""
        stand_in = StandInHandler()
        with holding:
            self.ticked(stand_in, limit=limit, scheduled=scheduled)

        self.assertEqual(set(stand_in.ran), set(FREE_ISSUES), "only the free issues run")
        self.assertEqual(self.written_issues(), set(FREE_ISSUES), "nothing is written on a held one")
        self.assertEqual(self.evaluated_issues(), set(FREE_ISSUES), "nothing is accounted for one")
        # The held closed issue carries no cycle its close could end, which
        # its record says, so there is nothing to hold for it.
        self.assertEqual(self._observed(REPO_SLUG), frozenset(), "a close that ends nothing is not kept")

    def ticked_once_released(self, *, limit: int, scheduled: bool) -> None:
        """The tick after the holder lets go, which runs every issue."""
        retry = StandInHandler()
        self.ticked(retry, limit=limit, scheduled=scheduled)

        self.assertEqual(set(retry.ran), set(ALL_ISSUES), "a released issue runs again")
        self.assertEqual(self.written_issues(), set(ALL_ISSUES))
