# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one run is identified by in a metadata tile, a table row, and a label."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import constants, models, run_html
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    CODEX_TOKENS,
    REPO,
    TOOL_BASH,
    TOOL_CALL,
    TOOL_RESULT,
    cost,
    run,
    step,
)

_UNSAFE_REPO = "o/<r&>"

_ESCAPED_REPO = "o/&lt;r&amp;&gt;"

_REVIEW_ROUND = 2

_INPUT_TOKENS = 12000

_OUTPUT_TOKENS = 340

_CACHED_TOKENS = 9000

_REPORTED_COST = 0.83

_ESTIMATED_COST = 0.4

_BLENDED_CELL = (
    "<td>$1.23 (blended: CLI-reported $0.83 + Gemini API token estimate "
    "$0.40)</td>"
)


class MetaHtmlTest(unittest.TestCase):
    """The identity grid draws the fields the record carried, and no others."""

    def test_only_present_fields_render(self) -> None:
        rendered = run_html.meta_html(
            run(session_id="sess-1", review_round=_REVIEW_ROUND),
        )
        self.assertIn(">Repo</div>", rendered)
        self.assertIn(f">{REPO}</div>", rendered)
        self.assertIn(">Review round</div>", rendered)
        self.assertIn(">sess-1</div>", rendered)
        # No retry count on this run -> the tile is omitted entirely, so an
        # absent field never reads as a recorded blank.
        self.assertNotIn(">Retry count</div>", rendered)

    def test_html_escaped(self) -> None:
        rendered = run_html.meta_html(run(repo=_UNSAFE_REPO))
        self.assertIn(_ESCAPED_REPO, rendered)
        self.assertNotIn(_UNSAFE_REPO, rendered)


class LabeledChipsHtmlTest(unittest.TestCase):
    """A chip row is drawn, marked empty, or dropped, depending on the ask."""

    def test_label_and_pills(self) -> None:
        rendered = run_html.labeled_chips_html("Tools offered", [TOOL_BASH, "Edit"])
        self.assertIn("Tools offered", rendered)
        self.assertIn(">Bash</span>", rendered)
        self.assertIn(">Edit</span>", rendered)

    def test_empty_is_blank(self) -> None:
        self.assertEqual(run_html.labeled_chips_html("Tools", []), "")

    def test_empty_marker_renders_none_state(self) -> None:
        # With a marker, an empty list still renders the row and flags the
        # chip with the `none` empty-state class instead of a real pill, so
        # "nothing fired" is distinguishable from an omitted row.
        rendered = run_html.labeled_chips_html(
            "Skills triggered", [], empty_marker="none",
        )
        self.assertIn(">Skills triggered</span>", rendered)
        self.assertIn('class="orch-traj-chip none"', rendered)
        self.assertIn(">none</span>", rendered)

    def test_escaped(self) -> None:
        rendered = run_html.labeled_chips_html("Skills", ["<x>"])
        self.assertIn("&lt;x&gt;", rendered)
        self.assertNotIn("<x>", rendered)


class RunsTableHtmlTest(unittest.TestCase):
    """The overview table's headers, its cells, and its fixture marking."""

    def test_headers_and_row_cells(self) -> None:
        rendered = run_html.runs_table_html([
            run(
                review_round=1,
                steps=(
                    step(TOOL_CALL, name=TOOL_BASH),
                    step(TOOL_RESULT, tool_id="t"),
                ),
            ),
        ])
        for header in (
            "Issue", "Repo", "Stage", "Role", "Backend", "Round",
            "Steps", "Tool calls", "Tokens", "Cost", "Recorded",
        ):
            with self.subTest(header=header):
                self.assertIn(f">{header}</th>", rendered)
        self.assertIn("#42", rendered)
        self.assertIn(f">{REPO}</td>", rendered)
        # Two steps, one of which is a tool call.
        self.assertIn(">2</td>", rendered)
        self.assertIn(">1</td>", rendered)

    def test_a_row_counts_cached_input_once(self) -> None:
        # The token total leaves Codex's cached input out of its input, and
        # the cost is the run's own amount on its named basis.
        codex = run_html.run_table_row_html(run(run_usage=models.RunUsageView(
            input_tokens=_INPUT_TOKENS,
            output_tokens=_OUTPUT_TOKENS,
            cached_tokens=_CACHED_TOKENS,
            cost_evidence=cost(
                usage_cost.COMPLETE, (usage_cost.OPENAI_API_ESTIMATE, _ESTIMATED_COST),
            ),
            token_evidence=CODEX_TOKENS,
        )))
        self.assertIn('<td class="num">12,340</td>', codex)
        self.assertIn("<td>$0.40 (OpenAI API token estimate)</td>", codex)

    def test_a_row_names_its_cost_basis(self) -> None:
        for name, run_usage, cells in (
            (
                "mixed",
                models.RunUsageView(cost_evidence=cost(
                    usage_cost.COMPLETE,
                    (usage_cost.CLI_REPORTED, _REPORTED_COST),
                    (usage_cost.GEMINI_API_ESTIMATE, _ESTIMATED_COST),
                )),
                (_BLENDED_CELL,),
            ),
            (
                "absent basis",
                models.RunUsageView(
                    input_tokens=_INPUT_TOKENS,
                    cached_tokens=_CACHED_TOKENS,
                    cost_evidence=cost(
                        usage_cost.UNKNOWN,
                        (usage_cost.UNKNOWN_BASIS, _REPORTED_COST),
                    ),
                ),
                (
                    '<td class="num">unknown</td>',
                    "<td>$0.83 (basis unknown, completeness unknown)</td>",
                ),
            ),
            ("no summary", None, ("<td>cost unknown</td>",)),
        ):
            row = run_html.run_table_row_html(run(run_usage=run_usage))
            for cell in cells:
                with self.subTest(name, cell=cell):
                    self.assertIn(cell, row)

    def test_repo_escaped(self) -> None:
        rendered = run_html.runs_table_html([run(repo=_UNSAFE_REPO)])
        self.assertIn(_ESCAPED_REPO, rendered)
        self.assertNotIn(_UNSAFE_REPO, rendered)

    def test_only_a_fixture_row_is_tagged(self) -> None:
        # The dimming class and the tag are what let an operator who left the
        # toggle off tell a synthetic record apart from a real one.
        fixture = run(user_input=constants.FIXTURE_PROMPT)
        self.assertTrue(fixture.is_fixture)
        tagged = run_html.runs_table_html([fixture])
        self.assertIn('<tr class="fixture">', tagged)
        self.assertIn(">fixture</span>", tagged)

        real = run()
        self.assertFalse(real.is_fixture)
        plain = run_html.runs_table_html([real])
        self.assertNotIn('class="fixture"', plain)
        self.assertNotIn("orch-traj-fixture-tag", plain)


class RunPickerLabelTest(unittest.TestCase):
    """One run's label inside the cohort already chosen above the picker."""

    def test_fixture_run_prefixed(self) -> None:
        fixture = run(session_id="sess-9")
        self.assertTrue(fixture.is_fixture)
        label = run_html.run_picker_label(fixture)
        self.assertTrue(label.startswith(run_html.FIXTURE_LABEL_PREFIX))
        self.assertIn(fixture.detail_label(), label)

    def test_real_run_plain_label(self) -> None:
        # The per-run picker drops repo / issue (chosen in the cascading
        # selectors above it) and shows only the `detail_label` cohort.
        real = run()
        self.assertEqual(run_html.run_picker_label(real), real.detail_label())
        self.assertNotIn(real.repo, run_html.run_picker_label(real))


if __name__ == "__main__":
    unittest.main()
