# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dispatch a captured completion is decided in, the stage handler and the road's owner stood in for.

The road's owner is resolved by name, as the recovery resolves every owner
(`completion_recovery.ROUTE_OWNERS`), so a case installs one here rather than
patching the recovery's own call. With none installed no road has an owner,
as in this build. What one dispatch did is read back whole (`observed`): the
handlers it reached, what the owner was handed, the pinned comment before
and after, the pinned writes sent, and what the dispatch said.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import (
    completion_recovery as _recovery,
    completion_routes as _routes,
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from tests.workflow.engine import completion_recovery_support as _support, completion_turn_support as _turns
from tests.workflow.fixtures import _TEST_SPEC

_WORKFLOW_LOG = "orchestrator.workflow"


class RoadOwner:
    """The owner a case hands every road to: it keeps what it is handed and answers whether the tick stops.

    `installed` is the one a case has installed, which the owner every road
    names resolves to.
    """

    installed: RoadOwner | None = None

    def __init__(self, stops: bool = True) -> None:
        self.handed: list = []
        self._stops = stops

    def __call__(self, admitted) -> bool:
        """Keep `admitted`, and stop the tick or let it carry on."""
        self.handed.append(admitted)
        return self._stops


# Every road owned by the installed owner, as the defining module and the function taking the handoff.
ROAD_OWNERS = MappingProxyType(dict.fromkeys(_routes.CompletionRoute, (__name__, "take")))


def take(admitted) -> bool:
    """Hand `admitted` to the installed owner."""
    return RoadOwner.installed(admitted)


def owned(owner: RoadOwner) -> contextlib.AbstractContextManager:
    """Every road owned by `owner` for the block."""
    owning = contextlib.ExitStack()
    owning.enter_context(patch.object(_recovery, "ROUTE_OWNERS", ROAD_OWNERS))
    owning.enter_context(patch.object(RoadOwner, "installed", owner))
    return owning


@dataclass(frozen=True)
class Observed:
    """What one dispatch did: the handlers it ran, the handoffs its owner kept, the record around it, and what it said.

    `writes` counts the pinned writes the dispatch sent.
    """

    ran: tuple
    handed: tuple
    before: dict
    after: dict
    writes: int
    said: str

    @property
    def untouched(self) -> bool:
        """Whether the dispatch left the pinned comment exactly as it found it, with nothing sent."""
        return self.before == self.after and not self.writes

    def says(self, reason, standing=None) -> bool:
        """Whether the dispatch said it decided for `reason` -- under `standing`, where it held the tick."""
        decided = f"({reason})" if standing is None else f"({standing}: {reason})"
        return decided in self.said


def observed(
    world: _support.CapturedWorld,
    owner: RoadOwner | None = None,
    turn: _turns.Turn | None = None,
) -> Observed:
    """Make `turn`'s moves, then dispatch the world's issue once, its stage handler stood in for."""
    return _Dispatch(world, owner).run(turn or _turns.Turn())


class _Dispatch:
    """One dispatch of a world's issue, and what it reached."""

    def __init__(self, world: _support.CapturedWorld, owner: RoadOwner | None) -> None:
        self._world = world
        self._owner = owner
        self._ran: list[int] = []
        self._said = _Said()

    def run(self, turn: _turns.Turn) -> Observed:
        """Make `turn`'s moves, dispatch once, and read back what that did."""
        unanswered = _turns.turned(self._world, turn)
        before, writes = self._world.record(), self._world.github.write_state_calls
        with self._seams(unanswered):
            _issue_processing._process_issue(self._world.github, _TEST_SPEC, self._world.issue)
        handed = () if self._owner is None else tuple(self._owner.handed)
        return Observed(
            ran=tuple(self._ran),
            handed=handed,
            before=before,
            after=self._world.record(),
            writes=self._world.github.write_state_calls - writes,
            said="\n".join(self._said.lines),
        )

    def _seams(self, unanswered: contextlib.AbstractContextManager) -> contextlib.ExitStack:
        """The request left unanswered, the checkout, the handler, the road's owner, and the channel listened on."""
        seams = contextlib.ExitStack()
        seams.enter_context(unanswered)
        seams.enter_context(self._world.checkout())
        seams.enter_context(patch.object(_stage_targets, "_call_handler", self._handled))
        if self._owner is not None:
            seams.enter_context(owned(self._owner))
        seams.enter_context(self._said.listening())
        return seams

    def _handled(self, _gh, _spec, issue, _target) -> None:
        self._ran.append(issue.number)


class _Said(logging.Handler):
    """Every line the dispatch said on the workflow's channel."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the line."""
        self.lines.append(record.getMessage())

    @contextlib.contextmanager
    def listening(self):
        """Listen on the workflow's channel at INFO for the block, as `assertLogs` would."""
        channel = logging.getLogger(_WORKFLOW_LOG)
        level = channel.level
        channel.addHandler(self)
        channel.setLevel(logging.INFO)
        try:
            yield
        finally:
            channel.setLevel(level)
            channel.removeHandler(self)
