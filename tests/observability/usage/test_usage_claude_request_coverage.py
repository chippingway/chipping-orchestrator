# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude request coverage: what a stream left out is a limitation or a gap, never a borrowed or invented value."""

import json
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import (
    protocol,
    request_claude_stream,
    request_coverage as coverage,
    request_models as models,
    request_scan,
    trajectory,
)
from orchestrator.observability.usage.request_claude_messages import RequestFold
from tests.observability.usage import (
    usage_claude_request_branches as branches,
    usage_claude_request_streams as stream,
    usage_request_cases as cases,
)

_ID = "id"
_KIND = "id_kind"
_TURN = "trajectory_turn"
_LIMITATIONS = "limitations"
_CONFLICTING = "conflicting"
_MESSAGE = "msg_a"
_REQUEST_ID = "req_a"
_OUTPUT = 40
_INIT = stream.init()
_TERMINAL = branches.terminal()
_TIMESTAMP = "2026-11-12T08:00:00Z"
_FALLBACK = "claude-configured-model"
_SAMPLE_LIMIT = 2
_MARKER_LIMIT = 1
_PADDING = 1024
_COMPACTION = stream.line({stream.TYPE: "system", "subtype": "compact_boundary", "compact_metadata": {}})
# The block every message below starts with.
_BLOCK = stream.usage()
_BY_MESSAGE = ("api-message", _MESSAGE)
# Messages whose frames name less of who they are, a closing report printed alone among them -- it names its message
# on its wrapper -- each with the identity kind it is then known by, and its key.
_IDENTITY_CASES = (
    ("a message id", stream.assistant(_MESSAGE, _BLOCK, request_id=_REQUEST_ID), _BY_MESSAGE),
    ("a closing report alone", stream.delta(_MESSAGE, _OUTPUT), _BY_MESSAGE),
    ("a request id alone", stream.assistant(None, _BLOCK, request_id=_REQUEST_ID), ("api-request", _REQUEST_ID)),
    ("no id at all", stream.assistant(None, _BLOCK), ("source-position", "position:0")),
)
_BOUNDED = 1
_TRACKED_STEPS = "MAX_TRACKED_STEPS"
_OUTPUT_TOKENS = "output_tokens"
_STREAM_EVENT = "stream_event"
_EVENT = "event"
_SESSION_ID = "session_id"
# A block naming its model on the frame rather than its message, beside an `init` naming another.
_FRAME_MODEL = stream.line({
    stream.TYPE: "assistant",
    stream.MODEL_KEY: stream.OTHER_MODEL,
    stream.MESSAGE: {"id": _MESSAGE, stream.USAGE: dict(_BLOCK)},
})
_FRAME_NAMED = (stream.OTHER_MODEL, models.STREAM_MODEL)
# A content event naming its message's session and timestamp, in a stream nothing else names them in.
_CONTENT_SESSION = "session-from-content"
_NAMED_CONTENT = stream.line({
    stream.TYPE: _STREAM_EVENT,
    "api_message_id": _MESSAGE,
    _SESSION_ID: _CONTENT_SESSION,
    "timestamp": _TIMESTAMP,
    _EVENT: {stream.TYPE: "content_block_delta", "index": 0, "delta": {stream.TYPE: "text_delta", "text": "a"}},
})
_UNNAMED_TERMINAL = stream.line({stream.TYPE: "result", "subtype": "success"})
_CONTENT_FIELDS = (_SESSION_ID, "source_timestamp")
_CONTENT_NAMES = (_CONTENT_SESSION, _TIMESTAMP)
# A message whose start and block name the API request alone, no message id.
_UNNAMED_MESSAGE = MappingProxyType({stream.MODEL_KEY: stream.MODEL, stream.USAGE: _BLOCK})
_REQUEST_START = stream.line({
    stream.TYPE: _STREAM_EVENT,
    "request_id": _REQUEST_ID,
    _EVENT: {stream.TYPE: "message_start", stream.MESSAGE: dict(_UNNAMED_MESSAGE)},
})
_REQUEST_BLOCK = stream.assistant(None, _BLOCK, request_id=_REQUEST_ID)
_KEYED_TURN = (_KIND, _ID, "request_id", "position", cases.STATUS, _TURN)
# A start naming the API request alone, then a block naming its message too and a close naming the message: whichever
# key a frame names it by, the frames are one request, at the line first printing it.
_JOINED = (
    _REQUEST_START,
    stream.assistant(_MESSAGE, _BLOCK, request_id=_REQUEST_ID),
    stream.delta(_MESSAGE, _OUTPUT),
)
_BY_REQUEST_ALONE = ("api-request", _REQUEST_ID, _REQUEST_ID, 0, models.PROVISIONAL, 0)
_BY_BOTH = ("api-message", _MESSAGE, _REQUEST_ID, 0, models.FINAL, 0)
# The same, with a content event naming the message held apart from the start before a block bridges the two.
_BRIDGED = (_REQUEST_START, _NAMED_CONTENT, *_JOINED[1:])
# A block naming the request alone, then one naming the message too: the trajectory numbers a turn under each key, and
# the request links the one numbered under its message id, which holds its settled output.
_RENAMED = (_REQUEST_BLOCK, *_JOINED[1:])
_BY_BOTH_RENAMED = (*_BY_BOTH[:-1], 1)
# Two messages naming one API request: a contradiction no frame resolves.
_OTHER_MESSAGE = "msg_b"
_SHARED_REQUEST = (
    stream.assistant(_MESSAGE, _BLOCK, request_id=_REQUEST_ID),
    stream.delta(_MESSAGE, _OUTPUT),
    stream.assistant(_OTHER_MESSAGE, _BLOCK, request_id=_REQUEST_ID),
    stream.delta(_OTHER_MESSAGE, _OUTPUT),
)
# The same two messages, closed by one report naming the shared request alone: it names neither of them.
_REQUEST_ONLY_CLOSE = stream.line({
    stream.TYPE: _STREAM_EVENT,
    "request_id": _REQUEST_ID,
    _EVENT: {stream.TYPE: "message_delta", stream.USAGE: {stream.OUTPUT: _OUTPUT}},
})
_UNSETTLED_SHARED = (_SHARED_REQUEST[0], _SHARED_REQUEST[2], _REQUEST_ONLY_CLOSE)
# A block naming the request alone, then a close naming the message too: the close joins the two keys, but the one turn
# the trajectory numbered is under the request id, and holds the count the message started with rather than its output.
_CLOSED_BY_BOTH = stream.line({**json.loads(_REQUEST_ONLY_CLOSE), "api_message_id": _MESSAGE})
_UNLINKED = (*_BY_BOTH[:-1], None)
# A block naming the request alone, then one naming the message alone, each numbered a turn of its own, then a close
# naming both: the close folds the second request into the first, which links the turn numbered under its message id.
_FOLDED_BY_CLOSE = (_REQUEST_BLOCK, stream.assistant(_MESSAGE, _BLOCK), _CLOSED_BY_BOTH)
_JOINED_CASES = (
    ("by the request alone", (_REQUEST_START, _REQUEST_BLOCK), _BY_REQUEST_ALONE),
    ("by the request, then the message", _JOINED, _BY_BOTH),
    ("held apart, then bridged", _BRIDGED, _BY_BOTH),
    ("a block by the request, then by the message", _RENAMED, _BY_BOTH_RENAMED),
    ("a block by each id, then folded by a close naming both", _FOLDED_BY_CLOSE, _BY_BOTH_RENAMED),
)
# Blocks naming their message on the wrapper alone, then its close: one request, under the message they name, while the
# trajectory numbers each block by its line, a key the request is not settled under.
_WRAPPED_BLOCK = stream.assistant(None, _BLOCK, api_message_id=_MESSAGE)
_WRAPPED = (_WRAPPED_BLOCK, _WRAPPED_BLOCK, stream.delta(_MESSAGE, _OUTPUT))
_BY_WRAPPER = ("api-message", _MESSAGE, None, 0, models.FINAL, None)
# Messages whose only turns are numbered under another key than the one they settle under, each with how it is keyed.
_UNLINKED_CASES = (
    ("a block by the request, closed by both", (_REQUEST_BLOCK, _CLOSED_BY_BOTH), _UNLINKED),
    ("blocks by the wrapper alone", _WRAPPED, _BY_WRAPPER),
)
_PROMPT_AND_OUTPUT = ("context_input_tokens", _OUTPUT_TOKENS)
_SETTLED_PROMPT = (sum(stream.START_COUNTS[:-1]), _OUTPUT)
# Frames naming another message on the message itself than on the wrapper's `api_message_id`, each before a close
# naming the wrapper's: neither message is credited with what they report.
_OTHER_START = json.loads(stream.start(_OTHER_MESSAGE, _BLOCK))
_TWO_MESSAGE_FRAMES = (
    ("a start", stream.line(dict(_OTHER_START, api_message_id=_MESSAGE))),
    ("an assistant block", stream.assistant(_OTHER_MESSAGE, _BLOCK, api_message_id=_MESSAGE)),
)
_SHARED_UNSETTLED_GAPS = MappingProxyType({
    coverage.IDENTITY_CONFLICTING: 1,
    coverage.UNINDEXED_FRAMES: 1,
    coverage.PROVISIONAL_USAGE: 2,
})
# Subagent calls, each printing one message under its own id, two more than the bound holds.
_PAST_THE_BOUND = tuple(f"toolu_{index}" for index in range(_BOUNDED + 2))
# One message whose blocks each name another API request id, every one past the metadata bound.
_LONG_REQUEST = "r" * (request_scan.MAX_METADATA_CHARS + 1)
_OVERSIZE_REQUESTED = tuple(
    stream.assistant(_MESSAGE, _BLOCK, request_id=f"{_LONG_REQUEST}{index}") for index in range(_BOUNDED + 4)
)
# Messages each naming the API request that produced it, two more than the bound holds.
_REQUESTED_PAST_THE_BOUND = tuple(
    stream.assistant(call, _BLOCK, request_id=f"req_{call}") for call in _PAST_THE_BOUND
)
# Messages each naming one API request, more than the bound holds, each opened by a start naming it on the wrapper and
# by an id past the metadata bound on itself, so no frame keeps a message id.
_SHARING_ONE_REQUEST = tuple(f"msg_{index}" for index in range(_BOUNDED + 4))
_LONG_MESSAGE = "x" * (request_scan.MAX_METADATA_CHARS + 1)
_LONG_MESSAGE_START = json.loads(stream.start(_LONG_MESSAGE, _BLOCK))
_SHARED_LONG_STARTS = tuple(
    stream.line(dict(_LONG_MESSAGE_START, api_message_id=message_id, request_id=_REQUEST_ID))
    for message_id in _SHARING_ONE_REQUEST
)
_EVERY_LIMITATION = (
    "no-reset-markers",
    "no-session-id",
    "no-message-id",
    "no-source-version",
    "no-source-timestamps",
    "no-context-capacity",
)
_ATTRIBUTION = (cases.MODEL, cases.MODEL_SOURCE)
_PROCESS_FIELDS = (_SESSION_ID, *_ATTRIBUTION, "source_version")
_PROCESS_NAMES = (stream.SESSION, stream.MODEL, models.STREAM_MODEL, stream.VERSION)
_CONFIGURED = (_FALLBACK, models.CONFIGURED_FALLBACK)
_UNAVAILABLE = (None, models.UNAVAILABLE)
_STREAM_NAMED = (stream.MODEL, models.STREAM_MODEL)
_ID_LESS_GAPS = MappingProxyType({coverage.NO_TERMINAL_RESULT: 1, coverage.PROVISIONAL_USAGE: 1})
_SUPPLIED_USAGE = branches.model_usage((*stream.START_COUNTS[:-1], 40))
_SUPPLIED_FIELDS = ("source_timestamp", "context_capacity")
_PROVISIONAL_START = (models.PROVISIONAL, 0)
_BY_REQUEST = ("api-request", _REQUEST_ID)
_SUPPLIED = (_TIMESTAMP, branches.CONTEXT_WINDOW)
_COMPACTION_MARKER = MappingProxyType({"kind": "compaction", "position": 5})
# Models a frame named that this collection refused -- no string, or too long to keep -- each with the model its request
# is then attributed and the gap it leaves: unknown rather than the process's, unless the run parsers read a kept one
# beside it or a later frame of the request names one.
_SHAPELESS = MappingProxyType({"unexpected": "shape"})
_MALFORMED = coverage.MALFORMED_METADATA
_OVERSIZE = coverage.OVERSIZE_METADATA
_UNESTABLISHED = (None, models.UNESTABLISHED)
# A block naming a refused model on its message beside a kept one on the frame: the run parsers pass over one that is
# no string for the frame's, but read one too long to keep.
_SHAPELESS_BESIDE_FRAME, _LONG_BESIDE_FRAME = (
    stream.line({
        **json.loads(_FRAME_MODEL),
        stream.MESSAGE: {"id": _MESSAGE, stream.MODEL_KEY: refused, stream.USAGE: dict(_BLOCK)},
    })
    for refused in (dict(_SHAPELESS), _LONG_MESSAGE)
)
_SHAPELESS_START = stream.start(_MESSAGE, _BLOCK, model=dict(_SHAPELESS))
_REFUSED_MODELS = (
    ("no string", (stream.assistant(_MESSAGE, _BLOCK, model=dict(_SHAPELESS)),), _UNESTABLISHED, _MALFORMED),
    ("too long", (stream.assistant(_MESSAGE, _BLOCK, model=_LONG_MESSAGE),), _UNESTABLISHED, _OVERSIZE),
    ("no string beside a kept frame model", (_SHAPELESS_BESIDE_FRAME,), _FRAME_NAMED, _MALFORMED),
    ("too long beside a kept frame model", (_LONG_BESIDE_FRAME,), _UNESTABLISHED, _OVERSIZE),
    ("before a kept one", (_SHAPELESS_START, stream.assistant(_MESSAGE, _BLOCK)), _STREAM_NAMED, _MALFORMED),
)
_UNREADABLE_HANDBACK = MappingProxyType({"agentId": branches.AGENT, stream.USAGE: (1,)})
# Unreadable frames: a discriminator that is no string, a message that is no object, a message with no usage, a
# usage block naming no counter this collection reads, and a hand-back whose usage is no object.
_UNREADABLE = (
    stream.line({stream.TYPE: ["assistant"]}),
    stream.line({stream.TYPE: "assistant", stream.MESSAGE: "text"}),
    stream.assistant(_MESSAGE, None),
    stream.assistant("msg_b", {"prompt_tokens": 3}),
    stream.line({stream.TYPE: "user", "tool_use_result": dict(_UNREADABLE_HANDBACK)}),
)
_UNREADABLE_GAPS = MappingProxyType({
    coverage.MALFORMED_ENVELOPES: 2,
    coverage.MALFORMED_USAGE: 2,
    coverage.UNREPORTED_USAGE: 2,
})
_TOTAL_OUTPUT = 5
_CONTRADICTED_TOTAL = stream.usage((*stream.START_COUNTS[:-1], _TOTAL_OUTPUT))
_CONTRADICTED_TOTAL[stream.DETAILS] = {stream.THINKING: _TOTAL_OUTPUT + 1}
_CONTRADICTED_TOTAL[stream.SPLIT] = {stream.FIVE_MINUTE: 9, stream.ONE_HOUR: 9}
_TOTAL_EVIDENCE = MappingProxyType({stream.CACHE_WRITE: _CONFLICTING, stream.THINKING: _CONFLICTING})
_TOTAL_GAPS = MappingProxyType({
    coverage.CONFLICTING_COUNTERS: 1,
    coverage.MALFORMED_USAGE: 1,
    coverage.AGGREGATE_ONLY_USAGE: 1,
})
# A message the stream printed only the content of: its usage was never reported.
_CONTENT_ONLY = stream.line({
    stream.TYPE: _STREAM_EVENT,
    "api_message_id": _MESSAGE,
    _EVENT: {stream.TYPE: "content_block_delta", "index": 0, "delta": {stream.TYPE: "text_delta", "text": "a"}},
})
_INTERRUPTED_GAPS = MappingProxyType({
    coverage.MALFORMED_LINES: 1,
    coverage.NO_TERMINAL_RESULT: 1,
    coverage.PROVISIONAL_USAGE: 1,
})
_MODELS = ("m1", "m2", "m3")


def _collected(*lines: str, fallback_model: str | None = None) -> cases.Collected:
    return cases.collected(*lines, fallback_model=fallback_model, backend=protocol.CLAUDE)


def _bare(message_id: str | None, **wrapper: object) -> str:
    """A lone `assistant` frame naming nothing about its process."""
    return stream.assistant(message_id, _BLOCK, **wrapper)


def _model_changes() -> tuple[str, ...]:
    """Three lead-thread messages, each on another model than the one before."""
    messages = (stream.message(f"msg_{model}", _OUTPUT, model=model) for model in _MODELS)
    return tuple(frame for message in messages for frame in message)


class IdentityTest(unittest.TestCase):
    """An ID-less run's requests are still the process's own, each labelled by what identifies it."""

    def test_requests_are_known_by_what_names_them(self) -> None:
        for name, frame, identified in _IDENTITY_CASES:
            with self.subTest(name):
                sample = _collected(frame).samples[0]
                self.assertEqual(cases.picked(sample, _KIND, _ID), identified)

    def test_request_id_joins_start_and_blocks(self) -> None:
        # Frames naming no message are keyed by the API request, so its start and its blocks are one request, and a
        # frame naming both the request and the message joins the two keys.
        for name, frames, keyed in _JOINED_CASES:
            with self.subTest(name):
                samples = _collected(*frames).samples
                self.assertEqual(len(samples), 1)
                self.assertEqual(cases.picked(samples[0], *_KEYED_TURN), keyed)
                # The turn the request links holds its own output, settled or not.
                turns = trajectory.parse_claude_trajectory("\n".join(frames)).turns
                self.assertEqual(
                    turns[keyed[-1]].output_tokens,
                    samples[0][_OUTPUT_TOKENS],
                )

    def test_a_turn_under_another_key_is_not_linked(self) -> None:
        # The frames are still one request, its prompt from the blocks and its output from the close.
        for name, frames, keyed in _UNLINKED_CASES:
            with self.subTest(name):
                samples = _collected(*frames).samples
                self.assertEqual(len(samples), 1)
                self.assertEqual(cases.picked(samples[0], *_KEYED_TURN), keyed)
                self.assertEqual(cases.picked(samples[0], *_PROMPT_AND_OUTPUT), _SETTLED_PROMPT)

    def test_two_message_ids_fold_into_neither(self) -> None:
        # A frame naming one message on itself and another on its wrapper credits neither with what it reports, and
        # the contradiction is a gap.
        for name, frame in _TWO_MESSAGE_FRAMES:
            with self.subTest(name):
                collection = _collected(frame, stream.delta(_MESSAGE, _OUTPUT))
                self.assertEqual(cases.column(collection.samples, _ID), [_MESSAGE])
                self.assertEqual(cases.column(collection.samples, _OUTPUT_TOKENS), [_OUTPUT])
                self.assertEqual(collection.reasons.get(coverage.IDENTITY_CONFLICTING), 1)

    def test_messages_sharing_a_request_stay_apart(self) -> None:
        # Each message keeps its own sample, and the identity evidence contradicting itself is a gap.
        collection = _collected(_INIT, *_SHARED_REQUEST, _TERMINAL)
        self.assertEqual(cases.column(collection.samples, _ID), [_MESSAGE, _OTHER_MESSAGE])
        self.assertEqual(collection.reasons, {coverage.IDENTITY_CONFLICTING: 1})
        # From then on the shared request id names neither message, so a report naming it alone settles nothing.
        unsettled = _collected(_INIT, *_UNSETTLED_SHARED, _TERMINAL)
        statuses = set(cases.column(unsettled.samples, cases.STATUS))
        self.assertEqual(statuses, {models.PROVISIONAL})
        self.assertEqual(unsettled.reasons, _SHARED_UNSETTLED_GAPS)

    def test_an_id_less_run_lists_what_it_left_out(self) -> None:
        # No `init`, no session, no version, no total: the request is still collected, and every identity and
        # metadata the stream left out is a limitation, never a guess.
        collection = _collected(_bare(None), fallback_model=_FALLBACK)
        sample = collection.samples[0]
        self.assertNotIn(_SESSION_ID, sample)
        self.assertEqual(cases.picked(sample, *_ATTRIBUTION), _STREAM_NAMED)
        self.assertEqual(tuple(collection.coverage[_LIMITATIONS]), _EVERY_LIMITATION)
        self.assertEqual(collection.reasons, _ID_LESS_GAPS)

    def test_lead_models_fall_back_in_order(self) -> None:
        # A lead message runs on the model its own frame names wherever the run parsers read it, and naming none, on
        # the process's `init` model, then the configured one, then none.
        framed = _collected(_INIT, _FRAME_MODEL, _TERMINAL).samples[0]
        self.assertEqual(cases.picked(framed, *_ATTRIBUTION), _FRAME_NAMED)
        unnamed = _bare(_MESSAGE, model=None)
        from_init = _collected(_INIT, unnamed, _TERMINAL).samples[0]
        self.assertEqual(cases.picked(from_init, *_PROCESS_FIELDS), _PROCESS_NAMES)
        configured = _collected(unnamed, fallback_model=_FALLBACK).samples[0]
        self.assertEqual(cases.picked(configured, *_ATTRIBUTION), _CONFIGURED)
        unattributed = _collected(unnamed, _TERMINAL)
        self.assertEqual(cases.picked(unattributed.samples[0], *_ATTRIBUTION), _UNAVAILABLE)
        self.assertIn(coverage.MODEL_UNATTRIBUTED, unattributed.reasons)


class MetadataTest(unittest.TestCase):
    """Source timestamps, version, and context capacity are recorded only where the stream supplied them."""

    def test_content_events_supply_metadata(self) -> None:
        # A content event names its message's session and timestamp like any frame of it, adding no usage of its own.
        collection = _collected(_bare(_MESSAGE), _NAMED_CONTENT, stream.delta(_MESSAGE, _OUTPUT), _UNNAMED_TERMINAL)
        self.assertEqual(len(collection.samples), 1)
        self.assertEqual(cases.picked(collection.samples[0], *_CONTENT_FIELDS), _CONTENT_NAMES)

    def test_supplied_metadata_is_kept(self) -> None:
        collection = _collected(
            _INIT,
            stream.assistant(_MESSAGE, _BLOCK, timestamp=_TIMESTAMP),
            stream.delta(_MESSAGE, _OUTPUT),
            branches.terminal(modelUsage=_SUPPLIED_USAGE),
        )
        self.assertEqual(cases.picked(collection.samples[0], *_SUPPLIED_FIELDS), _SUPPLIED)
        self.assertEqual(collection.coverage[_LIMITATIONS], ["no-reset-markers"])

    def test_refused_models_stay_unknown(self) -> None:
        # A model a frame named that this collection refused is a gap, and the process's model never stands in for it.
        for name, frames, attributed, gap in _REFUSED_MODELS:
            with self.subTest(name):
                collection = _collected(_INIT, *frames, _TERMINAL)
                self.assertEqual(cases.picked(collection.samples[0], *_ATTRIBUTION), attributed)
                self.assertEqual(collection.reasons.get(gap), 1)

    def test_compaction_boundaries_are_markers(self) -> None:
        collection = _collected(_INIT, *stream.message(_MESSAGE, _OUTPUT), _COMPACTION, _TERMINAL)
        self.assertEqual(collection.markers, [dict(_COMPACTION_MARKER)])
        self.assertEqual(len(collection.samples), 1)


class DamagedStreamTest(unittest.TestCase):
    """A failed, interrupted, or malformed stream keeps every request it still attributes."""

    def test_interrupted_stream_keeps_its_requests(self) -> None:
        # The message started but never closed, a line in between was cut short, and no result ended the run.
        collection = _collected(_INIT, stream.start(_MESSAGE, _BLOCK), '{"type": "assist', _bare(_MESSAGE))
        sample = collection.samples[0]
        self.assertEqual(cases.picked(sample, cases.STATUS, _TURN), _PROVISIONAL_START)
        self.assertEqual(collection.reasons, _INTERRUPTED_GAPS)

    def test_unreadable_frames_are_gaps(self) -> None:
        collection = _collected(_INIT, *_UNREADABLE, _TERMINAL)
        self.assertEqual(collection.samples, [])
        self.assertEqual(collection.reasons, _UNREADABLE_GAPS)

    def test_message_without_usage_is_a_gap(self) -> None:
        # A message witnessed by its content alone was printed, so the invocation is not one that made no request.
        collection = _collected(_INIT, _CONTENT_ONLY, _TERMINAL)
        self.assertEqual(collection.samples, [])
        self.assertEqual(collection.reasons, {coverage.UNREPORTED_USAGE: 1})
        self.assertEqual(collection.status, coverage.INCOMPLETE)

    def test_no_stream_events_is_unavailable(self) -> None:
        collection = _collected("Claude Code banner", json.dumps({stream.TYPE: "rate_limit_event"}))
        self.assertEqual(collection.status, coverage.UNAVAILABLE)
        self.assertEqual(collection.reasons, {coverage.NO_STREAM_EVENTS: 1})

    def test_totals_keep_their_own_evidence(self) -> None:
        # A total whose split contradicts its aggregate, and whose thinking exceeds its output, says so; a
        # `modelUsage` that is no object is a gap; and a total alone is never a request.
        collection = _collected(_INIT, branches.terminal(usage=_CONTRADICTED_TOTAL, modelUsage=[1]))
        self.assertEqual(collection.checkpoints[0][cases.EVIDENCE], _TOTAL_EVIDENCE)
        self.assertEqual(collection.reasons, _TOTAL_GAPS)


class CollectionBoundTest(unittest.TestCase):
    """Every correlation bound holds, and one reached is a gap rather than a silence."""

    def test_correlation_bounds_cut_the_scan_short(self) -> None:
        messages = [_bare(f"msg_{index}") for index in range(_SAMPLE_LIMIT + 1)]
        with patch.object(request_scan, _TRACKED_STEPS, _SAMPLE_LIMIT):
            capped = _collected(_INIT, *messages, _TERMINAL)
        with patch.object(request_scan, "MAX_MARKERS", _MARKER_LIMIT):
            marked = _collected(_INIT, *_model_changes(), _TERMINAL)
        # The request past the bound is one gap, and the trajectory's turn builder it drops with it another.
        self.assertEqual(len(capped.samples), _SAMPLE_LIMIT)
        self.assertEqual(capped.reasons[coverage.CORRELATION_LIMIT], 2)
        self.assertEqual(capped.status, coverage.SOURCE_LIMIT_TRUNCATED)
        self.assertEqual(len(marked.markers), _MARKER_LIMIT)
        self.assertEqual(marked.reasons[coverage.CORRELATION_LIMIT], 1)

    def test_request_keys_hold_to_the_bound(self) -> None:
        # A frame naming its message's API request keeps that key only for a request held, so past the bound the keys
        # a stream names are dropped with the requests they name.
        with patch.object(request_scan, _TRACKED_STEPS, _BOUNDED):
            fold = request_claude_stream.StreamFold.read("\n".join(_REQUESTED_PAST_THE_BOUND))
            oversize = request_claude_stream.StreamFold.read("\n".join(_OVERSIZE_REQUESTED))
        self.assertEqual(len(fold.requests.held), _BOUNDED)
        self.assertLessEqual(len(fold.requests.aliases), _BOUNDED)
        # An id past the metadata bound is no identity kept, so it correlates nothing however many frames name one.
        self.assertEqual(oversize.requests.aliases, {})

    def test_request_keys_need_no_names(self) -> None:
        # Starts sharing one request, none keeping a message id: none is another key for a request held.
        with patch.object(request_scan, _TRACKED_STEPS, _BOUNDED):
            fold = request_claude_stream.StreamFold.read("\n".join(_SHARED_LONG_STARTS))
        self.assertLessEqual(len(fold.requests.aliases), len(fold.requests.held))
        self.assertGreater(fold.gaps[coverage.IDENTITY_CONFLICTING], 0)
        # The index holds that bound itself, by what it joined, so requests whose frames kept no id are held to it too.
        index = request_claude_stream.RequestIndex(_BOUNDED, request_scan.MAX_METADATA_CHARS)
        for message_id in _SHARING_ONE_REQUEST:
            key = index.join((request_claude_stream.TURN, message_id), json.loads(_REQUEST_BLOCK))
            if key is not None and index.room:
                index.held.setdefault(key, RequestFold(0))
        self.assertLessEqual(len(index.aliases), len(index.held))
        self.assertEqual(index.gaps[coverage.IDENTITY_CONFLICTING], 1)

    def test_turn_builder_holds_to_the_bound(self) -> None:
        # The trajectory's own turn builder sees every event, so it is held to the request bound too: past it the
        # builder keeps no message, and the bound reached is a gap.
        subagents = [branches.subagent(call, call=call) for call in _PAST_THE_BOUND]
        with patch.object(request_scan, _TRACKED_STEPS, _BOUNDED):
            fold = request_claude_stream.StreamFold.read("\n".join(subagents))
        builder = fold.turns.builder
        settlement = builder.settlement
        held = (fold.requests.held, builder.by_key, builder.turn_index, settlement.subagent_messages)
        self.assertLessEqual(max(map(len, held)), _BOUNDED)
        self.assertGreater(fold.gaps[coverage.CORRELATION_LIMIT], 0)

    def test_oversize_metadata_is_dropped_whole(self) -> None:
        long_id = "m" * (request_scan.MAX_METADATA_CHARS + 1)
        collection = _collected(_INIT, _bare(long_id, request_id=_REQUEST_ID), _TERMINAL)
        sample = collection.samples[0]
        self.assertEqual(cases.picked(sample, _KIND, _ID), _BY_REQUEST)
        self.assertEqual(collection.reasons[coverage.OVERSIZE_METADATA], 1)

    def test_a_skipped_line_links_no_turn(self) -> None:
        # A line too long to read may have held a frame the trajectory numbered, so no turn is linked past it.
        oversize = stream.assistant("msg_long", _BLOCK, padding="x" * _PADDING)
        with patch.object(request_scan, "MAX_LINE_CHARS", len(oversize) - 1):
            collection = _collected(_INIT, oversize, *stream.message(_MESSAGE, _OUTPUT), _TERMINAL)
        self.assertNotIn(_TURN, collection.samples[0])
        self.assertEqual(collection.status, coverage.SOURCE_LIMIT_TRUNCATED)
