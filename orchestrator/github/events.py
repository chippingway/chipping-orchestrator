# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Structured GitHub audit event construction, persistence, and the lookup of one already filed.

`filed` answers whether an event a caller may already have filed is on the
stream -- in the client's in-memory tail, or anywhere in the audit log
(`EVENT_LOG_PATH`) -- for a caller whose durable record says it was about to
file it and nothing says whether it did: a process lost between the two files
it once rather than twice, however long the retry takes. The whole log is
read, a block at a time and only the lines naming the event parsed, so a log
grown since by any amount still answers. A log the process cannot read is
nobody's answer (None), never an absence: the caller holds rather than files.
A log never written, or no log configured at all, is an absence -- an event a
lost process filed with none went nowhere durable, and the live process's
tail is all there is to ask. A log rotated or truncated by its operator
between the two no longer carries what it dropped.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, BinaryIO

from orchestrator import config

log = logging.getLogger("orchestrator.github")

# How much of the audit log `filed` reads at a time: four mebibytes.
_BLOCK = 4_194_304

_NEWLINE = b"\n"


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


def filed(client: Any, event: str, *, issue_number: int, **identity: Any) -> bool | None:
    """Whether `event` for `issue_number`, carrying every member of `identity`, is already on the stream.

    Asked of `client`'s in-memory tail of recorded events and then of the
    whole audit log, each record matched on its event, issue, repository, and
    every member of `identity` (`_matches`). None where the log is configured
    and would not read, which says nothing either way.
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
    logged = _logged(Path(event_path), event)
    if logged is None:
        return None
    return any(_matches(record, wanted) for record in logged)


def _matches(record: Any, wanted: dict) -> bool:
    """Whether `record` is an event record carrying every member of `wanted` exactly."""
    if not isinstance(record, dict):
        return False
    carried = {field: record.get(field) for field in wanted}
    return carried == wanted


def _logged(event_path: Path, event: str) -> list | None:
    """Every record of the audit log whose line names `event`; [] for a log never written, None for one unread."""
    named = json.dumps(event).encode()
    try:
        with event_path.open("rb") as event_stream:
            lines = list(_named_lines(event_stream, named))
    except FileNotFoundError:
        return []
    except OSError as error:
        log.warning("could not read event log %s back: %s", event_path, error)
        return None
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except ValueError:
            log.debug("skipping an event log line that does not parse")
    return records


def _named_lines(event_stream: BinaryIO, named: bytes) -> Iterator[bytes]:
    """The lines of `event_stream` naming `named`, read a block at a time.

    Each block is cut at its last line end and the rest carried into the one
    behind it, so a line is only ever read whole, and only a block naming
    `named` is split into lines at all.
    """
    carried = b""
    for block in iter(partial(event_stream.read, _BLOCK), b""):
        whole = carried + block
        cut = whole.rfind(_NEWLINE) + 1
        carried = whole[cut:]
        lines = whole[:cut]
        if named in lines:
            yield from (line for line in lines.split(_NEWLINE) if named in line)
    if named in carried:
        yield carried
