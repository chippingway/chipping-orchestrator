# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude request samples: one per API message, its blocks grouped and its output settled by the report closing it."""

import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
)
from tests.observability.usage import usage_claude_request_streams as stream, usage_request_cases as cases

_CONTEXT = normalization.CONTEXT_INPUT_TOKENS
_OUTPUT = normalization.OUTPUT_TOKENS
_REASONING = normalization.REASONING_TOKENS
_SETTLED = (cases.STATUS, "settlement")
_DELTA_SETTLED = (models.FINAL, "message-delta")
_START_SETTLED = (models.PROVISIONAL, "message-start")
_ID = "id"
_NORMALIZED_WRITES = (normalization.CACHE_WRITE_TOKENS, normalization.CACHE_WRITE_LIFETIMES, _CONTEXT)
_FINAL_OUTPUT = 50
_THINKING = 20
_BLOCKS = 3
_FIRST = "msg_a"
_SECOND = "msg_b"
# The `init` frame prints first, so a message's start prints on line 1.
_PLACED = ((_FIRST, 1),)
_ONE_MESSAGE = stream.message(_FIRST, _FINAL_OUTPUT, thinking=_THINKING)
_OPENED = _ONE_MESSAGE[:-1]
_INIT = stream.init()
_TERMINAL = stream.line({stream.TYPE: "result", "subtype": "success"})
_INVALID = (normalization.INVALID, None)
_START_OUTPUT = (normalization.OBSERVED, stream.START_COUNTS[-1])
_PROVISIONAL_GAPS = MappingProxyType({coverage.PROVISIONAL_USAGE: 1})
_INVALID_GAPS = MappingProxyType({coverage.INVALID_COUNTERS: 1})
_UNNAMED_GAPS = MappingProxyType({coverage.PROVISIONAL_USAGE: 1, coverage.UNINDEXED_FRAMES: 1})
_TWO_CLOSES = (stream.delta(_FIRST, _FINAL_OUTPUT), stream.delta(_FIRST, _THINKING))
_CONFLICT = (_DELTA_SETTLED, (normalization.CONFLICTING, None), MappingProxyType({coverage.CONFLICTING_COUNTERS: 1}))
# A close reporting no output beside its thinking settles the thinking alone, never beside the start count.
_THINKING_ALONE = stream.delta(_FIRST, None, thinking=_THINKING)
_PARTIAL = (models.FINAL, "message-delta-partial")
_NO_OUTPUT = (normalization.MISSING, None)
_MISSING_GAPS = MappingProxyType({coverage.MISSING_COUNTERS: 1})
# A message closed by each kind of report, then the status and settlement that leaves it, its output's evidence and
# count, and the gaps its collection records.
_DELTA_CASES = (
    ("no closing report", (), (_START_SETTLED, _START_OUTPUT, _PROVISIONAL_GAPS)),
    ("a negative output", (stream.delta(_FIRST, -5),), (_DELTA_SETTLED, _INVALID, _INVALID_GAPS)),
    ("an output that is no count", (stream.delta(_FIRST, "many"),), (_DELTA_SETTLED, _INVALID, _INVALID_GAPS)),
    ("two disagreeing closes", _TWO_CLOSES, _CONFLICT),
    ("a close naming no message", (stream.delta(None, _FINAL_OUTPUT),), (_START_SETTLED, _START_OUTPUT, _UNNAMED_GAPS)),
    ("a close breaking out its thinking alone", (_THINKING_ALONE,), (_PARTIAL, _NO_OUTPUT, _MISSING_GAPS)),
)
_FIVE = 4
_HOUR = 6
_WRITES = _FIVE + _HOUR
_SPLIT = MappingProxyType({stream.FIVE_MINUTE: _FIVE, stream.ONE_HOUR: _HOUR})
_NORMALIZED_SPLIT = MappingProxyType({"cache_write_5m": _FIVE, "cache_write_1h": _HOUR})
_PROMPT = stream.START_COUNTS[0] + stream.START_COUNTS[1] + _WRITES
_WHOLE = ((_WRITES, _NORMALIZED_SPLIT, _PROMPT), MappingProxyType({}))
_UNSPLIT = ((_WRITES, None, _PROMPT), MappingProxyType({}))
_CONTRADICTED = ((None, None, None), MappingProxyType({coverage.CONFLICTING_COUNTERS: 1}))
_UNREAD_SPLIT = ((_WRITES, None, _PROMPT), _INVALID_GAPS)
# A message's cache-write fields, then the cache writes, lifetimes, and context input it normalizes to, beside the
# gaps it records.
_LIFETIME_CASES = (
    ("an aggregate beside its split", MappingProxyType({stream.CACHE_WRITE: _WRITES, stream.SPLIT: _SPLIT}), _WHOLE),
    ("an aggregate alone", MappingProxyType({stream.CACHE_WRITE: _WRITES, stream.SPLIT: None}), _UNSPLIT),
    ("a split alone", MappingProxyType({stream.CACHE_WRITE: None, stream.SPLIT: _SPLIT}), _WHOLE),
    ("a contradicting split", MappingProxyType({stream.CACHE_WRITE: _WRITES + 1, stream.SPLIT: _SPLIT}), _CONTRADICTED),
    ("a split that is no object", MappingProxyType({stream.CACHE_WRITE: _WRITES, stream.SPLIT: (1,)}), _UNREAD_SPLIT),
)


def _single(*lines: str) -> cases.Collected:
    return cases.collected(_INIT, *lines, _TERMINAL, backend=protocol.CLAUDE)


def _closing_reading(closes: tuple[str, ...]) -> tuple[object, ...]:
    collection = _single(*_OPENED, *closes)
    sample = collection.samples[0]
    output = (sample[cases.EVIDENCE][_OUTPUT], sample.get(_OUTPUT))
    return cases.picked(sample, *_SETTLED), output, collection.reasons


def _written_into(block: dict[str, object], name: str, written: object) -> None:
    """Set one cache-write field the way a stream prints it, or leave it out where `written` is None."""
    block.pop(name, None)
    if written is not None:
        block[name] = dict(written) if isinstance(written, MappingProxyType) else written


def _opened_with(block: dict[str, object]) -> tuple[str, ...]:
    """A message whose frames all carry `block`, closed with one output token."""
    opened = stream.start(_FIRST, block)
    return opened, stream.assistant(_FIRST, block), stream.delta(_FIRST, 1)


def _lifetime_reading(writes: MappingProxyType) -> tuple[object, ...]:
    block = stream.usage()
    for name, written in writes.items():
        _written_into(block, name, written)
    collection = _single(*_opened_with(block))
    return cases.picked(collection.samples[0], *_NORMALIZED_WRITES), collection.reasons


class MessageFoldTest(unittest.TestCase):
    """A message is one request however many blocks it prints, its output settled by the report closing it."""

    def test_repeated_blocks_are_one_request(self) -> None:
        collection = _single(*stream.message(_FIRST, _FINAL_OUTPUT, blocks=_BLOCKS))
        placed = tuple(cases.picked(sample, _ID, "position") for sample in collection.samples)
        self.assertEqual(placed, _PLACED)
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_equal_counts_stay_distinct_messages(self) -> None:
        opened = stream.message(_FIRST, _FINAL_OUTPUT)
        samples = _single(*opened, *stream.message(_SECOND, _FINAL_OUTPUT)).samples
        self.assertEqual(cases.column(samples, _ID), [_FIRST, _SECOND])
        self.assertEqual(cases.column(samples, "branch_order"), [0, 1])
        first, second = cases.column(samples, cases.RAW)
        self.assertEqual(first, second)

    def test_final_delta_replaces_the_start_count(self) -> None:
        # The close reports the whole output, thinking included, so it replaces the start count rather than adding.
        sample = _single(*_ONE_MESSAGE).samples[0]
        self.assertEqual(cases.picked(sample, _OUTPUT, _REASONING), (_FINAL_OUTPUT, _THINKING))
        self.assertEqual(sample[cases.RAW][stream.THINKING], _THINKING)
        self.assertEqual(cases.picked(sample, *_SETTLED), _DELTA_SETTLED)

    def test_missing_and_invalid_closes(self) -> None:
        for name, closes, expected in _DELTA_CASES:
            with self.subTest(name):
                self.assertEqual(_closing_reading(closes), expected)
        # A start count stays provisional: it establishes no separate thinking count.
        provisional = _single(*_OPENED).samples[0]
        self.assertEqual(provisional[cases.EVIDENCE][_REASONING], normalization.MISSING)
        # A close that breaks out the thinking and leaves out the output keeps the thinking it reported.
        partial = _single(*_OPENED, _THINKING_ALONE).samples[0]
        self.assertEqual(partial[cases.RAW][stream.THINKING], _THINKING)
        self.assertEqual(partial[_REASONING], _THINKING)

    def test_cache_lifetimes_and_contradictions(self) -> None:
        for name, writes, expected in _LIFETIME_CASES:
            with self.subTest(name):
                self.assertEqual(_lifetime_reading(writes), expected)

    def test_frames_disagreeing_on_input_conflict(self) -> None:
        disagreeing = stream.usage((3, *stream.START_COUNTS[1:]))
        collection = _single(
            stream.start(_FIRST, stream.usage()),
            stream.assistant(_FIRST, disagreeing),
            stream.delta(_FIRST, _FINAL_OUTPUT),
        )
        sample = collection.samples[0]
        self.assertNotIn(stream.INPUT, sample[cases.RAW])
        self.assertEqual(sample[cases.EVIDENCE][_CONTEXT], normalization.CONFLICTING)
        self.assertEqual(collection.reasons, {coverage.CONFLICTING_COUNTERS: 1})
