# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an `agent_exit` record's usage evidence fills on its row.

The raw evidence rides in `extras`, where no view can fold it, so the row also carries what the record's cost and
tokens mean, read through the same readers every usage surface uses: each basis's amount in its own column, an
estimate's verification dates, the completeness, the cache overlap, and the non-overlapping token total. The cases
name the answers downstream aggregation must keep apart, and read them off the row the INSERT is sent.
"""
from __future__ import annotations

import json
import unittest
from typing import Any

from orchestrator.observability.analytics.sync import columns, records, rows
from orchestrator.observability.analytics.sync.evidence import derived_columns
from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens
from tests.observability.analytics import analytics_usage_cases as cases

_COMPLETENESS = columns.COST_COMPLETENESS

_TOTAL = columns.TOTAL_TOKENS

_OVERLAP = columns.TOKEN_CACHE_OVERLAP

_REPORTED_USD = "cost_cli_reported_usd"

_ANTHROPIC_USD = "cost_anthropic_estimate_usd"

_OPENAI_USD = "cost_openai_estimate_usd"

_GEMINI_USD = "cost_gemini_estimate_usd"

_UNKNOWN_USD = "cost_unknown_basis_usd"

_ANTHROPIC_DATES = "anthropic_rates_verified_on"

_OPENAI_DATES = "openai_rates_verified_on"

_GEMINI_DATES = "gemini_rates_verified_on"

_LEGACY_COST = 0.07

_CACHED_INPUT = 40

_UNKNOWN_OVERLAP = usage_tokens.UNKNOWN

# Each cost a producer writes, and the cost cells it fills: its completeness, and every amount under its own basis
# with an estimate's dates beside it. A cell the cost states nothing for is absent, which the INSERT sends as NULL.
_COST_CASES = (
    ("reported", cases.REPORTED, {_COMPLETENESS: usage_cost.COMPLETE, _REPORTED_USD: cases.REPORTED_USD}),
    (
        "anthropic estimate",
        cases.ANTHROPIC_ESTIMATE,
        {_COMPLETENESS: usage_cost.COMPLETE, _ANTHROPIC_USD: cases.ANTHROPIC_USD, _ANTHROPIC_DATES: [cases.VERIFIED]},
    ),
    (
        "gemini estimate",
        cases.GEMINI_ESTIMATE,
        {_COMPLETENESS: usage_cost.COMPLETE, _GEMINI_USD: cases.GEMINI_USD, _GEMINI_DATES: [cases.VERIFIED]},
    ),
    (
        "blended",
        cases.BLENDED,
        {
            _COMPLETENESS: usage_cost.COMPLETE,
            _REPORTED_USD: cases.BLENDED_REPORTED_USD,
            _OPENAI_USD: cases.BLENDED_OPENAI_USD,
            _OPENAI_DATES: [cases.VERIFIED],
        },
    ),
    (
        "incomplete subtotal",
        cases.INCOMPLETE_SUBTOTAL,
        {_COMPLETENESS: usage_cost.INCOMPLETE, _ANTHROPIC_USD: cases.SUBTOTAL_USD, _ANTHROPIC_DATES: [cases.VERIFIED]},
    ),
    ("unpriced", cases.UNPRICED, {_COMPLETENESS: usage_cost.INCOMPLETE}),
    ("complete zero", cases.COMPLETE_ZERO, {_COMPLETENESS: usage_cost.COMPLETE, _REPORTED_USD: 0}),
    ("no usage", cases.NO_USAGE, {_COMPLETENESS: usage_cost.NO_USAGE}),
)

_COST_CELLS = (_COMPLETENESS, *columns.COST_AMOUNT_COLUMNS.values(), *columns.RATE_DATE_COLUMNS.values())


def _cost_cells(record: dict[str, Any]) -> dict[str, Any]:
    """The cost cells a record fills, with the ones it states nothing for left out."""
    derived = derived_columns(record)
    return {column: derived[column] for column in _COST_CELLS if column in derived}


def _row_cell(record: dict[str, Any], column: str) -> Any:
    """One cell of the positional row the INSERT sends for `record`."""
    promoted, extras = rows.split_row(record)
    provenance = rows.RowProvenance(source_path=None, source_line=1, content_hash=records.content_hash(record))
    cells = rows.row_values(promoted, extras, provenance, json.dumps)
    return cells[columns.TABLE_COLUMNS.index(column)]


class DerivedCostCellsTest(unittest.TestCase):
    """Each basis lands in its own column, so a sum per column is a sum per basis."""

    def test_each_cost_fills_its_basis_columns(self) -> None:
        for name, spent, expected in _COST_CASES:
            with self.subTest(cost=name):
                self.assertEqual(_cost_cells(cases.usage_record(1, spent, cases.DISJOINT)), expected)

    def test_a_subtotal_keeps_its_amount(self) -> None:
        # `cost_usd` is the complete amount alone, so an incomplete cost leaves
        # it NULL while the subtotal it does state stays in its basis column.
        record = cases.usage_record(1, cases.INCOMPLETE_SUBTOTAL, cases.DISJOINT)
        self.assertIsNone(_row_cell(record, usage_cost.COST_USD))
        self.assertEqual(_row_cell(record, _ANTHROPIC_USD), cases.SUBTOTAL_USD)
        self.assertEqual(_row_cell(record, "cost_source"), usage_cost.UNKNOWN_PRICE_SOURCE)

    def test_a_record_without_evidence_reads_unknown(self) -> None:
        # An earlier build wrote no evidence, and evidence this format does not
        # serialize is none: either way the recorded amount is kept under the
        # `unknown` basis -- never a provider's, whatever its source or backend
        # says -- and a record with no valid amount states none.
        unserializable = cases.usage_record(1, cases.REPORTED, cases.DISJOINT, cost_usd=_LEGACY_COST)
        refused = unserializable[usage_cost.COST_EVIDENCE][usage_cost.CONTRIBUTIONS][0]
        refused[usage_cost.AMOUNT_USD] = -1
        for name, record, expected in (
            (
                "earlier build",
                cases.unevidenced_record(1, cost_usd=_LEGACY_COST, cost_source="estimated", backend="claude"),
                {_COMPLETENESS: usage_cost.UNKNOWN, _UNKNOWN_USD: _LEGACY_COST},
            ),
            ("no amount", cases.unevidenced_record(1, cost_source="reported"), {_COMPLETENESS: usage_cost.UNKNOWN}),
            ("unserializable", unserializable, {_COMPLETENESS: usage_cost.UNKNOWN, _UNKNOWN_USD: _LEGACY_COST}),
        ):
            with self.subTest(record=name):
                self.assertEqual(_cost_cells(record), expected)

    def test_an_estimate_keeps_its_dates_sorted_once(self) -> None:
        spent = cases.cost(
            usage_cost.COMPLETE,
            cases.contribution(
                usage_cost.GEMINI_API_ESTIMATE,
                cases.GEMINI_USD,
                cases.LATER_VERIFIED,
                cases.VERIFIED,
                cases.LATER_VERIFIED,
            ),
        )
        record = cases.usage_record(1, spent, cases.UNSETTLED)
        self.assertEqual(_row_cell(record, _GEMINI_DATES), [cases.VERIFIED, cases.LATER_VERIFIED])


class DerivedTokenCellsTest(unittest.TestCase):
    """The stored total counts each token once, and stays unknown where nothing settles how the counters overlap."""

    def test_the_total_follows_the_declared_overlap(self) -> None:
        for name, record, total, overlap in (
            # Claude's cache reads and writes sit beside its input, so they add.
            ("disjoint", cases.usage_record(1, cases.REPORTED, cases.DISJOINT), cases.CLAUDE_TOTAL, "disjoint"),
            # Codex's cached tokens are already inside its input count.
            (
                "within input",
                cases.usage_record(1, cases.OPENAI_ESTIMATE, cases.WITHIN_INPUT),
                cases.CODEX_TOTAL,
                "within-input",
            ),
            # Nothing establishes yet whether Antigravity's cache reads are input.
            ("unsettled", cases.usage_record(1, cases.GEMINI_ESTIMATE, cases.UNSETTLED), None, _UNKNOWN_OVERLAP),
            ("nothing observed", cases.usage_record(1, cases.NO_USAGE, cases.NOTHING_OBSERVED), 0, _UNKNOWN_OVERLAP),
            (
                "earlier build, no cache",
                cases.unevidenced_record(1, input_tokens=100, output_tokens=10),
                110,
                _UNKNOWN_OVERLAP,
            ),
            (
                "earlier build, cached",
                cases.unevidenced_record(1, input_tokens=100, output_tokens=10, cached_tokens=_CACHED_INPUT),
                None,
                _UNKNOWN_OVERLAP,
            ),
        ):
            with self.subTest(record=name):
                derived = derived_columns(record)
                self.assertEqual((derived[_TOTAL], derived[_OVERLAP]), (total, overlap))


class DerivedRowTest(unittest.TestCase):
    """Deriving adds cells beside the record; the record, its raw evidence, and its hash stay as written."""

    def test_raw_evidence_and_hash_stay_as_written(self) -> None:
        record = cases.usage_record(1, cases.BLENDED, cases.WITHIN_INPUT)
        written = json.dumps(record, sort_keys=True)
        prepared, reason = rows.prepare_record(written)
        self.assertIsNone(reason)
        self.assertEqual(prepared.content_hash, records.content_hash(json.loads(written)))
        self.assertEqual(
            {key: prepared.extras[key] for key in (usage_cost.COST_EVIDENCE, "token_evidence")},
            {usage_cost.COST_EVIDENCE: cases.BLENDED.to_dict(), "token_evidence": cases.WITHIN_INPUT.to_dict()},
        )
        self.assertEqual(prepared.columns[_TOTAL], cases.CODEX_TOTAL)

    def test_other_events_fill_no_evidence_cell(self) -> None:
        # Only an `agent_exit` states usage; a NULL here is no reading at all,
        # never an unknown cost or a zero-token run.
        stage_enter = {**cases.unevidenced_record(1, input_tokens=5), "event": "stage_enter"}
        self.assertEqual(derived_columns(stage_enter), {})
        for column in columns.DERIVED_COLUMNS:
            with self.subTest(column=column):
                self.assertIsNone(_row_cell(stage_enter, column))


if __name__ == "__main__":
    unittest.main()
