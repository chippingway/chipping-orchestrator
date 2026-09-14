# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex frame payloads and their ordered trajectory steps.

The item normalizers fill these records; the timeline builder merges them by
item identity. A shared missing-field sentinel preserves earlier frame values
when a later frame omits them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.observability.usage.trajectory_models import TrajectoryStep

ASSISTANT_MESSAGE = "assistant_message"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
UNSUPPORTED_ITEM = "unsupported_item"

MISSING = object()


@dataclass
class CodexItemPayloads:
    """The step family one item belongs to and the payloads it carries.

    `MISSING` is what separates a field a frame did not carry from one it
    carried empty: the builder merges frame by frame and only overwrites what
    a frame actually reported, so a completed frame that omits a field leaves
    the started frame's value standing.
    """

    kind: str
    name: str = ""
    call_payload: Any = MISSING
    result_payload: Any = MISSING
    keeps_first_call: bool = False

    def contributes_call(self, recorded_call: Any) -> bool:
        """Whether this frame's invocation replaces the one already recorded.

        An item codex republishes whole on every frame -- a plan, rewritten as
        it is worked through -- is invoked once, by the frame that opened it,
        so a later frame revises the outcome rather than the call. Every other
        item is named by whichever frame filled the field last, which is how a
        search that announces itself with an empty query is still recorded
        under the one it ran.
        """
        if self.call_payload is MISSING:
            return False
        return not (self.keeps_first_call and recorded_call is not MISSING)

    def steps(self, tool_id: str) -> tuple[TrajectoryStep, ...]:
        """Order what this item accumulated into the steps it contributes."""
        if self.kind == ASSISTANT_MESSAGE:
            if self.call_payload is MISSING:
                return ()
            return (
                TrajectoryStep(
                    kind=ASSISTANT_MESSAGE,
                    content=self.call_payload,
                ),
            )
        if self.kind == UNSUPPORTED_ITEM:
            return (
                TrajectoryStep(
                    kind=UNSUPPORTED_ITEM,
                    name=self.name,
                    tool_id=tool_id,
                    content=self.call_payload,
                ),
            )
        return self._tool_steps(tool_id)

    def _tool_steps(self, tool_id: str) -> tuple[TrajectoryStep, ...]:
        tool_steps: list[TrajectoryStep] = []
        if self.call_payload is not MISSING:
            tool_steps.append(
                TrajectoryStep(
                    kind=TOOL_CALL,
                    name=self.name,
                    tool_id=tool_id,
                    content=self.call_payload,
                ),
            )
        if self.result_payload is not MISSING:
            tool_steps.append(
                TrajectoryStep(
                    kind=TOOL_RESULT,
                    tool_id=tool_id,
                    content=self.result_payload,
                ),
            )
        return tuple(tool_steps)
