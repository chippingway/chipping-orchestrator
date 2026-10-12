# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Structured GitHub audit event construction, persistence, and the lookup of one already filed.

`filed` answers whether an event a caller is about to file is already on the
stream -- in the client's in-memory tail, or in the tail of the audit log
(`EVENT_LOG_PATH`) -- so a caller whose own durable record of filing it could
not land before its process was lost files it once rather than twice. Only the
log's last `_FILED_TAIL` bytes are read, since a caller retrying a step follows
its first try within ticks; with no log configured, an event filed by a
process that was lost went nowhere durable, and the tail of the live one is
all there is to ask.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator import config

log = logging.getLogger("orchestrator.github")

# How much of the audit log's end `filed` reads: one mebibyte.
_FILED_TAIL = 1_048_576


def append_event_line(event_path: Path, event_record: dict) -> None:
    """Create the parent directory and append one JSONL event line."""
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as event_stream:
        event_stream.write(f"{json.dumps(event_record, sort_keys=True)}\n")


def write_event_record(event_record: dict) -> None:
    """Append an event when the optional audit path is configured."""
    event_path = config.EVENT_LOG_PATH
    if event_path is None:
        return
    try:
        append_event_line(event_path, event_record)
    except OSError as error:
        log.warning("could not write event log %s: %s", event_path, error)


def build_event_record(
    *,
    repo: str,
    issue_number: int,
    event: str,
    stage: str | None = None,
    **extras: Any,
) -> dict:
    """Build a second-precision UTC audit record without null extras."""
    event_record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo": repo,
        "issue": int(issue_number),
        "event": event,
    }
    if stage is not None:
        event_record["stage"] = stage
    for field_name, field_value in extras.items():
        if field_value is not None:
            event_record[field_name] = field_value
    return event_record


def filed(client: Any, event: str, *, issue_number: int, **identity: Any) -> bool:
    """Whether `event` for `issue_number`, carrying every member of `identity`, is already on the stream.

    Asked of `client`'s in-memory tail of recorded events and of the audit
    log's tail, each record matched on its event, issue, repository, and every
    member of `identity` (`_matches`); a log nobody could read answers for
    none of its lines.
    """
    wanted = {"event": event, "issue": int(issue_number), **identity}
    repo = getattr(client, "_repo_slug", None)
    if repo is not None:
        wanted["repo"] = repo
    if any(_matches(record, wanted) for record in getattr(client, "recorded_events", ())):
        return True
    event_path = config.EVENT_LOG_PATH
    if event_path is None:
        return False
    return any(_matches(record, wanted) for record in _logged_tail(event_path))


def _matches(record: Any, wanted: dict) -> bool:
    """Whether `record` is an event record carrying every member of `wanted` exactly."""
    if not isinstance(record, dict):
        return False
    carried = {field: record.get(field) for field in wanted}
    return carried == wanted


def _logged_tail(event_path: Path) -> list:
    """The records the audit log's last `_FILED_TAIL` bytes parse as, a partial first line dropped."""
    try:
        with Path(event_path).open("rb") as event_stream:
            size = event_stream.seek(0, os.SEEK_END)
            event_stream.seek(max(0, size - _FILED_TAIL))
            tail = event_stream.read().decode("utf-8", "replace").splitlines()
    except OSError as error:
        log.warning("could not read event log %s back: %s", event_path, error)
        return []
    if size > _FILED_TAIL:
        tail = tail[1:]
    records = []
    for line in tail:
        try:
            records.append(json.loads(line))
        except ValueError:
            log.debug("skipping an event log line that does not parse")
    return records
