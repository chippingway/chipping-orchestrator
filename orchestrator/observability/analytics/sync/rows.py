# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One JSONL line turned into the row the INSERT sends, or into a skip reason.

The statement and the parameter tuple are built from the same column list in
the same order, so the row is positional and no per-row dict-to-tuple mapping
stands between the two. That list is the promoted fields followed by the
columns derived from an `agent_exit` record's usage evidence, so a row carries
what its record's cost and tokens mean beside the raw values it copied.

Every way a line can fail -- not JSON, JSON that is not an object, a required
field the table would reject -- resolves to a reason string instead of an
exception: one bad line in a rotated JSONL file must not abort the replay of
the thousands after it. A blank line comes back with neither a row nor a
reason, which is what keeps it out of the malformed tally.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from orchestrator.observability.analytics.sync.columns import (
    JSONB_COLUMNS,
    TABLE_COLUMNS,
)
from orchestrator.observability.analytics.sync.evidence import derived_columns
from orchestrator.observability.analytics.sync.records import (
    content_hash,
    extra_columns,
    required_columns,
)


def split_row(record: dict) -> tuple[dict, dict] | None:
    """Promote known columns, derive the evidence ones, and route the rest to `extras`.

    Returns (columns, extras), or None if a required key is missing
    or `ts` does not parse. The caller treats None as a malformed-line
    skip so a record with garbled `ts` does not abort the entire sync.
    """
    columns = required_columns(record)
    if columns is None:
        return None
    extras = extra_columns(record, columns)
    columns.update(derived_columns(record))
    return columns, extras


def build_insert_sql() -> str:
    """Construct the parameterised INSERT once per call.

    All promoted and derived columns are emitted in a fixed order so
    the parameter tuple in `row_values` lines up positionally without a
    per-row dict-to-tuple mapping.
    """
    columns = (
        *TABLE_COLUMNS,
        "extras",
        "source_path",
        "source_line",
        "content_hash",
    )
    placeholders = ", ".join("%s" for _ in columns)
    column_list = ", ".join(columns)
    return f"INSERT INTO analytics_events ({column_list}) VALUES ({placeholders}) ON CONFLICT (content_hash) DO NOTHING"


@dataclass(frozen=True)
class RowProvenance:
    """Source identity and stable dedup hash for one prepared row."""

    source_path: str | None
    source_line: int
    content_hash: str


def row_values(
    columns: dict,
    extras: dict,
    provenance: RowProvenance,
    json_adapter: Callable[[Any], Any],
) -> tuple:
    cells: list[Any] = []
    for col in TABLE_COLUMNS:
        cell = columns.get(col)
        if col in JSONB_COLUMNS and cell is not None:
            cell = json_adapter(cell)
        cells.append(cell)
    cells.append(json_adapter(extras) if extras else None)
    cells.append(provenance.source_path)
    cells.append(provenance.source_line)
    cells.append(provenance.content_hash)
    return tuple(cells)


@dataclass(frozen=True)
class PreparedRecord:
    """Validated promoted fields, extras, and hash for one JSONL record."""

    columns: dict[str, Any]
    extras: dict[str, Any]
    content_hash: str


def prepare_record(
    raw_line: str,
) -> tuple[PreparedRecord | None, str | None]:
    stripped = raw_line.strip()
    if not stripped:
        return None, None
    try:
        record = json.loads(stripped)
    except json.JSONDecodeError:
        return None, "not JSON"
    if not isinstance(record, dict):
        return None, "JSON not an object"
    split = split_row(record)
    if split is None:
        return None, "missing/invalid required keys"
    columns, extras = split
    return PreparedRecord(columns, extras, content_hash(record)), None
