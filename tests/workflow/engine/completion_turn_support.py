# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What happens to a captured issue between its capture and the dispatch that decides on it.

Each turn is somebody else's move -- a human relabelling, closing, or
commenting on the issue, a commit or reset in the checkout, a push to or a
close of the pull request, a hand edit of the pinned comment -- or a request
GitHub leaves unanswered while the dispatch reads. None of them is a second
orchestrator writer: the dispatch holds the issue's claim, so every move is
made before it, and an unanswered request is one the dispatch makes itself.
"""
from __future__ import annotations

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.state import WorkflowLabel
from tests.support.github.models import FakeComment, FakeLabel, FakeUser
from tests.workflow.engine import completion_recovery_support as _support

# The one request whose first answer the dispatch needs and whose later ones a turn may leave unanswered.
_PINNED_READ = "read_pinned_state"

_HUMAN = FakeUser("alice")

_COMMENT_ID = 10_000

_DROPPED = _support.DROPPED


@dataclass(frozen=True)
class Turn:
    """One move, every member left as it is unless named.

    `labels` are the issue's labels now, and `refetched` the ones a fetch of
    it during the dispatch reads -- a control applied meanwhile; `comment` a
    human's added to the thread; `head` and `identity` the checkout's;
    `pull_request` the state, merge, and head its pull request is read with; `edits`
    a hand edit of the pinned comment (`CapturedWorld.hand_edit`) and
    `members` one of the capture's own members; `unanswered` a client request
    GitHub leaves unanswered during the dispatch -- the pinned read's second
    and every later one.
    """

    labels: tuple[str, ...] | None = None
    refetched: tuple[str, ...] | None = None
    closed: bool = False
    comment: str = ""
    head: str | None = None
    identity: ProbeAnswer | None = None
    pull_request: Mapping = field(default_factory=lambda: MappingProxyType({}))
    edits: Mapping = field(default_factory=lambda: MappingProxyType({}))
    members: Mapping = field(default_factory=lambda: MappingProxyType({}))
    unanswered: str = ""


@dataclass(frozen=True)
class Case:
    """One case of a table: the move, what the dispatch says it found, and the world it is made on.

    `run` overrides the captured run, as `(member, value)` pairs; `label` is
    the stage the issue is on and `road` the one the capture was taken on
    (`road()`), the first implementation's where None.
    """

    turn: Turn
    reason: object
    pull_request: bool = False
    run: tuple = ()
    label: WorkflowLabel = WorkflowLabel.IMPLEMENTING
    road: tuple | None = None


def turned(world: _support.CapturedWorld, turn: Turn) -> contextlib.AbstractContextManager:
    """Make `turn`'s moves on `world`, and answer the block its unanswered request is left unanswered in."""
    if turn.labels is not None:
        world.issue.labels = [FakeLabel(name) for name in turn.labels]
    world.issue.closed = world.issue.closed or turn.closed
    if turn.comment:
        commented = FakeComment(id=_COMMENT_ID, body=turn.comment, user=_HUMAN)
        world.issue.comments.append(commented)
    world.head = world.head if turn.head is None else turn.head
    world.identity = turn.identity or world.identity
    world.hand_edit(**turn.edits)
    _moved_capture(world, turn.members)
    _moved_pull_request(world, turn.pull_request)
    return _unanswered(world, turn)


def _unanswered(world: _support.CapturedWorld, turn: Turn) -> contextlib.AbstractContextManager:
    """The block `turn`'s unanswered request, or its refetch under other labels, is answered that way in."""
    if turn.refetched is not None:
        labels = [FakeLabel(name) for name in turn.refetched]
        return patch.object(world.github, "get_issue", return_value=replace(world.issue, labels=labels))
    if turn.unanswered == _PINNED_READ:
        return patch.object(world.github, _PINNED_READ, side_effect=_AnsweredOnce(world.github.read_pinned_state))
    if turn.unanswered:
        return patch.object(world.github, turn.unanswered, side_effect=RuntimeError(f"{turn.unanswered} unanswered"))
    return contextlib.nullcontext()


def _moved_capture(world: _support.CapturedWorld, members: Mapping) -> None:
    """A hand edit of the capture's own `members`: each set, or taken off where given `DROPPED`."""
    if not members:
        return
    spelled = {**world.record()[_support.FIELD], **members}
    kept = {member: spelling for member, spelling in spelled.items() if spelling is not _DROPPED}
    world.hand_edit(**{_support.FIELD: kept})


def _moved_pull_request(world: _support.CapturedWorld, moves: Mapping) -> None:
    """Move the recorded pull request: its `state`, whether it was `merged`, and the `sha` its head stands on."""
    if not moves:
        return
    pull_request = world.github.get_pr(_support.PR_NUMBER)
    pull_request.state = moves.get("state", pull_request.state)
    pull_request.merged = moves.get("merged", pull_request.merged)
    pull_request.head.sha = moves.get("sha", pull_request.head.sha)


class _AnsweredOnce:
    """A read answered the first time, as the dispatch's own reading, and left unanswered every time after."""

    def __init__(self, reader) -> None:
        self._reader = reader
        self._answered = False

    def __call__(self, issue):
        """The first reading, or the request left unanswered."""
        if self._answered:
            raise RuntimeError("the pinned comment would not read")
        self._answered = True
        return self._reader(issue)
