# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one JSONL record hashes to, and which of its fields the table names.

The hash is the dedup key the INSERT arbitrates on, so its encoding is pinned
to the one the sink wrote the line with rather than chosen here. The parse
beside it answers a narrower question than validation: every required field
either narrows to the type its column is declared as or the whole record is
refused, because a row the table would reject is cheaper to skip than to send.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from orchestrator.observability.analytics.sync.columns import (
    COL_EVENT,
    COL_ISSUE,
    COL_REPO,
    COL_TS,
    PROMOTED_COLUMNS,
    REQUIRED_KEYS,
)


def canonical_json(record: dict) -> str:
    """Stable JSON form used for the content hash.

    Must match `analytics.sink.append_jsonl_record`'s on-disk encoding
    (`sort_keys=True`, default separators) so a record round-trips
    through file -> parse -> hash without drift.
    """
    return json.dumps(record, sort_keys=True)


def content_hash(record: dict) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def parse_ts(raw: Any) -> datetime | None:
    """Parse the `ts` field into a timezone-aware datetime.

    The sink always writes an explicit `+00:00`. A line without an offset
    (a hand-edited one) is read as UTC, the reading
    `retention_scan.prune_timestamp` gives the same line, so the sync and
    the prune agree on when it happened. Returns None when the input is
    missing or unparseable; the caller treats that as a malformed-line
    skip.
    """
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def required_text(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    return raw


def issue_number(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def required_columns(record: dict) -> dict[str, Any] | None:
    if any(key not in record for key in REQUIRED_KEYS):
        return None
    timestamp = parse_ts(record.get(COL_TS))
    repo = required_text(record.get(COL_REPO))
    issue = issue_number(record.get(COL_ISSUE))
    event = required_text(record.get(COL_EVENT))
    if timestamp is None or repo is None or issue is None or event is None:
        return None
    return {
        COL_TS: timestamp,
        COL_REPO: repo,
        COL_ISSUE: issue,
        COL_EVENT: event,
    }


def extra_columns(record: dict, columns: dict[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    for key, field_value in record.items():
        if key in REQUIRED_KEYS:
            continue
        if key in PROMOTED_COLUMNS:
            columns[key] = field_value
        else:
            extras[key] = field_value
    return extras
