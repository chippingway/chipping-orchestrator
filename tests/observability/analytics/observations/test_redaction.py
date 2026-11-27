# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A secret in a reply is masked in the telemetry copy, never in the reply the attachment is read from.

The redactor replaces each secret's literal value, so every spelling of the
secret has to be found whole first: across the reply's raw lines, inside a
description or a refused line its JSON escaped -- canonically or not, behind
any escape, or once more inside JSON a description quotes -- overlapping
another, before a field limit would cut it into halves the redactor no longer
recognizes, and before a character the database refuses is replaced inside
it; and the line the sink writes is searched last, whole. The
attachment itself is read off the reply as written, so a secret's raw line
break inside the JSON leaves the line malformed rather than repaired by the
mask.
"""
from __future__ import annotations

import json
import os
import re
import time
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.agents.backends.codex import read_last_message
from orchestrator.config import credentials
from orchestrator.observability.analytics.observations import attachments, bounds, redaction
from tests.observability.analytics.observations import observation_test_support as _support

# A secret the process environment holds, spanning two lines, and the parts
# none of which may reach the sink.
_SECRET = "first-line-of-the-secret\nsecond-line-of-the-secret"

# A second one, spelling a backslash sequence of its own, which decoding the
# reply's escapes would turn into another character.
_BACKSLASHED_LINE = r"other-secret-first\tline"
_BACKSLASHED = f"{_BACKSLASHED_LINE}\nother-secret-second"

# A third, whose value spells a JSON escape: written inside a JSON string it
# decodes to another character, and serializing spells it back exactly.
_ESCAPE_SPELLING = r"spelled-token-first\nspelled-token-second"

# A fourth, holding a byte the environment carries as a lone surrogate, which
# the database refuses: masked as written, before the copy is made storable.
_SURROGATE_ESCAPED = "carried-token-first\udcffcarried-token-last"

_FRAGMENTS = ("first-line", "second-line", "of-the-secret", "other-secret", "spelled-token", "carried-token")

# Room a case leaves beside a secret, under a field limit.
_ROOM = 40

# Padding that puts a secret where each field limit would cut it.
_NEAR_THE_DESCRIPTION_CUT = "d" * (bounds.DESCRIPTION_CHARS - _ROOM)
_NEAR_THE_EXCERPT_CUT = "d" * (bounds.EXCERPT_CHARS - _ROOM)

# A snapshot's opening, its payload's close, and a payload that never closes.
_OPENING = 'ANALYTICS: task-snapshot v1 {"description": "'
_CLOSING = '"}'
_UNCLOSED = "ANALYTICS: task-snapshot v1 {"
_UNQUOTED = 'ANALYTICS: task-snapshot v1 {"description": '

# The secret as JSON spells it, and as an agent may spell it instead.
_ESCAPED = json.dumps(_SECRET)
_ESCAPED_BODY = _ESCAPED[1:-1]
_UNICODE_ESCAPED = _SECRET.replace("\n", r"\u000a").replace("-", r"\u002d")

# JSON a description quotes, escaping the secret once more than the attachment does.
_QUOTED = json.dumps({"password": _SECRET})

# Runs of backslashes a refused line ends on: halving at each level, one is
# escaped exactly as deep as a reply is searched, the other one level past it.
_BACKSLASH = "\\"
_AT_DEPTH = 256
_PAST_DEPTH = 512

# A credential holding the quotes its value is written between once the sink
# serializes the description it decodes to.
_QUOTED_VALUE = r'"mock-secret-first\nmock-secret-second"'

# One credential each of many refused lines holds.
_TOKEN = "mock-duplicate-token"
_REPEATS = 64
_DUPLICATED = f"ANALYTICS: {_TOKEN}\n" * _REPEATS
_TOKEN_SPANS = tuple(found.span() for found in re.finditer(_TOKEN, _DUPLICATED))
_EXCERPTED = "\n".join(("ANALYTICS: ***",) * _REPEATS)

_SNAPSHOT = "task_snapshot"
_MALFORMED = "malformed"

# Each reply's preamble, and what its attachment reads as.
_CASES = (
    (_support.snapshot_line(f"Uses {_SECRET} to log in."), _SNAPSHOT),
    (f"{_OPENING}{_UNICODE_ESCAPED}{_CLOSING}", _SNAPSHOT),
    (_support.snapshot_line(f"{_NEAR_THE_DESCRIPTION_CUT}{_SECRET}"), _SNAPSHOT),
    (f"{_OPENING}{_SECRET}{_CLOSING}", _MALFORMED),
    (f"{_UNCLOSED}{_NEAR_THE_EXCERPT_CUT}{_SECRET}", _MALFORMED),
    (f"{_UNQUOTED}{_ESCAPED}", _MALFORMED),
    (f"{_UNCLOSED}{_NEAR_THE_EXCERPT_CUT}{_UNICODE_ESCAPED}", _MALFORMED),
    (f"{_UNCLOSED}{_BACKSLASHED}", _MALFORMED),
    (f"{_OPENING}Keep {_ESCAPE_SPELLING} out.{_CLOSING}", _SNAPSHOT),
    (f"{_UNCLOSED}{_ESCAPE_SPELLING}", _MALFORMED),
    (_support.snapshot_line(f"Uses {_SURROGATE_ESCAPED} to log in."), _SNAPSHOT),
    (f"{_UNCLOSED}{_SURROGATE_ESCAPED}", _MALFORMED),
    (_support.snapshot_line(f"Example config: {_QUOTED}"), _SNAPSHOT),
    (f"{_UNCLOSED}{json.dumps(_QUOTED)}", _MALFORMED),
    (f"{_UNCLOSED}{_BACKSLASH}{_ESCAPED_BODY}", _MALFORMED),
)

# One credential inside another, listed first, so replacing one value at a
# time would leave the outer one's ends behind.
_INNER = "mock-inner-token"
_OUTER = f"mock-outer-start\n{_INNER}\nmock-outer-end"

# A credential whose value is the escape a valid description decodes.
_ESCAPE_VALUED = r"mock-token-start\u000amock-token-end"

# A multiline credential written escaped, its two occurrences sharing a line.
_FRAGMENT = "mock-line-fragment"
_REPEATED = f"{_FRAGMENT}\n{_FRAGMENT}"
_OVERLAPPING = json.dumps(f"{_REPEATED}\n{_FRAGMENT}")

_MASKED_USE = "Uses ***."

# A credential across two lines, assembled only once two refused lines are
# joined: its first character escaped, its first line ending the first refused
# line exactly at the excerpt limit, so a cut before searching would leave it.
_JOINED_SECOND = "ANALYTICS: demo-second-line"
_JOINED_TOKEN = f"demo-first-line\n{_JOINED_SECOND}"
_JOINED_FIRST = f"{_BACKSLASH}u0064emo-first-line"
_JOINED_HEAD = _UNCLOSED.ljust(bounds.EXCERPT_CHARS - len(_JOINED_FIRST), ".")

# Two credentials across the same two refused lines, the shorter one a prefix
# of the longer and listed first, so a redactor run before every match was
# found would leave the longer one's end behind.
_JOINED_LINE = "demo-first-line"
_JOINED_SHORT = f"{_JOINED_LINE}\nANALYTICS:"
_JOINED_LONG = f"{_JOINED_LINE}\n{_JOINED_SECOND}"

# A credential two of whose spellings start at one place, the longer taking a
# backslash as written and the next letter as a unicode escape.
_SHARED_TOKEN = f"demo-first\ndemo-second{_BACKSLASH}u"
_SHARED_SPELLED = f"demo-first{_BACKSLASH}ndemo-second{_BACKSLASH}{_BACKSLASH}u0075"

# A credential holding a backslash, a `u`, and the digits a unicode escape of
# that `u` spells: written with the backslash doubled, then the escape and the
# digits again, its two spellings start together and end four characters apart.
_APART_TOKEN = f"fixture-first\nfixture-last{_BACKSLASH}u0075"
_APART_SPELLED = f"fixture-first{_BACKSLASH}nfixture-last{_BACKSLASH}{_BACKSLASH}u00750075"

# A credential JSON-escaped twice inside a description, behind a backslash
# written as it is, which shifts how a decoder reading from the start pairs the
# backslashes before it: found wherever its nested spelling starts.
_NESTED_TOKEN = f"{_BACKSLASH}t-review-head\nreview-tail"
_NESTED_ONCE = json.dumps(_NESTED_TOKEN)[1:-1]
_NESTED_TWICE = json.dumps(_NESTED_ONCE)[1:-1]
_NESTED_DESCRIPTION = f"Copied sample: {_BACKSLASH}{_NESTED_TWICE}"

# A backslash's unicode escape, as a credential may hold it written out.
_ESCAPED_BACKSLASH = f"{_BACKSLASH}u005c"

# A credential holding two such ambiguous places, every spelling of it to be
# found from its start to its furthest end.
_TWO_RUNS_TOKEN = f"fixture-first\n{_ESCAPED_BACKSLASH}{_BACKSLASH}u0075"
_TWO_RUNS_SPELLED = (
    f"fixture-first{_BACKSLASH}n{_ESCAPED_BACKSLASH}{_ESCAPED_BACKSLASH}{_BACKSLASH}u00750075"
)

# A credential the reply holds in one refused line, inside a longer one
# assembled only when that line is joined with another: both searched for
# before either is masked.
_PART = "fixture-first-part"
_SECOND_PART = "ANALYTICS: fixture-second-part"
_PARTS = f"{_PART}\n{_SECOND_PART}"

# Each overlap's environment and reply, and the one text its record keeps.
_OVERLAPS = (
    (
        MappingProxyType({"ANALYTICS_TEST_INNER_TOKEN": _INNER, "ANALYTICS_TEST_OUTER_TOKEN": _OUTER}),
        _support.snapshot_line(f"Uses {_OUTER}."),
        _support.DESCRIPTION_FIELD,
        _MASKED_USE,
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_ESCAPE_TOKEN": _ESCAPE_VALUED}),
        f"{_OPENING}Uses {_ESCAPE_VALUED}.{_CLOSING}",
        _support.DESCRIPTION_FIELD,
        _MASKED_USE,
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_REPEATED_TOKEN": _REPEATED}),
        f"{_UNQUOTED}{_OVERLAPPING}",
        _support.EXCERPT_FIELD,
        f'{_UNQUOTED}"***"',
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_JOINED_TOKEN": _JOINED_TOKEN}),
        f"{_JOINED_HEAD}{_JOINED_FIRST}\nIntervening prose.\n{_JOINED_SECOND}",
        _support.EXCERPT_FIELD,
        f"{_JOINED_HEAD}***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_SHORT_TOKEN": _JOINED_SHORT, "ANALYTICS_TEST_LONG_TOKEN": _JOINED_LONG}),
        f"ANALYTICS: {_JOINED_LINE}\nUnrelated prose.\n{_JOINED_SECOND}",
        _support.EXCERPT_FIELD,
        "ANALYTICS: ***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_SHARED_TOKEN": _SHARED_TOKEN}),
        f"{_UNCLOSED}{_SHARED_SPELLED}",
        _support.EXCERPT_FIELD,
        f"{_UNCLOSED}***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_TWO_RUNS_TOKEN": _TWO_RUNS_TOKEN}),
        f"{_UNCLOSED}{_TWO_RUNS_SPELLED}",
        _support.EXCERPT_FIELD,
        f"{_UNCLOSED}***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_PART_TOKEN": _PART, "ANALYTICS_TEST_PARTS_TOKEN": _PARTS}),
        f"ANALYTICS: {_PART}\nIntervening prose.\n{_SECOND_PART}",
        _support.EXCERPT_FIELD,
        "ANALYTICS: ***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_NESTED_TOKEN": _NESTED_TOKEN}),
        _support.snapshot_line(_NESTED_DESCRIPTION),
        _support.DESCRIPTION_FIELD,
        "Copied sample: ***",
    ),
    (
        MappingProxyType({"ANALYTICS_TEST_APART_TOKEN": _APART_TOKEN}),
        f"{_UNCLOSED}{_APART_SPELLED}",
        _support.EXCERPT_FIELD,
        f"{_UNCLOSED}***",
    ),
)

# Replies at and past the escape depth, and what each one is recorded as: its
# category or event, and the text kept, None for none. Past the depth a
# credential could continue where the search never looked, so no text is
# shown, wherever in the reply the escapes are. A backslash written as it is
# before a line feed's escape shifts how a decoder reading from the start
# pairs the run: the escape is judged as deep as it is wherever it starts,
# at the depth and one level past it.
_AT_DEPTH_LINE = _UNCLOSED + _BACKSLASH * _AT_DEPTH
_PAST_DEPTH_RUN = _BACKSLASH * _PAST_DEPTH
_ESCAPING_AT_DEPTH = _BACKSLASH * (_AT_DEPTH // 2)
_ESCAPING_PAST_DEPTH = _BACKSLASH * _AT_DEPTH
_SHIFTED_AT_DEPTH = f"{_UNCLOSED}{_BACKSLASH}{_ESCAPING_AT_DEPTH}n"
_SHIFTED_PAST_DEPTH = f"{_UNCLOSED}{_BACKSLASH}{_ESCAPING_PAST_DEPTH}n"
_DEPTHS = (
    (_AT_DEPTH_LINE, (_MALFORMED, _AT_DEPTH_LINE)),
    (_UNCLOSED + _PAST_DEPTH_RUN, (_MALFORMED, None)),
    (f"{_support.snapshot_line()}\n{_PAST_DEPTH_RUN}", (_SNAPSHOT, None)),
    (_SHIFTED_AT_DEPTH, (_MALFORMED, _SHIFTED_AT_DEPTH)),
    (_SHIFTED_PAST_DEPTH, (_MALFORMED, None)),
)

# A multiline credential whose last line break is escaped past the depth, and
# the refused line holding its first line, which alone the search could see.
_DEEP_TOKEN = "demo-first\ndemo-middle\ndemo-last"
_DEEP_SHOWN = f"{_UNCLOSED}demo-first"
_DEEP_REPLY = f"{_DEEP_SHOWN}\ndemo-middle{_PAST_DEPTH_RUN}ndemo-last"

# A credential holding a run of backslashes, and a refused line holding its
# escaped spelling twice: once spoiled at its end, once whole.
_RUN = 26
_RUN_OF_BACKSLASHES = _BACKSLASH * _RUN
_RUN_TOKEN = f"mock-run-token{_RUN_OF_BACKSLASHES}-end"
_RUN_ESCAPED = _RUN_OF_BACKSLASHES * 2
_RUN_SPELLED = f"mock-run-token{_RUN_ESCAPED}"
_RUN_LINE = f"{_UNCLOSED}{_RUN_SPELLED}-x {_RUN_SPELLED}-end"
_RUN_SECONDS = 1

# A credential written out as many backslash escapes, and a refused line
# holding twice as many, spoiled at its end: every way to split the runs is
# tracked at once rather than tried in turn, and nothing matches.
_ESCAPED_RUNS = 24
_RUNS_WRITTEN = _ESCAPED_BACKSLASH * _ESCAPED_RUNS
_RUNS_SPOILED = _RUNS_WRITTEN * 2
_RUNS_TOKEN = f"fixture-first\n{_RUNS_WRITTEN}fixture-last"
_RUNS_LINE = f"{_UNCLOSED}fixture-first{_BACKSLASH}n{_RUNS_SPOILED}other-tail"

# A credential of backslashes long enough that the ways to spell it along a
# long run pass the work bound: the whole text counts as the credential.
_PAST_BUDGET = 160
_HEAVY_TOKEN = _BACKSLASH * _PAST_BUDGET

# A credential holding a unicode escape written out, which the sink spells a
# description's accented letter as: a description ending its first line on the
# description limit, so a cut there would leave the line's check only the part
# of the credential before it.
_ACCENTED = "\N{LATIN SMALL LETTER E WITH ACUTE}"
_SINK_FIRST = f"example-{_BACKSLASH}u00e9-first"
_SINK_TOKEN = f"{_SINK_FIRST}\nexample-second"
_SINK_HEAD = f"example-{_ACCENTED}-first".rjust(bounds.DESCRIPTION_CHARS, ".")
_SINK_DESCRIPTION = f"{_SINK_HEAD}\nexample-second"
_SINK_LINE = f"{_OPENING}{_SINK_HEAD}{_BACKSLASH}nexample-second{_CLOSING}"

# A credential far longer than a short reply, its first letter in the reply.
_LONG_TAIL = 16384
_LONG_XS = "x" * _LONG_TAIL
_LONG_TOKEN = f"s{_LONG_XS}"
_SHORT_REPLY = "small reply"

# A multiline value only the credential owner's selection names, and its JSON
# spelling, which the existing redactor's literal search would not see.
_SELECTED = "selected-first\nselected-second"
_SELECTED_SPELLED = json.dumps(_SELECTED)[1:-1]

# A multiline credential with a line feed, the same with a CRLF, and a reply
# whose every line break is a CRLF, one of them breaking a refused line.
_LF_TOKEN = "fixture-head\nfixture-tail"
_CRLF_TOKEN = "fixture-head\r\nfixture-tail"
_LINES_KEY = "ANALYTICS_TEST_LINES_TOKEN"
_CRLF_REPLY = _support.reply(f"{_OPENING}{_LF_TOKEN}{_CLOSING}").replace("\n", "\r\n")

# The credential escaped inside a description with the other line break, and
# raw inside a refused line with a carriage return alone.
_ESCAPED_CRLF = _support.reply(_support.snapshot_line(f"Uses {_CRLF_TOKEN}."))
_ESCAPED_LF = _support.reply(_support.snapshot_line(f"Uses {_LF_TOKEN}."))
_LONE_RETURN = _support.reply(f"{_UNCLOSED}fixture-head\rfixture-tail")

# The refused line of the CRLF reply, its credential masked.
_CRLF_SHOWN = f"{_OPENING}***"

# Replies holding a credential with other line breaks than its own, and what
# each records: its category or event, and the text kept.
_LINE_BREAKS = (
    (_LF_TOKEN, _CRLF_REPLY, (_MALFORMED, _CRLF_SHOWN)),
    (_LF_TOKEN, _ESCAPED_CRLF, (_SNAPSHOT, _MASKED_USE)),
    (_CRLF_TOKEN, _ESCAPED_LF, (_SNAPSHOT, _MASKED_USE)),
    (_LF_TOKEN, _LONE_RETURN, (_MALFORMED, f"{_UNCLOSED}***")),
)

# The forward step a counted stand-in answers through.
_STEP = redaction._Spelling._step

# A credential of backslashes alone, matched at every place of a long run.
_BACKSLASH_TOKEN = _BACKSLASH * 8
_AT_DEPTH_RUN = _BACKSLASH * _AT_DEPTH
_LONG_RUN = f"ANALYTICS: {_AT_DEPTH_RUN}"

# The escape pattern itself, which a counted stand-in answers through.
_ESCAPES = redaction._ESCAPE_RE

# Refused lines matched against a credential of their own within the work
# bound, and the excerpt each is recorded with.
_BOUNDED = (
    (MappingProxyType({"ANALYTICS_TEST_RUN_TOKEN": _RUN_TOKEN}), _RUN_LINE, f"{_UNCLOSED}{_RUN_SPELLED}-x ***"),
    (MappingProxyType({"ANALYTICS_TEST_RUNS_TOKEN": _RUNS_TOKEN}), _RUNS_LINE, _RUNS_LINE),
    (MappingProxyType({"ANALYTICS_TEST_HEAVY_TOKEN": _HEAVY_TOKEN}), f"{_UNCLOSED}{_AT_DEPTH_RUN}", "***"),
)

# The process environment the cases run under: four credentials.
_CREDENTIALS = MappingProxyType({
    "ANALYTICS_TEST_TOKEN": _SECRET,
    "ANALYTICS_TEST_KEY": _BACKSLASHED,
    "ANALYTICS_TEST_PASSWORD": _ESCAPE_SPELLING,
    "ANALYTICS_TEST_SECRET": _SURROGATE_ESCAPED,
})


class RedactionTest(_support.SinkCase):
    """No fragment of a multiline secret reaches the sink."""

    def setUp(self) -> None:
        super().setUp()
        secret_set = patch.dict(os.environ, _CREDENTIALS)
        secret_set.start()
        self.addCleanup(secret_set.stop)

    def test_no_secret_fragment_reaches_the_sink(self) -> None:
        # Escaped inside the JSON, raw across the reply's lines, and where the
        # field limit would cut it in two, in a snapshot and in a refused
        # line's excerpt; a raw line break inside the JSON is no snapshot.
        for preamble, reading in _CASES:
            with self.subTest(preamble=preamble[-_ROOM:]):
                self.path.unlink(missing_ok=True)
                recorded = self.record(_support.reply(preamble))[0]
                written = self.path.read_text(encoding="utf-8")
                self.assertEqual(recorded.get(_support.CATEGORY, recorded[_support.EVENT]), reading)
                self.assertIn("***", written)
                self.assertEqual([fragment for fragment in _FRAGMENTS if fragment in written], [])

    def test_overlapping_matches_are_masked_whole(self) -> None:
        # One credential inside another, one spelled as the escape its
        # description decodes, and one whose occurrences overlap: every match
        # is found before any text is replaced, so none leaves an end behind.
        for environment, preamble, field, kept in _OVERLAPS:
            with self.subTest(credentials=tuple(environment)), patch.dict(os.environ, environment):
                self.path.unlink(missing_ok=True)
                recorded = self.record(_support.reply(preamble))[0]
                self.assertEqual(recorded[field][_support.TEXT], kept)

    def test_the_escape_depth_bounds_the_search(self) -> None:
        # At the depth, the refused line is excerpted whole, its serialized
        # spelling searched deeper still; one level past, a credential could
        # continue where the search never looked, so each record keeps its
        # category or event and drops its text.
        for preamble, recorded_as in _DEPTHS:
            with self.subTest(recorded_as=recorded_as):
                self.path.unlink(missing_ok=True)
                recorded = self.record(_support.reply(preamble))
                self.assertEqual(list(map(_excerpted, recorded)), [recorded_as])

    def test_an_unbounded_depth_reading_hides_text(self) -> None:
        # With no credential to search for, only reading the reply for a
        # deeper escape spends work: past the bound, where it stopped could
        # hold one, so a reply with a backslash shows no text, and one with
        # none, read without spending any, shows its own.
        no_credentials = patch.dict(os.environ, {}, clear=True)
        with no_credentials, patch.object(redaction, "_WORK_PER_CHARACTER", 0):
            self.record(_support.reply(_SHIFTED_AT_DEPTH))
            recorded = self.record(_support.reply(_UNCLOSED))
        expected = [(_MALFORMED, None), (_MALFORMED, _UNCLOSED)]
        self.assertEqual(list(map(_excerpted, recorded)), expected)

    def test_a_line_holding_a_credential_has_no_text(self) -> None:
        # The value spells the description in the quotes the sink writes it
        # between, so only the line as written holds it: the record is kept,
        # its text dropped and its length stated.
        line = rf'{_OPENING}mock-secret-first\u000amock-secret-second{_CLOSING}'
        with patch.dict(os.environ, {"ANALYTICS_TEST_QUOTED_TOKEN": _QUOTED_VALUE}):
            recorded = self.record(_support.reply(line))
        described = recorded[0][_support.DESCRIPTION_FIELD]
        self.assertEqual(described, {_support.CHARS: 36, _support.TRUNCATED: True})
        self.assertNotIn(_QUOTED_VALUE, self.path.read_text(encoding="utf-8"))

    def test_a_credential_is_masked_as_written(self) -> None:
        # The byte the database refuses is replaced only once the credential
        # around it is masked, so nothing of it is left to replace.
        recorded = self.record(_support.reply(_support.snapshot_line(f"Use {_SURROGATE_ESCAPED} for the test.")))
        self.assertEqual(recorded[0][_support.DESCRIPTION_FIELD][_support.TEXT], "Use *** for the test.")


class OwnCredentialTest(_support.SinkCase):
    """A credential of the case's own, which the search has to see whole or show nothing of."""

    def test_a_deep_continuation_shows_no_text(self) -> None:
        # The excerpt holds the credential's first line, and its continuation
        # is escaped past where the search looked: the excerpt keeps its
        # length alone.
        with patch.dict(os.environ, {"ANALYTICS_TEST_DEEP_TOKEN": _DEEP_TOKEN}):
            recorded = self.record(_support.reply(_DEEP_REPLY))
        excerpt = recorded[0][_support.EXCERPT_FIELD]
        self.assertEqual(excerpt, {_support.CHARS: len(_DEEP_SHOWN), _support.TRUNCATED: True})

    def test_matching_stays_within_its_bound(self) -> None:
        # Each backslash is spelled one or two characters long, or as an
        # escape: tried one way at a time, the ways to split runs spoiled at
        # their end would multiply past any wait. A whole spelling is still
        # found, and past the work bound the whole text is masked.
        for environment, line, shown in _BOUNDED:
            with self.subTest(credentials=tuple(environment)), patch.dict(os.environ, environment):
                self.path.unlink(missing_ok=True)
                excerpt, elapsed = self._timed(line)
                self.assertLess(elapsed, _RUN_SECONDS)
                self.assertEqual(excerpt[_support.TEXT], shown)

    def test_a_cut_cannot_hide_a_sink_spelling(self) -> None:
        # The whole description is searched in the sink's encoding before it
        # is cut: it spells the credential there, so it keeps its length alone.
        with patch.dict(os.environ, {"ANALYTICS_TEST_SINK_TOKEN": _SINK_TOKEN}):
            recorded = self.record(_support.reply(_SINK_LINE))
        described = recorded[0][_support.DESCRIPTION_FIELD]
        self.assertEqual(described, {_support.CHARS: len(_SINK_DESCRIPTION), _support.TRUNCATED: True})
        self.assertNotIn(_SINK_FIRST, self.path.read_text(encoding="utf-8"))

    def test_the_redactor_selection_is_searched(self) -> None:
        # Whatever the credential owner selects is searched for in every
        # spelling, here one only an escape-aware search finds in an excerpt.
        with patch.object(credentials, "secret_values", return_value=(_SELECTED,)):
            recorded = self.record(_support.reply(f"{_UNCLOSED}{_SELECTED_SPELLED}"))
        excerpt = recorded[0][_support.EXCERPT_FIELD]
        self.assertEqual(excerpt[_support.TEXT], f"{_UNCLOSED}***")

    def test_any_line_break_spells_one(self) -> None:
        # Raw across a refused line or escaped inside a description, a line
        # feed, a carriage return, or the two in turn spells each of the
        # credential's own line breaks; the reply is read as handed over.
        for token, message, kept in _LINE_BREAKS:
            with self.subTest(message=message), patch.dict(os.environ, {_LINES_KEY: token}):
                self.path.unlink(missing_ok=True)
                self.assertEqual(_excerpted(self.record(message)[0]), kept)

    def test_a_reply_read_back_with_line_feeds(self) -> None:
        # Codex's last-message file is read with universal newlines, so a CRLF
        # credential the reply wrote verbatim reaches the recorder as line feeds.
        reply_file = self.path.with_name("last-message.txt")
        reply_file.write_bytes(_CRLF_REPLY.encode())
        message = read_last_message(reply_file)
        self.assertNotIn("\r", message)
        with patch.dict(os.environ, {_LINES_KEY: _CRLF_TOKEN}):
            recorded = self.record(message)[0]
        self.assertEqual(_excerpted(recorded), (_MALFORMED, _CRLF_SHOWN))

    def _timed(self, line: str) -> tuple[dict, float]:
        """The excerpt one refused `line` is recorded with, and how long recording it took."""
        started = time.perf_counter()
        recorded = self.record(_support.reply(line))
        return recorded[0][_support.EXCERPT_FIELD], time.perf_counter() - started


def _excerpted(record: dict) -> tuple[str, str | None]:
    """A diagnostic's category -- a snapshot's event -- and the text it kept, None for none."""
    excerpt = record.get(_support.EXCERPT_FIELD) or record.get(_support.DESCRIPTION_FIELD, {})
    named = record.get(_support.CATEGORY, record[_support.EVENT])
    return (named, excerpt.get(_support.TEXT))


class _Counted:
    """Spans counting each one a walk over them hands out."""

    def __init__(self, spans: tuple) -> None:
        self.spans = spans
        self.handed = 0

    def __iter__(self):
        """Each span, counted as it is handed out."""
        for span in self.spans:
            self.handed += 1
            yield span


class _CountedEscapes:
    """The escape pattern, counting every place it is asked to match at."""

    def __init__(self) -> None:
        self.asked = 0

    def match(self, text: str, at: int):
        """The escape at `at`, counted."""
        self.asked += 1
        return _ESCAPES.match(text, at)


class ExcerptWorkTest(unittest.TestCase):
    """Masking a reply stays linear: its credential spans are walked once, and so are the escapes they widen over."""

    def test_widening_looks_at_each_place_once(self) -> None:
        # Every place of a long backslash run starts a match of a credential
        # of backslashes, and each match widens over the run's escapes.
        escapes = _CountedEscapes()
        credentials = redaction.Credentials((redaction._Spelling(_BACKSLASH_TOKEN),), str)
        with patch.object(redaction, "_ESCAPE_RE", escapes):
            redaction._Masker.over(_LONG_RUN, credentials)
        self.assertLessEqual(escapes.asked, len(_LONG_RUN))

    def test_a_search_with_nothing_left_stops(self) -> None:
        # Once no place can continue the credential's spelling, nothing more
        # is stepped through, however much of the credential is left.
        steps = MagicMock(side_effect=_STEP)
        with patch.object(redaction._Spelling, "_step", steps):
            self.assertEqual(redaction._Spelling(_LONG_TOKEN).spans(_SHORT_REPLY), [])
        self.assertLessEqual(steps.call_count, len(_SHORT_REPLY) + 1)

    def test_each_span_is_handed_out_once(self) -> None:
        lines = attachments.attachment_lines(_DUPLICATED)
        spans = _Counted(_TOKEN_SPANS)
        text, covered = redaction._Masker(_DUPLICATED, spans, False).excerpt(lines)
        masked = redaction._Masker(text, (), False).masked(covered)
        self.assertEqual(masked, _EXCERPTED)
        self.assertEqual(spans.handed, _REPEATS)


class WrittenDescriptionTest(unittest.TestCase):
    """A description is masked only in the spelling it was decoded from."""

    def test_another_decoded_text_is_refused(self) -> None:
        # Masking another text than the one read would record that text: the
        # redaction refuses instead, which the recorder diagnoses as its step.
        message = _support.snapshot_line()
        reading = attachments.SnapshotReading("Another description.", (), 1, (0, len(message)))
        with self.assertRaises(ValueError):
            redaction.Credentials.held().sanitized(message, reading)
