# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of a run's request usage one collection covered, and the field the observations ride in.

A collection's status is read off the gaps it recorded rather than set beside them, so the two cannot disagree. A
collection is `unavailable` where nothing could be read -- no stream event at all, or a collector that failed --
`source-limit-truncated` where a collection bound stopped the scan short of the whole invocation,
`storage-truncated` where the record kept fewer samples or markers than were observed, `incomplete` where the scan
covered the invocation but some request is missing, unsettled, unattributed, observed only in part, or contradicts
itself, `complete-empty` where it covered the invocation and found no request, and `complete` otherwise. Each gap is
kept as a reason code with the number of times it occurred, a vocabulary fixed here, so the reasons are bounded however
damaged a stream is.

The counts are kept with the scope they were taken over. Observed samples are the requests the scan found and retained
samples the ones the record kept; a scan a bound cut short is `partial`, so its count is never read as the
invocation's. Source limitations -- what a provider's stream never reports, such as timestamps or cache writes -- are
listed apart from the gaps, since they say nothing about whether this run's collection was whole.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import request_normalization as normalization
from orchestrator.observability.usage.request_models import (
    OUTPUT_SCOPE,
    PROVISIONAL,
    RequestMarker,
    RequestObservation,
    UsageCheckpoint,
)

UNAVAILABLE = "unavailable"
SOURCE_LIMIT_TRUNCATED = "source-limit-truncated"
STORAGE_TRUNCATED = "storage-truncated"
INCOMPLETE = "incomplete"
COMPLETE_EMPTY = "complete-empty"
COMPLETE = "complete"

INVOCATION_SCOPE = "invocation"
PARTIAL_SCOPE = "partial"
NO_SCOPE = "none"

# Nothing could be read.
COLLECTOR_ERROR = "collector-error"
NO_STREAM_EVENTS = "no-stream-events"
# A collection bound stopped the scan short of the whole invocation.
SCAN_LIMIT = "scan-limit"
OVERSIZE_LINES = "oversize-lines"
CORRELATION_LIMIT = "correlation-limit"
# The record kept fewer entries than the scan observed.
STORAGE_BUDGET = "storage-budget"
# The scan covered the invocation, but the evidence in it does not.
MALFORMED_LINES = "malformed-lines"
NO_TERMINAL_RESULT = "no-terminal-result"
UNSETTLED_STEPS = "unsettled-steps"
UNREPORTED_USAGE = "unreported-usage"
UNINDEXED_FRAMES = "unindexed-frames"
CONVERSATION_AMBIGUOUS = "conversation-ambiguous"
PROVISIONAL_USAGE = "provisional-usage"
MISSING_COUNTERS = "missing-counters"
UNSUPPORTED_COUNTERS = "unsupported-counters"
INVALID_COUNTERS = "invalid-counters"
CONFLICTING_COUNTERS = "conflicting-counters"
MODEL_UNATTRIBUTED = "model-unattributed"
SUBAGENT_MODEL_UNESTABLISHED = "subagent-model-unestablished"
SUBAGENT_USAGE_UNAVAILABLE = "subagent-usage-unavailable"
SUBAGENT_UNIDENTIFIED = "subagent-unidentified"
SUBAGENT_ATTRIBUTION_CONFLICTING = "subagent-attribution-conflicting"
OVERSIZE_METADATA = "oversize-metadata"
MALFORMED_METADATA = "malformed-metadata"
MALFORMED_ENVELOPES = "malformed-envelopes"
MALFORMED_USAGE = "malformed-usage"
OUTPUT_ONLY_OBSERVATIONS = "output-only-observations"
AGGREGATE_ONLY_USAGE = "aggregate-only-usage"
IDENTITY_CONFLICTING = "identity-conflicting"

_UNAVAILABLE_REASONS = frozenset((COLLECTOR_ERROR, NO_STREAM_EVENTS))
_SOURCE_LIMIT_REASONS = frozenset((SCAN_LIMIT, OVERSIZE_LINES, CORRELATION_LIMIT))
# The counters one request's usage is unusable without, each of which has to be observed; an output-only observation
# has its output alone to observe, the thinking inside it beside it.
_CORE_FIELDS = (normalization.CONTEXT_INPUT_TOKENS, normalization.OUTPUT_TOKENS)
_OUTPUT_ONLY_FIELDS = (normalization.OUTPUT_TOKENS, normalization.REASONING_TOKENS)
_COUNTER_GAPS = MappingProxyType({
    normalization.CONFLICTING: CONFLICTING_COUNTERS,
    normalization.INVALID: INVALID_COUNTERS,
})
# The gap a core field leaves where it establishes no count although no counter of it is invalid or conflicting: an
# optional counter the profile has none of is a limitation of the source, but a core one is a request left unread.
_CORE_GAPS = MappingProxyType({
    normalization.MISSING: MISSING_COUNTERS,
    normalization.UNSUPPORTED: UNSUPPORTED_COUNTERS,
})


def collection_status(reasons: Mapping[str, int], observed_samples: int) -> str:
    """The status a collection's gaps leave it in, the most severe first."""
    if _UNAVAILABLE_REASONS.intersection(reasons):
        return UNAVAILABLE
    if _SOURCE_LIMIT_REASONS.intersection(reasons):
        return SOURCE_LIMIT_TRUNCATED
    if STORAGE_BUDGET in reasons:
        return STORAGE_TRUNCATED
    if reasons:
        return INCOMPLETE
    return COMPLETE if observed_samples else COMPLETE_EMPTY


def evidence_gaps(states: Iterable[str]) -> Iterator[str]:
    """The gaps counters in `states` leave: one for conflicting counters and one for invalid ones, each once."""
    present = frozenset(states)
    yield from (gap for state, gap in _COUNTER_GAPS.items() if state in present)


def _judged(observation: RequestObservation) -> tuple[frozenset[str], tuple[str, ...]]:
    """The evidence states an observation is judged on, and the core fields it is unusable without.

    An observation of a request's output alone establishes no context input by its scope, so its one core field is
    its output, and only the fields it observes are judged: the ones its scope leaves out hold no evidence about the
    request.
    """
    usage = observation.usage
    if observation.scope != OUTPUT_SCOPE:
        return usage.states(), _CORE_FIELDS
    states = frozenset(usage.fields[name].state for name in _OUTPUT_ONLY_FIELDS)
    return states, _OUTPUT_ONLY_FIELDS[:1]


def observation_gaps(observation: RequestObservation, *, subagent: bool) -> Iterator[str]:
    """The gaps one observation leaves in its collection: unusable counters, unsettled usage, no model.

    The part of a request an output-only observation never observed is a gap of its own rather than a missing counter.
    """
    states, core_fields = _judged(observation)
    yield from evidence_gaps(states)
    core = frozenset(observation.usage.fields[name].state for name in core_fields)
    yield from (gap for state, gap in _CORE_GAPS.items() if state in core)
    if observation.scope == OUTPUT_SCOPE:
        yield OUTPUT_ONLY_OBSERVATIONS
    if observation.status == PROVISIONAL:
        yield PROVISIONAL_USAGE
    if observation.attribution.model is None:
        yield SUBAGENT_MODEL_UNESTABLISHED if subagent else MODEL_UNATTRIBUTED


@dataclass(frozen=True)
class CollectionCoverage:
    """The gaps one collection recorded, what its source never reports, and how much of the stream it read."""

    reasons: Mapping[str, int]
    limitations: tuple[str, ...] = ()
    scanned_lines: int = 0
    skipped_lines: int = 0
    observed_checkpoints: int = 0

    @property
    def scan_scope(self) -> str:
        if _UNAVAILABLE_REASONS.intersection(self.reasons) and not self.scanned_lines:
            return NO_SCOPE
        if _SOURCE_LIMIT_REASONS.intersection(self.reasons):
            return PARTIAL_SCOPE
        return INVOCATION_SCOPE


@dataclass(frozen=True)
class RequestUsage:
    """The request usage one run's stream yielded: its observations, markers, checkpoints, and coverage."""

    coverage: CollectionCoverage
    observations: tuple[RequestObservation, ...] = ()
    markers: tuple[RequestMarker, ...] = ()
    checkpoints: tuple[UsageCheckpoint, ...] = ()

    @classmethod
    def failed(cls) -> RequestUsage:
        """The collection a collector that raised leaves: nothing read, and the reason why."""
        return cls(CollectionCoverage(MappingProxyType({COLLECTOR_ERROR: 1})))

    def unlinked(self) -> RequestUsage:
        """This collection with no observation naming a trajectory turn: what a record with no timeline keeps."""
        observations = tuple(
            replace(observation, identity=replace(observation.identity, trajectory_turn=None))
            for observation in self.observations
        )
        return replace(self, observations=observations)

    def summary(self, retained_samples: int, retained_markers: int) -> dict[str, Any]:
        """The coverage of a record keeping the first `retained_samples` samples and `retained_markers` markers.

        Whatever the record could not keep is a `storage-budget` gap counting the dropped entries, so the status
        says the record holds less than the scan found.
        """
        dropped = len(self.observations) - retained_samples
        dropped += len(self.markers) - retained_markers
        reasons = dict(self.coverage.reasons)
        if dropped:
            reasons[STORAGE_BUDGET] = dropped
        return {
            "status": collection_status(reasons, len(self.observations)),
            "reasons": reasons,
            "limitations": list(self.coverage.limitations),
            "scan_scope": self.coverage.scan_scope,
            "scanned_lines": self.coverage.scanned_lines,
            "skipped_lines": self.coverage.skipped_lines,
            "observed_samples": len(self.observations),
            "retained_samples": retained_samples,
            "observed_markers": len(self.markers),
            "retained_markers": retained_markers,
            "observed_checkpoints": self.coverage.observed_checkpoints,
            "retained_checkpoints": len(self.checkpoints),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.summary(len(self.observations), len(self.markers)),
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "markers": [marker.to_dict() for marker in self.markers],
            "samples": [observation.to_dict() for observation in self.observations],
        }
