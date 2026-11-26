# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The limits an observation's text and record are held to, and how a bounded text says what it left out.

Three limits, each measured where it bites. A field limit caps the
characters one text keeps: the head is kept and the rest is cut, and the
text says so -- how long it was and that it was cut -- rather than reading as
complete. The attachment limit is the reader's (`attachments.ATTACHMENT_CHARS`)
and refuses a line before it is decoded. The record limit caps one JSONL
line as serialized: a record past it keeps every identifier and drops its
texts whole, each still saying how long it was (`records.serialized`).

The numbers come from what a reply carries. A developer report is asked to
stay within 4,000 characters, and the two sentences a published one opens
on ran to 228 characters at the median and 362 at most over a sample of 35;
a description is asked for in one or two sentences within 300, and a
thousand characters keeps every one of those whole with room to spare. An
excerpt is evidence for an operator reading why an attachment was refused,
and its first 500 characters hold the prefix, kind, version, and the start
of the payload. The sink escapes every character past ASCII, at six bytes a
character and twelve for one outside the Basic Multilingual Plane, so a
whole description of non-ASCII text still fits in 8 KiB beside its
identifiers, and the record limit sits there: it binds only on text made
mostly of those widest characters, which no ordinary record is.

Only the telemetry copy is bounded. Nothing here shortens what an agent was
handed or what the workflow publishes.
"""
from __future__ import annotations

from dataclasses import dataclass

# Characters of a task description the record keeps.
DESCRIPTION_CHARS = 1000

# Characters of a refused attachment line a diagnostic keeps.
EXCERPT_CHARS = 500

# Bytes one serialized record may take, its line break aside. The sink
# escapes everything past ASCII, so a line's bytes are its characters.
RECORD_BYTES = 8192

TEXT = "text"

CHARS = "chars"

TRUNCATED = "truncated"


@dataclass(frozen=True)
class BoundedText:
    """One text as a record keeps it: the head it kept, if any, and how long the whole was.

    `kept` is None where the record dropped the text whole; `chars` is the
    length of the redacted text it was cut from.
    """

    kept: str | None
    chars: int

    @property
    def truncated(self) -> bool:
        """Whether the record holds less than the whole text."""
        return self.kept is None or len(self.kept) < self.chars

    def fields(self) -> dict:
        """The text as a record carries it: `text` where any was kept, its length, and whether it was cut."""
        spelled: dict = {CHARS: self.chars, TRUNCATED: self.truncated}
        if self.kept is not None:
            spelled[TEXT] = self.kept
        return spelled


def bounded(text: str, limit: int) -> BoundedText:
    """`text`'s first `limit` characters, beside its whole length."""
    return BoundedText(text[:limit], len(text))


def dropped(spelled: dict) -> dict:
    """A bounded text's fields with the text itself dropped, its length kept."""
    return BoundedText(None, spelled[CHARS]).fields()
