# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The usage counters as the accounting checkpoint holds them: their spelling, what one run adds, and how it is added.

A counter is a total its writers spell as one -- the run and token counts whole
numbers of any size, the cost any number a float holds, each non-negative and
never a flag, which JSON spells apart from `1` and a reader in this language
would add as one -- and the cost tags a list of words. A run's parsed usage is countable only
where what it adds is spelled the same way: a parser handing back a negative
count, or a negative cost or one no float holds, gives the checkpoint nothing it
can commit, so
it is refused before anything is read or written rather than landed as a total
the next reading refuses. Each transformation asks the same of the total it
makes, so no candidate carries a counter its own read-back would refuse.

The arithmetic is the stage fold's (`issue_usage._accumulate_issue_usage`):
one run, its tokens, its cost where it has one, and its cost tag.
"""
from __future__ import annotations

import functools
import sys
from collections.abc import Mapping
from typing import Any

from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    pinned_commit_models as _commit_models,
)

# How a count and a cost total are spelled: the types either may be.
_Spelling = tuple[type, ...]
_WHOLE: _Spelling = (int,)
_AMOUNT: _Spelling = (int, float)


def usage_folds(usage: UsageMetrics) -> dict[str, _commit_models.Transform]:
    """What one invoked run's parsed `usage` adds to each counter, as transformations over its fresh value.

    Applied over whatever the comment carries when the commit lands, so
    another road's fold since is kept beside it. A `None` cost adds nothing to
    the cost total and creates no zero: a `no-usage` or `unknown-price` run
    leaves it exactly as it stands, absent included. A counter spelled as
    nothing its writers write, before or after the run is added, answers
    CONFLICT, so the commit is refused rather than landing a number nobody kept.
    """
    return {
        _issue_usage.AGENT_RUNS: functools.partial(_added, 1, spelled=_WHOLE),
        _issue_usage.TOTAL_TOKENS: functools.partial(_added, _issue_usage._run_tokens(usage), spelled=_WHOLE),
        _issue_usage.TOTAL_COST: functools.partial(_added, usage.cost_usd, spelled=_AMOUNT),
        _issue_usage.COST_SOURCES: functools.partial(_tagged, usage.cost_source),
    }


def countable(usage: UsageMetrics) -> bool:
    """Whether what `usage` adds to each counter is spelled as its writers spell a total.

    Every token count the run total sums, and the cost where there is one;
    codex's `cached_tokens` is no part of that total, so it decides nothing.
    """
    counts = (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens)
    if not all(_total(count, _WHOLE) for count in counts):
        return False
    priced = usage.cost_usd is None or _total(usage.cost_usd, _AMOUNT)
    return priced and isinstance(usage.cost_source, str)


def miscounted(record: Mapping[str, Any]) -> bool:
    """Whether `record` carries a counter spelled as nothing its writers write; an absent one is none."""
    held = {
        _issue_usage.AGENT_RUNS: _WHOLE,
        _issue_usage.TOTAL_TOKENS: _WHOLE,
        _issue_usage.TOTAL_COST: _AMOUNT,
    }
    for counter, spelled in held.items():
        if counter in record and not _total(record[counter], spelled):
            return True
    return _issue_usage.COST_SOURCES in record and not _tags(record[_issue_usage.COST_SOURCES])


def _total(written: Any, spelled: _Spelling) -> bool:
    """Whether `written` is a total as its writers spell one: of `spelled`'s types, non-negative, and no flag.

    A count is any whole number, however large: it is added as one and never
    converted. A cost may be a float, so it is also one a float holds -- NaN,
    an infinity, and a whole number past the largest float are none -- asked
    by comparison alone, which this language makes exact between a whole
    number and a float rather than converting either.
    """
    if isinstance(written, bool) or not isinstance(written, spelled):
        return False
    if float in spelled:
        return 0 <= written <= sys.float_info.max
    return written >= 0


def _tags(written: Any) -> bool:
    """Whether `written` is the cost tags as their writer spells them: a list of words."""
    if not isinstance(written, list):
        return False
    return all(isinstance(tag, str) for tag in written)


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
    if not all(_total(part, spelled) for part in parts):
        return _commit_models.CONFLICT
    total = sum(parts)
    return total if _total(total, spelled) else _commit_models.CONFLICT


def _tagged(tag: str, fresh: Any, *_moves: Any) -> Any:
    """The cost tags with `tag` joined, sorted; CONFLICT where `fresh` is no list of words."""
    if fresh is _commit_models.ABSENT:
        return [tag]
    return sorted({*fresh, tag}) if _tags(fresh) else _commit_models.CONFLICT
