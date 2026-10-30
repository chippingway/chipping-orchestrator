# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which columns the events table fills from one JSONL record.

One inventory behind four questions a record is measured against -- what it
must carry, what the table has a column for, which of those columns hold JSON,
and which it derives from the record's usage evidence rather than copies off a
field. The required-key guard, the promoted-column extraction, the derivation,
and the INSERT's parameter order all read this list, and a row lands in the
wrong column the moment two of them disagree about it.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.observability.usage import cost_evidence as usage_cost

COL_TS = "ts"
COL_REPO = "repo"
COL_ISSUE = "issue"
COL_EVENT = "event"

# Anything outside this list lands in the `extras` JSONB column, so a record
# written by a newer orchestrator version never loses fields to a database
# that has no column for them yet.
PROMOTED_COLUMNS = (
    COL_TS,
    COL_REPO,
    COL_ISSUE,
    COL_EVENT,
    "stage",
    "duration_s",
    "result",
    "agent_role",
    "backend",
    "agent_spec",
    "resume_session_id",
    "session_id",
    "review_round",
    "retry_count",
    "exit_code",
    "timed_out",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "models",
    "turns",
    "cost_usd",
    "cost_source",
)

# psycopg adapts dict / list to JSON natively but a few drivers need an
# explicit Json wrapper, which is what a caller's own `json_adapter` covers.
JSONB_COLUMNS = ("models", "extras")

REQUIRED_KEYS = (COL_TS, COL_REPO, COL_ISSUE, COL_EVENT)

COST_COMPLETENESS = "cost_completeness"

TOKEN_CACHE_OVERLAP = "token_cache_overlap"

TOTAL_TOKENS = "total_tokens"

# One amount column per cost basis. The basis is the key, so a contribution
# lands in its own column whatever order the record listed it in.
COST_AMOUNT_COLUMNS = MappingProxyType({
    usage_cost.CLI_REPORTED: "cost_cli_reported_usd",
    usage_cost.ANTHROPIC_API_ESTIMATE: "cost_anthropic_estimate_usd",
    usage_cost.OPENAI_API_ESTIMATE: "cost_openai_estimate_usd",
    usage_cost.GEMINI_API_ESTIMATE: "cost_gemini_estimate_usd",
    usage_cost.UNKNOWN_BASIS: "cost_unknown_basis_usd",
})

# The verification dates of the rates an estimate was priced at. Only an
# estimate is priced at rates, so the reported and unknown bases have none.
RATE_DATE_COLUMNS = MappingProxyType({
    usage_cost.ANTHROPIC_API_ESTIMATE: "anthropic_rates_verified_on",
    usage_cost.OPENAI_API_ESTIMATE: "openai_rates_verified_on",
    usage_cost.GEMINI_API_ESTIMATE: "gemini_rates_verified_on",
})

# Filled from an `agent_exit` record's evidence rather than from a field of
# the same name, so a record never names them and none of them is promoted.
DERIVED_COLUMNS = (
    COST_COMPLETENESS,
    *COST_AMOUNT_COLUMNS.values(),
    *RATE_DATE_COLUMNS.values(),
    TOKEN_CACHE_OVERLAP,
    TOTAL_TOKENS,
)

# Every column a row fills from its record, in the order the INSERT names them
# ahead of the extras blob and the provenance behind it.
TABLE_COLUMNS = PROMOTED_COLUMNS + DERIVED_COLUMNS
