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
bzip2, or xz read through that decompressor. The log itself is always read
plain, as its writer appends it, even where its configured name ends as a
compressed copy's would. An event is found behind a rotation for as long as
the copy carrying it stays beside the log; a copy the retention deleted, one
moved to another directory, and a log truncated with no copy kept no longer
carry what they dropped.

A rotation can also run while the copies are being read: the log renamed to
its first copy and created afresh between the listing and the open leaves the
event in a copy the listing never named, and a copy made and the log
truncated behind the listing does the same. So a reading counts only where
the copies held still across it (`_reads`): they are listed again behind the
read, each name to the file it is, and a name added, removed, or put on
another file meanwhile reads everything again over the new listing. A
rotation still moving them after `_READINGS` readings is nobody's answer.

Every copy is read whole, a block at a time, and only the lines naming the
event are parsed, so a log grown since by any amount still answers. A
directory never made holds no copy, and a log never written is no copy
either: nothing was filed there. Anything else that would not read is
nobody's answer (None), never an absence: a copy the process may not read, a
compressed copy whose stream is damaged or still being written, a copy that
stays listed and cannot be opened -- a dangling link -- and a directory that
will not list.
"""
from __future__ import annotations

import bz2
import gzip
import json
import logging
import lzma
import zlib
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO

log = logging.getLogger("orchestrator.github")

# How much of a copy `logged` reads at a time: four mebibytes.
_BLOCK = 4_194_304

_NEWLINE = b"\n"

# How many times `logged` lists and reads the copies before a rotation still
# moving them under every reading holds the answer.
_READINGS = 3

# What opens a copy compressed under each suffix logrotate's compressors leave;
# any other copy is read as written.
_DECOMPRESSING = MappingProxyType({".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open})

# What a copy that would not read raises: the filesystem's refusals -- a
# gzip or bzip2 stream with a damaged header or checksum among them -- a
# compressed stream cut short, a damaged gzip body, and damaged xz data.
_UNREAD = (OSError, EOFError, zlib.error, lzma.LZMAError)

# The log and its copies as one listing saw them: each name to the file it
# is, its device and inode.
_Listing = dict[str, tuple[int, int]]


def logged(event_path: Path, event: str) -> list | None:
    """Every record naming `event` on the audit log and each rotated copy beside it; None where one would not read.

    [] where no copy was ever written. A line that does not parse is passed
    over. A reading the copies moved under is taken again, and None where they
    moved under every one of `_READINGS`.
    """
    named = json.dumps(event).encode()
    for _ in range(_READINGS):
        try:
            records = _reads(event_path, named)
        except _UNREAD as error:
            log.warning("could not read event log %s back: %s", event_path, error)
            return None
        if records is not None:
            return records
    log.warning(
        "event log %s or a copy beside it kept moving, or could not be looked at, over %d readings; no answer",
        event_path, _READINGS,
    )
    return None


def _reads(event_path: Path, named: bytes) -> list | None:
    """The records of every listed copy naming `named`; None where the copies moved between the listing and behind it.

    The log is read ahead of its copies, and a copy is always made before the
    log it was made from is truncated, so wherever the log was read empty
    under a rotation, the copy read behind it carries what the log dropped --
    if the listing named it. So a reading counts only where the listing taken
    behind it names every copy to the very file the listing ahead of it did:
    a name added, removed, or put on another file -- a rename, a create, a
    copy made -- is a rotation the reading may have missed, and so is a copy
    gone by the time it is opened.
    """
    listed = _looked_at(_copies(event_path))
    if listed is None:
        return None
    records = []
    for name in listed:
        try:
            records.extend(_named_in(event_path, name, named))
        except FileNotFoundError:
            return None
    return records if _looked_at(_copies(event_path)) == listed else None


def _copies(event_path: Path) -> list[Path]:
    """The audit log and every rotated copy of it its directory holds; none where that directory was never made.

    The log is listed under its own name whatever the entry is, so a path
    that is no file is read, and refused, as the log it stands for. A rotated
    copy is never a directory.
    """
    prefixes = (f"{event_path.name}.", f"{event_path.name}-")
    try:
        entries = list(event_path.parent.iterdir())
    except FileNotFoundError:
        return []
    named = [entry for entry in entries if entry.name.startswith(prefixes)]
    rotated = [entry for entry in named if not entry.is_dir()]
    return [entry for entry in entries if entry.name == event_path.name] + rotated


def _looked_at(copies: list[Path]) -> _Listing | None:
    """Each of `copies` named to the file it is; None where one went away before it was looked at."""
    try:
        looked = [(copy.name, copy.stat()) for copy in copies]
    except FileNotFoundError:
        return None
    return {name: (seen.st_dev, seen.st_ino) for name, seen in looked}


def _named_in(event_path: Path, name: str, named: bytes) -> list:
    """The records naming `named` in the copy of the log at `event_path` that `name` names.

    The log itself is read as its writer appends it -- plain JSON lines --
    whatever its configured name ends in; a rotated copy is decompressed where
    its suffix says logrotate compressed it. A line that does not parse is
    passed over.
    """
    opens = Path.open
    if name != event_path.name:
        opens = _DECOMPRESSING.get(Path(name).suffix, Path.open)
    with opens(event_path.with_name(name), "rb") as event_stream:
        lines = list(_named_lines(event_stream, named))
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
