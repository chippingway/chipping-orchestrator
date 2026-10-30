# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run cost, tallied once for the whole run and once per turn.

Two readings of the same spend, and the note between them is why there are two.
The run-level row is the amount the record stored for the whole run, on the
basis it names -- a CLI-reported figure stays CLI-reported, and is never
replaced by the turns' estimates summed or a historical record repriced
against today's rates; the strip drawn at an assistant-turn boundary is a
claude-only estimate on that turn's own basis. The two need not sum, so the row
says so in the copy rather than leaving an operator to reconcile them -- and it
says it differently for a backend that recorded no turns at all, where there
are no strips to reconcile against and the run summary is the only usage
surface the page has.

A chip is drawn for a fact the record actually carried. A token counter is
drawn only where the record's evidence observed it, because a counter no usage
payload reported is missing rather than zero, and one observed with no count
on the line reads as unknown for the same reason; the total beside them is the
non-overlapping one, and it reads as unknown, with the note saying why, where
nothing the record states settles whether its cache counts sit inside its
input. The cache-hit pill is drawn only where a turn read from cache. The cost
chip is the exception: it is drawn whether or not an amount resolved, worded by
``cost_text`` with its basis and any completeness qualifier, so an unpriced run
reads as unpriced rather than as free work, and an amount short of all the
usage never reads as complete spend.

Every caller-supplied string goes through ``html.escape`` before it reaches the
markup, because a page writes these with ``unsafe_allow_html=True`` and a model
name is record text this viewer does not own.
"""

from __future__ import annotations

import html
from types import MappingProxyType

from orchestrator.observability.dashboard import cost_text, formatting
from orchestrator.observability.trajectory_viewer.models import (
    RunUsageView,
    TurnUsageView,
)
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun
from orchestrator.observability.usage import (
    protocol,
    token_evidence as usage_tokens,
)

USAGE_SEPARATOR = '<span class="orch-traj-usage-sep">·</span>'

_COUNTER_LABELS = MappingProxyType({
    protocol.INPUT_TOKENS: "in",
    protocol.OUTPUT_TOKENS: "out",
    protocol.CACHED_TOKENS: "cached",
    protocol.CACHE_READ_TOKENS: "cache-read",
    protocol.CACHE_WRITE_TOKENS: "cache-write",
})

_RUN_COST_NOTE = (
    "Run cost is the amount this record stored, on the basis it names, and is "
    "never repriced. A CLI-reported amount is what the agent CLI printed, not "
    "a verified bill, and an API token estimate is a Standard list-price "
    "equivalent, not a charge."
)

_TURNS_NOTE = (
    "The per-turn strips in the timeline are claude-only estimates on their "
    "own basis; they need not sum to it and never replace it. Entries with no "
    "strip (tool results, user turns) are turn inputs, billed on the next "
    "assistant turn."
)

_NO_TURNS_NOTE = (
    "Per-turn usage is not available for this backend, so the run-level "
    "summary is its only usage surface."
)

_UNKNOWN_TOTAL_NOTE = (
    "The token total is unknown: nothing this record states says whether its "
    "cache counts sit inside its input."
)

_MISSING_COUNT_NOTE = (
    "The token total is unknown: this record names a counter it carries no "
    "count for."
)

_WITHIN_INPUT_NOTE = (
    "Cached tokens are part of the input count, so the total counts them once."
)


def usage_chip(text: str, css_class: str = "") -> str:
    """Render one pill, carrying the extra class where the caller named one."""
    classes = f"orch-traj-chip {css_class}".rstrip()
    return f'<span class="{classes}">{html.escape(text)}</span>'


def counter_texts(usage: RunUsageView | TurnUsageView) -> tuple[str, ...]:
    """Spell each counter the record observed, in counter order."""
    observed = usage.token_evidence.observed
    return tuple(
        _counter_text(counter, count)
        for counter, count in usage.token_counts.items()
        if counter in observed
    )


def run_usage_chips(run: TrajectoryRun) -> list[str]:
    """Build the pills a run's own usage summary is read as."""
    usage = run.run_usage
    if usage is None:
        return []
    chips = [usage_chip(model) for model in usage.models]
    total = usage.total_tokens
    chips.append(usage_chip(
        "total unknown" if total is None
        else f"total {formatting.fmt_num(total)} tok",
    ))
    chips.extend(usage_chip(counted) for counted in counter_texts(usage))
    if usage.turns is not None:
        chips.append(usage_chip(f"{usage.turns} turns"))
    chips.append(usage_chip(cost_text.cost_text(usage.cost_evidence), "cost"))
    rates = cost_text.rates_text(usage.cost_evidence)
    if rates:
        chips.append(usage_chip(rates))
    return chips


def run_usage_note(run: TrajectoryRun) -> str:
    """Say how the row relates to the strips, and why a total is unknown."""
    sentences = [_RUN_COST_NOTE, _TURNS_NOTE if run.turns else _NO_TURNS_NOTE]
    usage = run.run_usage
    if usage is not None and usage.total_tokens is None:
        missing = any(
            usage.token_counts.get(counter) is None
            for counter in usage.token_evidence.observed
        )
        sentences.append(_MISSING_COUNT_NOTE if missing else _UNKNOWN_TOTAL_NOTE)
    elif usage is not None and (
        usage.token_evidence.cache_overlap == usage_tokens.WITHIN_INPUT
    ):
        sentences.append(_WITHIN_INPUT_NOTE)
    return " ".join(sentences)


def run_usage_html(run: TrajectoryRun) -> str:
    """Render run-level usage chips and their accuracy note."""
    if run.run_usage is None:
        return ""
    chips_html = "".join(run_usage_chips(run))
    row_html = (
        '<div class="orch-traj-chips"><span class="lbl">Run usage</span>'
        f"{chips_html}</div>"
    )
    return (
        f'{row_html}<p class="orch-traj-usage-note">'
        f"{html.escape(run_usage_note(run))}</p>"
    )


def turn_usage_html(usage: TurnUsageView) -> str:
    """Render compact usage for one assistant turn, its estimate's basis too."""
    segments = []
    if usage.model:
        segments.append(
            f'<span class="orch-traj-turn-model">{html.escape(usage.model)}</span>',
        )
    segments.extend(
        f"<span>{html.escape(counted)}</span>"
        for counted in counter_texts(usage)
    )
    rates = cost_text.rates_text(usage.cost_evidence)
    rates_title = f' title="{html.escape(rates)}"' if rates else ""
    estimate = cost_text.cost_text(usage.cost_evidence, decimals=4)
    segments.append(f"<span{rates_title}>{html.escape(estimate)}</span>")
    cache_hit = (
        '<span class="orch-traj-cache-hit">cache hit</span>'
        if (usage.cache_read_tokens or 0) > 0
        else ""
    )
    return (
        '<div class="orch-traj-turn">'
        f"{USAGE_SEPARATOR.join(segments)}{cache_hit}</div>"
    )


def _counter_text(counter: str, count: int | None) -> str:
    spelled = "unknown" if count is None else formatting.fmt_num(count)
    return f"{_COUNTER_LABELS[counter]} {spelled}"
