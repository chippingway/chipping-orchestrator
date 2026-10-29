# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which token counters a run evidences, how its cache counters relate to its input, and the total they establish."""

import json
import unittest
from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.observability.usage import (
    metrics as _metrics,
    protocol as _protocol,
    token_evidence as _tokens,
    trajectory as _trajectory,
)
from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_claude_subagent_events as _subagent,
    usage_codex_events as _codex,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)
from tests.support import agy_stream as _agy

_INPUT = _protocol.INPUT_TOKENS
_OUTPUT = _protocol.OUTPUT_TOKENS
_CACHED = _protocol.CACHED_TOKENS
_CACHE_READ = _protocol.CACHE_READ_TOKENS
_CACHE_WRITE = _protocol.CACHE_WRITE_TOKENS
_INPUT_COUNT = 10
_OUTPUT_COUNT = 5
_CACHE_READ_COUNT = 30
_CACHE_WRITE_COUNT = 40
_CACHED_COUNT = 7
_HANDBACK_OUTPUT = _usage_cases.TOKEN_COUNT_TWENTY
_LEAD_OUTPUT = _usage_cases.TOKEN_COUNT_FIFTY


@dataclass(frozen=True)
class _Case:
    """One run's stream, the token evidence it serializes, its raw counters, and the total they establish."""

    name: str
    backend: str
    stdout: str
    evidence: dict
    raw: tuple
    total: int | None


def _evidence(cache_overlap: str, *observed: str) -> dict:
    return {_tokens.OBSERVED: list(observed), _tokens.CACHE_OVERLAP: cache_overlap}


def _counts(**raw: int) -> dict:
    return {_INPUT: _INPUT_COUNT, _OUTPUT: _OUTPUT_COUNT, _CACHED: 0, _CACHE_READ: 0, _CACHE_WRITE: 0, **raw}


def _claude_stdout(**cache: int) -> str:
    usage = _claude.usage(input=_INPUT_COUNT, output=_OUTPUT_COUNT, **cache)
    return _jsonl.jsonl(_claude.assistant(model=_usage_cases.SONNET, usage=usage))


def _codex_usage(**fields: int) -> dict:
    return {_usage_cases.TYPE_FIELD: "turn.completed", _usage_cases.MODEL_FIELD: _usage_cases.GPT_FIVE_MINI, **fields}


_CODEX_FINAL = _codex.turn_complete(
    model=_usage_cases.GPT_FIVE_MINI,
    input=_usage_cases.CODEX_FINAL_INPUT_TOKENS,
    cached=_usage_cases.CODEX_FINAL_CACHED_TOKENS,
    output=_usage_cases.CODEX_FINAL_OUTPUT_TOKENS,
)
_CODEX_FINAL_RAW = (
    _usage_cases.CODEX_FINAL_INPUT_TOKENS,
    _usage_cases.CODEX_FINAL_OUTPUT_TOKENS,
    _usage_cases.CODEX_FINAL_CACHED_TOKENS,
    0,
    0,
)
_CODEX_FINAL_TOTAL = _usage_cases.CODEX_FINAL_INPUT_TOKENS + _usage_cases.CODEX_FINAL_OUTPUT_TOKENS
_UNCACHED = MappingProxyType({_INPUT: _INPUT_COUNT, _OUTPUT: _OUTPUT_COUNT})
_CLAUDE_COUNTERS = (_INPUT, _OUTPUT, _CACHE_READ, _CACHE_WRITE)
_CODEX_COUNTERS = (_INPUT, _OUTPUT, _CACHED)
_AGY_COUNTERS = (_INPUT, _OUTPUT, _CACHE_READ)
_UNCACHED_RAW = (_INPUT_COUNT, _OUTPUT_COUNT, 0, 0, 0)
_UNCACHED_TOTAL = _INPUT_COUNT + _OUTPUT_COUNT

_RUN_CASES = (
    _Case(
        "claude counts each cache class beside its input",
        _usage_cases.CLAUDE,
        _claude_stdout(cache_read=_CACHE_READ_COUNT, cache_write=_CACHE_WRITE_COUNT),
        _evidence(_tokens.DISJOINT, *_CLAUDE_COUNTERS),
        (_INPUT_COUNT, _OUTPUT_COUNT, 0, _CACHE_READ_COUNT, _CACHE_WRITE_COUNT),
        _UNCACHED_TOTAL + _CACHE_READ_COUNT + _CACHE_WRITE_COUNT,
    ),
    _Case(
        "claude reporting zero cache counts observes them",
        _usage_cases.CLAUDE,
        _claude_stdout(cache_read=0, cache_write=0),
        _evidence(_tokens.DISJOINT, *_CLAUDE_COUNTERS),
        _UNCACHED_RAW,
        _UNCACHED_TOTAL,
    ),
    _Case(
        "claude omitting cache counts observes none",
        _usage_cases.CLAUDE,
        _claude_stdout(),
        _evidence(_tokens.DISJOINT, _INPUT, _OUTPUT),
        _UNCACHED_RAW,
        _UNCACHED_TOTAL,
    ),
    _Case(
        "codex counts its cached input inside its input",
        _usage_cases.CODEX,
        _jsonl.jsonl(_CODEX_FINAL),
        _evidence(_tokens.WITHIN_INPUT, *_CODEX_COUNTERS),
        _CODEX_FINAL_RAW,
        _CODEX_FINAL_TOTAL,
    ),
    _Case(
        "codex omitting cached input observes none",
        _usage_cases.CODEX,
        _jsonl.jsonl(_codex_usage(usage=dict(_UNCACHED))),
        _evidence(_tokens.WITHIN_INPUT, _INPUT, _OUTPUT),
        _UNCACHED_RAW,
        _UNCACHED_TOTAL,
    ),
    _Case(
        "codex reporting only zeros observes them",
        _usage_cases.CODEX,
        _jsonl.jsonl(_codex.turn_complete(model=_usage_cases.GPT_FIVE_MINI)),
        _evidence(_tokens.WITHIN_INPUT, *_CODEX_COUNTERS),
        (0, 0, 0, 0, 0),
        0,
    ),
    _Case(
        "codex reported zeros outlast a later block reporting none",
        _usage_cases.CODEX,
        _jsonl.jsonl(_codex.turn_complete(model=_usage_cases.GPT_FIVE_MINI), _codex.task_complete(usage={})),
        _evidence(_tokens.WITHIN_INPUT, *_CODEX_COUNTERS),
        (0, 0, 0, 0, 0),
        0,
    ),
    _Case(
        "codex observes the record its counts come from",
        _usage_cases.CODEX,
        _jsonl.jsonl(_CODEX_FINAL, _codex_usage(usage={_INPUT: 0})),
        _evidence(_tokens.WITHIN_INPUT, *_CODEX_COUNTERS),
        _CODEX_FINAL_RAW,
        _CODEX_FINAL_TOTAL,
    ),
    _Case(
        "antigravity cache reads of unknown overlap",
        _agy.BACKEND,
        _agy.resumed_stream(),
        _evidence(_tokens.UNKNOWN, *_AGY_COUNTERS),
        (_agy.INPUT_TOKENS, _agy.OUTPUT_TOKENS, 0, _agy.CACHE_READ_TOKENS, 0),
        None,
    ),
    _Case(
        "antigravity reporting zero cache reads observes them",
        _agy.BACKEND,
        _agy.step(1, usage={**_UNCACHED, _CACHE_READ: 0}),
        _evidence(_tokens.UNKNOWN, *_AGY_COUNTERS),
        _UNCACHED_RAW,
        _UNCACHED_TOTAL,
    ),
    _Case(
        "antigravity omitting cache reads observes none",
        _agy.BACKEND,
        _agy.step(1, usage=dict(_UNCACHED)),
        _evidence(_tokens.UNKNOWN, _INPUT, _OUTPUT),
        _UNCACHED_RAW,
        _UNCACHED_TOTAL,
    ),
    _Case(
        "a run with no usage observes nothing",
        _usage_cases.CLAUDE,
        "",
        _evidence(_tokens.DISJOINT),
        (0, 0, 0, 0, 0),
        0,
    ),
)

_NOT_CURRENT_EVIDENCE = (
    None,
    _tokens.DISJOINT,
    _evidence("maybe", _INPUT),
    {_tokens.OBSERVED: _INPUT, _tokens.CACHE_OVERLAP: _tokens.DISJOINT},
    _evidence(_tokens.DISJOINT, _INPUT, _INPUT),
    _evidence(_tokens.DISJOINT, "reasoning_tokens"),
    {_tokens.OBSERVED: [[_INPUT]], _tokens.CACHE_OVERLAP: [_tokens.DISJOINT]},
)

_CLAUDE_EVIDENCE = _evidence(_tokens.DISJOINT, *_CLAUDE_COUNTERS)
# A turn record carries no `cached_tokens` key at all.
_TURN_SHAPED_COUNTS = MappingProxyType({
    counter: count for counter, count in _counts().items() if counter != _CACHED
})

# A lead message reporting no output count until a delta closes it, and a
# subagent message whose frame reports none at all.
_LEAD_INPUT_ONLY = _claude.assistant(
    id=_usage_cases.CLAUDE_TURN_ID,
    model=_usage_cases.SONNET,
    usage={_INPUT: _INPUT_COUNT},
)
_LEAD_CLOSED_AT_ZERO = _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=0)
_SUBAGENT_INPUT_ONLY = dict(
    _claude.assistant(id="msg_sub", model=_usage_cases.SONNET, usage={_INPUT: _subagent.SUBAGENT_INPUT_TOKENS}),
    parent_tool_use_id=_usage_cases.TOOL_USE_A_ID,
)
# The input and cache totals `modelUsage` reports for exactly what the stream printed.
_PRINTED_TOTALS = MappingProxyType(
    _subagent.model_totals(input_tokens=_INPUT_COUNT + _subagent.SUBAGENT_INPUT_TOKENS, output_tokens=0),
)
_PRINTED_INPUT_AND_CACHE = MappingProxyType({
    field_name: total for field_name, total in _PRINTED_TOTALS.items() if field_name != "outputTokens"
})
_SETTLED_OUTPUT = 7
_OBSERVED_INPUT = _evidence(_tokens.DISJOINT, _INPUT)
_OBSERVED_INPUT_AND_OUTPUT = _evidence(_tokens.DISJOINT, _INPUT, _OUTPUT)

# Each settlement: its stream, then each turn's token evidence and output count.
_SETTLEMENTS = (
    (
        "modelUsage reporting no output total settles none",
        _jsonl.jsonl(
            _LEAD_INPUT_ONLY,
            _LEAD_CLOSED_AT_ZERO,
            _SUBAGENT_INPUT_ONLY,
            _claude.terminal_result(modelUsage={_usage_cases.SONNET: dict(_PRINTED_INPUT_AND_CACHE)}),
        ),
        [(_OBSERVED_INPUT_AND_OUTPUT, 0), (_OBSERVED_INPUT, 0)],
    ),
    (
        # Every count the stream printed is zero, so an absent total read as
        # zero would pass for coverage.
        "modelUsage reporting no input or cache totals settles none",
        _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.SONNET,
                usage={_INPUT: 0, _OUTPUT: 0},
            ),
            _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=1),
            dict(
                _claude.assistant(id="msg_sub", model=_usage_cases.SONNET, usage={_OUTPUT: 1}),
                parent_tool_use_id=_usage_cases.TOOL_USE_A_ID,
            ),
            _claude.terminal_result(modelUsage={_usage_cases.SONNET: {"outputTokens": _SETTLED_OUTPUT}}),
        ),
        [(_OBSERVED_INPUT_AND_OUTPUT, 1), (_evidence(_tokens.DISJOINT, _OUTPUT), 1)],
    ),
    (
        "modelUsage reporting an output total settles it",
        _jsonl.jsonl(
            _LEAD_INPUT_ONLY,
            _LEAD_CLOSED_AT_ZERO,
            _SUBAGENT_INPUT_ONLY,
            _claude.terminal_result(
                modelUsage={_usage_cases.SONNET: {**_PRINTED_TOTALS, "outputTokens": _SETTLED_OUTPUT}},
            ),
        ),
        [(_OBSERVED_INPUT_AND_OUTPUT, 0), (_OBSERVED_INPUT_AND_OUTPUT, _SETTLED_OUTPUT)],
    ),
    (
        "a subagent on another model settles nothing unreported",
        _jsonl.jsonl(
            _LEAD_INPUT_ONLY,
            _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=_OUTPUT_COUNT),
            {**_SUBAGENT_INPUT_ONLY, "message": {**_SUBAGENT_INPUT_ONLY["message"], "model": _usage_cases.HAIKU}},
            _claude.terminal_result(modelUsage={_usage_cases.HAIKU: {"inputTokens": _subagent.SUBAGENT_INPUT_TOKENS}}),
        ),
        [(_OBSERVED_INPUT_AND_OUTPUT, _OUTPUT_COUNT), (_OBSERVED_INPUT, 0)],
    ),
    (
        "a delta reporting no count closes nothing",
        _jsonl.jsonl(_LEAD_INPUT_ONLY, _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens="n/a")),
        [(_OBSERVED_INPUT, 0)],
    ),
)

# A cache count is left out of a total only where it sits inside an observed input count.
_CACHE_TOTALS = (
    ({_CACHED: _CACHED_COUNT}, _tokens.WITHIN_INPUT, _CACHED_COUNT),
    ({_INPUT: _INPUT_COUNT, _CACHED: _CACHED_COUNT}, _tokens.WITHIN_INPUT, _INPUT_COUNT),
    ({_CACHE_READ: _CACHED_COUNT}, _tokens.UNKNOWN, _CACHED_COUNT),
    ({_INPUT: _INPUT_COUNT, _CACHE_READ: _CACHED_COUNT}, _tokens.UNKNOWN, None),
    ({_INPUT: _INPUT_COUNT, _CACHE_READ: _CACHED_COUNT}, _tokens.DISJOINT, _INPUT_COUNT + _CACHED_COUNT),
)

# Three messages: a lead one reporting no cache counts, closed by its delta;
# one reporting zero cache counts; and a subagent's, known only by its
# hand-back, which prints its output count alone.
_TURNS_STDOUT = _jsonl.jsonl(
    _subagent.lead_assistant(_usage_cases.SONNET),
    _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=_LEAD_OUTPUT),
    _claude.assistant(
        id="msg_zero_cache",
        model=_usage_cases.SONNET,
        usage=_claude.usage(input=_INPUT_COUNT, output=_OUTPUT_COUNT, cache_read=0, cache_write=0),
    ),
    _subagent.handback(_usage_cases.TOOL_USE_A_ID, _usage_cases.SONNET, output=_HANDBACK_OUTPUT),
)


class RunTokenEvidenceTest(unittest.TestCase):
    """What each parser states about a run's counters, beside the raw counters it keeps as reported."""

    def test_each_run_states_its_counters_and_overlap(self) -> None:
        for case in _RUN_CASES:
            with self.subTest(case.name):
                metrics = _metrics.parse_agent_usage(case.backend, case.stdout)
                serialized = json.loads(json.dumps(metrics.to_dict()))
                raw_counts = tuple(serialized[counter] for counter in _tokens.COUNTERS)
                self.assertEqual(serialized[_tokens.TOKEN_EVIDENCE], case.evidence)
                self.assertEqual(raw_counts, case.raw)
                self.assertEqual(_tokens.non_overlapping_total(serialized), case.total)
                self.assertEqual(
                    _tokens.TokenEvidence.from_dict(serialized[_tokens.TOKEN_EVIDENCE]),
                    metrics.token_evidence,
                )

    def test_each_turn_observes_its_own_row(self) -> None:
        # A run observes a counter once any row it sums reported it, and each
        # turn what its own row reported: the zeros a hand-back turn carries for
        # input and cache are no evidence of zero.
        turns = [turn.to_dict() for turn in _trajectory.parse_claude_trajectory(_TURNS_STDOUT).turns]
        run = _metrics.parse_claude_usage(_TURNS_STDOUT).to_dict()
        self.assertEqual(
            [turn[_tokens.TOKEN_EVIDENCE] for turn in turns],
            [
                _evidence(_tokens.DISJOINT, _INPUT, _OUTPUT),
                _CLAUDE_EVIDENCE,
                _evidence(_tokens.DISJOINT, _OUTPUT),
            ],
        )
        handback = turns[-1]
        self.assertEqual((handback[_INPUT], handback[_CACHE_READ]), (0, 0))
        self.assertEqual(run[_tokens.TOKEN_EVIDENCE], _CLAUDE_EVIDENCE)
        turn_totals = [_tokens.non_overlapping_total(turn) for turn in turns]
        self.assertEqual(turn_totals[-1], _HANDBACK_OUTPUT)
        self.assertEqual(_tokens.non_overlapping_total(run), sum(turn_totals))


    def test_settlement_observes_only_reported_output(self) -> None:
        # Settling an open subagent message from `modelUsage` observes its
        # output only where `modelUsage` reports an output total for its model.
        for name, stdout, expected in _SETTLEMENTS:
            with self.subTest(name):
                turns = [turn.to_dict() for turn in _trajectory.parse_claude_trajectory(stdout).turns]
                settled = [(turn[_tokens.TOKEN_EVIDENCE], turn[_OUTPUT]) for turn in turns]
                self.assertEqual(settled, expected)


class RecordedTokenTotalTest(unittest.TestCase):
    """A record stating no current evidence totals only where no cache counter could overlap its input."""

    def test_unstated_evidence_totals_only_uncached(self) -> None:
        # A record stating no evidence is read with the counters it holds.
        for evidence in ({}, *({_tokens.TOKEN_EVIDENCE: stated} for stated in _NOT_CURRENT_EVIDENCE)):
            with self.subTest(evidence=evidence):
                for uncached in (_counts(), _TURN_SHAPED_COUNTS):
                    self.assertEqual(_tokens.non_overlapping_total({**uncached, **evidence}), _UNCACHED_TOTAL)
                cached = {**_counts(**{_CACHE_READ: _CACHE_READ_COUNT}), **evidence}
                self.assertIsNone(_tokens.non_overlapping_total(cached))

    def test_cache_counts_once_beside_observed_input(self) -> None:
        for counts, cache_overlap, total in _CACHE_TOTALS:
            with self.subTest(counts=counts, cache_overlap=cache_overlap):
                record = {**counts, _tokens.TOKEN_EVIDENCE: _evidence(cache_overlap, *counts)}
                self.assertEqual(_tokens.non_overlapping_total(record), total)

    def test_malformed_observed_count_has_no_total(self) -> None:
        for input_count in (None, str(_INPUT_COUNT), -1, True):
            with self.subTest(input_count=input_count):
                record = {**_counts(), _INPUT: input_count, _tokens.TOKEN_EVIDENCE: _CLAUDE_EVIDENCE}
                self.assertIsNone(_tokens.non_overlapping_total(record))
