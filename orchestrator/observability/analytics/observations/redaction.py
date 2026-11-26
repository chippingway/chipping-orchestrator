# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The telemetry copy of a reply's text, with every credential in it masked before anything is cut or written.

The credential redactor (`config.credentials.redact_secrets`) replaces each
credential's literal value in a text it is handed whole. A description is
handed whole: it is one decoded JSON string, so the redactor runs over it as
it is, a credential the JSON escaped decoded back into its value.

An excerpt of a refused line is not handed whole. It is one line of a reply,
so a credential whose line break the agent wrote raw reaches it as a fragment
the literal no longer matches; and a credential inside a JSON string reaches
it escaped -- its line breaks, quotes, and characters past ASCII spelled as
escape sequences -- which is not its value either. So the whole reply is
searched first, for every value the redactor masks, both as written and with
its JSON string escapes decoded, and each place one sits is kept as a span of
the original text. An excerpt of any stretch of the reply then shows every
part of a span it covers as the redactor's own mask, and the redactor runs
over what is left as well.

Which values are credentials is the redactor's own policy, read off its owner
inside the call: the process environment's secret-shaped values
(`is_secret_environment_value`) and the configured GitHub tokens long enough
to mask. Nothing here decides what a secret is.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from types import ModuleType

    from orchestrator.observability.analytics.observations.attachments import SnapshotReading

# What the redactor replaces a credential with, and what an excerpt shows in its place.
MASK = "***"

# One JSON string escape: a surrogate pair first, so it decodes to the one
# character it spells, then any other unicode escape, then the short ones.
_ESCAPE_RE = re.compile(
    r"\\u[dD][89abAB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}"
    r"|\\u[0-9a-fA-F]{4}"
    r'|\\["\\/bfnrt]',
)

# Where something sits in a text: `(start, end)`, end exclusive.
_Span = tuple[int, int]

# The credential redactor's shape: a text in, the text with every credential masked out.
_Redactor = Callable[[str], str]


class Telemetry(NamedTuple):
    """A reading's texts as a record may carry them: the description redacted, and each problem's excerpt masked.

    `excerpts` follows the reading's problems one for one, None for a
    problem with no line.
    """

    description: str | None
    excerpts: tuple[str | None, ...]


def sanitized(message: str, reading: SnapshotReading) -> Telemetry:
    """The texts `reading` of `message` yields, with every credential the process holds masked."""
    from orchestrator import config

    redact = config.credentials.redact_secrets
    masker = _Masker.over(message, _credential_values(config))
    excerpts = tuple(masker.excerpt(problem.spans, redact) for problem in reading.problems)
    return Telemetry(masker.redacted(reading.description, redact), excerpts)


def _credential_values(config: ModuleType) -> tuple[str, ...]:
    """Every value the credential redactor masks, read off its owner as it would read them."""
    shortest = config.credentials._REDACT_MIN_VALUE_LEN
    found = [token for token in config.GITHUB_TOKENS if len(token) >= shortest]
    for key, secret in os.environ.items():
        if config.credentials.is_secret_environment_value(key, secret):
            found.append(secret)
    return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class _Decoded:
    """A text beside its JSON string escapes decoded, and the span of the text each decoded character came from."""

    raw: str
    text: str
    sources: tuple[_Span, ...]

    @classmethod
    def of(cls, raw: str) -> _Decoded:
        pieces = cls._pieces(raw)
        text = "".join(piece[0] for piece in pieces)
        return cls(raw, text, tuple(piece[1] for piece in pieces))

    def spans_of(self, secret: str) -> list[_Span]:
        """Every span of the raw text `secret` sits in, as written or behind escapes."""
        pattern = re.compile(re.escape(secret))
        spans = [found.span() for found in pattern.finditer(self.raw)]
        spans.extend(map(self._source, pattern.finditer(self.text)))
        return spans

    def _source(self, found: re.Match[str]) -> _Span:
        first = self.sources[found.start()]
        last = self.sources[found.end() - 1]
        return (first[0], last[1])

    @classmethod
    def _pieces(cls, raw: str) -> list[tuple[str, _Span]]:
        """`raw` one decoded character at a time, each beside the span it was decoded from."""
        pieces: list[tuple[str, _Span]] = []
        cursor = 0
        for escape in _ESCAPE_RE.finditer(raw):
            pieces.extend(cls._literal(raw, cursor, escape.start()))
            pieces.append(cls._unescaped(escape))
            cursor = escape.end()
        pieces.extend(cls._literal(raw, cursor, len(raw)))
        return pieces

    @classmethod
    def _literal(cls, raw: str, start: int, end: int) -> list[tuple[str, _Span]]:
        literal = []
        for offset in range(start, end):
            literal.append((raw[offset], (offset, offset + 1)))
        return literal

    @classmethod
    def _unescaped(cls, escape: re.Match[str]) -> tuple[str, _Span]:
        escaped = escape.group()
        return json.loads(f'"{escaped}"'), escape.span()


@dataclass(frozen=True)
class _Masker:
    """A reply, and the merged spans every credential in it sits in, in order."""

    message: str
    spans: tuple[_Span, ...]

    @classmethod
    def over(cls, message: str, secrets: tuple[str, ...]) -> _Masker:
        decoded = _Decoded.of(message)
        found = [span for secret in secrets for span in decoded.spans_of(secret)]
        return cls(message, cls._merged(found))

    def redacted(self, text: str | None, redact: _Redactor) -> str | None:
        """`text` through the redactor, where there is any."""
        return None if text is None else redact(text)

    def excerpt(self, lines: tuple[_Span, ...], redact: _Redactor) -> str | None:
        """The reply's `lines`, one per line, every credential in them masked; None for no lines."""
        if not lines:
            return None
        shown = [self._line(*line) for line in lines]
        return redact("\n".join(shown))

    def _line(self, start: int, end: int) -> str:
        pieces = []
        cursor = start
        for span_start, span_end in self._clipped(start, end):
            pieces.append(self.message[cursor:span_start])
            pieces.append(MASK)
            cursor = span_end
        pieces.append(self.message[cursor:end])
        return "".join(pieces)

    def _clipped(self, start: int, end: int) -> list[_Span]:
        """Each credential span overlapping `start` to `end`, cut to it."""
        clipped = []
        for span_start, span_end in self.spans:
            if span_start < end and span_end > start:
                clipped.append((max(span_start, start), min(span_end, end)))
        return clipped

    @classmethod
    def _merged(cls, spans: list[_Span]) -> tuple[_Span, ...]:
        """`spans` in order, every two that touch or overlap made one."""
        merged: list[list[int]] = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1]:
                last = merged[-1]
                last[1] = max(last[1], end)
            else:
                merged.append([start, end])
        return tuple((span[0], span[1]) for span in merged)
