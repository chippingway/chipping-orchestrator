# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The audit event log read back: the file at `EVENT_LOG_PATH` and every rotated copy of it beside it.

The one reader is `events.filed`, which asks whether an event a lost process
may have filed is already on the stream. The log has no rotation of its own --
its operator pairs it with logrotate or an equivalent -- and a rotation
between the event and the retry that asks for it moves the line out of the
file at `EVENT_LOG_PATH`. So the copies are read too: every entry in the log's
own directory named as the log is, or as logrotate names a copy of it -- the
log's name followed by a dot (`events.jsonl.1`, `events.jsonl.2.gz`) or a
dash (`events.jsonl-20261012`, its `dateext`) -- a copy compressed with gzip,
bzip2, or xz read through that decompressor. An event is found behind a
rotation for as long as the copy carrying it stays beside the log; a copy the
retention deleted, one moved to another directory, and a log truncated with no
copy kept no longer carry what they dropped.

Every copy is read whole, a block at a time, and only the lines naming the
event are parsed, so a log grown since by any amount still answers. A
directory never made holds no copy, and a log never written is no copy
either: nothing was filed there. Anything else that would not read is
nobody's answer (None), never an absence: a copy the process may not read, a
compressed copy whose stream is damaged or still being written, a copy a
rotation racing the read renamed or removed between the listing and its open,
and a directory that will not list.
"""
from __future__ import annotations

import bz2
import gzip
import json
import logging
import lzma
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO

log = logging.getLogger("orchestrator.github")

# How much of a copy `logged` reads at a time: four mebibytes.
_BLOCK = 4_194_304

_NEWLINE = b"\n"

# What opens a copy compressed under each suffix logrotate's compressors leave;
# any other copy is read as written.
_DECOMPRESSING = MappingProxyType({".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open})

# What a copy that would not read raises: the filesystem's refusals, a
# compressed stream cut short, and damaged xz data.
_UNREAD = (OSError, EOFError, lzma.LZMAError)


def logged(event_path: Path, event: str) -> list | None:
    """Every record naming `event` on the audit log and each rotated copy beside it; None where one would not read.

    [] where no copy was ever written. A line that does not parse is passed over.
    """
    named = json.dumps(event).encode()
    try:
        lines = [line for copy in _copies(event_path) for line in _named_in(copy, named)]
    except _UNREAD as error:
        log.warning("could not read event log %s back: %s", event_path, error)
        return None
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except ValueError:
            log.debug("skipping an event log line that does not parse")
    return records


def _copies(event_path: Path) -> list[Path]:
    """The audit log and every rotated copy of it its directory holds; none where that directory was never made.

    The log is listed under its own name whatever the entry is, so a path
    that is no file is read, and refused, as the log it stands for. A rotated
    copy is never a directory; an entry gone by the time it is asked is still
    listed, and its open refuses it.
    """
    prefixes = (f"{event_path.name}.", f"{event_path.name}-")
    try:
        entries = list(event_path.parent.iterdir())
    except FileNotFoundError:
        return []
    named = [entry for entry in entries if entry.name.startswith(prefixes)]
    rotated = [entry for entry in named if not entry.is_dir()]
    return [entry for entry in entries if entry.name == event_path.name] + rotated


def _named_in(copy: Path, named: bytes) -> list[bytes]:
    """The lines of `copy` naming `named`, decompressed where its suffix says it was compressed."""
    opens = _DECOMPRESSING.get(copy.suffix, Path.open)
    with opens(copy, "rb") as event_stream:
        return list(_named_lines(event_stream, named))


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
