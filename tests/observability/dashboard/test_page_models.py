# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the state one page render is threaded through answers for itself."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import Any, get_type_hints

from orchestrator.observability.dashboard import page_models, windows

_REPO = "chippingway/chipping-orchestrator"

_ISSUE = 1174

_YEAR = 2026

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, 8, tzinfo=UTC)

_WINDOW_DAYS = 7

# Every shape a render carries, so a new one is held to the same two rules the
# pipeline threads them under: nothing it was handed can be narrowed, and every
# name it is annotated in can be read back.
_PAGE_STATE = (
    page_models.DashboardModules,
    page_models.DashboardFilters,
    page_models.DashboardControls,
    page_models.DashboardPage,
    page_models.DashboardKpis,
    page_models.LoadedDashboard,
    page_models.ReliabilityPanelData,
)


def _filters(
    *,
    repo: str | None = None,
    issue_input: int | None = None,
    end: datetime = _WINDOW_END,
) -> page_models.DashboardFilters:
    """One run's selections, over a window ending where the caller says."""
    return page_models.DashboardFilters(
        window=windows.DateWindow(start=_WINDOW_START, end=end),
        repo=repo,
        issue_input=issue_input,
        events=None,
        stages=None,
    )


def _blank(shape: Any) -> Any:
    """One instance of `shape` with every field left unanswered."""
    return shape(**{field.name: None for field in fields(shape)})


class IssueScopeTest(unittest.TestCase):
    """A typed issue number narrows a read only once a repo names one."""

    def test_a_number_scopes_nothing_across_repos(self) -> None:
        # GitHub issue numbers repeat across repositories, so #1174 with no
        # repo picked names as many issues as the extent holds.
        self.assertIsNone(_filters(issue_input=_ISSUE).issue)

    def test_a_number_scopes_to_the_repo_picked(self) -> None:
        scoped = _filters(repo=_REPO, issue_input=_ISSUE)
        self.assertEqual(scoped.issue, _ISSUE)

    def test_a_repo_with_no_number_scopes_nothing(self) -> None:
        self.assertIsNone(_filters(repo=_REPO).issue)


class WindowSpanTest(unittest.TestCase):
    """The span per-day rates are divided by is the window, floored at one."""

    def test_the_span_is_the_window_in_whole_days(self) -> None:
        self.assertEqual(_filters().days, _WINDOW_DAYS)

    def test_a_window_shorter_than_a_day_spans_one(self) -> None:
        # Both bounds land on the same date whenever the filter bar is opened
        # and closed on it, and a rate divided by that span must not raise.
        self.assertEqual(_filters(end=_WINDOW_START).days, 1)


class ImmutableStateTest(unittest.TestCase):
    """No section can narrow the state the sections beside it were handed."""

    def test_every_shape_a_render_carries_is_frozen(self) -> None:
        for shape in _PAGE_STATE:
            with self.subTest(shape=shape.__name__), self.assertRaises(FrozenInstanceError):
                _blank(shape).repo = _REPO


class RuntimeAnnotationTest(unittest.TestCase):
    """The vocabulary these shapes are annotated in stays bound at runtime."""

    def test_every_shape_resolves_its_own_annotations(self) -> None:
        for shape in _PAGE_STATE:
            with self.subTest(shape=shape.__name__):
                # A name bound for a type checker alone surfaces as NameError:
                # postponed evaluation leaves the annotation as text, and this
                # is the caller reading it back.
                self.assertTrue(get_type_hints(shape))


if __name__ == "__main__":
    unittest.main()
