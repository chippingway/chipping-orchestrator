# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request attribution and coverage: what the collection attributes, and what it missed."""

import json
import unittest
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
_RECORD_KIND = "token_usage_record"
_USAGE = "usage"
_LAST_USAGE = "last_token_usage"
_TOTAL_USAGE = "total_token_usage"
_NEXT_USAGE = codex.counters(codex.NEXT_REQUEST)
_TASK_COMPLETE = "task_complete"
_PARENT_TURN = "parent_turn_id"
_PARENT = MappingProxyType({_PARENT_TURN: codex.APPENDED_TURN})
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
# The usage record the CLI writes just before a child request's report, naming the child turn it settles in: with the
# parent turn open beside it, nothing else tells whose a report is.
_CHILD_USAGE = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, _USAGE: _NEXT_USAGE})
_CHILD_RECORD = codex.line(_RECORD_KIND, dict(_CHILD_USAGE))
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
# A context naming a turn the log never opened, and what each context leaves of the thread request after it.
_FOREIGN_CONTEXT = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, cases.MODEL: "gpt-5.5-foreign"})
_UNPLACED_CONTEXT = codex.line(codex.TURN_CONTEXT, dict(_FOREIGN_CONTEXT))
_ATTRIBUTED = (cases.MODEL, _SOURCE)
# Lines no reading places: a child turn's start cut short before the parent it names, a context of the appended turn
# cut short before the model it names, and a context whose payload is no object. Any could have opened a turn or set a
# model.
_THREAD_CONTEXT = MappingProxyType({codex.TURN_ID: codex.APPENDED_TURN, cases.MODEL: _CHILD_MODEL})
_NAMED_CONTEXT = codex.line(codex.TURN_CONTEXT, dict(_THREAD_CONTEXT))
_CUT_CHILD_START = _CHILD_STARTED[:_CHILD_STARTED.rindex(codex.APPENDED_TURN)]
_CUT_CONTEXT = _NAMED_CONTEXT[:_NAMED_CONTEXT.rindex(_CHILD_MODEL)]
_CONTEXT_NO_OBJECT = codex.line(codex.TURN_CONTEXT, [_CHILD_MODEL])
# The appended request reported once more, advancing the running sum the report of it leaves.
_NEXT_AGAIN = codex.token_count((116000, 93100, 14900, 1270, 232, 117270), codex.NEXT_REQUEST)
_PAST_CUT_CONTEXT = (_CUT_CONTEXT, _STARTED, _NEXT, _NEXT_AGAIN, _COMPLETE)
_PAST_CONTEXT_NO_OBJECT = (_CONTEXT_NO_OBJECT, _STARTED, _NEXT, _NEXT_AGAIN, _COMPLETE)
_PAST_UNREAD = MappingProxyType({coverage.UNRECONCILED_USAGE: 1, coverage.MODEL_UNATTRIBUTED: 1})
_UNSET_MODELS = (
    (
        "a refused model",
        (_STARTED, _OVERSIZED_CONTEXT, _NEXT, _COMPLETE),
        (None, "unestablished"),
        {coverage.OVERSIZE_METADATA: 1, coverage.MODEL_UNATTRIBUTED: 1},
    ),
    (
        "a context naming another turn",
        (_STARTED, _UNPLACED_CONTEXT, _NEXT, _COMPLETE),
        (capture.SWITCHED_MODEL, "stream"),
        {coverage.CONVERSATION_AMBIGUOUS: 1},
    ),
    (
        "a turn after a context cut short",
        _PAST_CUT_CONTEXT,
        (None, "unestablished"),
        {**_PAST_UNREAD, coverage.MALFORMED_LINES: 1},
    ),
    (
        "a turn after a context no object",
        _PAST_CONTEXT_NO_OBJECT,
        (None, "unestablished"),
        {**_PAST_UNREAD, coverage.MALFORMED_ENVELOPES: 1},
    ),
)
_UNSTAMPED = f'"timestamp":"{codex.STAMP}",'
_TURN_LINES = (_STARTED, _NEXT, _COMPLETE)
_UNSTAMPED_TURN = tuple(text.replace(_UNSTAMPED, "") for text in _TURN_LINES)
_UNSTAMPED_LOG = (*capture.log_lines(), *_UNSTAMPED_TURN)
# An earlier invocation's running sum left with no usable input, output, or total -- the counters a request moves --
# and a report after it of the request it already reported, whose cache and reasoning counters stay at zero.
_REPLAYED = (100, 0, 0, 10, 0, 110)
_REPLAYED_COUNTERS = MappingProxyType(codex.counters(_REPLAYED))
_UNUSABLE_SUM = (_INVALID_STATE, 0, 0, _INVALID_STATE, 0, _INVALID_STATE)
_UNUSABLE_REPORT = MappingProxyType({
    _TOTAL_USAGE: codex.counters(_UNUSABLE_SUM),
    _LAST_USAGE: codex.counters(_REPLAYED),
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
# The captured log's last request, and a report of it again.
_LAST_REQUEST = (16500, 16000, 0, 25, 5, 16525)
_REPEAT = codex.token_count(codex.LAST_RUNNING, _LAST_REQUEST)
_WRONG = codex.token_count(codex.NEXT_RUNNING, (999, 500, 0, 10, 2, 1009))
_SMALLER = (1, 0, 0, 1, 0, 2)
_BACKWARD = codex.token_count(_SMALLER, _SMALLER)
# A compaction, and the context estimate the CLI follows one with: a total beside parts all zero, its sum unmoved.
_COMPACTED = codex.line("compacted", {})
_ESTIMATE_COUNTS = (0, 0, 0, 0, 0, 9548)
_ESTIMATE = codex.token_count(codex.NEXT_RUNNING, _ESTIMATE_COUNTS)
_OPENING = codex.token_count(codex.LAST_RUNNING, codex.NEXT_REQUEST)
_NO_USAGE = codex.event(codex.TOKEN_COUNT, info=None)
_ROLLBACK = codex.event("thread_rolled_back", num_turns=1)
# A repeat of the appended request's running sum giving half its usage.
_HALVED_REPEAT = codex.token_count(codex.NEXT_RUNNING, (500, 250, 0, 5, 1, 505))
_REPEATS_OF_ONE = (
    ("notifications repeating one report", (_OPENING, _NO_USAGE, _NEXT, _NEXT, _COMPACTED, _ESTIMATE), {}),
    ("a repeat giving other usage", (_NEXT, _HALVED_REPEAT), {coverage.CONFLICTING_COUNTERS: 1}),
    ("a repeat giving other usage after a reset", (_NEXT, _ROLLBACK, _HALVED_REPEAT), {}),
)
_THREAD_ONLY = MappingProxyType({_TOTAL_USAGE: codex.counters(codex.NEXT_RUNNING)})
# A report repeating the captured log's last running sum, its own request usage left out, or carrying a negative count.
_LAST_ONLY = MappingProxyType({_TOTAL_USAGE: codex.counters(codex.LAST_RUNNING)})
_NEGATIVE_REPEAT = (-1, 0, 0, 10, 0, 10)
_REPEAT_NO_USAGE = codex.event(codex.TOKEN_COUNT, info=dict(_LAST_ONLY))
# Repeats of the captured log's last request whose own parts contradict each other, or whose metadata is malformed.
_PAST_INPUT = (1000, 2000, 0, 10, 2, 1010)
_REPEAT_PAST_INPUT = codex.token_count(codex.LAST_RUNNING, _PAST_INPUT)
_OFF_TOTAL = (*_LAST_REQUEST[:-1], 9999)
_REPEAT_OFF_TOTAL = codex.token_count(codex.LAST_RUNNING, _OFF_TOTAL)
_REPEAT_BAD_WINDOW = codex.token_count(codex.LAST_RUNNING, _LAST_REQUEST, model_context_window=-1)
_REPEAT_BAD_FLAG = codex.token_count(codex.LAST_RUNNING, _LAST_REQUEST, last_usage_includes_reasoning="yes")
_INVALID = coverage.INVALID_COUNTERS
_CONFLICTING = coverage.CONFLICTING_COUNTERS
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
# shows and no report covers, one whose second request no report covers -- recorded after its first report, or before
# it, the one report answering only one record -- and one reporting no usage at all. Each resume after them reports the
# request the earlier turn settled last again -- or, after none, its own first one.
_PRIOR_STAMP = "2026-11-12T14:09:00.000Z"
_FRESH_STARTED = codex.event(codex.TASK_STARTED, turn_id=capture.FRESH_TURN)
_FRESH_COMPLETED = codex.event(_TASK_COMPLETE, turn_id=capture.FRESH_TURN)
_PRIOR_STARTED = _FRESH_STARTED.replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_COMPLETE = _FRESH_COMPLETED.replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_RECORD = codex.line(_RECORD_KIND, {_USAGE: codex.counters(_REPLAYED)}, _PRIOR_STAMP)
_PRIOR_REPORT = codex.token_count(_REPLAYED, _REPLAYED).replace(codex.STAMP, _PRIOR_STAMP)
_REPLAYED_TWICE = tuple(2 * count for count in _REPLAYED)
_REPLAYED_THRICE = tuple(3 * count for count in _REPLAYED)
_TWICE_REPLAYED_REPORT = codex.token_count(_REPLAYED_TWICE, _REPLAYED)
_THRICE_REPLAYED_REPORT = codex.token_count(_REPLAYED_THRICE, _REPLAYED)
_UNCOVERED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_COMPLETE)
_LAGGING = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_REPORT, _PRIOR_RECORD, _PRIOR_COMPLETE)
_TWICE_RECORDED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_RECORD, _PRIOR_REPORT, _PRIOR_COMPLETE)
_THRICE_RECORDED = (_FRESH_FIRST, _PRIOR_STARTED, *(_PRIOR_RECORD,) * 3, _PRIOR_REPORT, _PRIOR_COMPLETE)
# A turn whose second report gives a running sum of nothing, below the one its first gave; and one whose running sum
# climbs back from nothing short of where it stood, by exactly a request -- its second, replayed after it.
_NOTHING_COUNTED = (0, 0, 0, 0, 0, 0)
_PRIOR_EMPTIED = codex.token_count(_NOTHING_COUNTED, _NOTHING_COUNTED).replace(codex.STAMP, _PRIOR_STAMP)
_SHRINKING = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_REPORT, _PRIOR_EMPTIED, _PRIOR_COMPLETE)
_PRIOR_SECOND = _TWICE_REPLAYED_REPORT.replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_DROP = (_PRIOR_REPORT, _PRIOR_SECOND, _PRIOR_EMPTIED, _PRIOR_REPORT)
_REGAINING = (_FRESH_FIRST, _PRIOR_STARTED, *_PRIOR_DROP, _PRIOR_COMPLETE)
_UNUSED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_COMPLETE)
# A turn reporting its request, then writing a record no reading can place: a request it settled, whatever branch.
_UNPLACED_RECORD = codex.line(_RECORD_KIND, ["not an object"], _PRIOR_STAMP)
_UNPLACED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_REPORT, _UNPLACED_RECORD, _PRIOR_COMPLETE)
_REPLAYED_REPORT = codex.token_count(_REPLAYED, _REPLAYED)
# A resume after a turn whose second request no report covers: its turn opens repeating the running sum that turn left,
# the report of that earlier request follows late, and then the resume's own request is recorded and reported.
_OWN_RECORD = codex.line(_RECORD_KIND, {_USAGE: dict(_REPLAYED_COUNTERS)})
_OPENING_THEN_LATE = (
    *_LAGGING,
    _STARTED,
    _REPLAYED_REPORT,
    _TWICE_REPLAYED_REPORT,
    _OWN_RECORD,
    _THRICE_REPLAYED_REPORT,
    _COMPLETE,
)
_OWN_REPORT_LINE = len(_OPENING_THEN_LATE) - 2
# The same resume opening with a notification naming no running sum before the repeat: it shows no request new, so it
# answers no record either, and the report after the repeat is still the earlier request reported late.
_SUMLESS_REPLAYED = codex.event(codex.TOKEN_COUNT, info={_LAST_USAGE: dict(_REPLAYED_COUNTERS)})
_SUMLESS_THEN_LATE = (*_LAGGING, _STARTED, _SUMLESS_REPLAYED, _REPLAYED_REPORT, _TWICE_REPLAYED_REPORT, _COMPLETE)
_SUMLESS_GAPS = MappingProxyType({coverage.MALFORMED_USAGE: 1, coverage.UNRECONCILED_USAGE: 2})
# The same resume opening with the earlier sum repeated short of its reasoning count: agreeing on every counter it
# reports shows no rise, so it answers no record, and the report after it is still the earlier request reported late.
_SPARSE_REPEAT_SUM = MappingProxyType({
    counter: count
    for counter, count in _REPLAYED_COUNTERS.items()
    if counter != "reasoning_output_tokens"
})
_SPARSE_REPEAT_INFO = MappingProxyType({_TOTAL_USAGE: dict(_SPARSE_REPEAT_SUM), _LAST_USAGE: dict(_REPLAYED_COUNTERS)})
_SPARSE_REPEAT = codex.event(codex.TOKEN_COUNT, info=dict(_SPARSE_REPEAT_INFO))
_SPARSE_THEN_LATE = (*_LAGGING, _STARTED, _SPARSE_REPEAT, _TWICE_REPLAYED_REPORT, _COMPLETE)
# A turn leaving two requests no report covers, then a resume whose running sum shrinks and climbs back to the last one
# reported: neither rises past what the earlier reports established, so both requests are still the two reports after.
_TWO_LAGGING = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_REPORT, *(_PRIOR_RECORD,) * 2, _PRIOR_COMPLETE)
_HALVED_SUM = tuple(count // 2 for count in _REPLAYED)
_CLIMBING_BACK = (
    _STARTED,
    codex.token_count(_HALVED_SUM, _REPLAYED),
    _REPLAYED_REPORT,
    _TWICE_REPLAYED_REPORT,
    _THRICE_REPLAYED_REPORT,
    _COMPLETE,
)
_CLIMBING_GAPS = MappingProxyType({coverage.UNRECONCILED_USAGE: 4, coverage.CONFLICTING_COUNTERS: 1})
# An earlier turn whose child turn closed leaving a request no report covers, then a resume whose one report advances
# the thread by exactly that request: a report coming late settles in whatever turn is open, so it is no proven
# request of the resume's, however its counts fit.
_PRIOR_CHILD_ATTRIBUTION = MappingProxyType({_PARENT_TURN: capture.FRESH_TURN})
_PRIOR_CHILD_STARTED = codex.event(
    codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_PRIOR_CHILD_ATTRIBUTION),
).replace(codex.STAMP, _PRIOR_STAMP)
_PRIOR_CHILD_USAGE = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, _USAGE: dict(_REPLAYED_COUNTERS)})
_PRIOR_CHILD_RECORD = codex.line(_RECORD_KIND, dict(_PRIOR_CHILD_USAGE), _PRIOR_STAMP)
_PRIOR_CHILD_COMPLETE = codex.event(_TASK_COMPLETE, turn_id=codex.CHILD_TURN).replace(codex.STAMP, _PRIOR_STAMP)
_CLOSED_CHILD = (
    _FRESH_FIRST,
    _PRIOR_STARTED,
    _PRIOR_RECORD,
    _PRIOR_REPORT,
    _PRIOR_CHILD_STARTED,
    _PRIOR_CHILD_RECORD,
    _PRIOR_REPORT,
    _PRIOR_CHILD_RECORD,
    _PRIOR_CHILD_COMPLETE,
    _PRIOR_COMPLETE,
)
# An earlier turn whose child turn names no id, its report coming after its parent closed: no branch keeps that report's
# running sum, so it could be repeated in the resume's turn, and no report of the resume's is proven past it until the
# thread's own says where its sum stands, after which the resume's next request is its own.
_PRIOR_UNNAMED = codex.event(codex.TASK_STARTED, turn_attribution=dict(_PRIOR_CHILD_ATTRIBUTION))
_UNNAMED_REPORTED = (
    _FRESH_FIRST,
    _PRIOR_STARTED,
    _PRIOR_UNNAMED.replace(codex.STAMP, _PRIOR_STAMP),
    _PRIOR_COMPLETE,
    _PRIOR_REPORT,
)
_UNNAMED_THEN_RESUMED = (*_UNNAMED_REPORTED, _STARTED, _REPLAYED_REPORT, _OWN_RECORD, _TWICE_REPLAYED_REPORT, _COMPLETE)
# An earlier turn recording three requests under a turn id past the metadata bound, which places them on no branch,
# each reported late past the boundary: the first report placed in no turn, the next two in the resume's own.
_OVERSIZED_TURN = "t" * (request_scan.MAX_METADATA_CHARS + 1)
_UNBRANCHED_USAGE = MappingProxyType({codex.TURN_ID: _OVERSIZED_TURN, _USAGE: dict(_REPLAYED_COUNTERS)})
_UNBRANCHED_RECORD = codex.line(_RECORD_KIND, dict(_UNBRANCHED_USAGE), _PRIOR_STAMP)
_UNBRANCHED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_REPORT, *(_UNBRANCHED_RECORD,) * 3, _PRIOR_COMPLETE)
_FOURFOLD_REPORT = codex.token_count(tuple(4 * count for count in _REPLAYED), _REPLAYED)
_UNBRANCHED_LATE = (_STARTED, _TWICE_REPLAYED_REPORT, _THRICE_REPLAYED_REPORT, _FOURFOLD_REPORT, _COMPLETE)
_UNBRANCHED_GAPS = MappingProxyType({
    coverage.OVERSIZE_METADATA: 3,
    coverage.CONVERSATION_AMBIGUOUS: 1,
    coverage.UNRECONCILED_USAGE: 2,
})
# The same records, two of them, then a resume whose child turn records and reports three requests of its own before
# the thread reports the two earlier ones late: a record on no branch is answered by no report, and a report coming late
# could settle in any turn, so the thread's reports giving the counts those records repeat are no proven requests, while
# the child's last, giving others, is its own -- its first placed in no turn past the refused records, its second
# unproven past that.
_CHILD_TWICE_SUM = (2000, 1000, 0, 20, 4, 2020)
_CHILD_THRICE_SUM = (3000, 1500, 0, 30, 6, 3030)
_CHILD_RUNS = (
    _CHILD_RECORD,
    _CHILD_REQUEST,
    _CHILD_RECORD,
    codex.token_count(_CHILD_TWICE_SUM, codex.NEXT_REQUEST),
    _CHILD_RECORD,
    codex.token_count(_CHILD_THRICE_SUM, codex.NEXT_REQUEST),
)
_TWO_UNBRANCHED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_REPORT, *(_UNBRANCHED_RECORD,) * 2, _PRIOR_COMPLETE)
_CHILD_FIRST = (
    _STARTED,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    *_CHILD_RUNS,
    _CHILD_COMPLETE,
    _TWICE_REPLAYED_REPORT,
    _THRICE_REPLAYED_REPORT,
    _COMPLETE,
)
_CHILD_FIRST_SAMPLE = len(_TWO_UNBRANCHED) + 8
_CHILD_FIRST_GAPS = MappingProxyType({
    coverage.OVERSIZE_METADATA: 2,
    coverage.CONVERSATION_AMBIGUOUS: 1,
    coverage.UNRECONCILED_USAGE: 3,
    coverage.UNSUPPORTED_USAGE_SOURCE: 1,
})
# A resume whose parent turn finishes before the child turn it started, which then reports the request an earlier turn
# recorded and no report covered: that is its report coming late, settling in whatever turn is open, so it is no request
# of the child's, however its branch, opened after it, stands -- nor once the parent's own request, recorded before its
# report, is reported, which leaves the earlier record awaiting a report of the counts it repeats.
_CHILD_LATE = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _COMPLETE, _REPLAYED_REPORT, _CHILD_COMPLETE)
# An earlier turn whose one request was reported, its running sum the request alone, before that resume: the report in
# the child turn is the thread's last report repeated -- whole, or leaving a counter of its running sum out -- which
# settles in whatever turn is open too.
_COVERED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_REPORT, _PRIOR_COMPLETE)
_AFTER_COVERED = codex.APPENDED._replace(start=len(_COVERED))
_SPARSE_IN_CHILD = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _COMPLETE, _SPARSE_REPEAT, _CHILD_COMPLETE)
_REPEATS_IN_CHILD = (
    ("whole", (*_COVERED, *_CHILD_LATE)),
    ("sparser", (*_COVERED, *_SPARSE_IN_CHILD)),
)
_PARENT_RECORDED = (
    _STARTED,
    codex.line(_RECORD_KIND, {_USAGE: codex.counters(_REPLAYED_TWICE)}),
    codex.token_count(_REPLAYED_THRICE, _REPLAYED_TWICE),
    *_CHILD_LATE[1:],
)
_LATE_IN_CHILD_GAPS = MappingProxyType({coverage.UNRECONCILED_USAGE: 1, coverage.SUBAGENT_USAGE_UNAVAILABLE: 1})
# An earlier line whose event names nothing, so no reading places it, before the same resume: it could have been a
# report the child's first repeats, so a branch opened after it proves nothing by its first report.
_NAMELESS_INFO = MappingProxyType({_LAST_USAGE: dict(_REPLAYED_COUNTERS), _TOTAL_USAGE: dict(_REPLAYED_COUNTERS)})
_NAMELESS = codex.line(codex.EVENT_MSG, {"info": dict(_NAMELESS_INFO)}, _PRIOR_STAMP)
_NAMELESS_BEFORE = (_FRESH_FIRST, _NAMELESS)
_PARENT_THEN_CHILD_GAPS = MappingProxyType({coverage.UNRECONCILED_USAGE: 2, coverage.SUBAGENT_USAGE_UNAVAILABLE: 1})
# An earlier parent turn recording a request by its id while its child turn, already running on a model of its own, is
# open, and finishing first, the child then reporting a request it recorded none of: that report answers none of the
# parent's records, so the resume's first report of the thread is still that request reported late, and only the
# request the resume records after it is its own.
_PRIOR_PARENT_RECORD = codex.line(
    _RECORD_KIND, {codex.TURN_ID: capture.FRESH_TURN, _USAGE: codex.counters(_REPLAYED_TWICE)}, _PRIOR_STAMP,
)
_PARENT_BEHIND_CHILD = (
    _FRESH_FIRST,
    _PRIOR_STARTED,
    _PRIOR_CHILD_STARTED,
    _CHILD_CONTEXT.replace(codex.STAMP, _PRIOR_STAMP),
    _PRIOR_PARENT_RECORD,
    _PRIOR_COMPLETE,
    _PRIOR_REPORT,
    _PRIOR_CHILD_COMPLETE,
)
_PARENT_LATE = (
    _STARTED,
    codex.token_count(_REPLAYED_TWICE, _REPLAYED_TWICE),
    _OWN_RECORD,
    _THRICE_REPLAYED_REPORT,
    _COMPLETE,
)
_AFTER_PARENT_LATE = len(_PARENT_BEHIND_CHILD) + len(_PARENT_LATE) - 2
# An earlier turn leaving two requests of other counts no report covers, then a resume whose child turn records and
# reports a request of its own.
_TWO_AWAITED = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_RECORD, _PRIOR_PARENT_RECORD, _PRIOR_COMPLETE)
_AWAITED_THEN_CHILD = (
    *_TWO_AWAITED, _STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _CHILD_RECORD, _CHILD_REQUEST, _CHILD_COMPLETE, _COMPLETE,
)
# An earlier report whose request is more than the running sum beside it, and a resume's sum past that sum yet still
# below that request: a sum holds the request beside it, so the earlier one is contradicted, and no baseline is kept.
_TENTH = tuple(count // 10 for count in _REPLAYED)
_TWO_TENTHS = tuple(2 * count for count in _TENTH)
_BELOW_ITS_OWN = codex.token_count(_TENTH, _REPLAYED).replace(codex.STAMP, _PRIOR_STAMP)
_BELOW_ITS_OWN_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, _BELOW_ITS_OWN, _PRIOR_COMPLETE)
_STILL_BELOW = codex.token_count(_TWO_TENTHS, _TENTH)
_STILL_BELOW_GAPS = MappingProxyType({coverage.UNRECONCILED_USAGE: 1, coverage.CONFLICTING_COUNTERS: 1})
# The same, the request past the sum reported beside a repeat of it: a repeat is no request, but its sum holds the one
# reported beside it all the same.
_REPEAT_PAST_ITS_SUM = codex.token_count(_REPLAYED, _REPLAYED_TWICE).replace(codex.STAMP, _PRIOR_STAMP)
_REPEAT_BELOW_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_REPORT, _REPEAT_PAST_ITS_SUM, _PRIOR_COMPLETE)
# So is such a repeat right after a compaction: only the context estimate, moving its total alone, is no request.
_COMPACTED_PRIOR = codex.line("compacted", {}, _PRIOR_STAMP)
_COMPACTED_REPEAT_PRIOR = (*_REPEAT_BELOW_PRIOR[:3], _COMPACTED_PRIOR, *_REPEAT_BELOW_PRIOR[3:])
_PAST_REPEAT_SUM = tuple(
    whole + part
    for whole, part in zip(_REPLAYED, _TENTH, strict=True)
)
_PAST_REPEAT = codex.token_count(_PAST_REPEAT_SUM, _TENTH)
# A resume whose parent turn records two requests of other counts and closes before the child turn it started reports
# them both late, the child having recorded one of the second's counts: neither report is the child's, whichever of the
# parent's records it could repeat, the earliest or not.
_PARENT_USAGES = (
    (codex.APPENDED_TURN, _REPLAYED),
    (codex.APPENDED_TURN, _REPLAYED_TWICE),
    (codex.CHILD_TURN, _REPLAYED_TWICE),
)
_PARENT_RECORDS = tuple(
    codex.line(_RECORD_KIND, {codex.TURN_ID: turn, _USAGE: codex.counters(counts)})
    for turn, counts in _PARENT_USAGES
)
_PARENT_LATE_TWICE = (
    _FRESH_FIRST,
    _STARTED,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    *_PARENT_RECORDS[:2],
    _COMPLETE,
    _PARENT_RECORDS[2],
    _REPLAYED_REPORT,
    codex.token_count(_REPLAYED_THRICE, _REPLAYED_TWICE),
    _CHILD_COMPLETE,
)
_PARENT_LATE_TWICE_GAPS = MappingProxyType({
    coverage.UNRECONCILED_USAGE: 2,
    coverage.UNSUPPORTED_USAGE_SOURCE: 2,
    coverage.SUBAGENT_USAGE_UNAVAILABLE: 1,
})
_NO_GAPS = MappingProxyType({})
_ONE_UNPROVEN = MappingProxyType({coverage.UNRECONCILED_USAGE: 1})
_TWO_UNPROVEN = MappingProxyType({coverage.UNRECONCILED_USAGE: 2})
_BEHIND = (
    (
        "a request no report covers",
        len(_UNCOVERED),
        (*_UNCOVERED, _STARTED, _REPLAYED_REPORT, _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "a request past the last report",
        len(_LAGGING),
        (*_LAGGING, _STARTED, codex.token_count(_REPLAYED_TWICE, _REPLAYED), _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "two requests before the last report",
        len(_TWICE_RECORDED),
        (*_TWICE_RECORDED, _STARTED, codex.token_count(_REPLAYED_TWICE, _REPLAYED), _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "three requests before the last report, two reported past the boundary",
        len(_THRICE_RECORDED),
        (*_THRICE_RECORDED, _STARTED, _TWICE_REPLAYED_REPORT, _THRICE_REPLAYED_REPORT, _COMPLETE),
        ([], _TWO_UNPROVEN),
    ),
    (
        "a request past the last report, its record unreadable",
        len(_UNPLACED),
        (*_UNPLACED, _STARTED, codex.token_count(_REPLAYED_TWICE, _REPLAYED), _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "a running sum shrinking",
        len(_SHRINKING),
        (*_SHRINKING, _STARTED, _REPLAYED_REPORT, _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "a running sum climbing back short of where it stood",
        len(_REGAINING),
        (*_REGAINING, _STARTED, _TWICE_REPLAYED_REPORT, _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "a turn opening with the last running sum, then a request past it reported late",
        len(_LAGGING),
        _OPENING_THEN_LATE,
        ([_OWN_REPORT_LINE], _TWO_UNPROVEN),
    ),
    (
        "a notification naming no running sum, then a request past the last report reported late",
        len(_LAGGING),
        _SUMLESS_THEN_LATE,
        ([], _SUMLESS_GAPS),
    ),
    (
        "a sparser repeat of the last running sum, then a request past the last report reported late",
        len(_LAGGING),
        _SPARSE_THEN_LATE,
        ([], _TWO_UNPROVEN),
    ),
    (
        "a running sum shrinking and climbing back, then two requests past the last report reported late",
        len(_TWO_LAGGING),
        (*_TWO_LAGGING, *_CLIMBING_BACK),
        ([], _CLIMBING_GAPS),
    ),
    (
        "a closed child turn's request no report covers, then a report fitting the thread's advance",
        len(_CLOSED_CHILD),
        (*_CLOSED_CHILD, _STARTED, _TWICE_REPLAYED_REPORT, _COMPLETE),
        ([], _ONE_UNPROVEN),
    ),
    (
        "three requests recorded on no branch, reported past the boundary",
        len(_UNBRANCHED),
        (*_UNBRANCHED, *_UNBRANCHED_LATE),
        ([], _UNBRANCHED_GAPS),
    ),
    (
        "two requests recorded on no branch, then a new child turn's requests",
        len(_TWO_UNBRANCHED),
        (*_TWO_UNBRANCHED, *_CHILD_FIRST),
        ([_CHILD_FIRST_SAMPLE], _CHILD_FIRST_GAPS),
    ),
    (
        "a request no report covers, reported late in a child turn the resume opens",
        len(_UNCOVERED),
        (*_UNCOVERED, *_CHILD_LATE),
        ([], _LATE_IN_CHILD_GAPS),
    ),
    (
        "a request no report covers, reported late in a child turn after the parent's own",
        len(_UNCOVERED),
        (*_UNCOVERED, *_PARENT_RECORDED),
        ([], _PARENT_THEN_CHILD_GAPS),
    ),
    (
        "a running sum below the request reported beside it",
        len(_BELOW_ITS_OWN_PRIOR),
        (*_BELOW_ITS_OWN_PRIOR, _STARTED, _STILL_BELOW, _COMPLETE),
        ([], _STILL_BELOW_GAPS),
    ),
    (
        "a repeated running sum below the request reported beside it",
        len(_REPEAT_BELOW_PRIOR),
        (*_REPEAT_BELOW_PRIOR, _STARTED, _PAST_REPEAT, _COMPLETE),
        ([], _STILL_BELOW_GAPS),
    ),
    (
        "a repeated running sum below the request reported beside it, after a compaction",
        len(_COMPACTED_REPEAT_PRIOR),
        (*_COMPACTED_REPEAT_PRIOR, _STARTED, _PAST_REPEAT, _COMPLETE),
        ([], _STILL_BELOW_GAPS),
    ),
    (
        "a parent's two recorded requests reported late in its child turn",
        1,
        _PARENT_LATE_TWICE,
        ([], _PARENT_LATE_TWICE_GAPS),
    ),
    (
        "a report no branch takes, repeated in the resume's turn",
        len(_UNNAMED_REPORTED),
        _UNNAMED_THEN_RESUMED,
        ([len(_UNNAMED_THEN_RESUMED) - 2], _ONE_UNPROVEN),
    ),
    (
        "an envelope no reading could place, then a new child turn's first report",
        len(_NAMELESS_BEFORE),
        (*_NAMELESS_BEFORE, *_CHILD_LATE),
        ([], _LATE_IN_CHILD_GAPS),
    ),
    (
        "a parent's request no report covers, beside its child's report of none",
        len(_PARENT_BEHIND_CHILD),
        (*_PARENT_BEHIND_CHILD, *_PARENT_LATE),
        ([_AFTER_PARENT_LATE], _ONE_UNPROVEN),
    ),
    (
        "no usage before",
        len(_UNUSED),
        (*_UNUSED, _STARTED, _REPLAYED_REPORT, _COMPLETE),
        ([len(_UNUSED) + 1], _NO_GAPS),
    ),
)
# Reports that make no sample, and the evidence each still leaves: one naming no running sum beside request usage
# no count of which is usable, and a fresh run's first, repeating a running sum of nothing its own counts exceed.
_SUMLESS_COUNTS = codex.counters((-1, 0, 0, 10, 2, 0))
_SUMLESS_USAGE = MappingProxyType({_LAST_USAGE: _SUMLESS_COUNTS})
_SUMLESS = codex.event(codex.TOKEN_COUNT, info=dict(_SUMLESS_USAGE))
_PAST_NOTHING = codex.token_count((0, 0, 0, 0, 0, 0), codex.NEXT_REQUEST)
# An earlier turn whose report counted output alone, and a request after it whose input exceeds the running sum's.
_INPUT = codex.COUNTERS[0]
_OUTPUT = codex.COUNTERS[3]
_TOTAL = codex.COUNTERS[5]
_OUTPUT_COUNT = dict.fromkeys((_OUTPUT,), 10)
_OUTPUT_ONLY = MappingProxyType({_TOTAL_USAGE: _OUTPUT_COUNT, _LAST_USAGE: _OUTPUT_COUNT})
_OUTPUT_REPORT = codex.event(codex.TOKEN_COUNT, info=dict(_OUTPUT_ONLY))
_PRIOR_OUTPUT = _OUTPUT_REPORT.replace(codex.STAMP, _PRIOR_STAMP)
_OUTGROWN_COUNTERS = (_INPUT, _OUTPUT, _TOTAL)
_OUTGROWN_SUM = dict(zip(_OUTGROWN_COUNTERS, (1, 20, 21), strict=True))
_OUTGROWN_OWN = dict(zip(_OUTGROWN_COUNTERS, (100, 10, 110), strict=True))
_OUTGROWN_INFO = MappingProxyType({_TOTAL_USAGE: _OUTGROWN_SUM, _LAST_USAGE: _OUTGROWN_OWN})
_OUTGROWN = codex.event(codex.TOKEN_COUNT, info=dict(_OUTGROWN_INFO))
_PARTIAL_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, _PRIOR_OUTPUT, _PRIOR_COMPLETE)
# An earlier report proving no request -- its sparse running sum leaving out counters its request reports -- and a
# running sum after it holding less input than that request: whether or not it was new, the sum holds it.
_SPARSE_UNPROVEN_INFO = MappingProxyType({_TOTAL_USAGE: {_OUTPUT: 20}, _LAST_USAGE: dict(_OUTGROWN_OWN)})
_SPARSE_UNPROVEN_REPORT = codex.event(codex.TOKEN_COUNT, info=dict(_SPARSE_UNPROVEN_INFO))
_SPARSE_UNPROVEN = _SPARSE_UNPROVEN_REPORT.replace(codex.STAMP, _PRIOR_STAMP)
_UNPROVEN_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, _SPARSE_UNPROVEN, _PRIOR_COMPLETE)
_UNDER_UNPROVEN_SUM = dict(zip(_OUTGROWN_COUNTERS, (50, 30, 80), strict=True))
_UNDER_UNPROVEN_OWN = dict(zip(_OUTGROWN_COUNTERS, (1, 10, 11), strict=True))
_UNDER_UNPROVEN_INFO = MappingProxyType({_TOTAL_USAGE: _UNDER_UNPROVEN_SUM, _LAST_USAGE: _UNDER_UNPROVEN_OWN})
_UNDER_UNPROVEN = codex.event(codex.TOKEN_COUNT, info=dict(_UNDER_UNPROVEN_INFO))
# A child turn's second report, of three, replayed in its parent's turn once the child closed, fitting the thread's next
# step: no record of the thread's vouches for it, so it is no request of the thread's.
_CHILD_REPLAYED_USAGE = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, _USAGE: codex.counters(_REPLAYED)})
_CHILD_REPLAYED_RECORD = codex.line(_RECORD_KIND, dict(_CHILD_REPLAYED_USAGE))
_CHILD_REPLAYED_ON_THREAD = (
    *_COVERED,
    _STARTED,
    _NAMED_CONTEXT,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    _CHILD_REPLAYED_RECORD,
    _REPLAYED_REPORT,
    _CHILD_REPLAYED_RECORD,
    _TWICE_REPLAYED_REPORT,
    _CHILD_REPLAYED_RECORD,
    _THRICE_REPLAYED_REPORT,
    _CHILD_COMPLETE,
    _TWICE_REPLAYED_REPORT,
    _COMPLETE,
)
# A request after the resume, then a compaction and the context estimate after it, whose total, the context's size, is
# past the running sum: it is no request, so the sum is not held to it.
_ESTIMATED_PAST = (
    *_COVERED,
    _STARTED,
    _NAMED_CONTEXT,
    _OWN_RECORD,
    _TWICE_REPLAYED_REPORT,
    _COMPACTED,
    codex.token_count(_REPLAYED_TWICE, _ESTIMATE_COUNTS),
    _COMPLETE,
)
# The same estimate once a child turn reported between the thread's requests: it is no request whichever branches
# reported before it, so the thread's next request is still its own.
_ESTIMATED_AFTER_CHILD = (
    *_COVERED,
    _STARTED,
    _NAMED_CONTEXT,
    _OWN_RECORD,
    _TWICE_REPLAYED_REPORT,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    _CHILD_RECORD,
    _CHILD_REQUEST,
    _CHILD_COMPLETE,
    _COMPACTED,
    codex.token_count(_REPLAYED_TWICE, _ESTIMATE_COUNTS),
    _OWN_RECORD,
    _THRICE_REPLAYED_REPORT,
    _COMPLETE,
)
# The thread's first report after the resume replayed in a child turn once the thread reported again: no record of the
# child's vouches for it, so it is no request of the child's, whichever of the thread's earlier sums it repeats.
_EARLIER_REPLAYED = (
    *_COVERED,
    _STARTED,
    _NAMED_CONTEXT,
    _OWN_RECORD,
    _TWICE_REPLAYED_REPORT,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    _COMPLETE,
    _REPLAYED_REPORT,
    _CHILD_COMPLETE,
)
# Reasons a reader states for a log it read no line of.
_READER_REASONS = (
    coverage.NO_SESSION_IDENTITY,
    coverage.NO_LAUNCH_OBSERVATION,
    coverage.NATIVE_LOG_MISSING,
    coverage.NATIVE_LOG_UNREADABLE,
    coverage.DISCOVERY_LIMIT,
)
# Logs no proof places the invocation in, each refused before a line of them is attributed, whatever requests the fold
# read off them: one opening with no `session_meta`, a resume its launch counted no lines for, one whose stamps go
# backward, a turn stdout never printed, and a silent resume settling usage in the turn the interrupted invocation left
# open.
_RESUMED_LINES = capture.log_lines(capture.RESUMED.end)
_RESUMED_STAMP = '"timestamp":"2026-11-12T13:55:10.322Z"'
_EARLY_STAMP = '"timestamp":"2026-11-12T13:50:00.000Z"'
_RESTAMPED = tuple(text.replace(_RESUMED_STAMP, _EARLY_STAMP) for text in _RESUMED_LINES)
_SILENT = codex.APPENDED._replace(stdout="")
_AFTER_INTERRUPTED = codex.APPENDED._replace(start=capture.INTERRUPTED.end, stdout="")
_INTERRUPTED_USAGE = MappingProxyType({codex.TURN_ID: capture.INTERRUPTED_TURN, _USAGE: _NEXT_USAGE})
_INTRUDING = (
    *capture.log_lines(capture.INTERRUPTED.end),
    codex.line(_RECORD_KIND, dict(_INTERRUPTED_USAGE)),
    codex.token_count((98500, 76600, 14900, 1235, 225, 99735), codex.NEXT_REQUEST),
)
_UNATTRIBUTED = coverage.INVOCATION_UNATTRIBUTED
_REFUSED = (
    ("no session_meta first", capture.FRESH, _FRESH_LINES[1:], coverage.NATIVE_IDENTITY_UNPROVEN),
    ("a resume counted nothing for", capture.RESUMED._replace(start=None), _RESUMED_LINES, _UNATTRIBUTED),
    ("stamps going backward", capture.RESUMED, _RESTAMPED, _UNATTRIBUTED),
    ("a turn stdout never printed", _SILENT, (*capture.log_lines(), *_TURN_LINES), _UNATTRIBUTED),
    ("usage in an earlier invocation's open turn", _AFTER_INTERRUPTED, _INTRUDING, _UNATTRIBUTED),
)
_OBSERVED = ("observed_samples", "observed_markers", "observed_checkpoints")
# Reports never taken for a new request: one in the turn after a line no reading could place -- which could repeat the
# one that line held, an earlier invocation's included -- one whose running sum moves by anything but its own counters,
# and one in a child turn after its parent turn closed with a request recorded and unreported, which it could report.
_THREAD_RECORD = codex.line(_RECORD_KIND, {codex.TURN_ID: codex.APPENDED_TURN, _USAGE: _NEXT_USAGE})
_PARENT_LATE_IN_CHILD = (_STARTED, _THREAD_RECORD, _CHILD_STARTED, _CHILD_CONTEXT, _COMPLETE, _CHILD_REQUEST)
# A report its own counts cannot prove new: two of them negative, and its total below its output.
_UNUSABLE_COUNTS = (-1, -1, 0, 10, 2, 0)
_UNUSABLE_OWN = codex.token_count(codex.NEXT_RUNNING, _UNUSABLE_COUNTS)
_UNPROVEN_REPORTS = (
    ("after a line cut short", (_CUT_SHORT, _STARTED, _NEXT, _COMPLETE), {coverage.MALFORMED_LINES}),
    ("an earlier report after one cut short", (_CUT_SHORT, _STARTED, _REPEAT, _COMPLETE), {coverage.MALFORMED_LINES}),
    ("moving by another request", (_STARTED, _WRONG, _COMPLETE), set()),
    ("moving backward", (_STARTED, _BACKWARD, _COMPLETE), {_CONFLICTING}),
    ("its own counts unusable", (_STARTED, _UNUSABLE_OWN, _COMPLETE), {_INVALID, _CONFLICTING}),
    (
        "the parent's recorded request after its turn closed",
        (*_PARENT_LATE_IN_CHILD, _CHILD_COMPLETE),
        {coverage.UNSUPPORTED_USAGE_SOURCE, coverage.SUBAGENT_USAGE_UNAVAILABLE},
    ),
)
_UNREADABLE = (
    ("info no object", codex.event(codex.TOKEN_COUNT, info=[1]), coverage.MALFORMED_USAGE),
    ("no running sum", codex.event(codex.TOKEN_COUNT, info={_LAST_USAGE: {}}), coverage.MALFORMED_USAGE),
    ("no request usage", codex.event(codex.TOKEN_COUNT, info=dict(_THREAD_ONLY)), coverage.MALFORMED_USAGE),
    ("payload no object", codex.line(codex.EVENT_MSG, [1]), coverage.MALFORMED_ENVELOPES),
    ("event naming nothing", codex.line(codex.EVENT_MSG, {"info": {}}), coverage.MALFORMED_ENVELOPES),
    ("no kind", json.dumps({"timestamp": codex.STAMP, "payload": {}}), coverage.MALFORMED_ENVELOPES),
    ("a repeat naming no request usage", _REPEAT_NO_USAGE, coverage.MALFORMED_USAGE),
    ("a repeat reporting no whole count", codex.token_count(codex.LAST_RUNNING, _NEGATIVE_REPEAT), _INVALID),
    ("a repeat whose reads pass its input", _REPEAT_PAST_INPUT, coverage.CONFLICTING_COUNTERS),
    ("a repeat whose total its parts contradict", _REPEAT_OFF_TOTAL, coverage.CONFLICTING_COUNTERS),
    ("an estimate no compaction precedes", codex.token_count(codex.LAST_RUNNING, _ESTIMATE_COUNTS), _CONFLICTING),
    ("a repeat beside a malformed window", _REPEAT_BAD_WINDOW, coverage.MALFORMED_METADATA),
    ("a repeat beside a malformed flag", _REPEAT_BAD_FLAG, coverage.MALFORMED_METADATA),
)
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
_INVALID_CHILD_RUNNING = (-1, *codex.NEXT_REQUEST[1:])
_INVALID_CHILD_REQUEST = codex.token_count(_INVALID_CHILD_RUNNING, codex.NEXT_REQUEST)
_INVALID_CHILD_RUN = (_CHILD_STARTED, _CHILD_CONTEXT, _CHILD_RECORD, _INVALID_CHILD_REQUEST, _CHILD_COMPLETE)
_NO_OBJECTS = ('[{"type":"event_msg"}]', "Codex ready", "   ", "")
_UNUSABLE_STATES = frozenset((_INVALID_STATE, "conflicting"))
# Children the invocation's lines expose less than whole, each with the gaps it leaves and the requests kept: a child
# turn naming no id can never be closed, and one its parent finished without keeps what it settled, unfinished.
_UNAVAILABLE_CHILD = MappingProxyType({coverage.SUBAGENT_USAGE_UNAVAILABLE: 1})
_UNIDENTIFIED_CHILD = MappingProxyType({coverage.SUBAGENT_UNIDENTIFIED: 1})
_UNNAMED_TURN = MappingProxyType({coverage.SUBAGENT_UNIDENTIFIED: 1, coverage.NO_TERMINAL_RESULT: 1})
_UNEXPOSED = (
    ("child turn with no request", (_CHILD_STARTED, _CHILD_COMPLETE), _UNAVAILABLE_CHILD, 0),
    (
        "child turn naming no model",
        (_CHILD_STARTED, _CHILD_RECORD, _CHILD_REQUEST, _CHILD_COMPLETE),
        {coverage.SUBAGENT_MODEL_UNESTABLISHED: 1},
        1,
    ),
    (
        "child turn its parent finished without",
        (_CHILD_STARTED, _CHILD_CONTEXT, _CHILD_RECORD, _CHILD_REQUEST),
        {coverage.NO_TERMINAL_RESULT: 1},
        1,
    ),
    ("child turn naming no id", (_UNNAMED_CHILD, _NEXT), {**_UNNAMED_TURN, coverage.CONVERSATION_AMBIGUOUS: 1}, 0),
    ("child turn naming no id, no request", (_UNNAMED_CHILD,), _UNNAMED_TURN, 0),
    ("subagent threads", (_ACTIVITY, _ACTIVITY, _OTHER_ACTIVITY), {coverage.SUBAGENT_USAGE_UNAVAILABLE: 2}, 0),
    ("subagent naming no thread", (_UNNAMED_ACTIVITY,), _UNIDENTIFIED_CHILD, 0),
    ("legacy subagent event", (_LEGACY_EVENT,), _UNAVAILABLE_CHILD, 0),
    ("legacy subagent event naming no thread", (_UNNAMED_LEGACY_EVENT,), _UNIDENTIFIED_CHILD, 0),
)
# Each correlation bound, held to its least, and how many entries past it a collection drops: a child turn refused
# is one, whether or not a request follows it, and each request it leaves unattributable another.
_CHILD_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _CHILD_REQUEST, _COMPLETE)
_QUIET_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _CHILD_COMPLETE, _COMPLETE)
_OPEN_OVERRUN = (*capture.log_lines(), _STARTED, _CHILD_STARTED, _UNNAMED_CHILD, _NEXT, _COMPLETE)
_THREAD_OVERRUN = (*capture.log_lines(), _STARTED, _ACTIVITY, _OTHER_ACTIVITY, _ACTIVITY, _COMPLETE)
_BRANCHES = "MAX_BRANCHES"
# Three requests the invocation recorded and never reported, and the gaps they leave past a request bound of one.
_RECORDED_THRICE = (_STARTED, *(_OWN_RECORD,) * 3, _COMPLETE)
_PAST_REQUEST_BOUND = MappingProxyType({coverage.CORRELATION_LIMIT: 2, coverage.UNSUPPORTED_USAGE_SOURCE: 3})
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
_PADDED_LINE = " " * (_LONGEST + 1 - len(_NO_USAGE)) + _NO_USAGE
# What stops a reader before the log's end, which it records in the scan it shares once it stops: a read bound, and a
# read failing partway.
_READER_STOPS = (coverage.SCAN_LIMIT, coverage.NATIVE_READ_INTERRUPTED)
_APPENDED_FACTS = Invocation(capture.SESSION_ID, True, codex.APPENDED_AT, codex.APPENDED.start)
_ALL_BUT_LAST = capture.log_lines()[:-1]
_RESUMED_FACTS = Invocation(capture.SESSION_ID, True, capture.RESUMED.launched_at)
_REPEATED_STARTS = (_CHILD_STARTED,) * _REPEATS
_REPEATED_CHILD = (
    _STARTED, *_REPEATED_STARTS, _CHILD_CONTEXT, _CHILD_RECORD, _CHILD_REQUEST, _CHILD_COMPLETE, _COMPLETE,
)
_INVALID_TOTAL = MappingProxyType({"total_tokens": _INVALID_STATE})
_CHILD_RUN = (
    _STARTED,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    _CHILD_RECORD,
    _CHILD_REQUEST,
    _CHILD_COMPLETE,
    _THREAD_RECORD,
    _NEXT,
    _COMPLETE,
)
# A child turn switching models between its two requests.
_SWITCHED_CHILD_MODEL = "gpt-5.5-nano"
_SWITCHED_CHILD = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, cases.MODEL: _SWITCHED_CHILD_MODEL})
_CHILD_SWITCH = codex.line(codex.TURN_CONTEXT, dict(_SWITCHED_CHILD))
_CHILD_TWICE = tuple(2 * count for count in codex.NEXT_REQUEST)
_CHILD_SECOND = codex.token_count(_CHILD_TWICE, codex.NEXT_REQUEST)
_CHILD_SWITCH_RUN = (
    _STARTED,
    _CHILD_STARTED,
    _CHILD_CONTEXT,
    _CHILD_RECORD,
    _CHILD_REQUEST,
    _CHILD_SWITCH,
    _CHILD_RECORD,
    _CHILD_SECOND,
    _CHILD_COMPLETE,
    _COMPLETE,
)
_CHILD_MODEL_CHANGE = MappingProxyType({
    _KIND: "model-change",
    _POSITION: capture.LAST.end + 5,
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
_RECORD = codex.line(_RECORD_KIND, {_USAGE: codex.counters(codex.NEXT_REQUEST)})
_MALFORMED_RECORDS = (
    ("a payload no object", codex.line(_RECORD_KIND, ["not an object"]), {coverage.MALFORMED_ENVELOPES: 1}),
    ("usage naming no counter", codex.line(_RECORD_KIND, {_USAGE: {}}), {coverage.MALFORMED_USAGE: 1}),
    (
        "a negative count",
        codex.line(_RECORD_KIND, {_USAGE: {_INPUT: -1}}),
        {coverage.INVALID_COUNTERS: 1},
    ),
    (
        "reads past the input",
        codex.line(_RECORD_KIND, {_USAGE: codex.counters(_PAST_INPUT)}),
        {_CONFLICTING: 1, coverage.UNSUPPORTED_USAGE_SOURCE: 1},
    ),
)
# A child turn writing two usage records and reporting one request, beside a thread request reported with no record:
# the child's second record has no report of its own branch, however the thread's surplus report matches in number --
# which, giving the counts that record repeats, could be its request reported once the child's turn closed, so it is no
# proven request either.
_CHILD_RECORDS = (_CHILD_STARTED, _CHILD_CONTEXT, _CHILD_RECORD, _CHILD_REQUEST, _CHILD_RECORD, _CHILD_COMPLETE, _NEXT)
_ONE_UNOBSERVED = MappingProxyType({coverage.UNSUPPORTED_USAGE_SOURCE: 1})
_CHILD_RECORDS_GAPS = MappingProxyType({**_ONE_UNOBSERVED, coverage.UNRECONCILED_USAGE: 1})
# Two child turns open at once, each on a model of its own: told apart by the record before each report, or not.
_SECOND_CHILD = "01a1d020-0000-7000-8000-000000000003"
_SECOND_MODEL = "gpt-5.5-second"
_SECOND_STARTED = codex.event(codex.TASK_STARTED, turn_id=_SECOND_CHILD, turn_attribution=dict(_PARENT))
_SECOND_TURN_CONTEXT = MappingProxyType({codex.TURN_ID: _SECOND_CHILD, cases.MODEL: _SECOND_MODEL})
_SECOND_CONTEXT = codex.line(codex.TURN_CONTEXT, dict(_SECOND_TURN_CONTEXT))
_SECOND_USAGE = MappingProxyType({codex.TURN_ID: _SECOND_CHILD, _USAGE: _NEXT_USAGE})
_SECOND_RECORD = codex.line(_RECORD_KIND, dict(_SECOND_USAGE))
_SECOND_COMPLETE = codex.event(_TASK_COMPLETE, turn_id=_SECOND_CHILD)
_OVERLAPPING = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _SECOND_STARTED, _SECOND_CONTEXT)
_CLOSING = (_SECOND_COMPLETE, _CHILD_COMPLETE, _COMPLETE)
_TOLD_APART = (*_OVERLAPPING, _CHILD_RECORD, _CHILD_REQUEST, _SECOND_RECORD, _CHILD_REQUEST, *_CLOSING)
_UNTOLD = (*_OVERLAPPING, _CHILD_REQUEST, *_CLOSING)
_UNTOLD_PARENT = (_STARTED, _CHILD_STARTED, _CHILD_CONTEXT, _CHILD_REQUEST, _CHILD_COMPLETE, _COMPLETE)
_UNTOLD_CASES = (
    ("two child turns", _UNTOLD, 1),
    ("a parent and its child", _UNTOLD_PARENT, 1),
    ("past a child turn's start cut short", (_STARTED, _CUT_CHILD_START, _NEXT, _NEXT_AGAIN, _COMPLETE), 2),
    ("past a context cut short", (_STARTED, _CUT_CONTEXT, _NEXT, _NEXT_AGAIN, _COMPLETE), 2),
    ("past a context no object", (_STARTED, _CONTEXT_NO_OBJECT, _NEXT, _NEXT_AGAIN, _COMPLETE), 2),
)
_TOLD_TURNS = (codex.CHILD_TURN, _SECOND_CHILD)
_TOLD_MODELS = (_CHILD_MODEL, _SECOND_MODEL)
# A report no branch takes, its own counts and its context window unusable: placed in neither of two overlapping child
# turns, or in a child turn naming no id, the one turn open once its parent finished.
_DETACHED_COUNTS = (-1, 500, 0, 10, 2, 1010)
_DETACHED = codex.token_count(codex.NEXT_REQUEST, _DETACHED_COUNTS, model_context_window=-1)
_DETACHED_GAPS = MappingProxyType({coverage.INVALID_COUNTERS: 1, coverage.MALFORMED_METADATA: 1})
# A fresh turn whose first report's running sum leaves the input out, and whose second's cannot hold the input both
# requests report: the second is no proven request, the first kept.
_FRESH_MODEL = MappingProxyType({codex.TURN_ID: capture.FRESH_TURN, cases.MODEL: capture.FIRST_MODEL})
_FRESH_CONTEXT = codex.line(codex.TURN_CONTEXT, dict(_FRESH_MODEL))
_SPARSE_FIRST_INFO = MappingProxyType({_TOTAL_USAGE: _OUTPUT_COUNT, _LAST_USAGE: _OUTGROWN_OWN})
_SPARSE_SUM = dict(zip(_OUTGROWN_COUNTERS, (100, 20, 120), strict=True))
_SPARSE_SECOND_INFO = MappingProxyType({_TOTAL_USAGE: _SPARSE_SUM, _LAST_USAGE: _OUTGROWN_OWN})
_SPARSE_FIRST = codex.event(codex.TOKEN_COUNT, info=dict(_SPARSE_FIRST_INFO))
_SPARSE_SECOND = codex.event(codex.TOKEN_COUNT, info=dict(_SPARSE_SECOND_INFO))
_SPARSE = (_FRESH_FIRST, _FRESH_STARTED, _FRESH_CONTEXT, _SPARSE_FIRST, _SPARSE_SECOND, _FRESH_COMPLETED)
# The same turn, its second running sum holding more input than both requests together report.
_SURPLUS_SUM = dict(zip(_OUTGROWN_COUNTERS, (250, 20, 270), strict=True))
_SURPLUS_INFO = MappingProxyType({_TOTAL_USAGE: _SURPLUS_SUM, _LAST_USAGE: _OUTGROWN_OWN})
_SURPLUS_SECOND = codex.event(codex.TOKEN_COUNT, info=dict(_SURPLUS_INFO))
_SURPLUS = (_FRESH_FIRST, _FRESH_STARTED, _FRESH_CONTEXT, _SPARSE_FIRST, _SURPLUS_SECOND, _FRESH_COMPLETED)
# The sparse turn's first report left to an earlier invocation, the second the resume's own: the earlier request still
# holds the input it reported in the running sum, so the resume's cannot fit beside it.
_RESUMED_SPARSE = (_FRESH_FIRST, _PRIOR_STARTED, _SPARSE_FIRST.replace(codex.STAMP, _PRIOR_STAMP), _PRIOR_COMPLETE)
# An earlier turn's two requests, each of half the first number past any count, its running sums counting output alone,
# then the resume's running sum holding the input of one: the input the two add up to is no count a report could give,
# but it is the floor the resume's sum is held to all the same.
_HALF_PAST_ANY = cases.PAST_ANY_COUNT // 2
_HALF_COUNTS = (_HALF_PAST_ANY, 1, _HALF_PAST_ANY + 1)
_HALF_AGAIN_COUNTS = (_HALF_PAST_ANY, 3, _HALF_PAST_ANY + 3)
_HALF_OWN = dict(zip(_OUTGROWN_COUNTERS, _HALF_COUNTS, strict=True))
_HALF_AGAIN_SUM = dict(zip(_OUTGROWN_COUNTERS, _HALF_AGAIN_COUNTS, strict=True))
_HALVES = tuple(
    codex.event(codex.TOKEN_COUNT, info={_TOTAL_USAGE: {_OUTPUT: output}, _LAST_USAGE: _HALF_OWN})
    for output in (1, 2)
)
_PRIOR_HALVES = tuple(half.replace(codex.STAMP, _PRIOR_STAMP) for half in _HALVES)
_HALVES_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, *_PRIOR_HALVES, _PRIOR_COMPLETE)
_HALF_AGAIN = codex.event(codex.TOKEN_COUNT, info={_TOTAL_USAGE: _HALF_AGAIN_SUM, _LAST_USAGE: _HALF_OWN})
# A parent turn's report keeping no running sum -- naming none, or whose `info` is no object -- before the child turn it
# started reports a request once the parent closed: the parent reported all the same, so that could be its request
# reported again, its sum beside it, and is no request of the child's -- nor after a resume, the report an earlier
# invocation's.
_FRESH_CHILD_STARTED = _PRIOR_CHILD_STARTED.replace(_PRIOR_STAMP, codex.STAMP)
_CHILD_AFTER_PARENT = (_FRESH_CHILD_STARTED, _CHILD_CONTEXT, _FRESH_COMPLETED, _REPLAYED_REPORT, _CHILD_COMPLETE)
_INFO_NO_OBJECT = codex.event(codex.TOKEN_COUNT, info=[1])
_SUMLESS_PRIOR = (_FRESH_FIRST, _PRIOR_STARTED, _SUMLESS_REPLAYED.replace(codex.STAMP, _PRIOR_STAMP), _PRIOR_COMPLETE)
_SUMLESS_PARENT_GAPS = MappingProxyType({**_LATE_IN_CHILD_GAPS, coverage.MALFORMED_USAGE: 1})
# Running sums showing none of the counters a request moves -- zeros on the others, or the earlier sum's output alone --
# which prove no repeat of nothing, nor of the sum before.
_ZEROS_ALONE = (None, 0, 0, None, 0, None)
_OUTPUT_ALONE = (None, None, None, 10, None, None)
_UNSHOWN_ZEROS = codex.token_count(_ZEROS_ALONE, (100, 0, 0, 10, 0, 110))
_UNSHOWN_AGAIN = codex.token_count(_OUTPUT_ALONE, (100, 0, 0, 0, 0, 100))
_FRESH_TURN_HEAD = (_FRESH_FIRST, _FRESH_STARTED, _FRESH_CONTEXT)
# A fresh turn's cache reads or writes, then a running sum holding fewer of them beside a request leaving them out.
_LEAVING_CACHE_OUT = (100, None, None, 10, None, 110)
_READS_FIRST = (100, 50, None, 10, None, 110)
_WRITES_FIRST = (100, None, 50, 10, None, 110)
_READS_LEFT = (200, 0, None, 20, None, 220)
_WRITES_LEFT = (200, None, 0, 20, None, 220)
_READS_SHRUNK = codex.token_count(_READS_LEFT, _LEAVING_CACHE_OUT)
_WRITES_SHRUNK = codex.token_count(_WRITES_LEFT, _LEAVING_CACHE_OUT)
_READS_REPORT = codex.token_count(_READS_FIRST, _READS_FIRST)
_WRITES_REPORT = codex.token_count(_WRITES_FIRST, _WRITES_FIRST)
_READS_TURN = (*_FRESH_TURN_HEAD, _READS_REPORT, _READS_SHRUNK, _FRESH_COMPLETED)
_WRITES_TURN = (*_FRESH_TURN_HEAD, _WRITES_REPORT, _WRITES_SHRUNK, _FRESH_COMPLETED)
_SHRUNK_GAPS = MappingProxyType({coverage.UNRECONCILED_USAGE: 1, coverage.CONFLICTING_COUNTERS: 1})
# The fresh run's log, its turn's attribution no object: whether the turn is a root or a child is unproven.
_MALFORMED_START = _FRESH_LINES[1].replace('"turn_attribution":{', '"turn_attribution":["malformed"],"unread":{', 1)
_MALFORMED_ATTRIBUTION = (_FRESH_LINES[0], _MALFORMED_START, *_FRESH_LINES[2:])
# A usage record naming its turn by an id past the metadata bound: placed in no turn, so counted on no branch.
_REFUSED_RECORD = codex.line(_RECORD_KIND, {codex.TURN_ID: _OVERSIZED_TURN, _USAGE: _NEXT_USAGE})
# Each case: the gaps it leaves, and how many samples it keeps.
_UNSAMPLED = (
    (
        "naming no running sum",
        codex.APPENDED,
        (*capture.log_lines(), _STARTED, _SUMLESS, _COMPLETE),
        ({coverage.MALFORMED_USAGE: 1, coverage.INVALID_COUNTERS: 1, coverage.CONFLICTING_COUNTERS: 1}, 0),
    ),
    (
        "counts past a running sum an earlier one left a counter out of",
        codex.APPENDED._replace(start=len(_PARTIAL_PRIOR)),
        (*_PARTIAL_PRIOR, _STARTED, _OUTGROWN, _COMPLETE),
        ({coverage.UNRECONCILED_USAGE: 1, coverage.CONFLICTING_COUNTERS: 1}, 0),
    ),
    (
        "a running sum below a request an earlier report gave, proven or not",
        codex.APPENDED._replace(start=len(_UNPROVEN_PRIOR)),
        (*_UNPROVEN_PRIOR, _STARTED, _UNDER_UNPROVEN, _COMPLETE),
        ({coverage.UNRECONCILED_USAGE: 1, coverage.CONFLICTING_COUNTERS: 1}, 0),
    ),
    (
        "an earlier report of another branch replayed in a child turn",
        _AFTER_COVERED,
        _EARLIER_REPLAYED,
        (dict(_LATE_IN_CHILD_GAPS), 1),
    ),
    (
        "an older report of a child turn replayed in its parent's",
        _AFTER_COVERED,
        _CHILD_REPLAYED_ON_THREAD,
        (dict(_ONE_UNPROVEN), 3),
    ),
    (
        "a context estimate past the running sum after a compaction",
        _AFTER_COVERED,
        _ESTIMATED_PAST,
        ({}, 1),
    ),
    (
        "a context estimate past the running sum once a child turn reported",
        _AFTER_COVERED,
        _ESTIMATED_AFTER_CHILD,
        ({}, 3),
    ),
    (
        "counts past what a sparse running sum holds beside the request before it",
        capture.FRESH,
        _SPARSE,
        ({coverage.UNRECONCILED_USAGE: 1}, 1),
    ),
    (
        "counts past what a sparse running sum holds beside an earlier invocation's request",
        codex.APPENDED._replace(start=len(_RESUMED_SPARSE)),
        (*_RESUMED_SPARSE, _STARTED, _SPARSE_SECOND, _COMPLETE),
        ({coverage.UNRECONCILED_USAGE: 1}, 0),
    ),
    (
        "a running sum below the input earlier requests add up to past any count",
        codex.APPENDED._replace(start=len(_HALVES_PRIOR)),
        (*_HALVES_PRIOR, _STARTED, _HALF_AGAIN, _COMPLETE),
        (_SHRUNK_GAPS, 0),
    ),
    (
        "a parent's report naming no running sum, then a child's after the parent closed",
        capture.FRESH,
        (*_FRESH_TURN_HEAD, _SUMLESS_REPLAYED, *_CHILD_AFTER_PARENT),
        (_SUMLESS_PARENT_GAPS, 0),
    ),
    (
        "a parent's report whose info is no object, then a child's after the parent closed",
        capture.FRESH,
        (*_FRESH_TURN_HEAD, _INFO_NO_OBJECT, *_CHILD_AFTER_PARENT),
        (_SUMLESS_PARENT_GAPS, 0),
    ),
    (
        "an earlier invocation's report naming no running sum, then a resumed child's after its parent closed",
        codex.APPENDED._replace(start=len(_SUMLESS_PRIOR)),
        (*_SUMLESS_PRIOR, *_CHILD_LATE),
        (_LATE_IN_CHILD_GAPS, 0),
    ),
    (
        "complete samples a fresh run's last running sum does not add up to",
        capture.FRESH,
        _SURPLUS,
        ({coverage.UNRECONCILED_USAGE: 1}, 2),
    ),
    (
        "a turn whose attribution is no object",
        capture.FRESH,
        _MALFORMED_ATTRIBUTION,
        ({coverage.MALFORMED_METADATA: 1, coverage.CONVERSATION_AMBIGUOUS: 4}, 0),
    ),
    (
        "a running sum of zeros showing none of the counters the request moves",
        capture.FRESH,
        (*_FRESH_TURN_HEAD, _UNSHOWN_ZEROS, _FRESH_COMPLETED),
        ({coverage.UNRECONCILED_USAGE: 1}, 0),
    ),
    (
        "a running sum repeated showing none of the counters the request moves",
        capture.FRESH,
        (*_FRESH_TURN_HEAD, _SPARSE_FIRST, _UNSHOWN_AGAIN, _FRESH_COMPLETED),
        ({coverage.UNRECONCILED_USAGE: 1}, 1),
    ),
    (
        "a running sum's cache reads shrinking, the request leaving them out",
        capture.FRESH,
        _READS_TURN,
        (_SHRUNK_GAPS, 1),
    ),
    (
        "a running sum's cache writes shrinking, the request leaving them out",
        capture.FRESH,
        _WRITES_TURN,
        (_SHRUNK_GAPS, 1),
    ),
    (
        "counts past a running sum of nothing",
        capture.FRESH,
        (_FRESH_FIRST, _FRESH_STARTED, _PAST_NOTHING, _FRESH_COMPLETED),
        ({coverage.CONFLICTING_COUNTERS: 1}, 0),
    ),
    (
        "placed in neither of two overlapping turns",
        codex.APPENDED,
        (*capture.log_lines(), *_OVERLAPPING, _DETACHED, *_CLOSING),
        ({**_DETACHED_GAPS, coverage.CONVERSATION_AMBIGUOUS: 1, coverage.SUBAGENT_USAGE_UNAVAILABLE: 2}, 0),
    ),
    (
        "after a record naming its turn by a refused id",
        codex.APPENDED,
        (*capture.log_lines(), _STARTED, _REFUSED_RECORD, _NEXT, _COMPLETE),
        ({coverage.OVERSIZE_METADATA: 1, coverage.CONVERSATION_AMBIGUOUS: 1}, 0),
    ),
    (
        "in a child turn naming no id, its parent finished",
        codex.APPENDED,
        (*capture.log_lines(), _STARTED, _UNNAMED_CHILD, _COMPLETE, _DETACHED),
        ({**_DETACHED_GAPS, coverage.SUBAGENT_UNIDENTIFIED: 1, coverage.NO_TERMINAL_RESULT: 1}, 0),
    ),
)
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

    def test_unproven_logs_attribute_nothing(self) -> None:
        # The scope's refusal is the whole collection: no request the fold read off the log is kept, and the lines the
        # scan read before the collection knew are still counted.
        for name, invocation, lines, reason in _REFUSED:
            with self.subTest(name):
                collection = codex.collected(invocation, lines)
                self.assertEqual(collection.reasons, {reason: 1})
                self.assertEqual((collection.status, collection.coverage[_SCOPE]), _UNAVAILABLE_SCOPE)
                self.assertFalse(any(map(collection.coverage.get, _OBSERVED)))
                self.assertEqual(collection.coverage["scanned_lines"], len(lines))

    def test_an_invocation_that_wrote_nothing(self) -> None:
        # A resume that wrote no line, and whose stdout started no turn, made no request: complete with nothing, and
        # with no boundary crossed, no baseline either.
        collection = codex.appended(stdout="")
        self.assertEqual(collection.status, coverage.COMPLETE_EMPTY)
        self.assertEqual(collection.checkpoints, [])

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


class RequestIdentityTest(unittest.TestCase):
    """A repeated report is one request, and a report not proven new is none, so nothing is copied or doubled."""

    def test_repeated_notifications_are_one_request(self) -> None:
        # The turn opening with the last running sum, the request's report printed twice, the context estimate after a
        # compaction, whose running sum does not move, and a notification with no usage: one request. A repeat giving
        # other request usage than the report it repeats contradicts it, unless a reset came between.
        for name, lines, gaps in _REPEATS_OF_ONE:
            with self.subTest(name):
                collection = _appended_with(*lines)
                self.assertEqual(len(collection.samples), 1)
                self.assertEqual(collection.reasons, gaps)

    def test_unchanged_zeros_prove_no_request(self) -> None:
        # After an earlier running sum leaves the counters a request moves unusable, a report its sum's zeros alone
        # agree with is no proven request: it could be the earlier request reported again.
        collection = codex.collected(_AFTER_REPLAYED, _REPLAY_LOG)
        self.assertEqual(collection.samples, [])
        self.assertEqual(collection.reasons.get(coverage.UNRECONCILED_USAGE), 1)

    def test_a_running_sum_behind_a_settled_request(self) -> None:
        # A request the earlier lines settled with no `token_count` reporting it leaves the thread's running sum behind
        # it -- nothing at all, or the last sum reported, which answers one record however many came before it -- so no
        # baseline is kept, and the invocation's report of that request again is not proven new, nor is any report of
        # the invocation's answering a record the earlier lines left; and a running sum shrinking below an earlier one
        # contradicts it, so it is no baseline either. A turn opening with a repeat of that sum answers none of those
        # records, so the report after it of the request one of them settled is still that request reported late. Only a
        # report of a record's own branch answers it -- the invocation's own record first, else the earliest earlier one
        # whose counters it gives, since a record repeats its request's -- a record no branch is placed for none, and
        # while one is left no report of the invocation's on any branch giving counters it could repeat, a child turn's
        # it opens included, is proven new. After no usage at all, nothing lags, and the first report is a request.
        for name, start, lines, expected in _BEHIND:
            with self.subTest(name):
                collection = codex.collected(
                    codex.APPENDED._replace(start=start), lines, fallback_model=capture.FIRST_MODEL,
                )
                self.assertEqual((cases.column(collection.samples, _POSITION), collection.reasons), expected)
                self.assertNotIn("invocation-baseline", cases.column(collection.checkpoints, _KIND))

    def test_reports_keep_their_evidence(self) -> None:
        # A report no sample is made of -- none proven, or none a branch takes, a turn whose parentage is unproven
        # included -- still has its request usage judged: against its own parts, and against the running sum beside
        # it, which every request it sums adds to, nothing at all included, nor less than what earlier reports
        # establish where it leaves a counter out; and its metadata beside it. A running sum showing none of the
        # counters its request moves proves no repeat, and one holding less of a counter than earlier reports establish
        # contradicts them, whatever the request leaves out. The samples kept add up to what the last running sum
        # advanced, where nothing else is missing.
        for name, invocation, lines, expected in _UNSAMPLED:
            with self.subTest(name):
                collection = codex.collected(invocation, lines)
                self.assertEqual((collection.reasons, len(collection.samples)), expected)

    def test_records_keep_their_shape_as_evidence(self) -> None:
        # No request is read off a usage record, but one that is no object, whose usage names no counter, or whose
        # counters are no whole count or contradict its own parts is malformed, invalid, or conflicting evidence beside
        # the request its `token_count` reports, which is kept as a sample all the same -- and one whose counters the
        # report cannot repeat still awaits a report of its own.
        for name, record, gaps in _MALFORMED_RECORDS:
            with self.subTest(name):
                collection = _appended_with(record, _NEXT)
                self.assertEqual(len(collection.samples), 1)
                self.assertEqual(collection.reasons, gaps)

    def test_overlapping_turns_told_apart_by_records(self) -> None:
        # With several turns open at once -- two child turns, or a parent and its child -- the record before a report
        # names the turn it settles in; with none, nothing tells them apart, so the report is placed in none, and no
        # branch is proven past it, nor its running sum kept as a checkpoint. So is every report past a line no reading
        # could place, which could have opened such a turn, until a root turn opens.
        told = codex.appended(*_TOLD_APART)
        self.assertEqual(cases.column(told.samples, codex.TURN_ID), list(_TOLD_TURNS))
        self.assertEqual(cases.column(told.samples, cases.MODEL), list(_TOLD_MODELS))
        self.assertEqual(told.reasons, {})
        for name, lines, unplaced in _UNTOLD_CASES:
            with self.subTest(name):
                untold = codex.appended(*lines)
                self.assertEqual(untold.samples, [])
                self.assertEqual(untold.reasons.get(coverage.CONVERSATION_AMBIGUOUS), unplaced)
                self.assertEqual(cases.column(untold.checkpoints, _KIND), ["invocation-baseline"])

    def test_unproven_reports_are_no_requests(self) -> None:
        for name, lines, others in _UNPROVEN_REPORTS:
            with self.subTest(name):
                collection = codex.appended(*lines)
                reasons = collection.reasons
                self.assertEqual(collection.samples, [])
                self.assertEqual(reasons.pop(coverage.UNRECONCILED_USAGE), 1)
                self.assertEqual(set(reasons), others)
        for name, lines in _REPEATS_IN_CHILD:
            with self.subTest(name):
                collection = codex.collected(_AFTER_COVERED, lines)
                self.assertEqual((collection.samples, collection.reasons), ([], _LATE_IN_CHILD_GAPS))
                self.assertEqual(cases.column(collection.checkpoints, _KIND), ["invocation-baseline"])


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
        # A child turn's running sum is no checkpoint, but is held to the same arithmetic.
        child = _appended_with(*_INVALID_CHILD_RUN)
        self.assertEqual(len(child.samples), 1)
        self.assertEqual(child.reasons, {_INVALID: 1})

    def test_a_line_holding_no_object(self) -> None:
        # A native log holds JSON objects alone, so any other line -- a value that is no object, plain text, or nothing
        # but whitespace -- is scanned and malformed where it stands, while the request beside it is kept.
        lines = (*capture.log_lines(), _STARTED, _NEXT, *_NO_OBJECTS, _COMPLETE)
        collection = codex.collected(codex.APPENDED, lines)
        self.assertEqual(len(collection.samples), 1)
        self.assertEqual(collection.reasons, {coverage.MALFORMED_LINES: len(_NO_OBJECTS)})
        self.assertEqual(collection.coverage["scanned_lines"], len(lines))

    def test_usage_no_report_carries_is_a_gap(self) -> None:
        # A request is read off its `token_count` alone, so a usage record no later report of its branch answers --
        # every record, where its reports are missing, and one after the report it could have been mistaken for -- is
        # usage it could not observe, never no request.
        cases_by_name = {
            "every report missing": (codex.collected(lines=_REPORTLESS_FRESH), {coverage.UNSUPPORTED_USAGE_SOURCE: 3}),
            "one record beyond its report": (_appended_with(_RECORD, _OPENING, _NEXT, _NEXT, _RECORD), _ONE_UNOBSERVED),
            "a child's record another branch's report matches in number": (
                _appended_with(*_CHILD_RECORDS),
                _CHILD_RECORDS_GAPS,
            ),
            "a record after its turn's only report": (_appended_with(_NEXT, _RECORD), _ONE_UNOBSERVED),
            "a record of other counts than its report's": (_appended_with(_OWN_RECORD, _NEXT), _ONE_UNOBSERVED),
        }
        for name, (collection, unobserved) in cases_by_name.items():
            with self.subTest(name):
                self.assertEqual(collection.reasons, unobserved)
                self.assertEqual(collection.status, coverage.INCOMPLETE)
        self.assertEqual(_appended_with(_RECORD, _OPENING, _NEXT, _NEXT).reasons, {})

    def test_unreported_values_stay_unknown(self) -> None:
        # Reasoning a block leaves out is unknown, never zero; a flag or a context window reported as no usable value
        # is malformed metadata, while one left out is a limitation of the source alone.
        for reported, malformed in _METADATA_SHAPES:
            with self.subTest(reported=reported):
                usage = {**_THREAD_ONLY, _LAST_USAGE: dict(_NO_REASONING), **reported}
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

    def test_contexts_that_establish_no_model(self) -> None:
        # A context naming a model this collection refused leaves its turn's model unestablished, never the fallback;
        # one naming a turn neither the thread's open one nor a child the log named sets no model at all, so the
        # thread's request keeps the model the thread last ran on. A line no reading could place could have been a
        # context, so past it the thread's model is unestablished -- neither the one it last ran on nor the fallback --
        # and the first report of the turn after it, which could repeat the one that line held, is no proven request.
        for name, lines, attributed, gaps in _UNSET_MODELS:
            with self.subTest(name):
                collection = codex.appended(*lines, fallback_model=capture.FIRST_MODEL)
                self.assertEqual(cases.picked(collection.samples[0], *_ATTRIBUTED), attributed)
                self.assertEqual(collection.reasons, dict(gaps))

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
        for name, lines, gaps, kept in _UNEXPOSED:
            with self.subTest(name):
                collection = _appended_with(*lines)
                self.assertEqual(collection.reasons, dict(gaps))
                self.assertEqual(len(collection.samples), kept)

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

    def test_earlier_records_held_to_branch_bound(self) -> None:
        # A child turn's request giving other counts than every earlier record left awaiting a report is its own; past
        # the branch bound those records are no longer told apart, and the one standing for the rest rules nothing out.
        invocation = codex.APPENDED._replace(start=len(_TWO_AWAITED))
        told = codex.collected(invocation, _AWAITED_THEN_CHILD)
        self.assertEqual(cases.column(told.samples, codex.TURN_ID), [codex.CHILD_TURN])
        with patch.object(request_scan, _BRANCHES, 1):
            untold = codex.collected(invocation, _AWAITED_THEN_CHILD)
        self.assertEqual((untold.samples, untold.reasons), ([], _LATE_IN_CHILD_GAPS))

    def test_records_past_the_request_bound(self) -> None:
        # The invocation's records past the request bound are kept without their counters, each a `correlation-limit`
        # gap, and every one still awaits a report, so the collection still says it missed all three.
        with patch.object(request_scan, "MAX_TRACKED_STEPS", 1):
            collection = codex.appended(*_RECORDED_THRICE)
        self.assertEqual(collection.reasons, _PAST_REQUEST_BOUND)
        self.assertEqual(collection.status, coverage.SOURCE_LIMIT_TRUNCATED)

    def test_a_repeated_child_start_keeps_one_branch(self) -> None:
        # A child turn's start repeated opens it once, so its request is kept on its one branch, and nothing is a gap.
        collection = codex.appended(*_REPEATED_CHILD)
        self.assertEqual(cases.column(collection.samples, "turn_id"), [codex.CHILD_TURN])
        self.assertEqual(collection.reasons, {})

    def test_an_oversize_line_is_skipped(self) -> None:
        # A line past the line bound is counted and skipped however it was handed over, cutting the collection short
        # of the whole log: here it stands inside the invocation's turn, before its request, so it could have opened
        # another turn or held the report the one after it repeats, and that report is placed in no turn. The bound
        # holds the line as handed over, so padding a short one past it is as long as any.
        for oversize in (_OVERSIZE_LINE, _PADDED_LINE):
            bound = patch.object(request_scan, "MAX_LINE_CHARS", _LONGEST)
            with self.subTest(padded=oversize.startswith(" ")), bound:
                collection = codex.appended(_STARTED, oversize, _NEXT, _COMPLETE)
                self.assertEqual(len(oversize), _LONGEST + 1)
                self.assertEqual(collection.reasons, {coverage.OVERSIZE_LINES: 1, coverage.CONVERSATION_AMBIGUOUS: 1})
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
        # The bound holds the baseline and the last running sums together, none at all where it is zero.
        for bound, positions in ((2, [32, 52]), (0, [])):
            with self.subTest(bound=bound), patch.object(request_scan, "MAX_CHECKPOINTS", bound):
                collection = codex.collected(capture.SWITCHED)
                self.assertEqual(cases.column(collection.checkpoints, _POSITION), positions)
                self.assertEqual(collection.coverage["observed_checkpoints"], 3)
                self.assertEqual(collection.status, coverage.COMPLETE)


if __name__ == "__main__":
    unittest.main()
