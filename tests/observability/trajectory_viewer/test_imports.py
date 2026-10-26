# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the trajectory-viewer owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability import trajectory_viewer as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
)

_PACKAGE = "orchestrator.observability.trajectory_viewer"

_COERCION_OWNER = "coercion"

_CONSTANTS_OWNER = "constants"

_CONTROLS_OWNER = "controls"

_CSS_OWNER = "css"

_FILTER_MODELS_OWNER = "filter_models"

_FILTER_VALUES_OWNER = "filter_values"

_FILTERING_OWNER = "filtering"

_LOG_PATHS_OWNER = "log_paths"

_MODELS_OWNER = "models"

_PAGE_MODELS_OWNER = "page_models"

_PAGE_RENDER_OWNER = "page_render"

_PAGE_SETUP_OWNER = "page_setup"

_PARSING_OWNER = "parsing"

_PICKER_OWNER = "picker"

_READING_OWNER = "reading"

_RUN_HTML_OWNER = "run_html"

_RUN_RENDER_OWNER = "run_render"

_RUNS_OWNER = "runs"

_SUMMARIES_OWNER = "summaries"

_SUMMARY_HTML_OWNER = "summary_html"

_TIMELINE_HTML_OWNER = "timeline_html"

_TIMELINE_OWNER = "timeline_views"

_USAGE_HTML_OWNER = "usage_html"

_USAGE_OWNER = "usage_views"

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the module map, which is what the inventory check compares the directory
# against.
_OWNERS = (
    _COERCION_OWNER,
    _CONSTANTS_OWNER,
    _CONTROLS_OWNER,
    _CSS_OWNER,
    _FILTER_MODELS_OWNER,
    _FILTER_VALUES_OWNER,
    _FILTERING_OWNER,
    _LOG_PATHS_OWNER,
    _MODELS_OWNER,
    _PAGE_MODELS_OWNER,
    _PAGE_RENDER_OWNER,
    _PAGE_SETUP_OWNER,
    _PARSING_OWNER,
    _PICKER_OWNER,
    _READING_OWNER,
    _RUN_HTML_OWNER,
    _RUN_RENDER_OWNER,
    _RUNS_OWNER,
    _SUMMARIES_OWNER,
    _SUMMARY_HTML_OWNER,
    _TIMELINE_HTML_OWNER,
    _TIMELINE_OWNER,
    _USAGE_HTML_OWNER,
    _USAGE_OWNER,
)

# What each owner answers for, declared rather than discovered so a new public
# name is a deliberate edit: a second way to narrow a field, assemble a
# timeline, or total a run's tokens is a second answer a page and a filter
# could disagree over. Some owners report less than they hold because the check
# reads `__module__`, which only a class or a function carries -- `constants` is
# seven strings, `css` one, `usage_html`'s separator another, and
# `timeline_html`'s badge vocabulary a mapping proxy beside a type alias -- and
# because two shapes are private to the page that carries them: the KPI tile on
# `summary_html`, and the two page shapes on `page_models`, which is why that
# owner reports nothing at all.
_SURFACES = MappingProxyType({
    _COERCION_OWNER: (
        "as_list",
        "coerce_float",
        "coerce_int",
        "coerce_str",
        "coerce_str_tuple",
    ),
    _CONSTANTS_OWNER: (),
    _CONTROLS_OWNER: (
        "filter_page_runs",
        "render_categorical_filters",
        "render_text_filters",
        "render_trajectory_sidebar",
    ),
    _CSS_OWNER: (),
    _FILTER_MODELS_OWNER: (
        "FilterOptions",
        "RunFilterOptionFields",
        "RunFilterOptions",
        "RunFilters",
    ),
    _FILTER_VALUES_OWNER: (
        "distinct_sorted",
        "filter_options",
        "matches_query",
        "normalize_filter_query",
        "normalize_filter_values",
    ),
    _FILTERING_OWNER: (
        "filter_runs",
        "matches_dimension_filters",
        "matches_run_filters",
        "matches_scalar_filters",
        "normalize_run_filters",
    ),
    _LOG_PATHS_OWNER: (
        "configured_path",
        "resolve_path",
        "unconfigured_message",
    ),
    _MODELS_OWNER: (
        "RunUsageView",
        "TimelineEntry",
        "TrajectoryStepView",
        "TurnUsageView",
        "public_entry_content",
        "public_step_content",
    ),
    _PAGE_MODELS_OWNER: (),
    _PAGE_RENDER_OWNER: (
        "render_trajectory_footer",
        "render_trajectory_page",
    ),
    _PAGE_SETUP_OWNER: (
        "configure_page",
        "load_trajectory_page",
        "stop_if_unconfigured",
    ),
    _PARSING_OWNER: (
        "parse_record",
        "parse_run_usage",
        "parse_step",
        "parse_turn",
    ),
    _PICKER_OWNER: (
        "fixture_caption",
        "pick_issue",
        "pick_repo",
        "pick_run",
        "render_no_trajectories",
        "render_run_list",
        "render_run_picker",
    ),
    _READING_OWNER: (
        "parse_trajectory_line",
        "read_trajectories",
        "read_trajectory_file",
        "run_sort_key",
    ),
    _RUN_HTML_OWNER: (
        "labeled_chips_html",
        "meta_html",
        "run_picker_label",
        "run_table_row_html",
        "runs_table_html",
    ),
    _RUN_RENDER_OWNER: (
        "render_run",
        "render_run_card",
        "render_run_notices",
        "render_run_usage_and_chips",
        "render_system_prompt",
        "render_timeline",
        "render_timeline_entry",
    ),
    _RUNS_OWNER: ("TrajectoryRun",),
    _SUMMARIES_OWNER: ("TrajectorySummary", "summarize"),
    _SUMMARY_HTML_OWNER: (
        "card_header_html",
        "fmt_cost_usd",
        "kpi_strip_html",
        "topbar_html",
        "trajectory_kpi_html",
        "trajectory_kpis",
    ),
    _TIMELINE_HTML_OWNER: (
        "timeline_entry_html",
        "timeline_with_usage",
    ),
    _TIMELINE_OWNER: (
        "detail_label",
        "is_fixture",
        "label",
        "timeline",
        "turn_map",
    ),
    _USAGE_HTML_OWNER: (
        "run_usage_chips",
        "run_usage_html",
        "run_usage_note",
        "turn_usage_html",
        "usage_chip",
    ),
    _USAGE_OWNER: (
        "cost_source",
        "cost_usd",
        "model",
        "step_count",
        "tool_calls",
        "total_tokens",
        "usage_for_turn",
    ),
})

# The whole chain an import of each owner plants, declared per owner because
# the direction is the point: the two leaves reach nothing, the models name the
# vocabulary a kind is compared against, the two view owners name the models
# they build and return, and only the record names those views. Reaching the
# other way -- a view importing the record its functions are bound onto -- is
# the cycle this rejects, and is why the views name the record at type-check
# time, where no import happens at all: the record is absent from every chain
# but its own and the parse that builds it. The parse sits above the whole
# package for that reason, and nothing here names it back; the read that drives
# it sits above the parse for the same one. `log_paths` is off to the side of
# both: naming the file a read opens costs the vocabulary its banner is spelled
# in and nothing else here. The three filter and summary owners that answer over
# runs name the record at import rather than only at type-check time: their
# annotations are a published surface, so `typing.get_type_hints` on the reads a
# page calls has to resolve them, and a name bound only for a checker resolves
# to nothing at runtime. `filter_models` is the one that names no run at all,
# and it stays the shortest chain here. The rendering owners sit at the far end
# of the same direction: each names what it draws -- the record for `run_html`,
# `timeline_html`, and `usage_html`, the summary for `summary_html` -- and
# nothing names them back, while `css` names nothing in the package at all.
# `usage_html` is the one that also names a sibling renderer: the money on a run
# row and on a turn strip is the exact-cents format the KPI tile is drawn with,
# so it reaches `summary_html` for it rather than spelling a second one. The
# page owners close the same direction off at the top: they name the read, the
# filter, and the markup owners under them and nothing here names them back,
# with `page_render` the widest chain because it is the composition the rest are
# reached through -- the tiles from `summary_html`, the two empty states from
# `page_setup` and `picker`, and everything `picker` in turn composes, which is
# the second-widest for the same reason.
_PLANTED = MappingProxyType({
    _COERCION_OWNER: (),
    _CONSTANTS_OWNER: (),
    _CONTROLS_OWNER: (
        _CONSTANTS_OWNER,
        _FILTER_MODELS_OWNER,
        _FILTER_VALUES_OWNER,
        _FILTERING_OWNER,
        _MODELS_OWNER,
        _PAGE_MODELS_OWNER,
        _RUN_HTML_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _CSS_OWNER: (),
    _FILTER_MODELS_OWNER: (),
    _FILTER_VALUES_OWNER: (
        _CONSTANTS_OWNER,
        _FILTER_MODELS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _FILTERING_OWNER: (
        _CONSTANTS_OWNER,
        _FILTER_MODELS_OWNER,
        _FILTER_VALUES_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _LOG_PATHS_OWNER: (_CONSTANTS_OWNER,),
    _MODELS_OWNER: (_CONSTANTS_OWNER,),
    _PAGE_MODELS_OWNER: (
        _CONSTANTS_OWNER,
        _FILTER_MODELS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _PAGE_RENDER_OWNER: (
        _COERCION_OWNER,
        _CONSTANTS_OWNER,
        _CSS_OWNER,
        _FILTER_MODELS_OWNER,
        _FILTER_VALUES_OWNER,
        _LOG_PATHS_OWNER,
        _MODELS_OWNER,
        _PAGE_MODELS_OWNER,
        _PAGE_SETUP_OWNER,
        _PARSING_OWNER,
        _PICKER_OWNER,
        _READING_OWNER,
        _RUN_HTML_OWNER,
        _RUN_RENDER_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _SUMMARY_HTML_OWNER,
        _TIMELINE_HTML_OWNER,
        _TIMELINE_OWNER,
        _USAGE_HTML_OWNER,
        _USAGE_OWNER,
    ),
    _PAGE_SETUP_OWNER: (
        _COERCION_OWNER,
        _CONSTANTS_OWNER,
        _CSS_OWNER,
        _FILTER_MODELS_OWNER,
        _FILTER_VALUES_OWNER,
        _LOG_PATHS_OWNER,
        _MODELS_OWNER,
        _PAGE_MODELS_OWNER,
        _PARSING_OWNER,
        _READING_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _SUMMARY_HTML_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _PARSING_OWNER: (
        _COERCION_OWNER,
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _PICKER_OWNER: (
        _COERCION_OWNER,
        _CONSTANTS_OWNER,
        _CSS_OWNER,
        _FILTER_MODELS_OWNER,
        _FILTER_VALUES_OWNER,
        _LOG_PATHS_OWNER,
        _MODELS_OWNER,
        _PAGE_MODELS_OWNER,
        _PAGE_SETUP_OWNER,
        _PARSING_OWNER,
        _READING_OWNER,
        _RUN_HTML_OWNER,
        _RUN_RENDER_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _SUMMARY_HTML_OWNER,
        _TIMELINE_HTML_OWNER,
        _TIMELINE_OWNER,
        _USAGE_HTML_OWNER,
        _USAGE_OWNER,
    ),
    _READING_OWNER: (
        _COERCION_OWNER,
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _PARSING_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _RUN_HTML_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _RUN_RENDER_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUN_HTML_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _SUMMARY_HTML_OWNER,
        _TIMELINE_HTML_OWNER,
        _TIMELINE_OWNER,
        _USAGE_HTML_OWNER,
        _USAGE_OWNER,
    ),
    _RUNS_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _SUMMARIES_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _SUMMARY_HTML_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _TIMELINE_HTML_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _TIMELINE_OWNER: (_CONSTANTS_OWNER, _MODELS_OWNER),
    _USAGE_HTML_OWNER: (
        _CONSTANTS_OWNER,
        _MODELS_OWNER,
        _RUNS_OWNER,
        _SUMMARIES_OWNER,
        _SUMMARY_HTML_OWNER,
        _TIMELINE_OWNER,
        _USAGE_OWNER,
    ),
    _USAGE_OWNER: (_CONSTANTS_OWNER, _MODELS_OWNER),
})

# What an import of any owner here costs before it names anything: the root
# package and the chain down to this one.
_ALWAYS_PLANTED = frozenset((
    "orchestrator",
    "orchestrator.observability",
    _PACKAGE,
))

# The two sibling destinations an owner here may reach into, spelled once so a
# chain below is read as which owner under them it names.
_ANALYTICS_TREE = "orchestrator.observability.analytics"

_DASHBOARD_TREE = "orchestrator.observability.dashboard"

_ANALYTICS_CONFIG = f"{_ANALYTICS_TREE}.config"

_DASHBOARD_FORMATTING = f"{_DASHBOARD_TREE}.formatting"

# What a rendering owner that spells a count or a money figure reaches.
_FORMATTING_CHAIN = (_DASHBOARD_TREE, _DASHBOARD_FORMATTING)

# What a page owner that names both the sink's knob and the shared stylesheet
# reaches: the configuration owner behind `log_paths`, and the analytics page's
# own sheet with the palette and geometry it is interpolated from. `picker` and
# `page_render` pay the same list because they compose the owner that names
# them.
_PAGE_CHROME_CHAIN = (
    _ANALYTICS_TREE,
    _ANALYTICS_CONFIG,
    _DASHBOARD_TREE,
    f"{_DASHBOARD_TREE}.css",
    _DASHBOARD_FORMATTING,
    f"{_DASHBOARD_TREE}.palette",
    f"{_DASHBOARD_TREE}.tokens",
)

# The chains an owner here may reach for, declared per owner. `log_paths` names
# the analytics configuration owner, which is how the knob naming the file this
# page reads is read back off the holder the analytics parse bound it on, so
# the viewer answers with the sink's own setting rather than a second parse of
# the same variable -- and what it names is the settings *view*, not the
# `settings` holder those values are bound on, which is the distinction the
# check below turns on: the holder is handed in by the caller, so naming it
# here would decide for one. Three rendering owners name the theme both
# Streamlit pages are drawn in: the geometry owner for the font stacks a
# stylesheet cannot read out of a CSS variable, and the formatting owner for
# the thousands separators a count is rendered with. Both are plain data, so
# neither costs the optional dashboard dependency group.
# `controls` names that theme's filter-state owner for one thing: the parse
# that reads `#123` and `123` as the same issue, so both pages accept the
# spelling an operator types. That owner is typed by the window it also holds,
# which is what puts one result model from the analytics read behind it -- a
# dataclass module, so the chain is a shape and not a database driver.
_EXTERNAL_CHAINS = MappingProxyType({
    _CONTROLS_OWNER: (
        _ANALYTICS_TREE,
        f"{_ANALYTICS_TREE}.query",
        f"{_ANALYTICS_TREE}.query.overview_models",
        _DASHBOARD_TREE,
        f"{_DASHBOARD_TREE}.filters",
        f"{_DASHBOARD_TREE}.windows",
    ),
    _CSS_OWNER: (_DASHBOARD_TREE, f"{_DASHBOARD_TREE}.tokens"),
    _LOG_PATHS_OWNER: (_ANALYTICS_TREE, _ANALYTICS_CONFIG),
    _PAGE_RENDER_OWNER: _PAGE_CHROME_CHAIN,
    _PAGE_SETUP_OWNER: _PAGE_CHROME_CHAIN,
    _PICKER_OWNER: _PAGE_CHROME_CHAIN,
    _RUN_RENDER_OWNER: _FORMATTING_CHAIN,
    _SUMMARY_HTML_OWNER: _FORMATTING_CHAIN,
    _USAGE_HTML_OWNER: _FORMATTING_CHAIN,
})

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


def _planted_siblings(owner: str) -> tuple[str, ...]:
    """Owners in this package that importing `owner` plants besides itself."""
    own_name = _qualified(owner)
    return tuple(sorted(
        planted.rpartition(".")[2]
        for planted in _imported_orchestrator_modules(own_name)
        if planted.startswith(f"{_PACKAGE}.") and planted != own_name
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
    """The owners reach only what they compose, and never back to the page."""

    def test_each_owner_plants_only_its_own_chain(self) -> None:
        for owner, planted in _PLANTED.items():
            with self.subTest(owner=owner):
                self.assertEqual(_planted_siblings(owner), tuple(sorted(planted)))

    def test_owner_reaches_only_its_declared_chain(self) -> None:
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            outside = planted - _ALWAYS_PLANTED - {
                _qualified(sibling) for sibling in _OWNERS
            }
            with self.subTest(owner=owner):
                self.assertEqual(
                    tuple(sorted(outside)), _EXTERNAL_CHAINS.get(owner, ()),
                )


if __name__ == "__main__":
    unittest.main()
