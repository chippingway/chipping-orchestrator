# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude subagent requests: settled only where the evidence names one message, and kept on branches of their own."""

import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
)
from tests.observability.usage import (
    usage_claude_request_branches as branches,
    usage_claude_request_streams as stream,
    usage_request_cases as cases,
)

_OUTPUT = normalization.OUTPUT_TOKENS
_SETTLED = (cases.STATUS, "settlement")
_PROVISIONAL = (models.PROVISIONAL, "message-start")
_RECONCILED = (models.FINAL, "model-usage")
_ID = "id"
_ORDER = "branch_order"
_SCOPE = "scope"
_AGENT_ID = "agent_id"
_STREAM_EVENT = "stream_event"
_ATTRIBUTION = (cases.MODEL, cases.MODEL_SOURCE)
_LEAD = "msg_lead"
_SUB = "msg_sub"
_OTHER_SUB = "msg_sub_other"
_OTHER_CALL = "toolu_call_b"
_OTHER_AGENT = "agent_b"
_HANDBACK_ID = f"handback:{branches.CALL}"
_LEAD_OUTPUT = 30
_HANDBACK_OUTPUT = 20
_HANDBACK_THINKING = 15
# What `modelUsage` reports beyond every printed output: the subagent message's start count is 1 of it.
_UNPRINTED = 6
_START_OUTPUT = stream.START_COUNTS[-1]
_SETTLED_OUTPUT = _START_OUTPUT + _UNPRINTED
_MODEL_OUTPUT = _LEAD_OUTPUT + _SETTLED_OUTPUT + _HANDBACK_OUTPUT
# The lead message, the subagent's message, and its hand-back each start with the same prompt, the hand-back with its
# own, so each class's printed total is two message prompts and the hand-back's.
_MESSAGE_PROMPT = stream.START_COUNTS[:-1]
_PROMPT_PARTS = tuple(zip(_MESSAGE_PROMPT, branches.HANDBACK_PROMPT, strict=True))
_PRINTED = tuple(2 * part + handed for part, handed in _PROMPT_PARTS)
_WITH_ANOTHER = tuple(3 * part + handed for part, handed in _PROMPT_PARTS)
_INIT = stream.init()
_TASK = branches.task_started()
_LEAD_MESSAGE = stream.message(_LEAD, _LEAD_OUTPUT)
_SUBAGENT = branches.subagent(_SUB)
_HANDBACK = branches.handback(branches.CALL, _HANDBACK_OUTPUT, thinking=_HANDBACK_THINKING)
_UNREPORTED_CACHE_READS = branches.model_usage((*_PRINTED, _MODEL_OUTPUT))
_UNREPORTED_CACHE_READS[stream.MODEL].pop("cacheReadInputTokens")
_HANDBACK_RAW = MappingProxyType({stream.OUTPUT: _HANDBACK_OUTPUT, stream.THINKING: _HANDBACK_THINKING})
_HANDBACK_CORRELATION = ("handback-call", branches.CALL, branches.AGENT, branches.SUBAGENT_TYPE, models.OUTPUT_SCOPE)
# The turn after the lead message's and the subagent message's, and the place after the subagent message's.
_HANDBACK_PLACE = (2, 1)
_HANDBACK_IDS = (_HANDBACK_ID, f"handback:{_OTHER_CALL}", "position:8")
_ON_MODEL = (stream.MODEL, models.STREAM_MODEL)
_ON_OTHER_MODEL = (stream.OTHER_MODEL, models.STREAM_MODEL)
_ATTRIBUTIONS = (_ON_MODEL, _ON_OTHER_MODEL, (None, models.UNESTABLISHED), _ON_MODEL, _ON_OTHER_MODEL)
_CHANGE = ("model-change", stream.OTHER_MODEL, stream.MODEL)
_CHANGES = ((*_CHANGE, None), (*_CHANGE, branches.CALL))
_MARKER_FIELDS = ("kind", "model", "previous_model", stream.PARENT)
_INTERLEAVED_ORDER = (0, 0, 1, 1, 0)
_INTERLEAVED_CALLS = (branches.CALL, _OTHER_CALL, branches.CALL, _OTHER_CALL, None)
# The frames naming a subagent call before its hand-back, and hand-backs naming no agent: one answering that call,
# one answering a call nothing named.
_CHILD_PROMPT = stream.line({
    stream.TYPE: "user",
    stream.PARENT: branches.CALL,
    _AGENT_ID: branches.AGENT,
    stream.MESSAGE: {"role": "user", "content": [{stream.TYPE: "text", "text": "the task"}]},
})
_LAUNCHES = (("a task_started frame", _TASK), ("the subagent's user frame", _CHILD_PROMPT))
_AGENTLESS_HANDBACKS = (
    branches.handback(branches.CALL, _HANDBACK_OUTPUT, agent=None),
    branches.handback(_OTHER_CALL, _HANDBACK_OUTPUT, agent=None),
)
# A frame naming a subagent's agent but not the call that launched it, and the model and identities it then holds.
_AGENT_ONLY = stream.assistant(_SUB, stream.usage(), model=None, agent_id=branches.AGENT)
_AGENT_ONLY_FIELDS = (cases.MODEL, cases.MODEL_SOURCE, _AGENT_ID, stream.PARENT)
_AGENT_ONLY_HELD = (None, models.UNESTABLISHED, branches.AGENT, None)
# One message's blocks, the first naming no subagent, the second its call and agent, the third another call.
_UNPLACED_BLOCK = stream.assistant(_SUB, stream.usage(), model=None)
_PLACED_BLOCKS = (
    _UNPLACED_BLOCK,
    branches.subagent(_SUB, model=None),
    branches.subagent(_SUB, model=None, call=_OTHER_CALL),
)
_PLACED_HELD = (None, models.UNESTABLISHED, branches.AGENT, branches.CALL)
# Stream events naming a subagent's agent beside their message, and the frames of a message so named: by a block, by
# its start and close, and by a content event following a block naming neither call nor agent.
_AGENT_WRAPPER = MappingProxyType({"api_message_id": _SUB, _AGENT_ID: branches.AGENT})
_AGENT_MESSAGE = MappingProxyType({_ID: _SUB, stream.USAGE: stream.usage()})
_AGENT_START = stream.line({
    stream.TYPE: _STREAM_EVENT,
    **_AGENT_WRAPPER,
    "event": {stream.TYPE: "message_start", stream.MESSAGE: dict(_AGENT_MESSAGE)},
})
_AGENT_DELTA = stream.line({
    stream.TYPE: _STREAM_EVENT,
    **_AGENT_WRAPPER,
    "event": {stream.TYPE: "message_delta", stream.USAGE: {stream.OUTPUT: _HANDBACK_OUTPUT}},
})
_TEXT_DELTA = MappingProxyType({stream.TYPE: "text_delta", "text": "a"})
_AGENT_CONTENT = stream.line({
    stream.TYPE: _STREAM_EVENT,
    **_AGENT_WRAPPER,
    "event": {stream.TYPE: "content_block_delta", "index": 0, "delta": dict(_TEXT_DELTA)},
})
_AGENT_SHAPES = (
    ("a block", (_AGENT_ONLY,)),
    ("its start and close", (_AGENT_START, _AGENT_DELTA)),
    ("a later content event", (_UNPLACED_BLOCK, _AGENT_CONTENT)),
)


def _terminal(printed: tuple[int, ...]) -> str:
    return branches.terminal(modelUsage=branches.model_usage((*printed, _MODEL_OUTPUT)))


_SETTLING_TERMINAL = _terminal(_PRINTED)
# A model total and a hand-back's input reported as fractions: the run accounting truncates each to the whole number
# that settles the subagent's message, while to this collection neither is a count.
_HALF = 0.5
_UNREPORTED_TERMINAL = branches.terminal(modelUsage=_UNREPORTED_CACHE_READS)
_FRACTIONAL_TOTALS = (*_PRINTED, _MODEL_OUTPUT + _HALF)
_FRACTIONAL_TERMINAL = branches.terminal(modelUsage=branches.model_usage(_FRACTIONAL_TOTALS))
_WHOLE_INPUT = '"input_tokens": 2,'
_FRACTIONAL_HANDBACK = _HANDBACK.replace(_WHOLE_INPUT, '"input_tokens": 2.5,')
# Requests the run accounting's settlement never sums: a subagent message no frame reported usage for, and a hand-back
# naming no agent beside totals that leave its prompt out -- either of which could hold the remainder it attributes.
_SILENT_SUBAGENT = stream.assistant("msg_sub_silent", None, parent_tool_use_id=branches.CALL, agent_id=branches.AGENT)
_AGENTLESS_HANDBACK = branches.handback(branches.CALL, _HANDBACK_OUTPUT, agent=None)
_UNSUMMED = tuple(2 * part for part in _MESSAGE_PROMPT)
# A subagent message whose writes are a lifetime split alone, spelled as strings: the run accounting reads no write of
# it and settles against totals leaving them out, while this collection reads every one of them.
_STRING_SPLIT = stream.usage()
_STRING_SPLIT.pop(stream.CACHE_WRITE)
_START_WRITES = stream.START_COUNTS[2]
_STRING_SPLIT[stream.SPLIT] = {stream.FIVE_MINUTE: str(_START_WRITES), stream.ONE_HOUR: "0"}
_STRING_SPLIT_SUBAGENT = stream.assistant(
    _SUB, _STRING_SPLIT, parent_tool_use_id=branches.CALL, agent_id=branches.AGENT,
)
_UNREAD_WRITES = (*_PRINTED[:2], _PRINTED[2] - _START_WRITES)
# Evidence that names no one message: two open messages share a remainder no frame splits; a total covering usage
# the stream did not print establishes nothing about the one open message, and nor does one missing a total its
# check reads, one resting on a count that is no whole number -- in the total or in a request it sums -- or one
# leaving out a request this collection holds. Each with the subagent frames beside it and how many messages stay
# open.
_AMBIGUOUS = (
    ("two open messages", (_SUBAGENT, branches.subagent(_OTHER_SUB), _HANDBACK), _terminal(_WITH_ANOTHER), 2),
    ("a total covering unprinted usage", (_SUBAGENT, _HANDBACK), _terminal(_WITH_ANOTHER), 1),
    ("a total missing its cache reads", (_SUBAGENT, _HANDBACK), _UNREPORTED_TERMINAL, 1),
    ("a fractional total", (_SUBAGENT, _HANDBACK), _FRACTIONAL_TERMINAL, 1),
    ("a fractional prompt it sums", (_SUBAGENT, _FRACTIONAL_HANDBACK), _SETTLING_TERMINAL, 1),
    ("a message reporting no usage", (_SUBAGENT, _SILENT_SUBAGENT, _HANDBACK), _SETTLING_TERMINAL, 1),
    ("a hand-back naming no agent", (_SUBAGENT, _AGENTLESS_HANDBACK), _terminal(_UNSUMMED), 1),
    ("writes the accounting cannot read", (_STRING_SPLIT_SUBAGENT, _HANDBACK), _terminal(_UNREAD_WRITES), 1),
)


def _collected(*lines: str) -> cases.Collected:
    return cases.collected(*lines, backend=protocol.CLAUDE)


def _sample(collection: cases.Collected, request_id: str) -> dict:
    return next(sample for sample in collection.samples if sample[_ID] == request_id)


def _subagent_settlements(collection: cases.Collected) -> set[tuple[str, str]]:
    """How each subagent message -- a sample on a call's branch and of whole-request scope -- was settled."""
    subagents = [sample for sample in collection.samples if stream.PARENT in sample]
    messages = [sample for sample in subagents if sample[_SCOPE] == models.REQUEST_SCOPE]
    return {cases.picked(sample, *_SETTLED) for sample in messages}


class ModelUsageSettlementTest(unittest.TestCase):
    """`modelUsage` settles a subagent message only where its evidence names that message and no other."""

    def test_sole_open_message_settles(self) -> None:
        collection = _collected(_INIT, _TASK, *_LEAD_MESSAGE, _SUBAGENT, _HANDBACK, _SETTLING_TERMINAL)
        sample = _sample(collection, _SUB)
        self.assertEqual(cases.picked(sample, *_SETTLED), _RECONCILED)
        self.assertEqual(sample[_OUTPUT], _SETTLED_OUTPUT)
        # The frame reported the start count; the settled one is what the request is normalized from, with no
        # separate thinking count, which `modelUsage` never splits by message.
        self.assertEqual(sample[cases.RAW][stream.OUTPUT], _START_OUTPUT)
        self.assertEqual(sample[cases.EVIDENCE][normalization.REASONING_TOKENS], normalization.MISSING)
        self.assertEqual(collection.reasons, {coverage.OUTPUT_ONLY_OBSERVATIONS: 1})

    def test_ambiguous_evidence_settles_nothing(self) -> None:
        for name, subagent_frames, terminal, open_messages in _AMBIGUOUS:
            with self.subTest(name):
                collection = _collected(_INIT, *_LEAD_MESSAGE, *subagent_frames, terminal)
                self.assertEqual(_subagent_settlements(collection), {_PROVISIONAL})
                self.assertEqual(collection.reasons[coverage.PROVISIONAL_USAGE], open_messages)

    def test_a_result_total_is_never_a_request(self) -> None:
        # Usage reported only in aggregate is a checkpoint; nothing divides it among requests or makes one of it.
        collection = _collected(_INIT, branches.terminal(usage=stream.usage()))
        self.assertEqual(collection.samples, [])
        self.assertEqual(collection.checkpoints[0][_SCOPE], models.LEAD_THREAD_SCOPE)
        self.assertEqual(collection.reasons, {coverage.AGGREGATE_ONLY_USAGE: 1})
        self.assertEqual(collection.status, coverage.INCOMPLETE)


class HandbackTest(unittest.TestCase):
    """A hand-back is its subagent's closing output, under the call it answers."""

    def test_handback_is_an_output_only_observation(self) -> None:
        collection = _collected(_INIT, _TASK, *_LEAD_MESSAGE, _SUBAGENT, _HANDBACK, _SETTLING_TERMINAL)
        sample = _sample(collection, _HANDBACK_ID)
        correlation = cases.picked(sample, "id_kind", stream.PARENT, _AGENT_ID, "subagent_type", _SCOPE)
        self.assertEqual(correlation, _HANDBACK_CORRELATION)
        self.assertEqual(cases.picked(sample, *_SETTLED), (models.FINAL, "handback"))
        self.assertEqual(sample[cases.RAW], _HANDBACK_RAW)
        self.assertEqual(cases.picked(sample, _OUTPUT, normalization.CONTEXT_INPUT_TOKENS), (_HANDBACK_OUTPUT, None))
        # It is numbered after every message turn, as the trajectory's turns number it, and ends its branch.
        self.assertEqual(cases.picked(sample, "trajectory_turn", _ORDER), _HANDBACK_PLACE)

    def test_repeated_and_resumed_handbacks(self) -> None:
        # One call answered twice is one request; a resumed subagent -- the same agent answering a new call -- is
        # another, and a hand-back answering no named call is known by its line alone.
        collection = _collected(
            _INIT,
            *_LEAD_MESSAGE,
            _HANDBACK,
            _HANDBACK,
            branches.handback(_OTHER_CALL, _HANDBACK_OUTPUT),
            branches.handback(None, _HANDBACK_OUTPUT),
            branches.terminal(),
        )
        handbacks = [sample for sample in collection.samples if sample[_SCOPE] == models.OUTPUT_SCOPE]
        self.assertEqual(tuple(cases.column(handbacks, _ID)), _HANDBACK_IDS)
        self.assertEqual(set(cases.column(handbacks, _AGENT_ID)), {branches.AGENT})
        self.assertEqual(collection.reasons[coverage.SUBAGENT_UNIDENTIFIED], 1)

    def test_known_call_needs_no_agent(self) -> None:
        # A hand-back naming no agent is a subagent's where it answers a call the stream named a subagent for -- by a
        # `task_started` frame, or by the subagent's own `user` frame -- its agent identity listed as left out; a tool's
        # result answering any other call is no request.
        for name, launching in _LAUNCHES:
            with self.subTest(name):
                collection = _collected(_INIT, launching, *_AGENTLESS_HANDBACKS, branches.terminal())
                self.assertEqual(cases.column(collection.samples, _ID), [_HANDBACK_ID])
                self.assertNotIn(_AGENT_ID, collection.samples[0])
                self.assertEqual(collection.samples[0][_OUTPUT], _HANDBACK_OUTPUT)
                self.assertIn("no-agent-id", collection.coverage["limitations"])

    def test_disagreeing_handbacks_conflict(self) -> None:
        disagreeing = branches.handback(branches.CALL, _HANDBACK_OUTPUT + 1)
        collection = _collected(_INIT, *_LEAD_MESSAGE, _HANDBACK, disagreeing, branches.terminal())
        evidence = _sample(collection, _HANDBACK_ID)[cases.EVIDENCE]
        self.assertEqual(evidence[_OUTPUT], normalization.CONFLICTING)
        self.assertIn(coverage.CONFLICTING_COUNTERS, collection.reasons)

    def test_unanswered_subagent_is_a_gap(self) -> None:
        # A subagent the stream launched but whose closing message no hand-back carried left usage unobserved.
        collection = _collected(_INIT, _TASK, *_LEAD_MESSAGE, _SUBAGENT, branches.terminal())
        self.assertEqual(collection.reasons[coverage.SUBAGENT_USAGE_UNAVAILABLE], 1)
        self.assertEqual(collection.status, coverage.INCOMPLETE)


class BranchTest(unittest.TestCase):
    """Each branch keeps its own order and models, never borrowing another branch's."""

    def test_later_blocks_place_the_request(self) -> None:
        # A block naming the call and agent an earlier block left out makes the message the subagent's, so it takes
        # no lead-thread model; a block naming another call than that keeps the first and is a gap.
        collection = _collected(_INIT, *_PLACED_BLOCKS, branches.terminal())
        self.assertEqual(cases.picked(collection.samples[0], *_AGENT_ONLY_FIELDS), _PLACED_HELD)
        self.assertEqual(collection.reasons[coverage.SUBAGENT_ATTRIBUTION_CONFLICTING], 1)

    def test_agent_without_call_is_a_child(self) -> None:
        # Any frame of a message naming a subagent's agent but not its call makes the message the subagent's: it takes
        # no lead-thread model, and the call it sits under is a gap.
        for name, frames in _AGENT_SHAPES:
            with self.subTest(name):
                collection = _collected(_INIT, *frames, branches.terminal())
                self.assertEqual(cases.picked(collection.samples[0], *_AGENT_ONLY_FIELDS), _AGENT_ONLY_HELD)
                self.assertEqual(collection.reasons[coverage.SUBAGENT_UNIDENTIFIED], 1)
                self.assertIn(coverage.SUBAGENT_MODEL_UNESTABLISHED, collection.reasons)

    def test_interleaved_branches_keep_their_order(self) -> None:
        collection = _collected(
            _INIT,
            branches.subagent("msg_a_0"),
            branches.subagent("msg_b_0", call=_OTHER_CALL, agent=_OTHER_AGENT),
            branches.subagent("msg_a_1"),
            branches.subagent("msg_b_1", call=_OTHER_CALL, agent=_OTHER_AGENT),
            *_LEAD_MESSAGE,
            branches.terminal(),
        )
        samples = collection.samples
        self.assertEqual(tuple(cases.column(samples, _ORDER)), _INTERLEAVED_ORDER)
        self.assertEqual(tuple(cases.column(samples, stream.PARENT)), _INTERLEAVED_CALLS)
        positions = cases.column(samples, "position")
        self.assertEqual(positions, sorted(positions))

    def test_each_message_keeps_its_own_model(self) -> None:
        # A lead message on another model is a change of the lead thread's; a subagent naming none takes no other
        # message's model, the lead thread's included, and a change on its branch is marked with its call.
        collection = _collected(
            _INIT,
            *_LEAD_MESSAGE,
            *stream.message("msg_lead_next", _LEAD_OUTPUT, model=stream.OTHER_MODEL),
            branches.subagent(_SUB, model=None),
            branches.subagent("msg_sub_1"),
            branches.subagent("msg_sub_2", model=stream.OTHER_MODEL),
            branches.terminal(),
        )
        attribution = tuple(cases.picked(sample, *_ATTRIBUTION) for sample in collection.samples)
        self.assertEqual(attribution, _ATTRIBUTIONS)
        changes = tuple(cases.picked(marker, *_MARKER_FIELDS) for marker in collection.markers)
        self.assertEqual(changes, _CHANGES)
        self.assertEqual(collection.reasons[coverage.SUBAGENT_MODEL_UNESTABLISHED], 1)
