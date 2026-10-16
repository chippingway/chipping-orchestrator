# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Structured GitHub audit event construction, persistence, and the lookup of one already filed.

`filed` answers whether an event a caller may already have filed is on the
stream -- in the client's in-memory tail, or anywhere in the audit log
(`EVENT_LOG_PATH`) and the rotated copies of it beside it (`event_log`) --
for a caller that nothing durable can tell whether it filed it: a process lost
between filing it and the write that says so files it once rather than twice,
however long the retry takes and however often the log was rotated meanwhile
-- a rotation run while the log is read included, which is read again over.
A log the process cannot read, or one a rotation keeps moving under every
reading, is nobody's answer (None), never an absence: the caller holds rather
than files. A log never written, or no log configured
at all, is an absence -- an event a lost process filed with none went nowhere
durable, and the live process's tail is all there is to ask. A copy the
log's retention deleted, or a log truncated with no copy kept, no longer
carries what it dropped.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator import config
from orchestrator.github import event_log as _event_log

log = logging.getLogger("orchestrator.github")


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


def durable() -> bool:
    """Whether every event filed outlives this process, in the audit log `filed` reads back.

    False where no log is configured: `filed` then reads only this process's
    in-memory tail, so an event a process lost before it was recorded
    anywhere else is one no later process can find.
    """
    return config.EVENT_LOG_PATH is not None


def filed(client: Any, event: str, *, issue_number: int, **identity: Any) -> bool | None:
    """Whether `event` for `issue_number`, carrying every member of `identity`, is already on the stream.

    Asked of `client`'s in-memory tail of recorded events and then of the
    whole audit log and its rotated copies (`event_log.logged`), each record
    matched on its event, issue, repository, and every member of `identity`
    (`_matches`). None where the log is configured and it or a copy of it
    would not read, or a rotation kept moving them, which says nothing either
    way.
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
    logged = _event_log.logged(Path(event_path), event)
    if logged is None:
        return None
    return any(_matches(record, wanted) for record in logged)


def _matches(record: Any, wanted: dict) -> bool:
    """Whether `record` is an event record carrying every member of `wanted` exactly."""
    if not isinstance(record, dict):
        return False
    carried = {field: record.get(field) for field in wanted}
    return carried == wanted
