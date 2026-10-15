# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A unit file's `[Service]` settings and an `Environment=` value, read as systemd reads them."""
from __future__ import annotations

import re
import unittest
from types import MappingProxyType

from orchestrator.service.unit_syntax import (
    UnitSyntaxError,
    environment_assignments,
    service_settings,
    working_directory,
)

_SPECIFIERS = MappingProxyType({"h": "/home/alice", "u": "alice"})
_ENVIRONMENT = "Environment"
_BACKSLASH = "\\"

# A unit file, and the settings of its `[Service]` section: a continued line
# joined with its backslash read as a blank, a comment inside it skipped, an
# even run of backslashes ending a line, blanks around a key and a value
# dropped, and every other section's settings left out.
_UNIT_TEXT = r"""[Unit]
Description=Environment=not-a-service-setting
[Service]
# Environment=COMMENTED=1
Environment=A=1 \
; a comment inside the continuation
  B=2
ExecStart=/bin/true \\
  Restart = on-failure
Environment=
[Install]
Environment=Z=9
"""
_SETTINGS = (
    (_ENVIRONMENT, "A=1    B=2"),
    ("ExecStart", r"/bin/true \\"),
    ("Restart", "on-failure"),
    (_ENVIRONMENT, ""),
)

# A unit file systemd reads differently from Python's own text handling, and
# its settings: the first line starting with a byte-order mark loses it and a
# later one keeps it, a carriage return ends a line as a newline does while a
# Unicode line separator does not, and a no-break space is no blank.
_SYSTEMD_TEXT = (
    "[Unit]\r\ufeff[Service]\r\nEnvironment=A=1\u2028B=2\n\r"
    "Environment=C=3\u00a0\n\ufeffEnvironment=D=4\n"
)
_SYSTEMD_SETTINGS = (
    (_ENVIRONMENT, "A=1\u2028B=2"),
    (_ENVIRONMENT, "C=3\u00a0"),
    (f"\ufeff{_ENVIRONMENT}", "D=4"),
)
# Unit files whose comment a byte-order mark opens, and their settings:
# systemd tells comments before it drops the mark, so the comment is read as
# a line -- continued, it swallows the header below, leaving the setting after
# it in no section; inside a section it is a setting, or continues one.
_MARKED_COMMENTS = (
    (f"\ufeff# comment {_BACKSLASH}\n[Service]\nEnvironment=A=1\n", []),
    ("[Service]\n\ufeff; x=y\nEnvironment=A=1\n", [("; x", "y"), (_ENVIRONMENT, "A=1")]),
    (
        f"[Service]\nEnvironment=A=1 {_BACKSLASH}\n\ufeff# comment\nEnvironment=B=2\n",
        [(_ENVIRONMENT, "A=1  # comment"), (_ENVIRONMENT, "B=2")],
    ),
)

# Headers systemd reads -- an unknown section's among them, which it skips --
# and headers at which it stops reading the file: one never closed, one with
# more after its bracket, and one whose name holds a quote, a backslash, or a
# control character.
_READ_HEADERS = ("[X-Ours]\nA=1\n", "[]\nA=1\n", "[Ser]vice]\nA=1\n")
_MALFORMED_HEADERS = (
    "[Manager\n[Service]\nA=1\n",
    "[Service]x\nA=1\n",
    '[Ser"vice]\nA=1\n',
    f"[Ser{_BACKSLASH}vice]\nA=1\n",
    "[Ser\tvice]\nA=1\n",
)

# A `WorkingDirectory=` value, and the directory systemd starts the service in.
_DIRECTORIES = (
    ("", "/home/alice"),
    ("~", "/home/alice"),
    ("%h/work", "/home/alice/work"),
    ("/srv/%u", "/srv/alice"),
)
# A `WorkingDirectory=` value read differently here, and what the refusal says.
_UNREAD_DIRECTORIES = (
    ("-/srv/work", "the directory '-/srv/work' lets systemd skip it when missing"),
    ("work", "the directory 'work' is not an absolute path"),
    ("%t/work", "the directory '%t/work' holds a specifier other than %%, %h, %u"),
)

# An `Environment=` value, and the assignments systemd reads out of it.
_READ = (
    ("PATH=/usr/bin", [("PATH", "/usr/bin")]),
    ('A=1 "B=two words"  C=\'x y\'', [("A", "1"), ("B", "two words"), ("C", "x y")]),
    (r'Q="a\"b"', [("Q", 'a"b')]),
    (r"S='c\'d'", [("S", "c'd")]),
    (r"T=e\\f", [("T", r"e\f")]),
    ("D=%h/bin E=%u F=100%%", [("D", "/home/alice/bin"), ("E", "alice"), ("F", "100%")]),
    ("P=50% Q=% R=a%%%", [("P", "50%"), ("Q", "%"), ("R", "a%%")]),
    ('"G=quoted"tail H=', [("G", "quotedtail"), ("H", "")]),
)

# A value read differently here than by systemd, and what the refusal says.
_UNREAD = (
    ('A="open', "an unterminated quote or escape"),
    ("A=1 \\", "an unterminated quote or escape"),
    (r"A=\n", "the value of A holds a backslash before something other than a backslash or a quote"),
    ('"A=%t"', "the value of A holds a specifier other than %%, %h, %u"),
    ("1A=x", "a word that is not an assignment to a variable name"),
    ("lonely", "a word that is not an assignment to a variable name"),
    ("A=1\u00a0B=2 C", "a word that is not an assignment to a variable name"),
)


class ServiceSettingsTest(unittest.TestCase):
    """Only the `[Service]` settings are read, lines joined and comments skipped as systemd does."""

    def test_reads_the_service_section(self) -> None:
        self.assertEqual(service_settings(_UNIT_TEXT), list(_SETTINGS))

    def test_lines_marks_and_blanks_are_systemd_s(self) -> None:
        self.assertEqual(service_settings(_SYSTEMD_TEXT), list(_SYSTEMD_SETTINGS))
        for text, settings in _MARKED_COMMENTS:
            with self.subTest(text=text):
                self.assertEqual(service_settings(text), settings)

    def test_a_malformed_header_is_refused(self) -> None:
        for text in _READ_HEADERS:
            with self.subTest(text=text):
                self.assertEqual(service_settings(text), [])
        for text in _MALFORMED_HEADERS:
            with (
                self.subTest(text=text),
                self.assertRaisesRegex(UnitSyntaxError, "malformed section header"),
            ):
                service_settings(text)

    def test_a_nul_character_is_refused(self) -> None:
        with self.assertRaisesRegex(UnitSyntaxError, "NUL character"):
            service_settings("[Service]\nEnvironment=A=1\0B=2\n")


class EnvironmentAssignmentsTest(unittest.TestCase):
    """An `Environment=` value is split, unquoted, unescaped, and expanded, or refused."""

    def test_each_value_is_read_as_systemd_reads_it(self) -> None:
        for rvalue, assignments in _READ:
            with self.subTest(rvalue=rvalue):
                self.assertEqual(environment_assignments(rvalue, _SPECIFIERS), assignments)

    def test_what_is_read_differently_is_refused(self) -> None:
        for rvalue, refusal in _UNREAD:
            with (
                self.subTest(rvalue=rvalue),
                self.assertRaisesRegex(UnitSyntaxError, re.escape(refusal)),
            ):
                environment_assignments(rvalue, _SPECIFIERS)


class WorkingDirectoryTest(unittest.TestCase):
    """A `WorkingDirectory=` value names the home when empty or `~`, else an absolute path, or is refused."""

    def test_each_value_names_a_directory(self) -> None:
        for rvalue, directory in _DIRECTORIES:
            with self.subTest(rvalue=rvalue):
                self.assertEqual(working_directory(rvalue, _SPECIFIERS), directory)

    def test_what_is_read_differently_is_refused(self) -> None:
        for rvalue, refusal in _UNREAD_DIRECTORIES:
            with (
                self.subTest(rvalue=rvalue),
                self.assertRaisesRegex(UnitSyntaxError, re.escape(refusal)),
            ):
                working_directory(rvalue, _SPECIFIERS)


if __name__ == "__main__":
    unittest.main()
