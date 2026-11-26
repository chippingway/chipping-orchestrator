# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the one Cost details section says about a selection, and what it explains once for the whole page.

Each selection is the cohort the reader hands back for runs stating the shared usage cases, so the section is read
for what an operator opening it sees: the selection's amount and its own status, each source's part of it with the
dates an estimate's rates were verified on, the runs counted by how much of their usage was priced, and the bar sizing
it by recorded cost source -- for a mix of sources, a subtotal, an amount stated with no cost evidence, no usage, no
run at all, and a complete zero alike. The explanation beneath names every status the page marks a value with and
calls no amount a verified charge. The section's label carries the unpriced-run warning, read from both sides of its
share. Why the selection's unpriced runs have no amount is listed by model and reason, as its own read counts them,
the runs recorded without a reason under `Reason unavailable`, and every reason is explained beneath.

The body is one HTML block, opened by a tag and holding no blank line, because Markdown would otherwise read two
dollar amounts as a formula; that shape is pinned here too.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query.cost_models import CostCoverageRow, UnpricedReasonRow
from orchestrator.observability.dashboard import cost_details, spend_text, unpriced_text
from orchestrator.observability.usage import cost_evidence as usage_cost, unpriced as usage_unpriced
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.card_test_support import COST_SOURCE_REPORTED, REPORTED_COLOR, card_theme
from tests.observability.dashboard.page_render_test_support import RecordingRegion, markup_in, modules

_LABEL = cost_details.COST_DETAILS_LABEL

_COVERAGE = (CostCoverageRow(cost_source=COST_SOURCE_REPORTED, runs=1, total_tokens=100),)

_SELECTION = "<p><b>This selection</b>: {spend}</p>"

_RUNS = "<p><b>Runs</b>: {counts}</p>"

# A record an earlier build wrote with no cost evidence and no amount at all.
_NO_EVIDENCE = usage_cost.recorded_cost(cases.unevidenced_record(1, cost_usd=None))

# Each selection, what it reads as, the source lines listed under it, and how its runs are counted.
_SELECTIONS = (
    (
        "mixed sources",
        (cases.REPORTED, cases.GEMINI_ESTIMATE, cases.BLENDED),
        "$0.69",
        (
            "CLI-reported · $0.52",
            "Gemini API token estimate · $0.12 · rates verified 2026-10-29",
            "OpenAI API token estimate · $0.05 · rates verified 2026-10-29",
        ),
        "3 total · 3 fully priced · 0 unpriced or partly priced · 0 no usage · 0 no cost evidence",
    ),
    (
        "incomplete",
        (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED),
        f"$0.50 · {spend_text.SUBTOTAL}",
        ("Anthropic API token estimate · $0.50 · rates verified 2026-10-29",),
        "3 total · 1 fully priced · 2 unpriced or partly priced · 0 no usage · 0 no cost evidence",
    ),
    (
        "unknown evidence",
        (cases.REPORTED, cases.ABSENT_BASIS, _NO_EVIDENCE),
        f"$0.49 · {spend_text.COMPLETENESS_UNKNOWN}",
        ("CLI-reported · $0.42", "basis unknown · $0.07"),
        "3 total · 1 fully priced · 0 unpriced or partly priced · 0 no usage · 2 no cost evidence",
    ),
    (
        "unpriced only",
        (cases.UNPRICED,),
        spend_text.UNPRICED,
        (),
        "1 total · 0 fully priced · 1 unpriced or partly priced · 0 no usage · 0 no cost evidence",
    ),
    (
        "no usage",
        (cases.NO_USAGE, cases.NO_USAGE),
        spend_text.NO_USAGE,
        (),
        "2 total · 0 fully priced · 0 unpriced or partly priced · 2 no usage · 0 no cost evidence",
    ),
    (
        "complete zero",
        (cases.COMPLETE_ZERO,),
        "$0.00",
        ("CLI-reported · $0.00",),
        "1 total · 1 fully priced · 0 unpriced or partly priced · 0 no usage · 0 no cost evidence",
    ),
)

_ASTRA = "gpt-6-astra"

_ASTRA_RUNS = 8

# The observed selection: eight GPT-6 Astra runs, each unpriced for both reasons its record gave.
_OBSERVED_REASONS = (
    UnpricedReasonRow(_ASTRA, usage_unpriced.INDETERMINATE_REQUEST_TIER, _ASTRA_RUNS),
    UnpricedReasonRow(_ASTRA, usage_unpriced.MISSING_CACHE_WRITE_COUNT, _ASTRA_RUNS),
)

# Reason counts as the read ranks them -- separate reasons on separate models, and the runs an earlier build recorded
# with none, under the model they ran -- and the lines they are listed as.
_REASON_ROWS = (
    UnpricedReasonRow("third-party-model-x", usage_unpriced.MISSING_MODEL_PRICE, 3),
    UnpricedReasonRow("gpt-5.6-sol", usage_unpriced.MISSING_CACHE_WRITE_COUNT, 2),
    UnpricedReasonRow("claude-opus-4-7", usage_unpriced.MISSING_CACHE_WRITE_LIFETIME, 1),
    UnpricedReasonRow(_ASTRA, None, 2),
)

_REASON_LINES = (
    "third-party-model-x · Missing model price · 3 runs",
    "gpt-5.6-sol · Missing cache-write count · 2 runs",
    "claude-opus-4-7 · Missing cache-write lifetime · 1 run",
    f"{_ASTRA} · {unpriced_text.REASON_UNAVAILABLE} · 2 runs",
)

# What the reason list opens with, ahead of its lines.
_REASONS_HEADING = f"<p><b>{unpriced_text.UNPRICED_REASONS_HEADING}</b></p>"

# Priced runs beside one short run: a tenth of ten, and a hundredth of a hundred.
_TENTH = 9

_HUNDREDTH = 99

# Selections and whether their label warns: the share of runs left unpriced or partly priced reaching a tenth.
_WARNINGS = (
    (
        "a tenth exactly",
        (*(cases.REPORTED,) * _TENTH, cases.INCOMPLETE_SUBTOTAL),
        f"{_LABEL} · 1 of 10 runs unpriced or partly priced",
    ),
    ("one in a hundred", (*(cases.REPORTED,) * _HUNDREDTH, cases.UNPRICED), _LABEL),
    ("no evidence", (cases.ABSENT_BASIS, cases.ABSENT_BASIS), _LABEL),
    ("no usage", (cases.NO_USAGE,), _LABEL),
    ("no run", (), _LABEL),
)


def _listed(sources: tuple[str, ...]) -> str:
    """The lines a selection lists, as its sources are listed under its amount or its reasons under its runs."""
    lines = "".join(f"<li>{source}</li>" for source in sources)
    return f"<ul>{lines}</ul>"


def _details(*costs: usage_cost.CostEvidence, coverage=_COVERAGE, reasons=()) -> str:
    return cost_details.cost_details_html(cohort_cases.cohort(*costs), coverage, reasons, theme=card_theme())


class SelectionTest(unittest.TestCase):
    """The selection's amount, its sources, and its runs, as the filters narrowed it."""

    def test_each_selection_states_sources_and_runs(self) -> None:
        for name, costs, spend, sources, counts in _SELECTIONS:
            with self.subTest(selection=name):
                self._assert_selection(cohort_cases.cohort(*costs), spend, sources, counts)

    def test_a_selection_with_no_run_says_so_alone(self) -> None:
        self.assertEqual(
            cost_details.selection_html(cohort_cases.cohort()),
            _SELECTION.format(spend=spend_text.NO_RUNS),
        )

    def _assert_selection(self, cost, spend: str, sources: tuple[str, ...], counts: str) -> None:
        selection = cost_details.selection_html(cost)
        self.assertTrue(selection.startswith(_SELECTION.format(spend=spend)))
        self.assertEqual(_listed(sources) in selection, bool(sources))
        self.assertTrue(selection.endswith(_RUNS.format(counts=counts)))


class ExplanationTest(unittest.TestCase):
    """What the page's words mean, said once beneath the selection."""

    def test_every_status_on_the_page_is_explained(self) -> None:
        details = _details(cases.REPORTED)
        for status in (
            spend_text.SUBTOTAL,
            spend_text.COMPLETENESS_UNKNOWN,
            spend_text.UNPRICED,
            spend_text.COST_UNKNOWN,
            spend_text.NO_USAGE,
            spend_text.NO_RUNS,
            spend_text.SOURCES_DIFFER,
        ):
            with self.subTest(status=status):
                self.assertIn(f"<li><b>{status}</b>: ", details)
        self.assertIn("A $0.00 with no label is a genuine zero.", details)

    def test_no_amount_is_called_a_verified_charge(self) -> None:
        # Both sources are said to be what they are -- what the CLI printed and
        # a token-only list-price estimate -- and the one sentence naming a
        # verified charge denies it of every amount on the page.
        details = _details(cases.REPORTED, cases.GEMINI_ESTIMATE)
        self.assertIn("No amount on this page is a verified charge.", details)
        self.assertEqual(details.count("verified charge"), 1)
        self.assertIn("Nothing checks it against an invoice", details)
        self.assertIn("is not what anyone was billed", details)
        self.assertIn("Antigravity usage is priced as Gemini API usage", details)

    def test_every_reason_is_explained(self) -> None:
        details = _details(cases.UNPRICED)
        for label in (*unpriced_text.REASON_LABELS.values(), unpriced_text.REASON_UNAVAILABLE):
            with self.subTest(reason=label):
                self.assertIn(f"<li><b>{label}</b>: ", details)
        self.assertIn("is counted under each, so the counts by model and reason overlap.", details)

    def test_the_token_share_split_is_an_allocation(self) -> None:
        self.assertIn("an allocation, not a measured cache charge", _details(cases.REPORTED))

    def test_the_coverage_bar_rides_beside_it(self) -> None:
        self.assertIn(f"background:{REPORTED_COLOR}", _details(cases.REPORTED))
        self.assertNotIn("orch-cov-bar", _details(cases.REPORTED, coverage=()))

    def test_the_body_is_one_html_block(self) -> None:
        # Markdown reads a pair of dollar amounts as a formula outside a block
        # opened by a tag and unbroken by a blank line.
        details = _details(cases.REPORTED, cases.GEMINI_ESTIMATE)
        self.assertTrue(details.startswith('<div class="orch-cost-details">'))
        self.assertTrue(details.endswith("</div>"))
        self.assertNotIn("\n\n", details)


class UnpricedReasonsTest(unittest.TestCase):
    """Why the selection's unpriced runs have no amount, counted by model and reason."""

    def test_the_observed_runs_name_both_reasons(self) -> None:
        # Eight GPT-6 Astra runs on an active catalogue row are Unpriced, and
        # the section says why: each run's cumulative input left its request
        # tier indeterminate and its CLI counters left its cache-write count
        # missing, so all eight are counted under both reasons.
        runs = (cases.UNPRICED,) * _ASTRA_RUNS
        cost = cohort_cases.cohort(*runs)
        details = _details(*runs, reasons=_OBSERVED_REASONS)
        self.assertEqual(
            cost_details.cost_details_label(cost),
            f"{cost_details.COST_DETAILS_LABEL} · 8 of 8 runs unpriced or partly priced",
        )
        self.assertIn(_SELECTION.format(spend=spend_text.UNPRICED), details)
        listed = _listed((
            f"{_ASTRA} · Indeterminate request tier · 8 runs",
            f"{_ASTRA} · Missing cache-write count · 8 runs",
        ))
        self.assertIn(f"{_REASONS_HEADING}{listed}", details)

    def test_each_count_is_listed_as_read(self) -> None:
        details = _details(cases.UNPRICED, reasons=_REASON_ROWS)
        self.assertIn(f"{_REASONS_HEADING}{_listed(_REASON_LINES)}", details)

    def test_no_unpriced_run_lists_nothing(self) -> None:
        self.assertNotIn(unpriced_text.UNPRICED_REASONS_HEADING, _details(cases.REPORTED))

    def test_a_model_name_is_escaped(self) -> None:
        details = _details(cases.UNPRICED, reasons=(UnpricedReasonRow("<b>x</b>", None, 1),))
        self.assertIn("<li>&lt;b&gt;x&lt;/b&gt; · Reason unavailable · 1 run</li>", details)


class LabelTest(unittest.TestCase):
    """The unpriced-run warning the section's label carries."""

    def test_the_warning_starts_at_a_tenth(self) -> None:
        # A run with no cost evidence is not counted as unpriced: nothing
        # states whether it was, and its own status already says so.
        for name, costs, label in _WARNINGS:
            with self.subTest(selection=name):
                self.assertEqual(cost_details.cost_details_label(cohort_cases.cohort(*costs)), label)


class RenderTest(unittest.TestCase):
    """The section as a page draws it."""

    def test_it_is_drawn_collapsed_as_markup(self) -> None:
        st = RecordingRegion()
        cost = cohort_cases.cohort(cases.REPORTED, cases.UNPRICED)
        cost_details.render_cost_details(modules(st), cost, (), _OBSERVED_REASONS[:1])
        self.assertEqual(
            st.markup,
            [
                (f"{_LABEL} · 1 of 2 runs unpriced or partly priced", {"expanded": False}),
                (
                    cost_details.cost_details_html(cost, (), _OBSERVED_REASONS[:1], theme=None),
                    {"unsafe_allow_html": True},
                ),
            ],
        )
        self.assertIn(f"$0.42 · {spend_text.SUBTOTAL}", markup_in(st))


if __name__ == "__main__":
    unittest.main()
