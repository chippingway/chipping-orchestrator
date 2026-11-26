# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A secret in a reply is masked in the telemetry copy, never in the reply the attachment is read from.

The redactor replaces each secret's literal value, so it has to see the
secret whole: across the reply's raw lines, inside a description or a
refused line its JSON escaped -- canonically or not -- in the JSON spelling
the sink writes a decoded description back in, before a field limit would cut
it into halves the redactor no longer recognizes, and before a character the
database refuses is replaced inside it. The
attachment itself is read off the reply as written, so a secret's raw line
break inside the JSON leaves the line malformed rather than repaired by the
mask.
"""
from __future__ import annotations

import json
import os
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.analytics.observations import bounds
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
_UNICODE_ESCAPED = _SECRET.replace("\n", r"\u000a").replace("-", r"\u002d")

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

    def test_a_credential_is_masked_as_written(self) -> None:
        # The byte the database refuses is replaced only once the credential
        # around it is masked, so nothing of it is left to replace.
        recorded = self.record(_support.reply(_support.snapshot_line(f"Use {_SURROGATE_ESCAPED} for the test.")))
        self.assertEqual(recorded[0][_support.DESCRIPTION_FIELD][_support.TEXT], "Use *** for the test.")
