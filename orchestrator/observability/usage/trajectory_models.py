# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory records one parsed run is reconstructed into.

Two of the records here answer different questions about the same run. The
ordered `TrajectoryStep` list is what the run *did*; the `SourceItem` list
beside it is what the parser did with every item the provider stream
identified, so an id that reaches no step is a decision this record names
rather than a silence a reader has to reconstruct.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage.skills import SkillTriggers

KIND_FIELD = "kind"
NAME_FIELD = "name"
TOOL_ID_FIELD = "tool_id"
TURN_FIELD = "turn"
CONTENT_FIELD = "content"
ITEM_ID_FIELD = "item_id"
ITEM_TYPE_FIELD = "item_type"
DISPOSITION_FIELD = "disposition"

# Where one identified source item ended up. The four are exhaustive by
# construction -- a parser assigns exactly one per id -- which is what lets a
# reader tell an item the parser held back from one it never saw.
ITEM_STORED = "stored"
ITEM_UNSUPPORTED = "unsupported"
ITEM_EXCLUDED = "excluded"
ITEM_EMPTY = "empty"
STEP_SIGNATURE = inspect.Signature(
    parameters=(
        inspect.Parameter(KIND_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(NAME_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TOOL_ID_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=""),
        inspect.Parameter(TURN_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
        inspect.Parameter(CONTENT_FIELD, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
    )
)


def public_step_content(step: TrajectoryStep) -> Any:
    """Return a step payload through the `content` name it is serialized under."""
    return step.step_payload


@dataclass(frozen=True, init=False)
class TrajectoryStep:
    """One ordered message, tool call, or tool result in an agent run."""

    kind: str
    name: str = ""
    tool_id: str = ""
    turn: int | None = None
    step_payload: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        bound = STEP_SIGNATURE.bind(*args, **kwargs)
        bound.apply_defaults()
        object.__setattr__(self, KIND_FIELD, bound.arguments[KIND_FIELD])
        object.__setattr__(self, NAME_FIELD, bound.arguments[NAME_FIELD])
        object.__setattr__(self, TOOL_ID_FIELD, bound.arguments[TOOL_ID_FIELD])
        object.__setattr__(self, TURN_FIELD, bound.arguments[TURN_FIELD])
        object.__setattr__(self, "step_payload", bound.arguments[CONTENT_FIELD])

    def to_dict(self) -> dict[str, Any]:
        return {
            KIND_FIELD: self.kind,
            NAME_FIELD: self.name,
            TOOL_ID_FIELD: self.tool_id,
            TURN_FIELD: self.turn,
            CONTENT_FIELD: self.step_payload,
        }


@dataclass(frozen=True)
class SourceItem:
    """One identified provider stream item, and where the parser put it.

    The provider identifies an item once and then reports it over as many
    frames as it takes, so one of these stands for the whole item rather than
    for a frame of it. `disposition` is the classification the parser settled
    on: `stored` when the item's own steps are in the trajectory, `unsupported`
    when nothing normalized its type and a placeholder step names it instead,
    `excluded` when the parser deliberately keeps neither the item nor its
    payload, and `empty` when its frames carried nothing to store.

    A `stored` message item is the reason this record exists. A text turn is
    not a tool call and carries no `tool_id`, so the id the provider gave it
    has nowhere to live on the step itself -- and reusing the tool field for
    one would make a message look like a call to everything downstream that
    joins a result to its invocation by that field.
    """

    item_id: str
    item_type: str
    disposition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            ITEM_ID_FIELD: self.item_id,
            ITEM_TYPE_FIELD: self.item_type,
            DISPOSITION_FIELD: self.disposition,
        }


@dataclass(frozen=True)
class TurnUsage:
    """Per-turn token usage for one Claude assistant turn."""

    turn: int
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = "estimated"

    def to_dict(self) -> dict[str, Any]:
        return {
            TURN_FIELD: self.turn,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
            "cost_source": self.cost_source,
        }


@dataclass(frozen=True)
class AgentTrajectory:
    """Structured trajectory reconstructed from one agent JSONL stream."""

    backend: str
    system_prompt: str | None = None
    tools: tuple[str, ...] = ()
    skills: SkillTriggers = field(default_factory=SkillTriggers)
    steps: tuple[TrajectoryStep, ...] = ()
    source_items: tuple[SourceItem, ...] = ()
    final_output: str | None = None
    turns: tuple[TurnUsage, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "system_prompt": self.system_prompt,
            "tools": list(self.tools),
            "skills": {
                "triggered": list(self.skills.triggered),
                "trigger_counts": dict(self.skills.trigger_counts),
                "available": list(self.skills.available),
            },
            "steps": [step.to_dict() for step in self.steps],
            "source_items": [
                source_item.to_dict() for source_item in self.source_items
            ],
            "final_output": self.final_output,
            "turns": [turn_usage.to_dict() for turn_usage in self.turns],
        }


setattr(TrajectoryStep, CONTENT_FIELD, property(public_step_content))
TrajectoryStep.__signature__ = STEP_SIGNATURE
