# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a reviewer is told about, and the declaration it is taught to close with.

Evidence current for the reviewer's subject is quoted whole -- the artifact's
summary and every command with its exit status and output, every line quoted
whatever ends it -- under the `sha256:` revision a reuse names, and says which
of the commands it lists did not exit 0 -- about those commands alone, never
whether they are the ones the repository requires. Evidence re-read from the
comment it was published as, as after a restart, is handed over just as
completely, whether that comment hides its commands in a payload or is one
the legacy format published. A reviewer handed none is told so. What the
repository configures is named command by command, or plainly as nothing,
since an empty configuration is no evidence that any check passed. The
reviewer is then taught the one declaration its final message carries, in
the very spellings the declaration's reader accepts -- the RUN block naming
the head it is handed, and the REUSED line only beside evidence it was handed
-- and told that a SHA, a count, or a command the orchestrator publishes
itself is no change to request, while genuine failures and inaccurate claims
still are.
"""
from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    review_evidence_prompts,
    review_prompts,
    review_verification,
    review_verification_models,
)
from tests.support.fakes import FakeComment, make_issue
from tests.support.github import legacy_artifacts
from tests.workflow.engine import verification_record_test_support as _record_support
from tests.workflow.repo_values import _TEST_SPEC

LINT = "uv run ruff check orchestrator tests"

# Output spanning several lines, every one of which the quotation has to carry.
SUITE_OUTPUT = "collected 12 items\n\n12 passed in 0.4s"

# What the suite printed failing, in the comment the legacy format published of it.
LEGACY_OUTPUT = "collected 12 items\n\n1 failed, 11 passed in 0.4s"

# Output a progress line rewrote in place, bare carriage returns and all.
REWRITTEN_OUTPUT = "collecting 3 items\rcollecting 12 items\r\n12 passed in 0.4s"

# Where the configuration follows the quoted evidence.
CONFIGURED = "\n\nThis repository"

HEAD = _record_support.SUBJECT.commit

POLICY = (
    "do NOT request changes merely to have a developer or a human copy a "
    "commit SHA, a test count, or a command"
)

STILL_ACTIONABLE = (
    "A check that failed, verification the change still needs, a report "
    "claiming something that did not happen, and evidence about another commit "
    "or subject remain changes to request."
)

NOTHING_HANDED = "No current workflow verification evidence covers this subject"

EMPTY = "configures no verification commands (`VERIFY_COMMANDS` is empty)"

REUSE = "VERIFICATION: REUSED"

# What separates a quoted summary from the commands quoted under it.
SUMMARY_BREAK = "\n\n"


def _lint(exit_status: int) -> _evidence.VerifiedCommand:
    """The linter, beside the suite, having exited with `exit_status`."""
    return _evidence.VerifiedCommand(command=LINT, exit_status=exit_status, output="Found 1 error.")


# The suite passing and the linter it was run beside, passing.
PASSING = (_record_support.ran(SUITE_OUTPUT), _lint(0))


def _handed(commands=PASSING) -> review_evidence_prompts.HandedEvidence:
    """Reviewer-reported evidence of `commands`, settled for the recorded subject."""
    state = _record_support.reread(PinnedState(comment_id=1, state_data={}))
    pending = _record_support.minted(
        state, _record_support.binding(source=_evidence.EvidenceSource.REVIEWER_REPORTED), commands,
    )
    return review_evidence_prompts.HandedEvidence(
        _record_support.current(pending), pending.artifact,
    )


def _reread(body: str, published: review_evidence_prompts.HandedEvidence) -> review_evidence_prompts.HandedEvidence:
    """What a reviewer is handed once the comment carrying `body` is re-read, as after a restart.

    The record is the one `published` settled; the artifact is whatever the
    comment reads back as now.
    """
    return review_evidence_prompts.HandedEvidence(
        published.current,
        _artifacts.verification_artifact_from_comment(
            FakeComment(id=_record_support.ARTIFACT_COMMENT, body=body), bot_login=None,
        ),
    )


def _block(handed=None, commands=(_record_support.SUITE,)) -> str:
    """What a reviewer of the recorded subject handed `handed` is told under `commands` as `VERIFY_COMMANDS`."""
    with patch.object(config, "VERIFY_COMMANDS", commands):
        return review_evidence_prompts._verification_block(handed, _record_support.SUBJECT)


def _taught(prompt: str, marker: str) -> str:
    """The declaration line `prompt` teaches opening on `marker`, as a reviewer would copy it."""
    taught = re.compile(rf"^  ({re.escape(marker)} \S+)$", re.MULTILINE)
    return taught.search(prompt).group(1)


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
        # Every line of the artifact, summary and commands alike, is quoted
        # in order: a reviewer reusing the revision has read all of it.
        artifact = passing.artifact
        whole = SUMMARY_BREAK.join((artifact.summary, artifact.evidence)).split("\n")
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
            SUMMARY_BREAK.join((handed.artifact.summary, handed.artifact.evidence)),
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

    def test_a_compact_comment_hands_over_everything(self) -> None:
        # The comment shows a summary alone, yet the reviewer is quoted every
        # command, status, and output line its hidden payload recorded.
        published = _handed((_record_support.ran(SUITE_OUTPUT), _lint(1)))

        self._hands_over(published, _artifacts.render_verification_artifact(published.artifact), (
            f"> `{_record_support.SUITE}` -- exit 0\n",
            "> collected 12 items\n> \n> 12 passed in 0.4s\n",
            f"> `{LINT}` -- exit 1\n",
            "> Found 1 error.\n",
            f"did NOT exit 0: `{LINT}` (exit 1):",
        ))

    def test_a_legacy_comment_hands_over_everything(self) -> None:
        # A comment the legacy format published, fixed as it was posted,
        # hands over the commands its visible section showed.
        published = _handed((_record_support.ran(LEGACY_OUTPUT, 1),))

        self._hands_over(published, legacy_artifacts.FAILED, (
            f"> `{_record_support.SUITE}` -- exit 1\n",
            "> collected 12 items\n> \n> 1 failed, 11 passed in 0.4s\n",
            f"did NOT exit 0: `{_record_support.SUITE}` (exit 1):",
        ))

    def test_the_configuration_is_named(self) -> None:
        configured = _block(commands=(_record_support.SUITE, LINT))
        empty = _block(commands=())

        self.assertIn(
            f"are, in order: `{_record_support.SUITE}`, `{LINT}`. An approval's declaration has to "
            "list each of them exactly as written here, with the exit status it returned, or reuse "
            "evidence that does; further commands may be listed beside them.",
            configured,
        )
        self.assertNotIn(EMPTY, configured)
        self.assertIn(f"{EMPTY}, so no particular command is required and nothing the orchestrator runs", empty)
        for name, told in (("configured", configured), ("empty", empty)):
            with self.subTest(name):
                self.assertIn(NOTHING_HANDED, told)
                self.assertNotIn("sha256:", told)
                # A reviewer handed nothing is taught to run the checks on
                # the head it is handed, and never a reuse.
                self.assertIn(f"  VERIFICATION: RUN {HEAD}\n", told)
                self.assertNotIn("VERIFICATION: REUSED", told)
                self.assertIn(POLICY, told)
                self.assertIn(STILL_ACTIONABLE, told)

    def _hands_over(
        self, published: review_evidence_prompts.HandedEvidence, body: str, recorded: tuple[str, ...],
    ) -> None:
        """Assert a reviewer handed the comment carrying `body`, re-read, is told all of `recorded`.

        Re-read rather than handed the artifact `published` minted, as after a
        restart, and taught a reuse of the very revision its evidence was
        settled under, which the declaration's reader accepts.
        """
        handed = _reread(body, published)
        told = _block(handed)

        self.assertEqual(handed.artifact.commands, published.artifact.commands)
        self.assertEqual([line for line in recorded if line not in told], [])
        self.assertEqual(_taught(told, REUSE), f"{REUSE} sha256:{handed.revision}")
        self.assertIn(f":content={handed.revision}-->", body)
        self.assertIsInstance(
            review_verification._parse_verification_outcome(
                _taught(told, REUSE), review_verification_models._VerificationSubject(HEAD, handed.revision),
            ),
            review_verification_models._ReusedVerification,
        )


class DeclarationContractTest(unittest.TestCase):
    """The declaration a reviewer is taught, in the prompt it closes on."""

    def test_the_taught_declarations_parse(self) -> None:
        # Spelled from the same models the reader parses, so a reviewer
        # writing exactly what it is shown is read back -- the reuse naming
        # the evidence it was handed, the run naming the head under review.
        handed = _handed()
        with patch.object(config, "VERIFY_COMMANDS", (_record_support.SUITE,)):
            prompt = review_prompts._build_review_prompt(
                _TEST_SPEC, make_issue(7, body="users want a foo flag"), "", [],
                review_prompts.ReviewHandover(subject=_record_support.SUBJECT, evidence=handed),
            )
        reuse = _taught(prompt, "VERIFICATION: REUSED")
        run = "\n".join((
            _taught(prompt, "VERIFICATION: RUN"),
            f"COMMAND: {_record_support.SUITE}",
            "EXIT: 0",
            "VERIFICATION: END",
        ))
        subject = review_verification_models._VerificationSubject(HEAD, handed.revision)

        self.assertEqual(reuse, f"VERIFICATION: REUSED sha256:{handed.revision}")
        self.assertIsInstance(
            review_verification._parse_verification_outcome(reuse, subject),
            review_verification_models._ReusedVerification,
        )
        self.assertIsInstance(
            review_verification._parse_verification_outcome(run, subject),
            review_verification_models._FreshVerification,
        )
        # The verification sits between the commands that inspect the branch
        # and the verdict the prompt closes on, and its declaration is asked
        # for above that verdict.
        self.assertLess(prompt.index("git diff"), prompt.index("Workflow verification evidence"))
        self.assertLess(prompt.index(POLICY), prompt.rindex("VERDICT: APPROVED"))
        self.assertIn("the verification declaration described above goes above the verdict line", prompt)

    def test_no_subject_names_the_checkout(self) -> None:
        told = review_evidence_prompts._verification_block(None, None)

        self.assertIn("on the commit `git rev-parse HEAD` names:", told)
        self.assertIn("  VERIFICATION: RUN <full commit id>\n", told)


if __name__ == "__main__":
    unittest.main()
