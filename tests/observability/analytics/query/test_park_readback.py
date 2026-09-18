# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A human-wait record read back whole, from its recorder through ingest to a trace.

The recorder builds the record, the ingest's own row preparation decides which
column each field lands in, and the per-issue read selects it back -- so the
record under test is the one a park produces rather than a hand-built row, and
the columns it is stored under are the ones the INSERT names.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.analytics.query.query_rows import IssueEventQueryRow
from orchestrator.observability.analytics.query.raw_reads import get_issue_events
from orchestrator.observability.analytics.recording import events as recording_events
from orchestrator.observability.analytics.recording.models import PARK_AWAITING_HUMAN_SIGNATURE
from orchestrator.observability.analytics.sync import (
    columns as sync_columns,
    records as sync_records,
    rows as sync_rows,
)
from tests.observability.analytics.query.query_fake_driver import FakeConnection

_REPO = "owner/r"

_ISSUE = 7

_STAGE = "implementing"

# One park carrying a value for every field its recorder accepts beyond the
# envelope, so the readback covers the whole vocabulary rather than the fields
# one stage happens to pass. `timed_out` is False rather than True because a
# stored False is the value a careless narrowing turns into None.
_PARK_CORRELATION = MappingProxyType({
    "reason": "agent_question",
    "route": "dev_fix",
    "agent_role": "developer",
    "backend": "claude",
    "agent_spec": "claude:opus",
    "session_id": "sess-park-2",
    "resume_session_id": "sess-park-1",
    "review_round": 2,
    "retry_count": 1,
    "pr_number": 42,
    "conflict_round": 3,
    "dirty_files": 4,
    "exit_code": 0,
    "timed_out": False,
    "sha": "0123456789abcdef0123456789abcdef01234567",
    "reservation_id": "0123456789ab-3",
})

# The envelope fields the recorder binds outside the correlation above.
_PARK_ENVELOPE = frozenset(("repo", "issue", "stage"))

_PROMOTED = frozenset(_PARK_CORRELATION) & frozenset(sync_columns.PROMOTED_COLUMNS)


def _recorded_park_line() -> str:
    """The JSONL line the analytics sink is handed for the park above.

    The append is intercepted on the recorder's own owner, and the record is
    encoded the way the ingest pins the sink's on-disk form to.
    """
    with patch.object(recording_events, "append_record") as append:
        recording_events.record_park_awaiting_human(
            repo=_REPO,
            issue=_ISSUE,
            stage=_STAGE,
            **_PARK_CORRELATION,
        )
        return sync_records.canonical_json(append.call_args.args[0])


def _stored_trace_row(line: str, json_adapter) -> tuple:
    """What the trace's SELECT reads back for one ingested JSONL line.

    The ingest's own INSERT is what decides which column a field lands in, so
    its statement is read for the column order the prepared cells follow, and
    the trace's named row for the order they are selected back in.
    """
    prepared, _ = sync_rows.prepare_record(line)
    provenance = sync_rows.RowProvenance(
        source_path=None,
        source_line=1,
        content_hash=prepared.content_hash,
    )
    column_clause = sync_rows.build_insert_sql().split("(", 1)[1]
    stored = dict(zip(
        column_clause.split(")", 1)[0].split(", "),
        sync_rows.row_values(
            prepared.columns, prepared.extras, provenance, json_adapter,
        ),
        strict=True,
    ))
    return tuple(stored[column] for column in IssueEventQueryRow._fields)


def _read_back(json_adapter):
    """Record the park, ingest it under `json_adapter`, and read it back."""
    stored = _stored_trace_row(_recorded_park_line(), json_adapter)
    trace = get_issue_events(
        repo=_REPO, issue=_ISSUE, conn=FakeConnection(rows=(stored,)),
    )
    return trace[0]


class ParkReadbackTest(unittest.TestCase):
    """Every field a park carries lands where the ingest routes it -- a promoted
    column or the `extras` blob -- and the trace reads both, so nothing a park
    was correlated by is lost between the sink and the page, and nothing
    needed a column the table does not already have.
    """

    def test_the_park_covers_the_recorder_vocabulary(self) -> None:
        # A field the recorder gains and this park does not carry would go
        # unproven below, so the two have to be widened together.
        self.assertEqual(
            frozenset(PARK_AWAITING_HUMAN_SIGNATURE.parameters),
            _PARK_ENVELOPE | frozenset(_PARK_CORRELATION),
        )

    def test_every_park_field_reads_back(self) -> None:
        # psycopg hands a JSONB cell back as its own object and another driver
        # as the JSON text, so the park has to read back whole either way.
        for adapter in (dict, sync_records.canonical_json):
            with self.subTest(adapter=adapter.__name__):
                park = _read_back(adapter)
                self.assertEqual(
                    (park.event, park.stage),
                    ("park_awaiting_human", _STAGE),
                )
                self.assertEqual(
                    {name: getattr(park, name) for name in _PROMOTED},
                    {name: _PARK_CORRELATION[name] for name in _PROMOTED},
                )
                self.assertEqual(
                    park.extras,
                    {
                        name: field_value
                        for name, field_value in _PARK_CORRELATION.items()
                        if name not in _PROMOTED
                    },
                )


if __name__ == "__main__":
    unittest.main()
