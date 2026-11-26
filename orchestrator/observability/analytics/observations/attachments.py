# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The analytics attachment an agent reply may carry, and the one reader that types it.

An attachment is ONE line: the prefix, the attachment's kind, its version,
and a JSON object, `ANALYTICS: task-snapshot v1 {"description": "..."}`. One
line is the whole framing on purpose. Every line-level syntax a workflow
reader reacts to -- a report marker, an `ACK:`, a code fence -- has to open a
line, and a JSON string escapes its line breaks, so nothing an agent writes
inside an attachment can open a line another reader would see. The prompt
asks for it above the reply's report outcome, which keeps it out of the
report block and out of the digest the published report is identified by.

The reader is handed a reply already split at its report outcome -- the text
above the first line the report reader treats as a marker, and that line
onwards -- because where the outcome starts is the report reader's question
and not this one's. It reads every line opening on the prefix, anywhere in
either half:

* one in the first half is the attachment, typed when it is exactly the
  current kind and version over the one field it carries, and refused as
  `oversized`, `unsupported`, or `malformed` otherwise;
* two or more there are `duplicate` and none of them is read, since which one
  the agent meant is a guess;
* one in the second half sits inside the report block or past the outcome,
  and is `misplaced` -- never read, since the report it rides is published;
* none at all, beside an outcome, is `missing`: the prompt asked for one. A
  reply with no outcome was asked for nothing, and missing nothing.

Nothing here bounds, redacts, or writes anything: a problem carries the whole
line it was read off, and the recorder redacts it before it bounds it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

PREFIX = "ANALYTICS:"

TASK_SNAPSHOT = "task-snapshot"

TASK_SNAPSHOT_VERSION = 1

DESCRIPTION = "description"

# What the prompt asks a description to stay within. The telemetry copy is
# bounded more generously (`bounds.DESCRIPTION_CHARS`), so a description a
# little past the request is kept whole rather than cut.
DESCRIPTION_REQUEST_CHARS = 300

# The longest attachment line read at all: past it, the line is refused
# before any JSON is decoded. Room for a description well past what the
# telemetry copy keeps, escaped, so an attachment is refused for its size
# only where it is far from what was asked for.
ATTACHMENT_CHARS = 4000

# The line the prompt teaches, spelled from the vocabulary it is read by.
TASK_SNAPSHOT_TEMPLATE = (
    f'{PREFIX} {TASK_SNAPSHOT} v{TASK_SNAPSHOT_VERSION} {{"{DESCRIPTION}": "<one or two sentences>"}}'
)

# Every line opening on the prefix, whatever follows it.
_ATTACHMENT_LINE_RE = re.compile(rf"^[ \t]*{re.escape(PREFIX)}[^\r\n]*", re.MULTILINE)

# The kind and version spelling the one attachment this build reads.
_CURRENT = (TASK_SNAPSHOT, str(TASK_SNAPSHOT_VERSION))

_HEADER_RE = re.compile(
    rf"[ \t]*{re.escape(PREFIX)}[ \t]*(?P<kind>[^ \t]+)[ \t]+v(?P<version>[0-9]+)[ \t]+(?P<payload>.*)",
)


class Problem(StrEnum):
    """Why a reply's attachment is no observation."""

    MISSING = "missing"
    MALFORMED = "malformed"
    UNSUPPORTED = "unsupported"
    MISPLACED = "misplaced"
    DUPLICATE = "duplicate"
    OVERSIZED = "oversized"


@dataclass(frozen=True)
class AttachmentProblem:
    """One problem a reading met, beside the whole line it was read off; None where there is no line."""

    category: Problem
    line: str | None = None


@dataclass(frozen=True)
class SnapshotReading:
    """What one reply's task snapshot attachment reads as.

    `description` is the one attachment's, as decoded and unbounded, or None
    where the reply carries none that reads. `found` counts every attachment
    line in the reply, read or refused.
    """

    description: str | None
    problems: tuple[AttachmentProblem, ...]
    found: int


def read_task_snapshot(preamble: str, outcome: str) -> SnapshotReading:
    """The task snapshot a reply split at its report outcome carries, and every problem with it.

    `preamble` is the reply above its report outcome, the whole reply where
    it has none; `outcome` is the outcome and everything after it, empty
    where there is none.
    """
    placed = [line.group() for line in _ATTACHMENT_LINE_RE.finditer(preamble)]
    misplaced = tuple(
        AttachmentProblem(Problem.MISPLACED, line.group())
        for line in _ATTACHMENT_LINE_RE.finditer(outcome)
    )
    reading = _placed_reading(placed, missing=bool(outcome) and not misplaced)
    return SnapshotReading(
        reading.description, (*reading.problems, *misplaced), reading.found + len(misplaced),
    )


def _placed_reading(placed: list[str], *, missing: bool) -> SnapshotReading:
    """What the attachment lines above the outcome read as; `missing` is whether none there is a problem."""
    if len(placed) > 1:
        duplicate = AttachmentProblem(Problem.DUPLICATE, "\n".join(placed))
        return SnapshotReading(None, (duplicate,), len(placed))
    if not placed:
        return SnapshotReading(None, (AttachmentProblem(Problem.MISSING),) if missing else (), 0)
    description = _description(placed[0])
    if isinstance(description, Problem):
        return SnapshotReading(None, (AttachmentProblem(description, placed[0]),), 1)
    return SnapshotReading(description, (), 1)


def _description(line: str) -> str | Problem:
    """The description one attachment line carries, or the problem that refuses it."""
    if len(line) > ATTACHMENT_CHARS:
        return Problem.OVERSIZED
    header = _HEADER_RE.fullmatch(line)
    if header is None:
        return Problem.MALFORMED
    if header.group("kind", "version") != _CURRENT:
        return Problem.UNSUPPORTED
    return _payload_description(header.group("payload"))


def _payload_description(payload: str) -> str | Problem:
    """The description a version-1 payload carries: an object of that one non-blank string, or malformed."""
    try:
        decoded = json.loads(payload)
    except (ValueError, RecursionError):
        return Problem.MALFORMED
    if not isinstance(decoded, dict) or set(decoded) != {DESCRIPTION}:
        return Problem.MALFORMED
    description = decoded[DESCRIPTION]
    if not isinstance(description, str) or not description.strip():
        return Problem.MALFORMED
    return description
