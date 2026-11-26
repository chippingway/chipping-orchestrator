# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one reply's task snapshot is recorded as on the analytics sink.

A snapshot names its source invocation whole, the road it came down, the
requirements revision its run was handed, and the task reference a reviewer
of a report stamped with that revision names it by; every problem is a
diagnostic naming the item, its category, the counts the collection
reached, and a bounded excerpt where there is a line. The records ride the
sink's own encoding into the database's `extras`, and a sink that is off
reads nothing at all.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.observations import recorder
from orchestrator.observability.analytics.sync import records as sync_records, rows
from tests.observability.analytics.observations import observation_test_support as _support

_DIAGNOSTIC = "observation_diagnostic"
_ATTACHMENT_KIND = "task-snapshot"
_TASK_REF = "task_ref"
_REVISION = "requirements_revision"

# What every record names beside its own fields.
_COMMON = MappingProxyType({
    "repo": _support.REPO,
    "issue": _support.ISSUE,
    "stage": _support.STAGE,
    "observation_version": 1,
    _support.SOURCE_FIELD: _support.SOURCE,
    "route": "implementation",
    _REVISION: _support.REVISION,
    _TASK_REF: _support.TASK_REF,
})


def _without_ts(record: dict) -> dict:
    return {key: field for key, field in record.items() if key != "ts"}


def _whole(text: str) -> dict:
    """A text a record kept whole."""
    return {_support.TEXT: text, _support.CHARS: len(text), _support.TRUNCATED: False}


def _diagnostic(category: str, counts: dict, line: str) -> dict:
    """The diagnostic a refused `line` becomes, beside everything every record names."""
    return {
        **_COMMON,
        _support.EVENT: _DIAGNOSTIC,
        "item": _ATTACHMENT_KIND,
        _support.CATEGORY: category,
        _support.COUNTS: counts,
        _support.EXCERPT_FIELD: _whole(line),
    }


class SnapshotRecordTest(_support.SinkCase):
    """A snapshot's record, and every problem's diagnostic."""

    def test_a_snapshot_names_its_source_and_task(self) -> None:
        recorded = self.record(_support.reply(f"Done.\n{_support.snapshot_line()}"))
        expected = {
            **_COMMON,
            _support.EVENT: "task_snapshot",
            "attachment_version": 1,
            _support.DESCRIPTION_FIELD: _whole(_support.DESCRIPTION),
        }
        self.assertEqual([_without_ts(record) for record in recorded], [expected])

    def test_an_unknown_identity_stays_unknown(self) -> None:
        # A cycle or comment the identity could not read is null, never a
        # guess; a road holding no revision names no task reference.
        damaged = replace(_support.INVOCATION, comment=None, cycle=None)
        unknown = replace(_support.RUN, invocation=damaged, requirements_revision=None)
        snapshot = self.record(_support.reply(_support.snapshot_line()), unknown)[0]
        source = snapshot[_support.SOURCE_FIELD]
        self.assertEqual((source["comment"], source["cycle"]), (None, None))
        self.assertNotIn(_REVISION, snapshot)
        self.assertNotIn(_TASK_REF, snapshot)

    def test_each_problem_is_a_diagnostic(self) -> None:
        malformed = "ANALYTICS: task-snapshot v1 {broken"
        misplaced = _support.snapshot_line()
        recorded = self.record(_support.reply(f"Done.\n{malformed}", f"{_support.OUTCOME}{misplaced}\n"))
        counts = {"found": 2, "recorded": 0}
        expected = [_diagnostic("malformed", counts, malformed), _diagnostic("misplaced", counts, misplaced)]
        self.assertEqual([_without_ts(record) for record in recorded], expected)

    def test_a_missing_snapshot_has_no_excerpt(self) -> None:
        # And a reply with no outcome was asked for nothing, so recording it
        # adds no record.
        missing = self.record(_support.reply("Done."))
        read = [
            (record[_support.CATEGORY], record[_support.COUNTS], _support.EXCERPT_FIELD in record)
            for record in missing
        ]
        self.assertEqual(read, [("missing", {"found": 0, "recorded": 0}, False)])
        self.assertEqual(self.record("A question for the human?"), missing)

    def test_records_ride_the_sink_encoding(self) -> None:
        # Each line is the canonical encoding the sync hashes, so a replay of
        # the same line deduplicates; what no column names lands in `extras`.
        self.record(_support.reply(f"Done.\n{_support.snapshot_line()}"))
        line = self.path.read_text(encoding="utf-8").splitlines()[0]
        prepared, refusal = rows.prepare_record(line)
        self.assertIsNone(refusal)
        self.assertEqual(sync_records.canonical_json(json.loads(line)), line)
        columns, extras = prepared.columns, prepared.extras
        self.assertEqual(columns[_support.EVENT], "task_snapshot")
        self.assertEqual(columns["stage"], _support.STAGE)
        self.assertEqual(
            (extras[_support.SOURCE_FIELD], extras[_TASK_REF], extras[_support.DESCRIPTION_FIELD]),
            (_support.SOURCE, _support.TASK_REF, _whole(_support.DESCRIPTION)),
        )

    def test_a_disabled_sink_reads_nothing(self) -> None:
        finding = MagicMock(side_effect=_support.outcome_at)
        observed = recorder.ObservedReply(_support.reply("Done."), finding)
        with patch.object(analytics_settings, "ANALYTICS_LOG_PATH", None):
            recorder.record_task_snapshot(_support.RUN, observed)
        finding.assert_not_called()
        self.assertEqual(self.written(), [])


if __name__ == "__main__":
    unittest.main()
