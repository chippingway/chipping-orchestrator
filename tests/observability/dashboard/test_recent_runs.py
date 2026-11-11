# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the run listing under the panels shows, and when it shows nothing.

Streamlit and pandas are faked so the render runs end-to-end in the default
install: the expander, the notice, and what is handed to `st.dataframe` are
what an operator sees, and the fake frame is the row list it was built from, so
the columns and their order can be read straight back off it. A run's cost is
read as its stored evidence states it -- a CLI-reported amount, one provider's
estimate, a blended run, a subtotal, an unpriced run, a run with no usage, and
an amount stored with no basis -- as its figure and its own status, never its
source, which the page's Cost details section explains once.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from orchestrator.observability.analytics.query.run_models import AgentExitRow
from orchestrator.observability.dashboard import recent_runs, spend_text
from tests.observability.analytics import analytics_usage_cases as cases

_YEAR = 2026

_MAY = 5

_NOON = 12

_UTC_NOON = datetime(_YEAR, _MAY, 4, _NOON, tzinfo=UTC)

_OFFSET_HOURS = 3

_FIRST_ISSUE = 42

_SECOND_ISSUE = 43

_TS_COLUMN = "ts"

_ISSUE_COLUMN = "issue"

# The columns one run is scanned by: when and where, then what ran, then how it
# went, then what it cost.
_COLUMNS = (
    _TS_COLUMN,
    "repo",
    _ISSUE_COLUMN,
    "stage",
    "agent",
    "backend",
    "duration (s)",
    "exit",
    "timed out",
    "round",
    "retry",
    "input tokens",
    "output tokens",
    "total tokens",
    "cost",
)

# What a run's cost cell reads for each cost its row can store.
_WORDED_RUNS = (
    (cases.REPORTED, "$0.42"),
    (cases.COMPLETE_ZERO, "$0.00"),
    (cases.ANTHROPIC_ESTIMATE, "$0.30"),
    (cases.GEMINI_ESTIMATE, "$0.12"),
    (cases.BLENDED, "$0.15"),
    (cases.INCOMPLETE_SUBTOTAL, f"$0.20 · {spend_text.SUBTOTAL}"),
    (cases.UNPRICED, spend_text.UNPRICED),
    (cases.NO_USAGE, spend_text.NO_USAGE),
    (cases.ABSENT_BASIS, f"$0.07 · {spend_text.COMPLETENESS_UNKNOWN}"),
)


class _RecordingPandas:
    """The `pd` handle the page passes in, framing rows as the rows."""

    def DataFrame(self, rows):  # noqa: N802 - the pandas method name the page calls
        return rows


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exception) -> bool:
        return False


class _RecentRunsStreamlit:
    """Fake `st` recording the expander, notices, and frames it is handed."""

    def __init__(self) -> None:
        self.expanders: list = []
        self.infos: list = []
        self.frames: list = []

    def expander(self, label, **options):
        self.expanders.append((label, options))
        return _NullContext()

    def dataframe(self, frame, **options) -> None:
        self.frames.append((frame, options))

    def show_information(self, text) -> None:
        self.infos.append(text)

    def __getattr__(self, attribute_name):
        if attribute_name == "info":
            return self.show_information
        raise AttributeError(attribute_name)


def _agent_exit(**overrides) -> AgentExitRow:
    readings = {
        _TS_COLUMN: _UTC_NOON,
        "repo": "owner/repo",
        _ISSUE_COLUMN: _FIRST_ISSUE,
        "stage": "implementing",
        "agent_role": "developer",
        "backend": "claude",
        "duration_s": 12.5,
        "exit_code": 0,
        "timed_out": False,
        "review_round": 1,
        "retry_count": 0,
        "input_tokens": 900,
        "output_tokens": 100,
        "total_tokens": 1000,
        "cost": cases.REPORTED,
    }
    readings.update(overrides)
    return AgentExitRow(**readings)


def _render(agent_exits, *, tz_offset_choice=0) -> _RecentRunsStreamlit:
    st = _RecentRunsStreamlit()
    recent_runs.render_recent_runs(
        st=st,
        pd=_RecordingPandas(),
        agent_exits=agent_exits,
        tz_offset_choice=tz_offset_choice,
    )
    return st


class RecentRunRowTest(unittest.TestCase):
    """One run is projected into the columns it is listed under."""

    def test_columns_are_in_scanning_order(self) -> None:
        row = recent_runs.recent_run_row(_agent_exit(), timedelta())
        self.assertEqual(tuple(row), _COLUMNS)

    def test_every_reading_comes_off_the_run(self) -> None:
        exit_row = _agent_exit()
        row = recent_runs.recent_run_row(exit_row, timedelta())
        self.assertEqual(
            tuple(row.values()),
            (
                exit_row.ts,
                exit_row.repo,
                exit_row.issue,
                exit_row.stage,
                exit_row.agent_role,
                exit_row.backend,
                exit_row.duration_s,
                exit_row.exit_code,
                exit_row.timed_out,
                exit_row.review_round,
                exit_row.retry_count,
                exit_row.input_tokens,
                exit_row.output_tokens,
                exit_row.total_tokens,
                "$0.42",
            ),
        )

    def test_a_cost_is_worded_by_its_evidence(self) -> None:
        # Nothing is re-priced from the tokens beside it: the amount and the
        # status are the ones the run's row stored, each run its own.
        for cost, worded in _WORDED_RUNS:
            with self.subTest(cost=cost):
                row = recent_runs.recent_run_row(_agent_exit(cost=cost), timedelta())
                self.assertEqual(row["cost"], worded)

    def test_an_unknown_token_total_stays_empty(self) -> None:
        row = recent_runs.recent_run_row(_agent_exit(total_tokens=None), timedelta())
        self.assertIsNone(row["total tokens"])

    def test_an_aware_timestamp_is_read_in_the_offset(self) -> None:
        # The instant is preserved and only the clock it is read on moves, so
        # a run stays where it happened rather than being shifted twice.
        offset = timedelta(hours=_OFFSET_HOURS)
        shifted = recent_runs.recent_run_row(_agent_exit(), offset)[_TS_COLUMN]
        self.assertEqual(shifted, _UTC_NOON)
        self.assertEqual(shifted.utcoffset(), offset)
        self.assertEqual(shifted.hour, _NOON + _OFFSET_HOURS)


class RenderRecentRunsTest(unittest.TestCase):
    """The listing is collapsed, and a window with no run says so."""

    def test_the_listing_opens_collapsed(self) -> None:
        for agent_exits in ([], [_agent_exit()]):
            with self.subTest(runs=len(agent_exits)):
                st = _render(agent_exits)
                self.assertEqual(
                    st.expanders, [("Recent agent runs", {"expanded": False})],
                )

    def test_an_empty_window_renders_the_notice(self) -> None:
        st = _render([])
        self.assertEqual(st.infos, [recent_runs.NO_AGENT_EXITS_MESSAGE])
        self.assertEqual(st.frames, [])

    def test_a_window_with_runs_renders_the_frame(self) -> None:
        st = _render([_agent_exit(), _agent_exit(issue=_SECOND_ISSUE)])
        self.assertEqual(st.infos, [])
        frame, options = st.frames[0]
        self.assertEqual(options, {"use_container_width": True})
        self.assertEqual(
            [row[_ISSUE_COLUMN] for row in frame],
            [_FIRST_ISSUE, _SECOND_ISSUE],
        )

    def test_the_offset_choice_is_the_rows_clock(self) -> None:
        st = _render([_agent_exit()], tz_offset_choice=_OFFSET_HOURS)
        frame, _ = st.frames[0]
        self.assertEqual(
            frame[0][_TS_COLUMN].utcoffset(), timedelta(hours=_OFFSET_HOURS),
        )


if __name__ == "__main__":
    unittest.main()
