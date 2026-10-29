# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The written lines and the owner-built objects the tests are written against."""
from __future__ import annotations

from datetime import date
from typing import Any

from orchestrator.observability.trajectory_viewer import constants, models, runs
from orchestrator.observability.usage import (
    cost_evidence as usage_cost,
    token_evidence as usage_tokens,
)

TOOL_CALL = "tool_call"

TOOL_RESULT = "tool_result"

ASSISTANT_MESSAGE = "assistant_message"

TOOL_BASH = "Bash"

TOOL_EDIT = "Edit"

TOOL_SKILL = "Skill"

TS = "2026-06-20T10:00:00+00:00"

REPO = "acme/widgets"

ISSUE = 42

STAGE = "implementing"

AGENT_ROLE = "developer"

BACKEND_CLAUDE = "claude"

# The date every active catalogue row was checked on, so an estimate a test
# states is dated the way a producer would date it.
RATES_VERIFIED_ON = date.fromisoformat("2026-10-29")

# What a producer states each backend's counters mean.
CLAUDE_TOKENS = usage_tokens.TokenEvidence(
    ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"),
    usage_tokens.DISJOINT,
)

CODEX_TOKENS = usage_tokens.TokenEvidence(
    ("input_tokens", "output_tokens", "cached_tokens"),
    usage_tokens.WITHIN_INPUT,
)

AGY_TOKENS = usage_tokens.TokenEvidence(
    ("input_tokens", "output_tokens", "cache_read_tokens"),
    usage_tokens.UNKNOWN,
)


def record(**overrides: Any) -> dict[str, Any]:
    """One decoded line, carrying the identity the sink writes on every run.

    A parse test names only the fields it is actually about, so what it does
    not name is what a plain run already looks like on disk.
    """
    written = {
        "ts": TS,
        "repo": REPO,
        "issue": ISSUE,
        "event": constants.TRAJECTORY_EVENT,
        "stage": STAGE,
        "agent_role": AGENT_ROLE,
        "backend": BACKEND_CLAUDE,
        "steps": [],
    }
    written.update(overrides)
    return written


def cost(completeness: str, *parts: tuple[str, float]) -> usage_cost.CostEvidence:
    """Evidence stating each `(basis, amount)` part at `completeness`.

    An estimate is dated with the rates it was priced at; a CLI-reported
    amount and an amount on no basis carry no rates at all.
    """
    undated = (usage_cost.CLI_REPORTED, usage_cost.UNKNOWN_BASIS)
    return usage_cost.CostEvidence(completeness, tuple(
        usage_cost.CostContribution(
            basis,
            amount,
            () if basis in undated else (RATES_VERIFIED_ON,),
        )
        for basis, amount in parts
    ))


def step(kind: str, **fields: Any) -> models.TrajectoryStepView:
    """One normalized step, defaulted the way a parsed record leaves it."""
    return models.TrajectoryStepView(kind=kind, **fields)


def run(**fields: Any) -> runs.TrajectoryRun:
    """A run carrying the identity every record has, overridable per test.

    The four identity fields are what the sink writes on every line, so a test
    about a timeline or a tally names only what it is actually about.
    """
    record = {"seq": 0, "ts": TS, "repo": REPO, "issue": ISSUE}
    record.update(fields)
    return runs.TrajectoryRun(**record)
