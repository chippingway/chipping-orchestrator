# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order one run of the analytics page reaches its owners in."""
from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from importlib.util import find_spec
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from orchestrator.apps import analytics_dashboard
from orchestrator.observability.analytics.query.overview_models import DataExtent
from orchestrator.observability.dashboard import (
    page_controls,
    page_models,
    page_pipeline,
    page_sections,
    page_states,
    read_mode,
    static_metadata,
    theme,
)

_PAGE_TITLE = "Orchestrator Analytics"

_LAYOUT = "wide"

_REFUSAL = "no database"

_YEAR = 2026

_MAY = 5

_LAST_DAY = 28

# An extent with rows behind it, and the empty one an un-ingested database
# answers with.
_EXTENT = DataExtent(
    min_ts=datetime(_YEAR, _MAY, 1, tzinfo=UTC),
    max_ts=datetime(_YEAR, _MAY, _LAST_DAY, tzinfo=UTC),
)

_NO_ROWS = DataExtent(min_ts=None, max_ts=None)

_OPTIONS = SimpleNamespace(repos=(), events=(), stages=())

_PREPARE = "prepare_dashboard_page"

_LOAD = "load_dashboard_data"

_WIDGETS = "render_dashboard_widgets"

_NO_DATA = "render_no_data"

# Each pass the render dispatches and the owner that holds it. Recording them
# on one mock is what makes the order across four separately patched owners
# readable as a single list.
_RENDER_PASSES = (
    (page_controls, _PREPARE),
    (page_pipeline, _LOAD),
    (page_sections, _WIDGETS),
    (page_states, _NO_DATA),
)

_PANDAS_REASON = "pandas not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"


class ScriptStopped(Exception):
    """What `st.stop()` raises, the way Streamlit's own does."""


class FakePage:
    """The stand-in a pass is drawn onto, recording what it was asked for."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = {}
        self.markup: list[str] = []
        self.warnings: list[str] = []

    def set_page_config(self, **request: Any) -> None:
        self.config = request

    def markdown(self, body: str, **_request: Any) -> None:
        self.markup.append(body)

    def warning(self, body: str) -> None:
        self.warnings.append(body)

    def stop(self) -> None:
        raise ScriptStopped()


def modules_for(page: FakePage) -> page_models.DashboardModules:
    """The handles a pass is given, with the page's own theme among them."""
    return page_models.DashboardModules(st=page, pd=None, theme=theme)


@contextmanager
def render_passes_recorded() -> Iterator[Mock]:
    """Patch every pass a render dispatches onto one recording mock."""
    recorder = Mock()
    with ExitStack() as patches:
        for owner, name in _RENDER_PASSES:
            recorder.attach_mock(Mock(), name)
            patches.enter_context(
                patch.object(owner, name, getattr(recorder, name)),
            )
        yield recorder


class PageChromeTest(unittest.TestCase):
    """The chrome and the refusal, both settled before any reading."""

    def test_the_page_is_settled_from_the_theme(self) -> None:
        # The stylesheet is the theme owner's own, so a page injects that
        # string rather than restating a hue or a radius of its own.
        page = FakePage()
        analytics_dashboard.configure_dashboard(modules_for(page))
        self.assertEqual(
            page.config, {"page_title": _PAGE_TITLE, "layout": _LAYOUT},
        )
        self.assertEqual(page.markup, [theme.PAGE_CSS])

    def test_no_database_stops_the_script(self) -> None:
        page = FakePage()
        with patch.object(
            read_mode, "db_unconfigured_message", return_value=_REFUSAL,
        ), self.assertRaises(ScriptStopped):
            analytics_dashboard.stop_if_dashboard_unconfigured(
                modules_for(page),
            )
        self.assertEqual(page.warnings, [_REFUSAL])

    def test_a_configured_database_draws_on(self) -> None:
        page = FakePage()
        with patch.object(
            read_mode, "db_unconfigured_message", return_value=None,
        ):
            analytics_dashboard.stop_if_dashboard_unconfigured(
                modules_for(page),
            )
        self.assertEqual(page.warnings, [])


class PageOpeningTest(unittest.TestCase):
    """A run opens on the two reads no filter narrows, cached as one pair.

    The extent and the filter vocabulary belong behind the metadata owner's
    wrappers, which cache them for the whole ingest cycle, rather than inline
    where every rerun would re-issue both.
    """

    def test_the_render_is_handed_the_read_pair(self) -> None:
        # The refusal is answered for rather than left to the environment:
        # a run reads the URL off the analytics settings holder, so a machine
        # with `ANALYTICS_DB_URL` exported and one without would otherwise
        # take different branches out of this pass. Which branch an
        # unconfigured database takes is `PageChromeTest`'s.
        page = FakePage()
        with (
            patch.object(
                read_mode, "db_unconfigured_message", return_value=None,
            ),
            patch.object(
                analytics_dashboard,
                "load_dashboard_modules",
                return_value=modules_for(page),
            ),
            patch.object(
                static_metadata,
                "read_static_metadata",
                return_value=(_EXTENT, _OPTIONS),
            ) as metadata,
            patch.object(analytics_dashboard, "render_dashboard") as render,
        ):
            analytics_dashboard.run_dashboard(page)
            metadata.assert_called_once_with(st=page)
            self.assertEqual(render.call_args.args[1:], (_EXTENT, _OPTIONS))

    @unittest.skipUnless(find_spec("pandas"), _PANDAS_REASON)
    def test_the_handles_carry_the_theme_owner(self) -> None:
        # The theme is a parameter every panel takes, so the page composes the
        # one object they are all drawn from rather than each importing one.
        bound = analytics_dashboard.load_dashboard_modules(FakePage())
        self.assertIs(bound.theme, theme)


class RenderBranchTest(unittest.TestCase):
    """Which passes a window reaches, and which end the render before them."""

    def test_no_rows_draws_the_no_data_state(self) -> None:
        page = FakePage()
        with render_passes_recorded() as recorder:
            analytics_dashboard.render_dashboard(
                modules_for(page), _NO_ROWS, _OPTIONS,
            )
            recorder.render_no_data.assert_called_once_with(
                st=page, extent=_NO_ROWS, theme=theme,
            )
            drawn = [name for name, _, _ in recorder.mock_calls]
            self.assertEqual(drawn, [_NO_DATA])

    def test_a_window_is_drawn_controls_first(self) -> None:
        modules = modules_for(FakePage())
        with render_passes_recorded() as recorder:
            analytics_dashboard.render_dashboard(modules, _EXTENT, _OPTIONS)
            opened = recorder.prepare_dashboard_page.return_value
            drawn = [name for name, _, _ in recorder.mock_calls]
            self.assertEqual(drawn, [_PREPARE, _LOAD, _WIDGETS])
            recorder.load_dashboard_data.assert_called_once_with(
                modules, opened,
            )
            recorder.render_dashboard_widgets.assert_called_once_with(
                modules, opened, recorder.load_dashboard_data.return_value,
            )

    def test_an_empty_window_ends_at_the_load(self) -> None:
        # A first wave that answered with no event hands nothing back, so
        # there is nothing for the panels beneath to be drawn from.
        with render_passes_recorded() as recorder:
            recorder.load_dashboard_data.return_value = None
            analytics_dashboard.render_dashboard(
                modules_for(FakePage()), _EXTENT, _OPTIONS,
            )
            recorder.render_dashboard_widgets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
