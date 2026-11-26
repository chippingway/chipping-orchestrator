# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The analytics attachment an agent reply may carry, and the one reader that types it.

An attachment is ONE line: the prefix, the attachment's kind, its version,
and a JSON object, `ANALYTICS: task-snapshot v1 {"description": "..."}`. One
line is the whole framing on purpose. Every line-level syntax a workflow
reader reacts to -- a report marker, an `ACK:`, a code fence -- has to open a
line, and a JSON string escapes its line breaks, so nothing an agent writes
inside an attachment can open a line another reader would see. The prompt
asks for it in every finished reply, above the report outcome where the reply
ends on one, which keeps it out of the report block and out of the digest the
published report is identified by.

The reader is handed the reply exactly as the agent wrote it, beside where
its report outcome begins -- the report reader's own question, not this
one's -- and reads every line opening on the prefix anywhere in it. A reply
carries exactly one:

* none at all is `missing`, whatever else the reply says;
* two or more are a `duplicate`, wherever they sit, and none of them is read,
  since which one the agent meant is a guess;
* the one line, at or past the outcome, sits inside the report block or after
  the outcome and is `misplaced` -- never read, since the report it rides is
  published;
* the one line above the outcome is the attachment, typed when it is exactly
  the current kind and version over a JSON object of one non-blank
  `description` and nothing else -- a key written twice included, which the
  decoder would otherwise settle silently -- and refused as `oversized`,
  `unsupported`, or `malformed` otherwise.

The framing is validated on the original text alone: nothing is redacted,
repaired, or normalized before it is read, so a credential's line break
written raw inside the JSON leaves the line as malformed as it was written.
Nothing here bounds, redacts, or writes anything either: a problem names where
its lines sit in the reply, and the redaction owner masks what it excerpts.

`without_attachments` is the other half of the framing: the workflow reads a
reply with its attachment lines taken out above the outcome, so a reply that
says nothing else reads as saying nothing, and no park or notice quotes it.
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

# The same lines with the break that ends each, as the workflow's reply leaves them out.
_TAKEN_OUT_RE = re.compile(rf"^[ \t]*{re.escape(PREFIX)}[^\r\n]*(?:\r?\n)?", re.MULTILINE)

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
    """One problem a reading met, and the `(start, end)` span in the reply of each line it was read off.

    No span is a problem with no line to show: a missing attachment.
    """

    category: Problem
    spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SnapshotReading:
    """What one reply's task snapshot attachment reads as.

    `description` is the one attachment's, as decoded and unbounded, or None
    where the reply carries none that reads; it never carries one beside a
    problem. `found` counts every attachment line in the reply, read or
    refused.
    """

    description: str | None
    problems: tuple[AttachmentProblem, ...]
    found: int


def read_task_snapshot(message: str, outcome_at: int) -> SnapshotReading:
    """The task snapshot `message` carries, or the one problem that leaves it none.

    `outcome_at` is where the reply's report outcome begins: the length of
    the message where it has none.
    """
    lines = tuple(_ATTACHMENT_LINE_RE.finditer(message))
    if not lines:
        return SnapshotReading(None, (AttachmentProblem(Problem.MISSING),), 0)
    spans = tuple(line.span() for line in lines)
    if len(lines) > 1:
        return SnapshotReading(None, (AttachmentProblem(Problem.DUPLICATE, spans),), len(lines))
    if lines[0].start() >= outcome_at:
        return SnapshotReading(None, (AttachmentProblem(Problem.MISPLACED, spans),), 1)
    description = _description(lines[0].group())
    if isinstance(description, Problem):
        return SnapshotReading(None, (AttachmentProblem(description, spans),), 1)
    return SnapshotReading(description, (), 1)


def without_attachments(text: str) -> str:
    """`text` with every line opening on the prefix taken out, the break that ends each line with it."""
    return _TAKEN_OUT_RE.sub("", text)


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
    """The description a version-1 payload carries: an object of that one non-blank string, or malformed.

    Every object decodes to the pairs it was written with, so a key written
    twice is two pairs rather than the last of them.
    """
    try:
        decoded = json.loads(payload, object_pairs_hook=tuple)
    except (ValueError, RecursionError):
        return Problem.MALFORMED
    if not isinstance(decoded, tuple) or len(decoded) != 1:
        return Problem.MALFORMED
    key, description = decoded[0]
    if key != DESCRIPTION or not isinstance(description, str):
        return Problem.MALFORMED
    return description if description.strip() else Problem.MALFORMED
