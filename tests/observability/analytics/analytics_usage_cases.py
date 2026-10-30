# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`agent_exit` records carrying usage evidence, written the way the producer writes them.

Each record's `cost_evidence` and `token_evidence` are the canonical serializers' own output, and its `cost_usd` and
`cost_source` are read off the same evidence the way `UsageMetrics.apply_cost` reads them, so a test that stores one
and reads it back is measuring the storage rather than a hand-typed shape. The cases name what downstream aggregation
has to keep apart: a CLI-reported amount and each provider's estimate, a blended record, an incomplete subtotal and an
unpriced run, a complete zero, no usage, and a record an earlier build wrote with no evidence at all -- beside the
three ways the cache counters relate to input.
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens

AGENT_EXIT = "agent_exit"

REPO = "owner/repo"

TS = "2026-10-30T09:15:00+00:00"

VERIFIED = date.fromisoformat("2026-10-29")

LATER_VERIFIED = date.fromisoformat("2026-12-01")

_INPUT = "input_tokens"

_OUTPUT = "output_tokens"

_CACHED = "cached_tokens"

_CACHE_READ = "cache_read_tokens"

_CACHE_WRITE = "cache_write_tokens"

# Claude's cache reads and writes are classes of their own beside its input.
_CLAUDE_COUNTERS = MappingProxyType({_INPUT: 100, _OUTPUT: 20, _CACHE_READ: 300, _CACHE_WRITE: 50})

# Codex's cached tokens are part of its input count.
_CODEX_COUNTERS = MappingProxyType({_INPUT: 1_000, _OUTPUT: 100, _CACHED: 400})

# Antigravity reports cache reads beside its input, and nothing establishes yet whether they sit inside it.
_AGY_COUNTERS = MappingProxyType({_INPUT: 500, _OUTPUT: 50, _CACHE_READ: 200})

CLAUDE_TOTAL = 470

CODEX_TOTAL = 1_100

# What each total holds: Claude's input, output, and the cache reads and writes beside them; Codex's output, its cached
# input, and the input no cache answered.
CLAUDE_INPUT = _CLAUDE_COUNTERS[_INPUT]

CLAUDE_OUTPUT = _CLAUDE_COUNTERS[_OUTPUT]

CLAUDE_CACHE = _CLAUDE_COUNTERS[_CACHE_READ] + _CLAUDE_COUNTERS[_CACHE_WRITE]

CODEX_OUTPUT = _CODEX_COUNTERS[_OUTPUT]

CODEX_CACHED = _CODEX_COUNTERS[_CACHED]

CODEX_UNCACHED_INPUT = _CODEX_COUNTERS[_INPUT] - CODEX_CACHED

DISJOINT = usage_tokens.TokenEvidence.reporting(_CLAUDE_COUNTERS, usage_tokens.DISJOINT)

WITHIN_INPUT = usage_tokens.TokenEvidence.reporting(_CODEX_COUNTERS, usage_tokens.WITHIN_INPUT)

UNSETTLED = usage_tokens.TokenEvidence.reporting(_AGY_COUNTERS, usage_tokens.UNKNOWN)

NOTHING_OBSERVED = usage_tokens.TokenEvidence((), usage_tokens.UNKNOWN)

_COUNTERS_BY_EVIDENCE = MappingProxyType({
    DISJOINT: _CLAUDE_COUNTERS,
    WITHIN_INPUT: _CODEX_COUNTERS,
    UNSETTLED: _AGY_COUNTERS,
})


def contribution(basis: str, amount: float, *verified_on: date) -> usage_cost.CostContribution:
    return usage_cost.CostContribution(basis, amount, verified_on)


def cost(completeness: str, *contributions: usage_cost.CostContribution) -> usage_cost.CostEvidence:
    return usage_cost.CostEvidence(completeness, contributions)


def usage_record(
    issue: int,
    spent: usage_cost.CostEvidence,
    tokens: usage_tokens.TokenEvidence,
    **fields: Any,
) -> dict[str, Any]:
    """One `agent_exit` line stating `spent` and `tokens`, its counters the ones `tokens` was built over."""
    record: dict[str, Any] = {
        "ts": TS,
        "repo": REPO,
        "issue": issue,
        "event": AGENT_EXIT,
        **_counters(tokens),
        "cost_source": spent.cost_source,
        usage_cost.COST_EVIDENCE: spent.to_dict(),
        usage_tokens.TOKEN_EVIDENCE: tokens.to_dict(),
    }
    if spent.complete_usd is not None:
        record[usage_cost.COST_USD] = spent.complete_usd
    record.update(fields)
    return record


def unevidenced_record(issue: int, **fields: Any) -> dict[str, Any]:
    """An `agent_exit` line an earlier build wrote: raw counters and a `cost_usd`, no evidence for either."""
    return {
        "ts": TS,
        "repo": REPO,
        "issue": issue,
        "event": AGENT_EXIT,
        _INPUT: 0,
        _OUTPUT: 0,
        _CACHED: 0,
        _CACHE_READ: 0,
        _CACHE_WRITE: 0,
        **fields,
    }


def stage_record(issue: int) -> dict[str, Any]:
    """A `stage_enter` line in `issue`, which states no usage whatever counters stand beside it."""
    return {**unevidenced_record(issue), "event": "stage_enter"}


def _counters(tokens: usage_tokens.TokenEvidence) -> dict[str, int]:
    # A producer writes every raw counter, zero for one no payload reported, so the evidence is what tells them apart.
    counts = _COUNTERS_BY_EVIDENCE.get(tokens, {})
    return {counter: counts.get(counter, 0) for counter in usage_tokens.COUNTERS}


REPORTED_USD = 0.42

ANTHROPIC_USD = 0.3

OPENAI_USD = 0.25

GEMINI_USD = 0.12

LATER_GEMINI_USD = 0.2

BLENDED_REPORTED_USD = 0.1

BLENDED_OPENAI_USD = 0.05

SUBTOTAL_USD = 0.2

REPORTED = cost(usage_cost.COMPLETE, contribution(usage_cost.CLI_REPORTED, REPORTED_USD))

ANTHROPIC_ESTIMATE = cost(
    usage_cost.COMPLETE,
    contribution(usage_cost.ANTHROPIC_API_ESTIMATE, ANTHROPIC_USD, VERIFIED),
)

OPENAI_ESTIMATE = cost(usage_cost.COMPLETE, contribution(usage_cost.OPENAI_API_ESTIMATE, OPENAI_USD, VERIFIED))

GEMINI_ESTIMATE = cost(usage_cost.COMPLETE, contribution(usage_cost.GEMINI_API_ESTIMATE, GEMINI_USD, VERIFIED))

LATER_GEMINI_ESTIMATE = cost(
    usage_cost.COMPLETE,
    contribution(usage_cost.GEMINI_API_ESTIMATE, LATER_GEMINI_USD, LATER_VERIFIED),
)

BLENDED = cost(
    usage_cost.COMPLETE,
    contribution(usage_cost.CLI_REPORTED, BLENDED_REPORTED_USD),
    contribution(usage_cost.OPENAI_API_ESTIMATE, BLENDED_OPENAI_USD, VERIFIED),
)

INCOMPLETE_SUBTOTAL = cost(
    usage_cost.INCOMPLETE,
    contribution(usage_cost.ANTHROPIC_API_ESTIMATE, SUBTOTAL_USD, VERIFIED),
)

UNPRICED = cost(usage_cost.INCOMPLETE)

# A reported zero is spend of zero, not an absence: its contribution stays.
COMPLETE_ZERO = cost(usage_cost.COMPLETE, contribution(usage_cost.CLI_REPORTED, 0))

NO_USAGE = cost(usage_cost.NO_USAGE)

# Three runs each priced at a row verified on a different date: a reduction keeping only the earliest and latest date
# would drop the middle one, which `reduce_costs` keeps.
THREE_DATED_ESTIMATES = tuple(
    cost(usage_cost.COMPLETE, contribution(usage_cost.OPENAI_API_ESTIMATE, OPENAI_USD, verified_on))
    for verified_on in map(date.fromisoformat, ("2026-08-01", "2026-09-01", "2026-10-01"))
)

# A record an earlier build wrote, read the way every surface reads one: `unknown`, its amount under that basis.
LEGACY_USD = 0.07

ABSENT_BASIS = usage_cost.recorded_cost(unevidenced_record(1, cost_usd=LEGACY_USD))
