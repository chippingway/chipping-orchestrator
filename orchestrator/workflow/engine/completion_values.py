# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each member of a captured completion may be, read off a comment anybody can edit.

Nothing here trusts the type it finds, and each reader answers None for a
value that is not what its field is, never raising: a capture is read on an
issue whose work is still in a worktree, and a `TypeError` out of a state read
would strand that work behind a crash on every poll. A member the field may
hold as `null` -- the session a CLI named none of, a verification read on a
pull request's description -- is read through `Member.optional`, so it is told
apart from a member that will not read.

The bounds are what a comment should hold for each field: a command and a
checkout path one line each and no longer than a path or a spec ever is, a
session id far shorter, and a frozen handoff no more than sixteen records,
each named as this workflow names its own pinned keys and held as one digest.
Text is held to what UTF-8 can carry, as every recorded report field is
(`report_record_values.carries_utf8`).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.engine import report_record_values as _record_values
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# How long a command, a checkout path, and a session id may be.
MAX_COMMAND = 4096

MAX_WORKTREE = 4096

MAX_SESSION = 256

# How many pinned records one handoff may be frozen over.
MAX_FROZEN = 16

# A frozen record's name: a pinned key as this workflow spells its own.
FIELD_SHAPE = re.compile("[a-z][a-z0-9_]{0,63}")

# What a member that will not read is answered as: never a value any member
# holds, so one read as None is told apart from damage.
DAMAGED = object()

# A frozen record: its name and its digest.
_FROZEN_PAIR = 2


@dataclass(frozen=True)
class Member:
    """One member's reader, answering None for damage; `optional` reads `null` as None."""

    reader: Callable[[Any], Any]
    optional: bool = False

    def read(self, raw: Any) -> Any:
        """What `raw` reads back as, or `DAMAGED`."""
        if raw is None and self.optional:
            return None
        member = self.reader(raw)
        return DAMAGED if member is None else member


def line(raw: Any, limit: int) -> str | None:
    """One single line UTF-8 carries, no longer than `limit`, or None."""
    if not _formats.is_bounded_text(raw, limit) or not _record_values.carries_utf8(raw):
        return None
    return raw


def shaped(raw: Any, shape: re.Pattern[str]) -> str | None:
    """A string whole-matching `shape`, or None."""
    if not isinstance(raw, str) or shape.fullmatch(raw) is None:
        return None
    return raw


def count(raw: Any) -> int | None:
    """A non-negative whole number inside the recorded bound, or None."""
    counted = _payloads.as_count(raw)
    if counted is None or counted > _record_values.MAX_RECORDED_NUMBER:
        return None
    return counted


def frozen(raw: Any) -> tuple | None:
    """A frozen handoff as a capture writes it -- named records, sorted, once each, within the bound -- or None."""
    if not isinstance(raw, list) or len(raw) > MAX_FROZEN:
        return None
    if not all(_frozen_pair(pair) for pair in raw):
        return None
    names = [pair[0] for pair in raw]
    if names != sorted(set(names)):
        return None
    return tuple((name, digest) for name, digest in raw)


def _frozen_pair(raw: Any) -> bool:
    """Whether one frozen record is a pinned key's name and one digest."""
    if not isinstance(raw, list) or len(raw) != _FROZEN_PAIR:
        return False
    name, digest = raw
    if shaped(name, FIELD_SHAPE) is None:
        return False
    return _payloads.as_hex(digest, _formats.DIGEST_LENGTHS) is not None


def report(raw: Any) -> str | None:
    """A complete report the report records' own reading takes, or None."""
    if _record_values.report_text_refusal(raw) is not None:
        return None
    return raw
