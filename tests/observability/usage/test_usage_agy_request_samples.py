# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity request samples: one per completed usage-bearing step of the process's own stream."""

import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    agy_events,
    metrics,
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
)
from tests.observability.usage import usage_agy_stream_capture as capture, usage_request_cases as cases
from tests.support import agy_stream as stream

_INPUT = protocol.INPUT_TOKENS
_OUTPUT = protocol.OUTPUT_TOKENS
_CACHE_READ = protocol.CACHE_READ_TOKENS
_TOTAL = "total_tokens"
_RAW_COUNTERS = (_INPUT, _OUTPUT, _CACHE_READ)
_TOTALLED = (*_RAW_COUNTERS, _TOTAL)
_CONTEXT = normalization.CONTEXT_INPUT_TOKENS
_NORMALIZED = (_CONTEXT, _OUTPUT, normalization.REASONING_TOKENS, normalization.SOURCE_TOTAL_TOKENS, _TOTAL)
_CACHE_WRITE = protocol.CACHE_WRITE_TOKENS
_SETTLED = (cases.STATUS, "settlement")
_INPUT_COUNT = 10
_OUTPUT_COUNT = 2
_STEP_USAGE = MappingProxyType({
    _INPUT: _INPUT_COUNT, _OUTPUT: _OUTPUT_COUNT, _CACHE_READ: 0, "thinking_tokens": 1, _TOTAL: 12,
})
# The guide's cached step, normalized: its ordinary input and its cache reads, and its own total kept apart.
_CACHED_CONTEXT = 30_492
_CACHED_OUTPUT = 4
_CACHED_SOURCE_TOTAL = 282
_CACHED_NORMALIZED = (_CACHED_CONTEXT, _CACHED_OUTPUT, 0, _CACHED_SOURCE_TOTAL, _CACHED_CONTEXT + _CACHED_OUTPUT)
_FALLBACK_ATTRIBUTION = (capture.MODEL, models.CONFIGURED_FALLBACK)
_COMPLETE_CAPTURES = (("fresh", capture.FRESH_RUN), ("guide", capture.GUIDE_RUN))
_TWO_STEP_IDS = (f"{stream.SESSION_ID}:1", f"{stream.SESSION_ID}:2")
_RESULT_TOTAL = ("result-total", "conversation", 2)
_INIT = stream.init_event()
_TERMINAL = stream.terminal()


def _usage_step(index: int, **fields) -> str:
    return stream.step(index, usage=dict(_STEP_USAGE), **fields)


def _run_counts(lines: tuple[str, ...]) -> list[int]:
    run = metrics.parse_agent_usage(protocol.AGY, "\n".join(lines), fallback_model=capture.MODEL)
    return [run.input_tokens, run.output_tokens, run.cache_read_tokens]


class CapturedStreamTest(unittest.TestCase):
    """The agy 1.4.10 captures and the headless guide's examples, read request by request."""

    def test_cached_step_adds_its_cache_reads(self) -> None:
        sample = cases.collected(capture.GUIDE_CACHED_STEP, fallback_model=capture.MODEL).samples[0]
        self.assertEqual(cases.picked(sample, *_NORMALIZED), _CACHED_NORMALIZED)
        self.assertEqual(sample[cases.RAW][_TOTAL], _CACHED_SOURCE_TOTAL)
        # The CLI reports no cache write or lifetime, so neither reads as a count.
        self.assertNotIn(_CACHE_WRITE, sample)
        self.assertEqual(sample[cases.EVIDENCE][_CACHE_WRITE], normalization.UNSUPPORTED)
        self.assertEqual(cases.picked(sample, cases.MODEL, cases.MODEL_SOURCE), _FALLBACK_ATTRIBUTION)

    def test_complete_runs_reconcile_in_scope(self) -> None:
        # A fresh run's conversation is its own process, so its terminal total covers the same steps.
        for name, lines in _COMPLETE_CAPTURES:
            with self.subTest(name):
                collection = cases.collected(*lines, fallback_model=capture.MODEL)
                self.assertEqual(collection.status, coverage.COMPLETE)
                self.assertEqual(cases.sums(collection.samples, _RAW_COUNTERS), _run_counts(lines))
                terminal = cases.picked(collection.checkpoints[0][cases.RAW], *_TOTALLED)
                self.assertEqual(tuple(cases.sums(collection.samples, _TOTALLED)), terminal)

    def test_resumed_run_samples_only_its_own_steps(self) -> None:
        collection = cases.collected(*capture.RESUMED_RUN, fallback_model=capture.MODEL)
        samples = collection.samples
        self.assertEqual(cases.column(samples, cases.STEP_INDEX), [4])
        self.assertEqual(cases.sums(samples, _RAW_COUNTERS), _run_counts(capture.RESUMED_RUN))
        # The terminal total counts the whole conversation: aggregate evidence of another scope, never a request.
        terminal = collection.checkpoints[0]
        self.assertEqual(cases.picked(terminal, "kind", "scope", "turns"), _RESULT_TOTAL)
        own_input = cases.sums(samples, (_INPUT,))
        self.assertGreater(terminal[cases.RAW][_INPUT], own_input[0])

    def test_helper_generations_are_requests(self) -> None:
        samples = cases.collected(*capture.GUIDE_RUN).samples
        self.assertEqual(cases.column(samples, "source_kind"), ["agent_response", "checkpoint"])
        self.assertEqual(cases.column(samples, "branch_order"), [0, 1])
        self.assertLess(*cases.column(samples, "position"))


class StepFoldTest(unittest.TestCase):
    """A step is folded from every frame of it, and keyed by its conversation and index alone."""

    def test_repeated_and_sparse_frames_keep_usage(self) -> None:
        collection = cases.collected(
            _INIT,
            _usage_step(1),
            stream.step(1),
            _usage_step(1),
            stream.step(1, usage={_INPUT: _INPUT_COUNT}),
            _TERMINAL,
        )
        raw = cases.column(collection.samples, cases.RAW)
        self.assertEqual(raw, [dict(_STEP_USAGE)])
        self.assertEqual(collection.status, coverage.COMPLETE)

    def test_equal_counts_stay_distinct_steps(self) -> None:
        collection = cases.collected(_INIT, _usage_step(1), _usage_step(2))
        samples = collection.samples
        self.assertEqual(tuple(cases.column(samples, "id")), _TWO_STEP_IDS)
        first, second = cases.column(samples, cases.RAW)
        self.assertEqual(first, second)

    def test_earlier_usage_is_only_provisional(self) -> None:
        early = stream.step(1, state=agy_events.ACTIVE, usage={_INPUT: 1000})
        settled = cases.collected(early, _usage_step(1)).samples[0]
        self.assertEqual(cases.picked(settled, *_SETTLED), (models.FINAL, "completed-frame"))
        self.assertEqual(settled[cases.RAW][_INPUT], _INPUT_COUNT)
        early = _usage_step(1, state=agy_events.ACTIVE)
        provisional = cases.collected(_INIT, early, stream.step(1), _TERMINAL)
        settlement = cases.picked(provisional.samples[0], *_SETTLED)
        self.assertEqual(settlement, (models.PROVISIONAL, "pre-completion-frame"))
        self.assertEqual(provisional.reasons, {coverage.PROVISIONAL_USAGE: 1})

    def test_completed_frames_disagreeing_conflict(self) -> None:
        disagreeing = stream.step(1, usage={_INPUT: _INPUT_COUNT + 1})
        collection = cases.collected(_usage_step(1), disagreeing, _TERMINAL)
        sample = collection.samples[0]
        self.assertNotIn(_INPUT, sample[cases.RAW])
        self.assertEqual(sample[cases.EVIDENCE][_CONTEXT], normalization.CONFLICTING)
        self.assertEqual(sample[_OUTPUT], _OUTPUT_COUNT)
        self.assertEqual(collection.reasons[coverage.CONFLICTING_COUNTERS], 1)
