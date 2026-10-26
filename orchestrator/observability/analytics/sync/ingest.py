# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One JSONL file streamed into one open connection, a batch at a time.

Two dedup filters stand between a line and the wire, and they answer different
questions. A startup scan pulls every persisted `content_hash` into a Python
set, so a record the database already holds is skipped before it costs a
round-trip, and a hash queued earlier in this same file joins that set as the
loop runs -- which is what makes two identical lines cost one insert rather
than two. `ON CONFLICT (content_hash) DO NOTHING` in the statement stays the
authoritative backstop underneath both, because a concurrent writer can land a
row after the scan has already answered.

What reaches the wire is batched: one `executemany` per full buffer collapses N
round-trips into one pipeline, and the driver's per-batch rowcount is what
splits it back into inserted and duplicate. A malformed line is counted and
logged rather than raised, and a blank one is neither, so a single bad line in
a rotated file never aborts the replay of the thousands after it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.observability.analytics.sync.models import IngestContext, SyncCounters
from orchestrator.observability.analytics.sync.rows import (
    RowProvenance,
    prepare_record,
    row_values,
)

BATCH_SIZE = 500

log = logging.getLogger("orchestrator.analytics.sync")


def emit_progress(counters: SyncCounters, start: float) -> None:
    """Log one progress record: cumulative counts + elapsed wall-clock.

    Fired after every batched `executemany` flush so an operator can watch a
    multi-thousand-record replay advance.
    """
    log.info(
        "analytics_sync: progress lines=%d inserted=%d duplicate=%d malformed=%d elapsed=%.3fs",
        counters.total_lines,
        counters.inserted,
        counters.skipped_duplicate,
        counters.skipped_malformed,
        time.monotonic() - start,
    )


def flush_batch(
    cur: Any,
    insert_sql: str,
    batch: list[tuple],
    counters: SyncCounters,
    start: float,
) -> None:
    """Flush the accumulated row batch in one `executemany`, then clear it.

    psycopg's rowcount on `executemany` is the total rows inserted across the
    batch, so the duplicate count is `len(batch) - rowcount`. A driver that
    reports -1 falls back to counting the whole batch as inserted -- the
    database is the authority and `inserted` stays a lower bound only if a
    driver bug strips the count entirely. A no-op on an empty batch, so the
    caller can invoke it unconditionally at EOF.
    """
    if not batch:
        return
    cur.executemany(insert_sql, batch)
    rowcount = getattr(cur, "rowcount", len(batch))
    if rowcount < 0:
        rowcount = len(batch)
    counters.inserted += rowcount
    counters.skipped_duplicate += len(batch) - rowcount
    batch.clear()
    emit_progress(counters, start)


def note_malformed_line(
    counters: SyncCounters,
    line_number: int,
    log_path: Path,
    reason: str,
) -> None:
    """Count and log one skipped malformed line without aborting the sync.

    `reason` names why the line was rejected (`not JSON`, `JSON not an
    object`, `missing/invalid required keys`). The line number is logged so
    the operator can clean it up out-of-band; the sync never rewrites the
    JSONL file.
    """
    counters.skipped_malformed += 1
    counters.malformed_lines.append(line_number)
    log.warning(
        "analytics_sync: skipping line %d (%s) in %s",
        line_number,
        reason,
        log_path,
    )


def existing_hashes(cur: Any) -> set[str]:
    """Read the dedup keys already stored, in one scan of the unique index.

    Every row this sync inserts carries the hash of the line it came from,
    so the set is exactly the keys a new record's insert could collide with.
    """
    cur.execute("SELECT content_hash FROM analytics_events")
    return {row[0] for row in cur}


@dataclass
class RecordIngester:
    """Classify, deduplicate, and batch records for one open cursor."""

    cur: Any
    context: IngestContext
    existing_hashes: set[str]
    batch_size: int
    batch: list[tuple] = field(default_factory=list)

    def add(self, line_number: int, raw_line: str) -> None:
        self.context.counters.total_lines += 1
        prepared, reason = prepare_record(raw_line)
        if prepared is None:
            if reason is not None:
                note_malformed_line(
                    self.context.counters,
                    line_number,
                    self.context.log_path,
                    reason,
                )
            return
        if prepared.content_hash in self.existing_hashes:
            self.context.counters.skipped_duplicate += 1
            return
        provenance = RowProvenance(
            source_path=self.context.source_path,
            source_line=line_number,
            content_hash=prepared.content_hash,
        )
        self.batch.append(
            row_values(
                prepared.columns,
                prepared.extras,
                provenance,
                self.context.json_adapter,
            )
        )
        self.existing_hashes.add(prepared.content_hash)
        if len(self.batch) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        flush_batch(
            self.cur,
            self.context.insert_sql,
            self.batch,
            self.context.counters,
            self.context.start,
        )


def stream_records(ingester: RecordIngester) -> None:
    with ingester.context.log_path.open("r", encoding="utf-8") as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            ingester.add(line_number, raw_line)


def ingest_records(
    conn: Any,
    context: IngestContext,
) -> None:
    """Stream `log_path` into `conn` under one cursor, batching valid rows.

    All tallies land on the context's counters; the trailing partial batch is
    flushed at EOF and the caller commits and closes the connection.
    """
    with conn.cursor() as cur:
        ingester = RecordIngester(
            cur=cur,
            context=context,
            existing_hashes=existing_hashes(cur),
            # Read off the module as the pass starts rather than frozen into a
            # default, so a caller that pins a smaller buffer is driving the
            # loop that actually runs.
            batch_size=BATCH_SIZE,
        )
        stream_records(ingester)
        ingester.flush()
