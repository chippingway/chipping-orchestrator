# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The telemetry copy of a reply's text, with every credential in it masked before anything is cut or written.

Every credential is masked in the text as the agent wrote it, before anything
normalizes it: a value holding a character the analytics database refuses --
a byte the environment carried as a lone surrogate -- matches only there, so
only the masked text is made storable, as it is bounded (`bounds.bounded`).
The credential redactor (`config.credentials.redact_secrets`) replaces each
credential's literal value in a text it is handed whole. A description is handed whole: it is one decoded
JSON string, so the redactor runs over it as it is, a credential the JSON
escaped decoded back into its value. Decoding can also do the opposite -- a
credential whose value itself spells an escape, a backslash and an `n`, decodes
into another character -- and the sink would spell it back exactly as it
serializes the record, so every text is searched once more in that JSON
spelling, and what a credential covers there is masked too.

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
    """The texts `reading` of `message` yields, with every credential the process holds masked, not yet storable."""
    from orchestrator import config

    masker = _Masker.over(message, _credential_values(config))
    redact = config.credentials.redact_secrets
    excerpts = (masker.excerpt(problem.spans) for problem in reading.problems)
    cleared = tuple(masker.cleared(excerpt, redact) for excerpt in excerpts)
    return Telemetry(masker.cleared(reading.description, redact), cleared)


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

    def masked(self, spans: tuple[_Span, ...]) -> str:
        """The decoded text, each run of characters decoded from inside `spans` of the raw text shown as the mask."""
        hidden = self._hidden(spans)
        pieces: list[str] = []
        for index, character in enumerate(self.text):
            if index not in hidden:
                pieces.append(character)
            elif index - 1 not in hidden:
                pieces.append(MASK)
        return "".join(pieces)

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

    def _hidden(self, spans: tuple[_Span, ...]) -> set[int]:
        """The decoded characters whose source overlaps any of `spans`."""
        hidden: set[int] = set()
        for start, end in spans:
            for index, source in enumerate(self.sources):
                if source[0] < end and source[1] > start:
                    hidden.add(index)
        return hidden

    @classmethod
    def _pieces(cls, raw: str) -> list[tuple[str, _Span]]:
        """`raw` one decoded character at a time, each beside the span it was decoded from."""
        pieces: list[tuple[str, _Span]] = []
        cursor = 0
        for escape in _ESCAPE_RE.finditer(raw):
            pieces.extend(_literal(raw, cursor, escape.start()))
            pieces.append(_unescaped(escape))
            cursor = escape.end()
        pieces.extend(_literal(raw, cursor, len(raw)))
        return pieces


@dataclass(frozen=True)
class _Masker:
    """A reply, the merged spans every credential in it sits in, in order, and the credentials themselves."""

    message: str
    spans: tuple[_Span, ...]
    secrets: tuple[str, ...]

    @classmethod
    def over(cls, message: str, secrets: tuple[str, ...]) -> _Masker:
        decoded = _Decoded.of(message)
        found = [span for secret in secrets for span in decoded.spans_of(secret)]
        return cls(message, cls._merged(found), secrets)

    def cleared(self, text: str | None, redact: _Redactor) -> str | None:
        """`text` redacted as written, and masked in the JSON spelling the sink writes it in; None for none.

        A credential's value may itself spell an escape -- a backslash and an
        `n`, written by an agent inside a JSON string -- which decoding turned
        into another character, so the redactor no longer sees it in the text,
        and serializing would spell it back exactly. Each character escaped
        into that spelling of a credential is masked in the text.
        """
        if text is None:
            return None
        redacted = redact(text)
        written = _Decoded.of(json.dumps(redacted)[1:-1])
        found = [span for secret in self.secrets for span in written.spans_of(secret)]
        return written.masked(self._merged(found)) if found else redacted

    def excerpt(self, lines: tuple[_Span, ...]) -> str | None:
        """The reply's `lines`, one per line, every credential in them masked; None for no lines."""
        if not lines:
            return None
        shown = [self._line(*line) for line in lines]
        return "\n".join(shown)

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


def _literal(raw: str, start: int, end: int) -> list[tuple[str, _Span]]:
    """`raw[start:end]` one character at a time, each beside the span it sits in."""
    literal = []
    for offset in range(start, end):
        literal.append((raw[offset], (offset, offset + 1)))
    return literal


def _unescaped(escape: re.Match[str]) -> tuple[str, _Span]:
    """The character one JSON string escape decodes to, beside the span it was written in."""
    escaped = escape.group()
    return json.loads(f'"{escaped}"'), escape.span()
