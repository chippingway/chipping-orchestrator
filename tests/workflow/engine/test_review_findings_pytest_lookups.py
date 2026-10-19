# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Each pytest summary line takes the section of its own run it reports, and names its test ID by those sections.

A test's line takes the first section of its run titled by the test's name --
its subtest's description beside it -- or printed untitled by `--tb=line`, no
line having taken it, the one whose exception the line's error opens where it
gives one; an error's line the setup or teardown section whose exception its
error opens, else a collection's section of its run naming its path however
spelled, or its run's interruption. A section showing a line's message names
the line's ID before a title does, and each section goes to one line at most,
so what no line took is left to read by its own title.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine.review_findings_pytest import COLLECTION
from orchestrator.workflow.engine.review_findings_summary import SummaryLine
from tests.workflow.engine.review_findings_pytest_test_support import (
    ERRORS_HEADING,
    FAILURES_HEADING,
    GROUPS_LINE,
    INTERRUPTED,
    MODULE,
    QUIET_PROGRESS,
    SUMMARY_HEADING,
    correlated,
)

_SETUP = "setup"
_FIRST = "tests/test_first.py::test_same"
_SECOND = "tests/test_second.py::test_same"
_BOTH = "tests/test_fixture.py::test_both"
_SETUP_NODE = f"{MODULE}::test_setup"
_FAILS = "assert 1 == 2"

# Tests of two modules sharing a name, and their fixtures, each taking the
# section pytest printed in its turn; a test failing in setup and teardown
# both, each line taking the phase whose section raised its error, cut short
# or not, whatever order the lines stand in; and failures `--tb=line` printed
# untitled going to their lines in turn, while a fixture's error keeps its
# section.
_SAME_TITLES = (
    "__________________________________ test_same ___________________________________\n"
    "E       ValueError: first module failed\n"
    "__________________________________ test_same ___________________________________\n"
    f"E       TypeError: second module failed\n{SUMMARY_HEADING}FAILED {_FIRST}\nFAILED {_SECOND}"
)
_SAME_FIXTURES = (
    "___ ERROR at setup of test_same ___\nE       RuntimeError: first fixture failed\n"
    f"___ ERROR at setup of test_same ___\nE       KeyError: second fixture failed\nERROR {_FIRST}\nERROR {_SECOND}"
)
_TEARDOWN_CUT = SummaryLine(_BOTH, "ValueError: teardown ex...", errored=True)
_SETUP_SAID = SummaryLine(_BOTH, "RuntimeError: setup exploded", errored=True)
_BOTH_PHASES = (
    "___ ERROR at setup of test_both ___\nE       RuntimeError: setup exploded\n"
    "___ ERROR at teardown of test_both ___\nE       ValueError: teardown exploded\n"
    f"ERROR {_BOTH} - {_TEARDOWN_CUT.error}\nERROR {_BOTH} - {_SETUP_SAID.error}"
)
_LINE_TRACEBACKS = (
    f"{ERRORS_HEADING}___ ERROR at setup of test_setup ___\nE   RuntimeError: fixture exploded\n"
    f"{FAILURES_HEADING}E   RuntimeError: the supplied diagnostic\n"
    f"/tmp/run/{MODULE}:9: RuntimeError: the supplied diagnostic\n"
    "E   KeyError: 'deep in a helper'\n/tmp/run/tests/helper_mod.py:2: KeyError: 'deep in a helper'\n"
    f"{SUMMARY_HEADING}ERROR {_SETUP_NODE}\nFAILED {MODULE}::test_check\nFAILED {MODULE}::test_helper"
)

# Two tests whose IDs overlap -- the second's parameter holding the first's
# ID, the dash, and text of the first's message -- each line's ID the one
# whose section, or line traceback, shows the exception its message opens,
# pytest's ellipsis closing a message it cut short aside; a message ending on
# a bracket, an ID running on to the line's end and its empty message showing
# nothing; and two lines alike, each taking the first section left.
_SHORT = SummaryLine("test_p.py::test_v[a]", "ValueError: b] - RuntimeError: first")
_LONG = SummaryLine("test_p.py::test_v[a] - ValueError: b]", "RuntimeError: second")
_OVERLAPPING_SUMMARY = (
    f"{SUMMARY_HEADING}FAILED {_SHORT.node} - {_SHORT.error}\n"
    f"FAILED {_LONG.node} - {_LONG.error}"
)
_OVERLAPPING_SECTIONS = (
    f"{FAILURES_HEADING}___ test_v[a] ___\nE           {_SHORT.error}\n"
    f"___ test_v[a] - ValueError: b] ___\nE       {_LONG.error}\n"
)
_OVERLAPPING = f"{_OVERLAPPING_SECTIONS}{_OVERLAPPING_SUMMARY}"
_OVERLAPPING_LINES = (
    f"{FAILURES_HEADING}E   {_SHORT.error}\n/tmp/run/test_p.py:5: {_SHORT.error}\n"
    f"E   {_LONG.error}\n/tmp/run/test_p.py:6: {_LONG.error}\n{_OVERLAPPING_SUMMARY}"
)
_SHORT_CUT = SummaryLine(_SHORT.node, "ValueError: b] - RuntimeError: fi...")
_OVERLAPPING_CUT = f"{_OVERLAPPING_SECTIONS}{_OVERLAPPING_SUMMARY.replace(_SHORT.error, _SHORT_CUT.error)}"
_BRACKETED = (
    f"{FAILURES_HEADING}E   ValueError: got [y]\n/tmp/run/test_p.py:3: ValueError: got [y]\n"
    f"{SUMMARY_HEADING}FAILED test_p.py::test_v[x] - ValueError: got [y]"
)
_IDENTICAL_SUMMARY = "FAILED test_probe.py::test_p[x] - ValueError: [y] - TypeError: boom"
_BOOM = SummaryLine("test_probe.py::test_p[x] - ValueError: [y]", "TypeError: boom")
_BOOM_SECTION = "___ test_p[x] - ValueError: [y] ___\nE   TypeError: boom\n"
_IDENTICAL = (
    f"{FAILURES_HEADING}___ test_p[x] ___\nE   ValueError: [y] - TypeError: boom\n{_BOOM_SECTION}"
    f"{SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n{_IDENTICAL_SUMMARY}"
)
_SPLIT = "ValueError: [y] - TypeError: boom"
_SPLIT_FIRST = SummaryLine("test_probe.py::test_p[x]", _SPLIT)

# Only a section of its own run names a line's ID or goes to it: a run
# printing none borrows none of the next run's.
_BORROWED = (
    f"{QUIET_PROGRESS}{SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n1 failed in 0.00s\n\n"
    f"{QUIET_PROGRESS}{FAILURES_HEADING}{_BOOM_SECTION}{SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n1 failed in 0.01s"
)
_UNTRACED_RUN = (
    f"E                                                                        [100%]\n{SUMMARY_HEADING}"
    f"ERROR {_FIRST}\n1 error in 0.01s\n"
    ".E                                                                       [100%]\n"
    f"{ERRORS_HEADING}___ ERROR at teardown of test_same ___\nE   ValueError: second run teardown failure\n"
    f"{SUMMARY_HEADING}ERROR {_FIRST}\n1 passed, 1 error in 0.01s"
)

# A title names a test by its classes dotted and its parameters as they are,
# a separator they hold included, so the ID it names is sure; each subtest
# takes the section its test's name and description title; a test's section
# ended CRLF takes the exception below a frame separator; and one in Python's
# own form takes the exception it ends on, a marked line's shape in its message
# aside, as exception groups' line tracebacks do, below what pytest captured
# -- one holding one exception giving that exception's repr -- a later
# failure's taking its own; native assertions whose messages a summary
# gives without `AssertionError: ` name tests whose IDs overlap; a strict
# XPASS, which `--tb=line` prints as its mark and reason, taking the section
# that mark is, beside a group holding one exception, its test's parameter
# holding the dash and an exception's name, named by the line traceback
# giving that exception's repr in full -- `--tb=no` printing none, the XPASS
# takes none, and the group's line says where its ID ends is unsure; and
# strict XPASSes whose IDs leave pytest no room for their mark, each taking
# its own -- pytest 9 printing each mark above what it captured and again in
# its line traceback's stead, two alike in turn, pytest 8 that line alone, cut
# at fifty characters or alike, its line traceback bare below them saying so
# -- a later failure taking its own line traceback.
_SEPARATED = SummaryLine("tests/test_fixture.py::TestK::test_m[a::b]", "AssertionError: got [b] - KeyError: c")
_SHAPED = SummaryLine("tests/test_x.py::test_x[a]", "AssertionError: got [b] - KeyError: 'c'")
_FINAL = SummaryLine("test_chain.py::test_chain", "ValueError: final failure")
_CRLF_CHAINED = (
    f"{FAILURES_HEADING}___ test_chain ___\nE   KeyError: x\n"
    f"During handling of the above exception, another exception occurred:\n_ _ _ _ _\nE   {_FINAL.error}\n"
    f"{SUMMARY_HEADING}FAILED {_FINAL.node} - {_FINAL.error}"
).replace("\n", "\r\n")
_NATIVE = SummaryLine("test_native.py::test_native", "")
_NATIVE_MARKED = (
    f"{FAILURES_HEADING}___ test_native ___\nTraceback (most recent call last):\n"
    '  File "test_native.py", line 2, in test_native\nRuntimeError: actual failure\n'
    f"E   ValueError: text in the exception message\n{SUMMARY_HEADING}FAILED {_NATIVE.node}"
)
_GROUPS_SUMMARISED = (
    f"{GROUPS_LINE}{SUMMARY_HEADING}FAILED test_probe.py::test_group - ValueError('inner') [single exception in E...\n"
    "FAILED test_probe.py::test_multi - ExceptionGroup: grouped failure (2 sub-exc...\n"
    "FAILED test_probe.py::test_later - RuntimeError: later failure\n3 failed in 0.01s"
)
_ASSERTED = "assert [1, 2] == [3, 4]"
_ASSERTED_SHORT = SummaryLine("test_probe.py::test_value[a]", _ASSERTED)
_ASSERTED_LONG = SummaryLine(f"test_probe.py::test_value[a] - {_ASSERTED}", _ASSERTED)
_NATIVE_OVERLAPPING = (
    f"{FAILURES_HEADING}___ test_value[a] ___\nTraceback (most recent call last):\nAssertionError: {_ASSERTED}\n"
    f"___ test_value[a] - {_ASSERTED} ___\nTraceback (most recent call last):\nAssertionError: {_ASSERTED}\n"
    f"{SUMMARY_HEADING}FAILED {_ASSERTED_SHORT.node} - {_ASSERTED}\nFAILED {_ASSERTED_LONG.node} - {_ASSERTED}"
)
_XPASS = SummaryLine("test_probe.py::test_xpass[case]", "[XPASS(strict)]")
_SINGLE = "ValueError('inner') [single exception in ExceptionGroup]"
_SINGLE_PARAMETERIZED = SummaryLine("test_probe.py::test_group[a] - ValueError: b]", _SINGLE)
_SINGLE_SUMMARY = (
    f"{SUMMARY_HEADING}FAILED {_XPASS.node} - {_XPASS.error} \n"
    f"FAILED {_SINGLE_PARAMETERIZED.node} - {_SINGLE}\n2 failed in 0.00s"
)
_SINGLE_LINE = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}[XPASS(strict)] \n[XPASS(strict)] \n"
    "  + Exception Group Traceback (most recent call last):\n"
    '  |   File "/tmp/run/test_probe.py", line 12, in test_group\n'
    '  |     raise ExceptionGroup("group", [ValueError("inner")])\n  | ExceptionGroup: group (1 sub-exception)\n'
    "  +-+---------------- 1 ----------------\n    | ValueError: inner\n    +------------------------------------\n"
    f"/tmp/run/test_probe.py:12: {_SINGLE}\n{_SINGLE_SUMMARY}"
)
_SINGLE_UNSURE = SummaryLine("test_probe.py::test_group[a]", f"ValueError: b] - {_SINGLE}", unsure=True)
_LONG_CASE = "x" * 100
_OTHER_CASE = "y" * 100
_XPASSED = SummaryLine(f"test_probe.py::test_xpass[{_LONG_CASE}]", "")
_XPASSED_OTHER = SummaryLine(f"test_probe.py::test_xpass[{_OTHER_CASE}]", "")
_XPASS_REASON = "[XPASS(strict)] expected to break"
_XPASS_CUT = "[XPASS(strict)] a reason long enough to pass the f"
_LATER = SummaryLine("test_probe.py::test_later", "RuntimeError: later failure")
_XPASSED_SUMMARY = (
    f"{SUMMARY_HEADING}FAILED {_XPASSED.node}\nFAILED {_XPASSED_OTHER.node}\n"
    f"FAILED {_LATER.node} - {_LATER.error}\n3 failed in 0.00s"
)
_XPASSED_TWICE = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}{_XPASS_REASON}\n"
    "----------------------------- Captured stdout call -----------------------------\n"
    f"printed by the xpass\n{_XPASS_REASON}\n{_XPASS_REASON}\n{_XPASS_REASON}\nE   {_LATER.error}\n"
    f"/tmp/run/test_probe.py:11: {_LATER.error}\n{_XPASSED_SUMMARY}"
)
_XPASSED_ONCE = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}{_XPASS_REASON}\n{_XPASS_CUT}\n"
    f"/tmp/run/test_probe.py:11: {_LATER.error}\n{_XPASSED_SUMMARY}"
)
_LATER_TAKEN = (_LATER, "", _LATER.error)
_SUBTESTS = (
    "___ TestCase.test_values (value=1) ___\nE               AssertionError: 1 != 0\n"
    "___ TestCase.test_values (value=2) ___\nE               AssertionError: 2 != 0\n"
    f"{SUMMARY_HEADING}SUBFAILED(value=2) {MODULE}::TestCase::test_values\n"
    f"SUBFAILED(value=1) {MODULE}::TestCase::test_values"
)

_TAKEN = (
    (_SAME_TITLES, [
        (SummaryLine(_FIRST, ""), "", "ValueError: first module failed"),
        (SummaryLine(_SECOND, ""), "", "TypeError: second module failed"),
    ]),
    (_SAME_FIXTURES, [
        (SummaryLine(_FIRST, "", errored=True), _SETUP, "RuntimeError: first fixture failed"),
        (SummaryLine(_SECOND, "", errored=True), _SETUP, "KeyError: second fixture failed"),
    ]),
    (_BOTH_PHASES, [
        (_TEARDOWN_CUT, "teardown", "ValueError: teardown exploded"),
        (_SETUP_SAID, _SETUP, _SETUP_SAID.error),
    ]),
    (_LINE_TRACEBACKS, [
        (SummaryLine(_SETUP_NODE, "", errored=True), _SETUP, "RuntimeError: fixture exploded"),
        (SummaryLine(f"{MODULE}::test_check", ""), "", "RuntimeError: the supplied diagnostic"),
        (SummaryLine(f"{MODULE}::test_helper", ""), "", "KeyError: 'deep in a helper'"),
    ]),
    (_OVERLAPPING, [(_SHORT, "", _SHORT.error), (_LONG, "", _LONG.error)]),
    (_OVERLAPPING_LINES, [(_SHORT, "", _SHORT.error), (_LONG, "", _LONG.error)]),
    (_OVERLAPPING_CUT, [(_SHORT_CUT, "", _SHORT.error), (_LONG, "", _LONG.error)]),
    (_BRACKETED, [(SummaryLine("test_p.py::test_v[x]", "ValueError: got [y]"), "", "ValueError: got [y]")]),
    (_IDENTICAL, [(_SPLIT_FIRST, "", _SPLIT), (_BOOM, "", _BOOM.error)]),
    (_BORROWED, [
        (SummaryLine("test_probe.py::test_p[x]", _SPLIT, unsure=True), "", None),
        (_BOOM, "", _BOOM.error),
    ]),
    (_UNTRACED_RUN, [
        (SummaryLine(_FIRST, "", errored=True), "", None),
        (SummaryLine(_FIRST, "", errored=True), "teardown", "ValueError: second run teardown failure"),
    ]),
    (f"___ TestK.test_m[a::b] ___\nFAILED {_SEPARATED.node} - {_SEPARATED.error}", [(_SEPARATED, "", "")]),
    (f"___ test_x[a] ___\nFAILED {_SHAPED.node} - {_SHAPED.error}", [(_SHAPED, "", "")]),
    (_SUBTESTS, [
        (SummaryLine(f"{MODULE}::TestCase::test_values", "", subtest="(value=2)"), "", "AssertionError: 2 != 0"),
        (SummaryLine(f"{MODULE}::TestCase::test_values", "", subtest="(value=1)"), "", "AssertionError: 1 != 0"),
    ]),
    (_CRLF_CHAINED, [(_FINAL, "", _FINAL.error)]),
    (_NATIVE_MARKED, [(_NATIVE, "", "RuntimeError: actual failure")]),
    (_GROUPS_SUMMARISED, [
        (SummaryLine("test_probe.py::test_group", "ValueError('inner') [single exception in E..."), "", (
            "ValueError('inner') [single exception in ExceptionGroup]"
        )),
        (SummaryLine("test_probe.py::test_multi", "ExceptionGroup: grouped failure (2 sub-exc..."), "", (
            "ExceptionGroup: grouped failure (2 sub-exceptions)"
        )),
        (SummaryLine("test_probe.py::test_later", "RuntimeError: later failure"), "", "RuntimeError: later failure"),
    ]),
    (_NATIVE_OVERLAPPING, [
        (_ASSERTED_SHORT, "", f"AssertionError: {_ASSERTED}"),
        (_ASSERTED_LONG, "", f"AssertionError: {_ASSERTED}"),
    ]),
    (_SINGLE_LINE, [(_XPASS, "", _XPASS.error), (_SINGLE_PARAMETERIZED, "", _SINGLE)]),
    (f"{QUIET_PROGRESS}{_SINGLE_SUMMARY}", [(_XPASS, "", None), (_SINGLE_UNSURE, "", None)]),
    (_XPASSED_TWICE, [(_XPASSED, "", _XPASS_REASON), (_XPASSED_OTHER, "", _XPASS_REASON), _LATER_TAKEN]),
    (_XPASSED_ONCE, [(_XPASSED, "", _XPASS_REASON), (_XPASSED_OTHER, "", _XPASS_CUT), _LATER_TAKEN]),
    (
        _XPASSED_ONCE.replace(_XPASS_CUT, _XPASS_REASON),
        [(_XPASSED, "", _XPASS_REASON), (_XPASSED_OTHER, "", _XPASS_REASON), _LATER_TAKEN],
    ),
)

# Collections: a module pytest could not import; a class it could not
# collect, its path's section saying so or its run's interruption; a node no
# section or interruption says anything of; one module failing in two runs;
# an interruption beside a run whose setup error printed no section; a
# doctest's text file, its error cut short or not given, its name holding the
# dash too; a fixture's error saying collection was interrupted, which no
# banner does; a run printed with `-rN`, its interruption's banner right above
# its statistics, or none where it went on past its collection errors -- its
# traceback marked, in Python's own form, or above what pytest captured --
# below which a `-q --tb=no` run opens past a blank line on its summary's
# heading, taking none of its sections; and a collection its section titles
# relative to pytest's root and its line names relative to where pytest ran,
# either the longer -- or another module ending on its name.
_NOWHERE = "ModuleNotFoundError: No module named 'nowhere'"
_UNCOLLECTED = (
    f"{ERRORS_HEADING}__________________________ ERROR collecting tests/test_b.py __________________________\n"
    f"ImportError while importing test module '/repo/tests/test_b.py'.\nE   {_NOWHERE}\n"
    f"{SUMMARY_HEADING}ERROR tests/test_b.py\n{INTERRUPTED}"
)
_CLASS = SummaryLine("tests/test_collector.py::TestBroken", "", errored=True)
_CLASS_SECTION = "___ ERROR collecting tests/test_collector.py ___\nE   RuntimeError: class construction exploded"
_UNSECTIONED = SummaryLine(_SETUP_NODE, "KeyError: 'k'", errored=True)
_COLLECTED = SummaryLine("test_collection_long_name_long_name_long_name_long_name_long_name.py", "", errored=True)
_COLLECTED_RUN = (
    f"{ERRORS_HEADING}___ ERROR collecting {_COLLECTED.node} ___\nE   {{}}\n"
    f"{SUMMARY_HEADING}ERROR {_COLLECTED.node}\n{INTERRUPTED}\n1 error in 0.01s"
)
_COLLECTED_TWICE = "\n".join(map(_COLLECTED_RUN.format, ("ValueError: one", "TypeError: two")))
_INTERRUPTED_BESIDE = (
    f"{_COLLECTED_RUN.format('ValueError: one')}\n"
    f"E                                                                        [100%]\n{SUMMARY_HEADING}"
    f"ERROR {_UNSECTIONED.node} - {_UNSECTIONED.error}\n1 error in 0.01s"
)
_DOCTEST = SummaryLine("sample.txt", "ValueError: line 2 of the docstring for sample.txt lacks b...", errored=True)
_DOCTEST_RAISED = "ValueError: line 2 of the docstring for sample.txt lacks blank after ..."
_DOCTEST_SECTIONED = (
    f"{ERRORS_HEADING}___ ERROR collecting sample.txt ___\nE   {_DOCTEST_RAISED}\n"
    f"{SUMMARY_HEADING}ERROR sample.txt - {_DOCTEST.error}\n{INTERRUPTED}\n1 error in 0.11s"
)
_SPACED_DOCTEST = f"{SUMMARY_HEADING}ERROR sample spaced.txt\n{INTERRUPTED}\n1 error in 0.11s"
_DASHED_DOCTEST = (
    f"{ERRORS_HEADING}___ ERROR collecting sample - spaced.txt ___\nE   ValueError: malformed doctest\n"
    f"{SUMMARY_HEADING}ERROR sample - spaced.txt\n{INTERRUPTED}\n1 error in 0.12s"
)
_DASHED_TAKEN = (SummaryLine("sample - spaced.txt", "", errored=True), COLLECTION, "ValueError: malformed doctest")
_SAID_INTERRUPTED = SummaryLine("t.py::test_p", "RuntimeError: Interrupted: 1 error during collection", errored=True)
_INTERRUPTION_SAID = (
    "E                                                                        [100%]\n"
    f"{SUMMARY_HEADING}ERROR {_SAID_INTERRUPTED.node} - {_SAID_INTERRUPTED.error}\n1 error in 0.00s"
)
_UNSUMMARISED_THEN_UNTRACED = (
    f"{ERRORS_HEADING}___ ERROR collecting test_probe.py ___\nE   RuntimeError: first run\n{INTERRUPTED}\n"
    f"1 error in 0.07s\n{SUMMARY_HEADING}ERROR test_probe.py - RuntimeError: second run\n{INTERRUPTED}\n"
    "1 error in 0.07s"
)
_CONTINUED = (
    f"{ERRORS_HEADING}________________________ ERROR collecting test_probe.py ________________________\n"
)
_UNTRACED_SECOND = f"1 error in 0.01s\n\n{SUMMARY_HEADING}ERROR test_probe.py - ValueError: second\n1 error in 0.00s"
_CONTINUED_CAPTURED = (
    "E   ValueError: first\n----------------------------- Captured stdout call -----------------------------\n"
    "captured text\n"
)
_CONTINUED_TRACEBACKS = (
    'test_probe.py:1: in <module>\n    raise ValueError("first")\nE   ValueError: first\n',
    'Traceback (most recent call last):\n  File "test_probe.py", line 1, in <module>\nValueError: first\n',
    _CONTINUED_CAPTURED,
)
_ROOTED = "sub/test_broken.py"
_MISSING = "ModuleNotFoundError: No module named 'missing_dependency'"
_ROOTED_SECTION = f"{ERRORS_HEADING}___ ERROR collecting {_ROOTED} ___\nE   {_MISSING}\n{SUMMARY_HEADING}"
_COLLECTIONS = (
    (_UNCOLLECTED, [(SummaryLine("tests/test_b.py", "", errored=True), COLLECTION, _NOWHERE)], []),
    (f"{_CLASS_SECTION}\nERROR {_CLASS.node}", [(_CLASS, COLLECTION, "RuntimeError: class construction exploded")], []),
    (f"ERROR {_CLASS.node}\n{INTERRUPTED}", [(_CLASS, COLLECTION, "")], []),
    (f"ERROR {_UNSECTIONED.node} - {_UNSECTIONED.error}", [(_UNSECTIONED, "", None)], []),
    (_COLLECTED_TWICE, [(_COLLECTED, COLLECTION, "ValueError: one"), (_COLLECTED, COLLECTION, "TypeError: two")], []),
    (_INTERRUPTED_BESIDE, [(_COLLECTED, COLLECTION, "ValueError: one"), (_UNSECTIONED, "", None)], []),
    (_DOCTEST_SECTIONED, [(_DOCTEST, COLLECTION, _DOCTEST_RAISED)], []),
    (_SPACED_DOCTEST, [(SummaryLine("sample spaced.txt", "", errored=True), COLLECTION, "")], []),
    (_DASHED_DOCTEST, [_DASHED_TAKEN], []),
    (_INTERRUPTION_SAID, [(_SAID_INTERRUPTED, "", None)], []),
    (
        _UNSUMMARISED_THEN_UNTRACED,
        [(SummaryLine("test_probe.py", "RuntimeError: second run", errored=True), COLLECTION, "")],
        [("ERROR collecting test_probe.py", "RuntimeError: first run")],
    ),
    *(
        (
            f"{_CONTINUED}{traceback}{_UNTRACED_SECOND}",
            [(SummaryLine("test_probe.py", "ValueError: second", errored=True), "", None)],
            [("ERROR collecting test_probe.py", "ValueError: first")],
        )
        for traceback in _CONTINUED_TRACEBACKS
    ),
    *(
        (
            f"{_ROOTED_SECTION}ERROR {spelled}\n{INTERRUPTED}",
            [(SummaryLine(spelled, "", errored=True), COLLECTION, raised)],
            left,
        )
        for spelled, raised, left in (
            (f"../../proj/{_ROOTED}", _MISSING, []),
            ("test_broken.py", _MISSING, []),
            ("other/test_broken.py", "", [(f"ERROR collecting {_ROOTED}", _MISSING)]),
        )
    ),
)

# What no summary line reports: a summary leaving a failure out (`-rE`), or
# printed with none (`-rN`), its setup's, teardown's, and test's sections
# left; a collection only its section names; a doctest's section its line,
# naming it otherwise, does not take; a conftest or a plugin pytest could
# not load before running any test; and a run printed with `-rN` ending on
# what it captured from a test, or on a collection's traceback in Python's
# own form, a runner's text below its statistics, whose section no later
# run's line takes -- the next run opening on its progress, another run past
# more text below that, or opening past a blank line on its summary's heading.
_PHASES = (
    "E.EF                                                                     [100%]\n"
    f"{ERRORS_HEADING}___ ERROR at setup of test_setup ___\nE   RuntimeError: fixture exploded\n"
    "___ ERROR at teardown of test_teardown ___\nE   KeyError: 'teardown broke'\n"
    f"{FAILURES_HEADING}___ test_fails ___\nE   {_FAILS}\n"
)
_SETUP_LEFT = ("ERROR at setup of test_setup", "RuntimeError: fixture exploded")
_TEARDOWN_LEFT = ("ERROR at teardown of test_teardown", "KeyError: 'teardown broke'")
_FAILS_LEFT = ("test_fails", _FAILS)
_ERRORS_ONLY = f"{_PHASES}{SUMMARY_HEADING}ERROR test_probe.py::test_setup\n1 failed, 1 passed, 2 errors in 0.01s"
_FAILURES_ONLY = f"{_PHASES}{SUMMARY_HEADING}FAILED test_probe.py::test_fails - {_FAILS}\n1 failed in 0.01s"
_UNSUMMARISED_COLLECTION = (
    f"{ERRORS_HEADING}___ ERROR collecting test_broken.py ___\nE   {_NOWHERE}\n{INTERRUPTED}\n1 error in 0.07s"
)
_DOCTEST_TITLED = (
    f"{FAILURES_HEADING}___ [doctest] sample.txt ___\n001 >>> 1\n/tmp/run/sample.txt:1: DocTestFailure\n"
    f"{SUMMARY_HEADING}FAILED sample.txt::sample.txt\n1 failed in 0.01s"
)
_CONFTEST = "ImportError while loading conftest '/tmp/run/conftest.py'."
_PLUGIN = 'ImportError: Error importing plugin "missing_plugin": No module named \'missing_plugin\''
_UNLOADED = "ModuleNotFoundError: No module named 'x'"
_RETRIED = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "__________________________________ test_same ___________________________________\n"
    "E   ValueError: first run\n----------------------------- Captured stdout call -----------------------------\n"
    "normal captured text\n1 failed in 0.01s\nRetrying with --tb=no\n"
)
_SAME_LEFT = ("test_same", "ValueError: first run")
_RETRY = SummaryLine("tests/test_same.py::test_same", "ValueError: second run")
_RETRY_AGAIN = SummaryLine("tests/test_same.py::test_same", "ValueError: third run")
_RETRY_UNCOLLECTED = SummaryLine("tests/test_same.py", "ValueError: second run", errored=True)
_RETRIED_UNTRACED = (
    f"{_RETRIED}{QUIET_PROGRESS}{SUMMARY_HEADING}FAILED {_RETRY.node} - {_RETRY.error}\n1 failed in 0.01s\n"
)
_RETRIED_TWICE = (
    f"{_RETRIED_UNTRACED}Retrying once more\n{QUIET_PROGRESS}{SUMMARY_HEADING}"
    f"FAILED {_RETRY_AGAIN.node} - {_RETRY_AGAIN.error}\n1 failed in 0.01s"
)
_RETRIED_UNCOLLECTED = (
    f"{ERRORS_HEADING}___ ERROR collecting tests/test_same.py ___\nTraceback (most recent call last):\n"
    '  File "tests/test_same.py", line 1, in <module>\nValueError: first run\n1 error in 0.01s\n'
    f"Retrying with --tb=no\n\n{SUMMARY_HEADING}ERROR {_RETRY_UNCOLLECTED.node} - {_RETRY_UNCOLLECTED.error}\n"
    "1 error in 0.01s"
)
_LEFT = (
    (_ERRORS_ONLY, [
        (SummaryLine("test_probe.py::test_setup", "", errored=True), _SETUP, "RuntimeError: fixture exploded"),
    ], [_TEARDOWN_LEFT, _FAILS_LEFT]),
    (f"{_PHASES}1 failed, 1 passed, 2 errors in 0.01s", [], [_SETUP_LEFT, _TEARDOWN_LEFT, _FAILS_LEFT]),
    (_FAILURES_ONLY, [(SummaryLine("test_probe.py::test_fails", _FAILS), "", _FAILS)], [_SETUP_LEFT, _TEARDOWN_LEFT]),
    (_UNSUMMARISED_COLLECTION, [], [("ERROR collecting test_broken.py", _NOWHERE)]),
    (_DOCTEST_TITLED, [(SummaryLine("sample.txt::sample.txt", ""), "", None)], [("[doctest] sample.txt", "")]),
    (f"{_CONFTEST}\nE   {_UNLOADED}", [], [(_CONFTEST, _UNLOADED)]),
    (f"Traceback (most recent call last):\n{_PLUGIN}", [], [(_PLUGIN, _PLUGIN)]),
    (_RETRIED_UNTRACED, [(_RETRY, "", None)], [_SAME_LEFT]),
    (_RETRIED_TWICE, [(_RETRY, "", None), (_RETRY_AGAIN, "", None)], [_SAME_LEFT]),
    (_RETRIED_UNCOLLECTED, [(_RETRY_UNCOLLECTED, "", None)], [("ERROR collecting tests/test_same.py", _SAME_LEFT[1])]),
)


class PytestLookupsTest(unittest.TestCase):
    """Each summary line takes the section it reports, and what none takes is left."""

    def test_lines_take_their_sections(self) -> None:
        for output, taken in _TAKEN:
            with self.subTest(output=output):
                self.assertEqual(correlated(output), (taken, []))

    def test_lines_take_their_collections(self) -> None:
        for output, taken, left in _COLLECTIONS:
            with self.subTest(output=output):
                self.assertEqual(correlated(output), (taken, left))

    def test_sections_no_line_takes_are_left(self) -> None:
        for output, taken, left in _LEFT:
            with self.subTest(output=output):
                self.assertEqual(correlated(output), (taken, left))


if __name__ == "__main__":
    unittest.main()
