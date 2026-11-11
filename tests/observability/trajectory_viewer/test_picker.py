# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a narrowed read is presented, and how one run is reached inside it."""
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

from orchestrator.observability.trajectory_viewer import picker, run_html
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    ISSUE,
    REPO,
    run,
)

_LOG_PATH = Path("/var/log/orchestrator/trajectories.jsonl")

_OTHER_REPO = "acme/gadgets"

_OTHER_ISSUE = 7

_FIXTURE_SESSION = "sess-abc"

_ONE_FIXTURE = 1

_TWO_FIXTURES = 2

_SECOND_CANDIDATE = 1

_ONE_DIGIT_ISSUE = 9

_PREFIX_ISSUE = 12

_TWO_DIGIT_ISSUE = 34

_THREE_DIGIT_ISSUE = 120

_OTHER_REPO_TOP_ISSUE = 500


def _captions(st: Any) -> str:
    return "".join(call.args[0] for call in st.caption.call_args_list)


def _cohort() -> tuple:
    """Two repositories, one of which carries two runs on the same issue."""
    return (
        run(seq=3, repo=REPO, issue=ISSUE, backend="claude"),
        run(seq=2, repo=REPO, issue=ISSUE, backend="codex"),
        run(seq=1, repo=REPO, issue=_OTHER_ISSUE),
        run(seq=0, repo=_OTHER_REPO, issue=ISSUE),
    )


def _numbered_cohort() -> list:
    """Issues of one to three digits, read out of order, one of them twice.

    The other repository holds the highest number of all, so an issue list
    that leaked across repositories would lead with it.
    """
    return [
        run(seq=5, repo=REPO, issue=_TWO_DIGIT_ISSUE, backend="claude"),
        run(seq=4, repo=REPO, issue=_ONE_DIGIT_ISSUE),
        run(seq=3, repo=_OTHER_REPO, issue=_OTHER_REPO_TOP_ISSUE),
        run(seq=2, repo=REPO, issue=_THREE_DIGIT_ISSUE),
        run(seq=1, repo=REPO, issue=_PREFIX_ISSUE),
        run(seq=0, repo=REPO, issue=_TWO_DIGIT_ISSUE, backend="codex"),
    ]


class NoTrajectoriesTest(unittest.TestCase):
    """An empty file says what has to happen, and which file it read."""

    def test_the_message_names_the_file_it_read(self) -> None:
        st = Mock()
        picker.render_no_trajectories(st, _LOG_PATH)
        self.assertIn("TRAJECTORY_LOG_PATH", st.info.call_args.args[0])
        self.assertIn(str(_LOG_PATH), _captions(st))

    def test_an_unresolved_path_is_left_unnamed(self) -> None:
        st = Mock()
        picker.render_no_trajectories(st, None)
        st.caption.assert_not_called()


class FixtureCaptionTest(unittest.TestCase):
    """The toggle's receipt, worded for whichever way it is set."""

    def test_it_reads_for_the_toggle_and_the_count(self) -> None:
        for total, hidden, expected in (
            (_ONE_FIXTURE, True, "1 synthetic fixture run hidden."),
            (_TWO_FIXTURES, True, "2 synthetic fixture runs hidden."),
            (_ONE_FIXTURE, False, "1 synthetic fixture run flagged;"),
        ):
            with self.subTest(total=total, hidden=hidden):
                caption = picker.fixture_caption(total, hidden)
                self.assertTrue(caption.startswith(expected))


class RunListTest(unittest.TestCase):
    """The overview table is capped, and says so where it capped."""

    def test_a_long_read_is_capped_and_says_so(self) -> None:
        over_cap = picker.RUN_TABLE_LIMIT + 1
        st = self._render_list([run(seq=seq) for seq in range(over_cap)])
        rows = "".join(
            call.args[0] for call in st.markdown.call_args_list
        ).count("<tr")
        # One header row plus the capped body.
        self.assertEqual(rows, picker.RUN_TABLE_LIMIT + 1)
        self.assertIn(f"most recent of {over_cap} matching runs", _captions(st))

    def test_a_short_read_is_drawn_whole(self) -> None:
        st = self._render_list([run()])
        self.assertNotIn("most recent of", _captions(st))
        self.assertNotIn("synthetic fixture", _captions(st))

    def test_the_receipt_needs_a_fixture(self) -> None:
        st = self._render_list([run(session_id=_FIXTURE_SESSION)], fixtures=1)
        self.assertIn("synthetic fixture", _captions(st))

    def _render_list(self, shown, fixtures: int = 0) -> Any:
        st = MagicMock()
        picker.render_run_list(st, shown, fixtures, False)
        return st


class CascadingPickerTest(unittest.TestCase):
    """Each selection is offered only what the one above it left."""

    def test_the_repo_choice_is_sorted_distinct(self) -> None:
        st = Mock()
        picker.pick_repo(st, _cohort())
        self.assertEqual(st.selectbox.call_args.args[1], [_OTHER_REPO, REPO])

    def test_the_issue_choice_follows_the_repo(self) -> None:
        st = Mock()
        picker.pick_issue(st, _cohort(), _OTHER_REPO)
        self.assertEqual(st.selectbox.call_args.args[1], [ISSUE])

    def test_issues_lead_with_the_highest_number(self) -> None:
        st = MagicMock()
        st.selectbox.side_effect = [REPO, _TWO_DIGIT_ISSUE, _SECOND_CANDIDATE]
        cohort = _numbered_cohort()
        picker.render_run_picker(st, cohort)
        _, issue_choice, run_choice = st.selectbox.call_args_list
        # Numeric, not textual: as text "12" sorts beside "120", and "9" past both.
        self.assertEqual(
            [(issue, issue_choice.kwargs["format_func"](issue)) for issue in issue_choice.args[1]],
            [
                (_THREE_DIGIT_ISSUE, "#120"),
                (_TWO_DIGIT_ISSUE, "#34"),
                (_PREFIX_ISSUE, "#12"),
                (_ONE_DIGIT_ISSUE, "#9"),
            ],
        )
        # The picked issue still hands the run choice both of its runs.
        self.assertEqual(
            [run_choice.kwargs["format_func"](index) for index in run_choice.args[1]],
            [run_html.run_picker_label(cohort[0]), run_html.run_picker_label(cohort[-1])],
        )
        self.assertIn(
            f"Run #{_TWO_DIGIT_ISSUE} · {REPO}",
            "".join(call.args[0] for call in st.markdown.call_args_list),
        )

    def test_the_run_choice_follows_the_pair(self) -> None:
        st = Mock()
        st.selectbox.return_value = _SECOND_CANDIDATE
        picked = picker.pick_run(st, _cohort(), REPO, ISSUE)
        # Both runs on that pair stay reachable, in the order they were read.
        self.assertEqual(
            list(st.selectbox.call_args.args[1]), [0, _SECOND_CANDIDATE],
        )
        self.assertEqual(picked.seq, 2)

    def test_the_picked_run_is_the_one_drawn(self) -> None:
        st = MagicMock()
        st.selectbox.side_effect = [REPO, _OTHER_ISSUE, 0]
        picker.render_run_picker(st, _cohort())
        drawn = "".join(call.args[0] for call in st.markdown.call_args_list)
        self.assertIn(f"Run #{_OTHER_ISSUE} · {REPO}", drawn)


if __name__ == "__main__":
    unittest.main()
