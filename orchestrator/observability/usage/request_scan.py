# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The bounded pass a request collector reads a run's stdout in, and the bounds it is held to.

Request collection is a second reading of a stream the run parsers have already read, so everything it adds is
bounded: how much of the stdout it scans, how long one line may be, how many events it decodes, how many steps,
branches, and markers it correlates, how many aggregate checkpoints it keeps, and how long a piece of correlation
metadata may be. Each line is decoded by the standard JSON decoder the run parsers read through, with one difference:
a number spelled with a fraction or an exponent is kept as the exact `Decimal` it spells rather than the float nearest
it, so a counter such as `1e-400` or `2.0000000000000000001` is read as the fraction it is, never as the whole number
its float rounds to. The run parsers keep decoding floats. The decoder raises for a line it refuses although it parses
-- a number past the interpreter's digit limit, nesting past its depth -- and the run parsers let that refusal cancel
the run's record as they always have; this scan alone catches it, for the one line it was decoding. A bound that stops
the scan, or a line it cannot decode, is recorded as a gap, so a collection that read less than the whole invocation
says so. A line shaped like a JSON object that does not decode is a malformed frame, a line the decoder refuses
included; any other line that decodes to no event -- banner text, or a value that is no object -- is skipped without
being one, since it could never have been an event.

The bounds are module defaults rather than knobs, read once per collection by `current_limits`, so a caller shrinks
one here and the next collection is held to it.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from orchestrator.observability.usage import request_coverage as coverage

MAX_SCAN_CHARS = 67_108_864  # 64 Mi characters
MAX_LINE_CHARS = 4_194_304  # 4 Mi characters
MAX_EVENTS = 200_000
MAX_TRACKED_STEPS = 20_000
MAX_BRANCHES = 64
MAX_MARKERS = 256
MAX_CHECKPOINTS = 4
MAX_METADATA_CHARS = 128

_OBJECT_START = "{"
_NON_SPACE = re.compile(r"\S")
# What a number literal whose exponent no `Decimal` holds is read as: no number at all, which no reader takes for one.
_UNREADABLE_NUMBER = Decimal("NaN")

PositionedEvent = tuple[int, dict[str, Any]]


@dataclass(frozen=True)
class CollectionLimits:
    """Every bound one collection is held to."""

    scan_chars: int
    line_chars: int
    events: int
    tracked_steps: int
    branches: int
    markers: int
    checkpoints: int
    metadata_chars: int


@dataclass
class Metadata:
    """Correlation metadata read within its bound and its shape, each refusal counted.

    A string too long to keep is dropped and counted, never cut; a value that is no string at all -- a number, a list,
    an object -- is dropped and counted apart, so a malformed field costs its own reading and nothing beside it.
    """

    limit: int
    oversize: int = 0
    malformed: int = 0

    def text(self, raw: Any) -> str | None:
        if raw is None or raw == "":
            return None
        if not isinstance(raw, str):
            self.malformed += 1
            return None
        if len(raw) <= self.limit:
            return raw
        self.oversize += 1
        return None


@dataclass
class EventScan:
    """The events one bounded scan decoded, each with the stdout line it came from, and what the scan left out."""

    limits: CollectionLimits
    events: list[PositionedEvent] = field(default_factory=list)
    scanned_lines: int = 0
    skipped_lines: int = 0
    gaps: Counter[str] = field(default_factory=Counter)

    def read(self, position: int, raw_line: str) -> bool:
        """Decode one line into the scan; False for an event past the most the scan may decode, which it drops."""
        line = raw_line.strip()
        if not line:
            return True
        decoded = self._decoded(line)
        if decoded and len(self.events) >= self.limits.events:
            return False
        self.scanned_lines += 1
        if decoded:
            self.events.append((position, decoded[0]))
        return True

    def _decoded(self, line: str) -> list[dict[str, Any]]:
        """The event one line decodes to, or none, with why a line was skipped counted where it is a gap.

        Only a line shaped like an object could have been an event, so one that decodes to none -- cut short, or
        refused by the decoder for a number past the interpreter's digit limit or nesting past its depth -- is a
        malformed line of this scan, while any other skipped line is not.
        """
        if len(line) > self.limits.line_chars:
            return self._skipped(coverage.OVERSIZE_LINES)
        decoded = decode_event(line)
        if decoded is not None:
            return [decoded]
        return self._skipped(coverage.MALFORMED_LINES if line.startswith(_OBJECT_START) else None)

    def _skipped(self, gap: str | None) -> list[dict[str, Any]]:
        self.skipped_lines += 1
        if gap is not None:
            self.gaps[gap] += 1
        return []


def exact_number(literal: str) -> Decimal:
    """A number literal with a fraction or an exponent, as the `Decimal` it spells.

    One whose exponent is past any `Decimal` -- too large or too small for any count or duration -- is no number this
    collection can read, so it is read as NaN, which every reader of a count or a duration refuses, rather than raising
    out of the line.
    """
    try:
        return Decimal(literal)
    except InvalidOperation:
        return _UNREADABLE_NUMBER


def decode_event(line: str) -> dict[str, Any] | None:
    """The event one line holds, its numbers exact, or None where it holds no JSON object or the decoder refuses it.

    The refusal is caught here rather than in the run parsers' shared decoder, so it costs this scan one line and
    leaves the run parsers' refusal of the stream as it was.
    """
    try:
        decoded = json.loads(line, parse_float=exact_number)
    except (ValueError, RecursionError):
        return None
    return decoded if isinstance(decoded, dict) else None


def current_limits() -> CollectionLimits:
    """Read the bounds in force at the moment one collection starts."""
    return CollectionLimits(
        scan_chars=MAX_SCAN_CHARS,
        line_chars=MAX_LINE_CHARS,
        events=MAX_EVENTS,
        tracked_steps=MAX_TRACKED_STEPS,
        branches=MAX_BRANCHES,
        markers=MAX_MARKERS,
        checkpoints=MAX_CHECKPOINTS,
        metadata_chars=MAX_METADATA_CHARS,
    )


def scan_events(stdout: str, limits: CollectionLimits) -> EventScan:
    """Decode `stdout` within `limits`, numbering each event by the stdout line it was printed on."""
    scan = EventScan(limits)
    # Only output the bound leaves unread cuts the scan short, and trailing whitespace past it is nothing to read. The
    # tail is looked at over as many characters again as the scan reads at most; output going on past that is taken
    # to be unread, so a whitespace tail costs no more than the bound however long it is.
    tail_end = limits.scan_chars * 2
    if len(stdout) > tail_end or _NON_SPACE.search(stdout, limits.scan_chars, tail_end):
        scan.gaps[coverage.SCAN_LIMIT] += 1
    for position, raw_line in enumerate(stdout[:limits.scan_chars].splitlines()):
        if not scan.read(position, raw_line):
            scan.gaps[coverage.SCAN_LIMIT] += 1
            break
    return scan
