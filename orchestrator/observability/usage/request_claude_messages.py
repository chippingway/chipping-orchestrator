# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One Claude request folded from every frame that names it, and the usage that request settled on.

What the frames carry is pinned to Claude Code 2.1.295, the captures the run accounting is: an API message prints a
`message_start` stream event and one `assistant` frame per content block, each repeating the usage it started with,
and a `message_delta` stream event naming it through its wrapper's `api_message_id` and carrying its final output
count, thinking included. So a message is folded counter by counter. Its input, cache-read, and cache-write counters
are the same on every frame that reports them: a repeated frame adds nothing, and two disagreeing make that counter
`conflicting`. Its output and thinking are settled: a closing `message_delta` replaces the counts the message started
with rather than adding to them, two closing reports disagreeing contradict each other, and a message no closing
report reached keeps its start counts as provisional. A closing report that breaks out the thinking but reports no
output settles the thinking alone (`message-delta-partial`): the output is missing rather than the start count, which
a final thinking count beside it would contradict. Where `modelUsage` settled a subagent message's output instead, the
frames' start count stays what was reported and the settled count is what the request is normalized from, beside any
thinking a closing report gave.

A subagent hand-back is the output of the message that closed the subagent, which printed no frame of its own, so it
is observed by its output and thinking alone and is final as soon as it is reported. Its input and cache counters are
never recorded: they are kept apart only to check that a `modelUsage` settlement summing them reads them as whole
counts too.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, NamedTuple

from orchestrator.observability.usage import (
    claude_requests,
    protocol,
    request_models,
    request_normalization as normalization,
)
from orchestrator.observability.usage.request_claude_counters import COUNTERS, SETTLED, Readings
from orchestrator.observability.usage.request_claude_reports import SESSION_ID
from orchestrator.observability.usage.request_normalization import Reading
from orchestrator.observability.usage.request_scan import Metadata

# A closing report that settled the thinking it broke out but reported no output.
SETTLED_IN_PART = "message-delta-partial"
# What a `modelUsage` settlement sums of each request: its prompt by class, and the output of one it does not settle.
_SETTLEMENT_FIELDS = (
    normalization.CONTEXT_INPUT_TOKENS,
    normalization.CACHE_READ_TOKENS,
    normalization.CACHE_WRITE_TOKENS,
    normalization.OUTPUT_TOKENS,
)
_PROMPT_FIELDS = _SETTLEMENT_FIELDS[:-1]
# Every set of counters a request folds its frames into.
_READINGS = ("shared", "start", "final", "prompt")


def fold(target: Readings, readings: Readings) -> None:
    """Fold one report into what earlier ones established: an agreeing count adds nothing, another conflicts."""
    for counter, reading in readings.items():
        if target.setdefault(counter, reading) != reading:
            target[counter] = Reading(state=normalization.CONFLICTING)


@dataclass(frozen=True)
class Names:
    """The identities and metadata the frames of one request named, each the first a frame gave.

    A model a frame named that this collection refused reads `REFUSED`, which a model a later frame names and this
    collection keeps completes, as it completes a name no frame gave.
    """

    message_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    model: str | None = None
    timestamp: str | None = None

    def merged(self, later: Names) -> Names:
        """These names, completed by what a later frame named that no earlier one did, or did and was refused."""
        completed: dict[str, str] = {}
        for name in _NAME_FIELDS:
            text = getattr(later, name)
            if text is not None and not getattr(self, name):
                completed[name] = text
        return replace(self, **completed)


_NAME_FIELDS = tuple(name_field.name for name_field in fields(Names))


def handback_names(
    metadata: Metadata,
    event: dict[str, Any],
    handback: dict[str, Any],
) -> Names:
    """What one subagent hand-back names: its agent and the model it resolved to, on its `tool_use_result`."""
    return Names(
        session_id=metadata.text(event.get(SESSION_ID)),
        agent_id=metadata.text(handback.get("agentId")),
        model=metadata.text(handback.get("resolvedModel")),
        timestamp=metadata.text(event.get("timestamp")),
    )


def _normalized(readings: Readings) -> normalization.NormalizedUsage:
    neutral = {COUNTERS[name]: reading for name, reading in readings.items()}
    return normalization.normalize(protocol.CLAUDE, neutral)


class SettledUsage(NamedTuple):
    """The counters one request reported, the ones it is normalized from, their status, and what settled them."""

    raw: Readings
    readings: Readings
    status: str
    settlement: str

    def normalized(self) -> normalization.NormalizedUsage:
        return _normalized(self.readings)


@dataclass
class RequestFold:
    """Everything the stream said about one request, in the order it said it.

    `position` is the line the request was first printed on, `branch` the subagent call whose branch it is on -- None
    on the lead thread, or for a subagent whose call this collection refused to name, which `subagent` still marks --
    `key` the key the trajectory's settlement knows it by, where it knows it at all, and `turn` the trajectory turn an
    `assistant` frame of it was numbered under, by the turn key in `turn_key` -- its link only where that key is `key`,
    the turn settled as it is. `prompt` holds a hand-back's input and cache counters, which its observation never
    records.
    """

    position: int
    key: str | None = None
    branch: str | None = None
    subagent: bool = False
    handback: bool = False
    turn: int | None = None
    turn_key: str | None = None
    names: Names = field(default_factory=Names)
    shared: Readings = field(default_factory=dict)
    start: Readings = field(default_factory=dict)
    final: Readings = field(default_factory=dict)
    prompt: Readings = field(default_factory=dict)

    @property
    def reported(self) -> bool:
        """Whether any frame of the request carried a counter."""
        return bool(self.shared or self.start or self.final)

    def labelled(self) -> tuple[str, str]:
        """What the request is called, and what kind of name that is: an id the stream gave, or else its first line."""
        if self.handback and self.branch is not None:
            return f"handback:{self.branch}", request_models.HANDBACK_CALL
        if self.names.message_id is not None:
            return self.names.message_id, request_models.API_MESSAGE
        if self.names.request_id is not None:
            return self.names.request_id, request_models.API_REQUEST
        return f"position:{self.position}", request_models.SOURCE_POSITION

    def absorb(self, readings: Readings, *, closing: bool) -> None:
        """Fold one frame's counters: the settled ones as a start or a closing report, the rest as shared.

        A hand-back observes its message's output alone, so the rest of its counters are kept apart as its prompt.
        """
        settled = {name: reading for name, reading in readings.items() if name in SETTLED}
        fold(self.final if closing else self.start, settled)
        shared = {name: reading for name, reading in readings.items() if name not in SETTLED}
        fold(self.prompt if self.handback else self.shared, shared)

    def placed(self, branch: str | None, *, subagent: bool) -> bool:
        """Complete the request's branch with what one more frame named; False where it names another call."""
        if branch is not None and self.branch not in {None, branch}:
            return False
        self.branch = self.branch or branch
        self.subagent = self.subagent or subagent
        return True

    def joined(self, later: RequestFold, key: str) -> bool:
        """Fold a later-printed request the stream showed to be this one, settled under `key`; False on a branch clash.

        The joined request is first printed where this one was, keeps the names this one gave first, and folds every
        counter the other reported as a repeated frame of it would. Of the two turns, it keeps the one numbered under
        `key` -- the turn holding its settled output -- and failing that the one this request gave first.
        """
        numbered = later.turn_key == key or self.turn is None
        if numbered and self.turn_key != key:
            self.turn = later.turn
            self.turn_key = later.turn_key
        self.key = key
        self.names = self.names.merged(later.names)
        for readings in _READINGS:
            fold(getattr(self, readings), getattr(later, readings))
        return self.placed(later.branch, subagent=later.subagent)

    def counts(self, *, output: bool) -> tuple[int, ...] | None:
        """The request's context input, cache reads, cache writes, and -- where `output` -- output, as read here.

        None where any of them is no whole count here: the run accounting reads some counters this collection cannot
        -- a fraction as the whole number it truncates to -- and leaves out some it can, such as a lifetime spelled as
        a string, so a settlement it derived is held to the counts this collection reads instead.
        """
        fields = _normalized({**self.prompt, **self.shared, **self.start, **self.final}).fields
        names = _SETTLEMENT_FIELDS if output else _PROMPT_FIELDS
        summed = [fields[name] for name in names]
        if not all(reading.known for reading in summed):
            return None
        counted = tuple(reading.count or 0 for reading in summed)
        return counted if output else (*counted, 0)

    def usage(self, reconciled: int | None) -> SettledUsage:
        """The usage the request settled on, `reconciled` the output `modelUsage` settled it to where it did.

        A closing report's output outranks that settlement, which only ever settles a message no closing report gave an
        output; what a closing report did give -- its thinking -- is kept either way.
        """
        if self.handback:
            return SettledUsage(self.final, self.final, request_models.FINAL, claude_requests.SETTLED_BY_HANDBACK)
        if protocol.OUTPUT_TOKENS in self.final:
            closed = {**self.shared, **self.final}
            return SettledUsage(closed, closed, request_models.FINAL, claude_requests.SETTLED_BY_DELTA)
        reported = {**self.shared, **self.start, **self.final}
        if reconciled is not None:
            settled = {**self.shared, **self.final, protocol.OUTPUT_TOKENS: Reading(reconciled, normalization.OBSERVED)}
            return SettledUsage(reported, settled, request_models.FINAL, claude_requests.SETTLED_BY_MODEL_USAGE)
        if self.final:
            partial = {**self.shared, **self.final}
            return SettledUsage(partial, partial, request_models.FINAL, SETTLED_IN_PART)
        return SettledUsage(reported, reported, request_models.PROVISIONAL, claude_requests.SETTLED_AT_START)
