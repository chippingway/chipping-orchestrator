# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the chart owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.dashboard import charts as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _run_import_probe,
)

_DASHBOARD = "orchestrator.observability.dashboard"

_PACKAGE = f"{_DASHBOARD}.charts"

_COST_LAYOUT_OWNER = "cost_layout"

_COST_RANKING_OWNER = "cost_horizontal"

_COST_REPO_OWNER = "cost_repo"

_COST_REVIEW_OWNER = "cost_review"

_COST_STAGE_OWNER = "cost_stage"

_HEATMAP_OWNER = "heatmap"

_PRIMITIVES_OWNER = "primitives"

_THROUGHPUT_OWNER = "throughput"

_USAGE_OWNER = "usage"

_USAGE_AXIS_OWNER = "usage_axis"

_USAGE_BANDS_OWNER = "usage_bands"

_USAGE_SERIES_OWNER = "usage_series"

_USAGE_TRACES_OWNER = "usage_traces"

# The declared inventory. A new chart family is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = (
    _COST_LAYOUT_OWNER,
    _COST_RANKING_OWNER,
    _COST_REPO_OWNER,
    _COST_REVIEW_OWNER,
    _COST_STAGE_OWNER,
    _HEATMAP_OWNER,
    _PRIMITIVES_OWNER,
    _THROUGHPUT_OWNER,
    _USAGE_OWNER,
    _USAGE_AXIS_OWNER,
    _USAGE_BANDS_OWNER,
    _USAGE_SERIES_OWNER,
    _USAGE_TRACES_OWNER,
)

# What each owner answers for, declared rather than discovered so a second way
# to say "nothing matches this window", label a bar, frame and size the panel
# it sits in, rank a window's spend, name the repository one of those bars
# stands for, split a stage's spend into the half the cache paid for, split a
# review round's the same way across its two roles, bucket a token volume into
# a weekday cell, lay a window's rows over its calendar, count a day of usage,
# scale the axis it is drawn against, stack it, or assemble the figure it is
# read off is a deliberate edit rather than a place two chart families could
# disagree. The two bar-sizing constants, the panel margin, the empty-ranking
# height, the pinned call signature, the cache-shading factor and its hex base,
# the review-round labels, order, and row heights, the heatmap's weekday labels,
# hour span, and subtotal note, the strip's pinned height, the band names, the
# per-day table's alias, and the usage grid-step and height constants are all
# invisible here because the check reads `__module__`, which only a class or a
# function carries.
_SURFACES = MappingProxyType({
    _COST_LAYOUT_OWNER: (
        "CostBarTrace",
        "HorizontalCostLayout",
        "apply_horizontal_cost_layout",
        "cost_bar_trace",
    ),
    _COST_RANKING_OWNER: (
        "HorizontalBarRequest",
        "HorizontalBars",
        "cost_horizontal_bars",
        "cost_item_sort_key",
        "horizontal_bars_data",
        "reverse_horizontal_bars",
    ),
    _COST_REPO_OWNER: (
        "cost_by_repo",
        "repo_short_name",
    ),
    _COST_REVIEW_OWNER: (
        "ReviewCostBars",
        "cost_by_review_round",
        "developer_cost_total",
        "reverse_review_cost_bars",
        "review_cost_bars",
        "review_cost_traces",
        "reviewer_cost_total",
    ),
    _COST_STAGE_OWNER: (
        "StageCostBars",
        "cost_by_stage",
        "lighten_hex",
        "reverse_stage_cost_bars",
        "stage_cost_bars",
        "stage_cost_sort_key",
        "stage_no_cache_cost",
    ),
    _HEATMAP_OWNER: (
        "heatmap_hover_notes",
        "heatmap_layout",
        "heatmap_matrix",
        "hour_weekday_heatmap",
        "unknown_total_note",
        "valid_heatmap_point",
    ),
    _PRIMITIVES_OWNER: (
        "empty_figure",
        "horizontal_legend",
        "horizontal_panel_height",
        "money_text",
        "monospace_textfont",
        "reverse_lists",
        "two_line_y_ticks",
    ),
    _THROUGHPUT_OWNER: (
        "ThroughputSeries",
        "calendar_days",
        "done_per_day_bars",
        "throughput_series",
    ),
    _USAGE_OWNER: (
        "backend_per_day",
        "usage_over_time",
    ),
    _USAGE_AXIS_OWNER: (
        "nice_axis_max",
        "usage_axis_ranges",
        "usage_layout",
    ),
    _USAGE_BANDS_OWNER: (
        "daily_token_total",
        "empty_token_bucket",
        "roll_up_time_series",
    ),
    _USAGE_SERIES_OWNER: (
        "UsageAxisRanges",
        "UsageChartData",
        "backend_names",
        "date_axis",
        "ensure_backend_days",
        "usage_stack_totals",
    ),
    _USAGE_TRACES_OWNER: (
        "add_backend_usage_traces",
        "add_token_stack_trace",
        "add_token_type_usage_traces",
        "add_usage_cost_trace",
        "add_usage_stack_traces",
        "prepare_usage_data",
    ),
})

# What an owner here may reach: the theme owners a figure is drawn with, which
# is one package up, the read models whose rows it is drawn from, which are
# under the analytics query owners, and the root package every import plants on
# its way in. A color, a font stack, the layout every figure is merged with,
# and the shape of a row are answers already decided there, so a builder names
# those owners rather than restating a hue, a margin, or a field of its own.
_PERMITTED_PREFIXES = ("orchestrator.observability", "orchestrator._package")

# Plotly ships in the optional `dashboard` dependency group, so a figure is
# built with an import inside the call rather than at module scope. Both the
# package a page reaches these builders through and the owner behind it have to
# stay importable in the default install, which carries neither Plotly nor
# Streamlit -- the tree-wide sweep in `test_optional_dependencies` proves the
# import is refused there, and this probe proves it is not paid for in an
# install that does have the package.
_PLOTLY_PROBE = """
import sys
import {module}
loaded = [name for name in sys.modules if name.split('.')[0] == 'plotly']
sys.exit(', '.join(loaded) if loaded else 0)
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
    """The owners reach only the theme they draw with and the read models
    they are drawn from, and nothing here -- nor the package a page opens
    them through -- loads Plotly to be imported.
    """

    def test_no_owner_reaches_outside_observability(self) -> None:
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(_PERMITTED_PREFIXES)
                        or imported == "orchestrator",
                        f"{owner} reaches {imported}",
                    )

    def test_no_import_here_loads_plotly(self) -> None:
        for module in (_DASHBOARD, _PACKAGE, *map(_qualified, _OWNERS)):
            completed = _run_import_probe(_PLOTLY_PROBE.format(module=module))
            with self.subTest(module=module):
                self.assertEqual(
                    completed.returncode, 0, msg=completed.stderr,
                )


if __name__ == "__main__":
    unittest.main()
