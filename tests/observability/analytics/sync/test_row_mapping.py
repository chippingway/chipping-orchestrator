# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one JSONL line becomes on the way to the analytics events table."""
from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from orchestrator.observability.analytics.sync import columns, records, rows

_TS_FIELD = "ts"

_REPO_FIELD = "repo"

_ISSUE_FIELD = "issue"

_EVENT_FIELD = "event"

_MODELS_FIELD = "models"

_SAMPLE_TS = "2026-05-25T12:00:00+00:00"

_SAMPLE_REPO = "owner/repo"

_SAMPLE_EVENT = "agent_exit"

_SAMPLE_ISSUE = 42

_SAMPLE_STAGE = "implementing"

_SAMPLE_LINE = 7

_SAMPLE_PATH = "/logs/analytics.jsonl"

_SAMPLE_HASH = "hash-abc"

# A field no column exists for, which is what the extras blob has to catch.
_FUTURE_FIELD = "future_key"

_FUTURE_VALUE = "new"

# The part of a human-wait record no column exists for: why it waited, the road
# it came off, the pull request and commit it stands on, and a report revision
# no recorder passes today -- standing in for a field a newer writer adds.
_PARK_EXTRAS = MappingProxyType({
    "reason": "agent_question",
    "route": "dev_fix",
    "pr_number": 42,
    "sha": "0123456789abcdef0123456789abcdef01234567",
    "report_revision": 3,
})

# The four columns the INSERT's parameter tuple ends with, after the promoted
# list and the extras blob: where a row came from, and the hash it is
# deduplicated on.
_TRAILING_COLUMNS = ("extras", "source_path", "source_line", "content_hash")


def _record(**overrides: Any) -> dict:
    """One well-formed analytics record, with fields swapped in by keyword."""
    record = {
        _TS_FIELD: _SAMPLE_TS,
        _REPO_FIELD: _SAMPLE_REPO,
        _ISSUE_FIELD: _SAMPLE_ISSUE,
        _EVENT_FIELD: _SAMPLE_EVENT,
    }
    record.update(overrides)
    return record


class ContentHashTest(unittest.TestCase):
    """The dedup key is taken over the encoding the sink wrote the line with,
    so a record that round-trips through the file hashes to what is already
    stored rather than to a second row.
    """

    def test_canonical_json_sorts_the_keys(self) -> None:
        record = _record(zeta=1, alpha=2)
        self.assertEqual(records.canonical_json(record), json.dumps(record, sort_keys=True))

    def test_hash_keys_off_the_content_only(self) -> None:
        staged = _record(stage=_SAMPLE_STAGE)
        reordered = dict(reversed(list(staged.items())))
        self.assertEqual(
            records.content_hash(staged), records.content_hash(reordered),
        )
        self.assertNotEqual(
            records.content_hash(staged), records.content_hash(_record()),
        )


class RequiredFieldParseTest(unittest.TestCase):
    """Every required field either narrows to the type its column is declared
    as or the whole record is refused, because a row the table would reject
    costs more to send than to skip.
    """

    def test_naive_timestamp_reads_as_utc(self) -> None:
        # An older writer, or a hand-edit, leaves the offset off; the record
        # still has to hash and land where the offset-carrying one does.
        parsed = records.parse_ts(_SAMPLE_TS.removesuffix("+00:00"))
        self.assertEqual(parsed, records.parse_ts(_SAMPLE_TS))
        self.assertEqual(parsed.tzinfo, UTC)

    def test_unusable_timestamp_reads_as_none(self) -> None:
        for raw in ("", "not-a-timestamp", None, 1748174400):
            with self.subTest(raw=raw):
                self.assertIsNone(records.parse_ts(raw))

    def test_text_and_number_coercions(self) -> None:
        self.assertEqual(records.required_text(_SAMPLE_REPO), _SAMPLE_REPO)
        self.assertIsNone(records.required_text(""))
        self.assertIsNone(records.required_text(7))
        self.assertEqual(records.issue_number("42"), _SAMPLE_ISSUE)
        self.assertIsNone(records.issue_number(None))
        self.assertIsNone(records.issue_number("not-a-number"))

    def test_required_columns_are_narrowed(self) -> None:
        narrowed = records.required_columns(_record(issue="42"))
        self.assertEqual(narrowed[_ISSUE_FIELD], _SAMPLE_ISSUE)
        self.assertIsInstance(narrowed[_TS_FIELD], datetime)
        self.assertEqual(narrowed[_REPO_FIELD], _SAMPLE_REPO)
        self.assertEqual(narrowed[_EVENT_FIELD], _SAMPLE_EVENT)

    def test_an_unusable_required_field_refuses(self) -> None:
        for record in (
            {_TS_FIELD: _SAMPLE_TS},
            _record(ts="not-a-timestamp"),
            _record(repo=""),
            _record(issue="not-a-number"),
            _record(event=None),
        ):
            with self.subTest(record=record):
                self.assertIsNone(records.required_columns(record))


class ColumnRoutingTest(unittest.TestCase):
    """A field the table has a column for is promoted and everything else
    lands in `extras`, so a record from a newer orchestrator version loses
    nothing to a database that has no column for it yet.
    """

    def test_promoted_and_extra_fields_split(self) -> None:
        promoted, extras = rows.split_row(
            _record(stage=_SAMPLE_STAGE, future_key=_FUTURE_VALUE),
        )
        self.assertEqual(promoted["stage"], _SAMPLE_STAGE)
        self.assertEqual(extras, {_FUTURE_FIELD: _FUTURE_VALUE})

    def test_a_park_keeps_its_correlation(self) -> None:
        # The session is the one field here the table has a column for; the
        # rest ride in the blob, including a field the recorder does not know
        # yet, so widening a park is an emitter change rather than a migration.
        promoted, extras = rows.split_row(
            _record(
                event="park_awaiting_human",
                stage=_SAMPLE_STAGE,
                session_id="sess-park-1",
                **_PARK_EXTRAS,
            ),
        )
        self.assertEqual(
            (promoted[_EVENT_FIELD], promoted["stage"], promoted["session_id"]),
            ("park_awaiting_human", _SAMPLE_STAGE, "sess-park-1"),
        )
        self.assertEqual(extras, _PARK_EXTRAS)

    def test_required_fields_stay_out_of_extras(self) -> None:
        promoted = records.required_columns(_record())
        extras = records.extra_columns(_record(), promoted)
        self.assertEqual(extras, {})
        self.assertEqual(promoted[_REPO_FIELD], _SAMPLE_REPO)

    def test_a_refused_record_splits_to_none(self) -> None:
        self.assertIsNone(rows.split_row(_record(ts="not-a-timestamp")))


class InsertRowTest(unittest.TestCase):
    """The statement and the tuple that fills it are built from one column
    list in one order, so the row stays positional and no per-row mapping
    stands between them.
    """

    def test_insert_names_every_column_once(self) -> None:
        statement = rows.build_insert_sql()
        column_clause = statement.split("(", 1)[1]
        listed = column_clause.split(")", 1)[0].split(", ")
        required = len(columns.REQUIRED_KEYS)
        trailing = len(_TRAILING_COLUMNS)
        self.assertEqual(tuple(listed[:required]), columns.REQUIRED_KEYS)
        self.assertEqual(tuple(listed[-trailing:]), _TRAILING_COLUMNS)
        self.assertEqual(len(listed), len(frozenset(listed)))
        self.assertEqual(statement.count("%s"), len(listed))
        self.assertTrue(statement.endswith("ON CONFLICT (content_hash) DO NOTHING"))

    def test_row_follows_the_column_order(self) -> None:
        cells = self._cells(_record(backend="claude"))
        order = columns.PROMOTED_COLUMNS
        self.assertEqual(cells[order.index(_REPO_FIELD)], _SAMPLE_REPO)
        self.assertEqual(cells[order.index("backend")], "claude")
        self.assertIsNone(cells[order.index("turns")])
        self.assertEqual(len(cells), len(order) + len(_TRAILING_COLUMNS))

    def test_provenance_trails_the_row(self) -> None:
        cells = self._cells(_record(future_key=_FUTURE_VALUE))
        tail = cells[len(columns.PROMOTED_COLUMNS):]
        self.assertEqual(tail[0], json.dumps({_FUTURE_FIELD: _FUTURE_VALUE}))
        self.assertEqual(tail[1:], (_SAMPLE_PATH, _SAMPLE_LINE, _SAMPLE_HASH))

    def test_json_cells_pass_the_adapter(self) -> None:
        cells = self._cells(_record(models=["claude-opus"]))
        models_cell = cells[columns.PROMOTED_COLUMNS.index(_MODELS_FIELD)]
        self.assertEqual(models_cell, json.dumps(["claude-opus"]))
        # An empty extras blob is a NULL rather than an adapted `{}`, so a
        # record carrying nothing unknown reads back as having no extras.
        self.assertIsNone(cells[len(columns.PROMOTED_COLUMNS)])

    def _cells(self, record: dict) -> tuple:
        promoted, extras = rows.split_row(record)
        provenance = rows.RowProvenance(
            source_path=_SAMPLE_PATH,
            source_line=_SAMPLE_LINE,
            content_hash=_SAMPLE_HASH,
        )
        return rows.row_values(promoted, extras, provenance, json.dumps)


class PreparedLineTest(unittest.TestCase):
    """Every way one line can fail resolves to a reason string rather than an
    exception, so a single bad line never aborts the replay of the thousands
    after it -- and a blank line is not a failure at all.
    """

    def test_blank_line_is_not_malformed(self) -> None:
        for raw_line in ("", "   ", "\n"):
            with self.subTest(raw_line=raw_line):
                self.assertEqual(rows.prepare_record(raw_line), (None, None))

    def test_each_refused_shape_has_a_reason(self) -> None:
        for raw_line, reason in (
            ("{not json", "not JSON"),
            ("[1, 2]", "JSON not an object"),
            (json.dumps({_TS_FIELD: _SAMPLE_TS}), "missing/invalid required keys"),
            (json.dumps(_record(ts="nope")), "missing/invalid required keys"),
        ):
            with self.subTest(raw_line=raw_line):
                self.assertEqual(rows.prepare_record(raw_line), (None, reason))

    def test_prepared_record_carries_the_hash(self) -> None:
        record = _record(future_key=_FUTURE_VALUE)
        prepared, reason = rows.prepare_record(f"{json.dumps(record)}\n")
        self.assertIsNone(reason)
        self.assertEqual(prepared.content_hash, records.content_hash(record))
        self.assertEqual(prepared.extras, {_FUTURE_FIELD: _FUTURE_VALUE})
        self.assertEqual(prepared.columns[_EVENT_FIELD], _SAMPLE_EVENT)


if __name__ == "__main__":
    unittest.main()
