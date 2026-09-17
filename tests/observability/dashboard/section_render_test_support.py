# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The page surface a section pass draws onto, and the rows it draws.

Streamlit and pandas live in the optional `dashboard` group and every panel is
handed its own, so a pass over the sections beneath the figure cards runs
end-to-end against the stand-ins here in an install carrying neither. The page
is the chrome recorder next door grown to the rest of that surface: every line
a panel puts on screen -- markup, notice, caption, subheading, and the label a
fold-out names itself by -- lands in the one stream, in the order it was
written, which is what makes the order the sections were drawn in readable off
the page rather than inferred from which owner was called. A table is kept
apart from that stream, because a frame is the rows themselves rather than a
line on screen.

The rows answer the question the name-answering reads next door cannot: a
section pass has to render them, so each read carries a word none of the others
does -- the cohort's backend, the matrix's skill, the adopted skill -- and a
view drawn from the wrong family reports a word its own rows never held.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.run_models import AgentExitRow
from orchestrator.observability.analytics.query.skill_models import (
    SkillAdoptionRow,
    SkillTriggerMatrixRow,
    SkillTriggerRateRow,
)
from tests.observability.dashboard.page_render_test_support import (
    WINDOW_START,
    RecordingRegion,
)

# The issue an operator typed into the sidebar, which opens the trace at the
# foot of the page.
ISSUE_NUMBER = 118

# The repository the listed runs were recorded against. No repository is picked
# in the filters, which is what the trace answers with rather than a listing of
# unrelated runs that happen to share a number.
RUN_REPO = "owner/repo"

# The two runs the listing reports, told apart by the issue each ran on.
RUN_ISSUES = (ISSUE_NUMBER, 119)

# What the window totalled, which the footer restates.
AGENT_RUNS = 57

# The cohort the skill cells report over, sized so the numerator stays distinct
# from the denominator.
_COHORT_RUNS = 4

_SKILL_RUNS = 1

_BACKEND = "claude"

_ROLE = "developer"

_PROJECT_LEVEL = "project"

# What one listed run cost and how long it took, so the frame carries readings
# an assertion can tell from the issue numbers beside them.
_RUN_SECONDS = 12.5

_INPUT_TOKENS = 900

_OUTPUT_TOKENS = 100

_RUN_COST = 0.25

# The calls a panel puts a bare line on screen with, all of which land in the
# one stream the page is read back off.
_TEXT_CALLS = frozenset(("caption", "info", "subheader"))

_LISTED_RUN = AgentExitRow(
    ts=WINDOW_START,
    repo=RUN_REPO,
    issue=ISSUE_NUMBER,
    stage="implementing",
    agent_role=_ROLE,
    backend=_BACKEND,
    duration_s=_RUN_SECONDS,
    exit_code=0,
    timed_out=False,
    review_round=1,
    retry_count=0,
    input_tokens=_INPUT_TOKENS,
    output_tokens=_OUTPUT_TOKENS,
    cost_usd=_RUN_COST,
    cost_source="parsed",
)

_TRIGGER_COHORT = SkillTriggerRateRow(
    agent_role=_ROLE,
    backend="codex",
    runs=_COHORT_RUNS,
    skill_runs=_SKILL_RUNS,
    total_triggers=_SKILL_RUNS,
)

_MATRIX_CELL = SkillTriggerMatrixRow(
    repo=RUN_REPO,
    skill="decompose",
    agent_role=_ROLE,
    backend=_BACKEND,
    level=_PROJECT_LEVEL,
    runs=_COHORT_RUNS,
    skill_runs=_SKILL_RUNS,
)

_ADOPTION_CELL = SkillAdoptionRow(
    repo=RUN_REPO,
    skill="develop",
    agent_role=_ROLE,
    backend=_BACKEND,
    level=_PROJECT_LEVEL,
    sessions=_COHORT_RUNS,
    adopted=_SKILL_RUNS,
    invocations=_COHORT_RUNS,
)

# The word each of the card's three reads is told apart by, in the order the
# views reporting them are drawn.
SKILL_READS = (
    _TRIGGER_COHORT.backend,
    _MATRIX_CELL.skill,
    _ADOPTION_CELL.skill,
)


class RecordingPage(RecordingRegion):
    """Fake `st` recording the whole surface a section pass draws onto.

    A fold-out names itself on the page before anything is written inside it,
    so its label joins the same stream the markup does and the order the
    sections were drawn in is read off that one sequence.
    """

    def __init__(self, query_params: dict[str, str] | None = None) -> None:
        super().__init__()
        self.query_params = query_params or {}
        self.frames: list[Any] = []

    def container(self, **options) -> Any:
        return nullcontext()

    def expander(self, label: str, **options) -> Any:
        self.markup.append((label, options))
        return nullcontext()

    def dataframe(self, frame: Any, **options) -> None:
        self.frames.append(frame)

    def write_line(self, line: str) -> None:
        """Record one bare line, which the lookup below routes here."""
        self.markup.append((line, {}))

    def __getattr__(self, attribute_name: str) -> Any:
        if attribute_name in _TEXT_CALLS:
            return self.write_line
        raise AttributeError(attribute_name)


def frames() -> SimpleNamespace:
    """The `pd` handle the listing is framed by, answering with the rows."""
    return SimpleNamespace(DataFrame=list)


def section_rows() -> dict[str, Any]:
    """The rows the panels beneath the figure cards are drawn from."""
    return {
        "agent_exits": [
            replace(_LISTED_RUN, issue=issue) for issue in RUN_ISSUES
        ],
        "skill_adoption_rows": [_ADOPTION_CELL],
        "skill_matrix_rows": [_MATRIX_CELL],
        "skill_rows": [_TRIGGER_COHORT],
        "summary": Summary(total_agent_runs=AGENT_RUNS),
    }
