# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A secret in a reply is masked on the raw text, before anything cuts or escapes it.

The redactor replaces each secret's literal value, so it has to see the
secret whole: across the reply's raw lines, inside the description its JSON
escaped, and before a field limit would cut it into halves the redactor no
longer recognizes -- in a snapshot and in a refused line's excerpt alike.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from orchestrator.observability.analytics.observations import bounds
from tests.observability.analytics.observations import observation_test_support as _support

# A secret the process environment holds, spanning two lines, and the parts
# none of which may reach the sink.
_SECRET = "first-line-of-the-secret\nsecond-line-of-the-secret"
_FRAGMENTS = ("first-line", "second-line", "of-the-secret")

# Room a case leaves beside a secret, under a field limit.
_ROOM = 40

# Padding that puts a secret where each field limit would cut it.
_NEAR_THE_DESCRIPTION_CUT = "d" * (bounds.DESCRIPTION_CHARS - _ROOM)
_NEAR_THE_EXCERPT_CUT = "d" * (bounds.EXCERPT_CHARS - _ROOM)

# A snapshot's opening, its payload's close, and a payload that never closes.
_OPENING = 'ANALYTICS: task-snapshot v1 {"description": "'
_CLOSING = '"}'
_UNCLOSED = "ANALYTICS: task-snapshot v1 {"

_CASES = (
    _support.snapshot_line(f"Uses {_SECRET} to log in."),
    f"{_OPENING}{_SECRET}{_CLOSING}",
    _support.snapshot_line(f"{_NEAR_THE_DESCRIPTION_CUT}{_SECRET}"),
    f"{_UNCLOSED}{_NEAR_THE_EXCERPT_CUT}{_SECRET}",
)


class RedactionTest(_support.SinkCase):
    """No fragment of a multiline secret reaches the sink."""

    def setUp(self) -> None:
        super().setUp()
        secret_set = patch.dict(os.environ, {"ANALYTICS_TEST_TOKEN": _SECRET})
        secret_set.start()
        self.addCleanup(secret_set.stop)

    def test_no_secret_fragment_reaches_the_sink(self) -> None:
        # Escaped inside the JSON, raw across the reply's lines, and where the
        # field limit would cut it in two, in a snapshot and in an excerpt.
        for preamble in _CASES:
            with self.subTest(preamble=preamble[-_ROOM:]):
                self.path.unlink(missing_ok=True)
                self.record(_support.reply(preamble))
                written = self.path.read_text(encoding="utf-8")
                self.assertIn("***", written)
                self.assertEqual([fragment for fragment in _FRAGMENTS if fragment in written], [])
