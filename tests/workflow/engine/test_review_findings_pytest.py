# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""pytest's output read for the sections it printed and the runs its summary lines report on.

A section reads with its title and the exception it shows: the first line set
out least in its last run of marked lines, else where Python's own traceback
ends -- an exception group's at its rail's margin -- and with `--tb=line`
each failure's crash line is a section titled by nothing. Nothing pytest
captured from a test is read as its own, nor a run a test printed, nor what
pytest reports under a heading for what did not fail; and each summary line,
or error refusing a run, is read with the run it stands in.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine.review_findings_pytest import PytestOutput, Section
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

_SESSION_HEADING = "============================= test session starts ==============================\n"
_CAPTURE_RULE = "----------------------------- Captured stdout call -----------------------------\n"
_STATS = "============================== 1 failed in 0.01s ===============================\n"
_OUTER_STATS = "============================== 2 failed in 0.02s ==============================="
_TEST_FIRST = "test_first"
_TEST_FAILURE = "test_failure"

# Sections as pytest prints them: a fixture's assertion over its explanation
# and diff hint, a line marked blank among them; a syntax error below its
# source set out further; an exception raised handling another, its lines
# ended CRLF too, a frame separator's carriage return no title, nor a line of
# spaced dashes' a rule; a local named `E` `--showlocals` printed; a long
# title padded by one underscore each side over a frame separator; Python's
# own tracebacks `--tb=native` prints, one chained, one whose exception's
# message runs on in a marked line's shape; an exception group of failed
# finalizers, and one an exception pytest marks was raised from; `--tb=line`
# crash lines -- one in a helper, one below an explanation holding a colon a
# blank follows and a diff holding a line of their shape set out further,
# ones naming a path holding blanks or a colon -- beside a fixture's section,
# one quoted set in with no marked line above it, and exception groups'
# below what was captured, one holding one exception and one two, above a
# later failure's; a conftest and a plugin
# pytest could not load, alone and below the statistics closing a run printed
# with no summary; and a doctest's section marking no line.
_DIFF_HINT = (
    "___________________________ ERROR at setup of test_x ___________________________\n"
    "E       assert [1, 2] == [3, 4]\nE         \nE         At index 0 diff: 1 != 3\n"
    "E         Use -v to get more diff"
)
_SYNTAX = (
    "_______________________ ERROR collecting tests/test_syntax.py _______________________\n"
    'E     File "/tmp/run/tests/test_syntax.py", line 1\nE       def broken(:\nE                  ^\n'
    "E   SyntaxError: '(' was never closed"
)
_CHAINED = (
    "__________________________________ test_chain __________________________________\n"
    "E           KeyError: 'x'\nDuring handling of the above exception, another exception occurred:\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ \n"
    "E           ValueError: chained failure"
)
_CHAINED_SECTION = ("test_chain", "ValueError: chained failure")
_DASHES_CRLF = "___ test_dashes ___\r\nE   ValueError: first\r\n- - - - -\r\nE   TypeError: last\r"
_SHOWN_LOCALS = (
    "_________________________________ test_failure _________________________________\n\n"
    '    def test_failure():\n        E = "local value"\n>       assert value == 1\n'
    f"E       assert 0 == 1\n\nE          = 'local value'\nvalue      = 0\n\n{MODULE}:4: AssertionError"
)
_LONG_TITLE = "test_value[a_very_long_parameter_value_with_separators_left] - Error: right]"
_LONG = (
    f"_ {_LONG_TITLE} _\n    def test_value(case):\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n"
    "E       assert 0 == 1"
)
_NATIVE = (
    "__________________________________ test_check __________________________________\n"
    f'Traceback (most recent call last):\n  File "/tmp/run/{MODULE}", line 9, in test_check\n'
    '    raise RuntimeError("the supplied diagnostic")\nRuntimeError: the supplied diagnostic\n'
    "__________________________________ test_chain __________________________________\n"
    "Traceback (most recent call last):\n    {}[\"x\"]\nKeyError: 'x'\n\n"
    "During handling of the above exception, another exception occurred:\n\n"
    "Traceback (most recent call last):\n    raise ValueError(\"chained failure\")\nValueError: chained failure"
)
_NATIVE_MARKED = (
    "_________________________________ test_native __________________________________\n"
    'Traceback (most recent call last):\n  File "test_native.py", line 2, in test_native\n'
    "RuntimeError: actual failure\nE   ValueError: text in the exception message"
)
_GROUP_RAISED = 'ExceptionGroup: errors while tearing down fixture "broken" of <Function test_group> (2 sub-exceptions)'
_GROUPED = (
    "_______________________ ERROR at teardown of test_group ________________________\n"
    "  + Exception Group Traceback (most recent call last):\n"
    f"  |     raise BaseExceptionGroup(msg, exceptions[::-1])\n  | {_GROUP_RAISED}\n"
    "  +-+---------------- 1 ----------------\n"
    "    | Traceback (most recent call last):\n    |     raise ValueError('first finalizer')\n"
    "    | ValueError: first finalizer\n"
    "    +---------------- 2 ----------------\n"
    "    | Traceback (most recent call last):\n    | TypeError: second finalizer\n"
    "    +------------------------------------"
)
_GROUP_CAUSED = (
    "__________________________________ test_mixed __________________________________\n"
    "  + Exception Group Traceback (most recent call last):\n  | ExceptionGroup: group cause (1 sub-exception)\n"
    "  +-+---------------- 1 ----------------\n    | ValueError: inner\n    +------------------------------------\n\n"
    "The above exception was the direct cause of the following exception:\n\n"
    '    def test_mixed():\n>       raise RuntimeError("final") from group\nE       RuntimeError: final'
)
_LINE_TRACEBACKS = (
    f"{ERRORS_HEADING}_________________________ ERROR at setup of test_setup _________________________\n"
    f"E   RuntimeError: fixture exploded\n{FAILURES_HEADING}"
    f"E   RuntimeError: the supplied diagnostic\n/tmp/run/{MODULE}:9: RuntimeError: the supplied diagnostic\n"
    "E   KeyError: 'deep in a helper'\n/tmp/run/tests/helper_mod.py:2: KeyError: 'deep in a helper'\n"
    "E   assert [1, 2] == [3, 4]\n      \n      At index 0 diff: 1 != 3\n      Full diff: a:12: b\n"
    "      -     'pkg/foo.py:123: expected',\n"
    f"/tmp/run/{MODULE}:18: assert [1, 2] == [3, 4]\n"
    "E   RuntimeError: failure 0\n/tmp/run/test spaced_module.py:2: RuntimeError: failure 0\n"
    "E   KeyError: 'colon'\n/tmp/run/test:probe.py:2: KeyError: 'colon'"
)
_SINGLE_GROUP = "ValueError('inner') [single exception in ExceptionGroup]"
_LATER = "RuntimeError: later failure"
_CONFTEST = "ImportError while loading conftest '/tmp/run/conftest.py'."
_CONFTEST_UNLOADED = (
    f"{_CONFTEST}\n/tmp/run/conftest.py:1: in <module>\n    import missing_dependency\n"
    "E   ModuleNotFoundError: No module named 'missing_dependency'"
)
_PLUGIN = 'ImportError: Error importing plugin "missing_plugin": No module named \'missing_plugin\''
_PLUGIN_UNIMPORTED = (
    "Traceback (most recent call last):\n"
    '  File "/venv/lib/python3.12/site-packages/_pytest/config/__init__.py", line 913, in import_plugin\n'
    f"    mod = importlib.import_module(importspec)\n{_PLUGIN}"
)
_UNSUMMARISED_FIRST = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "__________________________________ test_first __________________________________\n"
    "E   ValueError: first failure\n1 failed in 0.01s\n"
)
_FIRST_LEFT = ("test_first", "ValueError: first failure")
_MISSING = "ModuleNotFoundError: No module named 'missing_dependency'"
_DOCTEST = (
    f"{FAILURES_HEADING}____________________________ [doctest] sample.txt _____________________________\n"
    "001 >>> 1\nExpected:\n    2\nGot:\n    1\n\n/tmp/run/sample.txt:1: DocTestFailure"
)
_SECTIONS = (
    (_DIFF_HINT, [("ERROR at setup of test_x", "assert [1, 2] == [3, 4]")]),
    (_SYNTAX, [("ERROR collecting tests/test_syntax.py", "SyntaxError: '(' was never closed")]),
    (_CHAINED, [_CHAINED_SECTION]),
    (_CHAINED.replace("\n", "\r\n"), [_CHAINED_SECTION]),
    (_DASHES_CRLF, [("test_dashes", "TypeError: last")]),
    (_SHOWN_LOCALS, [(_TEST_FAILURE, "assert 0 == 1")]),
    (_LONG, [(_LONG_TITLE, "assert 0 == 1")]),
    (_NATIVE, [("test_check", "RuntimeError: the supplied diagnostic"), ("test_chain", "ValueError: chained failure")]),
    (_NATIVE_MARKED, [("test_native", "RuntimeError: actual failure")]),
    (_GROUPED, [("ERROR at teardown of test_group", _GROUP_RAISED)]),
    (_GROUP_CAUSED, [("test_mixed", "RuntimeError: final")]),
    (_LINE_TRACEBACKS, [
        ("ERROR at setup of test_setup", "RuntimeError: fixture exploded"),
        ("", "RuntimeError: the supplied diagnostic"),
        ("", "KeyError: 'deep in a helper'"),
        ("", "assert [1, 2] == [3, 4]"),
        ("", "RuntimeError: failure 0"),
        ("", "KeyError: 'colon'"),
    ]),
    (f"   {FAILURES_HEADING}   /tmp/run/test_quoted.py:3: assert 0", [("", "assert 0")]),
    (_CONFTEST_UNLOADED, [(_CONFTEST, _MISSING)]),
    (_PLUGIN_UNIMPORTED, [(_PLUGIN, _PLUGIN)]),
    (GROUPS_LINE, [("", _SINGLE_GROUP), ("", "ExceptionGroup: grouped failure (2 sub-exceptions)"), ("", _LATER)]),
    (f"{_UNSUMMARISED_FIRST}{_CONFTEST_UNLOADED}", [(_CONFTEST, _MISSING), _FIRST_LEFT]),
    (f"{_UNSUMMARISED_FIRST}{_PLUGIN_UNIMPORTED}", [(_PLUGIN, _PLUGIN), _FIRST_LEFT]),
    (_DOCTEST, [("[doctest] sample.txt", "")]),
)

# Tests printing lines of pytest's own shapes, which it captured and prints
# below a rule: a marked line below a section's own; summary lines and what
# pytest prints failing to load a conftest or a plugin, above the short
# summary and with no short summary at all (`-rN`); with `--tb=line`, a crash
# line and a marked line above the crash line closing the capture, and a line
# giving the failure's exception set further in than its marked lines, above
# a crash line of the capture's own; and a title narrower than pytest pads
# its own.
_OUTER_FAILED = SummaryLine("tests/test_outer.py::test_outer", "RuntimeError: outer test failed")
_PRINTED_LINES = (
    "__________________________________ test_outer __________________________________\n"
    f"E       RuntimeError: outer test failed\n{_CAPTURE_RULE}"
    "FAILED tests/test_child.py::test_child - ValueError: simulated output\n"
    "ERROR tests/test_child.py - ImportError: simulated collection\n"
    f"{_CONFTEST}\nE   ModuleNotFoundError: No module named 'simulated'\n{_PLUGIN}\n"
)
_PRINTED_SUMMARISED = f"{_PRINTED_LINES}{SUMMARY_HEADING}FAILED {_OUTER_FAILED.node} - {_OUTER_FAILED.error}"
_PRINTED_MARKED = (
    "_________________________________ test_output __________________________________\n"
    f"E       RuntimeError: actual failure\n/tmp/run/{MODULE}:3: RuntimeError\n{_CAPTURE_RULE}"
    f"E   captured stdout is not the exception\n{SUMMARY_HEADING}FAILED {MODULE}::test_output"
)
_PRINTED_CRASH = (
    f"{FAILURES_HEADING}E   RuntimeError: actual failure\n{_CAPTURE_RULE}"
    "tests/helper.py:3: printed a crash-shaped line\nE   printed a marked line\n"
    f"/tmp/run/{MODULE}:4: RuntimeError: actual failure\nE   assert 1 == 2\n/tmp/run/{MODULE}:8: assert 1 == 2\n"
    f"{SUMMARY_HEADING}FAILED {MODULE}::test_output\nFAILED {MODULE}::test_second"
)
_ACTUAL = "RuntimeError: actual failure"
_PRINTED_INDENTED_CRASH = (
    f"{FAILURES_HEADING}E   {_ACTUAL}\n{_CAPTURE_RULE}  helper.py:1: {_ACTUAL}\nfake.py:2: ValueError: captured text\n"
    f"test_probe.py:4: {_ACTUAL}\n{SUMMARY_HEADING}FAILED test_probe.py::test_probe - {_ACTUAL}"
)
_PRINTED_TITLE = (
    f"{FAILURES_HEADING}__________________________________ test_first __________________________________\n"
    f"E       RuntimeError: actual first failure\n{_CAPTURE_RULE}"
    "___ test_second ___\nE   ValueError: captured text only\n"
    "_________________________________ test_second __________________________________\n"
    f"E       TypeError: actual second failure\n{SUMMARY_HEADING}"
    f"FAILED {MODULE}::test_first\nFAILED {MODULE}::test_second"
)

# Only the last short summary of a run is its own; a run a test printed is
# captured to its statistics, the outer run summarised or not (`-rN`), unless
# the test cut it short, which hides nothing below it; a run a test printed
# -- opening on its session's heading, or on `-q` progress letters a
# subtest's among them -- may title a section as the outer run does, closing
# on statistics counting subtests; a run printed with `-q -s` opens on the
# heading right below its progress letters, which carry no percentage, a line
# of their shape a test printed right above the outer run's summary hiding
# nothing; and runs a test printed, each captured in the one around it, each
# captured to its own statistics -- a `-q` run's later progress lines going
# on with its run -- the outer run's summary its own, and the next run's.
_OUTER_OPENING = (
    "__________________________________ test_outer __________________________________\n"
    f"E   RuntimeError: outer failure\n{_CAPTURE_RULE}"
)
_OUTER = (SummaryLine(f"{MODULE}::test_outer", ""), "", "RuntimeError: outer failure")
_PLAIN = (SummaryLine(f"{MODULE}::test_plain", ""), "", "assert 1 == 2")
_PRINTED_SUMMARY = (
    f"{_OUTER_OPENING}{SUMMARY_HEADING}FAILED nested/test_inner.py::test_inner - ValueError: only captured text\n"
    f"{SUMMARY_HEADING}FAILED {MODULE}::test_outer"
)
_NESTED_RUN = (
    f"{_OUTER_OPENING}{_SESSION_HEADING}collected 1 item\n\n"
    "test_inner.py F                                                          [100%]\n\n"
    f"{FAILURES_HEADING}E   ValueError: inner only\n/tmp/inner/test_inner.py:2: ValueError: inner only\n"
    f"{SUMMARY_HEADING}FAILED test_inner.py::test_inner - ValueError: inner only\n{_STATS}\n"
    "__________________________________ test_plain __________________________________\nE   assert 1 == 2\n"
)
_NESTED_SUMMARISED = (
    f"{_NESTED_RUN}{SUMMARY_HEADING}FAILED {MODULE}::test_outer\nFAILED {MODULE}::test_plain\n{_OUTER_STATS}"
)
_NESTED_UNSUMMARISED = f"{_NESTED_RUN}{_OUTER_STATS}"
_CUT_RUN = f"{_OUTER_OPENING}{_SESSION_HEADING}collected 1 item\n{SUMMARY_HEADING}FAILED {MODULE}::test_outer\n{_STATS}"
_NESTED_TITLES = (
    "______________________________ test_prints_child _______________________________\n"
    f"E   RuntimeError: outer first failure\n{_CAPTURE_RULE}{{opening}}"
    "__________________________________ test_same ___________________________________\n"
    f"E   ValueError: captured child failure\n{SUMMARY_HEADING}"
    "FAILED child/test_inner.py::test_same - ValueError: captured child failure\n"
    "======================== 1 failed, 1 subtests passed in 0.01s ========================\n"
    "__________________________________ test_same ___________________________________\n"
    f"E   TypeError: outer second failure\n{SUMMARY_HEADING}"
    f"FAILED {MODULE}::test_prints_child\nFAILED {MODULE}::test_same\n{_OUTER_STATS}"
)
_SUBTEST_PROGRESS = "uF                                                                       [100%]\n"
_NESTED_TITLES_TAKEN = (
    (SummaryLine(f"{MODULE}::test_prints_child", ""), "", "RuntimeError: outer first failure"),
    (SummaryLine(f"{MODULE}::test_same", ""), "", "TypeError: outer second failure"),
)

# What did not fail is read as nothing: sections `-rP --xfail-tb` printed,
# titled as a failure's, below the headings reporting it; and a warning's
# text in shapes of a refusal and a conftest pytest could not load, below the
# run's warnings summary or the final one below its short summary. And lines
# of a refusal's shapes refuse nothing, summary or none: in a traceback `-rN
# --tb=native` printed, or in a section and what it captured; nor do a
# conftest's or a plugin's failure in a test's own section and traceback.
_UNFAILED = (
    f".Fx                                                                      [100%]\n{FAILURES_HEADING}"
    "___________________________________ test_bad ___________________________________\nE   AssertionError: bad\n"
    "================================== XFAILURES ===================================\n"
    "____________________________ test_expected_failure _____________________________\n"
    "E   AssertionError: expected failure\n"
    "==================================== PASSES ====================================\n"
    f"___________________________________ test_ok ____________________________________\n{_CAPTURE_RULE}"
    "ok output\n1 failed, 1 passed, 1 xfailed in 0.01s"
)
_WARNING = (
    "test_p.py::test_warns\n  test_p.py:4: UserWarning: nested command failed:\n"
    f"  ERROR: file or directory not found: inner.py\n  {_CONFTEST}\n"
)
_WARNED_FAILURE = SummaryLine("test_p.py::test_warns", "ValueError: actual failure")
_WARNED_SUMMARY = f"{SUMMARY_HEADING}FAILED {_WARNED_FAILURE.node} - {_WARNED_FAILURE.error}\n"
_WARNED = (
    f"=============================== warnings summary ===============================\n{_WARNING}"
    f"{_WARNED_SUMMARY}1 failed, 1 warning in 0.01s"
)
_WARNED_FINAL = (
    f"{_WARNED_SUMMARY}=========================== warnings summary (final) ===========================\n"
    f"{_WARNING}1 failed, 1 warning in 0.01s"
)
_NATIVE_REFUSALS = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "_________________________________ test_failure _________________________________\n"
    "Traceback (most recent call last):\n"
    r'    raise RuntimeError("outer failure\nERROR: file or directory not found: nested")'
    "\nRuntimeError: outer failure\nERROR: file or directory not found: nested\n"
    "python -m pytest: error: unrecognized arguments: --nested\n1 failed in 0.00s"
)
_REFUSAL_PRINTED = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "__________________________________ test_first __________________________________\n"
    f"    ERROR: file or directory not found: __traced__.py\nE   ValueError: first\n{_CAPTURE_RULE}"
    f"python -m pytest: error: unrecognized arguments: --captured-flag\n{SUMMARY_HEADING}"
    "FAILED tests/test_first.py::test_first - ValueError: first\n1 failed in 0.01s"
)
_FIRST = (SummaryLine("tests/test_first.py::test_first", "ValueError: first"), "", "ValueError: first")

# A run `-rN --tb=native` printed, its exception's message running on in a
# summary line's shape: below a heading or a run's opening, whichever the
# output holds, that reports nothing.
_NATIVE_PRINTED = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "_________________________________ test_failure _________________________________\n"
    'Traceback (most recent call last):\n    raise RuntimeError("outer failure")\nRuntimeError: outer failure\n'
    "FAILED fake/test_inner.py::test_inner - ValueError: printed diagnostic\n1 failed in 0.01s"
)
_FAILURE_LEFT = (_TEST_FAILURE, "RuntimeError: outer failure")
_NATIVE_SHAPES = (
    _NATIVE_PRINTED,
    _NATIVE_PRINTED.removeprefix(QUIET_PROGRESS),
    _NATIVE_PRINTED.replace(FAILURES_HEADING, ""),
)
# A line of statistics a test printed, above a run it printed; a native
# traceback's exception saying one, the run's summary or its next section
# right below it; and a run a test printed whole above one it cut short.
_STATS_PRINTED = _NESTED_SUMMARISED.replace(_CAPTURE_RULE, f"{_CAPTURE_RULE}1 passed in 0.00s\nprinted text\n", 1)
_STATS_TRACEBACK = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "__________________________________ test_probe __________________________________\n"
    "Traceback (most recent call last):\n"
    r'    raise RuntimeError("outer failure\n1 passed in 0.01s")'
    "\nRuntimeError: outer failure\n1 passed in 0.01s\n"
)
_PROBE = SummaryLine("test_probe.py::test_probe", _FAILURE_LEFT[1])
_TWO = SummaryLine("test_probe.py::test_two", "ValueError: two")
_STATS_RAISED = f"{_STATS_TRACEBACK}{SUMMARY_HEADING}FAILED {_PROBE.node} - {_PROBE.error}\n1 failed in 0.01s"
_STATS_RAISED_ABOVE = (
    f"{_STATS_TRACEBACK}___ test_two ___\nE   {_TWO.error}\n{SUMMARY_HEADING}"
    f"FAILED {_PROBE.node} - {_PROBE.error}\nFAILED {_TWO.node} - {_TWO.error}\n2 failed in 0.01s"
)
_CUT_BELOW_WHOLE = _NESTED_TITLES.format(opening=_SESSION_HEADING).replace(
    "E   TypeError: outer second failure\n",
    f"E   TypeError: outer second failure\n{_CAPTURE_RULE}{_SESSION_HEADING}collected 1 item\n",
)
_QUIET_CHILD = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}{_OUTER_OPENING}F\n{FAILURES_HEADING}"
    "__________________________________ test_inner __________________________________\n"
    f"E       ValueError: inner failure\n\ntest_inner.py:2: ValueError\n{SUMMARY_HEADING}"
    "FAILED test_inner.py::test_inner - ValueError: inner failure\n1 failed in 0.01s\n"
    f"{SUMMARY_HEADING}FAILED {MODULE}::test_outer\n1 failed in 0.18s"
)
_LETTERS_PRINTED = f"{_OUTER_OPENING}...\n{SUMMARY_HEADING}FAILED {MODULE}::test_outer\n1 failed in 0.01s"
_RECURSIVE = (
    f"{_OUTER_OPENING}{{child}}{FAILURES_HEADING}"
    "__________________________________ test_child __________________________________\n"
    f"E   ValueError: child\n{_CAPTURE_RULE}{{leaf}}{SUMMARY_HEADING}FAILED leaf.py::test_leaf - KeyError: leaf\n"
    f"{{stats}}{SUMMARY_HEADING}FAILED child.py::test_child - ValueError: child\n{{stats}}"
    f"{SUMMARY_HEADING}FAILED {MODULE}::test_outer\n{_OUTER_STATS}\n"
    f"{QUIET_PROGRESS}{SUMMARY_HEADING}FAILED other.py::test_other - ValueError: other\n1 failed in 0.01s"
)
_RECURSIVE_TAKEN = (_OUTER, (SummaryLine("other.py::test_other", "ValueError: other"), "", None))
_RECURSIVE_SHAPES = (
    _RECURSIVE.format(child=_SESSION_HEADING, leaf=_SESSION_HEADING, stats=_STATS),
    _RECURSIVE.format(
        child=f"{QUIET_PROGRESS.replace('[100%]', '[ 50%]')}{QUIET_PROGRESS}",
        leaf=QUIET_PROGRESS,
        stats="1 failed in 0.01s\n",
    ),
)
_PLUGIN_RAISED = (
    f"{FAILURES_HEADING}___ test_plugin ___\n{_CONFTEST}\nTraceback (most recent call last):\n{_PLUGIN}\n"
    f"{SUMMARY_HEADING}FAILED test_plugin.py::test_plugin - {_PLUGIN}\n1 failed in 0.01s"
)

# What a test printed, each summary line then reading as and taking, and the
# sections no line took: (output, taken, left).
_CAPTURED = (
    (_PRINTED_SUMMARISED, [(_OUTER_FAILED, "", _OUTER_FAILED.error)], []),
    (f"{_PRINTED_LINES}1 failed in 0.01s", [], [("test_outer", _OUTER_FAILED.error)]),
    (_PRINTED_MARKED, [(SummaryLine(f"{MODULE}::test_output", ""), "", "RuntimeError: actual failure")], []),
    (_PRINTED_CRASH, [
        (SummaryLine(f"{MODULE}::test_output", ""), "", _ACTUAL),
        (SummaryLine(f"{MODULE}::test_second", ""), "", "assert 1 == 2"),
    ], []),
    (_PRINTED_INDENTED_CRASH, [(SummaryLine("test_probe.py::test_probe", _ACTUAL), "", _ACTUAL)], []),
    (_PRINTED_TITLE, [
        (SummaryLine(f"{MODULE}::test_first", ""), "", "RuntimeError: actual first failure"),
        (SummaryLine(f"{MODULE}::test_second", ""), "", "TypeError: actual second failure"),
    ], []),
    (_PRINTED_SUMMARY, [_OUTER], []),
    (_NESTED_SUMMARISED, [_OUTER, _PLAIN], []),
    (_NESTED_UNSUMMARISED, [], [("test_outer", "RuntimeError: outer failure"), ("test_plain", "assert 1 == 2")]),
    (_CUT_RUN, [_OUTER], []),
    (_NESTED_TITLES.format(opening=_SESSION_HEADING), list(_NESTED_TITLES_TAKEN), []),
    (_NESTED_TITLES.format(opening=_SUBTEST_PROGRESS), list(_NESTED_TITLES_TAKEN), []),
    (_UNFAILED, [], [("test_bad", "AssertionError: bad")]),
    *((warned, [(_WARNED_FAILURE, "", None)], []) for warned in (_WARNED, _WARNED_FINAL)),
    (_NATIVE_REFUSALS, [], [_FAILURE_LEFT]),
    (_REFUSAL_PRINTED, [_FIRST], []),
    (_PLUGIN_RAISED, [(SummaryLine("test_plugin.py::test_plugin", _PLUGIN), "", _PLUGIN)], []),
    *((native, [], [_FAILURE_LEFT]) for native in _NATIVE_SHAPES),
    (_STATS_PRINTED, [_OUTER, _PLAIN], []),
    (_STATS_RAISED, [(_PROBE, "", _PROBE.error)], []),
    (_STATS_RAISED_ABOVE, [(_PROBE, "", _PROBE.error), (_TWO, "", _TWO.error)], []),
    (_CUT_BELOW_WHOLE, list(_NESTED_TITLES_TAKEN), []),
    *((printed, [_OUTER], []) for printed in (_QUIET_CHILD, _LETTERS_PRINTED)),
    *((recursive, list(_RECURSIVE_TAKEN), []) for recursive in _RECURSIVE_SHAPES),
)

# Runs one check printed one after another: runs opening on their sessions'
# headings, on `-q` progress lines, or -- failing collection alone, or with
# `-q -s` -- on a heading below the statistics closing the run before, or on
# the errors heading standing in its summary where the output leaves those
# statistics out, or right below `-q` statistics closing what pytest captured
# from a test -- a passing one's (`-rP`) -- the next run printing no section
# (`--tb=no`), its progress letters carrying a percentage or, with `-q -s`,
# none, or failing collection alone, or refused, and a run after those; runs
# pytest refused, before and after a run it reported; and summary lines quoted
# alone, which stand in no run opened.
_QUIET_FIRST = (
    f"{QUIET_PROGRESS}{FAILURES_HEADING}"
    "__________________________________ test_first __________________________________\n"
    f"E   ValueError: first\n{SUMMARY_HEADING}FAILED tests/test_first.py::test_first - ValueError: first\n"
    "1 failed in 0.01s\n"
)
_QUIET_SECOND = (
    f"{_QUIET_FIRST}{QUIET_PROGRESS}{FAILURES_HEADING}"
    "_________________________________ test_second __________________________________\n"
    f"E   KeyError: 'second'\n{SUMMARY_HEADING}"
    "FAILED tests/test_second.py::test_second - KeyError: 'second'\n1 failed in 0.01s"
)
_UNCOLLECTED_RUN = (
    f"{ERRORS_HEADING}_______________________ ERROR collecting tests/test_b.py _______________________\n"
    f"E   ModuleNotFoundError: No module named 'nowhere'\n{SUMMARY_HEADING}ERROR tests/test_b.py\n{INTERRUPTED}\n"
    "1 error in 0.07s"
)
_TWO_RUNS = (
    f"{_SESSION_HEADING}{SUMMARY_HEADING}FAILED tests/test_a.py::test_a - ValueError: first run\n{_STATS}"
    f"{_SESSION_HEADING}{SUMMARY_HEADING}FAILED tests/test_b.py::test_b - KeyError: second run\n{_STATS}"
)
_HEADED_FIRST = (
    f"{_SESSION_HEADING}{SUMMARY_HEADING}FAILED tests/test_first.py::test_first - ValueError: first\n{_STATS}"
)
_UNCLOSED_FIRST = _QUIET_FIRST.removesuffix("1 failed in 0.01s\n")
_PASSED_CAPTURED = (
    f".F                                                                       [100%]\n{FAILURES_HEADING}"
    "_________________________________ test_failure _________________________________\n"
    "E       RuntimeError: first run error\n"
    "==================================== PASSES ====================================\n"
    f"__________________________________ test_pass ___________________________________\n{_CAPTURE_RULE}"
    "passed capture\n1 failed, 1 passed in 0.01s\n"
)
_FAILURE_SECOND = ("test_probe.py::test_failure", 2)
_UNTRACED_SECOND = (
    f"{QUIET_PROGRESS}{SUMMARY_HEADING}FAILED test_probe.py::test_failure - RuntimeError: second run error\n"
    "1 failed in 0.00s"
)
_UNTRACED_SHAPES = tuple(_UNTRACED_SECOND.replace(QUIET_PROGRESS, letters) for letters in (QUIET_PROGRESS, "F\n"))
_QUOTED = "FAILED tests/test_load.py::test_empty - ValueError: empty file\n1 failed in 3.02s"
_UNPROGRESSED = (
    f"F\n{SUMMARY_HEADING}FAILED test_first.py::test_first - ValueError: first failure\n1 failed in 0.00s\n\n"
    f"F\n{SUMMARY_HEADING}FAILED test_second.py::test_second - ValueError: second failure\n1 failed in 0.00s"
)
_SKIPPED = (
    f"{_QUIET_FIRST}.s                                                                       [100%]\n"
    f"{SUMMARY_HEADING}SKIPPED [1] tests/test_skips.py:5: later\n1 passed, 1 skipped in 0.01s"
)
_SUBTESTS = (
    f"{_QUIET_FIRST}\n{_SUBTEST_PROGRESS}{SUMMARY_HEADING}"
    "SUBFAILED(value=1) test_second.py::test_second - assert 2 == 3\n"
    "FAILED test_second.py::test_second - contains 1 failed subtest\n2 failed in 0.01s"
)
_UNFOUND = "file or directory not found: __missing__.py"
_UNPARSED = (
    f"{_QUIET_FIRST}ERROR: usage: python -m pytest [options] [file_or_dir] [file_or_dir] [...]\n"
    "python -m pytest: error: unrecognized arguments: --bogus-flag\n  inifile: None\n  rootdir: /tmp/run"
)
_FIRST_RUN = ("tests/test_first.py::test_first", 1)
_SECOND_RUN = ("test_second.py::test_second", 2)
_COLLECTED_RUN = ("tests/test_b.py", 2)
_COLLECTING = ("ERROR collecting tests/test_b.py", 2)
_RUNS = (
    (_TWO_RUNS, [("tests/test_a.py::test_a", 1), ("tests/test_b.py::test_b", 2)], []),
    (_QUIET_SECOND, [_FIRST_RUN, ("tests/test_second.py::test_second", 2)], [(_TEST_FIRST, 1), ("test_second", 2)]),
    (f"{_QUIET_FIRST}\n{_UNCOLLECTED_RUN}", [_FIRST_RUN, _COLLECTED_RUN], [(_TEST_FIRST, 1), _COLLECTING]),
    (f"{_UNCLOSED_FIRST}{_UNCOLLECTED_RUN}", [_FIRST_RUN, _COLLECTED_RUN], [(_TEST_FIRST, 1), _COLLECTING]),
    (f"{_HEADED_FIRST}{_UNCOLLECTED_RUN}", [_FIRST_RUN, _COLLECTED_RUN], [_COLLECTING]),
    (_UNPROGRESSED, [("test_first.py::test_first", 0), ("test_second.py::test_second", 1)], []),
    (_SKIPPED, [_FIRST_RUN], [(_TEST_FIRST, 1)]),
    (_SUBTESTS, [_FIRST_RUN, _SECOND_RUN, _SECOND_RUN], [(_TEST_FIRST, 1)]),
    (f"ERROR: {_UNFOUND}\n\nno tests ran in 0.00s\n{_QUIET_FIRST}", [(_UNFOUND, 0), _FIRST_RUN], [(_TEST_FIRST, 1)]),
    (_UNPARSED, [_FIRST_RUN, ("unrecognized arguments: --bogus-flag", 1)], [(_TEST_FIRST, 1)]),
    (_QUOTED, [("tests/test_load.py::test_empty", 0)], []),
    *((f"{_PASSED_CAPTURED}{second}", [_FAILURE_SECOND], [(_TEST_FAILURE, 1)]) for second in _UNTRACED_SHAPES),
    (f"{_PASSED_CAPTURED}ERROR: {_UNFOUND}\n\nno tests ran in 0.00s", [(_UNFOUND, 1)], [(_TEST_FAILURE, 1)]),
    (f"{_PASSED_CAPTURED}{_UNCOLLECTED_RUN}", [_COLLECTED_RUN], [(_TEST_FAILURE, 1), _COLLECTING]),
    (
        f"{_PASSED_CAPTURED}{_UNTRACED_SECOND}\n{_UNCOLLECTED_RUN}",
        [_FAILURE_SECOND, ("tests/test_b.py", 3)],
        [(_TEST_FAILURE, 1), ("ERROR collecting tests/test_b.py", 3)],
    ),
)


# What a check's output says stood in which run, by the run's count.
_Runs = list[tuple[str, int]]


def _unnamed(node: str, message: str) -> tuple[int, ...]:
    """A naming callback naming nothing."""
    return ()


def _runs(output: str) -> tuple[_Runs, _Runs]:
    """Each failure a line of `output` reports, by its node ID or refusal, and each section, with the run of each."""
    read = PytestOutput(output.split("\n"))
    reported = [_reported(line, run) for line, run in read.summary]
    sections = [(section.title, section.run) for section in read.sections]
    return [found for found in reported if found], sections


def _reported(line: str, run: int) -> tuple[str, int] | None:
    """The failure `line` reports, by its node ID or refusal, with its `run`; None where it reports none."""
    summary = SummaryLine.read(line, _unnamed)
    return None if summary is None else (summary.node or summary.error, run)


class PytestSectionsTest(unittest.TestCase):
    """Each section pytest printed reads with its title and the exception it shows."""

    def test_sections_show_their_exception(self) -> None:
        for output, sections in _SECTIONS:
            with self.subTest(output=output):
                read = PytestOutput(output.split("\n"))
                self.assertEqual([(section.title, section.raised) for section in read.sections], sections)

    def test_errors_open_on_shown_exceptions(self) -> None:
        # An error pytest gives opens on a traceback's exception: an assertion
        # without the name Python's own form keeps, and a group holding one
        # exception by that exception's repr and the group's own name -- which
        # a `--tb=line` section holds as given.
        said = (
            ("AssertionError: assert 0 == 1", "assert 0 == 1", True),
            ("ExceptionGroup: group (1 sub-exception)", _SINGLE_GROUP, True),
            (_SINGLE_GROUP, _SINGLE_GROUP, True),
            ("ValueError('other') [single exception in ExceptionGroup]", _SINGLE_GROUP, False),
            ("ExceptionGroup: group (2 sub-exceptions)", _SINGLE_GROUP, False),
            ("BaseExceptionGroup: group (1 sub-exception)", _SINGLE_GROUP, False),
            ("ValueError: empty", "", False),
        )
        for raised, shown, opens in said:
            with self.subTest(raised=raised, shown=shown):
                self.assertIs(Section.says(raised, shown), opens)

    def test_titles_say_what_failed(self) -> None:
        # A title says what failed and in which phase -- a test's own failure
        # in none, one `--tb=line` printed naming nothing.
        titled = (
            ("ERROR collecting tests/test_[b].py", ("collection", "tests/test_[b].py")),
            ("ERROR at setup of test_x[a b]", ("setup", "test_x[a b]")),
            ("ERROR at teardown of TestK.test_m", ("teardown", "TestK.test_m")),
            (_CONFTEST, ("conftest", "/tmp/run/conftest.py")),
            (_PLUGIN, ("plugin", "missing_plugin")),
            ("TestK.test_m[a::b]", ("", "TestK.test_m[a::b]")),
            ("", ("", "")),
        )
        for title, failed in titled:
            with self.subTest(title=title):
                self.assertEqual(Section(title, "", 0).failed, failed)

    def test_names_are_titles(self) -> None:
        # A test's name is its node ID past the path, classes dotted,
        # parameters as written; a path alone names no test.
        named = (
            ("tests/test_a.py::TestK::Inner::test_m[a::b.c]", "TestK.Inner.test_m[a::b.c]"),
            ("test - named.py::test_value[left - right]", "test_value[left - right]"),
            ("sample.txt::sample.txt", "sample.txt"),
            ("tests/test_b.py", ""),
        )
        for node, name in named:
            with self.subTest(node=node):
                self.assertEqual(PytestOutput.name(node), name)


class PytestOutputRegionsTest(unittest.TestCase):
    """Only what pytest printed of its own is read, each summary line with the run it reports on."""

    def test_nothing_captured_is_pytests_own(self) -> None:
        for output, taken, left in _CAPTURED:
            with self.subTest(output=output):
                self.assertEqual(correlated(output), (taken, left))

    def test_lines_report_on_their_own_runs(self) -> None:
        for output, reported, sections in _RUNS:
            with self.subTest(output=output):
                self.assertEqual(_runs(output), (reported, sections))


if __name__ == "__main__":
    unittest.main()
