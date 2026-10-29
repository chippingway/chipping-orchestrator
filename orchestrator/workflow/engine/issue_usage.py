# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned issue usage totals and the receipt posted when a workflow ends.

Unknown and estimated costs remain distinguishable. Updating these cumulative
usage counters decides nothing about the separate lifetime launch allowance,
whose ledger reads the run count only as a floor under its own charges.

The counter names and one run's token total are shared with the accounting
checkpoint (`usage_checkpoint`), the one writer of these counters, whose
arithmetic over a fresh reading and spelling rules live on `usage_counters`."""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    comments as _comments,
)

# The cumulative counters, as the pinned comment spells them.
AGENT_RUNS = "issue_agent_runs"
TOTAL_TOKENS = "issue_total_tokens"
TOTAL_COST = "issue_total_cost_usd"
COST_SOURCES = "issue_cost_sources"
USAGE_COUNTERS = (AGENT_RUNS, TOTAL_TOKENS, TOTAL_COST, COST_SOURCES)


def _format_issue_usage_verdict(state: PinnedState) -> str | None:
    """Render the cumulative per-issue usage verdict for a terminal surface.

    Reads the counters the accounting checkpoint lands on pinned state and
    returns a single visible line:

        :receipt: this issue: 3 agent runs · 45,200 tokens · $0.87

    The cost slot follows `issue_cost_sources`: `(est.)` is appended when any
    run's cost was `estimated` from the price table, and the whole figure
    collapses to `unknown` when any `unknown-price` run leaves the priced
    total incomplete (that dominates -- an unknown total cannot also be an
    estimate). A `no-usage` run contributes nothing and marks neither.

    Returns None when no agent run was ever counted (`issue_agent_runs` is
    0 / absent) so a terminal with nothing to report skips the line instead
    of posting a zero receipt.
    """
    runs = int(state.get(AGENT_RUNS) or 0)
    if runs <= 0:
        return None
    tokens = int(state.get(TOTAL_TOKENS) or 0)
    prior_sources = state.get(COST_SOURCES)
    sources = set(prior_sources) if isinstance(prior_sources, list) else set()
    if "unknown-price" in sources:
        cost = "unknown"
    else:
        cost = f"${float(state.get(TOTAL_COST) or 0):.2f}"
        if "estimated" in sources:
            cost = f"{cost} (est.)"
    return (
        f":receipt: this issue: {runs} agent runs · "
        f"{tokens:,} tokens · {cost}"
    )


def _post_issue_usage_verdict(
    gh: GitHubClient, issue: Issue, state: PinnedState
) -> None:
    """Post the terminal usage verdict as its own tracked issue comment.

    Thin wrapper over `_format_issue_usage_verdict` + `_post_issue_comment`
    for the PR merged / rejected finalizers, which otherwise post no comment
    of their own. Must run BEFORE the finalizer's `write_pinned_state` so the
    comment id lands in the same persisted state and a later drift/watermark
    tick recognizes it as orchestrator-authored. A no-op when there is
    nothing to report (no counted agent run).
    """
    verdict = _format_issue_usage_verdict(state)
    if verdict:
        _comments._post_issue_comment(gh, issue, state, verdict)


def _run_tokens(usage: UsageMetrics) -> int:
    """One run's tokens: input, output, cache-read, and cache-write.

    codex's `cached_tokens` is left out: it is the portion of `input_tokens`
    already served from cache, so summing it would count part of the input
    twice.
    """
    return sum((
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
    ))
