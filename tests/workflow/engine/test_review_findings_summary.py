# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A line of pytest's short summary read for the failure it reports, its test ID's end decided by its caller's naming.

Each `FAILED`, `ERROR`, or `SUBFAILED` line reads as the node ID pytest
printed -- parameters, classes, and a path holding blanks, brackets, or the
dash included -- and the message after it, or as the path whose collection
failed. Where nothing names the ID, it ends where a message of pytest's shape
may first begin, saying so where a later split could end it too; where the
caller's naming callback names one, the longest of those named surest wins. A
line saying pytest refused the run reports no node, and any other line nothing.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from orchestrator.workflow.engine.review_findings_summary import SummaryLine

# Parameters and a message each holding the dash and text of the other's shape.
_SHAPED_NODE = "tests/test_parameter.py::test_value[left] - Error: right]"
_SHAPED_SUMMARY = f"FAILED {_SHAPED_NODE} - AssertionError: values differ"
_SHAPED_SHORT = "tests/test_parameter.py::test_value[left]"
_SHAPED_MESSAGE = "FAILED tests/test_x.py::test_x[a] - AssertionError: got [b] - KeyError: 'c'"
_SEPARATED = "FAILED tests/test_fixture.py::TestK::test_m[a::b] - AssertionError: got [b] - KeyError: c"
_SURE = (1,)
# A doctest's node ID, its test repeating its text file's name, the dash in it.
_DOCTEST = "sample - spaced.txt::sample - spaced.txt"

# Summary lines as pytest prints them, each with the node ID and the message
# it reads as where nothing names the ID: parameters with blanks, dashes, and
# the very dash and bracket that part an ID from its message, a message cut
# short or holding brackets and dashes of its own, a bare exception's name, a
# strict XPASS's mark, the repr of a group's one exception, a class, paths
# holding blanks, brackets, or the dash, doctests named by their text files,
# the dash in those too, and no message at all.
_FAILED = (
    ("tests/test_a.py::test_fail", "AssertionError: values differ - badly"),
    ("tests/test_a.py::test_param[a b]", "AssertionError: assert 'a b' == 'nope'"),
    ("tests/test_a.py::test_param[lost-response]", "AssertionError: assert 'lost-re..."),
    ("tests/test_a.py::test_param[x - y]", "AssertionError: assert 'x - y' == 'nope'"),
    ("tests/test_a.py::TestK::test_m", "KeyError: 'VERIFY_COMMANDS'"),
    ("tests/test_a.py::test_value[left] - right]", "assert 1 == 2"),
    ("tests/test_a.py::test_items[case]", "assert [1] == [2]"),
    ("tests/test_a.py::test_list[x]", "AssertionError: lists [1] - [2] differ"),
    ("tests/test_a.py::test_raise[p]", "ValueError"),
    ("test_probe.py::test_xpass[case]", "[XPASS(strict)]"),
    ("test_probe.py::test_group[case]", "ValueError('inner') [single exception in ExceptionGroup]"),
    ("tests/test file.py::test_value[a b]", "ValueError: actual failure"),
    ("dir [x]/test_[api].py::test_value", "assert 0 == 1"),
    ("dir [x]/test_[api].py::test_param[a - b]", "AssertionError: assert 'a - b' == 1"),
    ("test - named.py::test_value[left - right]", "assert 0 == 1"),
    ("sub/test - named.py::test_value[left - right]", ""),
    ("sample spaced.txt::sample spaced.txt", ""),
    (_DOCTEST, ""),
    ("docs/a - b.txt::a - b.txt", "ValueError: x"),
)

# Error lines: a node ID, its message holding the dash a path alone could end
# on were it short of the ID's separator; and a path alone -- holding blanks,
# the dash, or a separator in its message -- whose collection failed, a
# doctest's text file holding the dash, its suffix no exception's name, with
# no message where the terminal leaves pytest no room for one, or a bare one.
_ERRORED = (
    ("tests/test_a.py::test_setup", "RuntimeError: fixture exploded"),
    ("tests/test_a.py::test_import", "ImportError: a - b"),
    ("tests/test_b.py", ""),
    ("tests/test file.py", "ImportError: cannot import name 'b' from 'a::c'"),
    ("test - broken.py", ""),
    ("sample.txt", "ValueError: line 2 of the docstring for sample.txt lacks b..."),
    ("sample - spaced.txt", ""),
    ("sample - spaced.txt", "pkg.BrokenError"),
)

# Subtest lines: the description, in brackets, parentheses, or both, holding
# brackets, separators, and the dash of its own, beside paths holding blanks,
# a bracket a blank follows, or neither; and a message whose bracket nothing
# closes, read so where no other way is.
_SUBFAILED = (
    ("(value=1)", "test_sub.py::TestCase::test_values", "AssertionError: 1 != 0"),
    ("[first case] (n=3)", "tests/test_sub.py::test_fixture", ""),
    ("(i=0)", "test probes.py::test_probe", "assert 1 == 2"),
    ("[case [a] b] (n=3)", "test probes.py::test_probe", "assert 3 == 4"),
    ("[case [a] - b] (n=3)", "test_probes.py::test_probe", "assert 5 == 6"),
    ("[case [a] - b] (n=3)", "test probes.py::test_probe", "assert 3 == 4"),
    ("[see [a] x::y]", "test_probes.py::test_probe", "assert 7 == 8"),
    ("[m]", "dir [x] y/test_probes.py::test_probe", "assert 9 == 0"),
    ("(i=0)", "dir [x] y/test_probes.py::test_probe", "assert 2 == 3"),
    ("[a [b]", "test_probes.py::test_probe", "assert 1 == 1"),
)

# Lines reporting nothing: statistics, a heading, a failure naming no test,
# pytest's usage line, a marked line, and a passing test's line.
_UNREPORTED = (
    "1 failed, 7851 passed in 330.02s",
    "=========================== short test summary info ============================",
    "FAILED test_empty - ValueError: empty input",
    "ERROR: usage: python -m pytest [options] [file_or_dir] [file_or_dir] [...]",
    "E   AssertionError: values differ",
    "PASSED tests/test_a.py::test_ok",
    "",
)


def _unnamed(node: str, message: str) -> tuple[int, ...]:
    """A naming callback naming nothing."""
    return ()


def _line(outcome: str, node: str, error: str) -> str:
    """The summary line reporting `outcome` of `node` and `error`, the dash left out where it gives none."""
    return f"{outcome} {node} - {error}".removesuffix(" - ")


def _naming(*named: str):
    """A naming callback naming each of `named` alike."""
    return lambda node, message: _SURE if node in named else ()


class SummaryLineTest(unittest.TestCase):
    """Each summary line reads as the failure pytest reports, nothing naming its ID."""

    def test_failed_lines_read_exact_ids(self) -> None:
        for node, error in _FAILED:
            line = _line("FAILED", node, error)
            with self.subTest(line=line):
                self.assertEqual(SummaryLine.read(line, _unnamed), SummaryLine(node, error))
        # The blanks and carriage return framing a line read as none of it.
        self.assertEqual(
            SummaryLine.read("  FAILED tests/test_a.py::test_x - ValueError: x \r", _unnamed),
            SummaryLine("tests/test_a.py::test_x", "ValueError: x"),
        )

    def test_error_and_subtest_lines(self) -> None:
        for node, error in _ERRORED:
            line = _line("ERROR", node, error)
            with self.subTest(line=line):
                read = SummaryLine.read(line, _unnamed)
                self.assertEqual(read, SummaryLine(node, error, errored=True))
        for subtest, node, error in _SUBFAILED:
            line = _line(f"SUBFAILED{subtest}", node, error)
            with self.subTest(line=line):
                read = SummaryLine.read(line, _unnamed)
                self.assertEqual(read, SummaryLine(node, error, subtest=subtest))

    def test_refusals_report_no_node(self) -> None:
        # pytest refusing a run before running any test reports no node, its
        # message the error: a usage it refuses, or an argument its parser could
        # not read -- however that parser names the program.
        refusals = (
            ("ERROR: file or directory not found: __missing__.py", "file or directory not found: __missing__.py"),
            ("python -m pytest: error: unrecognized arguments: --bogus-flag", "unrecognized arguments: --bogus-flag"),
            ("pytest: error: argument -k: expected one argument", "argument -k: expected one argument"),
        )
        for line, error in refusals:
            with self.subTest(line=line):
                refused = SummaryLine("", error, errored=True)
                self.assertEqual(SummaryLine.read(line, _unnamed), refused)
                self.assertEqual(SummaryLine.refused(line), refused)
        self.assertIsNone(SummaryLine.refused("ERROR tests/test_b.py"))
        for line in _UNREPORTED:
            with self.subTest(line=line):
                self.assertIsNone(SummaryLine.read(line, _unnamed))


class SummaryLineNamingTest(unittest.TestCase):
    """Where a test ID ends where the dash could end it at several places."""

    def test_unnamed_ids_end_at_the_first_message(self) -> None:
        # Nothing naming the ID, it ends where a message of pytest's shape may
        # first begin, so the message is never cut short; where a later split
        # leaves one too, the line says where the ID ends is unsure.
        unsure = (
            (_SHAPED_SUMMARY, _SHAPED_SHORT, "Error: right] - AssertionError: values differ"),
            (_SHAPED_MESSAGE, "tests/test_x.py::test_x[a]", "AssertionError: got [b] - KeyError: 'c'"),
            (_SEPARATED, "tests/test_fixture.py::TestK::test_m[a::b]", "AssertionError: got [b] - KeyError: c"),
        )
        for line, node, error in unsure:
            with self.subTest(line=line):
                read = SummaryLine.read(line, _unnamed)
                self.assertEqual(read, SummaryLine(node, error, unsure=True))

    def test_callback_is_asked_each_end(self) -> None:
        # Each ID the line may end on is asked about in turn, with the message
        # that would follow it.
        named = Mock(return_value=())
        SummaryLine.read(_SHAPED_SUMMARY, named)
        self.assertEqual([asked.args for asked in named.call_args_list], [
            (_SHAPED_SHORT, "Error: right] - AssertionError: values differ"),
            (_SHAPED_NODE, "AssertionError: values differ"),
        ])

    def test_surest_longest_named_id_wins(self) -> None:
        # The ID named surest wins, the longest among those named alike, and
        # one named is never unsure.
        named = (
            (_naming(_SHAPED_NODE), _SHAPED_NODE),
            (_naming(_SHAPED_SHORT), _SHAPED_SHORT),
            (_naming(_SHAPED_SHORT, _SHAPED_NODE), _SHAPED_NODE),
            (lambda node, message: (2, 0) if node == _SHAPED_SHORT else _SURE, _SHAPED_SHORT),
            (lambda node, message: (2, -len(node)), _SHAPED_SHORT),
        )
        for naming, node in named:
            with self.subTest(node=node):
                read = SummaryLine.read(_SHAPED_SUMMARY, naming)
                self.assertEqual((read.node, read.unsure), (node, False))
                self.assertEqual(f"{read.node} - {read.error}", _SHAPED_SUMMARY.removeprefix("FAILED "))

    def test_naming_parts_a_subtest_description(self) -> None:
        # The ID named surest decides where a subtest's description ends too,
        # ahead of how pytest writes one.
        read = SummaryLine.read("SUBFAILED[m] dir [x] y/test.py::t - assert 0", _naming("y/test.py::t"))
        self.assertEqual(read, SummaryLine("y/test.py::t", "assert 0", subtest="[m] dir [x]"))

    def test_doctests_holding_the_dash_are_offered(self) -> None:
        # A doctest's whole ID is asked about, and the callback decides over
        # it as over any other.
        named = Mock(return_value=())
        SummaryLine.read(f"FAILED {_DOCTEST}", named)
        self.assertIn((_DOCTEST, ""), [asked.args for asked in named.call_args_list])
        for node in (_DOCTEST, "sample - spaced.txt::sample"):
            with self.subTest(node=node):
                self.assertEqual(SummaryLine.read(f"FAILED {_DOCTEST}", _naming(node)).node, node)


if __name__ == "__main__":
    unittest.main()
