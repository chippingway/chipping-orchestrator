# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a by-age prune reads before it decides to rewrite anything.

The read half of retention, shared by both JSONL sinks: how a record's age is
established, what an unreadable one costs, and the split of a file into the
lines that survive a cutoff and the count that did not. Nothing here opens a
file for writing, so "is this record expired?" is answered in one place no
matter which sink asked.

The answer is deliberately conservative. A line that is not JSON, and a record
whose ``ts`` is missing, not a string, or unparseable, is kept verbatim: a
prune an operator cannot audit afterwards is worse than a file that keeps a few
lines nobody can interpret. A naive ``ts`` is read as UTC to match what the
writer emits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.observability.analytics.sink import log

_KeptRemoved = tuple[list[str], int]


def probe_exists(path: Path) -> bool:
    """True if `path` exists; False when it is absent or the probe raised.

    An absent sink is expected before its first append and stays quiet.
    Probe failures must warn without interrupting the caller. `Path.stat()`
    preserves those errors; `Path.exists()` can suppress them.
    """
    try:
        path.stat()
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("could not probe %s for prune: %s", path, error)
        return False
    return True


def prune_timestamp(raw_line: str) -> datetime | None:
    """Parse a JSONL record timestamp, returning None for kept malformed data."""
    try:
        record = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    raw_timestamp = record.get("ts") if isinstance(record, dict) else None
    if not isinstance(raw_timestamp, str):
        return None
    try:
        timestamp = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp


def normalized_jsonl_line(raw_line: str) -> str:
    if raw_line.endswith("\n"):
        return raw_line
    return f"{raw_line}\n"


@dataclass
class PruneScan:
    """Mutable partition of retained and expired JSONL records."""

    kept: list[str] = field(default_factory=list)
    removed: int = 0

    def add(self, raw_line: str, cutoff: datetime) -> None:
        if not raw_line.strip():
            return
        timestamp = prune_timestamp(raw_line)
        if timestamp is not None and timestamp < cutoff:
            self.removed += 1
            return
        self.kept.append(normalized_jsonl_line(raw_line))


def read_kept_records(
    path: Path,
    cutoff: datetime,
) -> _KeptRemoved | None:
    """Split `path`'s lines into (kept, removed_count) by the `cutoff` time.

    A record is removed only when its `ts` parses to a time strictly before
    `cutoff`. Returns None when the read itself raises OSError, which the
    caller turns into a logged no-op.
    """
    scan = PruneScan()
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                scan.add(raw_line, cutoff)
    except OSError as error:
        log.warning("could not read file %s for prune: %s", path, error)
        return None
    return scan.kept, scan.removed
