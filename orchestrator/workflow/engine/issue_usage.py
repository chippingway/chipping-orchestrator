# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned issue usage totals and the receipt posted when a workflow ends.

The totals keep what each run's usage record states its cost and tokens mean
(`usage.cost_evidence`, `usage.token_evidence`) rather than one figure merging
them. `issue_cost_evidence` is every counted run's cost reduced the way
`reduce_costs` reduces many -- an amount per basis, beside the dates an
estimate's rates were verified on, and the weakest completeness any run states
-- so a CLI-reported amount, each provider's API estimate, unpriced usage, and an
amount whose basis nothing states stay apart, and a subtotal never reads as
complete spend. `issue_total_tokens` adds each run's non-overlapping total
(`token_evidence.non_overlapping_total`) where its evidence settles one; a run
whose total that evidence leaves unknown adds nothing to it and is counted in
`issue_total_tokens_unknown_runs` instead. `issue_total_cost_usd` sums each
complete cost and `issue_cost_sources` keeps the distinct cost tags, but no
receipt reads either where the evidence stands.

Runs an earlier build counted carry no evidence, and none is inferred for them:
not from `issue_cost_sources`, a backend, or a model. Their totals read as one
usage record without evidence (`EarlierUsage`) -- their summed cost under the
`unknown` basis with an `unknown` completeness, and their tokens as that build
summed them, with a cache overlap nothing establishes. The first run this build
counts over them folds that reading into `issue_cost_evidence` and keeps how
many they were in `issue_unevidenced_runs`, so the runs counted after them
never make their basis or overlap known.

Updating these cumulative usage counters decides nothing about the separate
lifetime launch allowance, whose ledger reads the run count only as a floor
under its own charges.

The field names are shared with the accounting checkpoint
(`usage_checkpoint`), the one writer of these totals, whose arithmetic over a
fresh reading and spelling rules live on `usage_counters`."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.dashboard import cost_text as _cost_text
from orchestrator.observability.usage import (
    cost_evidence as _usage_cost,
    token_evidence as _usage_tokens,
)
from orchestrator.workflow.engine import (
    comments as _comments,
)

# The cumulative totals, as the pinned comment spells them.
AGENT_RUNS = "issue_agent_runs"
TOTAL_TOKENS = "issue_total_tokens"
TOKENS_UNKNOWN_RUNS = "issue_total_tokens_unknown_runs"
TOTAL_COST = "issue_total_cost_usd"
COST_SOURCES = "issue_cost_sources"
COST_EVIDENCE = "issue_cost_evidence"
UNEVIDENCED_RUNS = "issue_unevidenced_runs"
USAGE_COUNTERS = (
    AGENT_RUNS, TOTAL_TOKENS, TOKENS_UNKNOWN_RUNS, TOTAL_COST, COST_SOURCES, COST_EVIDENCE, UNEVIDENCED_RUNS,
)

# What a cost evidence no reader takes states: no basis, no amount, and no completeness.
_UNSTATED = _usage_cost.CostEvidence(_usage_cost.UNKNOWN)

# What a reading carrying no evidence is read as an earlier build's runs off.
_EARLIER_READS = (COST_EVIDENCE, AGENT_RUNS, TOTAL_COST)


@dataclass(frozen=True)
class EarlierUsage:
    """The runs an earlier build counted on an issue's totals, with no evidence of what their cost and tokens mean.

    Read as one usage record without evidence (`cost_evidence.recorded_cost`):
    their summed `issue_total_cost_usd` under the `unknown` basis with an
    `unknown` completeness, none where they summed no amount.
    """

    runs: int
    cost: _usage_cost.CostEvidence

    @classmethod
    def of(cls, record: Mapping[str, Any]) -> EarlierUsage | None:
        """What the totals `record` carries held before they kept evidence; None where they keep it.

        A record that counted nothing holds no earlier run and states no cost:
        the fold of no cost at all, `no-usage`.
        """
        if COST_EVIDENCE in record:
            return None
        runs = _count(record.get(AGENT_RUNS))
        if not runs and TOTAL_COST not in record:
            return cls(0, _usage_cost.reduce_costs(()))
        return cls(runs, _usage_cost.recorded_cost({_usage_cost.COST_USD: record.get(TOTAL_COST)}))

    @classmethod
    def decided_on(cls, record: Mapping[str, Any]) -> tuple[str, ...]:
        """The fields `of` reads off `record`: none where it keeps the evidence, which starts nothing."""
        return () if COST_EVIDENCE in record else _EARLIER_READS


@dataclass(frozen=True)
class IssueUsage:
    """What an issue's totals state: its runs, its tokens and the runs they leave unsettled, and its cost."""

    runs: int
    tokens: int
    untotaled_runs: int
    unevidenced_runs: int
    cost: _usage_cost.CostEvidence

    @classmethod
    def read(cls, record: Mapping[str, Any]) -> IssueUsage:
        """The totals `record` carries: one keeping no evidence read as an earlier build's, a damaged one as unknown."""
        earlier = EarlierUsage.of(record)
        if earlier is None:
            earlier = EarlierUsage(
                _count(record.get(UNEVIDENCED_RUNS)),
                carried_cost(record.get(COST_EVIDENCE)) or _UNSTATED,
            )
        return cls(
            runs=_count(record.get(AGENT_RUNS)),
            tokens=_count(record.get(TOTAL_TOKENS)),
            untotaled_runs=_count(record.get(TOKENS_UNKNOWN_RUNS)),
            unevidenced_runs=earlier.runs,
            cost=earlier.cost,
        )

    def tokens_text(self) -> str:
        """The token count, saying which runs it settles no non-overlapping total for; bare where it settles all."""
        notes = []
        if self.untotaled_runs:
            notes.append(f"subtotal: token total unknown for {_runs_text(self.untotaled_runs)}")
        if self.unevidenced_runs:
            notes.append(f"{_runs_text(self.unevidenced_runs)} counted without usage evidence")
        counted = f"{self.tokens:,} tokens"
        if not notes:
            return counted
        noted = "; ".join(notes)
        return f"{counted} ({noted})"


def carried_cost(spelled: Any) -> _usage_cost.CostEvidence | None:
    """The cost evidence `spelled` states where the totals can carry it; None where they cannot.

    It has to be evidence a usage record carries (`CostEvidence.from_dict`),
    and its amounts, each a float already, have to add up to a total one holds
    too: two bases' amounts can each fit and their sum not, and a receipt
    states that sum.
    """
    evidence = _usage_cost.CostEvidence.from_dict(spelled)
    if evidence is None:
        return None
    try:
        summed = evidence.total_usd
    except OverflowError:
        return None
    return evidence if summed is None or math.isfinite(summed) else None


def _format_issue_usage_verdict(state: PinnedState) -> str | None:
    """Render the cumulative per-issue usage verdict for a terminal surface.

    Reads the totals the accounting checkpoint lands on pinned state and
    returns a single visible line:

        :receipt: this issue: 3 agent runs · 45,200 tokens · $0.87 (CLI-reported)

    The cost is worded off `issue_cost_evidence` by the shared `cost_text`
    owner, as every other surface words one: an amount never without its
    basis -- a Gemini API token estimate where Antigravity usage was priced on
    Gemini rates, `blended` with each basis's own amount beside it where the
    runs were stated on several -- an `incomplete subtotal` where some usage
    carries no amount, `completeness unknown` where nothing states how much an
    amount covers, and `unpriced`, `no usage`, or `cost unknown` where no amount
    is stated at all. The tokens say how many runs their count settles no
    non-overlapping total for. An issue whose totals keep no evidence -- every
    run an earlier build counted -- reads as those runs (`EarlierUsage`), its
    cost unknown in basis and completeness however `issue_cost_sources` tags
    it.

    Returns None when no agent run was ever counted (`issue_agent_runs` is
    0 / absent) so a terminal with nothing to report skips the line instead
    of posting a zero receipt.
    """
    usage = IssueUsage.read(state.state_data)
    if usage.runs <= 0:
        return None
    return (
        f":receipt: this issue: {usage.runs} agent runs · "
        f"{usage.tokens_text()} · {_cost_text.cost_text(usage.cost)}"
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


def _count(written: Any) -> int:
    """A count the totals carry, or 0 where they carry none spelled as one."""
    return written if _usage_tokens.is_count(written) else 0


def _runs_text(runs: int) -> str:
    noun = "run" if runs == 1 else "runs"
    return f"{runs:,} {noun}"
