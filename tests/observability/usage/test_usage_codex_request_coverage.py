# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request attribution and coverage: which log lines are the invocation's, and what the collection missed."""

import json
import unittest
from datetime import datetime
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import request_codex, request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_scope import Invocation
from tests.observability.usage import (
    usage_codex_native_capture as capture,
    usage_codex_request_cases as codex,
    usage_request_cases as cases,
)

_SCOPE = "scan_scope"
_SOURCE = cases.MODEL_SOURCE
_POSITION = "position"
_KIND = "kind"
_LIMITATIONS = "limitations"
_UNAVAILABLE_SCOPE = (coverage.UNAVAILABLE, coverage.NO_SCOPE)
_ITEM_COMPLETED = "item_completed"
_SUBAGENT = "SubAgentActivity"
_PARENT = MappingProxyType({"parent_turn_id": codex.APPENDED_TURN})
_CHILD_MODEL = "gpt-5.5-mini"
_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.APPENDED_TURN)
_COMPLETE = codex.event("task_complete", turn_id=codex.APPENDED_TURN)
_NEXT = codex.token_count(codex.NEXT_RUNNING, codex.NEXT_REQUEST)
_CUT_SHORT = '{"timestamp":"2026-11-12T14:10:01.000Z","type":"event_msg","payload":{"type":"token_'
_CHILD_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_PARENT))
_CHILD_CONTEXT = codex.line(codex.TURN_CONTEXT, {codex.TURN_ID: codex.CHILD_TURN, "model": _CHILD_MODEL})
_CHILD_COMPLETE = codex.event("task_complete", turn_id=codex.CHILD_TURN)
# A child turn's running sum is its own branch's, beginning at nothing.
_CHILD_REQUEST = codex.token_count(codex.NEXT_REQUEST, codex.NEXT_REQUEST)
_UNNAMED_CHILD = codex.event(codex.TASK_STARTED, turn_attribution=dict(_PARENT))
_ACTIVITY = codex.event(_ITEM_COMPLETED, item={"type": _SUBAGENT, "agent_thread_id": "thread-a"})
_OTHER_ACTIVITY = codex.event(_ITEM_COMPLETED, item={"type": _SUBAGENT, "agent_thread_id": "thread-b"})
_UNNAMED_ACTIVITY = codex.event(_ITEM_COMPLETED, item={"type": _SUBAGENT})
_OVERSIZED_MODEL = "m" * (request_scan.MAX_METADATA_CHARS + 1)
_OVERSIZED_CONTEXT = codex.line(codex.TURN_CONTEXT, {codex.TURN_ID: codex.APPENDED_TURN, "model": _OVERSIZED_MODEL})
_UNSTAMPED = f'"timestamp":"{codex.STAMP}",'
_RESUMED_STAMP = '"timestamp":"2026-11-12T13:55:10.322Z"'
_EARLY_STAMP = '"timestamp":"2026-11-12T13:50:00.000Z"'
_FOREIGN_TURN = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN)
_REPEAT = codex.token_count(codex.LAST_RUNNING, (16500, 16000, 0, 25, 5, 16525))
_WRONG = codex.token_count(codex.NEXT_RUNNING, (999, 500, 0, 10, 2, 1009))
_SMALLER = (1, 0, 0, 1, 0, 2)
_BACKWARD = codex.token_count(_SMALLER, _SMALLER)
_ESTIMATE = codex.token_count(codex.NEXT_RUNNING, (0, 0, 0, 0, 0, 9548))
_OPENING = codex.token_count(codex.LAST_RUNNING, codex.NEXT_REQUEST)
_NO_USAGE = codex.event(codex.TOKEN_COUNT, info=None)
_ROLLBACK = codex.event("thread_rolled_back", num_turns=1)
_THREAD_ONLY = MappingProxyType({"total_token_usage": codex.counters(codex.NEXT_RUNNING)})
# Reasons a reader states for a log it read no line of.
_READER_REASONS = (
    coverage.NO_SESSION_IDENTITY,
    coverage.NO_LAUNCH_OBSERVATION,
    coverage.NATIVE_LOG_MISSING,
    coverage.NATIVE_LOG_UNREADABLE,
    coverage.DISCOVERY_LIMIT,
)
_FRESH_LINES = capture.log_lines(capture.FRESH.end)
# Logs never adopted: another session's, one whose first line cannot be read, an empty one, one opening otherwise.
_NOT_OWN = (
    ("another session", {"session_id": "01a1d00a-0000-7000-8000-000000000000"}),
    ("first line cut short", {"lines": (_CUT_SHORT, *_FRESH_LINES[1:])}),
    ("empty log", {"lines": ()}),
    ("no session_meta first", {"lines": _FRESH_LINES[1:]}),
)
# Boundaries nothing proves: a fresh run's log begun before its launch, a resumed run's begun after it, and stamps
# going backward.
_UNPROVEN = (
    ("fresh log begun before the launch", capture.FRESH._replace(launched_at=capture.RESUMED.launched_at), None),
    ("resumed log begun after the launch", capture.RESUMED._replace(launched_at=capture.FRESH.launched_at), None),
    (
        "stamps going backward",
        capture.RESUMED,
        [text.replace(_RESUMED_STAMP, _EARLY_STAMP) for text in capture.log_lines(capture.RESUMED.end)],
    ),
)
# A turn another process appended meanwhile, and a turn stdout counts that the log never opened.
_FOREIGN = (
    ("another process's turn", (_STARTED, _NEXT, _COMPLETE, _FOREIGN_TURN)),
    ("a turn the log never opened", ()),
)
# Reports never taken for a new request: one after a line no reading could place -- which could repeat the one that
# line held, an earlier invocation's included -- and one whose running sum moves by anything but its own counters.
_UNPROVEN_REPORTS = (
    ("after a line cut short", (_STARTED, _CUT_SHORT, _NEXT, _COMPLETE), {coverage.MALFORMED_LINES}),
    ("an earlier report after one cut short", (_CUT_SHORT, _STARTED, _REPEAT, _COMPLETE), {coverage.MALFORMED_LINES}),
    ("moving by another request", (_STARTED, _WRONG, _COMPLETE), set()),
    ("moving backward", (_STARTED, _BACKWARD, _COMPLETE), set()),
)
_UNREADABLE = (
    ("info no object", codex.event(codex.TOKEN_COUNT, info=[1]), coverage.MALFORMED_USAGE),
    ("no running sum", codex.event(codex.TOKEN_COUNT, info={"last_token_usage": {}}), coverage.MALFORMED_USAGE),
    ("no request usage", codex.event(codex.TOKEN_COUNT, info=dict(_THREAD_ONLY)), coverage.MALFORMED_USAGE),
    ("payload no object", codex.line(codex.EVENT_MSG, [1]), coverage.MALFORMED_ENVELOPES),
    ("event naming nothing", codex.line(codex.EVENT_MSG, {"info": {}}), coverage.MALFORMED_ENVELOPES),
    ("no kind", json.dumps({"timestamp": codex.STAMP, "payload": {}}), coverage.MALFORMED_ENVELOPES),
)
# Requests whose counters are no usable count, each beside the field it leaves so and the gap it is.
_UNUSABLE = (
    ("negative input", (-5, 500, 0, 10, 2, 1010), ("context_input_tokens", coverage.INVALID_COUNTERS)),
    ("total off its parts", (1000, 500, 0, 10, 2, 1011), ("source_total_tokens", coverage.CONFLICTING_COUNTERS)),
    ("reads past the input", (1000, 2000, 0, 10, 2, 1010), ("cache_read_tokens", coverage.CONFLICTING_COUNTERS)),
    ("reasoning past output", (1000, 500, 0, 10, 20, 1010), ("reasoning_tokens", coverage.CONFLICTING_COUNTERS)),
)
_UNUSABLE_STATES = frozenset(("invalid", "conflicting"))
_UNEXPOSED = (
    ("child turn with no request", (_CHILD_STARTED, _CHILD_COMPLETE), coverage.SUBAGENT_USAGE_UNAVAILABLE, 1),
    ("child turn naming no model", (_CHILD_STARTED, _CHILD_REQUEST), coverage.SUBAGENT_MODEL_UNESTABLISHED, 1),
    ("child turn naming no id", (_UNNAMED_CHILD, _NEXT), coverage.SUBAGENT_UNIDENTIFIED, 1),
    ("subagent threads", (_ACTIVITY, _ACTIVITY, _OTHER_ACTIVITY), coverage.SUBAGENT_USAGE_UNAVAILABLE, 2),
    ("subagent naming no thread", (_UNNAMED_ACTIVITY,), coverage.SUBAGENT_UNIDENTIFIED, 1),
)
# Each correlation bound, held to its least, and how many entries past it a collection drops.
_CHILD_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _CHILD_REQUEST, _COMPLETE)
_BOUNDS = (
    ("requests", ("MAX_TRACKED_STEPS", 1), (capture.FRESH,), 2),
    ("markers", ("MAX_MARKERS", 1), (capture.SWITCHED,), 1),
    ("child turns", ("MAX_BRANCHES", 0), (codex.APPENDED, _CHILD_OVERRUN), 1),
)
_CHILD_RUN = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _CHILD_REQUEST, _CHILD_COMPLETE, _NEXT, _COMPLETE)
_CHILD_ATTRIBUTION = ("turn_id", "parent_turn_id", "model", "branch_order")
_THREAD_ATTRIBUTION = (codex.APPENDED_TURN, None, capture.SWITCHED_MODEL, 0)


def _advanced(own: tuple[int, ...]) -> tuple[int, ...]:
    """The running sum the captured log's last one advances to by `own`, counter by counter where both are counts."""
    pairs = zip(codex.LAST_RUNNING, own, strict=True)
    return tuple(before + max(part, 0) for before, part in pairs)


def _appended_with(*lines: str) -> cases.Collected:
    """What an invocation running one turn of `lines` after the capture collects."""
    return codex.appended(_STARTED, *lines, _COMPLETE)


class UnattributedCollectionTest(unittest.TestCase):
    """A collection that cannot prove what the invocation wrote attributes nothing, and says why."""

    def test_reader_reasons_attribute_nothing(self) -> None:
        facts = Invocation(capture.SESSION_ID, True, capture.RESUMED.launched_at)
        for reason in _READER_REASONS:
            with self.subTest(reason):
                session = request_codex.NativeSession(facts, unavailable=reason)
                usage = request_codex.collect("", session).to_dict()
                summary = usage[cases.COVERAGE]
                self.assertEqual(summary[cases.REASONS], {reason: 1})
                self.assertEqual((summary[cases.STATUS], summary[_SCOPE]), _UNAVAILABLE_SCOPE)
                self.assertEqual(usage[cases.SAMPLES], [])

    def test_a_log_not_the_sessions_own(self) -> None:
        for name, options in _NOT_OWN:
            with self.subTest(name):
                collection = codex.collected(**options)
                self.assertEqual(collection.reasons, {coverage.NATIVE_IDENTITY_UNPROVEN: 1})
                self.assertEqual((collection.status, collection.coverage[_SCOPE]), _UNAVAILABLE_SCOPE)
                self.assertEqual(collection.samples, [])

    def test_an_unprovable_boundary(self) -> None:
        for name, invocation, lines in _UNPROVEN:
            with self.subTest(name):
                self._assert_unattributed(codex.collected(invocation, lines))
        for foreign, appended_lines in _FOREIGN:
            with self.subTest(foreign):
                self._assert_unattributed(codex.appended(*appended_lines))

    def test_an_invocation_that_wrote_nothing(self) -> None:
        # A resume that wrote no line, and whose stdout started no turn, made no request: complete with nothing, and
        # with no boundary crossed, no baseline either.
        collection = codex.appended(stdout="")
        self.assertEqual(collection.status, coverage.COMPLETE_EMPTY)
        self.assertEqual(collection.checkpoints, [])

    def test_unstamped_lines_keep_their_order(self) -> None:
        # A line with no stamp is placed by where the log holds it: before the invocation's first stamped line it is
        # an earlier one's, and after it the invocation's own, kept with no source timestamp.
        twice = _advanced(tuple(part * 2 for part in codex.NEXT_REQUEST))
        earlier = _NEXT.replace(_UNSTAMPED, "")
        own = codex.token_count(twice, codex.NEXT_REQUEST).replace(_UNSTAMPED, "")
        collection = codex.appended(earlier, _STARTED, own, _COMPLETE)
        self.assertEqual(len(collection.samples), 1)
        self.assertNotIn("source_timestamp", collection.samples[0])
        self.assertIn("no-source-timestamps", collection.coverage[_LIMITATIONS])
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_the_launch_is_read_to_the_millisecond(self) -> None:
        # A line the process wrote in the very millisecond it was launched is its own.
        launched = datetime.fromisoformat("2026-11-12T13:55:10.309+00:00")
        collection = codex.collected(capture.RESUMED._replace(launched_at=launched))
        self.assertEqual(cases.column(collection.samples, _POSITION), [32])

    def _assert_unattributed(self, collection: cases.Collected) -> None:
        self.assertEqual(collection.reasons, {coverage.INVOCATION_UNATTRIBUTED: 1})
        self.assertEqual((collection.status, collection.coverage[_SCOPE]), _UNAVAILABLE_SCOPE)
        self.assertGreater(collection.coverage["scanned_lines"], 0)


class RequestIdentityTest(unittest.TestCase):
    """A repeated report is one request, and a report not proven new is none, so nothing is copied or doubled."""

    def test_repeated_notifications_are_one_request(self) -> None:
        # The turn opening with the last running sum, the request's report printed twice, a context estimate whose
        # running sum does not move, and a notification with no usage: one request.
        collection = _appended_with(_OPENING, _NO_USAGE, _NEXT, _NEXT, _ESTIMATE)
        self.assertEqual(len(collection.samples), 1)
        self.assertEqual(collection.reasons, {})

    def test_unproven_reports_are_no_requests(self) -> None:
        for name, lines, others in _UNPROVEN_REPORTS:
            with self.subTest(name):
                collection = codex.appended(*lines)
                reasons = collection.reasons
                self.assertEqual(collection.samples, [])
                self.assertEqual(reasons.pop(coverage.UNRECONCILED_USAGE), 1)
                self.assertEqual(set(reasons), others)


class SourceShapeTest(unittest.TestCase):
    """A shape this collection cannot read is a gap where it stands, and invalid or contradictory counters are kept."""

    def test_unreadable_shapes_are_gaps(self) -> None:
        for name, unreadable, gap in _UNREADABLE:
            with self.subTest(name):
                collection = _appended_with(unreadable)
                self.assertEqual(collection.reasons, {gap: 1})
                self.assertEqual(collection.samples, [])

    def test_unusable_counters_are_kept_as_reported(self) -> None:
        # Each request keeps the counter it reported, with the evidence it is, and the gap it leaves.
        for name, own, (field_name, gap) in _UNUSABLE:
            with self.subTest(name):
                collection = _appended_with(codex.token_count(_advanced(own), own))
                self.assertEqual(collection.reasons, {gap: 1})
                self._assert_kept(collection.samples[0], own, field_name)

    def test_unreported_reasoning_stays_unknown(self) -> None:
        own = codex.counters(codex.NEXT_REQUEST)
        own.pop("reasoning_output_tokens")
        usage = {**_THREAD_ONLY, "last_token_usage": own, "last_usage_includes_reasoning": "yes"}
        collection = _appended_with(codex.event(codex.TOKEN_COUNT, info=usage))
        sample = collection.samples[0]
        self.assertEqual(sample[cases.EVIDENCE]["reasoning_tokens"], "missing")
        self.assertFalse({"source_flags", "context_capacity"} & set(sample))
        self.assertEqual(collection.reasons, {coverage.MALFORMED_METADATA: 1})
        self.assertIn("no-context-capacity", collection.coverage[_LIMITATIONS])

    def _assert_kept(self, sample: dict, own: tuple[int, ...], field_name: str) -> None:
        self.assertEqual(sample[cases.RAW]["input_tokens"], own[0])
        self.assertIn(sample[cases.EVIDENCE][field_name], _UNUSABLE_STATES)


class AttributionTest(unittest.TestCase):
    """A request names the turn and model its own log lines establish, a child turn's as its own, never its parent's."""

    def test_a_thread_naming_no_model(self) -> None:
        # The thread falls back to the configured model where no `turn_context` named one, and to none without it.
        lines = [text for text in _FRESH_LINES if '"type":"turn_context"' not in text]
        configured = codex.collected(lines=lines, fallback_model=capture.FIRST_MODEL)
        unconfigured = codex.collected(lines=lines)
        self.assertEqual(set(cases.column(configured.samples, _SOURCE)), {"configured-fallback"})
        self.assertEqual(set(cases.column(unconfigured.samples, _SOURCE)), {"unavailable"})
        self.assertEqual(unconfigured.reasons, {coverage.MODEL_UNATTRIBUTED: 3})

    def test_a_refused_model_is_unestablished(self) -> None:
        collection = codex.appended(
            _STARTED, _OVERSIZED_CONTEXT, _NEXT, _COMPLETE, fallback_model=capture.FIRST_MODEL,
        )
        sample = collection.samples[0]
        attributed = cases.picked(sample, cases.MODEL, cases.MODEL_SOURCE)
        self.assertEqual(attributed, (None, "unestablished"))
        self.assertEqual(collection.reasons, {coverage.OVERSIZE_METADATA: 1, coverage.MODEL_UNATTRIBUTED: 1})

    def test_a_child_turn_keeps_its_attribution(self) -> None:
        collection = codex.appended(*_CHILD_RUN)
        child, thread = collection.samples
        child_attribution = cases.picked(child, *_CHILD_ATTRIBUTION)
        self.assertEqual(child_attribution, (codex.CHILD_TURN, codex.APPENDED_TURN, _CHILD_MODEL, 0))
        self.assertEqual(cases.picked(thread, *_CHILD_ATTRIBUTION), _THREAD_ATTRIBUTION)
        # Only the thread's running sums are checkpoints; a child turn's span nothing this log establishes.
        positions = cases.column(collection.checkpoints, _POSITION)
        self.assertEqual(positions[1:], [thread[_POSITION]])
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_unexposed_children_are_gaps(self) -> None:
        for name, lines, gap, count in _UNEXPOSED:
            with self.subTest(name):
                self.assertEqual(_appended_with(*lines).reasons.get(gap), count)

    def test_a_rollback_is_a_reset(self) -> None:
        collection = _appended_with(_ROLLBACK)
        self.assertEqual(cases.column(collection.markers, _KIND), ["reset"])


class CollectionBoundTest(unittest.TestCase):
    """Every bound on correlation state holds, and a bound reached is a gap rather than a silence."""

    def test_correlation_bounds_are_gaps(self) -> None:
        for name, bound, arguments, dropped in _BOUNDS:
            with self.subTest(name), patch.object(request_scan, *bound):
                collection = codex.collected(*arguments)
                self.assertEqual(collection.reasons.get(coverage.CORRELATION_LIMIT), dropped)
                self.assertEqual(collection.status, coverage.SOURCE_LIMIT_TRUNCATED)
                self.assertEqual(collection.coverage[_SCOPE], coverage.PARTIAL_SCOPE)

    def test_checkpoints_keep_baseline_and_last(self) -> None:
        with patch.object(request_scan, "MAX_CHECKPOINTS", 2):
            collection = codex.collected(capture.SWITCHED)
        self.assertEqual(cases.column(collection.checkpoints, _POSITION), [32, 52])
        self.assertEqual(collection.coverage["observed_checkpoints"], 3)
        self.assertEqual(collection.status, coverage.COMPLETE)


if __name__ == "__main__":
    unittest.main()
