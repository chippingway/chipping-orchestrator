# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the analytics and trajectory sinks share on the way to disk.

One owner for everything the two JSONL files answer the same way: the envelope
every record satisfies, the encoding and locking discipline one line reaches
disk under, the fail-open answer to a filesystem that refuses the write, and
the channel a refusal is reported on. They sit together because a reader
asking "what shape does a record have and how does it get written" has one
place to look, and because the two sinks cannot drift apart on any of it. A
writer whose own failure boundary has to see a refusal -- the observation
recorder, which warns of a refused append once and writes nothing more --
writes the lines it serialized through the same lock itself
(`write_jsonl_lines`), which raises what the filesystem raises.

*Which* file a record lands in is the caller's, which is why the path arrives
as an argument rather than being read here -- the ``config`` owner beside this
one answers that, and the recording and trajectory packages above it each ask
for their own knob.

Both locks are minted here rather than beside the appends that take them
because a sink is only safe when its append and the retention prune that
rewrites the file under it hold the *same* object. The two stay separate
objects so the two files never serialize against one another.

This owner sits above every write package -- recording, trajectories, and
observations -- and imports nothing from any of them. That is what keeps the
recording graph free of a back edge: an ``agent_exit`` composes the trajectory
write, and the trajectory writers reach the envelope and the line here rather
than back through the recorders that called them.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import typing
from pathlib import Path

# The channel every sink failure is reported under, spelled out rather than
# derived from `__package__` so relocating this owner leaves an operator's log
# filter where it was.
log = logging.getLogger("orchestrator.analytics")

ANALYTICS_FILE_LOCK = threading.Lock()

TRAJECTORY_FILE_LOCK = threading.Lock()


def build_record(
    *,
    repo: str,
    issue: int,
    event: str,
    stage: str | None = None,
    **extras: typing.Any,
) -> dict:
    """Build a single analytics record.

    `ts` is the current UTC time at second precision in ISO-8601 form.
    `stage` and any extra whose value is None are dropped so callers can
    pass optional context unconditionally without polluting records that
    don't carry them.
    """
    rec: dict[str, typing.Any] = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(
            timespec="seconds",
        ),
        "repo": repo,
        "issue": int(issue),
        "event": event,
    }
    if stage is not None:
        rec["stage"] = stage
    for key, field_value in extras.items():
        if field_value is not None:
            rec[key] = field_value
    return rec


def append_jsonl_record(
    path: Path | None,
    lock: threading.Lock,
    record: dict,
) -> None:
    """Append one JSONL line to `path` under `lock`; no-op when `path` is
    None.

    Shared core for the analytics and trajectory sinks: each passes its
    own path and the lock minted above for its file, so the two never
    serialize against one another. OSError is logged and swallowed so a
    misconfigured path (read-only mount, disk full, permission failure)
    cannot stop the per-issue tick from making progress.

    Holds `lock` around the actual filesystem ops so a concurrent prune
    cannot rewrite the file (via `os.replace`) between this append's open
    and write; otherwise the appended record would be written to the
    soon-unlinked inode and silently lost. Scheduler workers fan out
    across threads in the same process, so the race is real on the
    multi-issue path. JSON serialization is done outside the lock to keep
    the critical section short.
    """
    if path is None:
        return
    serialized = json.dumps(record, sort_keys=True)
    try:
        write_jsonl_lines(path, lock, (serialized,))
    except OSError as error:
        log.warning("could not write record to %s: %s", path, error)


def write_jsonl_lines(
    path: Path,
    lock: threading.Lock,
    lines: typing.Sequence[str],
) -> None:
    """Append already serialized JSONL lines to `path` under `lock`, in one write.

    The filesystem half of `append_jsonl_record`, taken under the same lock
    and reached directly by a writer whose own failure boundary has to see
    the `OSError` rather than have it swallowed here: the observation
    recorder warns of a refused append once, and writes nothing more for it
    (`observations/recorder.py`).
    """
    joined = "".join(f"{line}\n" for line in lines)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(joined)
