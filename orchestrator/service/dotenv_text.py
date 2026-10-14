# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settings written into a ``.env``'s text the way the configuration reads them.

The configuration reads a ``.env`` a line at a time. It skips a blank line and
one starting with ``#``, splits any other at its first ``=`` into a key and a
value, strips the blanks around each, then strips one pair of matching quotes
around the value. The first line naming a key is the one that counts.

``assign`` sets a key's value on that first line, so the setting edited is the
one in effect, and every other line -- the comments around it, a commented-out
example of the same key -- stays as it was, byte for byte. ``assignment``
spells a new line. Both refuse a value the configuration would not read back
as written: one spanning lines, with blanks at either end, or wrapped in
quotes the reader would take off.

Nothing here imports ``orchestrator.config``, whose reader this mirrors: a
setup writes the file on a host where importing it would exit.
"""
from __future__ import annotations

from orchestrator.service.validation import FieldError

_QUOTES = frozenset(("'", '"'))


def _key(line: str) -> str | None:
    """The key ``line`` sets, as the configuration reads it, if any."""
    spelled = line.strip()
    if not spelled or spelled.startswith("#"):
        return None
    return spelled.partition("=")[0].strip()


def assignment(key: str, setting: str) -> str:
    """The ``.env`` line setting ``key`` to ``setting``, without its line end."""
    one_line = setting.splitlines() in ([], [setting])
    opening = setting[:1]
    quoted = opening in _QUOTES and setting[1:].endswith(opening)
    if quoted or not one_line or setting.strip() != setting:
        raise FieldError(
            f"{setting!r} cannot be written as {key} in .env, which reads each "
            "value from one line and strips the blanks and quotes around it",
        )
    return f"{key}={setting}"


def assign(text: str, key: str, setting: str) -> str:
    """``text`` with the line setting ``key`` in effect now setting ``setting``.

    Raises ``LookupError`` when no line sets ``key``: the caller decides
    whether a missing setting is added or is a file it refuses.
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if _key(line) == key:
            ending = line.removeprefix(line.splitlines()[0])
            lines[index] = f"{assignment(key, setting)}{ending}"
            return "".join(lines)
    raise LookupError(f"no line of the .env sets {key}")
