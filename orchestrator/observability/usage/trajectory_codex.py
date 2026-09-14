# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct an ordered Codex trajectory from its stream items.

Codex emits several frames per operation -- started, then any updates, then
completed -- so this owner correlates them by `item.id` and keeps each item at
the position its first frame took. `trajectory_codex_payloads` owns their accumulated payloads and step projection;
`trajectory_codex_items` beside it decides
what each item type contributes, down to which frame's invocation an item is
recorded under; everything here is the correlation, the ordering, and the
frames a stream can carry without an id at all.

The id is what makes an operation one item rather than several, so a wrapper
frame reporting the id of the call nested inside it merges into that call
instead of doubling it -- and, when the wrapper is of a type nothing
normalizes, it neither replaces the normalized pair with a placeholder nor
adds one beside it. Nor does it survive inside one: a placeholder is named
after the wrapper's own type and payloaded with the wrapper's own status, so
the normalized frame replaces it whole rather than merging into it, and an
item the normalized frame reported no invocation for is left with none.

The same correlation is what lets this owner say where every identified item
went. One `SourceItem` per id, in first-seen order, records the disposition
the parser settled on, so a run's steps can be read against the items behind
them: a step-less item is a classification here rather than an id that
quietly stopped existing between the stream and the record. Only the id makes
that accounting possible, so a frame the stream left unidentified contributes
its steps and nothing else -- there is no name to account it under, and every
such frame would otherwise share one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage import (
    protocol,
    trajectory_codex_items as codex_items,
    trajectory_codex_payloads as codex_payloads,
)
from orchestrator.observability.usage.trajectory_models import (
    ITEM_EMPTY,
    ITEM_EXCLUDED,
    ITEM_STORED,
    ITEM_UNSUPPORTED,
    SourceItem,
    TrajectoryStep,
)

# How strong a claim one frame stakes on the id it reports. A wrapper the
# parser has no normalizer for carries the id of the call nested inside it, so
# the normalized frame names the item however the two are ordered -- the
# placeholder is what an id is left with only when no frame under it was ever
# claimed.
NORMALIZED_CLAIM = 3
UNSUPPORTED_CLAIM = 2
EXCLUDED_CLAIM = 1
UNTYPED_CLAIM = 0


def final_output(events: Iterable[dict[str, Any]]) -> str | None:
    final_text: str | None = None
    for event in events:
        stream_item = event.get(protocol.ITEM_KEY)
        if not isinstance(stream_item, dict):
            continue
        if stream_item.get(protocol.TYPE) != codex_items.AGENT_MESSAGE:
            continue
        candidate = stream_item.get(codex_items.TEXT)
        if isinstance(candidate, str):
            final_text = candidate
    return final_text


def reconstruct(events: Iterable[dict[str, Any]]) -> CodexTimeline:
    """Fold one codex stream into its steps and the items behind them."""
    builder = CodexTrajectoryBuilder()
    for event in events:
        builder.add_event(event)
    return builder.build()


@dataclass(frozen=True)
class CodexTimeline:
    """One run's ordered steps beside the accounting of its source items."""

    steps: tuple[TrajectoryStep, ...] = ()
    source_items: tuple[SourceItem, ...] = ()


@dataclass(frozen=True)
class ItemClaim:
    """The frame that currently names one item, and how strongly."""

    item_type: str
    strength: int

    def disposition(self, has_steps: bool) -> str:
        """Classify the item this claim named, given what it contributed."""
        if self.strength == UNSUPPORTED_CLAIM:
            return ITEM_UNSUPPORTED
        if self.strength == EXCLUDED_CLAIM:
            return ITEM_EXCLUDED
        return ITEM_STORED if has_steps else ITEM_EMPTY


def frame_claim(
    stream_item: dict[str, Any],
    payloads: codex_payloads.CodexItemPayloads | None,
) -> ItemClaim:
    """Read what one frame says about the item it reports under.

    The normalizer already separates a claimed type from an unclaimed one, so
    the only reading left here is the pair it declines to normalize at all: a
    reasoning item, whose exclusion is deliberate and whose hidden text is
    what the exclusion exists to keep out, and a frame too malformed to name a
    type, which cannot be classified any further than the id it arrived with.
    """
    item_type = stream_item.get(protocol.TYPE)
    named = item_type if isinstance(item_type, str) else ""
    if payloads is None:
        excluded = named == codex_items.REASONING
        return ItemClaim(named, EXCLUDED_CLAIM if excluded else UNTYPED_CLAIM)
    if payloads.kind == codex_payloads.UNSUPPORTED_ITEM:
        return ItemClaim(named, UNSUPPORTED_CLAIM)
    return ItemClaim(named, NORMALIZED_CLAIM)


@dataclass
class CodexTrajectoryBuilder:
    """Frames folded into one record per item, in first-seen order."""

    order: list[str] = field(default_factory=list)
    by_id: dict[str, codex_payloads.CodexItemPayloads] = field(default_factory=dict)
    anonymous: list[TrajectoryStep] = field(default_factory=list)
    claims: dict[str, ItemClaim] = field(default_factory=dict)

    def add_event(self, event: dict[str, Any]) -> None:
        stream_item = event.get(protocol.ITEM_KEY)
        if not isinstance(stream_item, dict):
            return
        payloads = codex_items.normalize_item(
            stream_item,
            event.get(protocol.TYPE) == codex_items.ITEM_COMPLETED,
        )
        item_id = self._item_id(stream_item)
        if item_id:
            self._claim(item_id, frame_claim(stream_item, payloads))
        if payloads is None:
            return
        if item_id:
            self._absorb(item_id, payloads)
            return
        # Nothing correlates frames a stream left unidentified, so each one
        # stands on its own and trails the ordered items rather than claiming
        # a position between two of them.
        self.anonymous.extend(payloads.steps(""))

    def build(self) -> CodexTimeline:
        steps: list[TrajectoryStep] = []
        recorded_ids: set[str] = set()
        for item_id in self.order:
            item_steps = self.by_id[item_id].steps(item_id)
            if item_steps:
                recorded_ids.add(item_id)
            steps.extend(item_steps)
        steps.extend(self.anonymous)
        return CodexTimeline(tuple(steps), self._source_items(recorded_ids))

    def _source_items(self, recorded_ids: set[str]) -> tuple[SourceItem, ...]:
        return tuple(
            SourceItem(
                item_id,
                claim.item_type,
                claim.disposition(item_id in recorded_ids),
            )
            for item_id, claim in self.claims.items()
        )

    def _item_id(self, stream_item: dict[str, Any]) -> str:
        raw_id = stream_item.get(protocol.ID)
        return raw_id if isinstance(raw_id, str) else ""

    def _claim(self, item_id: str, claim: ItemClaim) -> None:
        # Assigning an id already present keeps its first-seen position, so
        # the strongest frame renames the item without reordering it.
        recorded = self.claims.get(item_id)
        if recorded is None or claim.strength > recorded.strength:
            self.claims[item_id] = claim

    def _absorb(
        self,
        item_id: str,
        payloads: codex_payloads.CodexItemPayloads,
    ) -> None:
        recorded = self.by_id.get(item_id)
        if recorded is None:
            self.order.append(item_id)
            self.by_id[item_id] = payloads
            return
        placeholder = codex_payloads.UNSUPPORTED_ITEM
        if payloads.kind == placeholder and recorded.kind != placeholder:
            # One operation is one item however many frames wrap it. A frame
            # nothing claims -- an outer tool call the parser has no
            # normalizer for, reporting the same id as the web search or MCP
            # call nested inside it -- neither demotes the pair another frame
            # already named nor becomes a second step beside it.
            return
        if recorded.kind == placeholder and payloads.kind != placeholder:
            # Arriving in the other order, the normalized frame replaces the
            # placeholder rather than merging into it: a placeholder's name is
            # the wrapper's own item type and its payload the wrapper's own
            # status, and neither says anything about the call underneath. A
            # merge would leave whichever of them the normalized frame did not
            # fill standing as the item's -- an agent message the run never
            # spoke, reading back as the wrapper's status.
            self.by_id[item_id] = payloads
            return
        recorded.kind = payloads.kind
        recorded.name = payloads.name or recorded.name
        if payloads.contributes_call(recorded.call_payload):
            recorded.call_payload = payloads.call_payload
        if payloads.result_payload is not codex_payloads.MISSING:
            recorded.result_payload = payloads.result_payload
