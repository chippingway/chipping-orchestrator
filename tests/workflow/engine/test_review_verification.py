# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a completed reviewer run may declare, and nothing else.

Two declarations count: a RUN block listing the exact commands the reviewer
ran on the commit it was handed, and a REUSED line naming the current workflow
evidence revision it inspected. Both are sourced to the reviewer run and kept
as the reviewer wrote them. A missing, malformed, contradictory, truncated, or
stale declaration is refused, the verdict line is read beside it without
either reading the other, and no message is read at all from a run that never
started, was interrupted, timed out, was refused by its provider, or exited
nonzero.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import completion_verdicts, review_verification
from orchestrator.workflow.engine.review_verification_models import (
    _FreshVerification,
    _ReportedCommand,
    _ReusedVerification,
    _ReviewerSource,
    _VerificationRefusal,
    _VerificationSubject,
)
from tests.workflow.agent_failure_values import PROVIDER_OVERLOAD_MESSAGE
from tests.workflow.verdict_values import VERDICT_APPROVED, VERDICT_CHANGES_REQUESTED

_HEAD = "0123456789abcdef0123456789abcdef01234567"
_OTHER_HEAD = "89abcdef0123456789abcdef0123456789abcdef"
_SHA256_HEAD = "fedcba9876543210" * 4
_DIGEST = "0123456789abcdef" * 4
_OTHER_DIGEST = "89abcdef01234567" * 4
_UPPERCASE_DIGEST = _DIGEST.upper()
_SHORT_DIGEST = _DIGEST[:-1]
_SUBJECT = _VerificationSubject(_HEAD, _DIGEST)
_SESSION = "reviewer-session"
_SOURCE = _ReviewerSource(_SESSION, _HEAD)
_UNSOURCED = _ReviewerSource(None, _HEAD)
_INTERRUPTED_EXIT = -15
# Text to Markdown, never a blank.
_NO_BREAK_SPACE = "\N{NO-BREAK SPACE}"

_PYTEST = "uv run pytest tests"
_PYTEST_OUTPUT = "=== 4210 passed, 3 skipped in 812.40s ==="
_RUFF = "uv run ruff check orchestrator tests"
_RUFF_OUTPUT = "All checks passed!"
_DIFF_CHECK = "git diff --check origin/main...HEAD"
_FENCED_OUTPUT = f"```text\n{_PYTEST_OUTPUT}\n```"
# Output that opens on an indented code block and ends on a hard line break.
_INDENTED_OUTPUT = "    tests/foo.py::test_bar PASSED\n\n1 passed  "
_MAX_EXIT_STATUS = 255

_RUN_LINE = f"VERIFICATION: RUN {_HEAD}"
_END_LINE = "VERIFICATION: END"
_REUSED_LINE = f"VERIFICATION: REUSED sha256:{_DIGEST}"
_PYTEST_COMMAND = f"COMMAND: {_PYTEST}"
_EXIT_ZERO = "EXIT: 0"
_PYTEST_STEP = f"{_PYTEST_COMMAND}\n{_EXIT_ZERO}\n{_PYTEST_OUTPUT}"
_RUFF_STEP = f"COMMAND: {_RUFF}\n{_EXIT_ZERO}\n{_RUFF_OUTPUT}"
_RUN_BLOCK = f"{_RUN_LINE}\n{_PYTEST_STEP}\n\n{_RUFF_STEP}\n{_END_LINE}"
_FRESH = _FreshVerification(
    _SOURCE,
    (
        _ReportedCommand(_PYTEST, 0, _PYTEST_OUTPUT),
        _ReportedCommand(_RUFF, 0, _RUFF_OUTPUT),
    ),
)
_APPROVED_LINE = "VERDICT: APPROVED"
_APPROVAL = f"The change matches the issue.\n\n{_APPROVED_LINE}"
_REVIEW = f"Diff reviewed.\n\n{_RUN_BLOCK}\n\n{_APPROVAL}\n"


def _run(*steps: str, commit: str = _HEAD) -> str:
    """A RUN block for `commit` listing `steps`, one per line."""
    lines = "\n".join(steps)
    return f"VERIFICATION: RUN {commit}\n{lines}\n{_END_LINE}"


def _single(output: str, command: str = _PYTEST) -> _FreshVerification:
    """What a block listing `command` alone, exiting 0, is read as."""
    return _FreshVerification(_UNSOURCED, (_ReportedCommand(command, 0, output),))


# Messages that reach for the contract and miss it.
_MALFORMED_MESSAGES = (
    # Truncated: a block never closed, or closed on a line cut short.
    f"{_RUN_LINE}\n{_PYTEST_STEP}",
    f"{_RUN_LINE}\n{_PYTEST_STEP}\nVERIFICATION: EN",
    f"{_PYTEST_STEP}\n{_END_LINE}",
    # A block listing no command, or a step missing a part.
    f"{_RUN_LINE}\n{_END_LINE}",
    f"{_RUN_LINE}\n\n{_PYTEST_OUTPUT}\n{_END_LINE}",
    _run(_PYTEST_COMMAND),
    _run(_PYTEST_COMMAND, _PYTEST_OUTPUT),
    _run(_EXIT_ZERO, _PYTEST_OUTPUT),
    _run("COMMAND:", _EXIT_ZERO),
    _run(f"COMMAND:{_PYTEST}", _EXIT_ZERO),
    _run(_PYTEST_COMMAND, "EXIT:"),
    _run(_PYTEST_COMMAND, "", _EXIT_ZERO),
    _run(_PYTEST_COMMAND, _PYTEST_OUTPUT, _EXIT_ZERO),
    _run(_PYTEST_OUTPUT, _PYTEST_STEP),
    # Contradictory: a second exit status for one command, or two forms.
    _run(_PYTEST_STEP, "EXIT: 1"),
    _run(_PYTEST_COMMAND, _EXIT_ZERO, "EXIT: 1"),
    f"{_RUN_BLOCK}\n{_REUSED_LINE}",
    f"{_REUSED_LINE}\n{_RUN_BLOCK}",
    f"{_REUSED_LINE}\n{_REUSED_LINE}",
    f"{_RUN_BLOCK}\n{_RUN_BLOCK}",
    f"{_RUN_LINE}\n{_PYTEST_STEP}\n{_REUSED_LINE}\n{_END_LINE}",
    f"{_RUN_LINE}\n{_RUN_LINE}\n{_PYTEST_STEP}\n{_END_LINE}",
    # A commit, revision, or exit status out of shape.
    _run(_PYTEST_STEP, commit=_HEAD[:-1]),
    _run(_PYTEST_STEP, commit=_HEAD.upper()),
    f"{_RUN_LINE}.\n{_PYTEST_STEP}\n{_END_LINE}",
    f"VERIFICATION: RUN\n{_PYTEST_STEP}\n{_END_LINE}",
    f"VERIFICATION: REUSED {_DIGEST}",
    f"VERIFICATION: REUSED sha256:{_UPPERCASE_DIGEST}",
    f"VERIFICATION: REUSED sha256:{_SHORT_DIGEST}",
    f"{_REUSED_LINE} (inspected)",
    "VERIFICATION: NONE",
    "VERIFICATION: RUN tests passed",
    _run(_PYTEST_COMMAND, "EXIT: 256"),
    _run(_PYTEST_COMMAND, "EXIT: 01"),
    _run(_PYTEST_COMMAND, "EXIT: -1"),
    _run(_PYTEST_COMMAND, "EXIT: passed"),
    # A marker or step line that may render as code.
    f"```\n{_RUN_BLOCK}\n```",
    f"```\n{_REUSED_LINE}\n```",
    f"{_RUN_LINE}\n{_PYTEST_STEP}\n```\n{_END_LINE}",
    _run(_PYTEST_COMMAND, _EXIT_ZERO, "```", "COMMAND: pytest -k later", _EXIT_ZERO, "```"),
    f"Declared:\n\n    {_REUSED_LINE}",
    f"\t{_REUSED_LINE}",
    _run(f"    {_PYTEST_COMMAND}", _EXIT_ZERO),
    _run(_PYTEST_COMMAND, f"\t{_EXIT_ZERO}"),
    # A marker quoted beside the declaration.
    f"I will close with\n{_END_LINE}\nonce done.\n\n{_RUN_BLOCK}",
)

# Replies that never declare anything.
_MISSING_MESSAGES = (
    "",
    _APPROVAL,
    f"I ran the tests and they pass.\n\n{_APPROVED_LINE}",
    "I will end with `VERIFICATION: REUSED` once I have read the evidence.",
    f"verification: reused sha256:{_DIGEST}",
    f"> {_REUSED_LINE}",
    f"{_PYTEST_STEP}\n\n{_APPROVED_LINE}",
)

# A run that finished on its own terms, carrying a well-formed declaration.
_COMPLETED_RUN = AgentResult(
    session_id=_SESSION,
    last_message=_REVIEW,
    exit_code=0,
    timed_out=False,
    stdout="",
    stderr="",
)


class FreshVerificationTest(unittest.TestCase):
    """A RUN block yields every command in order, each exactly as written."""

    def test_block_yields_its_commands_in_order(self) -> None:
        self.assertEqual(
            review_verification._parse_verification_outcome(_REVIEW, _SUBJECT, _SESSION),
            _FRESH,
        )

    def test_command_and_output_stay_verbatim(self) -> None:
        # Only the blank lines framing the output go; everything a reviewer
        # quoted -- a fence, indentation, trailing blanks, a count -- stays.
        expected = {
            _run(_PYTEST_COMMAND, _EXIT_ZERO, _FENCED_OUTPUT): _single(_FENCED_OUTPUT),
            _run(_PYTEST_COMMAND, _EXIT_ZERO, "", _INDENTED_OUTPUT, " \t"): _single(
                _INDENTED_OUTPUT,
            ),
            _run(f"COMMAND:  `{_PYTEST}` \t", "EXIT:\t0  ", _PYTEST_OUTPUT): _single(
                _PYTEST_OUTPUT, command=f"`{_PYTEST}`",
            ),
            _run(f"COMMAND: {_DIFF_CHECK}", _EXIT_ZERO): _single("", command=_DIFF_CHECK),
            _run(f"COMMAND: {_DIFF_CHECK}", _EXIT_ZERO, "", _NO_BREAK_SPACE): _single(
                _NO_BREAK_SPACE, command=_DIFF_CHECK,
            ),
            # A command line quoted in the output is only output when it
            # opens on no step keyword.
            _run(_PYTEST_COMMAND, _EXIT_ZERO, "> COMMAND: echo"): _single("> COMMAND: echo"),
            f"  {_RUN_LINE}\r\n\r\n   {_PYTEST_COMMAND}\r\n{_EXIT_ZERO}\r\nline one\r\n"
            f"line two\r\n   {_END_LINE}  \r\n": _single("line one\r\nline two"),
        }
        for message, outcome in expected.items():
            with self.subTest(message=message):
                self.assertEqual(
                    review_verification._parse_verification_outcome(message, _SUBJECT),
                    outcome,
                )

    def test_failures_and_reruns_are_kept_as_listed(self) -> None:
        # Exit statuses are what the reviewer stated, a rerun is a second
        # step, and nothing decides here whether the run passed.
        message = _run(
            _PYTEST_COMMAND, "EXIT: 1", "1 failed", _PYTEST_COMMAND, _EXIT_ZERO,
            f"COMMAND: {_RUFF}", f"EXIT: {_MAX_EXIT_STATUS}",
        )
        self.assertEqual(
            review_verification._parse_verification_outcome(message, _SUBJECT),
            _FreshVerification(
                _UNSOURCED,
                (
                    _ReportedCommand(_PYTEST, 1, "1 failed"),
                    _ReportedCommand(_PYTEST, 0, ""),
                    _ReportedCommand(_RUFF, _MAX_EXIT_STATUS, ""),
                ),
            ),
        )

    def test_a_sha256_commit_is_a_full_object_id(self) -> None:
        subject = _VerificationSubject(_SHA256_HEAD)
        self.assertEqual(
            review_verification._parse_verification_outcome(
                _run(_PYTEST_STEP, commit=_SHA256_HEAD), subject,
            ),
            _FreshVerification(
                _ReviewerSource(None, _SHA256_HEAD),
                (_ReportedCommand(_PYTEST, 0, _PYTEST_OUTPUT),),
            ),
        )


class DeclaredSubjectTest(unittest.TestCase):
    """A declaration counts only about what the reviewer was handed: the
    commit under review, or the current evidence revision it was shown."""

    def test_current_revision_is_reused(self) -> None:
        for message in (
            _REUSED_LINE,
            f"Read the evidence.\n\n   {_REUSED_LINE} \t\n\n{_APPROVAL}",
            f"```\nnotes\n```\n{_REUSED_LINE}\r\n",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    review_verification._parse_verification_outcome(message, _SUBJECT, _SESSION),
                    _ReusedVerification(_SOURCE, _DIGEST),
                )

    def test_other_commit_or_revision_is_stale(self) -> None:
        stale = (
            (_run(_PYTEST_STEP, commit=_OTHER_HEAD), _SUBJECT),
            (f"VERIFICATION: REUSED sha256:{_OTHER_DIGEST}", _SUBJECT),
            (_REUSED_LINE, _VerificationSubject(_HEAD)),
            (_REUSED_LINE, _VerificationSubject(_OTHER_HEAD, _OTHER_DIGEST)),
        )
        for message, subject in stale:
            with self.subTest(message=message, subject=subject):
                self.assertIs(
                    review_verification._parse_verification_outcome(message, subject),
                    _VerificationRefusal.STALE,
                )

    def test_shape_is_settled_before_truth(self) -> None:
        self.assertIs(
            review_verification._parse_verification_outcome(
                _run(_PYTEST_COMMAND, commit=_OTHER_HEAD), _SUBJECT,
            ),
            _VerificationRefusal.MALFORMED,
        )


class RefusedMessageTest(unittest.TestCase):
    """Anything short of exactly one declaration is refused, and the refusal
    says whether the reply declared anything at all."""

    def test_near_misses_are_malformed(self) -> None:
        for message in _MALFORMED_MESSAGES:
            with self.subTest(message=message):
                self.assertIs(
                    review_verification._parse_verification_outcome(message, _SUBJECT),
                    _VerificationRefusal.MALFORMED,
                )

    def test_undeclared_replies_are_missing(self) -> None:
        for message in _MISSING_MESSAGES:
            with self.subTest(message=message):
                self.assertIs(
                    review_verification._parse_verification_outcome(message, _SUBJECT),
                    _VerificationRefusal.MISSING,
                )


class VerdictCoexistenceTest(unittest.TestCase):
    """The declaration and the verdict are read from one message apart: each
    reader finds its own marker, and neither needs the other."""

    def test_each_reader_finds_its_own_marker(self) -> None:
        changes = f"1. Add a test for the empty case\n\n{_REUSED_LINE}\n\nVERDICT: CHANGES_REQUESTED"
        messages = (
            (_REVIEW, _FRESH, VERDICT_APPROVED),
            (changes, _ReusedVerification(_SOURCE, _DIGEST), VERDICT_CHANGES_REQUESTED),
        )
        for message, declaration, verdict in messages:
            with self.subTest(verdict=verdict):
                self.assertEqual(
                    review_verification._parse_verification_outcome(message, _SUBJECT, _SESSION),
                    declaration,
                )
                self.assertEqual(completion_verdicts._parse_review_verdict(message)[0], verdict)

    def test_a_declaration_stands_without_a_verdict(self) -> None:
        self.assertEqual(
            review_verification._parse_verification_outcome(_RUN_BLOCK, _SUBJECT, _SESSION),
            _FRESH,
        )

    def test_a_block_holding_a_verdict_is_refused(self) -> None:
        # The verdict reader still takes its last marker; a block holding one
        # is refused rather than kept with a verdict as a command's output.
        for message in (
            _run(_PYTEST_STEP, _APPROVED_LINE),
            _run(_PYTEST_COMMAND, _EXIT_ZERO, "Tests pass. verdict: approved"),
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    completion_verdicts._parse_review_verdict(message)[0], VERDICT_APPROVED,
                )
                self.assertIs(
                    review_verification._parse_verification_outcome(message, _SUBJECT),
                    _VerificationRefusal.MALFORMED,
                )


class ReviewerRunTest(unittest.TestCase):
    """Only a run that completed on its own terms has its message read, and
    what it declares names that run as its only witness."""

    def test_completed_run_is_the_source(self) -> None:
        outcome = review_verification._verification_outcome_of_run(_COMPLETED_RUN, _SUBJECT)
        self.assertEqual(outcome, _FRESH)
        self.assertEqual(outcome.source.provenance, "reviewer_reported")

    def test_run_without_session_is_sourced_to_none(self) -> None:
        run = dataclasses.replace(_COMPLETED_RUN, session_id=None, last_message=_REUSED_LINE)
        self.assertEqual(
            review_verification._verification_outcome_of_run(run, _SUBJECT),
            _ReusedVerification(_UNSOURCED, _DIGEST),
        )

    def test_unfinished_run_is_refused_unread(self) -> None:
        # Each run still carries a well-formed declaration and exits nonzero,
        # and each earlier shortfall wins over the ones listed after it.
        unfinished = (
            (_VerificationRefusal.NOT_INVOKED, {"invoked": False}),
            (
                _VerificationRefusal.INTERRUPTED,
                {"exit_code": _INTERRUPTED_EXIT, "interrupted": True, "timed_out": True},
            ),
            (_VerificationRefusal.TIMED_OUT, {"timed_out": True}),
            (
                _VerificationRefusal.PROVIDER_FAILURE,
                {"last_message": f"{PROVIDER_OVERLOAD_MESSAGE}\n{_REVIEW}"},
            ),
            (_VerificationRefusal.NONZERO_EXIT, {}),
        )
        for refusal, shortfalls in unfinished:
            run = dataclasses.replace(_COMPLETED_RUN, **{"exit_code": 1, **shortfalls})
            with self.subTest(refusal=refusal):
                self.assertIs(
                    review_verification._verification_outcome_of_run(run, _SUBJECT), refusal,
                )


if __name__ == "__main__":
    unittest.main()
