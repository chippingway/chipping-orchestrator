# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the card for one selected run draws, and in what order."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, Mock

from orchestrator.observability.trajectory_viewer import constants, models, run_render
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    ASSISTANT_MESSAGE,
    ISSUE,
    REPO,
    TOOL_BASH,
    TOOL_CALL,
    cost,
    run,
    step,
)

_FIXTURE_SESSION = "sess-abc"

_PROMPT_TEXT = "you are a developer"

_OUTPUT_TEXT = "opened the PR"

_FIRST_TURN = 0

_COST_USD = 1.5

_TURN_COST = 0.0123

_REPORTED_RUN = models.RunUsageView(cost_evidence=cost(
    usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _COST_USD),
))


def _markup(st: Any) -> str:
    return "".join(call.args[0] for call in st.markdown.call_args_list)


class RunNoticeTest(unittest.TestCase):
    """The two facts that change how everything under them reads."""

    def test_a_fixture_and_a_truncation_are_named(self) -> None:
        st = Mock()
        run_render.render_run_notices(
            st, run(session_id=_FIXTURE_SESSION, truncated=True),
        )
        self.assertIn("synthetic test fixture", st.info.call_args.args[0])
        self.assertIn("record budget", st.warning.call_args.args[0])

    def test_an_ordinary_run_carries_no_notice(self) -> None:
        st = Mock()
        run_render.render_run_notices(st, run())
        st.info.assert_not_called()
        st.warning.assert_not_called()


class RunChipRowsTest(unittest.TestCase):
    """Which of the three chip rows the card draws, and which it marks.

    All three go through one chip builder, so what is pinned here is the card's
    own choice: which rows it draws at all, and which it draws with an
    empty-state marker.
    """

    def test_empty_skills_triggered_still_renders(self) -> None:
        # A session that fired no skill still shows the row, marked `none`, so
        # it is distinguishable from an omitted row; the equally-empty Tools
        # and Skills-available rows stay omitted.
        blob = self._render_chips()
        self.assertIn(">Skills triggered</span>", blob)
        self.assertIn('class="orch-traj-chip none"', blob)
        self.assertIn(">none</span>", blob)
        self.assertNotIn("Tools offered", blob)
        self.assertNotIn("Skills available", blob)

    def test_triggered_skills_are_plain_chips(self) -> None:
        blob = self._render_chips(skills_triggered=("develop", "review"))
        self.assertIn(">develop</span>", blob)
        self.assertIn(">review</span>", blob)
        self.assertNotIn('class="orch-traj-chip none"', blob)

    def test_a_priced_run_carries_its_usage_row(self) -> None:
        blob = self._render_chips(run_usage=_REPORTED_RUN)
        self.assertIn("orch-traj-usage", blob)
        self.assertIn("$1.50 (CLI-reported)", blob)

    def _render_chips(self, **overrides) -> str:
        st = Mock()
        run_render.render_run_usage_and_chips(st, run(**overrides))
        return _markup(st)


class SystemPromptTest(unittest.TestCase):
    """The system prompt is offered folded away, where there was one."""

    def test_it_is_drawn_verbatim_behind_an_expander(self) -> None:
        st = MagicMock()
        run_render.render_system_prompt(st, run(system_prompt=_PROMPT_TEXT))
        self.assertEqual(st.expander.call_args.args, ("System prompt",))
        self.assertEqual(st.code.call_args.args, (_PROMPT_TEXT,))

    def test_a_run_without_one_draws_nothing(self) -> None:
        st = MagicMock()
        run_render.render_system_prompt(st, run())
        st.expander.assert_not_called()


class TimelineEntryTest(unittest.TestCase):
    """How one entry's body is handed over, and where a strip sits."""

    def test_only_the_output_is_read_as_markdown(self) -> None:
        # Everything else is a prompt, a payload, or a result: text that has to
        # be shown as written rather than interpreted.
        for kind, is_output in (
            (ASSISTANT_MESSAGE, False),
            (constants.TIMELINE_OUTPUT, True),
        ):
            with self.subTest(kind=kind):
                st = Mock()
                run_render.render_timeline_entry(
                    st,
                    0,
                    None,
                    models.TimelineEntry(kind=kind, content=_OUTPUT_TEXT),
                )
                self.assertEqual(st.code.called, not is_output)
                self.assertEqual(_OUTPUT_TEXT in _markup(st), is_output)

    def test_a_strip_sits_above_the_entry_it_opens(self) -> None:
        st = Mock()
        run_render.render_timeline_entry(
            st,
            0,
            models.TurnUsageView(turn=_FIRST_TURN, model="sonnet"),
            models.TimelineEntry(kind=ASSISTANT_MESSAGE),
        )
        drawn = [call.args[0] for call in st.markdown.call_args_list]
        self.assertIn("sonnet", drawn[0])
        self.assertIn("orch-traj-step", drawn[1])


class TimelineTest(unittest.TestCase):
    """A run's whole sequence, or the reason there is none."""

    def test_every_entry_is_drawn_under_the_header(self) -> None:
        st = Mock()
        drawn = run(steps=(
            step(ASSISTANT_MESSAGE, content="a"),
            step(TOOL_CALL, name=TOOL_BASH),
        ))
        run_render.render_timeline(st, drawn)
        blob = _markup(st)
        self.assertIn("Trajectory timeline · 2 steps · 1 tool calls", blob)
        self.assertIn(TOOL_BASH, blob)
        st.caption.assert_not_called()

    def test_a_run_with_no_entries_says_so(self) -> None:
        st = Mock()
        run_render.render_timeline(st, run())
        self.assertIn("No timeline entries", st.caption.call_args.args[0])


class RunCardTest(unittest.TestCase):
    """The card names the run it opened, inside a container of its own."""

    def test_the_header_names_the_run_and_its_repo(self) -> None:
        st = MagicMock()
        run_render.render_run(st=st, run=run())
        st.container.assert_called_once_with(border=True)
        self.assertIn(f"Run #{ISSUE} · {REPO}", _markup(st))

    def test_a_repoless_run_still_reads_as_one(self) -> None:
        st = MagicMock()
        run_render.render_run_card(st, run(repo=""))
        self.assertIn("unknown repo", _markup(st))

    def test_run_and_turn_keep_their_own_bases(self) -> None:
        # The run row shows the amount its CLI reported and the strip the
        # turn's own API estimate; neither borrows the other's basis.
        st = MagicMock()
        run_render.render_run_card(st, run(
            run_usage=_REPORTED_RUN,
            turns=(models.TurnUsageView(turn=_FIRST_TURN, cost_evidence=cost(
                usage_cost.COMPLETE,
                (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN_COST),
            )),),
            steps=(step(ASSISTANT_MESSAGE, turn=_FIRST_TURN, content="a"),),
        ))
        blob = _markup(st)
        self.assertIn("$1.50 (CLI-reported)", blob)
        self.assertIn("$0.0123 (Anthropic API token estimate)", blob)
        self.assertNotIn("$0.01 (", blob)


if __name__ == "__main__":
    unittest.main()
