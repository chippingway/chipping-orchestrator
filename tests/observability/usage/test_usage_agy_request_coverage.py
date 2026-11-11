# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity request attribution and coverage: whose request each sample is, and what the collection missed."""

import json
import sys
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import (
    agy_events,
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_scan,
    trajectory,
)
from tests.observability.usage import usage_request_cases as cases
from tests.support import agy_stream as stream

_USAGE = MappingProxyType({protocol.INPUT_TOKENS: 10, protocol.OUTPUT_TOKENS: 2, protocol.CACHE_READ_TOKENS: 0})
_CHILD = "child-conversation"
_SILENT_CHILD = "silent-conversation"
_RESEARCH = "research"
_EARLIER_MODEL = "gemini-3.6-flash-high"
_INIT = stream.init_event()
_TERMINAL = stream.terminal()
_UNNAMED_TERMINAL = json.dumps({"event": "result", "result": {"status": "SUCCESS"}})
_FIRST = stream.step(1, usage=dict(_USAGE))
_SECOND = stream.step(2, usage=dict(_USAGE))
_FOURTH = stream.step(4, usage=dict(_USAGE))
_PARENT_FIELDS = ("parent_conversation_id", "parent_step_index", "subagent_type", cases.MODEL, cases.MODEL_SOURCE)
_CHILD_ATTRIBUTION = (stream.SESSION_ID, 2, _RESEARCH, None, models.UNESTABLISHED)
_IDENTITY_FIELDS = ("id", "id_kind", cases.CONVERSATION_ID, cases.MODEL)
_JOINED_IDENTITY = (f"{stream.SESSION_ID}:1", models.CONVERSATION_STEP, stream.SESSION_ID, stream.MODEL)
_PROCESS_IDENTITY = ("process:1", models.PROCESS_STEP, None, stream.MODEL)
_MARKER_FIELDS = ("kind", cases.MODEL, "previous_model", "position")
_MODEL_CHANGE = (models.MODEL_CHANGE, stream.MODEL, _EARLIER_MODEL, 2)
_ATTRIBUTION_FIELDS = (cases.MODEL, cases.MODEL_SOURCE)
_SUBAGENT_GAPS = MappingProxyType({coverage.SUBAGENT_MODEL_UNESTABLISHED: 1, coverage.SUBAGENT_USAGE_UNAVAILABLE: 1})
_INTERRUPTION_GAPS = MappingProxyType({coverage.UNSETTLED_STEPS: 1, coverage.NO_TERMINAL_RESULT: 1})
_CHECKPOINT_COUNTS = ("observed_checkpoints", "retained_checkpoints")


def _response(conversation: str | None, index: int = 0) -> str:
    """A completed response step of `conversation`, or of none where it is None."""
    fields = {
        "step_index": index,
        "step_type": "agent_response",
        "state": agy_events.DONE,
        "usage": dict(_USAGE),
    }
    if conversation is not None:
        fields[cases.CONVERSATION_ID] = conversation
    return stream.event(agy_events.STEP_UPDATE, **fields)


def _spawning(*children: str, subagent_type: str | None = _RESEARCH) -> str:
    named = {} if subagent_type is None else {"type_name": subagent_type}
    subagents = [{cases.CONVERSATION_ID: child, **named} for child in children]
    return stream.step(2, kind=agy_events.TOOL, subagent_info={"subagents": subagents})


def _init(model: str, conversation: str | None = stream.SESSION_ID) -> str:
    init = {"event": agy_events.INIT, agy_events.INIT: {"model": model}}
    if conversation is not None:
        init[cases.CONVERSATION_ID] = conversation
    return json.dumps(init)


_CHILD_RESPONSE = _response(_CHILD)
_CHILD_TERMINAL = stream.event("result", conversation_id=_CHILD, status=stream.SUCCESS)
_SPAWNING_TWO = _spawning(_CHILD, _SILENT_CHILD)
_EARLIER_INIT = _init(_EARLIER_MODEL)
_NEGATIVE_USAGE = MappingProxyType({**_USAGE, protocol.OUTPUT_TOKENS: -1})
_UNINDEXED_RESPONSE = stream.event(agy_events.STEP_UPDATE, step_type="agent_response", state=agy_events.DONE)
_MALFORMED_UNINDEXED = stream.event(agy_events.STEP_UPDATE, step_type={})
_BROKEN_USAGE = stream.step(3, kind=agy_events.TOOL, usage="broken")
_UNNAMED_USAGE = stream.step(3, kind=agy_events.TOOL, usage={"tokens": 5})
_MALFORMED_ENVELOPE = json.dumps({"event": agy_events.STEP_UPDATE, agy_events.STEP_UPDATE: []})
# A completed request whose duration is twice the largest float: an integer no float holds.
_PAST_FLOAT = int(sys.float_info.max) * 2
_UNFLOATABLE_DURATION = stream.step(3, usage=dict(_USAGE), duration_seconds=_PAST_FLOAT)
_UNREADABLE_SPAWN = stream.step(3, kind=agy_events.TOOL, subagent_info=[])
_UNNAMED_SPAWN = stream.step(3, kind=agy_events.TOOL, subagent_info=json.loads('{"subagents": [{"type_name": "x"}]}'))
_SUBAGENT_STREAM = (_INIT, _FIRST, _SPAWNING_TWO, _CHILD_RESPONSE, _TERMINAL)
# A child's own `init` between two of the parent's requests: it names the child's model, and changes the parent's none.
_CHILD_INIT_STREAM = (
    _INIT, _FIRST, _spawning(_CHILD), _init(_EARLIER_MODEL, _CHILD), _CHILD_RESPONSE, _FOURTH, _TERMINAL,
)
_UNNAMED_INIT = _init(stream.MODEL, None)
# A step naming no conversation: joined to the one a stream names, and kept as the process's where it names none.
_PLACEMENTS = (
    ("one named conversation", (_INIT, _FIRST, _response(None, 1), _TERMINAL), _JOINED_IDENTITY),
    ("no conversation named", (_UNNAMED_INIT, _response(None, 1), _UNNAMED_TERMINAL), _PROCESS_IDENTITY),
)
# A stream where a step naming no conversation could be more than one conversation's.
_UNPLACED = (
    ("a named subagent", (_INIT, _spawning(_CHILD), _response(None))),
    ("an unnamed subagent", (_INIT, _UNNAMED_SPAWN, _response(None, 1))),
)
_TWO_UNNAMED = (_UNNAMED_INIT, _response("one-conversation"), _response("another-conversation"))
_MODEL_CHANGE_STREAM = (_EARLIER_INIT, _FIRST, _INIT, _SECOND, _TERMINAL)
# A stream, and the model and provenance its last request is attributed to.
_REFUSED_INIT = _init(stream.MODEL, "p" * (request_scan.MAX_METADATA_CHARS + 1))
_UNATTRIBUTED = (
    ("another conversation", (_INIT, _response("other-conversation")), models.UNESTABLISHED),
    ("another conversation beside a refused process name", (_REFUSED_INIT, _response(_CHILD)), models.UNESTABLISHED),
    ("no conversation beside a subagent", (_INIT, _spawning(_CHILD), _response(None)), models.UNESTABLISHED),
    ("no model anywhere", (_FIRST,), models.UNAVAILABLE),
    ("two conversations, no init naming one", _TWO_UNNAMED, models.UNESTABLISHED),
)
# One damaged line beside a usable request, and the one gap it leaves.
_DAMAGED = (
    ("frame cut short", '{"event":"step_update","step_update":', coverage.MALFORMED_LINES),
    ("usage with no step index", stream.event(agy_events.STEP_UPDATE, usage=dict(_USAGE)), coverage.UNINDEXED_FRAMES),
    ("generation with no step index", _UNINDEXED_RESPONSE, coverage.UNINDEXED_FRAMES),
    ("response completed with no usage", stream.step(3), coverage.UNREPORTED_USAGE),
    ("negative count", stream.step(3, usage=dict(_NEGATIVE_USAGE)), coverage.INVALID_COUNTERS),
    ("unreadable subagent", _UNREADABLE_SPAWN, coverage.SUBAGENT_UNIDENTIFIED),
    ("unreadable subagent, repeated", f"{_UNREADABLE_SPAWN}\n{_UNREADABLE_SPAWN}", coverage.SUBAGENT_UNIDENTIFIED),
    ("malformed step type, no step index", _MALFORMED_UNINDEXED, coverage.MALFORMED_METADATA),
    ("an envelope that is no object", _MALFORMED_ENVELOPE, coverage.MALFORMED_ENVELOPES),
    ("a duration no float holds", _UNFLOATABLE_DURATION, coverage.MALFORMED_METADATA),
    ("tool usage that is no object", _BROKEN_USAGE, coverage.MALFORMED_USAGE),
    ("tool usage naming no counter", _UNNAMED_USAGE, coverage.MALFORMED_USAGE),
)
# Later `init` events naming no conversation: a change of the one unnamed conversation, and one placed nowhere.
_UNNAMED_EARLIER_INIT = _init(_EARLIER_MODEL, None)
_UNNAMED_CHANGE = (_UNNAMED_EARLIER_INIT, _response(None, 1), _UNNAMED_INIT, _response(None, 2))
_CHANGED_MODELS = (_EARLIER_MODEL, stream.MODEL)
_UNCHANGED_MODELS = (stream.MODEL, stream.MODEL)
_UNPLACED_CHANGE = (_INIT, _FIRST, _spawning(_CHILD), _init(_EARLIER_MODEL, None), _FOURTH)
# A subagent named over several frames: its type supplied by a later one, and then contradicted.
_TYPED_LATER = (_INIT, _spawning(_CHILD, subagent_type=None), _spawning(_CHILD), _CHILD_RESPONSE)
_RETYPED = (*_TYPED_LATER[:3], _spawning(_CHILD, subagent_type="review"), _CHILD_RESPONSE)
_SUBAGENT_TYPE = "subagent_type"
# A stream with nothing to collect, and the status its collection ends in.
_EMPTY = (
    ("no output", "", coverage.UNAVAILABLE),
    ("no Antigravity event", '{"type":"result","usage":{}}', coverage.UNAVAILABLE),
    ("ended with no request", stream.ToolStream.canceled_without_steps(), coverage.COMPLETE_EMPTY),
)
# Each correlation bound, the value it is held to, and a stream reaching it beside the one request that still fits.
_CORRELATION_BOUNDS = (
    ("tracked steps", "MAX_TRACKED_STEPS", 1, (_INIT, _FIRST, _SECOND)),
    ("subagent branches", "MAX_BRANCHES", 1, (_INIT, _SPAWNING_TWO, _CHILD_RESPONSE)),
    ("markers", "MAX_MARKERS", 0, (_EARLIER_INIT, _INIT, _FIRST)),
)


class BranchAttributionTest(unittest.TestCase):
    """A request is attributed to its own conversation's model, and to no other."""

    def test_subagent_usage_keeps_its_parent(self) -> None:
        collection = cases.collected(*_SUBAGENT_STREAM)
        child = collection.samples[1]
        self.assertEqual(cases.picked(child, *_PARENT_FIELDS), _CHILD_ATTRIBUTION)
        models_used = cases.column(collection.samples, cases.MODEL)
        self.assertEqual(models_used, [stream.MODEL, None])
        # The child's model is unestablished, and the child that exposed no usage is a gap of its own.
        self.assertEqual(collection.reasons, _SUBAGENT_GAPS)

    def test_no_model_is_borrowed_or_invented(self) -> None:
        for name, lines, source in _UNATTRIBUTED:
            with self.subTest(name):
                collection = cases.collected(*lines, _TERMINAL)
                attribution = cases.picked(collection.samples[-1], *_ATTRIBUTION_FIELDS)
                self.assertEqual(attribution, (None, source))
                self.assertIn(coverage.MODEL_UNATTRIBUTED, collection.reasons)

    def test_steps_naming_no_conversation_are_placed(self) -> None:
        for name, lines, identity in _PLACEMENTS:
            with self.subTest(name):
                collection = cases.collected(*lines)
                identities = [cases.picked(sample, *_IDENTITY_FIELDS) for sample in collection.samples]
                self.assertEqual(identities, [identity])
                self.assertEqual(collection.status, coverage.COMPLETE)

    def test_unplaced_steps_are_ambiguous(self) -> None:
        for name, lines in _UNPLACED:
            with self.subTest(name):
                collection = cases.collected(*lines, _TERMINAL)
                attribution = cases.picked(collection.samples[-1], *_ATTRIBUTION_FIELDS)
                self.assertEqual(attribution, (None, models.UNESTABLISHED))
                self.assertIn(coverage.CONVERSATION_AMBIGUOUS, collection.reasons)

    def test_a_child_init_names_its_own_model(self) -> None:
        collection = cases.collected(*_CHILD_INIT_STREAM)
        models_used = cases.column(collection.samples, cases.MODEL)
        self.assertEqual(models_used, [stream.MODEL, _EARLIER_MODEL, stream.MODEL])
        self.assertEqual(collection.samples[1][cases.MODEL_SOURCE], models.STREAM_MODEL)
        self.assertFalse(collection.markers)
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_one_named_conversation_is_the_process(self) -> None:
        # No `init` names the conversation, but the stream names only one: the process's own.
        collection = cases.collected(_UNNAMED_INIT, _response(_CHILD), _TERMINAL)
        attribution = cases.picked(collection.samples[0], *_ATTRIBUTION_FIELDS)
        self.assertEqual(attribution, (stream.MODEL, models.STREAM_MODEL))

    def test_model_changes_are_markers(self) -> None:
        collection = cases.collected(*_MODEL_CHANGE_STREAM)
        models_used = cases.column(collection.samples, cases.MODEL)
        self.assertEqual(models_used, [_EARLIER_MODEL, stream.MODEL])
        self.assertEqual(cases.picked(collection.markers[0], *_MARKER_FIELDS), _MODEL_CHANGE)
        self.assertEqual(collection.status, coverage.COMPLETE)


class LaterAttributionTest(unittest.TestCase):
    """What later frames add to a conversation's attribution, and what they cannot."""

    def test_init_naming_no_conversation(self) -> None:
        placed = cases.collected(*_UNNAMED_CHANGE, _TERMINAL)
        self.assertEqual(tuple(cases.column(placed.samples, cases.MODEL)), _CHANGED_MODELS)
        self.assertEqual(len(placed.markers), 1)
        self.assertEqual(placed.status, coverage.COMPLETE)
        # Where the stream names several conversations, the model it names could be any of theirs: a gap.
        unplaced = cases.collected(*_UNPLACED_CHANGE, _TERMINAL)
        self.assertEqual(tuple(cases.column(unplaced.samples, cases.MODEL)), _UNCHANGED_MODELS)
        self.assertIn(coverage.CONVERSATION_AMBIGUOUS, unplaced.reasons)

    def test_later_frames_complete_a_subagent(self) -> None:
        completed = cases.collected(*_TYPED_LATER, _TERMINAL)
        self.assertEqual(completed.samples[0][_SUBAGENT_TYPE], _RESEARCH)
        retyped = cases.collected(*_RETYPED, _TERMINAL)
        self.assertEqual(retyped.samples[0][_SUBAGENT_TYPE], _RESEARCH)
        self.assertIn(coverage.SUBAGENT_ATTRIBUTION_CONFLICTING, retyped.reasons)

    def test_fallback_model_is_bounded(self) -> None:
        oversize = "m" * (request_scan.MAX_METADATA_CHARS + 1)
        collection = cases.collected(_FIRST, _TERMINAL, fallback_model=oversize)
        attribution = cases.picked(collection.samples[0], *_ATTRIBUTION_FIELDS)
        self.assertEqual(attribution, (None, models.UNAVAILABLE))
        self.assertIn(coverage.OVERSIZE_METADATA, collection.reasons)


class CoverageGapTest(unittest.TestCase):
    """Interrupted, damaged, and unsupported streams keep their usable requests and say what they lack."""

    def test_interrupted_stream_keeps_requests(self) -> None:
        response = stream.step(2, state=agy_events.ACTIVE, text_delta="partial")
        command = stream.ToolStream.tool_step(3, state=agy_events.ACTIVE, args={"CommandLine": "sleep 9"})
        collection = cases.collected(_INIT, _FIRST, response, command)
        self.assertEqual(cases.column(collection.samples, cases.STEP_INDEX), [1])
        # A background command still running is no unreported request; the response cut short is.
        self.assertEqual(collection.reasons, _INTERRUPTION_GAPS)
        self.assertEqual(collection.status, coverage.INCOMPLETE)

    def test_damaged_frames_are_gaps(self) -> None:
        for name, line, gap in _DAMAGED:
            with self.subTest(name):
                collection = cases.collected(_INIT, _FIRST, line, _TERMINAL)
                self.assertEqual(collection.reasons, {gap: 1})
                self.assertEqual(collection.samples[0][cases.STEP_INDEX], 1)

    def test_streams_with_nothing_to_collect(self) -> None:
        for name, stdout, status in _EMPTY:
            with self.subTest(name):
                collection = cases.collected(stdout)
                self.assertEqual(collection.status, status)
                self.assertFalse(collection.samples)

    def test_only_the_process_result_ends_the_stream(self) -> None:
        # A subagent's result ends its own conversation; the process that spawned it never printed one of its own.
        collection = cases.collected(_INIT, _FIRST, _spawning(_CHILD), _CHILD_RESPONSE, _CHILD_TERMINAL)
        self.assertEqual(len(collection.samples), 2)
        self.assertIn(coverage.NO_TERMINAL_RESULT, collection.reasons)
        self.assertEqual(collection.status, coverage.INCOMPLETE)

    def test_dispatch_collects_for_antigravity_alone(self) -> None:
        for backend in (protocol.CLAUDE, protocol.CODEX):
            with self.subTest(backend):
                self.assertIsNone(trajectory.parse_agent_request_usage(backend, _FIRST))
        with self.assertRaises(ValueError):
            trajectory.parse_agent_request_usage("gemini", _FIRST)


class CollectionBoundTest(unittest.TestCase):
    """Every bound on correlation state and metadata holds, and a bound reached is a gap rather than a silence."""

    def test_correlation_bounds_cut_the_scan_short(self) -> None:
        for name, bound, held_to, lines in _CORRELATION_BOUNDS:
            with self.subTest(name), patch.object(request_scan, bound, held_to):
                collection = cases.collected(*lines, _TERMINAL)
                self.assertEqual(len(collection.samples), 1)
                self.assertEqual(collection.reasons.get(coverage.CORRELATION_LIMIT), 1)
                self.assertEqual(collection.coverage["scan_scope"], coverage.PARTIAL_SCOPE)

    def test_metadata_and_checkpoints_stay_bounded(self) -> None:
        metadata_bound = len(stream.SESSION_ID) - 1
        with patch.object(request_scan, "MAX_METADATA_CHARS", metadata_bound), \
                patch.object(request_scan, "MAX_CHECKPOINTS", 1):
            collection = cases.collected(_INIT, _FIRST, _TERMINAL, _TERMINAL)
        # A conversation id too long to keep is dropped, and the step is kept under its process identity; the stream
        # named a conversation this collection can no longer compare, so whose step it is stays unknown.
        identity = cases.picked(collection.samples[0], "id_kind", cases.MODEL)
        self.assertEqual(identity, (models.PROCESS_STEP, None))
        self.assertLessEqual({coverage.OVERSIZE_METADATA, coverage.CONVERSATION_AMBIGUOUS}, set(collection.reasons))
        self.assertEqual(cases.picked(collection.coverage, *_CHECKPOINT_COUNTS), (2, 1))
        self.assertEqual(len(collection.checkpoints), 1)
