# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The basis and completeness every usage cost is recorded with, how a record is read back, and the fold over many."""

import json
import math
import sys
import unittest
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from orchestrator.observability.usage import cost_evidence as _cost, metrics as _metrics
from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_codex_events as _codex,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)
from tests.support import agy_stream as _agy

_COST_SOURCE = "cost_source"
_VERIFIED_ON = "2026-10-29"
_LATER_VERIFIED_ON = "2026-11-30"
_MILLION_TOKENS = 1_000_000
# A million input tokens at Claude Sonnet 4.6's and GPT-5 mini's API input rates.
_SONNET_MILLION_INPUT_USD = 3.0
_GPT_FIVE_MINI_MILLION_INPUT_USD = 0.25
_RECORDED_USD = 1.5
# An integer no float holds: twice the largest finite float.
_UNREPRESENTABLE_USD = int(sys.float_info.max) * 2
_HALF_USD = 0.5
_TWO_USD = 2.0
_UNKNOWN_SOURCE = "unknown"


def _evidence(completeness: str, *contributions: dict) -> dict:
    return {_cost.COMPLETENESS: completeness, _cost.CONTRIBUTIONS: list(contributions)}


def _contribution(basis: str, amount_usd: object, *verified_on: str) -> dict:
    return {_cost.BASIS: basis, _cost.AMOUNT_USD: amount_usd, _cost.RATES_VERIFIED_ON: list(verified_on)}


def _complete(basis: str, amount_usd: float, *verified_on: str) -> _cost.CostEvidence:
    verified = tuple(date.fromisoformat(day) for day in verified_on)
    return _cost.CostEvidence(_cost.COMPLETE, (_cost.CostContribution(basis, amount_usd, verified),))


@dataclass(frozen=True)
class _Case:
    """One run's stream, the evidence it serializes, and the `cost_usd` / `cost_source` pair beside it."""

    name: str
    backend: str
    stdout: str
    evidence: dict
    legacy: tuple


_SONNET_MILLION_INPUT = _claude.assistant(model=_usage_cases.SONNET, usage=_claude.usage(input=_MILLION_TOKENS))
_GPT_FIVE_MINI_MILLION_INPUT = _codex.turn_complete(model=_usage_cases.GPT_FIVE_MINI, input=_MILLION_TOKENS)
_DORMANT_MODEL_INPUT = _claude.assistant(model=_usage_cases.OPUS_FOUR_EIGHT, usage=_claude.usage(input=1))
_INCOMPLETE = _evidence(_cost.INCOMPLETE)
_NO_USAGE = _evidence(_cost.NO_USAGE)
_UNPRICED = (None, _usage_cases.UNKNOWN_COST_SOURCE)
_NOTHING_TO_PRICE = (None, _cost.NO_USAGE_SOURCE)

_RUN_CASES = (
    _Case(
        "a reported zero wins over a priced estimate",
        _usage_cases.CLAUDE,
        _jsonl.jsonl(_SONNET_MILLION_INPUT, _claude.terminal_result(total_cost_usd=0)),
        _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, 0)),
        (0, _usage_cases.REPORTED_COST_SOURCE),
    ),
    _Case(
        "claude estimate",
        _usage_cases.CLAUDE,
        _jsonl.jsonl(_SONNET_MILLION_INPUT),
        _evidence(_cost.COMPLETE, _contribution(_cost.ANTHROPIC_API_ESTIMATE, _SONNET_MILLION_INPUT_USD, _VERIFIED_ON)),
        (_SONNET_MILLION_INPUT_USD, _usage_cases.ESTIMATED_COST_SOURCE),
    ),
    _Case(
        "claude on a dormant row",
        _usage_cases.CLAUDE,
        _jsonl.jsonl(_DORMANT_MODEL_INPUT),
        _INCOMPLETE,
        _UNPRICED,
    ),
    _Case("claude with no usage", _usage_cases.CLAUDE, "", _NO_USAGE, _NOTHING_TO_PRICE),
    _Case(
        "codex estimate",
        _usage_cases.CODEX,
        _jsonl.jsonl(_GPT_FIVE_MINI_MILLION_INPUT),
        _evidence(
            _cost.COMPLETE,
            _contribution(_cost.OPENAI_API_ESTIMATE, _GPT_FIVE_MINI_MILLION_INPUT_USD, _VERIFIED_ON),
        ),
        (_GPT_FIVE_MINI_MILLION_INPUT_USD, _usage_cases.ESTIMATED_COST_SOURCE),
    ),
    _Case(
        "codex reported",
        _usage_cases.CODEX,
        _jsonl.jsonl(
            _GPT_FIVE_MINI_MILLION_INPUT,
            _codex.task_complete(total_cost_usd=_usage_cases.CODEX_REPORTED_COST_USD),
        ),
        _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, _usage_cases.CODEX_REPORTED_COST_USD)),
        (_usage_cases.CODEX_REPORTED_COST_USD, _usage_cases.REPORTED_COST_SOURCE),
    ),
    _Case(
        "codex reporting only zeros has nothing to price",
        _usage_cases.CODEX,
        _jsonl.jsonl(_codex.turn_complete(model=_usage_cases.GPT_FIVE_MINI)),
        _NO_USAGE,
        _NOTHING_TO_PRICE,
    ),
    _Case("antigravity usage", _agy.BACKEND, _agy.resumed_stream(), _INCOMPLETE, _UNPRICED),
    _Case("antigravity with no usage", _agy.BACKEND, "", _NO_USAGE, _NOTHING_TO_PRICE),
)

# What a record an earlier producer wrote looks like: an amount and a tag, and no evidence beside them.
_HISTORICAL_RECORD = MappingProxyType({_cost.COST_USD: _RECORDED_USD, _COST_SOURCE: _usage_cases.ESTIMATED_COST_SOURCE})

_NOT_CURRENT_EVIDENCE = (
    None,
    _cost.COMPLETE,
    _evidence("partial"),
    {_cost.COMPLETENESS: _cost.COMPLETE, _cost.CONTRIBUTIONS: _cost.CLI_REPORTED},
    _evidence(_cost.COMPLETE),
    _evidence(_cost.NO_USAGE, _contribution(_cost.CLI_REPORTED, 0)),
    _evidence(_cost.COMPLETE, _contribution(_cost.UNKNOWN_BASIS, _RECORDED_USD)),
    _evidence(_cost.COMPLETE, _contribution("subscription", _RECORDED_USD)),
    _evidence(_cost.COMPLETE, _contribution([_cost.CLI_REPORTED], _RECORDED_USD)),
    _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, True)),
    _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, math.nan)),
    _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, str(_RECORDED_USD))),
    _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, -_HALF_USD)),
    _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, _UNREPRESENTABLE_USD)),
    _evidence(_cost.COMPLETE, _contribution(_cost.ANTHROPIC_API_ESTIMATE, _RECORDED_USD, "2026-13-01")),
    _evidence(_cost.COMPLETE, {_cost.BASIS: _cost.CLI_REPORTED, _cost.AMOUNT_USD: _RECORDED_USD}),
    _evidence(
        _cost.COMPLETE,
        _contribution(_cost.CLI_REPORTED, _TWO_USD),
        _contribution(_cost.CLI_REPORTED, _HALF_USD),
    ),
)

_ANTHROPIC = _complete(_cost.ANTHROPIC_API_ESTIMATE, 1, _VERIFIED_ON)
_REPORTED_ZERO = _complete(_cost.CLI_REPORTED, 0)
_HISTORICAL = _cost.recorded_cost(_HISTORICAL_RECORD)
_UNPRICED_RUN = _cost.CostEvidence(_cost.INCOMPLETE)
_NO_USAGE_RUN = _cost.CostEvidence(_cost.NO_USAGE)

# A CLI-reported amount a record states, what it reads back as, and the complete total it leaves beside a reported $1.
_STATED_AMOUNTS = (
    (-_HALF_USD, _cost.CostEvidence(_cost.UNKNOWN), None),
    (_UNREPRESENTABLE_USD, _cost.CostEvidence(_cost.UNKNOWN), None),
    (0, _REPORTED_ZERO, 1),
)
_REPORTED_ONE = _complete(_cost.CLI_REPORTED, 1)

# Each fold: its inputs, what they reduce to, and the reduced (total, complete total, basis).
_FOLDS = (
    ((), _NO_USAGE_RUN, (None, None, None)),
    ((_NO_USAGE_RUN, _REPORTED_ZERO), _REPORTED_ZERO, (0, 0, _cost.CLI_REPORTED)),
    (
        (_ANTHROPIC, _NO_USAGE_RUN, _complete(_cost.ANTHROPIC_API_ESTIMATE, _TWO_USD, _LATER_VERIFIED_ON)),
        _complete(_cost.ANTHROPIC_API_ESTIMATE, 1 + _TWO_USD, _VERIFIED_ON, _LATER_VERIFIED_ON),
        (1 + _TWO_USD, 1 + _TWO_USD, _cost.ANTHROPIC_API_ESTIMATE),
    ),
    (
        (_complete(_cost.GEMINI_API_ESTIMATE, _HALF_USD, _VERIFIED_ON), _REPORTED_ZERO, _ANTHROPIC),
        _cost.CostEvidence(
            _cost.COMPLETE,
            (
                *_ANTHROPIC.contributions,
                *_REPORTED_ZERO.contributions,
                _cost.CostContribution(_cost.GEMINI_API_ESTIMATE, _HALF_USD, (date.fromisoformat(_VERIFIED_ON),)),
            ),
        ),
        (_RECORDED_USD, _RECORDED_USD, _cost.BLENDED),
    ),
    (
        (_ANTHROPIC, _UNPRICED_RUN),
        _cost.CostEvidence(_cost.INCOMPLETE, _ANTHROPIC.contributions),
        (1, None, _cost.ANTHROPIC_API_ESTIMATE),
    ),
    (
        (_ANTHROPIC, _HISTORICAL),
        _cost.CostEvidence(_cost.UNKNOWN, (*_ANTHROPIC.contributions, *_HISTORICAL.contributions)),
        (1 + _RECORDED_USD, None, _cost.BLENDED),
    ),
    (
        (_HISTORICAL, _UNPRICED_RUN, _ANTHROPIC),
        _cost.CostEvidence(_cost.INCOMPLETE, (*_ANTHROPIC.contributions, *_HISTORICAL.contributions)),
        (1 + _RECORDED_USD, None, _cost.BLENDED),
    ),
)


class RunCostEvidenceTest(unittest.TestCase):
    """What each parser states about a run's cost, serialized and read back."""

    def test_each_run_states_basis_and_completeness(self) -> None:
        for case in _RUN_CASES:
            with self.subTest(case.name):
                metrics = _metrics.parse_agent_usage(case.backend, case.stdout)
                serialized = json.loads(json.dumps(metrics.to_dict()))
                self.assertEqual(serialized[_cost.COST_EVIDENCE], case.evidence)
                self.assertEqual((serialized[_cost.COST_USD], serialized[_COST_SOURCE]), case.legacy)
                self.assertEqual(_cost.recorded_cost(serialized), metrics.cost_evidence)


class RecordedCostTest(unittest.TestCase):
    """A record stating no current evidence keeps its amount under an unknown basis, inferring nothing."""

    def test_unstated_evidence_reads_unknown_basis(self) -> None:
        records = (
            _HISTORICAL_RECORD,
            *({**_HISTORICAL_RECORD, _cost.COST_EVIDENCE: evidence} for evidence in _NOT_CURRENT_EVIDENCE),
        )
        for record in records:
            with self.subTest(record=record):
                cost = _cost.recorded_cost(record)
                self.assertEqual(cost, _HISTORICAL)
                self.assertEqual((cost.basis, cost.complete_usd), (_cost.UNKNOWN_BASIS, None))
                self.assertEqual(cost.cost_source, _UNKNOWN_SOURCE)
        self.assertEqual(
            _HISTORICAL.contributions,
            (_cost.CostContribution(_cost.UNKNOWN_BASIS, _RECORDED_USD),),
        )

    def test_records_without_an_amount_state_none(self) -> None:
        for recorded_usd in (None, True, str(_RECORDED_USD), -_HALF_USD, _UNREPRESENTABLE_USD, math.inf):
            with self.subTest(recorded_usd=recorded_usd):
                record = {_cost.COST_USD: recorded_usd, _COST_SOURCE: _usage_cases.UNKNOWN_COST_SOURCE}
                cost = _cost.recorded_cost(record)
                self.assertEqual(cost, _cost.CostEvidence(_cost.UNKNOWN))
                self.assertIsNone(cost.total_usd)


    def test_invalid_amounts_contribute_nothing(self) -> None:
        # A negative amount, or one no float holds, is no cost: the record
        # reads as stating none and leaves a fold beside it incomplete, while a
        # reported zero stays complete spend of zero.
        for amount, stated, folded_complete in _STATED_AMOUNTS:
            with self.subTest(amount=amount):
                cost = _cost.recorded_cost({
                    _cost.COST_USD: amount,
                    _cost.COST_EVIDENCE: _evidence(_cost.COMPLETE, _contribution(_cost.CLI_REPORTED, amount)),
                })
                self.assertEqual(cost, stated)
                self.assertEqual(_cost.reduce_costs((_REPORTED_ONE, cost)).complete_usd, folded_complete)


class ReduceCostsTest(unittest.TestCase):
    """A fold keeps every basis's amount apart and the weakest completeness any input states."""

    def test_folds_keep_bases_and_weakest_state(self) -> None:
        for costs, reduced, totals in _FOLDS:
            with self.subTest(costs=costs):
                folded = _cost.reduce_costs(costs)
                self.assertEqual(folded, reduced)
                self.assertEqual((folded.total_usd, folded.complete_usd, folded.basis), totals)
                serialized = json.loads(json.dumps(folded.to_dict()))
                self.assertEqual(_cost.CostEvidence.from_dict(serialized), folded)
