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
# test's node ID whole, parameters with spaces and dashes included, then the
# message after a dash, however pytest cut it short -- and a test that errored
# in its fixture.
_SUITE = "COMMAND: uv run pytest tests"
_SUMMARY = (
    "FAILED tests/test_a.py::test_fail - AssertionError: values differ - badly\n"
    "FAILED tests/test_a.py::test_param[a b] - AssertionError: assert 'a b' == 'nope'\n"
    "FAILED tests/test_a.py::test_param[lost-response] - AssertionError: assert 'lost-re...\n"
    "FAILED tests/test_a.py::test_param[x - y] - AssertionError: assert 'x - y' == 'nope'\n"
    "FAILED tests/test_a.py::TestK::test_m - KeyError: 'VERIFY_COMMANDS'\n"
    "ERROR tests/test_a.py::test_setup - RuntimeError: fixture exploded\n"
    "5 failed, 1 passed, 1 error in 0.02s"
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
    "Failure: `tests/test_a.py::test_setup`, which errored outside the test itself\n"
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
# reproduction, and how the run printing its error is shown.
_QUOTED_ENTRY = f"```text\nFailure: A probe\nError: {_RELABEL_ERROR}\n```\n\n"
_UNREPRODUCED_ENTRY = f"Failure: A probe\nError: {_RELABEL_ERROR}\n\n"
_PROBE_FAILED = f"`.venv/bin/python -` exited with status 1:\n\n```\n{_RELABEL_ERROR}\n```"
# Entries for the module pytest could not collect, and for a test in it, which is another failure.
_COLLECTION_ENTRY = "Failure: pytest collection of tests/test_b.py\nError: ImportError: cannot import name 'thing'\n\n"
_TEST_ENTRY = "Failure: tests/test_b.py::test_x\nError: ImportError: cannot import name 'thing'\n\n"
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

    def test_collection_errors_name_the_failed_check(self) -> None:
        # A module pytest could not collect is named by that collection, never
        # by a test ID, with the exception its traceback ends on, else the
        # error of the entry naming it, else a line saying the summary gave none.
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
        )
        for output, written, lead in cases:
            with self.subTest(output=output, written=written):
                _assert_shown(
                    self,
                    f"{written}{_RUN_LINE}\n{_SUITE}\nEXIT: 2\n{output}\n{_END_LINE}",
                    f"{written}{lead}`uv run pytest tests` exited with status 2:\n\n```\n{output}\n```",
                )

    def test_missing_diagnostics_are_said(self) -> None:
        # A failure nothing names, that quoted no output, or that a stdin
        # command ran with no snippet given stays, saying what is missing; an
        # entry quoted in a code block, or backing another check, names nothing.
        cases = (
            ("", _RELABEL_ERROR, f"{_UNNAMED}{_STDIN_UNREPRODUCED}{_PROBE_FAILED}"),
            (_QUOTED_ENTRY, _RELABEL_ERROR, f"{_UNNAMED}{_STDIN_UNREPRODUCED}{_PROBE_FAILED}"),
            (_UNREPRODUCED_ENTRY, _RELABEL_ERROR, f"Failure: A probe\n{_STDIN_UNREPRODUCED}{_PROBE_FAILED}"),
            (
                _UNREPRODUCED_ENTRY,
                _ANNOUNCE_ERROR,
                f"{_UNNAMED}{_STDIN_UNREPRODUCED}{_PROBE_FAILED.replace(_RELABEL_ERROR, _ANNOUNCE_ERROR)}",
            ),
            (
                f"{_PROBE_ENTRIES}\n\n",
                "",
                f"{_UNNAMED}{_NO_OUTPUT}{_STDIN_UNREPRODUCED}`.venv/bin/python -` exited with status 1.",
            ),
        )
        for written, output, shown in cases:
            with self.subTest(written=written, output=output):
                step = f"{_PROBE}\nEXIT: 1\n{output}".rstrip("\n")
                _assert_shown(self, f"{written}{_RUN_LINE}\n{step}\n{_END_LINE}", f"{written}{shown}")


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
    """`findings` are shown as `shown`, which formats to itself and declares nothing."""
    case.assertEqual(review_findings._concise_findings(findings), shown)
    case.assertEqual(review_findings._concise_findings(shown), shown)
    case.assertIsNone(_PROTOCOL_LINE_RE.search(shown))
    case.assertIs(
        review_verification._parse_verification_outcome(shown, _SUBJECT),
        _VerificationRefusal.MISSING,
    )


if __name__ == "__main__":
    unittest.main()
