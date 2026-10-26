# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The immutable pieces one trajectory record is read back as.

A step, a timeline entry, and the two usage summaries are frozen dataclasses,
so the page can hand the same object to a filter, a table, and a detail card
without any of them being able to edit the record underneath the others.

The two that carry a body are built through a declared signature rather than
the generated ``__init__``. Their field is ``step_content`` / ``entry_content``
-- a dataclass cannot hold a field and a property of the same name -- while the
keyword a caller passes and the attribute it reads back are both ``content``,
which is the spelling the sink writes a step's body under and the one every
reader here names. Binding the call against that signature is what keeps
positional construction, keyword construction, and ``inspect.signature`` all
reporting the one public shape.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from orchestrator.observability.trajectory_viewer import constants

KIND_FIELD = "kind"
NAME_FIELD = "name"
TOOL_ID_FIELD = "tool_id"
CONTENT_FIELD = "content"
TURN_FIELD = "turn"
STEP_VIEW_SIGNATURE = inspect.Signature(
    parameters=(
        inspect.Parameter(KIND_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(NAME_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TOOL_ID_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(CONTENT_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TURN_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
    )
)
TIMELINE_ENTRY_SIGNATURE = inspect.Signature(
    parameters=(
        inspect.Parameter(KIND_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(CONTENT_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(NAME_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TOOL_ID_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TURN_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
    )
)


def public_step_content(step: TrajectoryStepView) -> str:
    """Return a step body through its public `content` name."""
    return step.step_content


def public_entry_content(entry: TimelineEntry) -> str:
    """Return a timeline body through its public `content` name."""
    return entry.entry_content


@dataclass(frozen=True, init=False)
class TrajectoryStepView:
    """One normalized step from a trajectory record."""

    kind: str
    name: str = ""
    tool_id: str = ""
    step_content: str = ""
    turn: int | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        bound = STEP_VIEW_SIGNATURE.bind(*args, **kwargs)
        bound.apply_defaults()
        object.__setattr__(self, KIND_FIELD, bound.arguments[KIND_FIELD])
        object.__setattr__(self, NAME_FIELD, bound.arguments[NAME_FIELD])
        object.__setattr__(self, TOOL_ID_FIELD, bound.arguments[TOOL_ID_FIELD])
        object.__setattr__(self, "step_content", bound.arguments[CONTENT_FIELD])
        object.__setattr__(self, TURN_FIELD, bound.arguments[TURN_FIELD])

    @property
    def is_call(self) -> bool:
        return self.kind == "tool_call"

    @property
    def is_result(self) -> bool:
        return self.kind == "tool_result"


@dataclass(frozen=True, init=False)
class TimelineEntry:
    """One normalized prompt, step, or output timeline entry."""

    kind: str
    entry_content: str = ""
    name: str = ""
    tool_id: str = ""
    turn: int | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        bound = TIMELINE_ENTRY_SIGNATURE.bind(*args, **kwargs)
        bound.apply_defaults()
        object.__setattr__(self, KIND_FIELD, bound.arguments[KIND_FIELD])
        object.__setattr__(self, "entry_content", bound.arguments[CONTENT_FIELD])
        object.__setattr__(self, NAME_FIELD, bound.arguments[NAME_FIELD])
        object.__setattr__(self, TOOL_ID_FIELD, bound.arguments[TOOL_ID_FIELD])
        object.__setattr__(self, TURN_FIELD, bound.arguments[TURN_FIELD])

    @property
    def is_prompt(self) -> bool:
        return self.kind == constants.TIMELINE_PROMPT

    @property
    def is_output(self) -> bool:
        return self.kind == constants.TIMELINE_OUTPUT


@dataclass(frozen=True)
class TurnUsageView:
    """Per-turn token usage for one Claude assistant turn."""

    turn: int | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class RunUsageView:
    """Run-level usage summary stored on a trajectory record."""

    models: tuple[str, ...] = ()
    turns: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


setattr(TrajectoryStepView, CONTENT_FIELD, property(public_step_content))
setattr(TimelineEntry, CONTENT_FIELD, property(public_entry_content))
TrajectoryStepView.__signature__ = STEP_VIEW_SIGNATURE
TimelineEntry.__signature__ = TIMELINE_ENTRY_SIGNATURE
