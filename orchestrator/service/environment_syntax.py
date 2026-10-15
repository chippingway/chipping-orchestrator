# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The part of systemd's environment-file syntax ``environment.d`` is read through.

``file_assignments`` reads one ``environment.d`` file as systemd's
environment-file parser does. A line ends at a newline or a carriage return.
A blank line, or one whose first character past its blanks is ``#`` or
``;``, says nothing; a line without a ``=`` is dropped, and so is one whose
key, stripped of trailing blanks, is not a valid variable name, or whose value
reads as empty -- systemd ignores such an assignment, leaving the variable as
it was. After the
``=`` and any blanks, the value is a run of parts: a single-quoted part taken
as it is; a double-quoted part, in which a backslash before a double quote,
a backslash, a dollar sign, or a backquote makes that character itself and is
kept before anything else; blanks between parts dropped; and, once a part
starts with anything but a quote, the rest of the line, each backslash making
the character after it itself and the blanks ending it dropped. A value or a
comment still open at the end of its line -- an unterminated quote, or a
backslash continuing it -- is refused, an invalid name's value too: systemd
reads that value before it drops the name, so a quote it leaves open runs on
over the lines after it. So is a file holding a NUL character.

``expanded`` expands a value against the variables set so far, as the
generator does: ``$$`` is a ``$``; ``$NAME`` and ``${NAME}`` are the variable,
empty where it is unset; ``${NAME:-TEXT}`` is ``TEXT`` where the variable is
unset, and ``${NAME:+TEXT}`` is ``TEXT`` where it is set, an empty value
counting as set either way -- as systemd 255 expands them, whatever
``environment.d(5)`` says of an empty one; any other ``$`` is itself. A ``${``
none of those reads, such as one nesting another expansion, is refused. Every
refusal is a ``UnitSyntaxError`` whose reason names the line or the variable
it refuses and quotes no value.

Nothing here imports from the package but ``unit_syntax``.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from functools import partial

from orchestrator.service.unit_syntax import UnitSyntaxError

_BLANKS = " \t"
_COMMENTS = ("#", ";")
_NUL = "\0"
_LINE_END = re.compile("[\n\r]")
_NAME = re.compile("[A-Za-z_][A-Za-z0-9_]*")
_CONTINUED = re.compile(r"(?<!\\)(?:\\\\)*\\\Z")

# One part of a value after the blanks before it: what a pair of single or
# double quotes holds, or the unquoted rest of the line.
_PART = re.compile(r'[ \t]*(?:\'([^\']*)\'|"((?:[^"\\]|\\.)*)"|([^\'" \t].*))', re.DOTALL)
_DOUBLE_QUOTED_ESCAPE = re.compile(r'\\([\\"$`])')
_UNQUOTED = re.compile(r"((?:\\.|[^\\])*?)[ \t]*", re.DOTALL)
_ESCAPE = re.compile(r"\\(.)", re.DOTALL)

# Each expansion the generator reads: an escaped `$`, a braced name with or
# without a default or alternate text, and a bare name.
_EXPANSION = re.compile(
    r"\$(?:(?P<escaped>\$)|\{(?P<braced>\w+)\}|\{(?P<tested>\w+):(?P<test>[-+])(?P<text>[^${}]*)\}|(?P<bare>\w+))",
    re.ASCII,
)
_OPENED = "${"
_DEFAULT = "-"

_HOLDS_NUL = "it holds a NUL character"
# Every reason names the line or the variable it refuses without quoting a
# value, since a value may hold a token.
_CONTINUED_LINE = "line {0} continues past its end, which is not read here"
_UNTERMINATED = "{0} holds an unterminated quote"
_THE_VALUE_OF = "the value of {0}"
_A_LINE = "line {0}"
_UNREAD_EXPANSION = "the value of {0} holds a ${{ expansion other than ${{NAME}}, ${{NAME:-TEXT}}, or ${{NAME:+TEXT}}"


def file_assignments(text: str) -> list[tuple[str, str]]:
    """Each ``KEY=value`` assignment of the environment file ``text``, in order, its value not yet expanded."""
    if _NUL in text:
        raise UnitSyntaxError(_HOLDS_NUL)
    assignments = []
    for number, line in enumerate(_LINE_END.split(text), start=1):
        assignment = _assignment(line, number)
        if assignment is not None:
            assignments.append(assignment)
    return assignments


def expanded(rvalue: str, environment: Mapping[str, str], name: str) -> str:
    """``rvalue``, the value of ``name``, with each expansion in it read against ``environment``."""
    if _OPENED in _EXPANSION.sub("", rvalue):
        raise UnitSyntaxError(_UNREAD_EXPANSION.format(name))
    return _EXPANSION.sub(partial(_expansion, environment=environment), rvalue)


def _assignment(line: str, number: int) -> tuple[str, str] | None:
    """The assignment ``line``, the file's ``number``-th, makes, or ``None`` where it makes none."""
    stripped = line.lstrip(_BLANKS)
    commented = stripped.startswith(_COMMENTS)
    if not commented and "=" not in stripped:
        return None
    if _CONTINUED.search(stripped):
        raise UnitSyntaxError(_CONTINUED_LINE.format(number))
    if commented:
        return None
    key, _, rvalue = stripped.partition("=")
    key = key.rstrip(_BLANKS)
    # systemd reads the value before it ignores an invalid name, so a quote
    # that value leaves open runs on over the lines after it all the same.
    read = _parts(rvalue, _described(key, number))
    return (key, read) if read and _NAME.fullmatch(key) else None


def _described(key: str, number: int) -> str:
    """How a refusal names the value of ``key``, on the file's ``number``-th line: by its name where it is valid."""
    return _THE_VALUE_OF.format(key) if _NAME.fullmatch(key) else _A_LINE.format(number)


def _parts(rvalue: str, described: str) -> str:
    """What ``rvalue``, the value ``described`` names, holds, its quotes and escapes read."""
    if not rvalue.strip(_BLANKS):
        return ""
    part = _PART.match(rvalue)
    if part is None:
        raise UnitSyntaxError(_UNTERMINATED.format(described))
    single, double, unquoted = part.groups()
    if unquoted is not None:
        return _ESCAPE.sub(r"\1", _UNQUOTED.fullmatch(unquoted).group(1))
    read = single if double is None else _DOUBLE_QUOTED_ESCAPE.sub(r"\1", double)
    return f"{read}{_parts(rvalue[part.end():], described)}"


def _expansion(expansion: re.Match[str], environment: Mapping[str, str]) -> str:
    """What one expansion reads as against ``environment``."""
    if expansion.group("escaped"):
        return "$"
    tested = expansion.group("tested")
    if tested is None:
        return environment.get(expansion.group("braced") or expansion.group("bare"), "")
    present = tested in environment
    if expansion.group("test") == _DEFAULT:
        return environment[tested] if present else expansion.group("text")
    return expansion.group("text") if present else ""
