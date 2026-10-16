# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reviewer's findings as a human is shown them, with no line of its declaration.

The reviewer's words stay wherever they sit around a fresh or reused
declaration, while every marker and step line, each passing check's
transcript, and each bare command inventory go. A check not shown to pass --
its one exit line not reading 0 -- stays as a sentence naming its command and
how it ended, over the output the reviewer quoted, protocol lines it quotes
hidden. Above that sentence it leads with what failed: each test pytest's
summary reports by its exact node ID, with its error; a module pytest could
not collect by that collection, never by a made-up test ID; or the failure
entry of the reviewer's whose error its output shows -- so two runs of one
stdin command each lead with their own scenario -- and otherwise a line saying
nothing names it, beside any error or reproduction the check leaves missing.
An entry leaving out its name, error, or reproduction says so where it
stands -- its labels read across the findings whole, the declaration's place
aside, up to the next finding -- and a check the concise layout before leads
showed is led as if read off the declaration it came from.
A declaration out of shape, or about something else, goes all the same,
without taking the findings written below a block cut short or below a fence
Markdown ends, and what is shown declares nothing the verification reader
would take. Findings with nothing left read as a sentence saying so, never as
the raw message, and formatting what was shown changes nothing.
"""
from __future__ import annotations

import re
import unittest

from orchestrator.workflow.engine import completion_verdicts, review_findings, review_verification
from orchestrator.workflow.engine.review_verification_models import (
    _ReusedVerification,
    _VerificationRefusal,
    _VerificationSubject,
)
from tests.workflow.verdict_values import VERDICT_CHANGES_REQUESTED

_HEAD = "0123456789abcdef0123456789abcdef01234567"
_OTHER_HEAD = "89abcdef0123456789abcdef0123456789abcdef"
_DIGEST = "0123456789abcdef" * 4
_SUBJECT = _VerificationSubject(_HEAD, _DIGEST)

_FINDINGS = (
    "1. **Guard the empty file.** `_load()` raises on one; return `None` and cover it.\n"
    "\n"
    "2. Name the new owner in the architecture map."
)
_CLOSING = "The rest of the diff matches the issue."

_RUN_LINE = f"VERIFICATION: RUN {_HEAD}"
_END_LINE = "VERIFICATION: END"
_REUSED_LINE = f"VERIFICATION: REUSED sha256:{_DIGEST}"
# The lines leading a failing check nothing names, and one that quoted no output.
_UNNAMED = "Failure: not named; no test ID or scenario name was recorded for this check\n"
_NO_OUTPUT = "Error: not recorded; the check quoted no output\n"
_RUFF_STEP = "COMMAND: uv run ruff check orchestrator tests\nEXIT: 0\nAll checks passed!"
_PYTEST_STEP = "COMMAND: uv run pytest tests\nEXIT: 0\n7852 passed, 56 skipped in 327.27s"
_FAILING_STEP = (
    "COMMAND: uv run pytest tests\n"
    "EXIT: 1\n"
    "\n"
    "FAILED tests/test_load.py::test_empty - ValueError: empty file\n"
    "1 failed, 7851 passed in 330.02s\n"
)
_FAILURE_SHOWN = (
    "Failure: `tests/test_load.py::test_empty`\n"
    "Error: `ValueError: empty file`\n"
    "`uv run pytest tests` exited with status 1:\n"
    "\n"
    "```\n"
    "FAILED tests/test_load.py::test_empty - ValueError: empty file\n"
    "1 failed, 7851 passed in 330.02s\n"
    "```"
)
# The same failure with its output right below the exit line, and how a block
# cut short shows it where a blank line parts the two.
_ATTACHED_FAILING_STEP = _FAILING_STEP.replace("EXIT: 1\n\n", "EXIT: 1\n")
_FAILING_OUTPUT = _FAILING_STEP.partition("EXIT: 1\n\n")[2]
_FAILURE_DETACHED = (
    f"{_UNNAMED}{_NO_OUTPUT}"
    "`uv run pytest tests` exited with status 1.\n"
    "\n"
    "FAILED tests/test_load.py::test_empty - ValueError: empty file\n"
    "1 failed, 7851 passed in 330.02s"
)
# Output quoted in a closed fence with a blank line inside, and how a failing
# check shows it: whole, inside a fence its own cannot close.
_FENCED_TRANSCRIPT = "```text\nAll checks passed!\n\n7867 passed, 56 skipped\n```"
_FENCED_DIAGNOSTIC = "```text\nFAILED tests/test_load.py::test_empty\n\nValueError: empty file\n```"
_DIAGNOSTIC_SHOWN = (
    "Failure: `tests/test_load.py::test_empty`\n"
    "Error: not on pytest's summary line; see the output below\n"
    f"`make lint` exited with status 1:\n\n````\n{_FENCED_DIAGNOSTIC}\n````"
)
# Failing output quoting step lines, as a test of this contract prints them,
# and how its check shows it: the quoted step lines hidden, the failure whole.
_QUOTED_PROTOCOL = "```text\nCOMMAND: echo fixture\nEXIT: 0\nFAILED test_empty - ValueError: empty input\n```"
_QUOTED_FAILURE = "```text\nFAILED test_empty - ValueError: empty input\n```"
_QUOTED_MARKER = _QUOTED_PROTOCOL.replace("FAILED", f"{_REUSED_LINE}\nFAILED")
# A finding quoting a test's fixture output that prints the protocol, and how it is shown.
_QUOTING = "1. Fix empty input handling. The failing test printed this fixture:"
_FIXTURE = "```text\nCOMMAND: echo fixture\nEXIT: 0\nAssertionError: empty input was accepted\n```"
_FIXTURE_SHOWN = f"{_QUOTING}\n\n```text\nAssertionError: empty input was accepted\n```"
_MARKED_FIXTURE = _FIXTURE.replace("COMMAND: echo", f"{_RUN_LINE}\nCOMMAND: echo")
# A failing check whose output quotes a fixture holding nothing but step lines, and how it is shown.
_BARE_FIXTURE_STEP = (
    "COMMAND: uv run pytest tests\n"
    "EXIT: 1\n"
    "FAILED test_empty: expected fixture follows\n"
    "```text\nCOMMAND: echo fixture\nEXIT: 0\n```\n"
    "AssertionError: empty input was accepted\n"
)
_BARE_FIXTURE_SHOWN = (
    f"{_UNNAMED}"
    "`uv run pytest tests` exited with status 1:\n"
    "\n"
    "```\n"
    "FAILED test_empty: expected fixture follows\n"
    "AssertionError: empty input was accepted\n"
    "```"
)
# A failing check whose output fence opens two spaces in and holds a run four spaces in, a fixture
# below that run, and how it is shown.
_INDENTED_FIXTURE_STEP = (
    "COMMAND: make lint\n"
    "EXIT: 1\n"
    "  ```text\n"
    "FAILED test_empty\n"
    "    ```\n"
    "COMMAND: echo fixture\n"
    "EXIT: 0\n"
    "AssertionError: empty input was accepted\n"
    "  ```\n"
)
_INDENTED_FIXTURE_SHOWN = (
    f"{_UNNAMED}"
    "`make lint` exited with status 1:\n"
    "\n"
    "````\n"
    "  ```text\n"
    "FAILED test_empty\n"
    "    ```\n"
    "AssertionError: empty input was accepted\n"
    "  ```\n"
    "````"
)
_LIST_FINDING = "1. Fix the empty-input crash."
# A failing check fenced below a passing one, and how it is shown.
_FENCED_FAILURE = "```\nCOMMAND: uv run pytest tests\nEXIT: 1\nAssertionError: empty input was accepted\n```"
_FENCED_FAILURE_SHOWN = (
    f"{_UNNAMED}`uv run pytest tests` exited with status 1:\n\n```\nAssertionError: empty input was accepted\n```"
)
_BARE_FENCED_FAILURE = "```\nCOMMAND: uv run pytest tests\nEXIT: 1\n```"
_BARE_FAILURE_SHOWN = f"{_UNNAMED}{_NO_OUTPUT}`uv run pytest tests` exited with status 1."
# A finding whose list item a lazy line continues, a fence set in the item quoting a fixture, and how
# it is shown.
_LAZY_FINDING = (
    "1. Fix the empty-input crash.\n"
    "The failing test prints this fixture:\n"
    "    ```text\n"
    "    COMMAND: echo fixture\n"
    "    EXIT: 0\n"
    "    AssertionError: empty input was accepted\n"
    "    ```"
)
_LAZY_SHOWN = _LAZY_FINDING.replace("    COMMAND: echo fixture\n    EXIT: 0\n", "")
# A thematic break, which opens no list item, above a fence quoting a fixture, and how it is shown.
_BROKEN_FINDING = (
    "1. Fix the empty-input crash.\n"
    "\n"
    "* * *\n"
    "   ```text\n"
    "COMMAND: echo fixture\n"
    "EXIT: 0\n"
    "AssertionError: empty input was accepted\n"
    "   ```"
)
_BROKEN_SHOWN = _BROKEN_FINDING.replace("COMMAND: echo fixture\nEXIT: 0\n", "")
_FAILED = "AssertionError: empty input"
# A finding quoting a fixture as indented code, in the findings and in a list item, and how each is shown.
_INDENTED_FINDING = f"Fix the crash.\n\n    COMMAND: echo fixture\n    EXIT: 0\n    {_FAILED}"
_INDENTED_SHOWN = f"Fix the crash.\n\n    {_FAILED}"
_ITEM_CODE_FINDING = f"1. Fix the crash.\n\n       COMMAND: echo fixture\n       EXIT: 0\n       {_FAILED}"
_ITEM_CODE_SHOWN = f"1. Fix the crash.\n\n       {_FAILED}"
# A failing step quoted as indented code, and how it is shown below a passing check.
_INDENTED_FAILURE = f"    COMMAND: uv run pytest tests\n    EXIT: 1\n    {_FAILED}"
_INDENTED_FAILURE_SHOWN = f"{_UNNAMED}`uv run pytest tests` exited with status 1:\n\n```\n    {_FAILED}\n```"
# A marker numbered past 1 right below prose, which goes on with the paragraph, above a fence quoting
# a fixture, and how it is shown.
_ORDERED_FINDING = (
    "The error happens at step\n"
    "2. The failing test printed:\n"
    "   ```text\n"
    "COMMAND: echo fixture\n"
    "EXIT: 0\n"
    f"{_FAILED}\n"
    "   ```"
)
_ORDERED_SHOWN = _ORDERED_FINDING.replace("COMMAND: echo fixture\nEXIT: 0\n", "")
_PASSING_BLOCK = f"{_RUN_LINE}\n{_RUFF_STEP}\n{_PYTEST_STEP}\n{_END_LINE}"
_STALE_BLOCK = f"VERIFICATION: RUN {_OTHER_HEAD}\n{_PYTEST_STEP}\n{_END_LINE}"
_ABBREVIATED_HEAD = "0123456"
_ABBREVIATED_BLOCK = f"VERIFICATION: RUN {_ABBREVIATED_HEAD}\n{_PYTEST_STEP}\n{_END_LINE}"
_LINT = "COMMAND: make lint"
_INVENTORY = f"{_LINT}\nCOMMAND: uv run pytest tests"

# The failures pytest's short summary reports, as pytest 9 prints them: a
# test's node ID whole, parameters with spaces, dashes, and the very dash and
# bracket that part an ID from its message included, then the message after a
# dash -- a rewritten assertion, brackets of its own included, an exception
# and what it says, however pytest cut it short, a dash and brackets of its
# own included, or the bare name of an exception saying nothing more -- and a
# test that errored in its fixture.
_SUITE = "COMMAND: uv run pytest tests"
_SUMMARY = (
    "FAILED tests/test_a.py::test_fail - AssertionError: values differ - badly\n"
    "FAILED tests/test_a.py::test_param[a b] - AssertionError: assert 'a b' == 'nope'\n"
    "FAILED tests/test_a.py::test_param[lost-response] - AssertionError: assert 'lost-re...\n"
    "FAILED tests/test_a.py::test_param[x - y] - AssertionError: assert 'x - y' == 'nope'\n"
    "FAILED tests/test_a.py::TestK::test_m - KeyError: 'VERIFY_COMMANDS'\n"
    "FAILED tests/test_a.py::test_value[left] - right] - assert 1 == 2\n"
    "FAILED tests/test_a.py::test_items[case] - assert [1] == [2]\n"
    "FAILED tests/test_a.py::test_list[x] - AssertionError: lists [1] - [2] differ\n"
    "FAILED tests/test_a.py::test_raise[p] - ValueError\n"
    "ERROR tests/test_a.py::test_setup - RuntimeError: fixture exploded\n"
    "9 failed, 1 passed, 1 error in 0.02s"
)
_SUMMARY_LEAD = (
    "Failure: `tests/test_a.py::test_fail`\n"
    "Error: `AssertionError: values differ - badly`\n"
    "Failure: `tests/test_a.py::test_param[a b]`\n"
    "Error: `AssertionError: assert 'a b' == 'nope'`\n"
    "Failure: `tests/test_a.py::test_param[lost-response]`\n"
    "Error: `AssertionError: assert 'lost-re...`\n"
    "Failure: `tests/test_a.py::test_param[x - y]`\n"
    "Error: `AssertionError: assert 'x - y' == 'nope'`\n"
    "Failure: `tests/test_a.py::TestK::test_m`\n"
    "Error: `KeyError: 'VERIFY_COMMANDS'`\n"
    "Failure: `tests/test_a.py::test_value[left] - right]`\n"
    "Error: `assert 1 == 2`\n"
    "Failure: `tests/test_a.py::test_items[case]`\n"
    "Error: `assert [1] == [2]`\n"
    "Failure: `tests/test_a.py::test_list[x]`\n"
    "Error: `AssertionError: lists [1] - [2] differ`\n"
    "Failure: `tests/test_a.py::test_raise[p]`\n"
    "Error: `ValueError`\n"
    "Failure: `tests/test_a.py::test_setup`, which errored outside any test body: "
    "in its collection, setup, or teardown\n"
    "Error: `RuntimeError: fixture exploded`\n"
)
# A module pytest could not import, as its summary and traceback report it, and how its failure leads.
_UNCOLLECTED = "ERROR tests/test_b.py"
_COLLECTION_TRACEBACK = (
    "==================================== ERRORS ====================================\n"
    "__________________________ ERROR collecting tests/test_b.py __________________________\n"
    "ImportError while importing test module '/repo/tests/test_b.py'.\n"
    "tests/test_b.py:1: in <module>\n"
    "    from nowhere import thing\n"
    "E   ModuleNotFoundError: No module named 'nowhere'\n"
    "=========================== short test summary info ============================\n"
    f"{_UNCOLLECTED}\n"
    "!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!"
)
_UNCOLLECTED_NAME = "Failure: collection of `tests/test_b.py`, before any test in it ran\n"
_UNSTATED = "Error: not on pytest's summary line; see the output below\n"
# Two probes of the reviewer's own, run by one stdin command, entered as the
# reviewer is taught: each named, with its error and the snippet reproducing it.
_PROBE = "COMMAND: .venv/bin/python -"
_RELABEL_ERROR = "AssertionError: a failed relabel revived settled evidence"
_ANNOUNCE_ERROR = "AssertionError: a lost announcement revived settled evidence"
_PROBE_ENTRIES = (
    "1. Reprove evidence on both failure paths.\n"
    "\n"
    "   Failure: A lost announcement revives settled evidence\n"
    f"   Error: `{_ANNOUNCE_ERROR}`\n"
    "   Reproduce: `.venv/bin/python -` reading:\n"
    "\n"
    "   ```python\n"
    "   from tests.workflow import relabel_support\n"
    "   assert not relabel_support.revived(relabel_support.lost_announcement())\n"
    "   ```\n"
    "\n"
    "   Failure: A failed relabel request revives settled evidence\n"
    "   Error:\n"
    "\n"
    "   ```text\n"
    "   Traceback (most recent call last):\n"
    f"   {_RELABEL_ERROR}\n"
    "   ```\n"
    "\n"
    "   Reproduce: `.venv/bin/python -` reading:\n"
    "\n"
    "   ```python\n"
    "   from tests.workflow import relabel_support\n"
    "   assert not relabel_support.revived(relabel_support.failed_relabel())\n"
    "   ```"
)
_STDIN_UNREPRODUCED = (
    "Reproduce: not recorded; `.venv/bin/python -` reads its code from stdin, and no snippet was given\n"
)
# A probe's entry quoted in a code block, the same entry written with no
# reproduction, then with a reproduction naming its stdin command but no
# snippet, and how the run printing its error is shown.
_QUOTED_ENTRY = f"```text\nFailure: A probe\nError: {_RELABEL_ERROR}\n```\n\n"
_UNREPRODUCED_ENTRY = f"Failure: A probe\nError: {_RELABEL_ERROR}\n\n"
_UNREPRODUCED_SHOWN = _UNREPRODUCED_ENTRY.replace(
    "\n\n", "\nReproduce: not recorded; the entry gives no reproduction\n\n",
)
_COMMAND_ONLY_ENTRY = f"Failure: A probe\nError: {_RELABEL_ERROR}\nReproduce: `.venv/bin/python -`\n\n"
_PROBE_FAILED = f"`.venv/bin/python -` exited with status 1:\n\n```\n{_RELABEL_ERROR}\n```"
# Entries for the module pytest could not collect, and for a test in it, which is another failure.
_COLLECTED_ERROR = (
    "Error: ImportError: cannot import name 'thing'\nReproduce: .venv/bin/python -m pytest tests/test_b.py"
)
_COLLECTION_ENTRY = f"Failure: pytest collection of tests/test_b.py\n{_COLLECTED_ERROR}\n\n"
_TEST_ENTRY = f"Failure: tests/test_b.py::test_x\n{_COLLECTED_ERROR}\n\n"
# A class pytest could not collect, and a test whose fixture failed, as the
# sections pytest printed for each and its summary report them; and how each
# leads once that context says which it was.
_CLASS_SECTION = "___ ERROR collecting tests/test_collector.py ___\nE   RuntimeError: class construction exploded"
_CLASS_ERROR = "ERROR tests/test_collector.py::TestBroken"
_CLASS_NAME = "Failure: collection of `tests/test_collector.py::TestBroken`, before any test in it ran\n"
_CLASS_EXPLODED = "Error: `RuntimeError: class construction exploded`\n"
_INTERRUPTED = "!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!"
_SETUP_SECTION = "___ ERROR at setup of test_setup ___\nE       RuntimeError: fixture exploded"
_SETUP_ERROR = "ERROR tests/test_a.py::test_setup - RuntimeError: fixture exploded"
_FIXTURE_EXPLODED = "Error: `RuntimeError: fixture exploded`\n"
# A parameter holding the very dash, and text of a message's shape, that part
# an ID from its message; and a message holding them past a parameter of its
# own, with the section pytest titles by the test it failed.
_SHAPED_NODE = "tests/test_parameter.py::test_value[left] - Error: right]"
_SHAPED_SUMMARY = f"FAILED {_SHAPED_NODE} - AssertionError: values differ"
_SHAPED_MESSAGE = "FAILED tests/test_x.py::test_x[a] - AssertionError: got [b] - KeyError: 'c'"
_SHAPED_SECTION = "___ test_x[a] ___"
_SHAPED_SHORT = "Failure: `tests/test_x.py::test_x[a]`\nError: `AssertionError: got [b] - KeyError: 'c'`\n"
_SHAPED_FULL = f"Failure: `{_SHAPED_NODE}`\nError: `AssertionError: values differ`\n"
# Entries naming each ID exactly.
_SHAPED_ENTRY = (
    f"Failure: `{_SHAPED_NODE}`\nError: AssertionError: values differ\nReproduce: pytest '{_SHAPED_NODE}'\n\n"
)
_SHORT_ENTRY = "Failure: tests/test_x.py::test_x[a]\nError: AssertionError: got\nReproduce: pytest tests/test_x.py\n\n"
# A test whose setup and teardown both failed, and a method whose parameter
# holds the very separator its class does, as pytest prints them.
_BOTH_PHASES = (
    "___ ERROR at setup of test_both ___\n"
    "E       RuntimeError: setup exploded\n"
    "___ ERROR at teardown of test_both ___\n"
    "E       ValueError: teardown exploded\n"
    "ERROR tests/test_fixture.py::test_both - RuntimeError: setup exploded\n"
    "ERROR tests/test_fixture.py::test_both - ValueError: teardown exploded"
)
_BOTH_LEAD = (
    "Failure: `tests/test_fixture.py::test_both`, whose setup failed\n"
    "Error: `RuntimeError: setup exploded`\n"
    "Failure: `tests/test_fixture.py::test_both`, whose teardown failed\n"
    "Error: `ValueError: teardown exploded`\n"
)
_SEPARATED_NODE = "tests/test_fixture.py::TestK::test_m[a::b]"
_SEPARATED = f"___ TestK.test_m[a::b] ___\nFAILED {_SEPARATED_NODE} - AssertionError: got [b] - KeyError: c"
_SEPARATED_LEAD = f"Failure: `{_SEPARATED_NODE}`\nError: `AssertionError: got [b] - KeyError: c`\n"
# A long parameterized ID and a long module path, as pytest prints them on an
# 80-column terminal: a section titled with a single underscore each side, a
# frame separator inside it, and summary lines too long to carry a message.
_LONG_CASE = "a_very_long_parameter_value_with_separators_left] - Error: right"
_LONG_NODE = f"test_id.py::test_value[{_LONG_CASE}]"
_LONG_OUTPUT = (
    f"_ test_value[{_LONG_CASE}] _\n"
    "    def test_value(case):\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n"
    "E       assert 0 == 1\n"
    "= short test summary info =\n"
    f"FAILED {_LONG_NODE}"
)
_LONG_LEAD = f"Failure: `{_LONG_NODE}`\nError: `assert 0 == 1`\n"
_LONG_MODULE = "test_configuration_with_a_long_module_name_for_the_setup_failure.py"
_UNSTATED_SETUP = (
    "___________________________ ERROR at setup of test_x ___________________________\n"
    "E       RuntimeError: fixture initialization exploded\n"
    f"ERROR {_LONG_MODULE}::test_x"
)
_UNSTATED_SETUP_LEAD = (
    f"Failure: `{_LONG_MODULE}::test_x`, whose setup failed\n"
    "Error: `RuntimeError: fixture initialization exploded`\n"
)
# Sections as pytest prints them on an 80-column terminal, summary lines too
# long to carry their errors: tests of two modules sharing a name, and their
# fixtures; a fixture's assertion over its explanation and diff hint, a line
# marked blank among them; and an exception raised handling another.
_FIRST = "tests/test_first_with_a_very_long_module_name_to_fill_the_terminal.py::test_same"
_SECOND = "tests/test_second_with_a_very_long_module_name_to_fill_the_terminal.py::test_same"
_SAME_TITLES = (
    "__________________________________ test_same ___________________________________\n"
    "E       ValueError: first module failed\n"
    "__________________________________ test_same ___________________________________\n"
    "E       TypeError: second module failed\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_FIRST}\nFAILED {_SECOND}"
)
_SAME_TITLES_LEAD = (
    f"Failure: `{_FIRST}`\nError: `ValueError: first module failed`\n"
    f"Failure: `{_SECOND}`\nError: `TypeError: second module failed`\n"
)
_SAME_FIXTURES = (
    "___ ERROR at setup of test_same ___\nE       RuntimeError: first fixture failed\n"
    "___ ERROR at setup of test_same ___\nE       KeyError: second fixture failed\n"
    f"ERROR {_FIRST}\nERROR {_SECOND}"
)
_SAME_FIXTURES_LEAD = (
    f"Failure: `{_FIRST}`, whose setup failed\nError: `RuntimeError: first fixture failed`\n"
    f"Failure: `{_SECOND}`, whose setup failed\nError: `KeyError: second fixture failed`\n"
)
_ASSERTED = "tests/test_fixture_assert_with_a_long_module_name_for_setup.py"
_DIFF_HINT = (
    "___________________________ ERROR at setup of test_x ___________________________\n"
    "E       assert [1, 2] == [3, 4]\n"
    "E         \n"
    "E         At index 0 diff: 1 != 3\n"
    "E         Use -v to get more diff\n"
    "=========================== short test summary info ============================\n"
    f"ERROR {_ASSERTED}::test_x"
)
_DIFF_HINT_LEAD = f"Failure: `{_ASSERTED}::test_x`, whose setup failed\nError: `assert [1, 2] == [3, 4]`\n"
_CHAINED = (
    "__________________________________ test_chain __________________________________\n"
    "E           KeyError: 'x'\n"
    "During handling of the above exception, another exception occurred:\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ \n"
    "E           ValueError: chained failure\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_ASSERTED}::test_chain"
)
_CHAINED_LEAD = f"Failure: `{_ASSERTED}::test_chain`\nError: `ValueError: chained failure`\n"
# A command running a parameterized test it names quoted, a dash among its
# parameters, which reads nothing from stdin; and commands passing a dash to a
# program given before it -- inline, by module, or as a script.
_QUOTED_NODE = "tests/test_values.py::test_value[x - y]"
_QUOTED_COMMAND = f".venv/bin/python -m pytest '{_QUOTED_NODE}'"
_ARGUMENT_DASHES = (
    _QUOTED_COMMAND,
    ".venv/bin/python -c 'raise RuntimeError(\"dash is argv\")' -",
    ".venv/bin/python -m pytest -",
    ".venv/bin/python tests/probe.py -",
)
# Failures as pytest prints them with `--tb=line` on an 80-column terminal:
# under the failures heading each is its marked lines and the file and line it
# crashed at -- a helper's, for one -- with its exception, titled by nothing,
# while a fixture's error keeps its section; and with `--tb=native`, each in a
# section of its own holding Python's own traceback, one raised handling
# another.
_LINE_MODULE = "tests/test_failure_with_a_long_module_name_to_fill_the_terminal.py"
_LINE_TRACEBACKS = (
    "==================================== ERRORS ====================================\n"
    "_________________________ ERROR at setup of test_setup _________________________\n"
    "E   RuntimeError: fixture exploded\n"
    "=================================== FAILURES ===================================\n"
    "E   RuntimeError: the supplied diagnostic\n"
    f"/tmp/run/{_LINE_MODULE}:9: RuntimeError: the supplied diagnostic\n"
    "E   KeyError: 'deep in a helper'\n"
    "/tmp/run/tests/helper_mod.py:2: KeyError: 'deep in a helper'\n"
    "E   assert [1, 2] == [3, 4]\n"
    "      \n"
    "      At index 0 diff: 1 != 3\n"
    "      Use -v to get more diff\n"
    f"/tmp/run/{_LINE_MODULE}:18: assert [1, 2] == [3, 4]\n"
    "=========================== short test summary info ============================\n"
    f"ERROR {_LINE_MODULE}::test_setup\n"
    f"FAILED {_LINE_MODULE}::test_check\nFAILED {_LINE_MODULE}::test_helper\nFAILED {_LINE_MODULE}::test_assert"
)
_LINE_TRACEBACKS_LEAD = (
    f"Failure: `{_LINE_MODULE}::test_setup`, whose setup failed\nError: `RuntimeError: fixture exploded`\n"
    f"Failure: `{_LINE_MODULE}::test_check`\nError: `RuntimeError: the supplied diagnostic`\n"
    f"Failure: `{_LINE_MODULE}::test_helper`\nError: `KeyError: 'deep in a helper'`\n"
    f"Failure: `{_LINE_MODULE}::test_assert`\nError: `assert [1, 2] == [3, 4]`\n"
)
_NATIVE_TRACEBACKS = (
    "__________________________________ test_check __________________________________\n"
    "Traceback (most recent call last):\n"
    f'  File "/tmp/run/{_LINE_MODULE}", line 9, in test_check\n'
    '    raise RuntimeError("the supplied diagnostic")\n'
    "RuntimeError: the supplied diagnostic\n"
    "__________________________________ test_chain __________________________________\n"
    "Traceback (most recent call last):\n"
    f'  File "/tmp/run/{_LINE_MODULE}", line 13, in chained\n'
    '    {}["x"]\n'
    "KeyError: 'x'\n"
    "\n"
    "During handling of the above exception, another exception occurred:\n"
    "\n"
    "Traceback (most recent call last):\n"
    f'  File "/tmp/run/{_LINE_MODULE}", line 15, in chained\n'
    '    raise ValueError("chained failure")\n'
    "ValueError: chained failure\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_LINE_MODULE}::test_check\nFAILED {_LINE_MODULE}::test_chain"
)
_NATIVE_TRACEBACKS_LEAD = (
    f"Failure: `{_LINE_MODULE}::test_check`\nError: `RuntimeError: the supplied diagnostic`\n"
    f"Failure: `{_LINE_MODULE}::test_chain`\nError: `ValueError: chained failure`\n"
)
# A test in a file whose path holds blanks, a module there pytest could not
# collect -- its message holding a separator of its own -- and a fixture whose
# finalizers both failed, which pytest prints as an exception group in any
# mode: each exception it holds set further in, behind the group's rail.
_SPACED_NODE = "tests/test file.py::test_value[a b]"
_SPACED = f"FAILED {_SPACED_NODE} - ValueError: actual failure"
_SPACED_LEAD = f"Failure: `{_SPACED_NODE}`\nError: `ValueError: actual failure`\n"
_SPACED_UNCOLLECTED = "ERROR tests/test file.py - ImportError: cannot import name 'b' from 'a::c'"
_SPACED_UNCOLLECTED_LEAD = (
    "Failure: collection of `tests/test file.py`, before any test in it ran\n"
    "Error: `ImportError: cannot import name 'b' from 'a::c'`\n"
)
_SPACED_MODULE = "test spaced_module_with_a_long_name_to_fill_the_terminal.py"
_SECOND_MODULE = "test_second_module_with_a_long_name_to_fill_the_terminal.py"
_SPACED_LINES = (
    "=================================== FAILURES ===================================\n"
    "E   RuntimeError: failure 0\n"
    f"/tmp/run/{_SPACED_MODULE}:2: RuntimeError: failure 0\n"
    "E   RuntimeError: failure 1\n"
    f"/tmp/run/{_SECOND_MODULE}:2: RuntimeError: failure 1\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_SPACED_MODULE}::test_check\nFAILED {_SECOND_MODULE}::test_check"
)
_SPACED_LINES_LEAD = (
    f"Failure: `{_SPACED_MODULE}::test_check`\nError: `RuntimeError: failure 0`\n"
    f"Failure: `{_SECOND_MODULE}::test_check`\nError: `RuntimeError: failure 1`\n"
)
_GROUP_MODULE = "test_teardown_failure_with_a_long_module_name_to_fill_the_terminal.py"
_GROUP_RAISED = 'ExceptionGroup: errors while tearing down fixture "broken" of <Function test_group> (2 sub-exceptions)'
_GROUPED = (
    "_______________________ ERROR at teardown of test_group ________________________\n"
    "  + Exception Group Traceback (most recent call last):\n"
    "  |     raise BaseExceptionGroup(msg, exceptions[::-1])\n"
    f"  | {_GROUP_RAISED}\n"
    "  +-+---------------- 1 ----------------\n"
    "    | Traceback (most recent call last):\n"
    "    |     raise ValueError('first finalizer')\n"
    "    | ValueError: first finalizer\n"
    "    +---------------- 2 ----------------\n"
    "    | Traceback (most recent call last):\n"
    "    |     raise TypeError('second finalizer')\n"
    "    | TypeError: second finalizer\n"
    "    +------------------------------------\n"
    "=========================== short test summary info ============================\n"
    f"ERROR {_GROUP_MODULE}::test_group"
)
_GROUPED_LEAD = f"Failure: `{_GROUP_MODULE}::test_group`, whose teardown failed\nError: `{_GROUP_RAISED}`\n"
# Tests printing lines of pytest's own shapes, which it captured and prints
# under a rule below each traceback, as on an 80-column terminal: a marked
# line below a long ID's section; a summary line above the short summary, and
# with no short summary at all (`-rN`); and, with `--tb=line`, a crash line
# and a marked line above the crash line pytest printed for the failure.
_CAPTURE_RULE = "----------------------------- Captured stdout call -----------------------------\n"
_OUTER_SECTION = (
    "__________________________________ test_outer __________________________________\n"
    "E       RuntimeError: outer test failed\n"
    f"{_CAPTURE_RULE}"
    "FAILED tests/test_child.py::test_child - ValueError: simulated output\n"
    "ERROR tests/test_child.py - ImportError: simulated collection\n"
)
_CAPTURED_MARKED = (
    "_________________________________ test_output __________________________________\n"
    "E       RuntimeError: actual failure\n"
    f"/tmp/run/{_LINE_MODULE}:3: RuntimeError\n"
    f"{_CAPTURE_RULE}"
    "E   captured stdout is not the exception\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_LINE_MODULE}::test_output"
)
_CAPTURED_MARKED_LEAD = f"Failure: `{_LINE_MODULE}::test_output`\nError: `RuntimeError: actual failure`\n"
_CAPTURED_SUMMARY = (
    f"{_OUTER_SECTION}"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_outer.py::test_outer - RuntimeError: outer test failed"
)
_CAPTURED_SUMMARY_LEAD = "Failure: `tests/test_outer.py::test_outer`\nError: `RuntimeError: outer test failed`\n"
_CAPTURED_UNSUMMARISED = f"{_OUTER_SECTION}1 failed in 0.01s"
_CAPTURED_LINES = (
    "=================================== FAILURES ===================================\n"
    "E   RuntimeError: actual failure\n"
    f"{_CAPTURE_RULE}"
    "tests/helper.py:3: printed a crash-shaped line\n"
    "E   printed a marked line\n"
    f"/tmp/run/{_LINE_MODULE}:4: RuntimeError: actual failure\n"
    "E   assert 1 == 2\n"
    f"/tmp/run/{_LINE_MODULE}:8: assert 1 == 2\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {_LINE_MODULE}::test_output\nFAILED {_LINE_MODULE}::test_second"
)
_CAPTURED_LINES_LEAD = (
    f"Failure: `{_LINE_MODULE}::test_output`\nError: `RuntimeError: actual failure`\n"
    f"Failure: `{_LINE_MODULE}::test_second`\nError: `assert 1 == 2`\n"
)
# Tests printing pytest's own output: a summary heading and line alone, above
# the run's own summary; a whole run, its sections and summary among it, with
# the outer run summarised and not (`-rN`); and a run cut short below its
# session's heading. Two runs of a check each keep their own summary.
_SESSION_HEADING = "============================= test session starts ==============================\n"
_SUMMARY_HEADING = "=========================== short test summary info ============================\n"
_OUTER_OPENING = (
    "__________________________________ test_outer __________________________________\n"
    "E   RuntimeError: outer failure\n"
    f"{_CAPTURE_RULE}"
)
_OUTER_LEAD = f"Failure: `{_LINE_MODULE}::test_outer`\nError: `RuntimeError: outer failure`\n"
_PRINTED_SUMMARY = (
    f"{_OUTER_OPENING}{_SUMMARY_HEADING}"
    "FAILED nested/test_inner.py::test_inner - ValueError: only captured text\n"
    f"{_SUMMARY_HEADING}FAILED {_LINE_MODULE}::test_outer"
)
_NESTED_RUN = (
    f"{_OUTER_OPENING}{_SESSION_HEADING}"
    "collected 1 item\n"
    "\n"
    "test_inner.py F                                                          [100%]\n"
    "\n"
    "=================================== FAILURES ===================================\n"
    "E   ValueError: inner only\n"
    "/tmp/inner/test_inner.py:2: ValueError: inner only\n"
    f"{_SUMMARY_HEADING}"
    "FAILED test_inner.py::test_inner - ValueError: inner only\n"
    "============================== 1 failed in 0.01s ===============================\n"
    "\n"
    "__________________________________ test_plain __________________________________\n"
    "E   assert 1 == 2\n"
)
_OUTER_STATS = "============================== 2 failed in 0.02s ==============================="
_NESTED_SUMMARISED = (
    f"{_NESTED_RUN}{_SUMMARY_HEADING}FAILED {_LINE_MODULE}::test_outer\nFAILED {_LINE_MODULE}::test_plain\n"
    f"{_OUTER_STATS}"
)
_NESTED_SUMMARISED_LEAD = f"{_OUTER_LEAD}Failure: `{_LINE_MODULE}::test_plain`\nError: `assert 1 == 2`\n"
_NESTED_UNSUMMARISED = f"{_NESTED_RUN}{_OUTER_STATS}"
_CUT_RUN = (
    f"{_OUTER_OPENING}{_SESSION_HEADING}collected 1 item\n{_SUMMARY_HEADING}FAILED {_LINE_MODULE}::test_outer\n"
    "============================== 1 failed in 0.01s ==============================="
)
_TWO_RUNS = (
    f"{_SESSION_HEADING}{_SUMMARY_HEADING}FAILED tests/test_a.py::test_a - ValueError: first run\n"
    "============================== 1 failed in 0.01s ===============================\n"
    f"{_SESSION_HEADING}{_SUMMARY_HEADING}FAILED tests/test_b.py::test_b - KeyError: second run\n"
    "============================== 1 failed in 0.01s ==============================="
)
_TWO_RUNS_LEAD = (
    "Failure: `tests/test_a.py::test_a`\nError: `ValueError: first run`\n"
    "Failure: `tests/test_b.py::test_b`\nError: `KeyError: second run`\n"
)
# A run a test printed holding a section titled as a test of the outer run is,
# whose summary line is too long to carry its error.
_NESTED_TITLES = (
    "______________________________ test_prints_child _______________________________\n"
    "E   RuntimeError: outer first failure\n"
    f"{_CAPTURE_RULE}{_SESSION_HEADING}"
    "__________________________________ test_same ___________________________________\n"
    "E   ValueError: captured child failure\n"
    f"{_SUMMARY_HEADING}"
    "FAILED child/test_inner.py::test_same - ValueError: captured child failure\n"
    "============================== 1 failed in 0.01s ===============================\n"
    "__________________________________ test_same ___________________________________\n"
    "E   TypeError: outer second failure\n"
    f"{_SUMMARY_HEADING}FAILED {_LINE_MODULE}::test_prints_child\nFAILED {_LINE_MODULE}::test_same\n"
    f"{_OUTER_STATS}"
)
_NESTED_TITLES_LEAD = (
    f"Failure: `{_LINE_MODULE}::test_prints_child`\nError: `RuntimeError: outer first failure`\n"
    f"Failure: `{_LINE_MODULE}::test_same`\nError: `TypeError: outer second failure`\n"
)
# Runs `-q` printed one after another, each opening on no session's heading:
# on its progress line, or -- failing collection alone, it reports no progress
# -- on its errors heading.
_QUIET_PROGRESS = "F                                                                        [100%]\n"
_QUIET_FIRST = (
    f"{_QUIET_PROGRESS}"
    "=================================== FAILURES ===================================\n"
    "__________________________________ test_first __________________________________\n"
    "E   ValueError: first\n"
    f"{_SUMMARY_HEADING}"
    "FAILED tests/test_first.py::test_first - ValueError: first\n"
    "1 failed in 0.01s\n"
)
_QUIET_FIRST_LEAD = "Failure: `tests/test_first.py::test_first`\nError: `ValueError: first`\n"
_QUIET_RUNS = (
    f"{_QUIET_FIRST}{_QUIET_PROGRESS}"
    "=================================== FAILURES ===================================\n"
    "_________________________________ test_second __________________________________\n"
    "E   KeyError: 'second'\n"
    f"{_SUMMARY_HEADING}"
    "FAILED tests/test_second.py::test_second - KeyError: 'second'\n"
    "1 failed in 0.01s"
)
_QUIET_RUNS_LEAD = f"{_QUIET_FIRST_LEAD}Failure: `tests/test_second.py::test_second`\nError: `KeyError: 'second'`\n"
_QUIET_UNCOLLECTED = (
    f"{_QUIET_FIRST}\n"
    "==================================== ERRORS ====================================\n"
    "_______________________ ERROR collecting tests/test_b.py _______________________\n"
    "E   ModuleNotFoundError: No module named 'nowhere'\n"
    f"{_SUMMARY_HEADING}"
    f"ERROR tests/test_b.py\n{_INTERRUPTED}\n"
    "1 error in 0.07s"
)
_QUIET_UNCOLLECTED_LEAD = (
    f"{_QUIET_FIRST_LEAD}{_UNCOLLECTED_NAME}Error: `ModuleNotFoundError: No module named 'nowhere'`\n"
)
_QUIET_SKIPPED = (
    f"{_QUIET_FIRST}"
    ".s                                                                       [100%]\n"
    f"{_SUMMARY_HEADING}"
    "SKIPPED [1] tests/test_skips.py:5: later\n"
    "1 passed, 1 skipped in 0.01s"
)
# A stdin check running pytest, which names the test that failed, and how it leads.
_STDIN_PYTEST = "FAILED tests/test_probe.py::test_probe - AssertionError: values differ"
_STDIN_PYTEST_SHOWN = (
    "Failure: `tests/test_probe.py::test_probe`\nError: `AssertionError: values differ`\n"
    f"{_STDIN_UNREPRODUCED}`.venv/bin/python -` exited with status 1:\n\n```\n{_STDIN_PYTEST}\n```"
)
# Entries whose reproduction is a fence holding no code, empty or blank.
_EMPTY_FENCE_ENTRY = (
    f"Failure: A probe\nError: {_RELABEL_ERROR}\nReproduce: `.venv/bin/python -` reading:\n\n```python\n```\n\n"
)
_BLANK_FENCE_ENTRY = _EMPTY_FENCE_ENTRY.replace("```python\n", "```python\n   \n")
# What an entry leaving out its name, error, or reproduction is shown saying.
_UNNAMED_ENTRY = "not named; the entry gives no test ID or scenario name"
_NO_ENTRY_ERROR = "not recorded; the entry gives no error"
_NO_ENTRY_REPRODUCTION = "not recorded; the entry gives no reproduction"
# Findings each opening on a list item or a heading, entries under them, and a
# paragraph of a finding's own between its entry's labels; and an entry above
# the declaration whose reproduction the reviewer wrote below it.
_FINDINGS_APART = (
    "1. A failed assertion without a reproduction.\n\n"
    "   Failure: Named assertion\n"
    "   Error: AssertionError: expected 1\n\n"
    "2. Another check has a reproduction but no failure-entry layout.\n\n"
    "   Reproduce: .venv/bin/python -m pytest tests/other.py\n\n"
    "Failure: Named probe\n"
    "Error: KeyError: 'x'\n\n"
    "The probe reads a missing key.\n\n"
    "Reproduce: .venv/bin/python -m pytest tests/probe.py\n\n"
    "## A heading's finding\n\n"
    "Reproduce: .venv/bin/python -m pytest tests/heading.py"
)
# Entries the next finding opens right below -- a heading, a list item, and
# the next item of a numbered list the entry stands under -- each with the
# indentation it stands in.
_ADJACENT_FINDINGS = (
    ("Failure: Named probe\nError: AssertionError: expected 1\n## Next finding", ""),
    ("Failure: Named probe\nError: AssertionError: expected 1\n- Next finding", ""),
    (
        (
            "1. First finding\n   Failure: Named probe\n   Error: AssertionError: expected 1\n"
            "2. Second finding\n   Reproduce: x"
        ),
        "   ",
    ),
)
_PROBE_ENTRY = f"Failure: A probe\nError: {_RELABEL_ERROR}\n\n"
_PROBE_SNIPPET = f"Reproduce: .venv/bin/python - reading:\n\n```python\nraise AssertionError('{_RELABEL_ERROR}')\n```"
# More tests failing than a lead names, and as many as it does.
_FAILED_TESTS = 12
_NAMED_TESTS = 10

# A line any reader of the contract would take for one of its own.
_PROTOCOL_LINE_RE = re.compile(r"^[ \t]*(?:VERIFICATION|COMMAND|EXIT):", re.MULTILINE)


class DeclarationFindingsTest(unittest.TestCase):
    """What a declaration leaves of the findings around it."""

    def test_findings_around_declarations_stay(self) -> None:
        cases = (
            (f"{_FINDINGS}\n\n{_PASSING_BLOCK}", _FINDINGS),
            (f"{_FINDINGS}\n\n{_PASSING_BLOCK}\n\n{_CLOSING}\n", f"{_FINDINGS}\n\n{_CLOSING}"),
            (f"{_FINDINGS}\n{_REUSED_LINE}", _FINDINGS),
            (f"{_FINDINGS}\n\n{_REUSED_LINE}\n\n{_CLOSING}", f"{_FINDINGS}\n\n{_CLOSING}"),
        )
        for findings, shown in cases:
            with self.subTest(findings=findings):
                _assert_shown(self, findings, shown)

    def test_verdict_body_keeps_its_declaration(self) -> None:
        message = f"{_FINDINGS}\n\n{_PASSING_BLOCK}\n\nVERDICT: CHANGES_REQUESTED\n"
        verdict, body = completion_verdicts._parse_review_verdict(message)
        self.assertEqual(verdict, VERDICT_CHANGES_REQUESTED)
        self.assertEqual(body, f"{_FINDINGS}\n\n{_PASSING_BLOCK}")
        _assert_shown(self, body, _FINDINGS)

    def test_failed_check_stays_over_its_output(self) -> None:
        findings = f"{_FINDINGS}\n\n{_RUN_LINE}\n{_RUFF_STEP}\n{_FAILING_STEP}{_END_LINE}\n\n{_CLOSING}"
        _assert_shown(self, findings, f"{_FINDINGS}\n\n{_FAILURE_SHOWN}\n\n{_CLOSING}")

    def test_command_inventory_is_dropped(self) -> None:
        cases = (
            (f"{_FINDINGS}\n\n{_INVENTORY}", _FINDINGS),
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_INVENTORY}\n{_END_LINE}\n\n{_CLOSING}", f"{_FINDINGS}\n\n{_CLOSING}"),
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_LINT}\nEXIT:\n{_END_LINE}", _FINDINGS),
            (f"{_FINDINGS}\n\n```\n{_INVENTORY}\n```", _FINDINGS),
        )
        for findings, shown in cases:
            with self.subTest(findings=findings):
                _assert_shown(self, findings, shown)

    def test_quoted_protocol_keeps_its_diagnostic(self) -> None:
        reused = f"{_QUOTING}\n\n{_FIXTURE}\n\n{_REUSED_LINE}"
        # Quoting a RUN line with nothing declared outside fences, the fixture is
        # still no whole declaration, so it stays a quote.
        marked = (f"{_QUOTING}\n\n{_MARKED_FIXTURE}\n\n{_REUSED_LINE}", f"{_QUOTING}\n\n{_MARKED_FIXTURE}")
        self.assertIsInstance(
            review_verification._parse_verification_outcome(reused, _SUBJECT), _ReusedVerification,
        )
        for findings in marked:
            self.assertIs(
                review_verification._parse_verification_outcome(findings, _SUBJECT),
                _VerificationRefusal.MALFORMED,
            )
        for findings in (reused, *marked, f"{_QUOTING}\n\n{_FIXTURE}"):
            with self.subTest(findings=findings):
                _assert_shown(self, findings, _FIXTURE_SHOWN)

    def test_unpassed_check_says_how_it_ended(self) -> None:
        # Nothing names these checks' failures, so each leads with a line saying so.
        cases = (
            (f"{_LINT}\nEXIT: 2", f"{_NO_OUTPUT}`make lint` exited with status 2."),
            (f"{_LINT}\nlint.py:3: E501", "`make lint` reported no exit status:\n\n```\nlint.py:3: E501\n```"),
            (
                f"{_LINT}\nEXIT:\nlint.py:3: E501",
                "`make lint` reported a blank exit status:\n\n```\nlint.py:3: E501\n```",
            ),
            (f"{_LINT}\nEXIT: 0\nEXIT: 0\nok", "`make lint` reported the exit statuses 0, 0:\n\n```\nok\n```"),
            (
                f"{_LINT}\nEXIT: 0\nEXIT:\nFAILED test_empty: ValueError",
                "`make lint` reported the exit statuses 0, (blank):\n\n```\nFAILED test_empty: ValueError\n```",
            ),
            (f"{_LINT}\nEXIT: 01", f"{_NO_OUTPUT}`make lint` exited with status 01."),
            ("EXIT: 1\nTraceback", "A check naming no command exited with status 1:\n\n```\nTraceback\n```"),
            (
                "COMMAND: `make` lint\nEXIT: 1\n```diff\n-old\n```",
                "`` `make` lint `` exited with status 1:\n\n````\n```diff\n-old\n```\n````",
            ),
        )
        for steps, shown in cases:
            with self.subTest(steps=steps):
                _assert_shown(self, f"{_RUN_LINE}\n{steps}\n{_END_LINE}", f"{_UNNAMED}{shown}")


class OutOfShapeFindingsTest(unittest.TestCase):
    """Refused declarations, findings with nothing left, and findings already concise."""

    def test_cut_short_block_keeps_findings_below(self) -> None:
        _assert_malformed_shown(
            self,
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_PYTEST_STEP}\n", _FINDINGS),
            (f"{_RUN_LINE}\n{_PYTEST_STEP}\n\n{_CLOSING}", _CLOSING),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{_CLOSING}", _CLOSING),
            (f"{_RUN_LINE}\n{_RUFF_STEP}\n\n{_PYTEST_STEP}\n\n{_CLOSING}", _CLOSING),
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_ATTACHED_FAILING_STEP}", f"{_FINDINGS}\n\n{_FAILURE_SHOWN}"),
            # Output a blank line parts from its exit line may be findings, so it stays as text.
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_RUFF_STEP}\n{_FAILING_STEP}", f"{_FINDINGS}\n\n{_FAILURE_DETACHED}"),
            # A block missing its RUN line opens on its first step, and reads as cut short
            # whatever closing line follows.
            (f"{_PYTEST_STEP}\n\n{_CLOSING}\n{_END_LINE}", _CLOSING),
            (f"{_FINDINGS}\n\n{_PYTEST_STEP}\n{_END_LINE}\n\n{_CLOSING}", f"{_FINDINGS}\n\n{_CLOSING}"),
            # A closed fence below a check is its output whole, blank lines inside included.
            (
                f"{_FINDINGS}\n\n{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{_FENCED_TRANSCRIPT}\n\n{_CLOSING}",
                f"{_FINDINGS}\n\n{_CLOSING}",
            ),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{_FENCED_TRANSCRIPT}\n\n{_CLOSING}", _CLOSING),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{_FENCED_TRANSCRIPT}\n{_CLOSING}", _CLOSING),
            (
                f"{_FINDINGS}\n\n{_RUN_LINE}\n{_LINT}\nEXIT: 1\n{_FENCED_DIAGNOSTIC}\n\n{_CLOSING}",
                f"{_FINDINGS}\n\n{_DIAGNOSTIC_SHOWN}\n\n{_CLOSING}",
            ),
        )

    def test_refused_declarations_are_dropped(self) -> None:
        _assert_malformed_shown(
            self,
            (f"{_FINDINGS}\n\n{_ABBREVIATED_BLOCK}", _FINDINGS),
            (f"{_FINDINGS}\n\n{_PASSING_BLOCK}\n{_REUSED_LINE}", _FINDINGS),
        )

    def test_stale_declaration_is_dropped(self) -> None:
        findings = f"{_FINDINGS}\n\n{_STALE_BLOCK}"
        self.assertIs(
            review_verification._parse_verification_outcome(findings, _SUBJECT),
            _VerificationRefusal.STALE,
        )
        _assert_shown(self, findings, _FINDINGS)

    def test_nothing_left_reads_as_no_findings(self) -> None:
        nothing_left = (
            f"```\n{_PASSING_BLOCK}",
            "",
            " \n\t\n",
            _PASSING_BLOCK,
            f"\n{_REUSED_LINE}\n",
            f"```\n{_PASSING_BLOCK}\n```",
            _INVENTORY,
            f"{_RUN_LINE}\n{_INVENTORY}\n{_END_LINE}",
            f"{_RUN_LINE}\n{_LINT}\nEXIT:\n{_END_LINE}",
        )
        for findings in nothing_left:
            with self.subTest(findings=findings):
                _assert_shown(self, findings, review_findings._NO_FINDINGS)

    def test_concise_findings_come_back_as_written(self) -> None:
        concise = (
            f"{_FINDINGS}\n"
            "\n"
            "The prompt should teach `VERIFICATION: RUN <head>` inline:\n"
            "\n"
            "```python\n"
            "    marker = 'COMMAND: ' + command\n"
            "```\n"
            "\n"
            f"> {_REUSED_LINE}\n"
            f"- {_END_LINE}"
        )
        _assert_shown(self, concise, concise)


class FenceFindingsTest(unittest.TestCase):
    """Where a code fence ends, as Markdown ends it, and what a fence below a check leaves."""

    def test_closing_run_is_read_from_its_list_item(self) -> None:
        # Markdown closes a fence on a run up to three spaces in from its list item's content column,
        # however far in it opened, so what follows is findings, a later fence quoting a fixture among them.
        for indent in (" ", "  ", "   "):
            transcript = f"```text\n7924 passed\n{indent}```"
            _assert_malformed_shown(
                self,
                (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{transcript}\n{_END_LINE}\n\n{_CLOSING}", _CLOSING),
                (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{transcript}\n\n{_CLOSING}", _CLOSING),
                (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{transcript}\n\n{_QUOTING}\n\n{_FIXTURE}", _FIXTURE_SHOWN),
            )
        # Four spaces in, a run is the fence's content however far in the fence opened, so the fixture
        # below it stays quoted output and the diagnostic below that stays the failing check's.
        _assert_malformed_shown(
            self,
            (f"{_RUN_LINE}\n{_INDENTED_FIXTURE_STEP}{_END_LINE}", _INDENTED_FIXTURE_SHOWN),
            (f"{_RUN_LINE}\n{_INDENTED_FIXTURE_STEP}\n{_CLOSING}", f"{_INDENTED_FIXTURE_SHOWN}\n\n{_CLOSING}"),
        )

    def test_list_item_ending_ends_its_fence(self) -> None:
        # A line set in less than the list item's content column ends the item, and a fence it held
        # with no closing run, so the findings below stay whether or not the block is closed.
        _assert_malformed_shown(
            self,
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n- ```text\n  All tests passed\n\n{_LIST_FINDING}", _LIST_FINDING),
            (
                f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n- output:\n  ```text\n  All tests passed\n\n{_LIST_FINDING}",
                _LIST_FINDING,
            ),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n- ```text\n  All tests passed\n{_END_LINE}\n\n{_CLOSING}", _CLOSING),
        )

    def test_lazy_lines_and_breaks_read_as_markdown(self) -> None:
        # A lazy line keeps its list item open, so a fence set in the item is read there, and a
        # thematic break opens no item, so a fence below it is read at the top level: either way the
        # fixture is quoted and its diagnostic stays, below a cut-short block too.
        for finding, shown in ((_LAZY_FINDING, _LAZY_SHOWN), (_BROKEN_FINDING, _BROKEN_SHOWN)):
            _assert_shown(self, finding, shown)
            _assert_malformed_shown(self, (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{finding}", shown))

    def test_indented_code_reads_as_a_quote(self) -> None:
        # Markdown shows indented code as code, so it reads as a fence with no fence lines: a fixture it
        # quotes keeps its diagnostic in the findings, in a list item, and below a cut-short block, and a
        # failing step it quotes under a passing check is shown.
        _assert_shown(self, _INDENTED_FINDING, _INDENTED_SHOWN)
        _assert_shown(self, _ITEM_CODE_FINDING, _ITEM_CODE_SHOWN)
        _assert_malformed_shown(
            self,
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{_INDENTED_FINDING}", _INDENTED_SHOWN),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{_INDENTED_FAILURE}\n{_END_LINE}", _INDENTED_FAILURE_SHOWN),
        )

    def test_ordered_marker_after_prose_opens_no_list(self) -> None:
        # Only a bullet or a marker numbered 1 interrupts a paragraph, so a later number goes on with the
        # prose, and the fence below is read at the top level with its fixture quoted.
        _assert_shown(self, _ORDERED_FINDING, _ORDERED_SHOWN)
        _assert_malformed_shown(self, (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n\n{_ORDERED_FINDING}", _ORDERED_SHOWN))

    def test_dropped_check_shows_failing_quoted_steps(self) -> None:
        # A fence below a check that passed, or said nothing, may list the block's next checks, so
        # a step it quotes that did not pass is shown though the check's output goes.
        _assert_malformed_shown(
            self,
            (f"{_RUN_LINE}\n{_RUFF_STEP}\n\n{_FENCED_FAILURE}\n{_END_LINE}", _FENCED_FAILURE_SHOWN),
            (f"{_RUN_LINE}\n{_RUFF_STEP}\n\n{_FENCED_FAILURE}\n\n{_CLOSING}", f"{_FENCED_FAILURE_SHOWN}\n\n{_CLOSING}"),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{_BARE_FENCED_FAILURE}\n{_END_LINE}", _BARE_FAILURE_SHOWN),
            (f"{_RUN_LINE}\n{_LINT}\n{_BARE_FENCED_FAILURE}\n{_END_LINE}", _BARE_FAILURE_SHOWN),
        )

    def test_wrapping_fence_keeps_output_with_check(self) -> None:
        _assert_malformed_shown(
            self,
            (f"{_FINDINGS}\n\n```\n{_PASSING_BLOCK}\n```\n\n{_CLOSING}", f"{_FINDINGS}\n\n{_CLOSING}"),
            # A fence never closed reads as one closed at the end.
            (f"{_FINDINGS}\n\n```\n{_PASSING_BLOCK}", _FINDINGS),
            # Holding less than a whole declaration, a fence may be quoting one: its text
            # stays, its protocol hidden.
            (
                f"{_FINDINGS}\n\n~~~text\n{_RUN_LINE}\n{_ATTACHED_FAILING_STEP}~~~\n{_CLOSING}",
                f"{_FINDINGS}\n\n~~~text\n{_FAILING_OUTPUT}~~~\n{_CLOSING}",
            ),
            # A closing line inside a check's output fence leaves the output with its check.
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n```text\n7921 passed\n{_END_LINE}\n```\n\n{_CLOSING}", _CLOSING),
            (
                f"{_RUN_LINE}\n{_LINT}\nEXIT: 1\n```text\nlint.py:3: E501\n{_END_LINE}\n```",
                f"{_UNNAMED}`make lint` exited with status 1:\n\n````\n```text\nlint.py:3: E501\n```\n````",
            ),
            # Below a command or exit line, a fence quoting protocol lines among its output is that
            # check's output, marker lines and all, and what it quotes passes nothing.
            (
                f"{_FINDINGS}\n\n{_RUN_LINE}\n{_LINT}\nEXIT: 1\n{_QUOTED_PROTOCOL}\n{_END_LINE}\n\n{_CLOSING}",
                (
                    f"{_FINDINGS}\n\n{_UNNAMED}`make lint` exited with status 1:\n\n````\n{_QUOTED_FAILURE}\n````\n\n"
                    f"{_CLOSING}"
                ),
            ),
            (
                f"{_RUN_LINE}\n{_LINT}\nEXIT: 1\nlint failed:\n{_QUOTED_PROTOCOL}\n\n{_CLOSING}",
                (
                    f"{_UNNAMED}`make lint` exited with status 1:\n\n````\nlint failed:\n{_QUOTED_FAILURE}\n````\n\n"
                    f"{_CLOSING}"
                ),
            ),
            (f"{_RUN_LINE}\n{_LINT}\nEXIT: 0\n{_QUOTED_PROTOCOL}\n{_END_LINE}\n\n{_CLOSING}", _CLOSING),
            (
                f"{_FINDINGS}\n\n{_RUN_LINE}\n{_LINT}\n{_QUOTED_PROTOCOL}\n{_END_LINE}\n\n{_CLOSING}",
                (
                    f"{_FINDINGS}\n\n{_UNNAMED}`make lint` reported no exit status:\n\n"
                    f"````\n{_QUOTED_FAILURE}\n````\n\n{_CLOSING}"
                ),
            ),
            (
                f"{_RUN_LINE}\n{_LINT}\nEXIT: 1\n{_QUOTED_MARKER}\n{_END_LINE}",
                f"{_UNNAMED}`make lint` exited with status 1:\n\n````\n{_QUOTED_FAILURE}\n````",
            ),
            # Holding nothing but step lines there, it is still output: it goes whole, and the
            # diagnostic below it stays the failing check's.
            (f"{_RUN_LINE}\n{_BARE_FIXTURE_STEP}{_END_LINE}", _BARE_FIXTURE_SHOWN),
            (f"{_FINDINGS}\n\n{_RUN_LINE}\n{_BARE_FIXTURE_STEP}", f"{_FINDINGS}\n\n{_BARE_FIXTURE_SHOWN}"),
            # Right below a RUN line, a fence holding step lines wraps the checks they list.
            (
                f"{_RUN_LINE}\n```\n{_RUFF_STEP}\n{_LINT}\nEXIT: 2\n```\n{_END_LINE}",
                f"{_UNNAMED}{_NO_OUTPUT}`make lint` exited with status 2.",
            ),
            # Parted from the RUN line by a finding, it is the findings quoting a fixture.
            (f"{_RUN_LINE}\n\n{_QUOTING}\n\n{_FIXTURE}", _FIXTURE_SHOWN),
            (
                f"{_RUN_LINE}\n\n{_QUOTING}\n\n{_FIXTURE}\n{_END_LINE}",
                f"{_UNNAMED}A check naming no command reported no exit status:\n\n````\n{_FIXTURE_SHOWN}\n````",
            ),
        )


class FailureNamesTest(unittest.TestCase):
    """Each check shown failing leads with what failed, its command and exit status below as supporting details.

    Every case is formatted twice too (`_assert_shown`): a lead is no
    declaration line, so what was shown formats to itself.
    """

    def test_pytest_failures_lead_by_exact_id(self) -> None:
        # Each failure pytest's summary reports leads by its node ID exactly as
        # pytest printed it, with its error; a failure nothing names alone
        # stays behind the line saying so.
        _assert_shown(
            self,
            f"{_FINDINGS}\n\n{_RUN_LINE}\n{_SUITE}\nEXIT: 1\n{_SUMMARY}\n{_END_LINE}",
            f"{_FINDINGS}\n\n{_SUMMARY_LEAD}`uv run pytest tests` exited with status 1:\n\n```\n{_SUMMARY}\n```",
        )
        failed = "\n".join(f"FAILED tests/test_c.py::test_{number}" for number in range(_FAILED_TESTS))
        named = "".join(f"Failure: `tests/test_c.py::test_{number}`\n{_UNSTATED}" for number in range(_NAMED_TESTS))
        _assert_shown(
            self,
            f"{_RUN_LINE}\n{_SUITE}\nEXIT: 1\n{failed}\n{_END_LINE}",
            f"{named}Failure: 2 more, named in the output below\n"
            f"`uv run pytest tests` exited with status 1:\n\n```\n{failed}\n```",
        )
        # A dash quoted inside an argument, or passed to a program given
        # before it, is no stdin the command reads its code from.
        quoted = f"FAILED {_QUOTED_NODE} - assert 0 == 1"
        for command in _ARGUMENT_DASHES:
            with self.subTest(command=command):
                _assert_shown(
                    self,
                    f"{_RUN_LINE}\nCOMMAND: {command}\nEXIT: 1\n{quoted}\n{_END_LINE}",
                    f"Failure: `{_QUOTED_NODE}`\nError: `assert 0 == 1`\n"
                    f"`{command}` exited with status 1:\n\n```\n{quoted}\n```",
                )

    def test_probes_sharing_a_command_stay_apart(self) -> None:
        # Two runs of one stdin command are two checks, each led by the entry
        # whose error its output shows -- a code block's last line for an error
        # quoted as one -- whatever order the entries stand in; the entries and
        # their snippets stay as written, and the declaration as it ran.
        findings = (
            f"{_PROBE_ENTRIES}\n\n{_RUN_LINE}\n{_PROBE}\nEXIT: 1\n{_RELABEL_ERROR}\n"
            f"{_PROBE}\nEXIT: 1\n{_ANNOUNCE_ERROR}\n{_END_LINE}"
        )
        declared = review_verification._parse_verification_outcome(findings, _SUBJECT)

        self.assertEqual(
            [(ran.command, ran.exit_status) for ran in declared.commands],
            [(".venv/bin/python -", 1), (".venv/bin/python -", 1)],
        )
        _assert_shown(
            self,
            findings,
            f"{_PROBE_ENTRIES}\n\n"
            "Failure: A failed relabel request revives settled evidence\n"
            f"`.venv/bin/python -` exited with status 1:\n\n```\n{_RELABEL_ERROR}\n```\n\n"
            "Failure: A lost announcement revives settled evidence\n"
            f"`.venv/bin/python -` exited with status 1:\n\n```\n{_ANNOUNCE_ERROR}\n```",
        )

    def test_sections_say_what_failed(self) -> None:
        # A module pytest could not collect is named by that collection, never
        # by a test ID, with the exception its section shows, else the error of
        # the entry naming it, else a line saying the summary gave none; and a
        # summary line too long to carry its error takes the exception of the
        # section it reports.
        cases = (
            (
                _COLLECTION_TRACEBACK,
                "",
                f"{_UNCOLLECTED_NAME}Error: `ModuleNotFoundError: No module named 'nowhere'`\n",
            ),
            (_UNCOLLECTED, _COLLECTION_ENTRY, f"{_UNCOLLECTED_NAME}Error: `ImportError: cannot import name 'thing'`\n"),
            (_UNCOLLECTED, "", f"{_UNCOLLECTED_NAME}{_UNSTATED}"),
            # An entry naming a test in that module names another failure.
            (_UNCOLLECTED, _TEST_ENTRY, f"{_UNCOLLECTED_NAME}{_UNSTATED}"),
            # A word reading as no path is no collection pytest reports.
            ("ERROR 404", "", _UNNAMED),
            # A node ID names a collection where pytest says it failed collecting
            # its path, or that collection was interrupted; and a setup where a
            # section says that failed; and, nothing saying which, an error in
            # any of the three.
            (f"{_CLASS_SECTION}\n{_CLASS_ERROR} - RuntimeError: class construction exploded", "", (
                f"{_CLASS_NAME}{_CLASS_EXPLODED}"
            )),
            (f"{_CLASS_SECTION}\n{_CLASS_ERROR}", "", f"{_CLASS_NAME}{_CLASS_EXPLODED}"),
            (f"{_CLASS_ERROR}\n{_INTERRUPTED}", "", f"{_CLASS_NAME}{_UNSTATED}"),
            (f"{_SETUP_SECTION}\n{_SETUP_ERROR}", "", (
                f"Failure: `tests/test_a.py::test_setup`, whose setup failed\n{_FIXTURE_EXPLODED}"
            )),
            # A test failing in setup and teardown both: each summary line
            # takes the phase whose section raised its error.
            (_BOTH_PHASES, "", _BOTH_LEAD),
            # A summary line too long to carry its error takes its section's.
            (_UNSTATED_SETUP, "", _UNSTATED_SETUP_LEAD),
            # Sections sharing a title each go to the summary line pytest
            # printed in their turn.
            (_SAME_TITLES, "", _SAME_TITLES_LEAD),
            (_SAME_FIXTURES, "", _SAME_FIXTURES_LEAD),
            # A section's exception is the first line set out least in its
            # last run of marked lines: not an explanation or diff hint set out
            # further, nor an exception another one was raised handling.
            (_DIFF_HINT, "", _DIFF_HINT_LEAD),
            (_CHAINED, "", _CHAINED_LEAD),
            # Failures `--tb=line` printed untitled go to their summary lines
            # in turn; a section holding Python's own traceback shows the
            # exception it ends on.
            (_LINE_TRACEBACKS, "", _LINE_TRACEBACKS_LEAD),
            (_NATIVE_TRACEBACKS, "", _NATIVE_TRACEBACKS_LEAD),
            # An exception group's own exception stands at the margin its rail
            # sets, past the exceptions it holds set further in.
            (_GROUPED, "", _GROUPED_LEAD),
            # A path pytest could not collect may hold blanks, and its message
            # a separator of its own; so may the path a line traceback names,
            # which still goes to its own summary line.
            (_SPACED_UNCOLLECTED, "", _SPACED_UNCOLLECTED_LEAD),
            (_SPACED_LINES, "", _SPACED_LINES_LEAD),
            # What pytest captured from a test is never read as its own: not
            # as a section's exception, a summary line, or a line traceback.
            (_CAPTURED_MARKED, "", _CAPTURED_MARKED_LEAD),
            (_CAPTURED_SUMMARY, "", _CAPTURED_SUMMARY_LEAD),
            (_CAPTURED_UNSUMMARISED, "", _UNNAMED),
            (_CAPTURED_LINES, "", _CAPTURED_LINES_LEAD),
            # Nor is pytest's own output a test printed: only the last short
            # summary of a run is the run's, and a whole run printed below a
            # rule is captured to its statistics -- unless a test cut it short,
            # which hides nothing below it.
            (_PRINTED_SUMMARY, "", _OUTER_LEAD),
            (_NESTED_SUMMARISED, "", _NESTED_SUMMARISED_LEAD),
            (_NESTED_UNSUMMARISED, "", _UNNAMED),
            (_CUT_RUN, "", _OUTER_LEAD),
            (_TWO_RUNS, "", _TWO_RUNS_LEAD),
            (_NESTED_TITLES, "", _NESTED_TITLES_LEAD),
            (_QUIET_RUNS, "", _QUIET_RUNS_LEAD),
            (_QUIET_UNCOLLECTED, "", _QUIET_UNCOLLECTED_LEAD),
            (_QUIET_SKIPPED, "", _QUIET_FIRST_LEAD),
        )
        for output, written, lead in cases:
            with self.subTest(output=output, written=written):
                _assert_shown(
                    self,
                    f"{written}{_RUN_LINE}\n{_SUITE}\nEXIT: 2\n{output}\n{_END_LINE}",
                    f"{written}{lead}`uv run pytest tests` exited with status 2:\n\n```\n{output}\n```",
                )

    def test_ids_end_where_they_are_named(self) -> None:
        # A parameter may hold the dash that parts an ID from its message, and
        # text of a message's shape after it: the ID is the longest an entry
        # names whole, or pytest titled a section by, and otherwise ends on the
        # last split leaving a message of pytest's shape.
        cases = (
            ("", _SHAPED_SUMMARY, _SHAPED_FULL),
            (_SHAPED_ENTRY, _SHAPED_SUMMARY, _SHAPED_FULL),
            ("", f"{_SHAPED_SECTION}\n{_SHAPED_MESSAGE}", _SHAPED_SHORT),
            (_SHORT_ENTRY, _SHAPED_MESSAGE, _SHAPED_SHORT),
            # A section names a test by its classes dotted, its parameters as
            # they are, a separator they hold included.
            ("", _SEPARATED, _SEPARATED_LEAD),
            # A long title is padded by a single underscore each side, and a
            # frame separator is no title; a summary line too long to carry its
            # error takes the first exception line of the test's section.
            ("", _LONG_OUTPUT, _LONG_LEAD),
            # A test's file path may hold blanks.
            ("", _SPACED, _SPACED_LEAD),
        )
        for written, output, lead in cases:
            with self.subTest(written=written, output=output):
                _assert_shown(
                    self,
                    f"{written}{_RUN_LINE}\n{_SUITE}\nEXIT: 1\n{output}\n{_END_LINE}",
                    f"{written}{lead}`uv run pytest tests` exited with status 1:\n\n```\n{output}\n```",
                )

    def test_missing_diagnostics_are_said(self) -> None:
        # A failure nothing names, that quoted no output, or that a stdin
        # command ran with no snippet given -- the command alone named as its
        # reproduction, or a fence holding no code below it, included -- stays,
        # saying what is missing; an entry quoted in a code block, or backing
        # another check, names nothing.
        cases = (
            ("", _RELABEL_ERROR, f"{_UNNAMED}{_STDIN_UNREPRODUCED}{_PROBE_FAILED}"),
            (_QUOTED_ENTRY, _RELABEL_ERROR, f"{_QUOTED_ENTRY}{_UNNAMED}{_STDIN_UNREPRODUCED}{_PROBE_FAILED}"),
            (
                _UNREPRODUCED_ENTRY,
                _RELABEL_ERROR,
                f"{_UNREPRODUCED_SHOWN}Failure: A probe\n{_STDIN_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            (
                _COMMAND_ONLY_ENTRY,
                _RELABEL_ERROR,
                f"{_COMMAND_ONLY_ENTRY}Failure: A probe\n{_STDIN_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            # A stdin check pytest names the failure of says no snippet too.
            ("", _STDIN_PYTEST, _STDIN_PYTEST_SHOWN),
            (
                _EMPTY_FENCE_ENTRY,
                _RELABEL_ERROR,
                f"{_EMPTY_FENCE_ENTRY}Failure: A probe\n{_STDIN_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            (
                _BLANK_FENCE_ENTRY,
                _RELABEL_ERROR,
                f"{_BLANK_FENCE_ENTRY}Failure: A probe\n{_STDIN_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            (
                _UNREPRODUCED_ENTRY,
                _ANNOUNCE_ERROR,
                (
                    f"{_UNREPRODUCED_SHOWN}{_UNNAMED}{_STDIN_UNREPRODUCED}"
                    f"{_PROBE_FAILED.replace(_RELABEL_ERROR, _ANNOUNCE_ERROR)}"
                ),
            ),
            (
                f"{_PROBE_ENTRIES}\n\n",
                "",
                (
                    f"{_PROBE_ENTRIES}\n\n{_UNNAMED}{_NO_OUTPUT}{_STDIN_UNREPRODUCED}"
                    "`.venv/bin/python -` exited with status 1."
                ),
            ),
        )
        for written, output, shown in cases:
            with self.subTest(written=written, output=output):
                step = f"{_PROBE}\nEXIT: 1\n{output}".rstrip("\n")
                _assert_shown(self, f"{written}{_RUN_LINE}\n{step}\n{_END_LINE}", shown)

    def test_previous_layout_is_led(self) -> None:
        # Feedback a tick before leads formatted holds no declaration, so each
        # check is read off the paragraph its sentence opens -- over its fenced
        # output, or alone -- and led as a live round's is. A sentence that
        # opens no paragraph, goes on with one, or a code block holds is the
        # reviewer's own text.
        previous = f"{_FINDINGS}\n\n`uv run pytest tests` exited with status 1:\n\n```\n{_SUMMARY}\n```"
        bare = "`make lint` exited with status 2."
        kept = (
            f"{_FINDINGS}\n{bare}",
            f"{bare}\nThe linter crashed before reporting.",
            f"```text\n{bare}\n```",
            f"{_FINDINGS}\n\n`uv run pytest tests` exited with status 1:\n\n```text\n{_SUMMARY}\n```",
        )
        _assert_shown(self, previous, previous.replace("\n\n`uv", f"\n\n{_SUMMARY_LEAD}`uv", 1))
        _assert_shown(self, bare, f"{_UNNAMED}{_NO_OUTPUT}{bare}")
        for written in kept:
            with self.subTest(written=written):
                _assert_shown(self, written, written)


class FailureEntriesTest(unittest.TestCase):
    """Each failure entry the reviewer writes is shown as written, what it leaves out said where it stands.

    Every case is formatted twice too (`_assert_shown`): what is said gives
    each label a value, so what was shown formats to itself.
    """

    def test_incomplete_entries_say_what_is_missing(self) -> None:
        # An entry naming nothing, or giving no error or reproduction -- its
        # label blank, or missing -- says so where it stands, in its own
        # indentation: a blank label in place, an error added below its name,
        # a reproduction below all its last label gives, a code block
        # included. The rest stays as written, and a complete entry as it is.
        blank = "Failure:\nError:\nReproduce:"
        unlabeled = (
            "1. Reprove the evidence.\n\n"
            "   Failure: A probe\n"
            "   Expected: the evidence is reproved\n"
            "   Observed: the attempt is released\n\n"
            "   ```text\n"
            "   attempt released\n"
            "   ```"
        )
        cases = (
            (
                blank,
                f"Failure: {_UNNAMED_ENTRY}\nError: {_NO_ENTRY_ERROR}\nReproduce: {_NO_ENTRY_REPRODUCTION}",
            ),
            (
                unlabeled,
                unlabeled.replace(
                    "   Failure: A probe\n", f"   Failure: A probe\n   Error: {_NO_ENTRY_ERROR}\n",
                )
                + f"\n   Reproduce: {_NO_ENTRY_REPRODUCTION}",
            ),
            (f"{_PROBE_ENTRIES}", f"{_PROBE_ENTRIES}"),
            # A label over a fence holding no code gives nothing.
            (
                "Failure: A probe\nError:\n\n```text\n```\nReproduce:\n\n```python\n   \n```",
                (
                    f"Failure: A probe\nError: {_NO_ENTRY_ERROR}\n\n```text\n```\n"
                    f"Reproduce: {_NO_ENTRY_REPRODUCTION}\n\n```python\n   \n```"
                ),
            ),
            # A reproduction said right above a sentence of the reviewer's
            # opens no lead, so showing it again says it no twice.
            (
                "Failure: Linter crashes\nError:\n```\nSegmentation fault\n```\n`make lint` exited with status 139.",
                (
                    "Failure: Linter crashes\nError:\n```\nSegmentation fault\n```\n"
                    f"Reproduce: {_NO_ENTRY_REPRODUCTION}\n`make lint` exited with status 139."
                ),
            ),
        )
        for written, shown in cases:
            with self.subTest(written=written):
                _assert_shown(self, written, shown)
        _assert_shown(
            self,
            f"Failure: A probe\nError:\nReproduce:\n\n{_RUN_LINE}\n{_PROBE}\nEXIT: 1\nprobe started\n{_END_LINE}",
            f"Failure: A probe\nError: {_NO_ENTRY_ERROR}\nReproduce: {_NO_ENTRY_REPRODUCTION}\n\n"
            f"{_UNNAMED}{_STDIN_UNREPRODUCED}"
            "`.venv/bin/python -` exited with status 1:\n\n```\nprobe started\n```",
        )

    def test_entries_end_at_the_next_finding(self) -> None:
        # An entry ends at the next finding -- a list item or a heading set
        # out no further, or a paragraph set out less -- so a later finding's
        # label never stands for one it leaves out; a paragraph of its own
        # finding's ends nothing.
        _assert_shown(
            self,
            _FINDINGS_APART,
            _FINDINGS_APART.replace("expected 1\n", f"expected 1\n   Reproduce: {_NO_ENTRY_REPRODUCTION}\n"),
        )
        # What an entry leaves out is said above the next finding even where
        # that opens right below its last label, so it is said once.
        for written, indent in _ADJACENT_FINDINGS:
            with self.subTest(written=written):
                said = f"expected 1\n{indent}Reproduce: {_NO_ENTRY_REPRODUCTION}\n"
                _assert_shown(self, written, written.replace("expected 1\n", said))

    def test_entries_read_across_the_declaration(self) -> None:
        # Entries are read across the findings whole, the declaration's place
        # aside, so a reproduction written below it is the entry's above it.
        _assert_shown(
            self,
            f"{_PROBE_ENTRY}{_RUN_LINE}\n{_PROBE}\nEXIT: 1\n{_RELABEL_ERROR}\n{_END_LINE}\n\n{_PROBE_SNIPPET}",
            f"{_PROBE_ENTRY}Failure: A probe\n{_PROBE_FAILED}\n\n{_PROBE_SNIPPET}",
        )


def _assert_malformed_shown(case: unittest.TestCase, *cases: tuple[str, str]) -> None:
    """Each case's findings hold a malformed declaration, and are shown as its second half."""
    for findings, shown in cases:
        with case.subTest(findings=findings):
            case.assertIs(
                review_verification._parse_verification_outcome(findings, _SUBJECT),
                _VerificationRefusal.MALFORMED,
            )
            _assert_shown(case, findings, shown)


def _assert_shown(case: unittest.TestCase, findings: str, shown: str) -> None:
    """`findings` are shown as `shown`, which formats to itself and declares nothing.

    The layout before leads showed `findings` as is shown as `shown` too, so
    feedback a tick of that layout persisted or posted is shown as a live
    round's is.
    """
    previous = review_findings._unled_findings(findings)
    case.assertEqual(review_findings._concise_findings(findings), shown)
    case.assertEqual(review_findings._concise_findings(shown), shown)
    case.assertEqual(review_findings._concise_findings(previous), shown)
    case.assertIsNone(_PROTOCOL_LINE_RE.search(shown))
    case.assertIs(
        review_verification._parse_verification_outcome(shown, _SUBJECT),
        _VerificationRefusal.MISSING,
    )


if __name__ == "__main__":
    unittest.main()
