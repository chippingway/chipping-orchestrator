# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run's spend reads as, for the whole run and for one assistant turn."""
from __future__ import annotations

import unittest
from typing import Any

from orchestrator.observability.trajectory_viewer import models, usage_html
from orchestrator.observability.usage import (
    cost_evidence as usage_cost,
    token_evidence as usage_tokens,
)
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    AGY_TOKENS,
    CLAUDE_TOKENS,
    CODEX_TOKENS,
    cost,
    run,
)

_MODEL_CLAUDE = "claude-opus-4-8"

_MODEL_CODEX = "gpt-6.1-sol"

_MODEL_AGY = "gemini-4-argon"

_RUN_COST = 0.83

_RUN_INPUT = 41230

_RUN_OUTPUT = 5120

_RUN_CACHE_READ = 812440

_RUN_CACHE_WRITE = 20110

_CODEX_INPUT = 1000

_CODEX_OUTPUT = 200

_CODEX_CACHED = 500

_CODEX_COST = 0.05

_TURN_COST = 0.0123

_TURN_INPUT = 12

_TURN_OUTPUT = 340

_TURN_CACHE_READ = 18240

_TURN_CACHE_WRITE = 512

_RATES = "rates verified 2026-10-29"

_TOTAL_UNKNOWN = ">total unknown</span>"

_UNKNOWN_TOTAL_NOTE = "token total is unknown"

_REPORTED_RUN = cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _RUN_COST))


def _claude_run_usage(**overrides: Any) -> models.RunUsageView:
    """The run summary a claude record whose CLI reported its cost carries."""
    fields = {
        "models": (_MODEL_CLAUDE,),
        "turns": 9,
        "input_tokens": _RUN_INPUT,
        "output_tokens": _RUN_OUTPUT,
        "cached_tokens": 0,
        "cache_read_tokens": _RUN_CACHE_READ,
        "cache_write_tokens": _RUN_CACHE_WRITE,
        "cost_evidence": _REPORTED_RUN,
        "token_evidence": CLAUDE_TOKENS,
    }
    fields.update(overrides)
    return models.RunUsageView(**fields)


def _turn(**overrides: Any) -> models.TurnUsageView:
    """One assistant turn priced as its own API estimate, overridable per test."""
    fields = {
        "turn": 0,
        "model": _MODEL_CLAUDE,
        "input_tokens": _TURN_INPUT,
        "output_tokens": _TURN_OUTPUT,
        "cache_read_tokens": _TURN_CACHE_READ,
        "cache_write_tokens": _TURN_CACHE_WRITE,
        "cost_evidence": cost(
            usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN_COST),
        ),
        "token_evidence": CLAUDE_TOKENS,
    }
    fields.update(overrides)
    return models.TurnUsageView(**fields)


class RunUsageHtmlTest(unittest.TestCase):
    """The run row draws the counters the record observed, and its basis."""

    def test_claude_summary_chips_and_estimate_note(self) -> None:
        rendered = usage_html.run_usage_html(run(
            run_usage=_claude_run_usage(),
            turns=(_turn(),),
        ))
        for fragment in (
            ">Run usage</span>",
            _MODEL_CLAUDE,
            "9 turns",
            # The cache classes sit beside the input, so each counts once.
            "total 878,900 tok",
            "cache-read 812,440",
            "cache-write 20,110",
            # The run's own amount, named with its basis and exact to the
            # cent, in the one chip drawn louder than the token pills.
            '<span class="orch-traj-chip cost">$0.83 (CLI-reported)</span>',
            "never repriced",
            "not a verified bill",
            "claude-only estimates",
            "need not sum to it and never replace it",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, rendered)
        # `cached_tokens` is no counter claude reports, and a CLI-reported
        # amount was priced at no rates.
        self.assertNotIn("cached ", rendered)
        self.assertNotIn(_RATES, rendered)

    def test_codex_cached_input_counts_once(self) -> None:
        rendered = usage_html.run_usage_html(run(run_usage=models.RunUsageView(
            models=(_MODEL_CODEX,),
            turns=3,
            input_tokens=_CODEX_INPUT,
            output_tokens=_CODEX_OUTPUT,
            cached_tokens=_CODEX_CACHED,
            cost_evidence=cost(
                usage_cost.COMPLETE, (usage_cost.OPENAI_API_ESTIMATE, _CODEX_COST),
            ),
            token_evidence=CODEX_TOKENS,
        )))
        for fragment in (
            _MODEL_CODEX,
            # The cached part of the input is shown, and left out of the total.
            ">cached 500</span>",
            ">total 1,200 tok</span>",
            "counts them once",
            "$0.05 (OpenAI API token estimate)",
            f">{_RATES}</span>",
            # No per-turn detail on this backend: the run summary plus a note
            # that says so, and never the estimates caveat.
            "not available for this backend",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, rendered)
        # Codex reports no read/write split, so neither is drawn as a zero.
        self.assertNotIn("cache-read", rendered)
        self.assertNotIn("need not sum to it", rendered)

    def test_agy_only_run_reads_as_a_gemini_estimate(self) -> None:
        rendered = usage_html.run_usage_html(run(run_usage=models.RunUsageView(
            models=(_MODEL_AGY,),
            input_tokens=_CODEX_INPUT,
            output_tokens=_CODEX_OUTPUT,
            cache_read_tokens=_CODEX_CACHED,
            cost_evidence=cost(
                usage_cost.COMPLETE, (usage_cost.GEMINI_API_ESTIMATE, _CODEX_COST),
            ),
            token_evidence=AGY_TOKENS,
        )))
        self.assertIn("$0.05 (Gemini API token estimate)", rendered)
        # Nothing says whether an AGY cache read sits inside its input.
        self.assertIn(_TOTAL_UNKNOWN, rendered)
        self.assertIn(_UNKNOWN_TOTAL_NOTE, rendered)

    def test_each_cost_names_what_it_is(self) -> None:
        for name, stated, chip in (
            (
                "mixed",
                cost(
                    usage_cost.COMPLETE,
                    (usage_cost.CLI_REPORTED, _RUN_COST),
                    (usage_cost.GEMINI_API_ESTIMATE, _CODEX_COST),
                ),
                "$0.88 (blended: CLI-reported $0.83 + Gemini API token estimate $0.05)",
            ),
            (
                "incomplete",
                cost(usage_cost.INCOMPLETE, (usage_cost.OPENAI_API_ESTIMATE, _CODEX_COST)),
                "$0.05 (OpenAI API token estimate, incomplete subtotal)",
            ),
            ("unpriced", cost(usage_cost.INCOMPLETE), "unpriced"),
            ("no usage", cost(usage_cost.NO_USAGE), "no usage"),
        ):
            with self.subTest(name):
                rendered = usage_html.run_usage_html(
                    run(run_usage=models.RunUsageView(cost_evidence=stated)),
                )
                self.assertIn(f'<span class="orch-traj-chip cost">{chip}</span>', rendered)

    def test_a_record_without_evidence_stays_unknown(self) -> None:
        # An earlier build's record: its amount on no basis, never relabelled
        # or repriced, and its cache counts placed nowhere.
        rendered = usage_html.run_usage_html(run(run_usage=_claude_run_usage(
            cost_evidence=cost(
                usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _RUN_COST),
            ),
            token_evidence=usage_tokens.TokenEvidence(
                usage_tokens.COUNTERS, usage_tokens.UNKNOWN,
            ),
        )))
        self.assertIn("$0.83 (basis unknown, completeness unknown)", rendered)
        self.assertIn(_TOTAL_UNKNOWN, rendered)
        self.assertIn(_UNKNOWN_TOTAL_NOTE, rendered)

    def test_an_observed_counter_with_no_count(self) -> None:
        # The line names a cache read it carries no count for: it is drawn
        # as unknown, never as a zero, and the total has no answer -- for
        # that reason, not for an overlap the record does state.
        rendered = usage_html.run_usage_html(run(run_usage=_claude_run_usage(
            cache_read_tokens=None,
        )))
        self.assertIn(">cache-read unknown</span>", rendered)
        self.assertNotIn("cache-read 0", rendered)
        self.assertIn(_TOTAL_UNKNOWN, rendered)
        self.assertIn("names a counter it carries no count for", rendered)
        self.assertNotIn("sit inside its input", rendered)

    def test_pre_usage_record_renders_nothing(self) -> None:
        self.assertEqual(usage_html.run_usage_html(run()), "")


class TurnUsageHtmlTest(unittest.TestCase):
    """The strip drawn above one assistant turn, and what it admits to."""

    def test_strip_carries_tokens_and_own_estimate(self) -> None:
        rendered = usage_html.turn_usage_html(_turn())
        for fragment in (
            "orch-traj-turn",
            _MODEL_CLAUDE,
            ">in 12</span>",
            ">out 340</span>",
            ">cache-read 18,240</span>",
            ">cache-write 512</span>",
            # Sub-cent precision so a small estimate is not floored to
            # `$0.00`, on the turn's own basis and dated by its rates.
            f'<span title="{_RATES}">$0.0123 (Anthropic API token estimate)</span>',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, rendered)

    def test_a_hand_back_turn_shows_its_output_alone(self) -> None:
        # A subagent hand-back reports only its output count, so the input
        # and cache counters it never reported are not drawn as zeros.
        rendered = usage_html.turn_usage_html(_turn(
            input_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            token_evidence=usage_tokens.TokenEvidence(
                ("output_tokens",), usage_tokens.DISJOINT,
            ),
        ))
        self.assertIn(">out 340</span>", rendered)
        self.assertNotIn("in 0", rendered)
        self.assertNotIn("cache-", rendered)

    def test_cache_hit_chip_only_when_cache_read(self) -> None:
        self.assertIn("cache hit", usage_html.turn_usage_html(_turn()))
        for no_read in (0, None):
            with self.subTest(cache_read_tokens=no_read):
                self.assertNotIn("cache hit", usage_html.turn_usage_html(
                    _turn(cache_read_tokens=no_read),
                ))
        # A turn naming a cache read it carries no count for says so.
        self.assertIn(
            "<span>cache-read unknown</span>",
            usage_html.turn_usage_html(_turn(cache_read_tokens=None)),
        )

    def test_an_unpriced_or_unattributed_turn_says_so(self) -> None:
        for name, stated, segment in (
            ("unpriced", cost(usage_cost.INCOMPLETE), "<span>unpriced</span>"),
            (
                "absent basis",
                cost(usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _TURN_COST)),
                "<span>$0.0123 (basis unknown, completeness unknown)</span>",
            ),
        ):
            with self.subTest(name):
                rendered = usage_html.turn_usage_html(_turn(cost_evidence=stated))
                self.assertIn(segment, rendered)

    def test_model_escaped(self) -> None:
        rendered = usage_html.turn_usage_html(_turn(model="<m>"))
        self.assertIn("&lt;m&gt;", rendered)
        self.assertNotIn("<m></span>", rendered)


if __name__ == "__main__":
    unittest.main()
