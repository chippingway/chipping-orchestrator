# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The telemetry copy of a reply's text, with every credential in it masked before anything is cut or written.

A credential is searched for as every spelling JSON strings nested in a text
can give it, not as one literal (`_Spelling`). Each of its characters is read
as written, or as an escape at any level up to `_ESCAPE_DEPTH`, whose own
characters are read one level less deep (`_Pieces`); every escape is tried
wherever it may start, whatever came before it. Every place each prefix of
the credential's spelling can reach is kept, from every place it can start,
and every piece on some complete spelling is then traced back. So every spelling is found whole, from each
start to each end, overlapping ones included, and the work is bounded: past a
fixed amount per character of the text searched, the whole text counts as the
credential. A credential's line breaks are each read as any line break -- a
carriage return, a line feed, or the two in turn, written or escaped -- since
a reply's line breaks need not be the credential's: an agent may write it with
CRLF, and a backend may read the reply back with universal newlines, as Codex's
last-message file is. Only the search reads them alike: the reply itself is
never normalized, so the reader's offsets and categories stand. The credential
redactor (`config.credentials.redact_secrets`)
replaces one value at a time, so where one credential sits inside another,
replacing the first would leave the other's ends behind; here every match is
found first, and each place one sits is kept as a span, touching spans made
one, each widened over every escape either end of it sits inside (`_closed`).

A text holding JSON of its own -- a description quoting a config, say --
holds a credential escaped once more, which the nested reading finds however
the escapes around it align. The reply is also read for an escape nested
deeper than `_ESCAPE_DEPTH` levels, tried wherever it may start, as the
search tries its own (`_Pieces.escaped_past`), so no backslash before one
changes whether it is seen. A credential could continue from a shown text
into such an escape, wherever in the reply it is, so a reply holding one
shows no text: each keeps its length alone, and its record its category. So
does a reply whose reading for one runs past the work bound. A reply with no
text to show -- no description and no refused line -- is not searched at all.

A shown text -- the refused lines of an excerpt joined, or a description
decoded from where the reply writes its JSON string
(`SnapshotReading.written_at`) -- is searched once more as assembled, since
joining refused lines can bring a credential's parts together. What the reply
search found in it and what this search finds are masked together, so neither
mask can hide part of a credential from the other, and only then does the
credential redactor run over it. The whole text is then searched in the sink's
own encoding, which can spell a credential out of characters it escapes: one
that does keeps its length alone. Every credential is masked as written before
anything normalizes it -- a value holding a character the analytics database
refuses matches only there -- and only then is the text bounded, made
storable as it is cut (`bounds.bounded`), so no cut leaves part of a
credential behind.

Decoding and serializing can still make a credential of what was none: a
description spelled out in characters the sink escapes, a value whose own
spelling includes the quotes a JSON string is written between. So every
line the recorder writes, a fallback diagnostic's included, is searched last,
whole, the same way (`Credentials.admits`), and a record whose line holds a
credential -- or is escaped deeper than any reply this search admits could
leave it -- keeps no text (`records.serialized`).

Which values are credentials is the redactor's own selection, read off its
owner inside the call (`config.credentials.secret_values`): the process
environment's secret-shaped values and the configured GitHub tokens long
enough to mask -- the very values the redactor masks by. Nothing here decides
what a secret is.
"""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple

from orchestrator.observability.analytics.observations import bounds

if TYPE_CHECKING:
    from orchestrator.observability.analytics.observations.attachments import SnapshotReading

# What the redactor replaces a credential with, and what an excerpt shows in its place.
MASK = "***"

# One JSON string escape: a surrogate pair first, so it decodes to the one
# character it spells, then any other unicode escape, then the short ones.
_ESCAPE = (
    r"\\u[dD][89abAB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}"
    r"|\\u[0-9a-fA-F]{4}"
    r'|\\["\\/bfnrt]'
)

_ESCAPE_RE = re.compile(_ESCAPE)

# One piece of a JSON string as decoding takes it: an escape, or failing one,
# one character as it is.
_PIECE_RE = re.compile(rf"{_ESCAPE}|[\s\S]")

# A backslash, where every JSON string escape starts.
_BACKSLASH = "\\"
_BACKSLASH_RE = re.compile(re.escape(_BACKSLASH))

# A line break as universal newlines read one, and the line feed a credential's
# spelling writes each of its own as, read back as any of them.
_LINE_BREAK_RE = re.compile(r"\r\n?|\n")
_LINE_FEED = "\n"
_CARRIAGE_RETURN = "\r"

# The characters JSON spells with a short escape, and the letter after its backslash.
_SHORT_ESCAPES = MappingProxyType({
    '"': '"',
    "\\": "\\",
    "/": "/",
    "\b": "b",
    "\f": "f",
    "\n": "n",
    "\r": "r",
    "\t": "t",
})

# What may follow an escape's backslash: a short escape's letter, or the `u`
# opening a unicode escape, which counts without its digits.
_ESCAPE_OPENERS = "".join((*_SHORT_ESCAPES.values(), "u"))

# Each hex digit of a unicode escape, as the characters it may be written as.
_HEX_CASES = MappingProxyType({digit: digit + digit.upper() for digit in "0123456789abcdef"})

# One escape, as the characters each of its places may be.
_Escape = tuple[str, ...]

# Where no spelling ends.
_NOWHERE: frozenset[int] = frozenset()

# How many places finding one credential in a text may keep, for each
# character of the text: past them, the whole text counts as the credential.
_WORK_PER_CHARACTER = 64

# How many levels of JSON string escapes a credential is searched for through.
# Ordinary text runs out of escapes within a few -- a run of backslashes halves
# at each -- so a reply holding an escape nested deeper shows no text.
_ESCAPE_DEPTH = 8

# How far before a position an escape covering it can start: a surrogate pair,
# the longest escape, is twelve characters.
_WIDEST_ESCAPE = 11

# The line a record is written as holds each text one JSON string deeper than
# the reply did, and a text ending on a backslash runs into the quote that
# closes it, so the line is searched two levels further down.
_LINE_DEPTH = _ESCAPE_DEPTH + 2

# Where something sits in a text: `(start, end)`, end exclusive.
_Span = tuple[int, int]

# Spans of one text, in order.
_Spans = tuple[_Span, ...]

# A span past the end of any text, closing a walk over a text's credential spans.
_PAST_EVERY_LINE: _Span = (sys.maxsize, sys.maxsize)

# A shown text, beside the spans of it a credential found in the reply covers.
_Shown = tuple[str, list[_Span]]

# The credential redactor's shape: a text in, the text with every credential masked out.
_Redactor = Callable[[str], str]

# A text as a record keeps it, or None for no text.
_Kept = bounds.BoundedText | None


class Telemetry(NamedTuple):
    """A reading's texts as a record keeps them: masked, redacted, and only then bounded.

    `excerpts` follows the reading's problems one for one, None for a
    problem with no line. A text the search could not see to the bottom of
    keeps its length alone.
    """

    description: _Kept
    excerpts: tuple[_Kept, ...]


@dataclass(frozen=True)
class Credentials:
    """Every credential the process holds, and the redactor run over what is left once each is masked."""

    spellings: tuple[_Spelling, ...]
    redact: _Redactor

    @classmethod
    def held(cls) -> Credentials:
        """The credentials the redactor masks right now, read off its owner."""
        from orchestrator import config

        # The selection lists a value once for each replacement pass masking
        # it, and one search finds every spelling of it however often it is
        # held. Each line break is written as a line feed, which the search
        # reads back as any line break.
        selected = config.credentials.secret_values()
        secrets = dict.fromkeys(_LINE_BREAK_RE.sub(_LINE_FEED, secret) for secret in selected)
        return cls(tuple(map(_Spelling, secrets)), config.credentials.redact_secrets)

    def sanitized(self, message: str, reading: SnapshotReading) -> Telemetry:
        """The texts `reading` of `message` yields, every credential masked, bounded and storable."""
        shown = tuple(problem.spans for problem in reading.problems)
        if reading.written_at is None and not any(shown):
            return Telemetry(None, (None,) * len(shown))
        reply = _Masker.over(message, self)
        description = self._kept(reply, reply.described(reading), bounds.DESCRIPTION_CHARS)
        return Telemetry(description, self._excerpts(reply, shown))

    def admits(self, line: str) -> bool:
        """Whether `line`, as the sink writes it, holds no credential in any spelling at any level searched."""
        if _Pieces(line, _LINE_DEPTH).escaped_past():
            return False
        return not any(spelling.spans(line, _LINE_DEPTH) for spelling in self.spellings)

    def _excerpts(self, reply: _Masker, shown: tuple[_Spans, ...]) -> tuple[_Kept, ...]:
        """Each problem's lines of the reply as a record keeps them."""
        texts = map(reply.excerpt, shown)
        return tuple(self._kept(reply, text, bounds.EXCERPT_CHARS) for text in texts)

    def _kept(self, reply: _Masker, shown: _Shown | None, limit: int) -> _Kept:
        """A shown text as a record keeps it: searched once more as assembled, masked and redacted, then bounded.

        What the reply search found in the text and what this search finds in
        it unmasked are masked together, and the redactor, which replaces one
        value at a time, runs only once every match is masked. Serializing can
        still spell a credential out of characters the sink escapes, and a cut
        would leave only the part of it before the cut for the line's own
        check, so the whole text is searched in the sink's encoding before it
        is cut. Where any of these searches cannot see to the bottom, or the
        encoding holds a credential, the text keeps its length alone.
        """
        if shown is None:
            return None
        text, covered = shown
        whole = _Masker.over(text, self)
        if reply.unresolved or whole.unresolved:
            return bounds.BoundedText(None, len(text))
        redacted = self.redact(whole.masked(covered))
        if not self.admits(json.dumps(bounds.storable(redacted))):
            return bounds.BoundedText(None, len(redacted))
        return bounds.bounded(redacted, limit)


@dataclass(frozen=True)
class _Spelling:
    """One credential, found in a text however JSON strings nested in it spell each of its characters.

    Every place each prefix of the credential's spelling can reach is kept,
    from every place it can start (`_forward`), and every piece on some
    complete spelling is traced back from where spellings end (`_backward`),
    so every spelling is found whole, from each start to each end. The text's
    pieces are read by `_Pieces`, whose work bound, spent by the places kept
    and the readings made, makes the whole text count as the credential once
    it runs out. `secret` writes each of its line breaks as a line feed, which
    a text may spell as any line break (`_ends`).
    """

    secret: str

    def spans(self, text: str, depth: int = _ESCAPE_DEPTH) -> list[_Span]:
        """Every piece of `text` on some spelling nested at most `depth` deep, or the whole text past the bound."""
        pieces = _Pieces(text, depth)
        reached = self._forward(pieces)
        if pieces.exhausted:
            return [(0, len(text))] if text else []
        return self._backward(pieces, reached) if reached else []

    def _forward(self, pieces: _Pieces) -> list[set[int]]:
        """Where each prefix of the spelling can end, from every place it can start.

        Empty where no spelling can be completed: the walk stops at the first
        prefix nothing reaches, or once the work bound runs out.
        """
        frontier = self._starts(pieces.text)
        reached = [frontier]
        pieces.spent += len(frontier)
        for character in self.secret:
            if not frontier or pieces.exhausted:
                return []
            frontier = self._step(pieces, frontier, character)
            pieces.spent += len(frontier)
            reached.append(frontier)
        return reached

    def _backward(self, pieces: _Pieces, reached: list[set[int]]) -> list[_Span]:
        """Every piece on some complete spelling, traced back from the places spellings end."""
        spans: list[_Span] = []
        ending = reached[-1]
        for index in reversed(range(len(self.secret))):
            starts = reached[index]
            ending, found = self._step_back(pieces, self.secret[index], starts, ending)
            spans.extend(found)
        return spans

    def _starts(self, text: str) -> set[int]:
        """Every place a spelling of the first character may start: the character itself, or any backslash.

        A line feed starts on either character a line break may open with.
        """
        first = self.secret[0]
        opening = _CARRIAGE_RETURN + _LINE_FEED if first == _LINE_FEED else first
        starting = re.compile(f"[{re.escape(opening + _BACKSLASH)}]")
        return {found.start() for found in starting.finditer(text)}

    @classmethod
    def _step(cls, pieces: _Pieces, frontier: set[int], character: str) -> set[int]:
        """Where a spelling of `character` ends, from each place of `frontier`."""
        return {after for at in frontier for after in cls._ends(pieces, at, character)}

    @classmethod
    def _step_back(
        cls, pieces: _Pieces, character: str, starts: set[int], ending: set[int],
    ) -> tuple[set[int], list[_Span]]:
        """The spellings of `character` from any of `starts` to any of `ending`, and the places they start."""
        found = []
        for at in starts:
            ends = cls._ends(pieces, at, character)
            found.extend((at, after) for after in ends if after in ending)
        return ({piece[0] for piece in found}, found)

    @classmethod
    def _ends(cls, pieces: _Pieces, at: int, character: str) -> frozenset[int]:
        """Where a spelling of `character` from `at` can end, a line feed spelled as any line break.

        A line break is a carriage return, a line feed, or the two in turn,
        each written or escaped, as universal newlines would read them.
        """
        if character != _LINE_FEED:
            return pieces.after(at, character)
        returns = pieces.after(at, _CARRIAGE_RETURN)
        pairs = [pieces.after(returned, _LINE_FEED) for returned in returns]
        return returns.union(pieces.after(at, _LINE_FEED), *pairs)


@dataclass
class _Pieces:
    """A text read as the characters JSON strings nested in it spell, remembering every reading made.

    A credential's own character is spelled as it is, or as one of its escapes
    at any level up to the text's depth (`after`): a backslash and a letter, or
    a backslash, a `u`, and four hex digits of either case per UTF-16 unit.
    An escape at a level is made of characters spelled exactly one level less
    deep (`_part`): each as it is, or escaped deeper still -- a backslash
    always escaped, since a JSON string holds none bare. Every escape is tried
    wherever it may start, whatever came before it, so how the text's own
    escapes align decides nothing. Each reading is made once, and counted in
    `spent`, which the work bound holds to `_WORK_PER_CHARACTER` for each
    character of the text.
    """

    text: str
    depth: int
    spent: int = 0
    _read: dict[tuple[int, str, int], frozenset[int]] = field(default_factory=dict)

    @property
    def exhausted(self) -> bool:
        """Whether the work bound has run out, so no reading can be trusted to be whole."""
        return self.spent > _WORK_PER_CHARACTER * (len(self.text) + 1)

    def escaped_past(self) -> bool:
        """Whether an escape nested deeper than the text is read starts anywhere in it, or the work bound ran out.

        Such an escape opens on a backslash spelled exactly as deep as the
        text is read, followed by what may follow an escape's backslash, each
        read as an escape's own characters are and tried wherever it may
        start, as every spelling is. A credential could continue there, past
        where any spelling of it is looked for.
        """
        opening = (_BACKSLASH, _ESCAPE_OPENERS)
        for backslash in _BACKSLASH_RE.finditer(self.text):
            if self._chain(backslash.start(), opening, self.depth):
                return True
        return self.exhausted

    def after(self, at: int, character: str) -> frozenset[int]:
        """Where a spelling of a credential's `character` from `at` can end: as written, or escaped at any level."""
        if self._cannot_start(at, character):
            return _NOWHERE
        known = self._read.get((at, character, -1))
        if known is not None:
            return known
        self.spent += 1
        ends: set[int] = set()
        if self.text[at] == character:
            ends.add(at + 1)
        escapes = self._escapes(character)
        for depth in range(self.depth):
            for escape in escapes:
                ends.update(self._chain(at, escape, depth))
        self._read[at, character, -1] = frozenset(ends)
        return self._read[at, character, -1]

    def _part(self, at: int, character: str, depth: int) -> frozenset[int]:
        """Where `character`, one character of an escape, spelled exactly `depth` levels deep from `at` can end."""
        if self._cannot_start(at, character):
            return _NOWHERE
        known = self._read.get((at, character, depth))
        if known is not None:
            return known
        self.spent += 1
        ends: set[int] = set()
        if not depth and self.text[at] == character:
            ends.add(at + 1)
        elif depth and character != _BACKSLASH:
            ends.update(self._part(at, character, depth - 1))
        for escape in self._escapes(character) if depth else ():
            ends.update(self._chain(at, escape, depth - 1))
        self._read[at, character, depth] = frozenset(ends)
        return self._read[at, character, depth]

    def _chain(self, at: int, escape: tuple[str, ...], depth: int) -> set[int]:
        """Where `escape` spelled `depth` deep from `at` can end, each of its places any character it lists."""
        frontier = {at}
        for options in escape:
            reached: set[int] = set()
            for start in frontier:
                for option in options:
                    reached.update(self._part(start, option, depth))
            frontier = reached
        return frontier

    def _cannot_start(self, at: int, character: str) -> bool:
        """Whether no spelling of `character` can start at `at`: only it, or an escape's backslash, can."""
        if at >= len(self.text) or self.exhausted:
            return True
        return self.text[at] != character and self.text[at] != _BACKSLASH

    @classmethod
    def _escapes(cls, character: str) -> tuple[_Escape, ...]:
        """Every escape of `character`, as the characters each of its places may be."""
        units = re.findall("....", character.encode("utf-16-be", "surrogatepass").hex())
        unicode: list[str] = []
        for unit in units:
            unicode.extend((_BACKSLASH, "u", *map(_HEX_CASES.get, unit)))
        short = _SHORT_ESCAPES.get(character)
        tail = () if short is None else ((_BACKSLASH, short),)
        return (tuple(unicode), *tail)


def _closed(text: str, spans: _Spans) -> list[_Span]:
    """The ordered `spans`, each widened over every escape of `text` either end of it sits inside.

    One spelling of a credential can end partway through an escape another
    spelling of it takes whole -- a backslash written as two, before a letter
    a unicode escape spells -- and the search finds only one of them, however
    the escapes there align. One walk serves every span: a place a span would
    look at again has already widened the span before it over any escape
    there, so the two are merged however this one would have grown.
    """
    closed = []
    at = 0
    for start, end in spans:
        at = max(start - _WIDEST_ESCAPE, at)
        while at < end:
            found = _ESCAPE_RE.match(text, at)
            if found is not None and found.end() > start:
                start = min(start, at)
                end = max(end, found.end())
            at += 1
        closed.append((start, end))
    return closed


@dataclass(frozen=True)
class _Decoded:
    """A JSON string's contents decoded, beside the span of the raw text each decoded character came from."""

    text: str
    sources: tuple[_Span, ...]

    @classmethod
    def of(cls, raw: str) -> _Decoded:
        """`raw` decoded as a JSON reader decodes a string's contents."""
        pieces = list(map(cls._piece, _PIECE_RE.finditer(raw)))
        text = "".join(piece[0] for piece in pieces)
        return cls(text, tuple(piece[1] for piece in pieces))

    def covered(self, spans: list[_Span]) -> list[_Span]:
        """The spans of the decoded text decoded from inside `spans` of the raw text."""
        return [(index, index + 1) for index in sorted(self._hidden(spans))]

    def _hidden(self, spans: list[_Span]) -> set[int]:
        """The decoded characters whose source overlaps any of `spans`."""
        hidden: set[int] = set()
        for start, end in spans:
            for index, source in enumerate(self.sources):
                if source[0] < end and source[1] > start:
                    hidden.add(index)
        return hidden

    @classmethod
    def _piece(cls, found: re.Match[str]) -> tuple[str, _Span]:
        """The character one piece of a JSON string decodes to -- an escape's, or the one it is -- and its span."""
        piece = found.group()
        if len(piece) == 1:
            return (piece, found.span())
        return (json.loads(f'"{piece}"'), found.span())


@dataclass(frozen=True)
class _Masker:
    """A text, and the merged spans every credential in it sits in, in order.

    `unresolved` says whether the text holds an escape nested deeper than any
    credential was looked for, wherever it starts (`_Pieces.escaped_past`).
    """

    message: str
    spans: tuple[_Span, ...]
    unresolved: bool

    @classmethod
    def over(cls, message: str, credentials: Credentials) -> _Masker:
        found = [span for spelling in credentials.spellings for span in spelling.spans(message)]
        closed = _closed(message, cls._merged(found))
        return cls(message, cls._merged(closed), _Pieces(message, _ESCAPE_DEPTH).escaped_past())

    def described(self, reading: SnapshotReading) -> _Shown | None:
        """The description `reading` decoded from where the reply writes it, beside the spans decoded from a credential.

        Raises where that spelling does not decode to the description the
        reader read, rather than masking a text other than the one recorded.
        """
        if reading.written_at is None:
            return None
        start, end = reading.written_at
        decoded = _Decoded.of(self.message[start:end])
        if decoded.text != reading.description:
            raise ValueError("the description does not decode from where the reply writes it")
        overlapping = self._overlapping((reading.written_at,))
        return (decoded.text, decoded.covered(overlapping))

    def excerpt(self, lines: _Spans) -> _Shown | None:
        """The reply's ordered `lines` joined by line breaks, beside the spans of them a credential covers."""
        if not lines:
            return None
        texts = []
        for line in lines:
            texts.append(self.message[line[0]:line[1]])
        return ("\n".join(texts), self._overlapping(lines))

    def masked(self, covered: list[_Span]) -> str:
        """The text, every credential span of its own and every one of `covered` shown as the mask."""
        pieces = []
        cursor = 0
        for span in self._merged([*self.spans, *covered]):
            pieces.append(self.message[cursor:span[0]])
            pieces.append(MASK)
            cursor = span[1]
        pieces.append(self.message[cursor:])
        return "".join(pieces)

    def _overlapping(self, lines: _Spans) -> list[_Span]:
        """The credential spans overlapping the ordered `lines`, cut to them and counted along the lines joined.

        One walk over both in order: each span is handed out once, and looked
        at again only for each further line it reaches into.
        """
        spans = iter((*self.spans, _PAST_EVERY_LINE))
        current = next(spans)
        covered: list[_Span] = []
        offset = 0
        for line in lines:
            while current[1] <= line[0]:
                current = next(spans)
            while current[0] < line[1]:
                covered.append(self._cut(current, line, offset))
                if current[1] > line[1]:
                    break
                current = next(spans)
            offset += line[1] - line[0] + 1
        return covered

    @classmethod
    def _cut(cls, span: _Span, line: _Span, offset: int) -> _Span:
        """`span` cut to `line`, counted from `offset`, where the line starts among the lines joined."""
        start, end = line
        first = max(span[0], start) - start + offset
        last = min(span[1], end) - start + offset
        return (first, last)

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
