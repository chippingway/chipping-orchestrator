# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The Claude Code 2.1.295 captures read request by request, each reconciled only with totals of its own scope."""

import unittest
from collections import Counter
from operator import itemgetter
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import (
    metrics,
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
    trajectory,
)
from tests.observability.usage import usage_claude_stream_capture as capture, usage_request_cases as cases

_INPUT = "input_tokens"
_OUTPUT = normalization.OUTPUT_TOKENS
_RAW_COUNTERS = (_INPUT, "cache_read_input_tokens", "cache_creation_input_tokens")
_RESULT_TOTAL = "result-total"
_MODEL_TOTAL = "model-usage"
_KIND = "kind"
_CHECKPOINT_RAW = MappingProxyType({
    _RESULT_TOTAL: (*_RAW_COUNTERS, _OUTPUT),
    _MODEL_TOTAL: ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens"),
})
_SETTLED = ("id", _OUTPUT, normalization.REASONING_TOKENS, cases.STATUS, "settlement")
_MAIN_SETTLED = tuple(
    (message.message_id, message.final_output_tokens, thinking, models.FINAL, "message-delta")
    for message, thinking in zip(capture.MAIN_RUN_MESSAGES, capture.MAIN_RUN_THINKING, strict=True)
)
_FIRST = capture.MAIN_RUN_MESSAGES[0].start
_FIRST_PROMPT = (
    _FIRST.input_tokens + _FIRST.cache_read_tokens + _FIRST.cache_write_tokens,
    MappingProxyType({"cache_write_5m": 0, "cache_write_1h": _FIRST.cache_write_tokens}),
)
_FIRST_IDENTITY = ("api-message", capture.MAIN_RUN_SESSION, "req_main_0", capture.MODEL, models.STREAM_MODEL)
_FIRST_SOURCE = (capture.CLI_VERSION, capture.CONTEXT_WINDOW, models.REQUEST_SCOPE)
# What the subagent run's sample prompts fall short of its model total by: the closing message's prompt.
_HANDBACK = capture.SUBAGENT_RUN_HANDBACK
_UNOBSERVED = (_HANDBACK.input_tokens, _HANDBACK.cache_read_tokens, _HANDBACK.cache_write_tokens)
_RUNS = (("main", capture.MAIN_RUN_STDOUT), ("subagent", capture.SUBAGENT_RUN_STDOUT))
# The subagent capture with its subagent message's counts spelled as a whole float, with an exponent, and as a zero
# with an exponent -- its cache writes in aggregate, or split by lifetime alone: the same counts to the run accounting,
# which decodes every one of them as a float.
_INTEGER_SPELLED = '"usage":{"input_tokens":2,"cache_creation_input_tokens":14561,"cache_read_input_tokens":0,'
_FLOAT_SPELLED = '"usage":{"input_tokens":2.0,"cache_creation_input_tokens":1.4561e4,"cache_read_input_tokens":0E0,'
_SPLIT_ALONE = '"usage":{"input_tokens":2.0,"cache_read_input_tokens":0E0,'
_INTEGER_SPLIT = '"cache_creation":{"ephemeral_5m_input_tokens":14561,"ephemeral_1h_input_tokens":0}'
_FLOAT_SPLIT = '"cache_creation":{"ephemeral_5m_input_tokens":1.4561e4,"ephemeral_1h_input_tokens":0.0}'
_UNSPLIT = capture.SUBAGENT_RUN_STDOUT.replace(_INTEGER_SPLIT, _FLOAT_SPLIT)
_RESPELLINGS = (
    ("an aggregate beside its split", capture.SUBAGENT_RUN_STDOUT.replace(_INTEGER_SPELLED, _FLOAT_SPELLED)),
    ("a lifetime split alone", _UNSPLIT.replace(_INTEGER_SPELLED, _SPLIT_ALONE)),
)
_SUBAGENT = capture.SUBAGENT_RUN_SUBAGENT_MESSAGES[0]
_SUBAGENT_SETTLED = (_SUBAGENT.message_id, "model-usage", _SUBAGENT.final_output_tokens)
_SETTLED_FIELDS = ("message_id", "settlement", _OUTPUT)
_MODEL_SHORTFALL = (*_UNOBSERVED, 0)

Outputs = dict[int, int]


def _captured(stdout: str) -> cases.Collected:
    return cases.collected(stdout, backend=protocol.CLAUDE)


def _sums(samples: list[dict[str, Any]]) -> tuple[int, ...]:
    """Each prompt counter as reported, then each settled output, added up over `samples`; none observed is none."""
    summed: Counter[str] = Counter()
    for sample in samples:
        summed.update(sample[cases.RAW])
    outputs = sum(settled[_OUTPUT] for settled in samples)
    return (*itemgetter(*_RAW_COUNTERS)(summed), outputs)


def _checkpoint_sums(collection: cases.Collected) -> dict[str, tuple[int, ...]]:
    """Each checkpoint's input, cache-read, cache-write, and output counts, keyed by its kind."""
    sums = {}
    for checkpoint in collection.checkpoints:
        kind = checkpoint[_KIND]
        raw = checkpoint[cases.RAW]
        sums[kind] = tuple(raw[name] for name in _CHECKPOINT_RAW[kind])
    return sums


def _shortfall(
    totals: tuple[int, ...],
    samples: list[dict[str, Any]],
) -> tuple[int, ...]:
    """What `samples` fall short of `totals` by, counter by counter."""
    pairs = zip(totals, _sums(samples), strict=True)
    return tuple(total - count for total, count in pairs)


def _run_counts(stdout: str) -> tuple[int, ...]:
    run = metrics.parse_claude_usage(stdout)
    return run.input_tokens, run.cache_read_tokens, run.cache_write_tokens, run.output_tokens


def _turn_outputs(stdout: str) -> tuple[Outputs, Outputs]:
    """Each sample's settled output by the trajectory turn it links, and each trajectory turn's own output."""
    linked = {sample["trajectory_turn"]: sample[_OUTPUT] for sample in _captured(stdout).samples}
    turns = trajectory.parse_claude_trajectory(stdout).turns
    return linked, {turn.turn: turn.output_tokens for turn in turns}


class CapturedRunTest(unittest.TestCase):
    """Each captured API message is one request, settled by the report the run accounting settles it by."""

    def test_complete_run_reconciles_in_scope(self) -> None:
        # The main run spawns no subagent, so its lead-thread total and its one model's total cover exactly its
        # samples, and the run accounting counts the same messages.
        collection = _captured(capture.MAIN_RUN_STDOUT)
        sums = _sums(collection.samples)
        self.assertEqual(collection.status, coverage.COMPLETE)
        self.assertEqual(sums, _run_counts(capture.MAIN_RUN_STDOUT))
        self.assertEqual(_checkpoint_sums(collection), {_RESULT_TOTAL: sums, _MODEL_TOTAL: sums})
        settled = tuple(cases.picked(sample, *_SETTLED) for sample in collection.samples)
        self.assertEqual(settled, _MAIN_SETTLED)

    def test_captured_metadata_rides_every_sample(self) -> None:
        # The context input is every class once: ordinary input, cache reads, and cache writes.
        sample = _captured(capture.MAIN_RUN_STDOUT).samples[0]
        identity = cases.picked(sample, "id_kind", "session_id", "request_id", cases.MODEL, cases.MODEL_SOURCE)
        self.assertEqual(identity, _FIRST_IDENTITY)
        self.assertEqual(cases.picked(sample, "source_version", "context_capacity", "scope"), _FIRST_SOURCE)
        context, lifetimes = _FIRST_PROMPT
        self.assertEqual(sample[normalization.CONTEXT_INPUT_TOKENS], context)
        self.assertEqual(sample[normalization.CACHE_WRITE_LIFETIMES], dict(lifetimes))

    def test_subagent_run_reconciles_its_lead(self) -> None:
        # The lead thread's samples close the lead-thread total. The subagent's coverage is partial -- its closing
        # message is seen by its output alone -- so the samples are never forced to match `modelUsage`: every output
        # is observed, and what the prompts fall short of it by is exactly that message's.
        collection = _captured(capture.SUBAGENT_RUN_STDOUT)
        lead = [sample for sample in collection.samples if "parent_tool_use_id" not in sample]
        totals = _checkpoint_sums(collection)
        self.assertEqual(totals[_RESULT_TOTAL], _sums(lead))
        self.assertEqual(collection.reasons, {coverage.OUTPUT_ONLY_OBSERVATIONS: 1})
        self.assertEqual(_shortfall(totals[_MODEL_TOTAL], collection.samples), _MODEL_SHORTFALL)

    def test_whole_counts_settle_however_spelled(self) -> None:
        # The subagent's message settles through `modelUsage` as it does with its counts spelled as integers, and
        # every sample still holds the output of the turn it links.
        for name, respelled in _RESPELLINGS:
            with self.subTest(name):
                self.assertNotEqual(respelled, capture.SUBAGENT_RUN_STDOUT)
                settled = [cases.picked(sample, *_SETTLED_FIELDS) for sample in _captured(respelled).samples]
                self.assertIn(_SUBAGENT_SETTLED, settled)
                self.assertEqual(*_turn_outputs(respelled))

    def test_turn_links_are_the_trajectory_turns(self) -> None:
        # Each sample names the turn the trajectory's own turns number it under, and holds that turn's settled output.
        for name, stdout in _RUNS:
            with self.subTest(name):
                linked, turns = _turn_outputs(stdout)
                self.assertEqual(linked, turns)
