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


def _spawning(*children: str, subagent_type: str | None = _RESEARCH, index: int = 2) -> str:
    named = {} if subagent_type is None else {"type_name": subagent_type}
    subagents = [{cases.CONVERSATION_ID: child, **named} for child in children]
    return stream.step(index, kind=agy_events.TOOL, subagent_info={"subagents": subagents})


_CHILD_SPAWN = _spawning(_CHILD)


def _init(model: object, conversation: str | None = stream.SESSION_ID) -> str:
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
_UNINDEXED_SPAWN = _spawning(_SILENT_CHILD).replace('"step_index": 2, ', "")
_BROKEN_USAGE = stream.step(3, kind=agy_events.TOOL, usage="broken")
_UNFINISHED_FIELDS = MappingProxyType({"kind": agy_events.TOOL, "state": agy_events.ACTIVE})
_UNFINISHED_TOOL = stream.step(3, usage=dict(_USAGE), **_UNFINISHED_FIELDS)
_INVALID_TERMINAL_USAGE = MappingProxyType({**_USAGE, protocol.INPUT_TOKENS: "invalid"})
_INVALID_TERMINAL = stream.terminal(usage=dict(_INVALID_TERMINAL_USAGE))
_TOTAL_TOKENS = "total_tokens"
_CONTRADICTED_TERMINAL_USAGE = MappingProxyType({**_USAGE, _TOTAL_TOKENS: 999})
_CONTRADICTED_TERMINAL = stream.terminal(usage=dict(_CONTRADICTED_TERMINAL_USAGE))
_HUGE_USAGE = MappingProxyType({**_USAGE, protocol.INPUT_TOKENS: cases.PAST_ANY_COUNT})
_PAST_ANY_COUNT = stream.step(3, usage=dict(_HUGE_USAGE))
_NEGATIVE_INDEX = _FIRST.replace('"step_index": 1', '"step_index": -1')
_UNNAMED_USAGE = stream.step(3, kind=agy_events.TOOL, usage={"tokens": 5})
_MALFORMED_ENVELOPE = json.dumps({"event": agy_events.STEP_UPDATE, agy_events.STEP_UPDATE: []})
# An `init` whose envelope is no object, naming its conversation beside it: the process's, and another one.
_MALFORMED_INIT = _init(None).replace('{"model": null}', "[]")
_MALFORMED_OTHER_INIT = _MALFORMED_INIT.replace(stream.SESSION_ID, "other-conversation")
# A terminal total smaller than the output it reports, its input unreported.
_UNDERCOUNTED_TERMINAL_USAGE = MappingProxyType({protocol.OUTPUT_TOKENS: 2, _TOTAL_TOKENS: 1})
_UNDERCOUNTED_TERMINAL = stream.terminal(usage=dict(_UNDERCOUNTED_TERMINAL_USAGE))
# A completed request whose duration is twice the largest float: an integer no float holds.
_PAST_FLOAT = int(sys.float_info.max) * 2
_UNFLOATABLE_DURATION = stream.step(3, usage=dict(_USAGE), duration_seconds=_PAST_FLOAT)
# Number literals no float holds exactly, printed as the stream would print them: too small, too precise, and an
# exponent past any number, as a count and as a duration.
_STEP_THREE = _UNFLOATABLE_DURATION.replace(str(_PAST_FLOAT), "1")
_INPUT_LITERAL = f'"{protocol.INPUT_TOKENS}": 10'
_TINY_INPUT = _STEP_THREE.replace(_INPUT_LITERAL, f'"{protocol.INPUT_TOKENS}": 1e-400')
_PRECISE_INPUT = _STEP_THREE.replace(_INPUT_LITERAL, f'"{protocol.INPUT_TOKENS}": 10.0000000000000000001')
_UNREADABLE_INPUT = _STEP_THREE.replace(_INPUT_LITERAL, f'"{protocol.INPUT_TOKENS}": 1e99999999999999999999')
_UNREADABLE_DURATION = _STEP_THREE.replace('"duration_seconds": 1', '"duration_seconds": 1e99999999999999999999')
_UNREADABLE_SPAWN = stream.step(3, kind=agy_events.TOOL, subagent_info=[])
_UNNAMED_SPAWN = stream.step(3, kind=agy_events.TOOL, subagent_info=json.loads('{"subagents": [{"type_name": "x"}]}'))
_SUBAGENT_STREAM = (_INIT, _FIRST, _SPAWNING_TWO, _CHILD_RESPONSE, _TERMINAL)
# A child's own `init` between two of the parent's requests: it names the child's model, and changes the parent's none.
_CHILD_INIT_STREAM = (
    _INIT, _FIRST, _CHILD_SPAWN, _init(_EARLIER_MODEL, _CHILD), _CHILD_RESPONSE, _FOURTH, _TERMINAL,
)
_UNNAMED_INIT = _init(stream.MODEL, None)
# A step naming no conversation: joined to the one a stream names, and kept as the process's where it names none.
_PLACEMENTS = (
    ("one named conversation", (_INIT, _FIRST, _response(None, 1), _TERMINAL), _JOINED_IDENTITY),
    ("no conversation named", (_UNNAMED_INIT, _response(None, 1), _UNNAMED_TERMINAL), _PROCESS_IDENTITY),
)
# A stream where a step naming no conversation could be more than one conversation's.
_UNPLACED = (
    ("a named subagent", (_INIT, _CHILD_SPAWN, _response(None))),
    ("an unnamed subagent", (_INIT, _UNNAMED_SPAWN, _response(None, 1))),
    # An unnamed process `init` beside a step and a `result` naming two other conversations is either one's.
    ("an unnamed process beside two conversations", (_UNNAMED_INIT, _response("one-conversation", 1))),
    # An `init` whose envelope is no object still names its conversation, so the stream names two.
    ("an unnamed process beside a malformed init", (_UNNAMED_INIT, _MALFORMED_OTHER_INIT, _FIRST)),
    # A frame whose envelope is no object could have named any conversation.
    ("a frame whose envelope is no object", (_INIT, _MALFORMED_ENVELOPE, _response(None, 1))),
)
_TWO_UNNAMED = (_UNNAMED_INIT, _response("one-conversation"), _response("another-conversation"))
_MODEL_CHANGE_STREAM = (_EARLIER_INIT, _FIRST, _INIT, _SECOND, _TERMINAL)
# A stream, and the model and provenance its last request is attributed to.
_REFUSED_INIT = _init(stream.MODEL, "p" * (request_scan.MAX_METADATA_CHARS + 1))
_OVERSIZE_MODEL_INIT = _init("m" * (request_scan.MAX_METADATA_CHARS + 1))
_UNATTRIBUTED = (
    ("a process model refused", (_OVERSIZE_MODEL_INIT, _FIRST), models.UNESTABLISHED),
    ("another conversation", (_INIT, _response("other-conversation")), models.UNESTABLISHED),
    ("another conversation beside a refused process name", (_REFUSED_INIT, _response(_CHILD)), models.UNESTABLISHED),
    ("no conversation beside a subagent", (_INIT, _CHILD_SPAWN, _response(None)), models.UNESTABLISHED),
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
    ("tool step reporting usage it never completed", _UNFINISHED_TOOL, coverage.UNSETTLED_STEPS),
    ("terminal counter that is no count", _INVALID_TERMINAL, coverage.INVALID_COUNTERS),
    ("an unindexed spawn of a silent subagent", _UNINDEXED_SPAWN, coverage.SUBAGENT_USAGE_UNAVAILABLE),
    ("terminal total contradicting its counters", _CONTRADICTED_TERMINAL, coverage.CONFLICTING_COUNTERS),
    ("a count past any token count", _PAST_ANY_COUNT, coverage.INVALID_COUNTERS),
    ("a step index no counter reaches", _NEGATIVE_INDEX, coverage.UNINDEXED_FRAMES),
    ("tool usage naming no counter", _UNNAMED_USAGE, coverage.MALFORMED_USAGE),
    ("a count too small for a float", _TINY_INPUT, coverage.INVALID_COUNTERS),
    ("a count too precise for a float", _PRECISE_INPUT, coverage.INVALID_COUNTERS),
    ("a count past any number", _UNREADABLE_INPUT, coverage.INVALID_COUNTERS),
    ("a duration past any number", _UNREADABLE_DURATION, coverage.MALFORMED_METADATA),
    ("terminal total below its output alone", _UNDERCOUNTED_TERMINAL, coverage.CONFLICTING_COUNTERS),
)
# Later `init` events naming no conversation: a change of the one unnamed conversation, and one placed nowhere.
_UNNAMED_EARLIER_INIT = _init(_EARLIER_MODEL, None)
_UNNAMED_CHANGE = (_UNNAMED_EARLIER_INIT, _response(None, 1), _UNNAMED_INIT, _response(None, 2))
_CHANGED_MODELS = (_EARLIER_MODEL, stream.MODEL)
_UNCHANGED_MODELS = (stream.MODEL, stream.MODEL)
_UNPLACED_CHANGE = (_INIT, _FIRST, _CHILD_SPAWN, _init(_EARLIER_MODEL, None), _FOURTH)
# A subagent named over several frames: its type supplied by a later one, and then contradicted.
_TYPED_LATER = (_INIT, _spawning(_CHILD, subagent_type=None), _CHILD_SPAWN, _CHILD_RESPONSE)
_RETYPED = (*_TYPED_LATER[:3], _spawning(_CHILD, subagent_type="review"), _CHILD_RESPONSE)
_SUBAGENT_TYPE = "subagent_type"
_PARENT_CONVERSATION = "parent_conversation_id"
# A subagent named again from another parent step contradicts the step it was spawned from.
_RESPAWNED = (_INIT, _CHILD_SPAWN, _spawning(_CHILD, index=3), _CHILD_RESPONSE)
# A spawn first printed naming no conversation, the parent's conversation supplied by its next frame.
_UNNAMED_PARENT_SPAWN = _CHILD_SPAWN.replace(f'"conversation_id": "{stream.SESSION_ID}", ', "")
_UNNAMED_PARENT = (_INIT, _UNNAMED_PARENT_SPAWN, _CHILD_SPAWN, _CHILD_RESPONSE)
# An unnamed process `init`, then one naming the process's settled conversation with another model.
_CHANGE_FIELDS = _MARKER_FIELDS[:3]
_EXPECTED_CHANGE = _MODEL_CHANGE[:3]
_UNNAMED_PROCESS_CHANGE = (_UNNAMED_EARLIER_INIT, _FIRST, _CHILD_SPAWN, _INIT, _FOURTH, _CHILD_RESPONSE)
# A later `init` naming a model this collection refused, and the gap the refusal leaves; the steps around it are begun
# under an earlier model, under no known one, and under one a still later `init` names.
_REFUSED_MODELS = (
    ("too long to keep", _OVERSIZE_MODEL_INIT, coverage.OVERSIZE_METADATA),
    ("no string", _init(7), coverage.MALFORMED_METADATA),
    ("an envelope that is no object", _MALFORMED_INIT, coverage.MALFORMED_ENVELOPES),
)
_CONFIGURED_MODEL = "configured-model"
_AROUND_REFUSAL = (_EARLIER_MODEL, None, stream.MODEL)
_SOURCES_AROUND_REFUSAL = (models.STREAM_MODEL, models.UNESTABLISHED, models.STREAM_MODEL)
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
# A stream the scan bound cuts short before the spawn its unread rest announces, the output it reads and the lines it
# leaves: read whole, its first request is a conversation's other than the process's, so read in part it is no more.
_CUT_SHORT = (
    ("a frame naming no conversation", f"{_INIT}\n{_response(None, 1)}", (_CHILD_SPAWN, _CHILD_RESPONSE, _TERMINAL)),
    ("an unnamed process init", f"{_UNNAMED_INIT}\n{_response(_CHILD, 1)}", (_CHILD_SPAWN, _TERMINAL)),
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
        collection = cases.collected(_UNNAMED_INIT, _response(_CHILD), _UNNAMED_TERMINAL)
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

    def test_later_frames_complete_the_parent(self) -> None:
        respawned = cases.collected(*_RESPAWNED, _TERMINAL)
        self.assertIn(coverage.SUBAGENT_ATTRIBUTION_CONFLICTING, respawned.reasons)
        completed = cases.collected(*_UNNAMED_PARENT, _TERMINAL)
        self.assertEqual(completed.samples[0][_PARENT_CONVERSATION], stream.SESSION_ID)
        # The process's first `init` named no conversation, but the stream settles one: a later `init` naming it with
        # another model is a change of that conversation's model.
        changed = cases.collected(*_UNNAMED_PROCESS_CHANGE, _TERMINAL)
        self.assertEqual(cases.picked(changed.markers[0], *_CHANGE_FIELDS), _EXPECTED_CHANGE)

    def test_a_refused_model_is_unknown_from_then_on(self) -> None:
        for name, refused, gap in _REFUSED_MODELS:
            with self.subTest(name):
                lines = (_EARLIER_INIT, _FIRST, refused, _SECOND, _INIT, _FOURTH, _TERMINAL)
                collection = cases.collected(*lines, fallback_model=_CONFIGURED_MODEL)
                self.assertEqual(tuple(cases.column(collection.samples, cases.MODEL)), _AROUND_REFUSAL)
                self.assertEqual(tuple(cases.column(collection.samples, cases.MODEL_SOURCE)), _SOURCES_AROUND_REFUSAL)
                # No change is known to or from a model this collection could not keep.
                self.assertFalse(collection.markers)
                self.assertEqual(collection.reasons, {gap: 1, coverage.MODEL_UNATTRIBUTED: 1})

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
        collection = cases.collected(_INIT, _FIRST, _CHILD_SPAWN, _CHILD_RESPONSE, _CHILD_TERMINAL)
        self.assertEqual(len(collection.samples), 2)
        self.assertIn(coverage.NO_TERMINAL_RESULT, collection.reasons)
        self.assertEqual(collection.status, coverage.INCOMPLETE)

    def test_checkpoints_keep_invalid_evidence(self) -> None:
        collection = cases.collected(_INIT, _FIRST, _INVALID_TERMINAL)
        checkpoint = collection.checkpoints[0]
        self.assertNotIn(protocol.INPUT_TOKENS, checkpoint[cases.RAW])
        self.assertEqual(checkpoint[cases.EVIDENCE], {protocol.INPUT_TOKENS: "invalid"})
        self.assertEqual(collection.status, coverage.INCOMPLETE)
        # A total its own counters contradict keeps its count, and says it is conflicting.
        contradicted = cases.collected(_INIT, _FIRST, _CONTRADICTED_TERMINAL).checkpoints[0]
        self.assertEqual(contradicted[cases.EVIDENCE], {_TOTAL_TOKENS: "conflicting"})
        # So does one smaller than the one counter it reports, the other unreported.
        undercounted = cases.collected(_INIT, _FIRST, _UNDERCOUNTED_TERMINAL)
        self.assertEqual(undercounted.checkpoints[0][cases.RAW], dict(_UNDERCOUNTED_TERMINAL_USAGE))
        self.assertEqual(undercounted.checkpoints[0][cases.EVIDENCE], {_TOTAL_TOKENS: "conflicting"})
        self.assertEqual(undercounted.status, coverage.INCOMPLETE)

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

    def test_unread_lines_leave_placement_open(self) -> None:
        for name, read, unread in _CUT_SHORT:
            with self.subTest(name), patch.object(request_scan, "MAX_SCAN_CHARS", len(read)):
                collection = cases.collected(read, *unread)
                attribution = cases.picked(collection.samples[0], *_ATTRIBUTION_FIELDS)
                self.assertEqual(attribution, (None, models.UNESTABLISHED))
                self.assertLessEqual({coverage.SCAN_LIMIT, coverage.CONVERSATION_AMBIGUOUS}, set(collection.reasons))

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
