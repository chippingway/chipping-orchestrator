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
# A stdin check backed by an entry giving no snippet, which its line names;
# and by two named probes, the first giving its snippet and the second none,
# which the second's line says whatever the first gives.
_PROBE_UNREPRODUCED = _STDIN_UNREPRODUCED.replace("was given\n", "was given for A probe\n")
_PAIRED_PROBES = (
    "Failure: First named probe\nError: AssertionError: first\n"
    "Reproduce: `.venv/bin/python -`\n\n"
    "```python\nraise AssertionError('first')\n```\n\n"
    "Failure: Second named probe\nError: AssertionError: second\n"
    "Reproduce: `.venv/bin/python -`\n\n"
)
_PAIRED_OUTPUT = "AssertionError: first\nAssertionError: second"
_PAIRED_PROBES_SHOWN = (
    f"{_PAIRED_PROBES}Failure: First named probe\nFailure: Second named probe\n"
    f"{_STDIN_UNREPRODUCED.replace('was given', 'was given for Second named probe')}"
    f"`.venv/bin/python -` exited with status 1:\n\n```\n{_PAIRED_OUTPUT}\n```"
)
# What parts the paragraphs findings are shown in.
_PARAGRAPHS = "\n\n"
# Two named probes whose errors overlap, the first's opening the second's,
# and their two runs, then a third run whose error a word runs on into: each
# run is led by the entry whose error ends a line of its output, never by one
# that output only holds, and the third by none.
_OVERLAPPING_PROBES = _PARAGRAPHS.join(
    f"Failure: {name}\nError: AssertionError: {error}\nReproduce: `.venv/bin/python -` reading:\n\n"
    f"```python\nraise AssertionError({error!r})\n```"
    for name, error in (("Short error probe", "stale"), ("Long error probe", "stale report"))
)
_OVERLAPPING_RUNS = ("AssertionError: stale", "AssertionError: stale report", "WrappedAssertionError: stale")
_OVERLAPPING_LEADS = (
    "Failure: Short error probe\n",
    "Failure: Long error probe\n",
    f"{_UNNAMED}{_STDIN_UNREPRODUCED}",
)
_OVERLAPPING_RAN = "".join(f"{_PROBE}\nEXIT: 1\n{output}\n" for output in _OVERLAPPING_RUNS)
_OVERLAPPING_SHOWN = _PARAGRAPHS.join((
    _OVERLAPPING_PROBES,
    *(
        f"{lead}`.venv/bin/python -` exited with status 1:\n\n```\n{output}\n```"
        for lead, output in zip(_OVERLAPPING_LEADS, _OVERLAPPING_RUNS, strict=True)
    ),
))
# Two named probes whose runs print errors of the shape pytest refuses a run
# in, `ERROR:` and a message, and how their runs are shown: each led by the
# scenario its entry names, as any probe's is.
_REFUSAL_RUNS = (("Stale report probe", "ERROR: stale report"), ("Lost receipt probe", "ERROR: lost receipt"))
_REFUSAL_PROBES = _PARAGRAPHS.join(
    f"Failure: {name}\nError: {error}\nReproduce: `.venv/bin/python -` reading:\n\n"
    f"```python\nraise SystemExit({error!r})\n```"
    for name, error in _REFUSAL_RUNS
)
_REFUSAL_RAN = "".join(f"{_PROBE}\nEXIT: 1\n{error}\n" for _name, error in _REFUSAL_RUNS)
_REFUSAL_SHOWN = _PARAGRAPHS.join((
    _REFUSAL_PROBES,
    *(
        f"Failure: {name}\n`.venv/bin/python -` exited with status 1:\n\n```\n{error}\n```"
        for name, error in _REFUSAL_RUNS
    ),
))
# pytest refusing a run before it ran any test: a path it could not find, and
# an argument its parser could not read, the usage line above it aside.
_REFUSED_LEAD = "Failure: the check's run itself, which reported this error before naming any test or scenario\n"
_UNFOUND_PATH = "ERROR: file or directory not found: __missing__.py\n\nno tests ran in 0.00s"
_UNFOUND_PATH_LEAD = f"{_REFUSED_LEAD}Error: `file or directory not found: __missing__.py`\n"
_UNPARSED_ARGUMENT = (
    "ERROR: usage: python -m pytest [options] [file_or_dir] [file_or_dir] [...]\n"
    "python -m pytest: error: unrecognized arguments: --bogus-flag\n"
    "  inifile: None\n"
    "  rootdir: /tmp/run"
)
_UNPARSED_ARGUMENT_LEAD = f"{_REFUSED_LEAD}Error: `unrecognized arguments: --bogus-flag`\n"
# An entry the reviewer wrote for the path pytest could not find.
_UNFOUND_ENTRY = (
    "Failure: Missing module run\nError: file or directory not found: __missing__.py\n"
    "Reproduce: .venv/bin/python -m pytest __missing__.py\n\n"
)
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
# Where nothing names the ID, it ends where the message may first begin, the
# lead saying where it ends is unavailable when a later split would do too.
_UNSURE = (
    "Unavailable: where the test ID ends; pytest's summary line could part it from its message at a later"
    " dash too, the ID running on into the error shown\n"
)
_SHAPED_UNSURE = (
    "Failure: `tests/test_parameter.py::test_value[left]`\n"
    f"Error: `Error: right] - AssertionError: values differ`\n{_UNSURE}"
)
# Entries naming each ID exactly.
_SHAPED_ENTRY = (
    f"Failure: `{_SHAPED_NODE}`\nError: AssertionError: values differ\nReproduce: pytest '{_SHAPED_NODE}'\n\n"
)
_SHORT_ENTRY = "Failure: tests/test_x.py::test_x[a]\nError: AssertionError: got\nReproduce: pytest tests/test_x.py\n\n"
# A test whose setup and teardown both failed, as pytest prints it.
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
# Sections as pytest prints them on an 80-column terminal, summary lines too
# long to carry their errors: a fixture's, tests of two modules sharing a
# name, and subtests, each titled by its test's name and its description.
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
_SUMMARY_HEADING = "=========================== short test summary info ============================\n"
_LINE_MODULE = "tests/test_failure_with_a_long_module_name_to_fill_the_terminal.py"
_SUBTESTS_SECTIONED = (
    "________________________ TestCase.test_values (value=1) ________________________\n"
    "E               AssertionError: 1 != 0\n"
    "________________________ TestCase.test_values (value=2) ________________________\n"
    "E               AssertionError: 2 != 0\n"
    "_______________________ test_fixture [first case] (n=3) ________________________\n"
    "E           assert 1 == 2\n"
    f"{_SUMMARY_HEADING}"
    f"SUBFAILED(value=1) {_LINE_MODULE}::TestCase::test_values\n"
    f"SUBFAILED(value=2) {_LINE_MODULE}::TestCase::test_values\n"
    f"SUBFAILED[first case] (n=3) {_LINE_MODULE}::test_fixture"
)
_SUBTESTS_SECTIONED_LEAD = (
    f"Failure: `{_LINE_MODULE}::TestCase::test_values`, subtest `(value=1)`\nError: `AssertionError: 1 != 0`\n"
    f"Failure: `{_LINE_MODULE}::TestCase::test_values`, subtest `(value=2)`\nError: `AssertionError: 2 != 0`\n"
    f"Failure: `{_LINE_MODULE}::test_fixture`, subtest `[first case] (n=3)`\nError: `assert 1 == 2`\n"
)
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
# Two tests whose IDs overlap -- the second's parameter holding the first's
# ID, the dash, and text of the first's message -- reported by two summary
# lines alike, each with the section pytest printed for it; and a run printing
# no section before one titling a section by an ID the first's summary line
# could end on as well: the first keeps its own error, where its ID ends
# unavailable, borrowing no title of another run.
_IDENTICAL_SUMMARY = "FAILED test_probe.py::test_p[x] - ValueError: [y] - TypeError: boom"
_IDENTICAL = (
    "=================================== FAILURES ===================================\n"
    "__________________________________ test_p[x] ___________________________________\n"
    "E   ValueError: [y] - TypeError: boom\n"
    "__________________________ test_p[x] - ValueError: [y] __________________________\n"
    "E   TypeError: boom\n"
    f"{_SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n{_IDENTICAL_SUMMARY}"
)
_IDENTICAL_LEAD = (
    "Failure: `test_probe.py::test_p[x]`\nError: `ValueError: [y] - TypeError: boom`\n"
    "Failure: `test_probe.py::test_p[x] - ValueError: [y]`\nError: `TypeError: boom`\n"
)
_QUIET_PROGRESS = "F                                                                        [100%]\n"
_BORROWED = (
    f"{_QUIET_PROGRESS}{_SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n1 failed in 0.00s\n\n"
    f"{_QUIET_PROGRESS}"
    "=================================== FAILURES ===================================\n"
    "__________________________ test_p[x] - ValueError: [y] __________________________\n"
    f"E   TypeError: boom\n{_SUMMARY_HEADING}{_IDENTICAL_SUMMARY}\n1 failed in 0.01s"
)
_BORROWED_LEAD = (
    f"Failure: `test_probe.py::test_p[x]`\nError: `ValueError: [y] - TypeError: boom`\n{_UNSURE}"
    "Failure: `test_probe.py::test_p[x] - ValueError: [y]`\nError: `TypeError: boom`\n"
)
# A `-q` run whose summary reports a failure, and a run pytest refused after
# it: the error refusing it stands below the statistics closing the first.
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
_REFUSED_LAST = f"{_QUIET_FIRST}{_UNPARSED_ARGUMENT}"
_REFUSED_LAST_LEAD = f"{_QUIET_FIRST_LEAD}{_UNPARSED_ARGUMENT_LEAD}"
# Failures only pytest's sections name: a collection a run printed with `-rN`
# failed; a setup, a teardown, and a test's own failure a run printed with no
# summary, then with one reporting the test alone; a run printed with `-rE`,
# its summary reporting the setup error alone; and a doctest whose section
# pytest titles otherwise than its summary line names it. A test's section
# leads by its title where no summary line reports it.
_ERRORS_HEADING = "==================================== ERRORS ====================================\n"
_TITLED_ONLY = "Failure: `{title}`, as pytest titled its section; no summary line gives its test ID\n"
_UNSUMMARISED_COLLECTION = (
    f"{_ERRORS_HEADING}"
    "_______________________ ERROR collecting test_broken.py ________________________\n"
    "ImportError while importing test module '/tmp/run/test_broken.py'.\n"
    "E   ModuleNotFoundError: No module named 'missing'\n"
    f"{_INTERRUPTED}\n1 error in 0.07s"
)
_UNSUMMARISED_COLLECTION_LEAD = (
    "Failure: collection of `test_broken.py`, before any test in it ran\n"
    "Error: `ModuleNotFoundError: No module named 'missing'`\n"
)
_PHASES_UNSUMMARISED = (
    "E.EF                                                                     [100%]\n"
    f"{_ERRORS_HEADING}"
    "_________________________ ERROR at setup of test_setup _________________________\n"
    "test_probe.py:5: in broken\n"
    '    raise RuntimeError("fixture exploded")\n'
    "E   RuntimeError: fixture exploded\n"
    "______________________ ERROR at teardown of test_teardown ______________________\n"
    "E   KeyError: 'teardown broke'\n"
    "=================================== FAILURES ===================================\n"
    "__________________________________ test_fails __________________________________\n"
    "E   assert 1 == 2\n"
    "1 failed, 1 passed, 2 errors in 0.01s"
)
_SETUP_ONLY = (
    "Failure: setup of `test_setup`, as pytest titled its section; no summary line gives its test ID\n"
    "Error: `RuntimeError: fixture exploded`\n"
)
_PHASES_UNSUMMARISED_LEAD = (
    f"{_SETUP_ONLY}"
    "Failure: teardown of `test_teardown`, as pytest titled its section; no summary line gives its test ID\n"
    "Error: `KeyError: 'teardown broke'`\n"
    f"{_TITLED_ONLY.format(title='test_fails')}Error: `assert 1 == 2`\n"
)
_FAILURES_SUMMARISED = _PHASES_UNSUMMARISED.replace(
    "1 failed, 1 passed, 2 errors in 0.01s",
    f"{_SUMMARY_HEADING}FAILED test_probe.py::test_fails - assert 1 == 2\n1 failed, 1 passed, 2 errors in 0.01s",
)
_FAILURES_SUMMARISED_LEAD = (
    "Failure: `test_probe.py::test_fails`\nError: `assert 1 == 2`\n"
    f"{_SETUP_ONLY}"
    "Failure: teardown of `test_teardown`, as pytest titled its section; no summary line gives its test ID\n"
    "Error: `KeyError: 'teardown broke'`\n"
)
_ERRORS_ONLY = (
    "FE                                                                       [100%]\n"
    f"{_ERRORS_HEADING}"
    "______________________ ERROR at setup of test_setup_error ______________________\n"
    "test_partial_summary.py:6: in broken_setup\n"
    "    raise RuntimeError('setup failed')\n"
    "E   RuntimeError: setup failed\n"
    "=================================== FAILURES ===================================\n"
    "_____________________________ test_primary_failure _____________________________\n"
    "test_partial_summary.py:3: in test_primary_failure\n"
    "    assert False, 'primary failure'\n"
    "E   AssertionError: primary failure\n"
    "E   assert False\n"
    f"{_SUMMARY_HEADING}"
    "ERROR test_partial_summary.py::test_setup_error\n"
    "1 failed, 1 error in 0.01s"
)
_ERRORS_ONLY_LEAD = (
    "Failure: `test_partial_summary.py::test_setup_error`, whose setup failed\n"
    "Error: `RuntimeError: setup failed`\n"
    f"{_TITLED_ONLY.format(title='test_primary_failure')}Error: `AssertionError: primary failure`\n"
)
_DOCTEST_TITLED = (
    "=================================== FAILURES ===================================\n"
    "____________________________ [doctest] sample.txt _____________________________\n"
    "001 >>> 1\nExpected:\n    2\nGot:\n    1\n\n/tmp/run/sample.txt:1: DocTestFailure\n"
    f"{_SUMMARY_HEADING}FAILED sample.txt::sample.txt\n1 failed in 0.01s"
)
# pytest failing before it ran any test: a conftest it could not load, its
# traceback below, and a plugin it could not import, its traceback's last line.
_CONFTEST_UNLOADED = (
    "ImportError while loading conftest '/tmp/run/conftest.py'.\n"
    "/tmp/run/conftest.py:1: in <module>\n"
    "    import missing_dependency\n"
    "E   ModuleNotFoundError: No module named 'missing_dependency'"
)
_CONFTEST_UNLOADED_LEAD = (
    "Failure: conftest `/tmp/run/conftest.py`, which pytest could not load before running any test\n"
    "Error: `ModuleNotFoundError: No module named 'missing_dependency'`\n"
)
_PLUGIN_UNIMPORTED = (
    "Traceback (most recent call last):\n"
    '  File "/venv/lib/python3.12/site-packages/_pytest/config/__init__.py", line 913, in import_plugin\n'
    "    mod = importlib.import_module(importspec)\n"
    'ImportError: Error importing plugin "missing_plugin": No module named \'missing_plugin\''
)
_PLUGIN_UNIMPORTED_LEAD = (
    "Failure: plugin `missing_plugin`, which pytest could not load before running any test\n"
    'Error: `ImportError: Error importing plugin "missing_plugin": No module named \'missing_plugin\'`\n'
)
# A failure printed with `--color=yes`, a terminal's colors among its title,
# its marked line, and its summary line, the node ID's among them.
_COLORED = (
    "\x1b[31mF\x1b[0m\x1b[31m                                                                        [100%]\x1b[0m\n"
    "=================================== FAILURES ===================================\n"
    "\x1b[31m\x1b[1m___________________________________ test_bad ___________________________________\x1b[0m\n"
    "\x1b[1m\x1b[31mE   AssertionError: bad\x1b[0m\n"
    "\x1b[36m\x1b[1m=========================== short test summary info ============================\x1b[0m\n"
    "\x1b[31mFAILED\x1b[0m test_probe.py::\x1b[1mtest_bad\x1b[0m - AssertionError: bad\n"
    "\x1b[31m\x1b[31m\x1b[1m1 failed\x1b[0m\x1b[31m in 0.02s\x1b[0m\x1b[0m"
)
_COLORED_LEAD = "Failure: `test_probe.py::test_bad`\nError: `AssertionError: bad`\n"
# A doctest's text file pytest could not collect, reported with `--tb=no` and
# no section but the run's interruption; and an error line of a check's own,
# whose words name no Python file, that nothing pytest printed says it failed
# collecting.
_DOCTEST_COLLECTED = "Failure: collection of `sample.txt`, before any test in it ran\n"
_DOCTEST_UNTRACED = f"{_SUMMARY_HEADING}ERROR sample.txt\n{_INTERRUPTED}\n1 error in 0.11s"
_UNPYTHONIC_ERROR = "ERROR could not write /tmp/out file - OSError: disk full"
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
# The output a crashing linter's check quoted, fenced below its sentence.
_SEGFAULT = "\n\n```\nSegmentation fault\n```"
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
# Many tests failing in one check, each named by its lead.
_FAILED_TESTS = 12

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
        # However many fail, each leads by its own ID and error.
        failed = "\n".join(
            f"FAILED tests/test_c.py::test_case[{number}] - AssertionError: case {number}"
            for number in range(_FAILED_TESTS)
        )
        named = "".join(
            f"Failure: `tests/test_c.py::test_case[{number}]`\nError: `AssertionError: case {number}`\n"
            for number in range(_FAILED_TESTS)
        )
        _assert_shown(
            self,
            f"{_RUN_LINE}\n{_SUITE}\nEXIT: 1\n{failed}\n{_END_LINE}",
            f"{named}`uv run pytest tests` exited with status 1:\n\n```\n{failed}\n```",
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
        # One entry's error opening another's backs only a run showing it
        # whole, so each run keeps its own scenario.
        _assert_shown(
            self,
            f"{_OVERLAPPING_PROBES}\n\n{_RUN_LINE}\n{_OVERLAPPING_RAN}{_END_LINE}",
            _OVERLAPPING_SHOWN,
        )
        # A run printing an error of the shape pytest refuses a run in is the
        # scenario of the entry giving that error, never pytest's refusal.
        _assert_shown(
            self,
            f"{_REFUSAL_PROBES}\n\n{_RUN_LINE}\n{_REFUSAL_RAN}{_END_LINE}",
            _REFUSAL_SHOWN,
        )

    def test_sections_say_what_failed(self) -> None:
        # A module pytest could not collect is named by that collection, never
        # by a test ID, with the exception its section shows, else the error of
        # the entry naming it, else a line saying the summary gave none.
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
            # Words reading as no path, or naming no Python file, are a
            # collection only where pytest says so.
            ("ERROR 404", "", _UNNAMED),
            (_UNPYTHONIC_ERROR, "", _UNNAMED),
            (_DOCTEST_UNTRACED, "", f"{_DOCTEST_COLLECTED}{_UNSTATED}"),
            # A node ID names a collection where pytest says it failed collecting
            # its path, or that collection was interrupted; and a setup or a
            # teardown where a section says that failed, each summary line
            # taking the phase whose section raised its error.
            (f"{_CLASS_SECTION}\n{_CLASS_ERROR}", "", f"{_CLASS_NAME}{_CLASS_EXPLODED}"),
            (f"{_CLASS_ERROR}\n{_INTERRUPTED}", "", f"{_CLASS_NAME}{_UNSTATED}"),
            (f"{_SETUP_SECTION}\n{_SETUP_ERROR}", "", (
                f"Failure: `tests/test_a.py::test_setup`, whose setup failed\n{_FIXTURE_EXPLODED}"
            )),
            (_BOTH_PHASES, "", _BOTH_LEAD),
            # A summary line too long to carry its error takes the exception
            # of the section it reports: a test's, a fixture's, or a
            # subtest's, titled by its test's name and its description.
            (_SAME_TITLES, "", _SAME_TITLES_LEAD),
            (_UNSTATED_SETUP, "", _UNSTATED_SETUP_LEAD),
            (_SUBTESTS_SECTIONED, "", _SUBTESTS_SECTIONED_LEAD),
            # A collection, a setup, or a teardown a section says failed leads
            # by that section though no summary line reports it; so does,
            # where the run's summary leaves it out, a test's own failure by
            # its section's title -- one a summary line names otherwise
            # leading once, by that line.
            (_UNSUMMARISED_COLLECTION, "", _UNSUMMARISED_COLLECTION_LEAD),
            (_PHASES_UNSUMMARISED, "", _PHASES_UNSUMMARISED_LEAD),
            (_FAILURES_SUMMARISED, "", _FAILURES_SUMMARISED_LEAD),
            (_ERRORS_ONLY, "", _ERRORS_ONLY_LEAD),
            (_DOCTEST_TITLED, "", f"Failure: `sample.txt::sample.txt`\n{_UNSTATED}"),
            # A terminal's colors hide nothing pytest printed.
            (_COLORED, "", _COLORED_LEAD),
            # A conftest or a plugin pytest could not load before running any
            # test leads by that, with the exception its traceback shows.
            (_CONFTEST_UNLOADED, "", _CONFTEST_UNLOADED_LEAD),
            (_PLUGIN_UNIMPORTED, "", _PLUGIN_UNIMPORTED_LEAD),
            # A run pytest refused before running any test leads as the run
            # itself, with the error pytest gave, alone or beside a run its
            # summary names a failure of -- or by the entry giving that error.
            (_UNFOUND_PATH, "", _UNFOUND_PATH_LEAD),
            (_UNFOUND_PATH, _UNFOUND_ENTRY, "Failure: Missing module run\n"),
            (_UNPARSED_ARGUMENT, "", _UNPARSED_ARGUMENT_LEAD),
            (_REFUSED_LAST, "", _REFUSED_LAST_LEAD),
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
        # text of a message's shape after it, as a message may hold a bracket
        # and a dash: the ID is the longest an entry names whole, or pytest
        # titled a section of the line's own run by, and otherwise ends where a
        # message of pytest's shape may first begin, saying where it ends is
        # unavailable when a later split leaves one too.
        cases = (
            ("", _SHAPED_SUMMARY, _SHAPED_UNSURE),
            ("", _SHAPED_MESSAGE, f"{_SHAPED_SHORT}{_UNSURE}"),
            (_SHAPED_ENTRY, _SHAPED_SUMMARY, _SHAPED_FULL),
            ("", f"{_SHAPED_SECTION}\n{_SHAPED_MESSAGE}", _SHAPED_SHORT),
            (_SHORT_ENTRY, _SHAPED_MESSAGE, _SHAPED_SHORT),
            ("", _BORROWED, _BORROWED_LEAD),
            # Two such lines alike each take the first section left showing
            # their error, in pytest's order, so each test keeps its own ID.
            ("", _IDENTICAL, _IDENTICAL_LEAD),
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
                f"{_UNREPRODUCED_SHOWN}Failure: A probe\n{_PROBE_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            (
                _COMMAND_ONLY_ENTRY,
                _RELABEL_ERROR,
                f"{_COMMAND_ONLY_ENTRY}Failure: A probe\n{_PROBE_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            # A stdin check pytest names the failure of says no snippet too.
            ("", _STDIN_PYTEST, _STDIN_PYTEST_SHOWN),
            # One entry's snippet is no other's.
            (_PAIRED_PROBES, _PAIRED_OUTPUT, _PAIRED_PROBES_SHOWN),
            (
                _EMPTY_FENCE_ENTRY,
                _RELABEL_ERROR,
                f"{_EMPTY_FENCE_ENTRY}Failure: A probe\n{_PROBE_UNREPRODUCED}{_PROBE_FAILED}",
            ),
            (
                _BLANK_FENCE_ENTRY,
                _RELABEL_ERROR,
                f"{_BLANK_FENCE_ENTRY}Failure: A probe\n{_PROBE_UNREPRODUCED}{_PROBE_FAILED}",
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
            # A code block nothing closes -- the findings ending, or its list
            # item -- is closed before what is added below it, which stands
            # outside the reviewer's block, so showing it again adds nothing.
            (
                "Failure: Probe\nError:\n\n```text\nAssertionError: boom",
                f"Failure: Probe\nError:\n\n```text\nAssertionError: boom\n```\nReproduce: {_NO_ENTRY_REPRODUCTION}",
            ),
            (
                "1. Finding\n   Failure: Probe\n\n   ~~~~\n   boom\n2. Next finding",
                (
                    f"1. Finding\n   Failure: Probe\n\n   ~~~~\n   boom\n   ~~~~\n   Error: {_NO_ENTRY_ERROR}\n"
                    f"   Reproduce: {_NO_ENTRY_REPRODUCTION}\n2. Next finding"
                ),
            ),
            # Labels right above a check's sentence that give nothing, or give
            # what no lead writes, are no lead the formatting wrote: an entry's.
            (
                f"{blank}\n`make probe` exited with status 1.",
                (
                    f"Failure: {_UNNAMED_ENTRY}\nError: {_NO_ENTRY_ERROR}\nReproduce: {_NO_ENTRY_REPRODUCTION}\n"
                    "`make probe` exited with status 1."
                ),
            ),
            (
                "Failure: A probe\nError: boom\n`make probe` exited with status 1.",
                (
                    f"Failure: A probe\nError: boom\nReproduce: {_NO_ENTRY_REPRODUCTION}\n"
                    "`make probe` exited with status 1."
                ),
            ),
            # Nor is a name and an error in a code span over a sentence saying
            # the check quoted nothing, which a lead says no error was recorded
            # for, or over one closing on a colon, where a lead gives an error
            # only for a failure pytest's output reports.
            (
                "Failure: Linter crashes\nError: `Segmentation fault`\n`make lint` exited with status 139.",
                (
                    "Failure: Linter crashes\nError: `Segmentation fault`\n"
                    f"Reproduce: {_NO_ENTRY_REPRODUCTION}\n`make lint` exited with status 139."
                ),
            ),
            (
                f"Failure: Linter crashes\nError: `Segmentation fault`\n`make lint` exited with status 139:{_SEGFAULT}",
                (
                    "Failure: Linter crashes\nError: `Segmentation fault`\n"
                    f"Reproduce: {_NO_ENTRY_REPRODUCTION}\n`make lint` exited with status 139:{_SEGFAULT}"
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
