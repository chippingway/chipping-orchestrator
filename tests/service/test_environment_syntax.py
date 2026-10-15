# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An `environment.d` file read, and its values expanded, as systemd's generator reads and expands them.

Each case read here was answered the same by systemd 255's own
`systemd-environment-d-generator`, an empty variable's `:-` and `:+` among
them.
"""
from __future__ import annotations

import re
import unittest
from types import MappingProxyType

from orchestrator.service.environment_syntax import expanded, file_assignments
from orchestrator.service.unit_syntax import UnitSyntaxError

# An environment file, and the assignments read out of it before expansion:
# blanks around a key and before a value dropped, and those ending an
# unquoted value; quoted parts joined, the blanks between them dropped; a
# quote inside an unquoted value kept; a backslash making the next character
# itself outside quotes, and only before `"`, `\`, `$`, or a backquote inside
# double quotes; and comments, lines without a `=`, invalid names, and empty
# values said nothing.
_LINES = (
    "  B = spaced  ",
    'C="dq $HOME"',
    "D='sq $HOME'",
    'E=x"y"',
    'F="a" "b"',
    "G='a'\"b\"c",
    r"H=a\ b",
    r'I="q\"x\\y\$z\n"',
    "R=a#b",
    "  # a comment",
    "; another",
    "no assignment",
    "1BAD=x",
    "S=",
    'T=""',
)
# A carriage return ends the first line as a newline ends the others.
_ENVIRONMENT_FILE = "\r".join(("A=plain", "\n".join(_LINES)))
_ASSIGNMENTS = (
    ("A", "plain"),
    ("B", "spaced"),
    ("C", "dq $HOME"),
    ("D", "sq $HOME"),
    ("E", 'x"y"'),
    ("F", "ab"),
    ("G", "abc"),
    ("H", "a b"),
    ("I", r'q"x\y$z\n'),
    ("R", "a#b"),
)

# What each value expands to against the variables set so far.
_ENVIRONMENT = MappingProxyType({"HOME": "/home/alice", "EMPTY": ""})
_EXPANDED = (
    ("$HOME/x", "/home/alice/x"),
    ("${HOME}y", "/home/alicey"),
    ("${NOPE:-default}", "default"),
    ("${EMPTY:-default}", ""),
    ("${EMPTY:+alternate}", "alternate"),
    ("${HOME:-default}", "/home/alice"),
    ("${HOME:+alternate}", "alternate"),
    ("${NOPE:+alternate}", ""),
    ("$$HOME", "$HOME"),
    ("$-x 50%", "$-x 50%"),
    ("$1abc", ""),
    ("$HOME$NOPE", "/home/alice"),
)

# What is read differently here, and what the refusal says. An invalid
# name's value is read all the same, as systemd reads it before ignoring the
# name, so a quote it leaves open would run on over the lines after it.
_BACKSLASH = "\\"
_UNREAD_FILES = (
    ('A="open\n', "the value of A holds an unterminated quote"),
    ('A=1\n"X="\nALLOWED_ISSUE_AUTHORS=alice\n', "line 2 holds an unterminated quote"),
    (f"A=1\nB=continued {_BACKSLASH}\nC=1\n", "line 2 continues past its end"),
    (f"# a comment {_BACKSLASH}\nA=1\n", "line 1 continues past its end"),
    ("A=1\0\n", "NUL character"),
)
_UNREAD_EXPANSIONS = ("${NOPE:-$HOME}", "${}", "${A B}", "${OPEN")


class FileAssignmentsTest(unittest.TestCase):
    """An environment file's assignments, quotes and escapes read, or the file refused."""

    def test_each_assignment_is_read(self) -> None:
        self.assertEqual(file_assignments(_ENVIRONMENT_FILE), list(_ASSIGNMENTS))

    def test_what_is_read_differently_is_refused(self) -> None:
        for text, refusal in _UNREAD_FILES:
            with (
                self.subTest(text=text),
                self.assertRaisesRegex(UnitSyntaxError, re.escape(refusal)),
            ):
                file_assignments(text)


class ExpandedTest(unittest.TestCase):
    """A value's expansions read against the variables set so far, or the value refused."""

    def test_each_expansion_is_read(self) -> None:
        for rvalue, expansion in _EXPANDED:
            with self.subTest(rvalue=rvalue):
                self.assertEqual(expanded(rvalue, _ENVIRONMENT, "X"), expansion)

    def test_an_unread_expansion_is_refused(self) -> None:
        for rvalue in _UNREAD_EXPANSIONS:
            with (
                self.subTest(rvalue=rvalue),
                self.assertRaisesRegex(UnitSyntaxError, re.escape("the value of X holds a ${ expansion other than")),
            ):
                expanded(rvalue, _ENVIRONMENT, "X")


if __name__ == "__main__":
    unittest.main()
