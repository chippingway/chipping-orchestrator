# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The final handoff boundaries a landed base rewrite's finish can die at once its evidence is resolved.

Behind the evidence a finish settles, retires, or leaves to the fresh reviewer
comes the tail of its route: the announcement -- the notice on the pull
request, the `base_rebased` event, and the checkpoint that marks the head
announced -- then the relabel to `workflow:validating`, then the write that
retires the attempt. Each boundary (`BOUNDARIES`) is a process killed at one
of those steps, behind every write ahead of it: before the announcement's
notice is posted, so nothing marks the head announced; behind the notice and
before the event's record, so the retry finds the notice with no event
recorded or filed; behind that record and before the event, so the retry
finds the event recorded and asks the stream, which does not carry it; behind
the event and before the checkpoint, so the retry finds the notice and the
event with no mark beside them; behind the checkpoint and before the relabel,
so the retry reads the head as already announced; and behind the relabel and
before the retirement, so the retry reads the issue as already relabelled
too. A boundary can also stand for another road's move behind the call it
picks rather than a death (`Boundary.moving`).

The death is the process exiting (`sys.exit`): the handler around the
notice's post catches whatever an `Exception` would raise, to read the
conversation again, which no handler on the finish's road does for an exit.
The client's step answers as it always does on every other call, and is put
back behind the death (`dies_at`). Every client double these cases use -- the
in-memory one and the real-git finish's -- names its steps alike.
"""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine.rewrite_finish_readings import KEY_ANNOUNCED, KEY_ANNOUNCED_EVENT, KEY_PENDING_PUSH

# How the announcement of a landing opens on the pull request.
_ANNOUNCES = ":mag:"


@dataclass(frozen=True)
class Boundary:
    """Where a finish's tail dies: the client `step`, on the one call `kills` picks out of its arguments."""

    name: str
    step: str
    kills: Callable[..., bool]

    def dying(self, live: Callable) -> Callable:
        """`live`, the client's own step, killing the process on the call this boundary picks."""
        return partial(self._answers, live)

    def moving(self, live: Callable, move: Callable[[], object]) -> Callable:
        """`live`, the client's own step, with `move` made once, behind the call this boundary picks."""
        return partial(self._moves, live, move, [])

    def _answers(self, live: Callable, *args, **kwargs):
        if self.kills(*args, **kwargs):
            sys.exit(f"the process was killed {self.name}")
        return live(*args, **kwargs)

    def _moves(self, live: Callable, move: Callable[[], object], moved: list, *args, **kwargs):
        answered = live(*args, **kwargs)
        if not moved and self.kills(*args, **kwargs):
            moved.append(True)
            move()
        return answered


class _Picks:
    """Which call of a client step each boundary picks out of its arguments."""

    def announcing(self, _pr_number, body: str, *_args, **_kwargs) -> bool:
        """Whether a pull-request post is a landing's announcement."""
        return body.startswith(_ANNOUNCES)

    def filing(self, event: str, *_args, **_kwargs) -> bool:
        """Whether an event is the landing's `base_rebased`."""
        return event == "base_rebased"

    def recording(self, _issue, state, *, over: dict, **_options) -> bool:
        """Whether a pinned-comment edit is the record of the event being filed, which the comment lacks."""
        records = state.get(KEY_ANNOUNCED_EVENT) is not None
        return records and over.get(KEY_ANNOUNCED_EVENT) is None

    def checkpointing(self, _issue, state, *, over: dict, **_options) -> bool:
        """Whether a pinned-comment edit is the checkpoint marking the head announced, which the comment lacks."""
        marks = state.get(KEY_ANNOUNCED) is not None
        return marks and over.get(KEY_ANNOUNCED) is None

    def relabelling(self, _issue, label, *_args, **_kwargs) -> bool:
        """Whether a label write is the route to `workflow:validating`."""
        return label == WorkflowLabel.VALIDATING

    def retiring(self, _issue, state, *, over: dict, **_options) -> bool:
        """Whether a pinned-comment edit is the one that retires the attempt the comment still carries."""
        retires = state.get(KEY_PENDING_PUSH) is None
        return retires and over.get(KEY_PENDING_PUSH) is not None


_PICKS = _Picks()

BEFORE_THE_ANNOUNCEMENT = Boundary("before the announcement", "pr_comment", _PICKS.announcing)

BEFORE_THE_EVENT_RECORD = Boundary("noticed, before the event's record", "edit_pinned_state", _PICKS.recording)

BEFORE_THE_EVENT = Boundary("the event recorded, before it is filed", "emit_event", _PICKS.filing)

BEFORE_THE_CHECKPOINT = Boundary("said, before the checkpoint", "edit_pinned_state", _PICKS.checkpointing)

BEFORE_THE_RELABEL = Boundary("announced, before the relabel", "set_workflow_label", _PICKS.relabelling)

BEFORE_THE_RETIREMENT = Boundary("relabelled, before the retirement", "edit_pinned_state", _PICKS.retiring)

BOUNDARIES = (
    BEFORE_THE_ANNOUNCEMENT,
    BEFORE_THE_EVENT_RECORD,
    BEFORE_THE_EVENT,
    BEFORE_THE_CHECKPOINT,
    BEFORE_THE_RELABEL,
    BEFORE_THE_RETIREMENT,
)


def dies_at(client, boundary: Boundary | None, finishing: Callable[[], object]) -> None:
    """Run `finishing` with `client` killing the process at `boundary`; with no boundary, run it through."""
    if boundary is None:
        finishing()
        return
    dying = boundary.dying(getattr(client, boundary.step))
    with patch.object(client, boundary.step, dying), contextlib.suppress(SystemExit):
        finishing()


def stage_entries(client, issue_number: int) -> list[str]:
    """The stage every stage-entry event filed for `issue_number` names, oldest first."""
    return [
        event.get("stage") for event in client.recorded_events
        if event.get("event") == "stage_enter" and event.get("issue") == issue_number
    ]
