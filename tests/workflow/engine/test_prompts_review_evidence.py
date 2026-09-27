# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a reviewer is told about: current evidence, then the configuration.

Evidence current for the reviewer's subject is quoted whole -- the witness's
preamble and every command with its exit status and output, every line quoted
whatever ends it -- under the `sha256:` revision a reuse names, and says which
of the commands it lists did not exit 0 -- about those commands alone, never
whether they are the ones the repository requires. A reviewer handed none is
told so. What the repository configures is named command by command, or
plainly as nothing, since an empty configuration is no evidence that any check
passed.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from orchestrator.workflow.engine import review_evidence_prompts
from tests.workflow.engine import verification_record_test_support as _record_support

LINT = "uv run ruff check orchestrator tests"

# Output spanning several lines, every one of which the quotation has to carry.
SUITE_OUTPUT = "collected 12 items\n\n12 passed in 0.4s"

# Output a progress line rewrote in place, bare carriage returns and all.
REWRITTEN_OUTPUT = "collecting 3 items\rcollecting 12 items\r\n12 passed in 0.4s"

# Where the configuration follows the quoted evidence.
CONFIGURED = "\n\nThis repository"

NOTHING_HANDED = "No current workflow verification evidence covers this subject"

EMPTY = "configures no verification commands (`VERIFY_COMMANDS` is empty)"


def _lint(exit_status: int) -> VerifiedCommand:
    """The linter, beside the suite, having exited with `exit_status`."""
    return VerifiedCommand(command=LINT, exit_status=exit_status, output="Found 1 error.")


# The suite passing and the linter it was run beside, passing.
PASSING = (_record_support.ran(SUITE_OUTPUT), _lint(0))


def _handed(commands=PASSING) -> review_evidence_prompts.HandedEvidence:
    """Reviewer-reported evidence of `commands`, settled for the recorded subject."""
    state = _record_support.reread(PinnedState(comment_id=1, state_data={}))
    pending = _record_support.minted(
        state, _record_support.binding(source=EvidenceSource.REVIEWER_REPORTED), commands,
    )
    return review_evidence_prompts.HandedEvidence(
        _record_support.current(pending), pending.artifact,
    )


def _block(handed=None, commands=(_record_support.SUITE,)) -> str:
    """What a reviewer handed `handed` is told under `commands` as `VERIFY_COMMANDS`."""
    with patch.object(config, "VERIFY_COMMANDS", commands):
        return review_evidence_prompts._verification_block(handed)


class VerificationBlockTest(unittest.TestCase):
    """What a reviewer is told about verification."""

    def test_current_evidence_is_quoted_whole(self) -> None:
        passing = _handed()

        quoted = _block(passing)

        self.assertIn(
            f"revision `sha256:{passing.revision}`, re-read in full by the orchestrator "
            f"from PR #{_record_support.PR_NUMBER}, comment {_record_support.ARTIFACT_COMMENT}",
            quoted,
        )
        # Every line the artifact shows, preamble and commands alike, is
        # quoted in order: a reviewer reusing the revision has read all of it.
        whole = (passing.artifact.preamble + passing.artifact.evidence).split("\n")
        self.assertIn("\n".join(f"> {line}" for line in whole), quoted)
        self.assertIn("> 12 passed in 0.4s\n", quoted)
        self.assertIn(f"> `{LINT}` -- exit 0\n", quoted)
        self.assertIn("and every command it lists exited 0:", quoted)
        self.assertNotIn(NOTHING_HANDED, quoted)
        self.assertEqual(passing.revision, passing.artifact.content_revision)

    def test_every_line_is_quoted_whatever_ends_it(self) -> None:
        # The words after a bare carriage return start a line wherever the
        # prompt is shown, so they are quoted as evidence too; and quoting
        # loses and reorders nothing of the artifact.
        handed = _handed((_record_support.ran(REWRITTEN_OUTPUT),))

        told = _block(handed)

        quote = told[told.index("> "):told.index(CONFIGURED)]
        lines = quote.splitlines(keepends=True)
        self.assertIn("items\r> collecting 12 items\r\n> 12 passed", told)
        self.assertEqual([line for line in lines if not line.startswith("> ")], [])
        self.assertEqual(
            "".join(line.removeprefix("> ") for line in lines),
            handed.artifact.preamble + handed.artifact.evidence,
        )

    def test_the_status_is_the_listed_commands_own(self) -> None:
        # The configured suite passed and the linter run beside it failed:
        # the evidence says which listed command failed, and nothing about
        # the configured one it passed on.
        for name, commands, told in (
            (
                "a listed command beside the suite failed",
                (_record_support.ran(SUITE_OUTPUT), _lint(1)),
                f"and these commands it lists did NOT exit 0: `{LINT}` (exit 1):",
            ),
            ("no command is listed", (), "and it lists no command, so it is not evidence that anything passed:"),
        ):
            with self.subTest(name):
                status = _block(_handed(commands))

                self.assertIn(told, status)
                self.assertNotIn("every command it lists exited 0", status)
                self.assertNotIn("required", status)
                self.assertNotIn(f"`{_record_support.SUITE}` (exit", status)

    def test_the_configuration_is_named(self) -> None:
        configured = _block(commands=(_record_support.SUITE, LINT))
        empty = _block(commands=())

        self.assertIn(f"are, in order: `{_record_support.SUITE}`, `{LINT}`.", configured)
        self.assertNotIn(EMPTY, configured)
        self.assertIn(EMPTY, empty)
        self.assertIn("nothing the orchestrator runs is evidence that any check passed", empty)
        for name, told in (("configured", configured), ("empty", empty)):
            with self.subTest(name):
                self.assertIn(NOTHING_HANDED, told)
                self.assertNotIn("sha256:", told)


if __name__ == "__main__":
    unittest.main()
