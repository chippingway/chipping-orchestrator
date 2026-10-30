# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issues a window spent the most on, ranked into one table.

The panel is inline HTML rather than `st.dataframe` because two of its six
columns are not text. Spend is drawn twice -- as the amount and as a bar under
the repository and issue number naming the row -- and that bar is a share of
the widest row in this table rather than of any window-wide figure, so a window
whose issues were all cheap still reads as a ranking rather than as a column of
stubs. A window whose rows state no amount has no widest bar to be a share of,
so the ranking divides by one and every bar renders empty rather than the panel
raising on a page opened to find out that nothing was priced.

An issue's spend is the cohort its runs fold to, so its cell is worded the way
the overview words a window's: the figure, then the basis it is stated on -- a
CLI-reported amount, one provider's API token estimate, or a blended total with
each basis's amount beside it -- and why it falls short of complete spend, the
unpriced or partly priced runs and the runs stating no cost evidence counted.
The bar is sized by the amount the read ranked the row on, a subtotal at its
known part, and an amount short of complete spend is drawn as an open bar, so
neither the figure nor its bar passes for the whole. An issue whose runs state
no amount reads as unpriced, unknown, or no usage, and one with no run at all
as having none -- never as a zero.

Two readings decide what a row says about rework, and both are judgements
rather than counts. A review round is drawn in the warn tone from the third one
on, because that is where an issue has been round-tripped past what the flow
expects and is worth an operator's eye; below it the number is plain, which is
what keeps the tone meaning something when it does appear. A row with no failed
run reads `clean` rather than a zero, since the column answers whether the
issue needs looking at rather than how many runs it took to get there.

Every reading a cell is built from, and the stylesheet, header, and body it is
assembled into, are the shared table's, so what is decided here is the six
columns, the rules the pills and bars are painted by, and what one row says.
The repository naming a row arrives off the sink rather
than out of this repository, so it is escaped into the markup a browser is
asked to interpret.
"""
from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass

from orchestrator.observability.analytics.query.run_models import (
    IssueSummaryRow,
)
from orchestrator.observability.dashboard import spend_text
from orchestrator.observability.dashboard.tables import (
    int_or_zero,
    relative_width_pct,
    short_repo_name,
    table_css,
    table_head_html,
    table_html,
)

ISSUES_TABLE_COLUMNS = (
    ("Issue", False),
    ("Cost", True),
    ("Runs", True),
    ("Review rds", True),
    ("Retries", True),
    ("Status", True),
)
ISSUES_TABLE_EXTRA_CSS = """
  .orch-issues td.strong { font-weight: 600; }
  .orch-issue-cell { display: flex; flex-direction: column; gap: 4px; }
  .orch-issue-name { color: var(--orch-ink); font-weight: 500; }
  .orch-issue-num { color: var(--orch-muted); font-weight: 400; margin-left: 2px; }
  .orch-issue-bar { display: block; height: 4px; border-radius: 2px;
    background: var(--orch-grid); overflow: hidden; }
  .orch-issue-bar > span { display: block; height: 100%;
    background: var(--orch-accent); border-radius: 2px; }
  .orch-issue-bar > span.partial { background: transparent;
    box-shadow: inset 0 0 0 1px var(--orch-accent); }
  .orch-issue-cost-note { display: block; color: var(--orch-muted);
    font-size: 11px; font-weight: 400; white-space: normal;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
  .orch-pill { display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 11.5px; font-weight: 500;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
  .orch-pill.ok { background: rgba(26, 163, 154, 0.14); color: var(--orch-success); }
  .orch-pill.bad { background: rgba(217, 83, 74, 0.14); color: var(--orch-danger); }
  .orch-badge-warn { color: var(--orch-warn); font-weight: 600; }
"""


def issue_status_pill(failed: int) -> str:
    """The pill a row's run health is read off, clean or a failure count."""
    if failed:
        return f'<span class="orch-pill bad">{failed} fail</span>'
    return '<span class="orch-pill ok">clean</span>'


def review_round_html(review_rounds: int) -> str:
    """The round count, toned to warn once an issue is past a third pass."""
    if review_rounds >= 3:
        return f'<span class="orch-badge-warn">{review_rounds}</span>'
    return str(review_rounds)


@dataclass(frozen=True)
class IssueRowView:
    short_repo: str
    cost_figure: str
    cost_note: str
    bar_pct: float
    partial: bool
    review_rounds: int
    retries: int
    failed: int


def issue_row_view(row: IssueSummaryRow, max_cost: float) -> IssueRowView:
    """Reduce one read row to the readings its cells are drawn from."""
    evidence = row.cost.evidence
    return IssueRowView(
        short_repo=short_repo_name(row.repo),
        cost_figure=spend_text.spend_figure(row.cost),
        cost_note=spend_text.spend_note(row.cost),
        bar_pct=relative_width_pct(float(row.stated_cost_usd or 0), max_cost),
        partial=evidence.total_usd is not None and evidence.complete_usd is None,
        review_rounds=int_or_zero(row.max_review_round),
        retries=int_or_zero(row.max_retry_count),
        failed=int(row.failed_agent_runs or 0),
    )


def issue_cost_html(row_view: IssueRowView) -> str:
    """The cost cell's contents: the figure, with its note beneath it where it has one."""
    figure = html.escape(row_view.cost_figure)
    if not row_view.cost_note:
        return figure
    note = html.escape(row_view.cost_note)
    return f'{figure}<span class="orch-issue-cost-note">{note}</span>'


def issue_table_row_html(row: IssueSummaryRow, *, max_cost: float) -> str:
    """Render one issue as a row, its bar sized against the costliest."""
    row_view = issue_row_view(row, max_cost)
    bar_class = ' class="partial"' if row_view.partial else ""
    return (
        '<tr><td><div class="orch-issue-cell">'
        f'<span><span class="orch-issue-name">{html.escape(row_view.short_repo)}</span>'
        f' <span class="orch-issue-num">#{int(row.issue)}</span></span>'
        f'<span class="orch-issue-bar"><span{bar_class} style="width:{row_view.bar_pct:.1f}%">'
        "</span></span></div></td>"
        f'<td class="r strong">{issue_cost_html(row_view)}</td>'
        f'<td class="r">{int(row.agent_exits or 0)}</td>'
        f'<td class="r">{review_round_html(row_view.review_rounds)}</td>'
        f'<td class="r">{row_view.retries}</td>'
        f'<td class="r">{issue_status_pill(row_view.failed)}</td></tr>'
    )


def issues_table_html(rows: Sequence[IssueSummaryRow]) -> str:
    """Render the most-expensive-issues table to inline HTML."""
    max_cost = max(
        (float(row.stated_cost_usd or 0) for row in rows),
        default=0,
    ) or 1.0
    return table_html(
        table_class="orch-issues",
        css=table_css(
            "orch-issues",
            extra_rules=ISSUES_TABLE_EXTRA_CSS,
        ),
        head=table_head_html(ISSUES_TABLE_COLUMNS),
        rows=[issue_table_row_html(row, max_cost=max_cost) for row in rows],
    )
