# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The usage totals as the accounting checkpoint holds them: their spelling, what one run adds, and how it is added.

A count is a total its writers spell as one -- the run and token counts whole
numbers of any size, the cost any number a float holds, each non-negative and
never a flag, which JSON spells apart from `1` and a reader in this language
would add as one -- the cost tags a list of words, and the cost evidence one a
usage record could carry whose amounts sum to a total a float holds
(`issue_usage.carried_cost`). A run's parsed usage is
countable only where what it adds is spelled the same way: a parser handing
back a negative count, a negative cost or one no float holds, or cost evidence
no record carries gives the checkpoint nothing it can commit, so it is refused
before anything is read or written rather than landed as a total the next
reading refuses. Each transformation asks the same of the total it makes, so no
candidate carries a total its own read-back would refuse.

What one run adds: one to the run count; its non-overlapping token total
(`token_evidence.non_overlapping_total`) to the token total where its evidence
settles one, and one to the runs whose total is unknown where it does not; its
cost where it has a complete one to the cost total, and its cost tag to the
sorted, distinct tags; and its cost evidence, reduced with the issue's
(`cost_evidence.reduce_costs`). A run is read as its usage record serializes
it, so metrics built with no evidence state an unknown cost and an overlap
nothing establishes, never a guessed one.

The evidence is decided where the reading carries none (`issue_usage.EarlierUsage`):
an issue that counted nothing starts it from no cost, and one whose runs an
earlier build counted starts it from their cost as one record without evidence,
with how many they were kept in `issue_unevidenced_runs` beside it. That
decision reads the run count and cost total as well, so the fields it read
(`EarlierUsage.decided_on`) are ones a commit has to find unmoved for it to
stand.
"""
from __future__ import annotations

import functools
import sys
from collections.abc import Mapping
from typing import Any

from orchestrator.observability.usage import (
    cost_evidence as _usage_cost,
    token_evidence as _usage_tokens,
)
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    pinned_commit_models as _commit_models,
)

# How a total is spelled: the types it may be, or a list of words.
_Spelling = tuple[type, ...]
_WHOLE: _Spelling = (int,)
_AMOUNT: _Spelling = (int, float)
_WORDS: _Spelling = (list,)

# The fields that hold no total by themselves: they stand only beside the evidence their runs were counted with.
_BESIDE_EVIDENCE = (_issue_usage.TOKENS_UNKNOWN_RUNS, _issue_usage.UNEVIDENCED_RUNS)


def usage_folds(usage: UsageMetrics, record: Mapping[str, Any]) -> dict[str, _commit_models.Transform]:
    """What one invoked run's parsed `usage` adds to each total, as transformations over its fresh value.

    Applied over whatever the comment carries when the commit lands, so
    another invocation's count since is kept beside it; `record` is the reading
    the commit was decided on, where the evidence starts if it carries none. A
    `None` increment adds nothing and creates no zero: an incomplete cost
    leaves the cost total exactly as it stands, absent included, and a known
    token total leaves the unknown-total runs so. A total spelled as nothing
    its writers write, before or after the run is added, answers CONFLICT, so
    the commit is refused rather than landing a number nobody kept.
    """
    written = usage.to_dict()
    run_tokens = _usage_tokens.non_overlapping_total(written)
    earlier = _issue_usage.EarlierUsage.of(record)
    return {
        _issue_usage.AGENT_RUNS: functools.partial(_added, 1, spelled=_WHOLE),
        _issue_usage.TOTAL_TOKENS: functools.partial(_added, run_tokens, spelled=_WHOLE),
        _issue_usage.TOKENS_UNKNOWN_RUNS: functools.partial(
            _added, 1 if run_tokens is None else None, spelled=_WHOLE,
        ),
        _issue_usage.TOTAL_COST: functools.partial(_added, usage.cost_usd, spelled=_AMOUNT),
        _issue_usage.COST_SOURCES: functools.partial(_tagged, usage.cost_source),
        _issue_usage.COST_EVIDENCE: functools.partial(
            _costed, _usage_cost.recorded_cost(written), None if earlier is None else earlier.cost,
        ),
        _issue_usage.UNEVIDENCED_RUNS: functools.partial(
            _added, earlier.runs if earlier is not None and earlier.runs else None, spelled=_WHOLE,
        ),
    }


def countable(usage: UsageMetrics) -> bool:
    """Whether what `usage` adds to each total is spelled as its writers spell a total.

    Every token count the non-overlapping total reads, the cost where there is
    one, and the cost evidence where the parser stated one: evidence no usage
    record carries would read back as no evidence at all.
    """
    written = usage.to_dict()
    if not all(_spelled(written[counter], _WHOLE) for counter in _usage_tokens.COUNTERS):
        return False
    priced = usage.cost_usd is None or _spelled(usage.cost_usd, _AMOUNT)
    evidence = written[_usage_cost.COST_EVIDENCE]
    stated = evidence is None or _issue_usage.carried_cost(evidence) is not None
    return priced and stated and isinstance(usage.cost_source, str)


def miscounted(record: Mapping[str, Any]) -> bool:
    """Whether `record` carries a total spelled as nothing its writers write; an absent one is none.

    The unknown-total and earlier runs are never written without the evidence
    they were counted beside, so either one carried without it is damage too.
    """
    held = {
        _issue_usage.AGENT_RUNS: _WHOLE,
        _issue_usage.TOTAL_TOKENS: _WHOLE,
        _issue_usage.TOKENS_UNKNOWN_RUNS: _WHOLE,
        _issue_usage.TOTAL_COST: _AMOUNT,
        _issue_usage.COST_SOURCES: _WORDS,
        _issue_usage.UNEVIDENCED_RUNS: _WHOLE,
    }
    for counter, spelled in held.items():
        if counter in record and not _spelled(record[counter], spelled):
            return True
    if _issue_usage.COST_EVIDENCE not in record:
        return any(beside in record for beside in _BESIDE_EVIDENCE)
    return _issue_usage.carried_cost(record[_issue_usage.COST_EVIDENCE]) is None


def _spelled(written: Any, spelling: _Spelling) -> bool:
    """Whether `written` is a total as its writers spell one: of `spelling`'s types, non-negative, and no flag.

    A count is any whole number, however large: it is added as one and never
    converted. A cost may be a float, so it is also one a float holds -- NaN,
    an infinity, and a whole number past the largest float are none -- asked
    by comparison alone, which this language makes exact between a whole
    number and a float rather than converting either. Tags are a list of words.
    """
    if isinstance(written, bool) or not isinstance(written, spelling):
        return False
    if list in spelling:
        return all(isinstance(tag, str) for tag in written)
    if float in spelling:
        return 0 <= written <= sys.float_info.max
    return written >= 0


def _added(increment: float | None, fresh: Any, *_moves: Any, spelled: _Spelling) -> Any:
    """`fresh` with `increment` added; CONFLICT where either one or their total is no total its writers spell.

    A `None` increment adds nothing: the total stays as it stands, an absent
    one absent.
    """
    parts = [] if increment is None else [increment]
    if fresh is not _commit_models.ABSENT:
        parts.append(fresh)
    if not parts:
        return _commit_models.ABSENT
    if not all(_spelled(part, spelled) for part in parts):
        return _commit_models.CONFLICT
    total = sum(parts)
    return total if _spelled(total, spelled) else _commit_models.CONFLICT


def _tagged(tag: str, fresh: Any, *_moves: Any) -> Any:
    """The cost tags with `tag` joined, sorted; CONFLICT where `fresh` is no list of words."""
    if fresh is _commit_models.ABSENT:
        return [tag]
    return sorted({*fresh, tag}) if _spelled(fresh, _WORDS) else _commit_models.CONFLICT


def _costed(
    run: _usage_cost.CostEvidence, earlier: _usage_cost.CostEvidence | None, fresh: Any, *_moves: Any,
) -> Any:
    """The issue's cost evidence with `run`'s reduced into it; CONFLICT where none can be read or carried.

    An absent one starts from `earlier`, decided over a reading that carried
    none; where that reading carried one, an absent one is a record somebody
    else rewrote, never an issue that counted nothing. A reduction the totals
    cannot carry (`issue_usage.carried_cost`) -- one basis's amount, or the
    amounts of every basis together, past what a float holds -- is refused
    before it lands, never committed for a receipt to fail on.
    """
    if fresh is _commit_models.ABSENT:
        prior = earlier
    else:
        prior = _issue_usage.carried_cost(fresh)
    if prior is None:
        return _commit_models.CONFLICT
    reduced = _usage_cost.reduce_costs((prior, run)).to_dict()
    if _issue_usage.carried_cost(reduced) is None:
        return _commit_models.CONFLICT
    return reduced
