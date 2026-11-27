# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The limits a recorded observation is held to.

A text is cut at its field limit with the cut stated -- its whole length
and that it was cut -- and a record past its limit drops its texts whole,
each still stating its length, while every identifier stays whole.
"""
from __future__ import annotations

import json

from orchestrator.observability.analytics.observations import bounds, records
from tests.observability.analytics.observations import observation_test_support as _support

# The published limits, written out rather than read off the owner, so a
# limit that moves fails here instead of moving the boundary with it.
_DESCRIPTION_CHARS = 1000
_EXCERPT_CHARS = 500
_RECORD_BYTES = 8192

# The widest character the sink escapes: twelve bytes for one character.
_WIDEST = "\U0001F600"

_EXCERPT_STEM = "ANALYTICS: task-snapshot v1 {"


def _boundaries(limit: int) -> tuple:
    """Each length a limit is tested at, and the cut it reads as: kept, whole length, cut."""
    return (
        (limit, (limit, limit, False)),
        (limit + 1, (limit, limit + 1, True)),
    )


def _cut(described: dict) -> tuple:
    kept = described[_support.TEXT]
    return (
        len(kept),
        described[_support.CHARS],
        described[_support.TRUNCATED],
    )


def _kept(described: dict) -> dict:
    """A recorded text's fields, as its bounded text is built from."""
    return {"kept": described[_support.TEXT], "chars": described[_support.CHARS]}


def _snapshot_of(text: str) -> dict:
    return records.task_snapshot_record(_support.RUN, bounds.bounded(text, _DESCRIPTION_CHARS))


def _record_of_length(length: int) -> dict:
    """A snapshot record whose serialized line is exactly `length` bytes, its text within the field limit."""
    for wide in range(_DESCRIPTION_CHARS + 1):
        widest = _WIDEST * wide
        short = length - len(json.dumps(_snapshot_of(widest), sort_keys=True))
        if 0 <= short <= _DESCRIPTION_CHARS - wide:
            record = _snapshot_of(widest + "d" * short)
            if len(json.dumps(record, sort_keys=True)) == length:
                return record
    raise AssertionError(f"no snapshot record serializes to {length} bytes")


class FieldLimitTest(_support.SinkCase):
    """Each text's limit, at and one past its boundary."""

    def test_a_description_is_cut_at_its_limit(self) -> None:
        for length, cut in _boundaries(_DESCRIPTION_CHARS):
            with self.subTest(length=length):
                self.path.unlink(missing_ok=True)
                recorded = self.record(_support.reply(_support.snapshot_line("d" * length)))
                self.assertEqual(_cut(recorded[0][_support.DESCRIPTION_FIELD]), cut)

    def test_an_excerpt_is_cut_at_its_limit(self) -> None:
        for length, cut in _boundaries(_EXCERPT_CHARS):
            with self.subTest(length=length):
                self.path.unlink(missing_ok=True)
                line = _EXCERPT_STEM.ljust(length, "d")
                excerpt = self.record(_support.reply(line))[0][_support.EXCERPT_FIELD]
                self.assertEqual(_cut(excerpt), cut)
                self.assertTrue(line.startswith(excerpt[_support.TEXT]))


class RecordLimitTest(_support.SinkCase):
    """A record at and past its limit, and the identifiers it never cuts."""

    def test_the_limit_drops_the_text_alone(self) -> None:
        at_limit = _record_of_length(_RECORD_BYTES)
        described = bounds.BoundedText(**_kept(at_limit[_support.DESCRIPTION_FIELD]))
        past = bounds.BoundedText(f"{described.kept}d", described.chars + 1)
        self.assertEqual(json.loads(records.serialized(at_limit)), at_limit)
        kept = json.loads(records.serialized(records.task_snapshot_record(_support.RUN, past)))
        self.assertEqual(
            (kept[_support.DESCRIPTION_FIELD], kept[_support.SOURCE_FIELD], kept["task_ref"]),
            ({_support.CHARS: past.chars, _support.TRUNCATED: True}, _support.SOURCE, _support.TASK_REF),
        )

    def test_the_widest_characters_pass_it(self) -> None:
        # A whole description of characters escaped twelve bytes wide is
        # within its field limit and past the record's: recorded, its text
        # dropped and its length kept.
        payload = json.dumps({_support.DESCRIPTION_FIELD: _WIDEST * _DESCRIPTION_CHARS}, ensure_ascii=False)
        recorded = self.record(_support.reply(f"ANALYTICS: task-snapshot v1 {payload}"))
        described = recorded[0][_support.DESCRIPTION_FIELD]
        self.assertEqual(described, {_support.CHARS: _DESCRIPTION_CHARS, _support.TRUNCATED: True})
        self.assertEqual(recorded[0][_support.SOURCE_FIELD], _support.SOURCE)
