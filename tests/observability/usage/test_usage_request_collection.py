# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of a stream one request collection covered: its status, its counts' scope, and the bounds it holds to."""

import dataclasses
import json
import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
    request_scan as scan,
)

_COMPLETE_EVENT = '{"event":"result","result":{}}'
_TWO_EVENTS = f"{_COMPLETE_EVENT}\n{_COMPLETE_EVENT}"
_TRUNCATED_FRAME = '{"event":"step_update","step_update":{"step_index":'
# A blank line, banner text, a frame cut short, one whole event, and a JSON value that is no event.
_MIXED_STDOUT = f"\nAntigravity CLI ready\n{_TRUNCATED_FRAME}\n{_COMPLETE_EVENT}\n[]"
_LIMITS = scan.current_limits()
_METADATA_LIMIT = 8
_STORAGE = coverage.STORAGE_BUDGET
_STATUS = "status"
_SCAN_SCOPE = "scan_scope"
_COUNT_NAMES = ("observed_samples", "retained_samples", "observed_markers", "retained_markers")
_ABSENT_IDENTITIES = frozenset(("turn_id", "message_id", "parent_conversation_id", "source_timestamp"))
_COMPLETE = MappingProxyType({normalization.INPUT: 1, normalization.CACHE_READ: 0, normalization.OUTPUT: 1})
_LINE = len(_COMPLETE_EVENT)
# Each bound, the events it lets a two-event stream decode, and the gap it records.
_BOUNDS = (
    ("line size", dataclasses.replace(_LIMITS, line_chars=_LINE - 1), 0, coverage.OVERSIZE_LINES),
    ("scanned characters", dataclasses.replace(_LIMITS, scan_chars=_LINE + 1), 1, coverage.SCAN_LIMIT),
    ("decoded events", dataclasses.replace(_LIMITS, events=1), 1, coverage.SCAN_LIMIT),
)
# How an observation differs from a final, attributed, complete one; whether it is a subagent's; and its gaps.
_OBSERVATION_GAPS = (
    ("final and attributed", {}, False, []),
    ("provisional", {"status": models.PROVISIONAL}, False, [coverage.PROVISIONAL_USAGE]),
    ("unattributed", {"model": None}, False, [coverage.MODEL_UNATTRIBUTED]),
    ("subagent", {"model": None}, True, [coverage.SUBAGENT_MODEL_UNESTABLISHED]),
    ("no cache reads", {normalization.CACHE_READ: None}, False, [coverage.MISSING_COUNTERS]),
    ("negative input", {normalization.INPUT: -1}, False, [coverage.INVALID_COUNTERS]),
    ("thinking past output", {normalization.REASONING: 2}, False, [coverage.CONFLICTING_COUNTERS]),
)


def _attribution(model: str | None) -> models.RequestAttribution:
    return models.RequestAttribution(model, models.STREAM_MODEL if model else models.UNAVAILABLE)


def _observation(
    *,
    model: str | None = "m",
    status: str = models.FINAL,
    **counts: int | None,
) -> models.RequestObservation:
    readings = {
        counter: normalization.Reading.of(count)
        for counter, count in counts.items()
    }
    return models.RequestObservation(
        identity=models.RequestIdentity("c:1", models.CONVERSATION_STEP, conversation_id="c", step_index=1),
        position=0,
        branch_order=0,
        attribution=_attribution(model),
        usage=normalization.normalize(protocol.AGY, readings),
        raw=MappingProxyType({}),
        status=status,
        settlement="completed-frame",
    )


def _usage(reasons: dict, samples: int = 1, markers: int = 0) -> coverage.RequestUsage:
    marker = models.RequestMarker(models.MODEL_CHANGE, 0, model="b", previous_model="a")
    return coverage.RequestUsage(
        coverage.CollectionCoverage(MappingProxyType(reasons), scanned_lines=1),
        observations=(_observation(**_COMPLETE),) * samples,
        markers=(marker,) * markers,
    )


def _gaps(overrides: dict, subagent: bool) -> list[str]:
    observation = _observation(**{**_COMPLETE, **overrides})
    return list(coverage.observation_gaps(observation, subagent=subagent))


class CollectionStatusTest(unittest.TestCase):
    """A status is read off the gaps the collection recorded, the most severe first."""

    def test_status_follows_the_most_severe_gap(self) -> None:
        cases = (
            ({}, 0, coverage.COMPLETE_EMPTY),
            ({}, 2, coverage.COMPLETE),
            ({coverage.MISSING_COUNTERS: 1}, 2, coverage.INCOMPLETE),
            ({_STORAGE: 1, coverage.MISSING_COUNTERS: 1}, 2, coverage.STORAGE_TRUNCATED),
            ({coverage.OVERSIZE_LINES: 1, _STORAGE: 1}, 2, coverage.SOURCE_LIMIT_TRUNCATED),
            ({coverage.NO_STREAM_EVENTS: 1, coverage.SCAN_LIMIT: 1}, 0, coverage.UNAVAILABLE),
            ({coverage.COLLECTOR_ERROR: 1}, 0, coverage.UNAVAILABLE),
        )
        for reasons, observed, status in cases:
            with self.subTest(reasons=reasons, observed=observed):
                self.assertEqual(coverage.collection_status(reasons, observed), status)

    def test_partial_scans_never_claim_the_invocation(self) -> None:
        cases = (
            ({}, coverage.INVOCATION_SCOPE),
            ({coverage.CORRELATION_LIMIT: 1}, coverage.PARTIAL_SCOPE),
            ({coverage.SCAN_LIMIT: 1}, coverage.PARTIAL_SCOPE),
        )
        for reasons, scope in cases:
            with self.subTest(reasons=reasons):
                summary = _usage(reasons).summary(1, 0)
                self.assertEqual(summary[_SCAN_SCOPE], scope)
                self.assertEqual(summary["observed_samples"], 1)
        failed = coverage.RequestUsage.failed().summary(0, 0)
        self.assertEqual(failed["reasons"], {coverage.COLLECTOR_ERROR: 1})
        self.assertEqual(failed[_STATUS], coverage.UNAVAILABLE)
        self.assertEqual(failed[_SCAN_SCOPE], coverage.NO_SCOPE)

    def test_dropped_entries_are_a_counted_gap(self) -> None:
        usage = _usage({coverage.NO_TERMINAL_RESULT: 1}, samples=3, markers=2)
        kept = usage.summary(1, 1)
        self.assertEqual(kept["reasons"], {coverage.NO_TERMINAL_RESULT: 1, _STORAGE: 3})
        self.assertEqual(kept[_STATUS], coverage.STORAGE_TRUNCATED)
        counts = [kept[name] for name in _COUNT_NAMES]
        self.assertEqual(counts, [3, 1, 2, 1])
        self.assertEqual(usage.to_dict()["coverage"], usage.summary(3, 2))

    def test_each_observation_names_its_own_gaps(self) -> None:
        for name, overrides, subagent, expected in _OBSERVATION_GAPS:
            with self.subTest(name):
                self.assertEqual(_gaps(overrides, subagent), expected)


class BoundedScanTest(unittest.TestCase):
    """The collector's own pass over stdout reads within its bounds and records what it left out."""

    def test_events_keep_their_stdout_line(self) -> None:
        events = scan.scan_events(_MIXED_STDOUT, _LIMITS)
        self.assertEqual([position for position, _ in events.events], [3])
        self.assertEqual((events.scanned_lines, events.skipped_lines), (4, 3))
        # Banner text and a bare JSON array are no frames; an object that does not decode is a damaged one.
        self.assertEqual(events.gaps, {coverage.MALFORMED_LINES: 1})

    def test_each_bound_stops_or_skips_and_says_so(self) -> None:
        for name, limits, decoded, gap in _BOUNDS:
            with self.subTest(name):
                events = scan.scan_events(_TWO_EVENTS, limits)
                self.assertEqual(len(events.events), decoded)
                self.assertIn(gap, events.gaps)

    def test_a_stream_within_its_bounds_is_whole(self) -> None:
        exact = scan.scan_events(_COMPLETE_EVENT, dataclasses.replace(_LIMITS, events=1))
        self.assertEqual(len(exact.events), 1)
        self.assertFalse(exact.gaps)
        # Whitespace past the scanned characters is nothing the bound left unread.
        trailing = scan.scan_events(f"{_COMPLETE_EVENT}\n \n", dataclasses.replace(_LIMITS, scan_chars=_LINE))
        self.assertFalse(trailing.gaps)

    def test_oversize_metadata_is_dropped_and_counted(self) -> None:
        metadata = scan.Metadata(_METADATA_LIMIT)
        oversize = "x" * (_METADATA_LIMIT + 1)
        kept = [metadata.text(raw) for raw in ("short", oversize, 7, "", None)]
        self.assertEqual(kept, ["short", None, None, None, None])
        self.assertEqual(metadata.oversize, 1)

    def test_observations_serialize_counters_alone(self) -> None:
        serialized = _observation(**_COMPLETE).to_dict()
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
        self.assertEqual(serialized["id"], "c:1")
        self.assertEqual(serialized["id_kind"], models.CONVERSATION_STEP)
        self.assertEqual(serialized["step_index"], 1)
        # Identities the stream never gave are absent rather than null.
        self.assertFalse(_ABSENT_IDENTITIES & set(serialized))
