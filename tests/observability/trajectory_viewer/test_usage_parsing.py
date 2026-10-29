# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a record's run summary and per-turn rows are read back as."""
from __future__ import annotations

import json
import unittest
from typing import Any

from orchestrator.observability.trajectory_viewer import parsing
from orchestrator.observability.usage import (
    cost_evidence as usage_cost,
    metrics as usage_metrics,
    token_evidence as usage_tokens,
    trajectory as usage_trajectory,
)
from tests.observability.analytics.analytics_assertions import assert_row_fields
from tests.observability.analytics.analytics_trajectory_cases import (
    claude_multistep_stdout,
)
from tests.observability.trajectory_viewer import (
    trajectory_viewer_test_support as _support,
)

_KIND = "kind"

_NAME = "name"

_CONTENT_KEY = "content"

_TOOL_ID = "tool_id"

_TURN = "turn"

_MODEL = "model"

_MODELS = "models"

_TURNS = "turns"

_RUN_USAGE = "run_usage"

_INPUT_TOKENS = "input_tokens"

_OUTPUT_TOKENS = "output_tokens"

_CACHED = "cached_tokens"

_CACHE_READ = "cache_read_tokens"

_CACHE_WRITE = "cache_write_tokens"

_COST_USD = "cost_usd"

_COST_SOURCE = "cost_source"

_MODEL_CLAUDE = "claude-opus-4-8"

_REPORTED = "reported"

_ESTIMATED = "estimated"

_UNKNOWN_PRICE = "unknown-price"

_DONE = "done"

_USAGE_INPUT = 12

_USAGE_OUTPUT = 340

_USAGE_CACHE_READ = 18240

_USAGE_CACHE_WRITE = 512

_RUN_COST = 0.83

_TURN0_COST = 0.0123

_CODEX_INPUT = 100

_CODEX_OUTPUT = 50

_CODEX_CACHED = 40

_AGY_COST = 0.02

# A counter the line leaves out altogether.
_ABSENT = object()

_REPORTED_RUN = _support.cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _RUN_COST))

_TURN0_ESTIMATE = _support.cost(
    usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN0_COST),
)


def _usage_record(**overrides: Any) -> dict[str, Any]:
    """A claude line carrying run and per-turn usage plus turn-stamped steps.

    The run's CLI reported its cost, so that amount is the run's; each turn
    states its own API estimate, the second one an unpriced turn.
    """
    written = _support.record(
        user_input="fix the parser",
        output=_DONE,
        run_usage={
            _MODELS: [_MODEL_CLAUDE],
            _TURNS: 2,
            _INPUT_TOKENS: _USAGE_INPUT,
            _OUTPUT_TOKENS: _USAGE_OUTPUT,
            _CACHED: 0,
            _CACHE_READ: _USAGE_CACHE_READ,
            _CACHE_WRITE: _USAGE_CACHE_WRITE,
            _COST_USD: _RUN_COST,
            _COST_SOURCE: _REPORTED,
            usage_cost.COST_EVIDENCE: _REPORTED_RUN.to_dict(),
            usage_tokens.TOKEN_EVIDENCE: _support.CLAUDE_TOKENS.to_dict(),
        },
        turns=[
            {
                _TURN: 0,
                _MODEL: _MODEL_CLAUDE,
                _INPUT_TOKENS: _USAGE_INPUT,
                _OUTPUT_TOKENS: _USAGE_OUTPUT,
                _CACHE_READ: _USAGE_CACHE_READ,
                _CACHE_WRITE: _USAGE_CACHE_WRITE,
                _COST_USD: _TURN0_COST,
                _COST_SOURCE: _ESTIMATED,
                usage_cost.COST_EVIDENCE: _TURN0_ESTIMATE.to_dict(),
                usage_tokens.TOKEN_EVIDENCE: _support.CLAUDE_TOKENS.to_dict(),
            },
            {
                _TURN: 1,
                _MODEL: _MODEL_CLAUDE,
                _INPUT_TOKENS: 5,
                _OUTPUT_TOKENS: 120,
                _CACHE_READ: 900,
                _CACHE_WRITE: 0,
                _COST_USD: None,
                _COST_SOURCE: _UNKNOWN_PRICE,
                usage_cost.COST_EVIDENCE: _support.cost(usage_cost.INCOMPLETE).to_dict(),
                usage_tokens.TOKEN_EVIDENCE: _support.CLAUDE_TOKENS.to_dict(),
            },
        ],
        steps=[
            {_KIND: _support.ASSISTANT_MESSAGE, _TURN: 0, _CONTENT_KEY: "let me look"},
            {_KIND: _support.TOOL_CALL, _NAME: _support.TOOL_EDIT,
             _TOOL_ID: "e1", _TURN: 0, _CONTENT_KEY: "patch"},
            {_KIND: _support.TOOL_RESULT, _TOOL_ID: "e1", _CONTENT_KEY: "ok"},
            {_KIND: _support.ASSISTANT_MESSAGE, _TURN: 1, _CONTENT_KEY: _DONE},
        ],
    )
    written.update(overrides)
    return written


def _written(metrics, turns) -> dict[str, Any]:
    """The line the sink writes for `metrics` and `turns`, through JSON."""
    run_usage = metrics.to_dict()
    run_usage.pop("backend")
    return json.loads(json.dumps(_support.record(
        run_usage=run_usage, turns=[turn.to_dict() for turn in turns],
    )))


def _parsed(written: dict[str, Any]):
    """Parse one line that is a run, as every line here is."""
    run = parsing.parse_record(written, sequence=0)
    assert run is not None
    return run


def _summary_only(backend: str, **run_usage: Any):
    """Parse a line whose run summary is `run_usage` and nothing per turn."""
    parsed = parsing.parse_record(
        _support.record(backend=backend, run_usage=run_usage), sequence=0,
    )
    assert parsed is not None and parsed.run_usage is not None
    return parsed.run_usage


class UsageParsingTest(unittest.TestCase):
    """Run and per-turn usage are read back tolerantly, or not at all."""

    def test_the_whole_summary_is_read_back(self) -> None:
        run = _parsed(_usage_record())
        assert run.run_usage is not None
        assert_row_fields(self, run.run_usage, {
            _MODELS: (_MODEL_CLAUDE,),
            _INPUT_TOKENS: _USAGE_INPUT,
            _TURNS: 2,
            "cost_evidence": _REPORTED_RUN,
            "token_evidence": _support.CLAUDE_TOKENS,
        })
        # Claude's cache classes sit beside its input, so each counts once.
        self.assertEqual(
            run.total_tokens,
            _USAGE_INPUT + _USAGE_OUTPUT + _USAGE_CACHE_READ + _USAGE_CACHE_WRITE,
        )
        # Each turn keeps its own estimate, the unpriced one included, while
        # the run's amount stays the one its CLI reported.
        self.assertEqual(
            [turn.cost_evidence for turn in run.turns],
            [_TURN0_ESTIMATE, _support.cost(usage_cost.INCOMPLETE)],
        )
        self.assertEqual(run.cost_evidence, _REPORTED_RUN)

    def test_a_step_carries_the_turn_it_was_billed_to(self) -> None:
        run = _parsed(_usage_record())
        # A tool result is the provider's input, not a billed turn of its own.
        billed = [step.turn for step in run.steps]
        self.assertEqual(billed, [0, 0, None, 1])

    def test_a_line_written_before_usage_existed(self) -> None:
        run = _parsed(_support.record(steps=[{
            _KIND: _support.TOOL_CALL,
            _NAME: _support.TOOL_EDIT,
            _CONTENT_KEY: "ls",
        }]))
        self.assertIsNone(run.run_usage)
        self.assertEqual(run.turns, ())
        self.assertIsNone(run.steps[0].turn)

    def test_a_pre_evidence_line_stays_unknown(self) -> None:
        # The model is one today's catalogue prices, and the source tag says
        # reported; neither is evidence, so the amount is kept on no basis
        # rather than relabelled or repriced, and a cache count beside an
        # input nothing places it in leaves the total unknown.
        written = _usage_record()
        # The same usage as a build predating its evidence wrote it.
        for usage in (written[_RUN_USAGE], *written[_TURNS]):
            usage.pop(usage_cost.COST_EVIDENCE)
            usage.pop(usage_tokens.TOKEN_EVIDENCE)
        run = _parsed(written)
        assert run.run_usage is not None
        self.assertEqual(run.cost_evidence, _support.cost(
            usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _RUN_COST),
        ))
        self.assertIsNone(run.total_tokens)
        self.assertEqual(
            [turn.cost_evidence for turn in run.turns],
            [
                _support.cost(usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _TURN0_COST)),
                _support.cost(usage_cost.UNKNOWN),
            ],
        )
        self.assertEqual(
            run.run_usage.token_evidence.cache_overlap, usage_tokens.UNKNOWN,
        )

    def test_a_counter_with_no_count_stays_unknown(self) -> None:
        # Absent, null, negative, a bool, or a number spelled as a string:
        # none is a count the usage owner reads, so an observed cache counter
        # holding one leaves the run's and the turn's totals unknown -- the
        # total that owner reads off the same line -- rather than a zero.
        for raw_count in (_ABSENT, None, -1, True, str(_USAGE_CACHE_READ)):
            written = _usage_record()
            for usage in (written[_RUN_USAGE], written[_TURNS][0]):
                usage[_CACHE_READ] = raw_count
                if raw_count is _ABSENT:
                    usage.pop(_CACHE_READ)
            run = _parsed(written)
            assert run.run_usage is not None
            with self.subTest(raw_count=raw_count):
                self.assertEqual(
                    (run.run_usage.cache_read_tokens, run.turns[0].cache_read_tokens),
                    (None, None),
                )
                self.assertEqual(
                    (run.total_tokens, run.turns[0].total_tokens), (None, None),
                )
                self.assertIsNone(
                    usage_tokens.non_overlapping_total(written[_RUN_USAGE]),
                )

    def test_a_malformed_summary_is_narrowed_away(self) -> None:
        run = _parsed(
            _support.record(
                run_usage="oops",
                turns=[
                    "not-a-dict",
                    {
                        _TURN: "bad",
                        _MODEL: _MODEL_CLAUDE,
                        _COST_USD: "free",
                        usage_cost.COST_EVIDENCE: {"completeness": "complete"},
                    },
                ],
                steps=[{_KIND: _support.TOOL_CALL, _NAME: _support.TOOL_EDIT,
                        _TURN: "nope", _CONTENT_KEY: "x"}],
            ),
        )
        self.assertIsNone(run.run_usage)
        self.assertEqual(run.cost_evidence, _support.cost(usage_cost.UNKNOWN))
        # The non-object entry is dropped; the readable one survives with its
        # unreadable fields narrowed away rather than raising, its evidence
        # included: one this format does not serialize states nothing.
        self.assertEqual(len(run.turns), 1)
        surviving = run.turns[0]
        self.assertIsNone(surviving.turn)
        self.assertEqual(surviving.cost_evidence, _support.cost(usage_cost.UNKNOWN))
        self.assertIsNone(run.steps[0].turn)

    def test_a_scalar_where_an_array_belongs(self) -> None:
        # A hand-edited line spelling `"turns": 1` must yield an empty section
        # rather than a TypeError when the parse iterates it.
        run = _parsed(_support.record(turns=1, steps=1))
        self.assertEqual((run.turns, run.steps), ((), ()))


class BackendUsageParsingTest(unittest.TestCase):
    """Each backend's summary reads back on its own basis and token semantics."""

    def test_codex_cached_input_counts_once(self) -> None:
        # Codex records no per-turn breakdown, and its `cached_tokens` is part
        # of its input: the total leaves it out where the evidence says so,
        # and has no answer where nothing does.
        counts = {
            _MODELS: ["gpt-6.1-sol"],
            _INPUT_TOKENS: _CODEX_INPUT,
            _OUTPUT_TOKENS: _CODEX_OUTPUT,
            _CACHED: _CODEX_CACHED,
        }
        stated = _summary_only(
            "codex", **counts,
            **{usage_tokens.TOKEN_EVIDENCE: _support.CODEX_TOKENS.to_dict()},
        )
        self.assertEqual(stated.cached_tokens, _CODEX_CACHED)
        self.assertEqual(stated.total_tokens, _CODEX_INPUT + _CODEX_OUTPUT)
        self.assertIsNone(_summary_only("codex", **counts).total_tokens)

    def test_agy_only_usage_stays_a_gemini_estimate(self) -> None:
        estimate = _support.cost(
            usage_cost.COMPLETE, (usage_cost.GEMINI_API_ESTIMATE, _AGY_COST),
        )
        evidence = {
            usage_cost.COST_EVIDENCE: estimate.to_dict(),
            usage_tokens.TOKEN_EVIDENCE: _support.AGY_TOKENS.to_dict(),
        }
        counted = {_INPUT_TOKENS: _CODEX_INPUT, _OUTPUT_TOKENS: _CODEX_OUTPUT}
        uncached = _summary_only("agy", **counted, **{_CACHE_READ: 0}, **evidence)
        self.assertEqual(uncached.cost_evidence, estimate)
        self.assertEqual(uncached.total_tokens, _CODEX_INPUT + _CODEX_OUTPUT)
        # Nothing establishes whether an AGY cache read sits inside its input.
        cached = _summary_only("agy", **counted, **{_CACHE_READ: 1}, **evidence)
        self.assertIsNone(cached.total_tokens)


class ProducedRecordParsingTest(unittest.TestCase):
    """A record the current producer writes reads back with its evidence."""

    def test_a_reported_run_outranks_its_turns(self) -> None:
        # The CLI reported the run's cost, so that amount is the run's; each
        # turn keeps the Anthropic API estimate it was priced at on its own.
        stdout = claude_multistep_stdout(
            n_steps=2, result_text="ok", total_cost_usd=_RUN_COST,
        )
        metrics = usage_metrics.parse_claude_usage(stdout)
        produced = usage_trajectory.parse_claude_trajectory(stdout).turns
        run = _parsed(_written(metrics, produced))
        self.assertEqual(run.cost_evidence, metrics.cost_evidence)
        self.assertEqual(run.cost_evidence.basis, usage_cost.CLI_REPORTED)
        self.assertEqual(
            [turn.cost_evidence for turn in run.turns],
            [turn.cost_evidence for turn in produced],
        )
        self.assertEqual(
            {turn.cost_evidence.basis for turn in run.turns},
            {usage_cost.ANTHROPIC_API_ESTIMATE},
        )
        self.assertEqual(
            run.total_tokens, sum(turn.total_tokens for turn in run.turns),
        )
        self.assertEqual(
            run.total_tokens,
            usage_tokens.non_overlapping_total(metrics.to_dict()),
        )


if __name__ == "__main__":
    unittest.main()
