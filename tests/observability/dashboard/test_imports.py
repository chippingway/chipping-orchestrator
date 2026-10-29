# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the dashboard owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability import dashboard as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _run_import_probe,
)

_PACKAGE = "orchestrator.observability.dashboard"

_ACTIVITY_PANEL_OWNER = "activity_panel"

_BACKEND_CARD_OWNER = "backend_card"

_BREAKDOWNS_OWNER = "breakdowns"

_CARD_HTML_OWNER = "card_html"

_CHART_SECTIONS_OWNER = "chart_sections"

_COVERAGE_CARD_OWNER = "coverage_card"

_CSS_OWNER = "css"

_DATE_CONTROLS_OWNER = "date_controls"

_DATE_FILTER_OWNER = "date_filter"

_DISPATCH_OWNER = "dispatch"

_DRILLDOWN_OWNER = "drilldown"

_FANOUT_OWNER = "fanout"

_FILTER_BINDING_OWNER = "filter_binding"

_FILTERS_OWNER = "filters"

_FORMATTING_OWNER = "formatting"

_INSIGHTS_OWNER = "insights"

_ISSUE_COST_PANEL_OWNER = "issue_cost_panel"

_ISSUE_TABLE_OWNER = "issue_table"

_KPIS_OWNER = "kpis"

_KPI_SERIES_OWNER = "kpi_series"

_KPI_STRIP_OWNER = "kpi_strip"

_LAYOUT_OWNER = "layout"

_PAGE_CONTROLS_OWNER = "page_controls"

_PAGE_MODELS_OWNER = "page_models"

_PAGE_PIPELINE_OWNER = "page_pipeline"

_PAGE_SECTIONS_OWNER = "page_sections"

_PAGE_STATES_OWNER = "page_states"

_PALETTE_OWNER = "palette"

_READ_MODE_OWNER = "read_mode"

_READ_PLAN_OWNER = "read_plan"

_RECENT_RUNS_OWNER = "recent_runs"

_RELIABILITY_PANEL_OWNER = "reliability_panel"

_RENDER_CONFIG_OWNER = "render_config"

_ROLLUPS_OWNER = "rollups"

_SCOPED_READS_OWNER = "scoped_reads"

_SKILL_ADOPTION_OWNER = "skill_adoption"

_SKILL_ADOPTION_COLUMNS_OWNER = "skill_adoption_columns"

_SKILL_ADOPTION_HEADERS_OWNER = "skill_adoption_headers"

_SKILL_ADOPTION_ROWS_OWNER = "skill_adoption_rows"

_SKILL_ADOPTION_SORT_OWNER = "skill_adoption_sort"

_SKILL_MATRIX_OWNER = "skill_matrix"

_SKILL_MATRIX_COLUMNS_OWNER = "skill_matrix_columns"

_SKILL_MATRIX_HEADERS_OWNER = "skill_matrix_headers"

_SKILL_MATRIX_ROWS_OWNER = "skill_matrix_rows"

_SKILL_MATRIX_SORT_OWNER = "skill_matrix_sort"

_SKILL_PANEL_OWNER = "skill_panel"

_SKILL_TRIGGER_PANEL_OWNER = "skill_trigger_panel"

_SKILL_TRIGGER_TABLE_OWNER = "skill_trigger_table"

_SKILLS_OWNER = "skills"

_SPARKLINE_HTML_OWNER = "sparkline_html"

_SPARKLINE_POINTS_OWNER = "sparkline_points"

_STAGE_COST_PANEL_OWNER = "stage_cost_panel"

_STATIC_METADATA_OWNER = "static_metadata"

_SUMMARY_HTML_OWNER = "summary_html"

_TABLES_OWNER = "tables"

_THEME_OWNER = "theme"

_TOKENS_OWNER = "tokens"

_USAGE_PANEL_OWNER = "usage_panel"

_WINDOWS_OWNER = "windows"

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the module map, which is what the inventory check compares the directory
# against.
_OWNERS = (
    _ACTIVITY_PANEL_OWNER,
    _BACKEND_CARD_OWNER,
    _BREAKDOWNS_OWNER,
    _CARD_HTML_OWNER,
    _CHART_SECTIONS_OWNER,
    _COVERAGE_CARD_OWNER,
    _CSS_OWNER,
    _DATE_CONTROLS_OWNER,
    _DATE_FILTER_OWNER,
    _DISPATCH_OWNER,
    _DRILLDOWN_OWNER,
    _FANOUT_OWNER,
    _FILTER_BINDING_OWNER,
    _FILTERS_OWNER,
    _FORMATTING_OWNER,
    _INSIGHTS_OWNER,
    _ISSUE_COST_PANEL_OWNER,
    _ISSUE_TABLE_OWNER,
    _KPIS_OWNER,
    _KPI_SERIES_OWNER,
    _KPI_STRIP_OWNER,
    _LAYOUT_OWNER,
    _PAGE_CONTROLS_OWNER,
    _PAGE_MODELS_OWNER,
    _PAGE_PIPELINE_OWNER,
    _PAGE_SECTIONS_OWNER,
    _PAGE_STATES_OWNER,
    _PALETTE_OWNER,
    _READ_MODE_OWNER,
    _READ_PLAN_OWNER,
    _RECENT_RUNS_OWNER,
    _RELIABILITY_PANEL_OWNER,
    _RENDER_CONFIG_OWNER,
    _ROLLUPS_OWNER,
    _SCOPED_READS_OWNER,
    _SKILL_ADOPTION_OWNER,
    _SKILL_ADOPTION_COLUMNS_OWNER,
    _SKILL_ADOPTION_HEADERS_OWNER,
    _SKILL_ADOPTION_ROWS_OWNER,
    _SKILL_ADOPTION_SORT_OWNER,
    _SKILL_MATRIX_OWNER,
    _SKILL_MATRIX_COLUMNS_OWNER,
    _SKILL_MATRIX_HEADERS_OWNER,
    _SKILL_MATRIX_ROWS_OWNER,
    _SKILL_MATRIX_SORT_OWNER,
    _SKILL_PANEL_OWNER,
    _SKILL_TRIGGER_PANEL_OWNER,
    _SKILL_TRIGGER_TABLE_OWNER,
    _SKILLS_OWNER,
    _SPARKLINE_HTML_OWNER,
    _SPARKLINE_POINTS_OWNER,
    _STAGE_COST_PANEL_OWNER,
    _STATIC_METADATA_OWNER,
    _SUMMARY_HTML_OWNER,
    _TABLES_OWNER,
    _THEME_OWNER,
    _TOKENS_OWNER,
    _USAGE_PANEL_OWNER,
    _WINDOWS_OWNER,
)

# What each owner answers for, declared rather than discovered so a second way
# to resolve a color, lay a chart out, shorten a number, spell a window, lay
# out the bar one is picked in, offer the presets that name one, turn the days
# typed into that bar back into a window,
# normalize a selection, key a cached read, read that key back as a read's
# filters, decide which way a load's reads are issued, stage that load into the
# two waves it is drawn in, run one wave of them that way, drive both waves
# around the render between them, check out the connection one of them runs on,
# draw a headline or lifecycle section from one of the seven reads behind it, a
# comparison panel from one of the six, or a skill panel from one of the three,
# open a page on the extent behind its filter bar, interrupt one with a banner,
# reduce its window to the four numbers a headline tile reports, plot the days
# behind three of them, assemble all four into the strip a page opens with,
# place one of those days on the line under a tile and write that line as the
# SVG the tile carries, banner what the database holds above that strip,
# restate what a run's filters narrowed it to, and annotate one of its tiles
# with the move it made,
# head a card and draw that banner and those numbers as the markup a browser
# reads, list a panel's rows in the compact table beside them, rank a window's
# issues into the first of those panels, report a cohort's skill-trigger rate
# in the second, read a page URL back as the order the third or the fourth is
# drawn in, head one of their columns as the control that writes that URL, say
# what one of their cells was offered, loaded, or triggered, assemble either
# panel those cells are sorted into, draw the card the two invocation views
# open and the adoption one folds under by source level together with the
# caption that names what a quiet window did record, draw the trigger-rate card
# a caller reaching past that one still gets, pair the lifecycle bars a window's spend is split across
# at the one height both are drawn at, rank that window's issues beside the
# backends that ran them, set that window's repositories beside the tiles and
# days the runs behind them are read for, lay the tokens under all of those out
# by the hour and weekday they landed on and name the zone that grid is read
# in, weigh
# one backend's spend against the
# tokens and runs behind it, size a window's
# priced share into one bar, read one of the runs under all of them back as
# the columns it is scanned by, trace one issue's events under that listing,
# read a historical call back as the state that trace is drawn from, draw the
# card above all of them on the stack an operator picked and total a day's
# tokens per backend for it, answer a database with nothing in it or a window
# matching nothing with the state a page leaves through, close a page that did
# draw on the span and run count it was drawn over, offer the sidebar a run of
# that page is narrowed in, read the zone its timestamps are displayed against
# back off the session, resolve one pass through those controls into what every
# read is bounded by, stage the load they open, fill the two slots that band
# left above the panels and raise the banners between them, drive the staged
# load the strip is drawn inside, stack the five figure cards that load
# answers for, close the page on the four panels beneath them, or carry what a
# render was
# narrowed to from
# the controls at the top of the page down to those panels is a
# deliberate edit rather than a place two panels -- or the reads' `ts < end`
# bound and the cache's tri-state -- could disagree. Four owners report
# nothing. Three of them because the check reads `__module__`, which only a
# class or a function
# carries: the geometry owner's whole surface is its measurements and the two
# font stacks, the stylesheet owner's is one string, and the render-config
# owner's is the single mapping every figure is drawn under. The fourth
# declares nothing of its own at all -- the theme a page hands every panel it
# draws is the five style owners read back under one name, so each value on it
# is the object one of them already holds. The palette's
# chrome
# colors and seven dimension maps, the preset vocabulary the window owner
# decides together with the three of those the control owner beside it offers
# inline, the read-mode owner's knob name, truthy spellings, worker cap,
# refusal message, and the flag its import binds, the alias the fan-out owner
# names a reader by, the TTL the read plan caches a wave's entries under, the
# spinner message the dispatch owner opens a load under together with the
# mapping a wave hands back and the logger its load line is emitted on, the cap
# the rollup owner reads a run list under, the two bands the insight owner
# raises a banner at and the spellings an unpriced run reaches it under, the
# columns the issue table is headed by and the rules its bars and pills are
# painted from, the columns and rate-bar rules the skill-trigger table beside it
# is drawn with together with the label it reads a category the sink left empty
# under, the row and base measurements the paired lifecycle bars are sized from
# and the notice the backend cards beside that ranking answer a window with no
# run with,
# the ten columns the adoption table is read across and the eight the
# trigger matrix is, each with the two query parameters its headings write and
# the counts among them a first click sorts down, the rules either scopes to
# its own class and the notice each renders in place of a table, the notice the
# trigger-rate card answers a window with no run at all with, the KPI
# owner's ranking cap and rework buckets, the floor the projection owner
# clamps a flat window's span at, the default box the rendering owner beside it
# draws a line in together with the keyword surface it binds one through, the
# two historical surfaces the chrome owner past them binds its pill and its
# banner through, the
# triple the
# strip owner hands its four entries back as, the label the run listing is
# collapsed under together with the notice a window with no run renders
# instead, the notice the trace beneath that listing answers a number typed
# before a repository with and the declared signature the adapter beside it
# binds a historical call through, the two messages an un-ingested database and
# a window nothing matched are answered with, the heading the sidebar is titled
# by together with the option its repository box names no repository under and
# the three help texts its other controls are qualified by, the two stack modes
# the hero card is drawn
# in together with the title, subtitle, and toggle label above them and the two
# keys the picked one is remembered and keyed by, and the TTL the metadata owner
# caches under are all
# invisible here for the same reason.
_SURFACES = MappingProxyType({
    _ACTIVITY_PANEL_OWNER: ("card_subtitle", "render_activity_heatmap"),
    _BACKEND_CARD_OWNER: (
        "BackendEfficiencyMetrics",
        "backend_efficiency_card_html",
        "backend_efficiency_metrics",
        "safe_ratio",
    ),
    _BREAKDOWNS_OWNER: (
        "read_backend_daily_tokens",
        "read_backend_efficiency",
        "read_cost_coverage",
        "read_hourly_heatmap",
        "read_repo_breakdown",
        "read_throughput",
    ),
    _CARD_HTML_OWNER: (
        "card_header_html",
        "insights_html",
        "reliability_tiles_html",
    ),
    _COVERAGE_CARD_OWNER: (
        "CoverageSegment",
        "cost_coverage_bar_html",
        "cost_coverage_weights",
        "cost_source_color",
        "coverage_segment",
        "coverage_segments",
    ),
    _CHART_SECTIONS_OWNER: ("render_chart_widgets",),
    _CSS_OWNER: (),
    _DATE_CONTROLS_OWNER: (
        "DateFilterColumns",
        "date_filter_columns",
        "preset_radio_index",
        "render_date_filter_label",
        "render_preset_choice",
    ),
    _DATE_FILTER_OWNER: (
        "initial_filter_window",
        "render_date_filter_bar",
        "render_date_inputs",
    ),
    _DISPATCH_OWNER: (
        "dispatch_reads",
        "log_dashboard_load",
        "run_read_waves",
    ),
    _DRILLDOWN_OWNER: (
        "drilldown_event_row",
        "read_issue_trace",
        "render_drilldown_view",
    ),
    _FANOUT_OWNER: ("fan_out_reads",),
    _FILTER_BINDING_OWNER: (
        "filter_list",
        "read_filter_kwargs",
        "read_filtered",
    ),
    _FILTERS_OWNER: (
        "DashboardCacheKey",
        "cache_key",
        "format_tz_offset",
        "parse_issue_number",
        "resolve_stage_filter",
        "shift_ts",
    ),
    _FORMATTING_OWNER: (
        "fmt_money",
        "fmt_money_exact",
        "fmt_num",
        "fmt_tokens",
    ),
    _INSIGHTS_OWNER: ("InsightBanner", "compute_insights"),
    _ISSUE_COST_PANEL_OWNER: ("render_issues_and_backends",),
    _ISSUE_TABLE_OWNER: (
        "IssueRowView",
        "issue_row_view",
        "issue_status_pill",
        "issue_table_row_html",
        "issues_table_html",
        "review_round_html",
    ),
    _KPIS_OWNER: (
        "kpi_delta",
        "reliability_tile_data",
        "rework_totals",
        "top_expensive_issues",
    ),
    _KPI_SERIES_OWNER: (
        "DailyKpiSeries",
        "daily_kpi_series",
        "daily_point_totals",
        "summary_total_tokens",
        "throughput_totals",
        "time_series_total_tokens",
    ),
    _KPI_STRIP_OWNER: (
        "KpiInputs",
        "KpiTotals",
        "build_kpi_strip_data",
        "cost_per_resolved",
        "kpi_strip_entries",
        "kpi_totals",
    ),
    _LAYOUT_OWNER: ("base_layout",),
    _PAGE_CONTROLS_OWNER: (
        "SidebarSelections",
        "prepare_dashboard_page",
        "render_dashboard_controls",
        "render_sidebar_filters",
        "resolve_dashboard_filters",
        "timezone_choice",
    ),
    _PAGE_MODELS_OWNER: (
        "DashboardControls",
        "DashboardFilters",
        "DashboardKpis",
        "DashboardModules",
        "DashboardPage",
        "LoadedDashboard",
        "ReliabilityPanelData",
    ),
    _PAGE_PIPELINE_OWNER: (
        "load_dashboard_data",
        "render_dashboard_insights",
        "render_first_wave",
        "render_topbar_and_meta",
    ),
    _PAGE_SECTIONS_OWNER: (
        "render_dashboard_widgets",
        "render_remaining_widgets",
    ),
    _PAGE_STATES_OWNER: (
        "render_dashboard_footer",
        "render_empty_window",
        "render_no_data",
    ),
    _PALETTE_OWNER: ("color_for",),
    _READ_MODE_OWNER: (
        "dashboard_parallel_reads_enabled",
        "db_unconfigured_message",
        "parse_parallel_reads_flag",
    ),
    _READ_PLAN_OWNER: (
        "DashboardReadPlan",
        "build_read_keys",
        "first_wave_readers",
        "second_wave_readers",
        "widget_readers",
        "widget_task",
    ),
    _RECENT_RUNS_OWNER: ("recent_run_row", "render_recent_runs"),
    _RELIABILITY_PANEL_OWNER: ("render_repo_and_reliability",),
    _RENDER_CONFIG_OWNER: (),
    _ROLLUPS_OWNER: (
        "read_prev_kpi",
        "read_recent_agent_exits",
        "read_review_round",
        "read_stage_breakdown",
        "read_summary",
        "read_time_series",
        "read_top_cost_issues",
    ),
    _SCOPED_READS_OWNER: ("scoped_read",),
    _SKILL_ADOPTION_OWNER: ("skill_adoption_html",),
    _SKILL_ADOPTION_COLUMNS_OWNER: ("SkillAdoptionColumn",),
    _SKILL_ADOPTION_HEADERS_OWNER: (
        "SkillAdoptionHeaderState",
        "skill_adoption_header_cell",
        "skill_adoption_header_html",
        "skill_adoption_header_state",
    ),
    _SKILL_ADOPTION_ROWS_OWNER: (
        "SkillAdoptionRowView",
        "adoption_count_html",
        "adoption_rate_html",
        "muted_zero_html",
        "skill_adoption_row_html",
        "skill_adoption_row_view",
    ),
    _SKILL_ADOPTION_SORT_OWNER: (
        "default_sort_skill_adoption_rows",
        "parse_skill_adoption_sort",
        "skill_adoption_default_sort_key",
        "sort_skill_adoption_rows",
    ),
    _SKILL_MATRIX_OWNER: ("skill_matrix_html",),
    _SKILL_MATRIX_COLUMNS_OWNER: ("SkillMatrixColumn",),
    _SKILL_MATRIX_HEADERS_OWNER: (
        "SkillMatrixHeaderState",
        "skill_matrix_header_cell",
        "skill_matrix_header_html",
        "skill_matrix_header_state",
    ),
    _SKILL_MATRIX_ROWS_OWNER: (
        "SkillMatrixRowView",
        "muted_zero_html",
        "skill_matrix_row_html",
        "skill_matrix_row_view",
    ),
    _SKILL_MATRIX_SORT_OWNER: (
        "default_sort_skill_matrix_rows",
        "parse_skill_matrix_sort",
        "skill_matrix_default_sort_key",
        "sort_skill_matrix_rows",
    ),
    _SKILL_PANEL_OWNER: (
        "render_skill_adoption",
        "render_skill_adoption_levels",
        "render_skill_invocation_diagnostics",
        "skill_adoption_evidence_caption",
        "skill_adoption_zero_caption",
    ),
    _SKILL_TRIGGER_PANEL_OWNER: (
        "render_skill_matrix_expander",
        "render_skill_triggers",
    ),
    _SKILL_TRIGGER_TABLE_OWNER: (
        "skill_trigger_row_html",
        "skill_triggers_html",
    ),
    _SKILLS_OWNER: (
        "read_skill_adoption",
        "read_skill_trigger_matrix",
        "read_skill_trigger_rates",
    ),
    _SPARKLINE_HTML_OWNER: (
        "SparklinePaths",
        "SparklineRequest",
        "render_sparkline",
        "sparkline_area_path",
        "sparkline_paths",
        "sparkline_point_text",
        "sparkline_svg",
    ),
    _SPARKLINE_POINTS_OWNER: (
        "SparklineLayout",
        "sparkline_layout",
        "sparkline_point",
        "sparkline_points",
        "sparkline_step",
        "sparkline_y",
    ),
    _STAGE_COST_PANEL_OWNER: (
        "paired_bars_height",
        "render_stage_review_bars",
    ),
    _STATIC_METADATA_OWNER: (
        "read_data_extent",
        "read_filter_options",
        "read_static_metadata",
    ),
    _SUMMARY_HTML_OWNER: (
        "TopbarRequest",
        "delta_pill",
        "delta_style",
        "filter_meta_html",
        "kpi_strip_html",
        "plural_s",
        "topbar_html",
    ),
    _TABLES_OWNER: (
        "int_or_zero",
        "money_or_dash",
        "relative_width_pct",
        "short_repo_name",
        "table_css",
        "table_head_html",
        "table_html",
    ),
    _THEME_OWNER: (),
    _TOKENS_OWNER: (),
    _USAGE_PANEL_OWNER: (
        "backend_tokens_by_day",
        "render_hero_usage",
        "select_stack_mode",
        "stack_mode_index",
        "stack_mode_label",
    ),
    _WINDOWS_OWNER: (
        "DateWindow",
        "default_date_range",
        "extent_dates",
        "preset_window",
        "previous_window",
        "to_window",
    ),
})

# The two owners that render a surface out of the tokens rather than declaring
# any: the Plotly defaults every figure is merged with, and the stylesheet the
# chrome around those figures is drawn by.
_RENDERED_SURFACES = (_CSS_OWNER, _LAYOUT_OWNER)

# What an owner here may reach: its siblings, plus the analytics owners named
# by the ones that touch a database. Each of those is one answer already
# decided elsewhere, so the owner that needs it names the owner that gives it
# rather than a facade in front of one: the extent a preset anchors at is a
# read's answer, whether there is a database to read at all is one knob's, the
# socket a read runs on is the connection cache's, the exception a failed read
# arrives as is the connection owner's, the two unfiltered reads a page opens
# with are the raw read family's, the seven a headline or lifecycle section is
# drawn from are the rollup, breakdown, and raw families' -- with the ordering
# one of them asks for spelled by the issue-summary owner that reads it -- the
# six a comparison panel is drawn from are the rollup and breakdown families',
# the three a skill panel is drawn from are the skill family's, and the totals
# and cost-source split a banner is raised over -- and the window totals a tile
# reports, the pair of windows the strip beneath it is reduced from, the issue
# rows a table is ranked from, the cohort rows the trigger-rate panel beneath it
# reports, the adoption cells and the matrix cells four of each panel's five
# owners order, parse for, reduce, and assemble -- and the two panel owners
# above all three of those tables are handed a window's worth of each -- the
# per-backend and per-cost-source rows the two card owners weigh and size, and
# the run rows the listing under all of them is projected from -- are the rows
# those reads hand back, and the trace under that listing names the raw family
# for the per-issue read it is the only page caller of.
# The two cost-comparison panels are handed four of
# those row families for the same reason and issue no read of their own: each
# is what the section it draws is typed against, and what it draws that section
# with -- a header, a ranking, a table, a card, a bar, a figure -- is the
# sibling owner that already decided it, down to the toolbar every figure is
# configured by.
# The page-state owner names two of those result
# families for the same reason without issuing a read of its own: the extent a
# page opened on and the window totals a comparison panel reports are what the
# shapes it threads are typed against, and the owner holding the two states a
# page leaves through with the line it ends on names the same pair, since the
# banner an un-ingested database is answered with and the footer a drawn page
# closes on are typed
# against those two readings. That owner is also the one place a sibling render
# is called rather than a shape: an empty window hands the page on to the trace
# at the foot of it, which is scoped by an issue rather than by the cache key
# the reads it skipped share. The owner at the top of the page names no result
# family at all, because what a run is narrowed by is decided out of the
# selections an operator made rather than out of anything read back: its whole
# reach is six siblings -- the bar the days are picked in and the window that
# bar resolves to, the normalization and default offset a selection is read
# through, the knob deciding how the load is issued and the plan staging it,
# and the shapes all of it is threaded on as. The panel below those two is typed
# against the shapes rather than the rows, so the page state is the only
# vocabulary it names, while the grid beneath it is back to the rows and names
# the activity family for the weekday-by-hour points it draws. The owner
# drawing the chrome between the two waves names two result families without
# issuing a read either -- the window aggregate its banner, filter line, and
# strip are all reduced from, and the cost-source rows one of its banners is
# raised over -- while the two that only order the panels beneath name no
# result family at all, since every row they hand on arrived with the load:
# their whole reach is the panels themselves plus the shapes those are typed
# against, and the second of the two names the first because one call has to
# draw the page's whole order. One sibling is a
# package rather than a
# module: the four owners that draw a figure inside a card name the chart
# families that build it -- the hero card one, the paired lifecycle bars two,
# the repository ranking beside the run-health tiles two more, and that grid
# one --
# since a panel is the card and the figure together and a handle passed in
# would let them be assembled from different families, which for a pairing
# pinned to one shared height is two panels measured apart.
_PERMITTED_PREFIXES = ("orchestrator.observability", "orchestrator._package")

# The driver the reads behind these windows are issued over. Nothing here
# dials anything, so a caller that only resolves a preset, hashes a filter set,
# or reads a color must not pay for it -- nor be unable to do any of the three
# on a machine with no Postgres client installed.
_DRIVER_PROBE = """
import sys
import {module}
driver = [name for name in sys.modules if name.split('.')[0] == 'psycopg']
sys.exit(', '.join(driver) if driver else 0)
"""


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
    """The owners reach only siblings, nothing dials, and each rendered
    surface is built from the tokens rather than restating them.
    """

    def test_no_owner_reaches_outside_the_package(self) -> None:
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(_PERMITTED_PREFIXES)
                        or imported == "orchestrator",
                        f"{owner} reaches {imported}",
                    )

    def test_no_owner_plants_the_driver(self) -> None:
        for owner in _OWNERS:
            completed = _run_import_probe(
                _DRIVER_PROBE.format(module=_qualified(owner)),
            )
            with self.subTest(owner=owner):
                self.assertEqual(
                    completed.returncode, 0, msg=completed.stderr,
                )

    def test_a_rendered_surface_names_the_tokens(self) -> None:
        # A CSS variable and a figure's gridline are the same value seen twice,
        # so both surfaces have to read it off the owners that hold it: a hue
        # or a radius restated in either place is a page whose chrome and
        # charts drift apart on the next edit.
        for owner in _RENDERED_SURFACES:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for token_owner in (_PALETTE_OWNER, _TOKENS_OWNER):
                with self.subTest(owner=owner, token_owner=token_owner):
                    self.assertIn(_qualified(token_owner), planted)


if __name__ == "__main__":
    unittest.main()
