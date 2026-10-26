# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which values a read offers, and which of its runs one request keeps."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import filter_models, filter_values, filtering
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    ASSISTANT_MESSAGE,
    TOOL_BASH,
    TOOL_CALL,
    TOOL_SKILL,
    run,
    step,
)

_REPO_A = "a/a"

_REPO_B = "b/b"

_BACKEND_CLAUDE = "claude"

_BACKEND_CODEX = "codex"

_ROLE_DEVELOPER = "developer"

_ROLE_REVIEWER = "reviewer"

_STAGE_IMPLEMENTING = "implementing"

_STAGE_IN_REVIEW = "in_review"

_DEVELOPER_ISSUE = 1

_REVIEWER_ISSUE = 2

_SKILL_DEVELOP = "develop"

_FIXTURE_PROMPT = "ignored"


def _developer_run(**fields) -> TrajectoryRun:
    """The claude developer run every selection test narrows towards."""
    identity = {
        "issue": _DEVELOPER_ISSUE,
        "repo": _REPO_A,
        "backend": _BACKEND_CLAUDE,
        "agent_role": _ROLE_DEVELOPER,
        "stage": _STAGE_IMPLEMENTING,
    }
    identity.update(fields)
    return run(**identity)


def _reviewer_run(**fields) -> TrajectoryRun:
    """The codex reviewer run every selection test narrows away from."""
    identity = {
        "issue": _REVIEWER_ISSUE,
        "repo": _REPO_B,
        "backend": _BACKEND_CODEX,
        "agent_role": _ROLE_REVIEWER,
        "stage": _STAGE_IN_REVIEW,
    }
    identity.update(fields)
    return run(**identity)


class FilterOptionsTest(unittest.TestCase):
    """A dropdown is offered each distinct value some run carries, sorted."""

    def test_distinct_non_empty_values_are_sorted(self) -> None:
        offered = filter_values.filter_options([
            _reviewer_run(),
            _developer_run(),
            run(repo=_REPO_A, backend=_BACKEND_CLAUDE, agent_role="", stage=""),
        ])
        self.assertEqual(offered.repos, (_REPO_A, _REPO_B))
        self.assertEqual(offered.backends, (_BACKEND_CLAUDE, _BACKEND_CODEX))
        # Empty role / stage are dropped, not offered as a blank choice.
        self.assertEqual(offered.agent_roles, (_ROLE_DEVELOPER, _ROLE_REVIEWER))
        self.assertEqual(offered.stages, (_STAGE_IMPLEMENTING, _STAGE_IN_REVIEW))


class _FilterRunsSupport(unittest.TestCase):
    """The two runs, one per dimension value, every selection is asked over."""

    def _runs(self) -> list[TrajectoryRun]:
        return [
            _developer_run(
                output="resolved the bug",
                steps=(step(TOOL_CALL, name=TOOL_BASH, content="grep needle file.py"),),
                skills_triggered=(_SKILL_DEVELOP,),
            ),
            _reviewer_run(output="looks good"),
        ]

    def _issues(self, **option_fields) -> list[int]:
        kept = filtering.filter_runs(self._runs(), **option_fields)
        return [kept_run.issue for kept_run in kept]


class FilterRunSelectionTest(_FilterRunsSupport):
    """Each field narrows on its own; an unticked one narrows nothing."""

    def test_no_filters_returns_all(self) -> None:
        self.assertEqual(self._issues(), [_DEVELOPER_ISSUE, _REVIEWER_ISSUE])

    def test_each_field_selects_the_run_carrying_it(self) -> None:
        selections = (
            ({"repo": _REPO_A}, _DEVELOPER_ISSUE),
            ({"issue": _REVIEWER_ISSUE}, _REVIEWER_ISSUE),
            ({"backends": [_BACKEND_CODEX]}, _REVIEWER_ISSUE),
            ({"agent_roles": [_ROLE_DEVELOPER]}, _DEVELOPER_ISSUE),
            ({"stages": [_STAGE_IN_REVIEW]}, _REVIEWER_ISSUE),
        )
        for selection, selected_issue in selections:
            with self.subTest(selection=selection):
                self.assertEqual(self._issues(**selection), [selected_issue])

    def test_empty_multi_value_is_no_constraint(self) -> None:
        both = [_DEVELOPER_ISSUE, _REVIEWER_ISSUE]
        self.assertEqual(self._issues(backends=[]), both)
        self.assertEqual(self._issues(stages=None), both)
        # A whitespace-only needle is the same "narrowed nothing".
        self.assertEqual(self._issues(query="   "), both)

    def test_query_spans_output_steps_and_skills(self) -> None:
        # The final output, a path inside a tool command, and a triggered
        # skill's name -- the last spelled in the case a page did not offer.
        for needle in ("resolved", "file.py", "DEVELOP"):
            with self.subTest(needle=needle):
                self.assertEqual(self._issues(query=needle), [_DEVELOPER_ISSUE])

    def test_query_matches_message_turn_content(self) -> None:
        # The newer `assistant_message` / `user_message` turns are steps too,
        # so the free-text search reaches their content like any tool payload.
        runs = [
            _developer_run(steps=(
                step(ASSISTANT_MESSAGE, content="I will refactor the cache layer"),
            )),
            _reviewer_run(),
        ]
        kept = filtering.filter_runs(runs, query="refactor")
        self.assertEqual([kept_run.issue for kept_run in kept], [_DEVELOPER_ISSUE])

    def test_filters_combine_preserving_input_order(self) -> None:
        base_runs = self._runs()
        matching_later = _developer_run(seq=9, output="resolved another bug")
        matching_fixture = _developer_run(
            seq=8,
            user_input=_FIXTURE_PROMPT,
            output="resolved fixture bug",
        )
        runs = [base_runs[0], matching_fixture, matching_later, base_runs[1]]
        kept = filtering.filter_runs(
            runs,
            repo=_REPO_A,
            backends=[_BACKEND_CLAUDE],
            agent_roles=[_ROLE_DEVELOPER],
            stages=[_STAGE_IMPLEMENTING],
            issue=_DEVELOPER_ISSUE,
            query="RESOLVED",
            exclude_fixtures=True,
        )
        self.assertEqual([kept_run.seq for kept_run in kept], [0, 9])


class FilterRequestShapeTest(_FilterRunsSupport):
    """A request is the keyword fields alone."""

    def test_an_options_object_is_refused(self) -> None:
        # The keywords are the one spelling a page calls with, so an options
        # object handed in beside the runs is a call nothing here answers.
        with self.assertRaises(TypeError):
            filtering.filter_runs(
                self._runs(), filter_models.RunFilterOptions(repo=_REPO_A),
            )


class FilterRunFixtureTest(unittest.TestCase):
    """The synthetic records an inherited file carries, kept unless refused."""

    def test_exclude_fixtures_default_off(self) -> None:
        runs = self._fixture_runs()
        self.assertEqual(len(filtering.filter_runs(runs)), len(runs))

    def test_exclude_fixtures_drops_every_tell(self) -> None:
        kept = filtering.filter_runs(self._fixture_runs(), exclude_fixtures=True)
        self.assertEqual([kept_run.issue for kept_run in kept], [_DEVELOPER_ISSUE])

    def test_a_selected_fixture_is_still_dropped(self) -> None:
        kept = filtering.filter_runs(
            self._fixture_runs(), issue=_REVIEWER_ISSUE, exclude_fixtures=True,
        )
        self.assertEqual(kept, [])

    def _fixture_runs(self) -> list[TrajectoryRun]:
        """One real run, then one carrying each tell that marks a fixture."""
        return [
            run(issue=_DEVELOPER_ISSUE, user_input="real work", session_id="uuid-1"),
            run(issue=_REVIEWER_ISSUE, user_input=_FIXTURE_PROMPT),
            run(issue=3, session_id="sess-7"),
            run(issue=4, steps=(
                step(TOOL_CALL, name=TOOL_SKILL, content=_SKILL_DEVELOP),
            )),
        ]


if __name__ == "__main__":
    unittest.main()
