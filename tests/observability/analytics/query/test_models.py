# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a read hands back: the empty shape, the share, and the alias."""
from __future__ import annotations

import unittest
from dataclasses import is_dataclass
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.activity_models import (
    BackendDailyTokensRow,
    HourlyHeatmapPoint,
    ThroughputDayRow,
)
from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
    CostCoverageRow,
    RepoBreakdownRow,
    ReviewRoundBucketRow,
)
from orchestrator.observability.analytics.query.overview_models import (
    DataExtent,
    FilterOptions,
    Summary,
    TimeSeriesPoint,
)
from orchestrator.observability.analytics.query.run_models import (
    RESULT_FIELD,
    AgentExitRow,
    EventBreakdown,
    IssueEventRow,
    IssueSummaryRow,
    StageBreakdown,
    public_event_result,
)
from orchestrator.observability.analytics.query.skill_models import (
    SkillAdoptionRow,
    SkillTriggerMatrixRow,
    SkillTriggerRateRow,
)

_REPO = "owner/r"

_SKILL = "develop"

_ROLE = "developer"

_BACKEND_CLAUDE = "claude"

_AGENT_EXIT = "agent_exit"

_STAGE_IMPLEMENTING = "implementing"

_APPROVED = "approved"

_RATE = "rate"

_ADOPTION_RATE = "adoption_rate"

_YEAR = 2026

_TS = datetime(_YEAR, 5, 1, tzinfo=UTC)

# One cohort and the part of it that counted, shared by the three shares so the
# expected quotient is written once.
_COHORT = 4

_COUNTED = 3

# Every result model a read family constructs. Declared rather than discovered
# so a row that stops being frozen -- or a new one that never was -- is a
# failure here rather than a page rebinding a column of a cached read.
_RESULT_MODELS = (
    BackendDailyTokensRow,
    HourlyHeatmapPoint,
    ThroughputDayRow,
    BackendEfficiencyRow,
    CostCoverageRow,
    RepoBreakdownRow,
    ReviewRoundBucketRow,
    DataExtent,
    FilterOptions,
    Summary,
    TimeSeriesPoint,
    AgentExitRow,
    EventBreakdown,
    IssueEventRow,
    IssueSummaryRow,
    StageBreakdown,
    SkillAdoptionRow,
    SkillTriggerMatrixRow,
    SkillTriggerRateRow,
)

# A cell whose cohort ran, the share it publishes, and what that share reads:
# the numerator's part of the cohort, or -- for the matrix cell a repo offered
# and nobody reached for -- the `0.0` that is the catalog signal itself.
_DIVIDED_SHARES = (
    (
        SkillTriggerRateRow(
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
            runs=_COHORT,
            skill_runs=_COUNTED,
        ),
        _RATE,
        _COUNTED / _COHORT,
    ),
    (
        SkillTriggerMatrixRow(
            repo=_REPO,
            skill=_SKILL,
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
            runs=_COHORT,
            skill_runs=_COUNTED,
        ),
        _RATE,
        _COUNTED / _COHORT,
    ),
    (
        SkillAdoptionRow(
            repo=_REPO,
            skill=_SKILL,
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
            sessions=_COHORT,
            adopted=_COUNTED,
        ),
        _ADOPTION_RATE,
        _COUNTED / _COHORT,
    ),
    (
        SkillTriggerMatrixRow(
            repo=_REPO,
            skill=_SKILL,
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
            runs=_COHORT,
        ),
        _RATE,
        float(0),
    ),
)

# The same cells with nothing in the denominator: a group the reader emitted
# defensively, and an adoption cell that exists only for its window diagnostics.
_EMPTY_SHARES = (
    (
        SkillTriggerRateRow(
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
            runs=0,
        ),
        _RATE,
    ),
    (
        SkillTriggerMatrixRow(
            repo=_REPO,
            skill=_SKILL,
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
        ),
        _RATE,
    ),
    (
        SkillAdoptionRow(
            repo=_REPO,
            skill=_SKILL,
            agent_role=_ROLE,
            backend=_BACKEND_CLAUDE,
        ),
        _ADOPTION_RATE,
    ),
)

_TRACE_ROW = IssueEventRow(
    ts=_TS,
    event=_AGENT_EXIT,
    stage=_STAGE_IMPLEMENTING,
    duration_s=None,
    event_result=_APPROVED,
    agent_role=_ROLE,
    backend=_BACKEND_CLAUDE,
    exit_code=0,
    cost_usd=None,
)


class FrozenResultTest(unittest.TestCase):
    """No field of a row can be rebound after the reader constructed it.

    The freeze is the shallow dataclass one: it rejects assignment to a field,
    not mutation of what a field holds, so `Summary`'s two breakdown dicts stay
    writable and it is unhashable for the same reason. What it buys is that a
    page handed a row cannot rebind a column another caller is still reading.
    """

    def test_each_model_is_a_frozen_dataclass(self) -> None:
        for model in _RESULT_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(is_dataclass(model))
                self.assertTrue(model.__dataclass_params__.frozen)


class EmptyReadShapeTest(unittest.TestCase):
    """What an unconfigured or empty window is answered with.

    A read with no `ANALYTICS_DB_URL` never dials and returns the bare
    construction, which the page then renders rather than branching on `None`,
    so the defaults are the contract that keeps that page meaningful.
    """

    def test_an_unset_database_zero_values_totals(self) -> None:
        summary = Summary()
        self.assertEqual(summary.total_events, 0)
        self.assertEqual(summary.total_cost_usd, float(0))
        self.assertEqual(summary.timed_out_agent_runs, 0)
        self.assertEqual(summary.by_event, {})
        self.assertEqual(summary.by_stage, {})

    def test_each_summary_owns_its_own_breakdowns(self) -> None:
        # The two dicts come from a factory rather than one shared default, so
        # a caller that fills in one window's counts cannot reach another's.
        first, second = Summary(), Summary()
        first.by_event[_AGENT_EXIT] = 1
        self.assertEqual(second.by_event, {})

    def test_an_empty_window_has_no_selections(self) -> None:
        self.assertEqual(FilterOptions().repos, ())
        self.assertEqual(FilterOptions().agent_roles, ())
        self.assertIsNone(DataExtent().min_ts)
        self.assertIsNone(DataExtent().max_ts)


class DerivedShareTest(unittest.TestCase):
    """The share each skill cell derives, and the cohort it is read against."""

    def test_a_share_divides_by_its_cohort(self) -> None:
        for row, attribute, share in _DIVIDED_SHARES:
            with self.subTest(row=type(row).__name__, share=share):
                self.assertEqual(getattr(row, attribute), share)

    def test_an_empty_cohort_never_divides(self) -> None:
        for row, attribute in _EMPTY_SHARES:
            with self.subTest(row=type(row).__name__):
                self.assertEqual(getattr(row, attribute), float(0))


class TraceCorrelationDefaultTest(unittest.TestCase):
    """A trace row built from the drill-down's own nine fields carries no
    correlation, so a caller that never selected it reads unset values rather
    than a measured zero.
    """

    def test_an_uncorrelated_row_reads_as_unset(self) -> None:
        for field_name in (
            "agent_spec",
            "session_id",
            "resume_session_id",
            "review_round",
            "retry_count",
            "timed_out",
        ):
            with self.subTest(field=field_name):
                self.assertIsNone(getattr(_TRACE_ROW, field_name))
        self.assertEqual(_TRACE_ROW.extras, {})


class TraceResultAliasTest(unittest.TestCase):
    """The trace row's outcome is reachable under the name the page reads."""

    def test_the_alias_answers_with_the_outcome(self) -> None:
        self.assertEqual(getattr(_TRACE_ROW, RESULT_FIELD), _APPROVED)
        self.assertEqual(public_event_result(_TRACE_ROW), _APPROVED)

    def test_the_alias_is_not_a_field_of_its_own(self) -> None:
        # A second field would let the two spellings hold different values;
        # the property is what keeps one stored column behind both names.
        self.assertNotIn(RESULT_FIELD, IssueEventRow.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
