# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The part of systemd's unit-file syntax the service's environment is read through.

``service_settings`` reads a unit file or drop-in the way systemd's parser
does. A line ends at a newline, a carriage return, or the two together; a
line starting with ``#`` or ``;`` is a comment, inside a continuation too;
only then does the first line that starts with a UTF-8 byte-order mark have
it dropped, so a comment the mark opens is read as a line; a line ending in
an odd number of backslashes continues on the next, that backslash read as a
blank; ``[Section]`` opens a section; and every other line holding
a ``=`` is a setting, its key and value stripped of the blanks around them. A
line that starts with ``[`` but does not end with ``]``, or whose name holds a
control character, a backslash, or a quote, is a malformed header, at which
systemd stops reading the file, and is refused.
Blanks are systemd's: a space, a tab, a newline, or a carriage return, and no
other character. Only the settings of one section are answered -- a unit's
``[Service]`` unless a caller names another, such as ``user.conf``'s
``[Manager]`` -- in the order they appear, and a file holding a NUL character
is refused.

``environment_assignments`` reads one ``Environment=`` value as systemd does:
split into words at blanks outside quotes, each word unquoted -- a double- or
single-quoted part keeps its blanks -- and unescaped, then its specifiers
expanded, and each word then a ``NAME=value`` assignment. Of systemd's
escapes only a backslash before a backslash or a quote is read, and of its
specifiers only ``%%`` and the ones a caller supplies -- a unit's or the user
manager's own -- a ``%`` ending a word being itself, as systemd leaves it.
``working_directory``
reads one ``WorkingDirectory=`` value: empty or ``~``, the home -- the
default a user manager gives its services -- and otherwise an absolute path,
its specifiers expanded. Anything else -- another escape or specifier, an
unterminated quote, a word that is not an assignment to a valid name, a
directory that is relative or marked ``-`` for systemd to skip when missing
-- raises ``UnitSyntaxError`` rather than being guessed at, since a value
misread here would be checked as something the service never receives. Its
reason names the variable whose value it refuses, and quotes no value but a
directory's: an ``Environment=`` value may hold a token.

Nothing here imports from the package.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

_SERVICE_SECTION = "[Service]"
_COMMENTS = ("#", ";")
_CONTINUED = "\\"
_BLANKS = " \t\n\r"
_NUL = "\0"
_HOME = "~"
_MISSING_OK = "-"
_ABSOLUTE = "/"

# Where a line ends, and the byte-order mark the first line holding one
# starts with.
_LINE_END = re.compile("\r\n|\n\r|[\n\r]")
_BYTE_ORDER_MARK = re.compile("^﻿", re.MULTILINE)
# A line opening a section header systemd refuses: one whose name holds a
# control character, a backslash, or a quote, or that does not end with the
# closing bracket.
_MALFORMED_HEADER_LINE = re.compile(r'\[(?![^\x00-\x1f\x7f\\"\']*\]\Z)')

# What a pair of double or single quotes holds, an escape, and one character
# a word holds outside quotes.
_IN_DOUBLE = r'(?:[^"\\]|\\.)*'
_IN_SINGLE = r"(?:[^'\\]|\\.)*"
_ESCAPED = r"\\."
_PLAIN = r'[^ \t\n\r"\'\\]'
# One word of an `Environment=` value, and the parts it is made of: what a
# pair of quotes holds, or a run of escapes and characters outside them.
_WORD_PATTERN = f"(?:\"{_IN_DOUBLE}\"|'{_IN_SINGLE}'|{_ESCAPED}|{_PLAIN})+"
_PART_PATTERN = f"\"({_IN_DOUBLE})\"|'({_IN_SINGLE})'|((?:{_ESCAPED}|{_PLAIN})+)"
_WORD = re.compile(_WORD_PATTERN, re.DOTALL)
_PART = re.compile(_PART_PATTERN, re.DOTALL)
_READ_ESCAPES = re.compile(r'(?:[^\\]|\\[\\"\'])*', re.DOTALL)
_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
_SPECIFIER = re.compile("%(.)", re.DOTALL)
_ASSIGNMENT = re.compile("([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)
# The variable a word assigns, read before its quotes are, to name it by.
_NAMED = re.compile("[\"']?([A-Za-z_][A-Za-z0-9_]*)=")

# Every reason names what it refuses without quoting a value of it, since an
# `Environment=` value may hold a token.
_HOLDS_NUL = "it holds a NUL character, where systemd would end a line"
_MALFORMED_HEADER = "it holds a malformed section header, at which systemd stops reading the file"
_UNTERMINATED = "an unterminated quote or escape"
_NOT_ASSIGNED = "a word that is not an assignment to a variable name"
_A_WORD = "a word"
_THE_VALUE_OF = "the value of {0}"
_UNREAD_ESCAPE = "{0} holds a backslash before something other than a backslash or a quote"
_UNREAD_SPECIFIER = "{0} holds a specifier other than {1}"
_SKIPPED_WHEN_MISSING = (
    "the directory {0!r} lets systemd skip it when missing, leaving the service where the user manager runs"
)
_RELATIVE = "the directory {0!r} is not an absolute path"


class UnitSyntaxError(ValueError):
    """A value read here differently from systemd, with what about it."""


def service_settings(text: str, section: str = _SERVICE_SECTION) -> list[tuple[str, str]]:
    """Each ``Key=value`` setting of ``section`` of the unit or configuration file ``text``, in order."""
    settings = []
    current = None
    for line in _logical_lines(text):
        # Refused, not quoted, since a header could hold anything a value does.
        if _MALFORMED_HEADER_LINE.match(line):
            raise UnitSyntaxError(_MALFORMED_HEADER)
        # A header opens a section; the one read holds no `=` to be taken
        # for a setting of its own.
        current = line if line.startswith("[") else current
        if current == section and "=" in line:
            key, rvalue = line.split("=", 1)
            settings.append((key.strip(_BLANKS), rvalue.strip(_BLANKS)))
    return settings


def environment_assignments(
    rvalue: str,
    specifiers: Mapping[str, str],
) -> list[tuple[str, str]]:
    """Each ``NAME=value`` assignment of the ``Environment=`` value ``rvalue``, in order.

    ``specifiers`` maps each specifier letter but ``%`` to what it expands to.
    """
    if _WORD.sub("", rvalue).strip(_BLANKS):
        raise UnitSyntaxError(_UNTERMINATED)
    assignments = []
    for word in _WORD.findall(rvalue):
        named = _NAMED.match(word)
        described = _THE_VALUE_OF.format(named.group(1)) if named else _A_WORD
        assignment = _ASSIGNMENT.fullmatch(_expanded(_unquoted(word, described), specifiers, described))
        if assignment is None:
            raise UnitSyntaxError(_NOT_ASSIGNED)
        assignments.append((assignment.group(1), assignment.group(2)))
    return assignments


def working_directory(rvalue: str, specifiers: Mapping[str, str]) -> str:
    """The directory the ``WorkingDirectory=`` value ``rvalue`` starts the service in.

    ``specifiers`` maps each specifier letter but ``%`` to what it expands
    to, ``h`` the home among them.
    """
    if rvalue in {"", _HOME}:
        return specifiers["h"]
    if rvalue.startswith(_MISSING_OK):
        raise UnitSyntaxError(_SKIPPED_WHEN_MISSING.format(rvalue))
    directory = _expanded(rvalue, specifiers, f"the directory {rvalue!r}")
    if not directory.startswith(_ABSOLUTE):
        raise UnitSyntaxError(_RELATIVE.format(rvalue))
    return directory


def _logical_lines(text: str) -> Iterator[str]:
    """Each line of ``text`` but its comments, its continuations joined and its blanks stripped."""
    if _NUL in text:
        raise UnitSyntaxError(_HOLDS_NUL)
    # systemd tells a comment before it drops the byte-order mark, so a line
    # the mark opens is never one, even when a comment follows the mark.
    uncommented = "\n".join(
        line for line in _LINE_END.split(text) if not line.lstrip(_BLANKS).startswith(_COMMENTS)
    )
    pending = ""
    for line in _BYTE_ORDER_MARK.sub("", uncommented, count=1).split("\n"):
        continued = line.removesuffix(_CONTINUED)
        if (len(line) - len(line.rstrip(_CONTINUED))) % 2:
            pending = f"{pending}{continued} "
            continue
        yield f"{pending}{line}".strip(_BLANKS)
        pending = ""
    yield pending.strip(_BLANKS)


def _unquoted(word: str, described: str) -> str:
    """``word`` with its quotes removed and its escapes read, ``described`` naming it in a refusal."""
    # Each part is held by the one group of the three that matched it.
    parts = ["".join(groups) for groups in _PART.findall(word)]
    if not all(_READ_ESCAPES.fullmatch(part) for part in parts):
        raise UnitSyntaxError(_UNREAD_ESCAPE.format(described))
    return "".join(_ESCAPE.sub(r"\1", part) for part in parts)


def _expanded(word: str, specifiers: Mapping[str, str], described: str) -> str:
    """``word`` with each of its specifiers expanded, ``described`` naming it in a refusal."""
    known = {"%": "%", **specifiers}
    letters = re.escape("".join(known))
    # A `%` with nothing after it is kept as it is.
    readable = f"(?:[^%]|%[{letters}])*%?"
    if not re.fullmatch(readable, word, re.DOTALL):
        named = ", ".join(f"%{letter}" for letter in known)
        raise UnitSyntaxError(_UNREAD_SPECIFIER.format(described, named))
    return _SPECIFIER.sub(lambda specifier: known[specifier.group(1)], word)
