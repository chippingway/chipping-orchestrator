# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one reply's task snapshot is recorded as on the analytics sink.

A snapshot names its source invocation whole, the road it came down, what
the reply's report outcome read as, the requirements revision its prompt was
handed, and the task reference a reviewer of a report stamped with that
revision names it by; a reply with no snapshot is one diagnostic naming the
item, its category, the attachment lines found and readable, and a bounded
excerpt where there are lines. The records ride the
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
    "report_outcome": _support.READY,
    _REVISION: _support.REVISION,
    _TASK_REF: _support.TASK_REF,
})


def _without_ts(record: dict) -> dict:
    return {key: field for key, field in record.items() if key != "ts"}


def _whole(text: str) -> dict:
    """A text a record kept whole."""
    return {_support.TEXT: text, _support.CHARS: len(text), _support.TRUNCATED: False}


def _diagnostic(category: str, found: int, excerpt: str) -> dict:
    """The diagnostic `found` refused lines shown as `excerpt` become, beside everything every record names."""
    return {
        **_COMMON,
        _support.EVENT: _DIAGNOSTIC,
        "item": _ATTACHMENT_KIND,
        _support.CATEGORY: category,
        _support.COUNTS: {"found": found, "readable": 0},
        _support.EXCERPT_FIELD: _whole(excerpt),
    }


# A refused line, and two lines where one alone would read.
_MALFORMED_LINE = "ANALYTICS: task-snapshot v1 {broken"
_FIRST = _support.snapshot_line("first")
_SECOND = _support.snapshot_line("second")

# Replies with no snapshot, and the one diagnostic each becomes.
_REFUSED = (
    (_support.reply(f"Done.\n{_MALFORMED_LINE}"), _diagnostic("malformed", 1, _MALFORMED_LINE)),
    (
        _support.reply(_FIRST, f"{_support.OUTCOME}{_SECOND}\n"),
        _diagnostic("duplicate", 2, f"{_FIRST}\n{_SECOND}"),
    ),
)

# Replies carrying no attachment line, and what each one's outcome reads as.
_UNATTACHED = ((_support.reply("Done."), _support.READY), ("A question?", _support.NO_MARKER))


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

    def test_a_refused_reply_is_one_diagnostic(self) -> None:
        # One refused line is excerpted; two lines -- one above the outcome
        # that would read, one after it -- are a duplicate, excerpted together,
        # and no snapshot.
        for message, expected in _REFUSED:
            with self.subTest(category=expected[_support.CATEGORY]):
                self.path.unlink(missing_ok=True)
                recorded = [_without_ts(record) for record in self.record(message)]
                self.assertEqual(recorded, [expected])

    def test_a_missing_snapshot_has_no_excerpt(self) -> None:
        # Whatever the reply ends on: a question is asked for one too.
        for message, outcome in _UNATTACHED:
            with self.subTest(outcome=outcome):
                self.path.unlink(missing_ok=True)
                missing = self.record(message)[0]
                read = (missing[_support.CATEGORY], missing[_support.COUNTS], missing["report_outcome"])
                self.assertEqual(read, ("missing", {"found": 0, "readable": 0}, outcome))
                self.assertNotIn(_support.EXCERPT_FIELD, missing)

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

    def test_a_disabled_sink_frames_nothing(self) -> None:
        finding = MagicMock(side_effect=_support.framing)
        observed = recorder.ObservedReply(_support.reply("Done."), finding)
        with patch.object(analytics_settings, "ANALYTICS_LOG_PATH", None):
            recorder.record_task_snapshot(_support.RUN, observed)
        finding.assert_not_called()
        self.assertEqual(self.written(), [])


if __name__ == "__main__":
    unittest.main()
