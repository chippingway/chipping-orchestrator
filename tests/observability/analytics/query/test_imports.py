# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the query owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics import query as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
)

_PACKAGE = "orchestrator.observability.analytics.query"

_CONNECTIONS_OWNER = "connections"

_CONNECTION_CACHE_OWNER = "connection_cache"

_EXECUTION_OWNER = "execution"

_CONDITIONS_OWNER = "conditions"

_FILTERS_OWNER = "filters"

_PREDICATES_OWNER = "predicates"

_REQUEST_MODELS_OWNER = "request_models"

_REQUESTS_OWNER = "requests"

_ACTIVITY_MODELS_OWNER = "activity_models"

_COST_MODELS_OWNER = "cost_models"

_OVERVIEW_MODELS_OWNER = "overview_models"

_RUN_MODELS_OWNER = "run_models"

_SKILL_MODELS_OWNER = "skill_models"

_AGENT_EXITS_OWNER = "agent_exits"

_EVENT_BREAKDOWNS_OWNER = "event_breakdowns"

_FILTER_OPTIONS_OWNER = "filter_options"

_ISSUE_EVENTS_OWNER = "issue_events"

_ISSUE_SUMMARIES_OWNER = "issue_summaries"

_QUERY_ROWS_OWNER = "query_rows"

_RAW_READS_OWNER = "raw_reads"

_RAW_VALUES_OWNER = "raw_values"

_BACKEND_EFFICIENCY_OWNER = "backend_efficiency"

_BACKEND_TOKENS_OWNER = "backend_tokens"

_BREAKDOWN_READS_OWNER = "breakdown_reads"

_CACHE_SHARES_OWNER = "cache_shares"

_COST_COVERAGE_OWNER = "cost_coverage"

_HOURLY_HEATMAPS_OWNER = "hourly_heatmaps"

_REVIEW_ROUNDS_OWNER = "review_rounds"

_SKILL_ADOPTION_OWNER = "skill_adoption"

_SKILL_MATRICES_OWNER = "skill_matrices"

_SKILL_PROVENANCE_OWNER = "skill_provenance"

_SKILL_READS_OWNER = "skill_reads"

_SKILL_SESSIONS_OWNER = "skill_sessions"

_SKILL_TRIGGER_RATES_OWNER = "skill_trigger_rates"

_SKILL_VALUES_OWNER = "skill_values"

_KPI_TOTALS_OWNER = "kpi_totals"

_REPO_BREAKDOWNS_OWNER = "repo_breakdowns"

_ROLLUP_READS_OWNER = "rollup_reads"

_ROW_CELLS_OWNER = "row_cells"

_STAGE_BREAKDOWNS_OWNER = "stage_breakdowns"

_SUMMARY_QUERIES_OWNER = "summary_queries"

_SUMMARY_RESULTS_OWNER = "summary_results"

_THROUGHPUT_DAYS_OWNER = "throughput_days"

_TIME_SERIES_OWNER = "time_series"

# The result families, kept as their own group because what they must not do is
# checked separately from what they answer for.
_MODEL_OWNERS = (
    _ACTIVITY_MODELS_OWNER,
    _COST_MODELS_OWNER,
    _OVERVIEW_MODELS_OWNER,
    _RUN_MODELS_OWNER,
    _SKILL_MODELS_OWNER,
)

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the module map, which is what the inventory check compares the directory
# against.
_OWNERS = _MODEL_OWNERS + (
    _AGENT_EXITS_OWNER,
    _BACKEND_EFFICIENCY_OWNER,
    _BACKEND_TOKENS_OWNER,
    _BREAKDOWN_READS_OWNER,
    _CACHE_SHARES_OWNER,
    _CONDITIONS_OWNER,
    _CONNECTION_CACHE_OWNER,
    _CONNECTIONS_OWNER,
    _COST_COVERAGE_OWNER,
    _EVENT_BREAKDOWNS_OWNER,
    _EXECUTION_OWNER,
    _FILTER_OPTIONS_OWNER,
    _FILTERS_OWNER,
    _HOURLY_HEATMAPS_OWNER,
    _ISSUE_EVENTS_OWNER,
    _ISSUE_SUMMARIES_OWNER,
    _KPI_TOTALS_OWNER,
    _PREDICATES_OWNER,
    _QUERY_ROWS_OWNER,
    _RAW_READS_OWNER,
    _RAW_VALUES_OWNER,
    _REPO_BREAKDOWNS_OWNER,
    _REQUEST_MODELS_OWNER,
    _REQUESTS_OWNER,
    _REVIEW_ROUNDS_OWNER,
    _ROLLUP_READS_OWNER,
    _ROW_CELLS_OWNER,
    _SKILL_ADOPTION_OWNER,
    _SKILL_MATRICES_OWNER,
    _SKILL_PROVENANCE_OWNER,
    _SKILL_READS_OWNER,
    _SKILL_SESSIONS_OWNER,
    _SKILL_TRIGGER_RATES_OWNER,
    _SKILL_VALUES_OWNER,
    _STAGE_BREAKDOWNS_OWNER,
    _SUMMARY_QUERIES_OWNER,
    _SUMMARY_RESULTS_OWNER,
    _THROUGHPUT_DAYS_OWNER,
    _TIME_SERIES_OWNER,
)

# What each owner answers for, declared rather than discovered so a new public
# name is a deliberate edit: a second way to open a socket, run a SELECT, or
# spell a window filter is a second place the close, the error wrapping, or the
# cleared-multiselect contract could disagree. The dialing owner is the error
# type and the two factories under it, plus the two judgments a caller makes
# about a connection rather than a query; the cache is the scope a thread
# reuses, its teardown, and the entry bookkeeping beneath them; execution is the
# resolved inputs one read carries and the two connection paths a SELECT runs
# through. On the input side, requests is the bind and the two projections a
# family reads back off it, request_models the parts it binds into, filters the
# selection and the builder a clause accumulates in, predicates the one clause
# builder behind the three tables it can be scanned on, and conditions the two
# splices and the exclusion probe. On the result side each family owns the rows
# a page reads back off it -- the time cells, the window frame, the spend
# breakdowns, the run and issue rows plus the accessor behind the trace row's
# `result` alias, and the skill cells. The raw reads are the six public
# entry points under raw_reads, one projection owner per family beneath them,
# the named rows the widest SELECT lists are read back through, and the
# coercions a raw column is narrowed by. The rollup reads are the seven public
# entry points under rollup_reads with one projection owner per read beneath
# them, and the breakdown reads the four under breakdown_reads with one owner
# each beneath them too, plus the cell readings a row from either is narrowed
# by. The skill reads are the three under skill_reads, the aggregate owner
# behind each, the session identity and evidence the adoption one is built on,
# the catalog scan and the level lookup an unclassified load is filled from,
# and the payload coercion, cohort, and ranking all of them share. Constants --
# the rollup view name, the two request field names, the `result` attribute
# name, the filter-option columns, the two sort modes, the terminal throughput
# stages, the token-share fragments, the finished-run condition, the two skill
# row caps, the session column offsets, the summary cast list, and the
# signatures themselves -- are not reported here: the check reads `__module__`,
# which only a class or function carries, which is why the token-share owner
# declares an empty surface.
_SURFACES = MappingProxyType({
    _CONNECTIONS_OWNER: (
        "AnalyticsReadError",
        "close_quietly",
        "default_connect",
        "default_persistent_connect",
        "is_broken_connection_exc",
    ),
    _CONNECTION_CACHE_OWNER: (
        "analytics_connection",
        "cached_entry",
        "close_thread_local_connection",
        "connection_for_url",
        "discard_broken_connection",
        "open_cached_connection",
    ),
    _EXECUTION_OWNER: (
        "ReadQuery",
        "connect_for_read",
        "execute_select",
        "read_connection",
        "select_rows",
    ),
    _CONDITIONS_OWNER: (
        "agent_event_excluded",
        "append_where_condition",
        "prepend_where_condition",
    ),
    _FILTERS_OWNER: (
        "WhereBuilder",
        "WindowFilters",
    ),
    _PREDICATES_OWNER: (
        "build_rollup_window_where",
        "build_view_window_where",
        "build_where",
        "build_window_where",
        "day_bound",
    ),
    _REQUEST_MODELS_OWNER: (
        "ReadConnection",
        "ReadFilters",
        "ReadOptions",
        "ReadRequest",
    ),
    _REQUESTS_OWNER: (
        "bind_read_request",
        "resolve_read_query",
        "window_filters",
    ),
    _ACTIVITY_MODELS_OWNER: (
        "BackendDailyTokensRow",
        "HourlyHeatmapPoint",
        "ThroughputDayRow",
    ),
    _COST_MODELS_OWNER: (
        "BackendEfficiencyRow",
        "CostCoverageRow",
        "RepoBreakdownRow",
        "ReviewRoundBucketRow",
    ),
    _OVERVIEW_MODELS_OWNER: (
        "DataExtent",
        "FilterOptions",
        "Summary",
        "TimeSeriesPoint",
    ),
    _RUN_MODELS_OWNER: (
        "AgentExitRow",
        "EventBreakdown",
        "IssueEventRow",
        "IssueSummaryRow",
        "StageBreakdown",
        "public_event_result",
    ),
    _SKILL_MODELS_OWNER: (
        "SkillAdoptionRow",
        "SkillTriggerMatrixRow",
        "SkillTriggerRateRow",
    ),
    _AGENT_EXITS_OWNER: (
        "agent_exit_from_row",
        "recent_agent_exit_rows",
    ),
    _EVENT_BREAKDOWNS_OWNER: (
        "event_breakdown_rows",
    ),
    _FILTER_OPTIONS_OWNER: (
        "filter_options_from_rows",
        "filter_options_sql",
    ),
    _ISSUE_EVENTS_OWNER: (
        "issue_event_from_row",
        "issue_event_rows",
    ),
    _ISSUE_SUMMARIES_OWNER: (
        "issue_order_sql",
        "issue_summary_from_row",
        "issue_summary_rows",
        "issues_sql",
    ),
    _QUERY_ROWS_OWNER: (
        "AgentExitQueryRow",
        "IssueEventQueryRow",
        "IssueSummaryQueryRow",
        "ReviewRoundQueryRow",
        "agent_exit_row",
        "issue_event_row",
        "issue_summary_row",
        "review_round_row",
    ),
    _RAW_READS_OWNER: (
        "get_data_extent",
        "get_event_breakdown",
        "get_filter_options",
        "get_issue_events",
        "get_issues",
        "get_recent_agent_exits",
    ),
    _RAW_VALUES_OWNER: (
        "bool_or_none",
        "decoded_json",
        "empty_filter_selected",
        "float_or_none",
        "int_or_none",
        "json_object",
        "row_int",
    ),
    _ROLLUP_READS_OWNER: (
        "get_backend_efficiency",
        "get_kpi_prev",
        "get_repo_breakdown",
        "get_stage_breakdown",
        "get_summary",
        "get_throughput_breakdown",
        "get_time_series",
    ),
    _SUMMARY_QUERIES_OWNER: (
        "build_summary_sql",
        "build_summary_where",
        "query_summary_rows",
    ),
    _SUMMARY_RESULTS_OWNER: (
        "ordered_summary_counts",
        "summary_count_order",
        "summary_from_rows",
        "summary_total_values",
        "summary_totals_row",
    ),
    _KPI_TOTALS_OWNER: (
        "kpi_prev_sql",
        "kpi_prev_summary",
    ),
    _TIME_SERIES_OWNER: (
        "time_series_from_row",
        "time_series_rows",
    ),
    _STAGE_BREAKDOWNS_OWNER: (
        "stage_breakdown_from_row",
        "stage_breakdown_rows",
        "stage_breakdown_sql",
    ),
    _BACKEND_EFFICIENCY_OWNER: (
        "backend_efficiency_from_row",
        "backend_efficiency_rows",
        "backend_efficiency_sql",
    ),
    _REPO_BREAKDOWNS_OWNER: (
        "repo_breakdown_rows",
    ),
    _THROUGHPUT_DAYS_OWNER: (
        "selected_throughput_stages",
        "throughput_from_row",
        "throughput_rows",
    ),
    _BREAKDOWN_READS_OWNER: (
        "get_backend_daily_tokens",
        "get_cost_coverage",
        "get_hourly_heatmap",
        "get_review_round_breakdown",
    ),
    _REVIEW_ROUNDS_OWNER: (
        "review_round_from_row",
        "review_round_rows",
        "review_round_sql",
    ),
    _COST_COVERAGE_OWNER: (
        "cost_coverage_from_row",
        "cost_coverage_rows",
    ),
    _BACKEND_TOKENS_OWNER: (
        "backend_daily_token_rows",
        "backend_daily_tokens_from_row",
    ),
    _HOURLY_HEATMAPS_OWNER: (
        "hourly_heatmap_from_row",
        "hourly_heatmap_rows",
    ),
    _SKILL_READS_OWNER: (
        "get_skill_adoption",
        "get_skill_trigger_matrix",
        "get_skill_trigger_rates",
    ),
    _SKILL_TRIGGER_RATES_OWNER: (
        "skill_trigger_rate_from_row",
        "skill_trigger_rate_rows",
        "skill_trigger_rate_sql",
    ),
    _SKILL_MATRICES_OWNER: (
        "SkillMatrixCounts",
        "skill_run_rows",
        "skill_trigger_matrix_rows",
    ),
    _SKILL_PROVENANCE_OWNER: (
        "SkillProvenance",
        "repo_skill_provenance",
        "skill_catalog",
        "skill_catalog_rows",
    ),
    _SKILL_ADOPTION_OWNER: (
        "SkillAdoption",
        "skill_adoption_rows",
    ),
    _SKILL_SESSIONS_OWNER: (
        "SessionEvidence",
        "SkillWindowRun",
        "skill_history_rows",
        "skill_session_evidence",
        "skill_session_key",
        "skill_window_rows",
        "skill_window_run",
    ),
    _SKILL_VALUES_OWNER: (
        "SkillCell",
        "as_skill_levels",
        "as_skill_names",
        "label_or_unknown",
        "leveled_skills",
        "skill_cohort",
    ),
    _CACHE_SHARES_OWNER: (),
    _ROW_CELLS_OWNER: (
        "cost_cell",
        "day_value",
        "row_value",
    ),
})

# What an owner here may reach: its siblings and the configuration owner both
# connection paths resolve an omitted `db_url=` through.
_REACHABLE_PREFIXES = (
    _PACKAGE,
    "orchestrator.observability.analytics.config",
    "orchestrator.observability",
    "orchestrator._package",
)

# Everything an import inside this tree plants before the owner's own module:
# the root package and the three above the owner. A result model is what the
# import-cost check reads against it.
_PACKAGE_CHAIN = frozenset((
    "orchestrator",
    "orchestrator.observability",
    "orchestrator.observability.analytics",
    _PACKAGE,
))

def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


def _defined_here(owner: str) -> tuple[str, ...]:
    """Public names the owner defines, as opposed to ones it imported."""
    module = import_module(_qualified(owner))
    return tuple(sorted(
        name
        for name, member in module.__dict__.items()
        if not name.startswith("_")
        and getattr(member, "__module__", None) == module.__name__
    ))


class OwnerInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))


class PublicSurfaceTest(unittest.TestCase):
    """Each owner answers for a narrow, declared surface."""

    def test_public_names_are_the_declared_ones(self) -> None:
        for owner, surface in _SURFACES.items():
            with self.subTest(owner=owner):
                self.assertEqual(_defined_here(owner), surface)

    def test_no_surface_is_declared_twice(self) -> None:
        # The package initializer is a marker, so a name is reached on the
        # owner that defines it rather than published a second time above it.
        self.assertNotIn("__all__", _package.__dict__)
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertNotIn(
                    "__all__", import_module(_qualified(owner)).__dict__,
                )


class LayeringTest(unittest.TestCase):
    """The owners reach only what they compose, and never the driver."""

    def test_no_owner_reaches_past_what_it_composes(self) -> None:
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(_REACHABLE_PREFIXES)
                        or imported == "orchestrator",
                        f"{owner} reaches {imported}",
                    )


class ResultModelImportCostTest(unittest.TestCase):
    """A result model is a plain dataclass, so importing one reaches nothing.

    Not a weaker restatement of the layering check above: that one bounds
    where an owner may reach, while a page or a test that only consumes the
    rows must not pay for a connection factory, the configuration behind an
    omitted `db_url=`, or the driver those two stand in front of.
    """

    def test_a_model_owner_costs_its_chain_only(self) -> None:
        for owner in _MODEL_OWNERS:
            with self.subTest(owner=owner):
                self.assertEqual(
                    _imported_orchestrator_modules(_qualified(owner)),
                    _PACKAGE_CHAIN | {_qualified(owner)},
                )


if __name__ == "__main__":
    unittest.main()
