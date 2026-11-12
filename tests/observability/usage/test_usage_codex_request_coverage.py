# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request attribution and coverage: which log lines are the invocation's, and what the collection missed."""

import dataclasses
import json
import unittest
from datetime import datetime
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import request_codex, request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_scope import Invocation, Turns
from tests.observability.usage import (
    usage_codex_native_capture as capture,
    usage_codex_request_cases as codex,
    usage_request_cases as cases,
)

_SCOPE = "scan_scope"
_INVALID_STATE = "invalid"
_SOURCE = cases.MODEL_SOURCE
_POSITION = "position"
_KIND = "kind"
_LIMITATIONS = "limitations"
_UNAVAILABLE_SCOPE = (coverage.UNAVAILABLE, coverage.NO_SCOPE)
_ITEM_COMPLETED = "item_completed"
_SUBAGENT = "SubAgentActivity"
_TYPE = "type"
_REPEATS = 50
_TASK_COMPLETE = "task_complete"
_PARENT = MappingProxyType({"parent_turn_id": codex.APPENDED_TURN})
_CHILD_MODEL = "gpt-5.5-mini"
_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.APPENDED_TURN)
_COMPLETE = codex.event(_TASK_COMPLETE, turn_id=codex.APPENDED_TURN)
_NEXT = codex.token_count(codex.NEXT_RUNNING, codex.NEXT_REQUEST)
_CUT_SHORT = '{"timestamp":"2026-11-12T14:10:01.000Z","type":"event_msg","payload":{"type":"token_'
_CHILD_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_PARENT))
_CHILD_CONTEXT = codex.line(codex.TURN_CONTEXT, {codex.TURN_ID: codex.CHILD_TURN, "model": _CHILD_MODEL})
_CHILD_COMPLETE = codex.event(_TASK_COMPLETE, turn_id=codex.CHILD_TURN)
# A child turn's running sum is its own branch's, beginning at nothing.
_CHILD_REQUEST = codex.token_count(codex.NEXT_REQUEST, codex.NEXT_REQUEST)
_UNNAMED_CHILD = codex.event(codex.TASK_STARTED, turn_attribution=dict(_PARENT))
_ACTIVITY = codex.event(_ITEM_COMPLETED, item={_TYPE: _SUBAGENT, "agent_thread_id": "thread-a"})
_OTHER_ACTIVITY = codex.event(_ITEM_COMPLETED, item={_TYPE: _SUBAGENT, "agent_thread_id": "thread-b"})
_UNNAMED_ACTIVITY = codex.event(_ITEM_COMPLETED, item={_TYPE: _SUBAGENT})
_LEGACY_ACTIVITY = MappingProxyType({
    _TYPE: "sub_agent_activity",
    "event_id": "spawn",
    "agent_thread_id": "thread-c",
    "agent_path": "/worker",
    "kind": "started",
})
_LEGACY_EVENT = codex.line(codex.EVENT_MSG, dict(_LEGACY_ACTIVITY))
_UNNAMED_LEGACY_EVENT = codex.event("sub_agent_activity", event_id="spawn", kind="started")
_FRESH_LINES = capture.log_lines(capture.FRESH.end)
_FRESH_FIRST = _FRESH_LINES[0]
_OVERSIZED_MODEL = "m" * (request_scan.MAX_METADATA_CHARS + 1)
_OVERSIZED_CONTEXT = codex.line(codex.TURN_CONTEXT, {codex.TURN_ID: codex.APPENDED_TURN, "model": _OVERSIZED_MODEL})
_UNSTAMPED = f'"timestamp":"{codex.STAMP}",'
_TURN_LINES = (_STARTED, _NEXT, _COMPLETE)
_UNSTAMPED_TURN = tuple(text.replace(_UNSTAMPED, "") for text in _TURN_LINES)
_UNSTAMPED_LOG = (*capture.log_lines(), *_UNSTAMPED_TURN)
# A line stamped after the captured log and before the appended invocation's launch.
_EARLIER_SETTINGS = codex.line(codex.EVENT_MSG, {_TYPE: "thread_settings_applied"}, "2026-11-12T14:05:00.000Z")
# The resumed invocation's first line, and the fresh one's last line less half a millisecond.
_FIRST_RESUMED_LINE = datetime.fromisoformat("2026-11-12T13:55:10.309+00:00")
_BESIDE_FRESH_END = datetime.fromisoformat("2026-11-12T13:54:56.703500+00:00")
# A resume launched once the fresh invocation had exited, on a clock stepped back to before its last requests, that
# wrote no line and printed nothing.
_STEPPED_BACK = capture.Invocation(
    datetime.fromisoformat("2026-11-12T13:54:56.650+00:00"), capture.FRESH.end, True, "", capture.FRESH.end,
)
# An earlier invocation's running sum left with no usable input, output, or total -- the counters a request moves --
# and a report after it of the request it already reported, whose cache and reasoning counters stay at zero.
_REPLAYED = (100, 0, 0, 10, 0, 110)
_UNUSABLE_SUM = (_INVALID_STATE, 0, 0, _INVALID_STATE, 0, _INVALID_STATE)
_UNUSABLE_REPORT = MappingProxyType({
    "total_token_usage": codex.counters(_UNUSABLE_SUM),
    "last_token_usage": codex.counters(_REPLAYED),
})
_REPLAY_LOG = (
    _FRESH_FIRST,
    codex.line(codex.EVENT_MSG, {_TYPE: codex.TOKEN_COUNT, "info": dict(_UNUSABLE_REPORT)}, "2026-11-12T14:00:00.000Z"),
    _STARTED,
    codex.token_count(_REPLAYED, _REPLAYED),
    _COMPLETE,
)
_AFTER_REPLAYED = codex.APPENDED._replace(start=2)
_FRESH_COMPLETE = MappingProxyType({_TYPE: _TASK_COMPLETE, codex.TURN_ID: capture.FRESH_TURN})
# A fresh legacy history: its subagent's activity is a `sub_agent_activity` event, not a completed item.
_LEGACY_LOG = (
    _FRESH_FIRST.replace('"history_mode":"paginated"', '"history_mode":"legacy"'),
    capture.log_lines(2)[1],
    codex.line(codex.EVENT_MSG, dict(_LEGACY_ACTIVITY), "2026-11-12T13:54:57.000Z"),
    codex.line(codex.EVENT_MSG, dict(_FRESH_COMPLETE), "2026-11-12T13:54:57.100Z"),
)
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
# A report repeating the captured log's last running sum, its own request usage left out, or carrying a negative count.
_LAST_ONLY = MappingProxyType({"total_token_usage": codex.counters(codex.LAST_RUNNING)})
_NEGATIVE_REPEAT = (-1, 0, 0, 10, 0, 9)
_REPEAT_NO_USAGE = codex.event(codex.TOKEN_COUNT, info=dict(_LAST_ONLY))
_INVALID = coverage.INVALID_COUNTERS
# A request's usage leaving its reasoning out, and what its report says beside it: nothing more, or a reasoning flag or
# context window no usable value, each with the malformed metadata it is.
_NO_REASONING = MappingProxyType({
    counter: count
    for counter, count in codex.counters(codex.NEXT_REQUEST).items()
    if counter != "reasoning_output_tokens"
})
_WINDOW = "model_context_window"
_METADATA_SHAPES = (
    ({}, 0),
    ({"last_usage_includes_reasoning": "yes"}, 1),
    ({_WINDOW: -1}, 1),
    ({_WINDOW: "wide"}, 1),
    ({_WINDOW: True}, 1),
)
# Earlier turns of the session, stamped before the appended invocation's launch: one whose request a usage record
# shows and no report covers, one whose second request no report covers, and one reporting no usage at all. Each
# resume after them reports the request the earlier turn settled last again -- or, after none, its own first one.
_PRIOR_STAMP = "2026-11-12T14:09:00.000Z"
_FRESH_STARTED = codex.event(codex.TASK_STARTED, turn_id=capture.FRESH_TURN)
_FRESH_COMPLETED = codex.event(_TASK_COMPLETE, turn_id=capture.FRESH_TURN)
_PRIOR_STARTED = _FRESH_STARTED.replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_COMPLETE = _FRESH_COMPLETED.replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_RECORD = codex.line("token_usage_record", {"usage": codex.counters(_REPLAYED)}, _PRIOR_STAMP)
_PRIOR_REPORT = codex.token_count(_REPLAYED, _REPLAYED).replace(codex.STAMP, _PRIOR_STAMP)
_REPLAYED_TWICE = tuple(2 * count for count in _REPLAYED)
_UNCOVERED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_COMPLETE)
_LAGGING = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_REPORT, _PRIOR_RECORD, _PRIOR_COMPLETE)
_UNUSED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_COMPLETE)
_REPLAYED_REPORT = codex.token_count(_REPLAYED, _REPLAYED)
_BEHIND = (
    ("a request no report covers", len(_UNCOVERED), (*_UNCOVERED, _STARTED, _REPLAYED_REPORT, _COMPLETE), 0),
    (
        "a request past the last report",
        len(_LAGGING),
        (*_LAGGING, _STARTED, codex.token_count(_REPLAYED_TWICE, _REPLAYED), _COMPLETE),
        0,
    ),
    ("no usage before", len(_UNUSED), (*_UNUSED, _STARTED, _REPLAYED_REPORT, _COMPLETE), 1),
)
# Reasons a reader states for a log it read no line of.
_READER_REASONS = (
    coverage.NO_SESSION_IDENTITY,
    coverage.NO_LAUNCH_OBSERVATION,
    coverage.NATIVE_LOG_MISSING,
    coverage.NATIVE_LOG_UNREADABLE,
    coverage.DISCOVERY_LIMIT,
)
# Logs never adopted: another session's, one whose first line cannot be read, an empty one, one opening otherwise.
_NOT_OWN = (
    ("another session", {"session_id": "01a1d00a-0000-7000-8000-000000000000"}),
    ("first line cut short", {"lines": (_CUT_SHORT, *_FRESH_LINES[1:])}),
    ("empty log", {"lines": ()}),
    ("no session_meta first", {"lines": _FRESH_LINES[1:]}),
)
_SHORTER = codex.APPENDED._replace(start=capture.LAST.end + 1, stdout="")
# Placements nothing proves: a resume its launch counted no lines for, none at all, or more than the log read whole
# holds; and stamps the clock contradicts -- a fresh run's log stamped before its launch, earlier lines stamped after
# it, the silent resume after a clock step back that would have taken the fresh invocation's last requests, an own line
# stamped before the launch, and stamps going backward.
_UNPROVEN = (
    ("a resume counted nothing for", capture.RESUMED._replace(start=None), None),
    ("a resume of an empty log", capture.RESUMED._replace(start=0), None),
    ("a silent resume of a log shorter than its count", _SHORTER, None),
    ("fresh log begun before the launch", capture.FRESH._replace(launched_at=capture.RESUMED.launched_at), None),
    ("earlier lines stamped after the launch", capture.RESUMED._replace(launched_at=capture.FRESH.launched_at), None),
    ("a silent resume after a clock step back", _STEPPED_BACK, None),
    ("an own line stamped before the launch", codex.APPENDED, (*capture.log_lines(), _EARLIER_SETTINGS, *_TURN_LINES)),
    (
        "stamps going backward",
        capture.RESUMED,
        [text.replace(_RESUMED_STAMP, _EARLY_STAMP) for text in capture.log_lines(capture.RESUMED.end)],
    ),
)
_SILENT = codex.APPENDED._replace(stdout="")
# Turns stdout does not account for: one another process appended meanwhile, one stdout counts that the log never
# opened, and one the log opened that stdout never printed.
_FOREIGN = (
    ("another process's turn", codex.APPENDED, (*capture.log_lines(), *_TURN_LINES, _FOREIGN_TURN)),
    ("a turn the log never opened", codex.APPENDED, capture.log_lines()),
    ("a turn stdout never printed", _SILENT, (*capture.log_lines(), *_TURN_LINES)),
)
# Lines placed past the count whatever their stamps: one in the launch's own millisecond, past an earlier line in it,
# and unstamped ones.
_IN_FIRST_LINE = capture.RESUMED._replace(launched_at=_FIRST_RESUMED_LINE)
_BESIDE_EARLIER_LINE = capture.RESUMED._replace(launched_at=_BESIDE_FRESH_END)
_PLACED = (
    ("a launch in its first line's millisecond", _IN_FIRST_LINE, None, [32]),
    ("an earlier line in the launch's millisecond", _BESIDE_EARLIER_LINE, None, [32]),
    ("unstamped lines", codex.APPENDED, _UNSTAMPED_LOG, [capture.LAST.end + 1]),
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
    ("a repeat naming no request usage", _REPEAT_NO_USAGE, coverage.MALFORMED_USAGE),
    ("a repeat reporting no whole count", codex.token_count(codex.LAST_RUNNING, _NEGATIVE_REPEAT), _INVALID),
)
_CONFLICTING = coverage.CONFLICTING_COUNTERS
# Requests whose counters are no usable count, each beside the running sum it advances, the field it leaves unusable,
# and the gaps it is: a running sum adding a request's contradiction carries it too, and is a gap of its own.
_NEGATIVE_INPUT = (-5, 500, 0, 10, 2, 1010)
_ONE_INVALID = MappingProxyType({_INVALID: 1})
_ONE_CONFLICT = MappingProxyType({_CONFLICTING: 1})
_TWO_CONFLICTS = MappingProxyType({_CONFLICTING: 2})
_UNUSABLE = (
    ("negative input", _NEGATIVE_INPUT, codex.NEXT_RUNNING, ("context_input_tokens", _ONE_INVALID)),
    ("total off its parts", (1000, 500, 0, 10, 2, 1011), None, ("source_total_tokens", _TWO_CONFLICTS)),
    ("reads past the input", (1000, 2000, 0, 10, 2, 1010), None, ("cache_read_tokens", _ONE_CONFLICT)),
    ("reasoning past output", (1000, 500, 0, 10, 20, 1010), None, ("reasoning_tokens", _ONE_CONFLICT)),
)
_INVALID_RUNNING = (*codex.NEXT_RUNNING[:5], -1)
_NO_OBJECTS = ('[{"type":"event_msg"}]', "Codex ready")
_UNUSABLE_STATES = frozenset((_INVALID_STATE, "conflicting"))
_UNEXPOSED = (
    ("child turn with no request", (_CHILD_STARTED, _CHILD_COMPLETE), coverage.SUBAGENT_USAGE_UNAVAILABLE, 1),
    ("child turn naming no model", (_CHILD_STARTED, _CHILD_REQUEST), coverage.SUBAGENT_MODEL_UNESTABLISHED, 1),
    ("child turn naming no id", (_UNNAMED_CHILD, _NEXT), coverage.SUBAGENT_UNIDENTIFIED, 1),
    ("child turn naming no id, no request", (_UNNAMED_CHILD,), coverage.SUBAGENT_UNIDENTIFIED, 1),
    ("subagent threads", (_ACTIVITY, _ACTIVITY, _OTHER_ACTIVITY), coverage.SUBAGENT_USAGE_UNAVAILABLE, 2),
    ("subagent naming no thread", (_UNNAMED_ACTIVITY,), coverage.SUBAGENT_UNIDENTIFIED, 1),
    ("legacy subagent event", (_LEGACY_EVENT,), coverage.SUBAGENT_USAGE_UNAVAILABLE, 1),
    ("legacy subagent event naming no thread", (_UNNAMED_LEGACY_EVENT,), coverage.SUBAGENT_UNIDENTIFIED, 1),
)
# Each correlation bound, held to its least, and how many entries past it a collection drops: a child turn refused
# is one, whether or not a request follows it, and each request it leaves unattributable another.
_CHILD_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _CHILD_REQUEST, _COMPLETE)
_QUIET_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _CHILD_COMPLETE, _COMPLETE)
_OPEN_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _UNNAMED_CHILD, _NEXT, _COMPLETE)
_THREAD_OVERRUN = (*capture.log_lines(), _STARTED, _ACTIVITY, _OTHER_ACTIVITY, _ACTIVITY, _COMPLETE)
_BRANCHES = "MAX_BRANCHES"
_BOUNDS = (
    ("requests", ("MAX_TRACKED_STEPS", 1), (capture.FRESH,), 2),
    ("markers", ("MAX_MARKERS", 1), (capture.SWITCHED,), 1),
    ("child turns named", (_BRANCHES, 0), (codex.APPENDED, _CHILD_OVERRUN), 2),
    ("a child turn refused with no request", (_BRANCHES, 0), (codex.APPENDED, _QUIET_OVERRUN), 1),
    ("child turns open at once", (_BRANCHES, 1), (codex.APPENDED, _OPEN_OVERRUN), 2),
    ("subagent threads named", (_BRANCHES, 1), (codex.APPENDED, _THREAD_OVERRUN), 1),
)
# The longest line the captured log holds, and a line one character longer, which a line bound of the first skips.
_LONGEST = max(map(len, capture.log_lines()))
_PADDING = _LONGEST + 1 - len(codex.event(_ITEM_COMPLETED, text=""))
_OVERSIZE_LINE = codex.event(_ITEM_COMPLETED, text="x" * _PADDING)
# What stops a reader before the log's end, which it records in the scan it shares once it stops: a read bound, and a
# read failing partway.
_READER_STOPS = (coverage.SCAN_LIMIT, coverage.NATIVE_READ_INTERRUPTED)
_APPENDED_FACTS = Invocation(capture.SESSION_ID, True, codex.APPENDED_AT, codex.APPENDED.start)
_ALL_BUT_LAST = capture.log_lines()[:-1]
_RESUMED_FACTS = Invocation(capture.SESSION_ID, True, capture.RESUMED.launched_at)
_REPEATED_STARTS = (_CHILD_STARTED,) * _REPEATS
_REPEATED_CHILD = (_STARTED, *_REPEATED_STARTS, _CHILD_CONTEXT, _CHILD_REQUEST, _CHILD_COMPLETE, _COMPLETE)
_CHILD_START = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, "turn_attribution": dict(_PARENT)})
_UNNAMED_START = MappingProxyType({"turn_attribution": dict(_PARENT)})
_CHILD_STARTS = (*(_CHILD_START,) * _REPEATS, _UNNAMED_START)
_INVALID_TOTAL = MappingProxyType({"total_tokens": _INVALID_STATE})
_CHILD_RUN = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _CHILD_REQUEST, _CHILD_COMPLETE, _NEXT, _COMPLETE)
# A child turn switching models between its two requests.
_SWITCHED_CHILD_MODEL = "gpt-5.5-nano"
_SWITCHED_CHILD = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, cases.MODEL: _SWITCHED_CHILD_MODEL})
_CHILD_SWITCH = codex.line(codex.TURN_CONTEXT, dict(_SWITCHED_CHILD))
_CHILD_TWICE = tuple(2 * count for count in codex.NEXT_REQUEST)
_CHILD_SECOND = codex.token_count(_CHILD_TWICE, codex.NEXT_REQUEST)
_CHILD_SWITCH_RUN = (
    _STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _CHILD_REQUEST, _CHILD_SWITCH, _CHILD_SECOND, _CHILD_COMPLETE, _COMPLETE,
)
_CHILD_MODEL_CHANGE = MappingProxyType({
    _KIND: "model-change",
    _POSITION: capture.LAST.end + 4,
    "conversation_id": capture.SESSION_ID,
    "turn_id": codex.CHILD_TURN,
    "parent_turn_id": codex.APPENDED_TURN,
    cases.MODEL: _SWITCHED_CHILD_MODEL,
    "previous_model": _CHILD_MODEL,
})
# Stamps no UTC moment reads as: one its offset moves before the first moment, one it moves past the last, one naming
# no offset, and one no ISO moment at all.
_UNREADABLE_STAMPS = ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00", "2026-11-12T14:10:01", "yesterday")
# A usage record of the appended request, as the CLI writes one beside each `token_count` reporting a request.
_RECORD = codex.line("token_usage_record", {"usage": codex.counters(codex.NEXT_REQUEST)})
_REPORTLESS_FRESH = tuple(text for text in _FRESH_LINES if '"type":"token_count"' not in text)
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
        # A caller states why it hands over no line; one handing over no session at all observed no launch.
        sessions = {
            reason: request_codex.NativeSession(_RESUMED_FACTS, unavailable=reason) for reason in _READER_REASONS
        }
        sessions[coverage.NO_LAUNCH_OBSERVATION] = None
        for reason, session in sessions.items():
            with self.subTest(reason):
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
        for name, invocation, lines in (*_UNPROVEN, *_FOREIGN):
            with self.subTest(name):
                self._assert_unattributed(codex.collected(invocation, lines))

    def test_an_invocation_that_wrote_nothing(self) -> None:
        # A resume that wrote no line, and whose stdout started no turn, made no request: complete with nothing, and
        # with no boundary crossed, no baseline either.
        collection = codex.appended(stdout="")
        self.assertEqual(collection.status, coverage.COMPLETE_EMPTY)
        self.assertEqual(collection.checkpoints, [])

    def test_lines_placed_by_the_count(self) -> None:
        # A resumed run's own lines are the ones past the count its launch took, whatever their stamps say short of a
        # contradiction: a line in the launch's own millisecond is placed by the count, and an unstamped one too.
        for name, invocation, lines, positions in _PLACED:
            with self.subTest(name):
                collection = codex.collected(invocation, lines)
                self.assertEqual(cases.column(collection.samples, _POSITION), positions)
                self.assertEqual(collection.status, coverage.COMPLETE)

    def test_stamps_that_place_nothing(self) -> None:
        # An unstamped line keeps no stamp, and a stamp no UTC moment reads as -- its offset carrying it out of range
        # included -- is malformed metadata kept as written; neither places anything, and the request is still read.
        unstamped = codex.collected(codex.APPENDED, _UNSTAMPED_LOG)
        self.assertNotIn("source_timestamp", unstamped.samples[0])
        self.assertIn("no-source-timestamps", unstamped.coverage[_LIMITATIONS])
        for stamp in _UNREADABLE_STAMPS:
            with self.subTest(stamp):
                collection = _appended_with(_NEXT.replace(codex.STAMP, stamp))
                self.assertEqual(collection.reasons, {coverage.MALFORMED_METADATA: 1})
                self.assertEqual(cases.column(collection.samples, "source_timestamp"), [stamp])

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

    def test_unchanged_zeros_prove_no_request(self) -> None:
        # After an earlier running sum leaves the counters a request moves unusable, a report its sum's zeros alone
        # agree with is no proven request: it could be the earlier request reported again.
        collection = codex.collected(_AFTER_REPLAYED, _REPLAY_LOG)
        self.assertEqual(collection.samples, [])
        self.assertEqual(collection.reasons.get(coverage.UNRECONCILED_USAGE), 1)

    def test_a_running_sum_behind_a_settled_request(self) -> None:
        # A request the earlier lines settled with no `token_count` reporting it leaves the thread's running sum behind
        # it -- nothing at all, or the last sum reported -- so no baseline is kept, and the invocation's report of that
        # request again is not proven new; after no usage at all, nothing lags, and the first report is a request.
        for name, start, lines, kept in _BEHIND:
            with self.subTest(name):
                collection = codex.collected(
                    codex.APPENDED._replace(start=start), lines, fallback_model=capture.FIRST_MODEL,
                )
                self.assertEqual(len(collection.samples), kept)
                self.assertEqual(collection.reasons, {} if kept else {coverage.UNRECONCILED_USAGE: 1})
                self.assertNotIn("invocation-baseline", cases.column(collection.checkpoints, _KIND))

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
        for name, own, running, expected in _UNUSABLE:
            with self.subTest(name):
                collection = _appended_with(codex.token_count(running or _advanced(own), own))
                self._assert_kept(collection, own, expected)

    def test_an_unusable_running_sum_is_a_gap(self) -> None:
        # The request it advances by is kept; the checkpoint keeps the count it is no usable one, and says so.
        collection = _appended_with(codex.token_count(_INVALID_RUNNING, codex.NEXT_REQUEST))
        self.assertEqual(len(collection.samples), 1)
        self.assertEqual(collection.reasons, {_INVALID: 1})
        running = collection.checkpoints[-1]
        self.assertEqual(running[cases.EVIDENCE], _INVALID_TOTAL)

    def test_a_line_holding_no_object(self) -> None:
        # A native log holds JSON objects alone, so any other line -- a value that is no object, or plain text -- is
        # malformed where it stands, while the request beside it is kept.
        collection = _appended_with(_NEXT, *_NO_OBJECTS)
        self.assertEqual(len(collection.samples), 1)
        self.assertEqual(collection.reasons, {coverage.MALFORMED_LINES: len(_NO_OBJECTS)})

    def test_usage_no_report_carries_is_a_gap(self) -> None:
        # A request is read off its `token_count` alone, so a usage record beyond the invocation's reports that repeat
        # nothing -- every record, where its reports are missing -- is usage it could not observe, never no request.
        cases_by_name = {
            "every report missing": (codex.collected(lines=_REPORTLESS_FRESH), 3),
            "one record beyond its report": (_appended_with(_RECORD, _OPENING, _NEXT, _NEXT, _RECORD), 1),
        }
        for name, (collection, unobserved) in cases_by_name.items():
            with self.subTest(name):
                self.assertEqual(collection.reasons, {coverage.UNSUPPORTED_USAGE_SOURCE: unobserved})
                self.assertEqual(collection.status, coverage.INCOMPLETE)
        self.assertEqual(_appended_with(_RECORD, _OPENING, _NEXT, _NEXT).reasons, {})

    def test_unreported_values_stay_unknown(self) -> None:
        # Reasoning a block leaves out is unknown, never zero; a flag or a context window reported as no usable value
        # is malformed metadata, while one left out is a limitation of the source alone.
        for reported, malformed in _METADATA_SHAPES:
            with self.subTest(reported=reported):
                usage = {**_THREAD_ONLY, "last_token_usage": dict(_NO_REASONING), **reported}
                collection = _appended_with(codex.event(codex.TOKEN_COUNT, info=usage))
                sample = collection.samples[0]
                self.assertEqual(sample[cases.EVIDENCE]["reasoning_tokens"], "missing")
                self.assertFalse({"source_flags", "context_capacity"} & set(sample))
                self.assertEqual(collection.reasons, {coverage.MALFORMED_METADATA: malformed} if malformed else {})
                self.assertIn("no-context-capacity", collection.coverage[_LIMITATIONS])

    def _assert_kept(self, collection: cases.Collected, own: tuple[int, ...], expected: tuple) -> None:
        field_name, gaps = expected
        sample = collection.samples[0]
        self.assertEqual(collection.reasons, gaps)
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

    def test_a_child_turn_marks_its_model_change(self) -> None:
        # A child turn's own `turn_context` naming another model changes that turn's branch, never the thread's.
        collection = codex.appended(*_CHILD_SWITCH_RUN)
        self.assertEqual(cases.column(collection.samples, cases.MODEL), [_CHILD_MODEL, _SWITCHED_CHILD_MODEL])
        self.assertEqual(collection.markers, [dict(_CHILD_MODEL_CHANGE)])
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_unexposed_children_are_gaps(self) -> None:
        for name, lines, gap, count in _UNEXPOSED:
            with self.subTest(name):
                self.assertEqual(_appended_with(*lines).reasons.get(gap), count)

    def test_a_legacy_history_names_its_subagents(self) -> None:
        # A legacy history persists a subagent's activity as an event of its own; its usage is a gap all the same.
        collection = codex.collected(lines=_LEGACY_LOG)
        self.assertEqual(collection.reasons, {coverage.SUBAGENT_USAGE_UNAVAILABLE: 1})
        self.assertEqual(collection.status, coverage.INCOMPLETE)

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

    def test_turn_state_stays_bounded(self) -> None:
        # A child turn's start repeated opens it once, and children past the bound open nothing more.
        collection = codex.appended(*_REPEATED_CHILD)
        self.assertEqual(cases.column(collection.samples, "turn_id"), [codex.CHILD_TURN])
        self.assertEqual(collection.reasons, {})
        limits = dataclasses.replace(request_scan.current_limits(), branches=1)
        turns = Turns(limits, request_scan.Metadata(limits.metadata_chars))
        turns.start({codex.TURN_ID: codex.APPENDED_TURN}, own=True)
        for child in _CHILD_STARTS:
            turns.start(dict(child), own=True)
        self.assertEqual(len(turns.open), 2)
        self.assertTrue(turns.overflowed)

    def test_an_oversize_line_is_skipped(self) -> None:
        # A line past the line bound is counted and skipped however it was handed over, cutting the collection short
        # of the whole log: here it stands where the invocation's turn would open, so stdout's turn cannot be held
        # against the log, and it could have held the report the one after it repeats, so that is no proven request.
        with patch.object(request_scan, "MAX_LINE_CHARS", _LONGEST):
            collection = codex.appended(_OVERSIZE_LINE, _NEXT, _COMPLETE)
        self.assertEqual(len(_OVERSIZE_LINE), _LONGEST + 1)
        self.assertEqual(collection.reasons, {coverage.OVERSIZE_LINES: 1, coverage.UNRECONCILED_USAGE: 1})
        self.assertEqual(collection.status, coverage.SOURCE_LIMIT_TRUNCATED)
        self.assertEqual(collection.coverage[_SCOPE], coverage.PARTIAL_SCOPE)
        self.assertEqual(collection.samples, [])

    def test_a_read_stopped_short(self) -> None:
        # A reader a bound or a failing read stopped records why in the scan it shares with the collection, which is
        # then partial, counting only the lines read; the lines past the cut prove nothing, so neither a turn stdout
        # printed and the read never reached nor a read ending short of the lines the launch counted refuses anything.
        for gap in _READER_STOPS:
            with self.subTest(gap):
                scan = request_scan.EventScan(request_scan.current_limits())
                scan.gaps[gap] += 1
                session = request_codex.NativeSession(_APPENDED_FACTS, enumerate(_ALL_BUT_LAST), scan)
                summary = request_codex.collect(codex.ONE_TURN_STDOUT, session).to_dict()[cases.COVERAGE]
                self.assertEqual(summary[cases.REASONS], {gap: 1})
                self.assertEqual(summary[cases.STATUS], coverage.SOURCE_LIMIT_TRUNCATED)
                self.assertEqual(summary[_SCOPE], coverage.PARTIAL_SCOPE)
                self.assertEqual(summary["scanned_lines"], len(_ALL_BUT_LAST))

    def test_checkpoints_keep_baseline_and_last(self) -> None:
        with patch.object(request_scan, "MAX_CHECKPOINTS", 2):
            collection = codex.collected(capture.SWITCHED)
        self.assertEqual(cases.column(collection.checkpoints, _POSITION), [32, 52])
        self.assertEqual(collection.coverage["observed_checkpoints"], 3)
        self.assertEqual(collection.status, coverage.COMPLETE)


if __name__ == "__main__":
    unittest.main()
