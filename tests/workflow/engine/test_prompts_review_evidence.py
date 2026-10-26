# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a reviewer is told about, the declaration it is taught to close with, and how it reports a failure.

Evidence current for the reviewer's subject is quoted whole -- the artifact's
summary and every command with its exit status and output, every line quoted
whatever ends it -- under the `sha256:` revision a reuse names, and says which
of the commands it lists did not exit 0 -- about those commands alone, never
whether they are the ones the repository requires. Evidence re-read from the
comment it was published as, as after a restart, is handed over just as
completely out of its hidden payload, while a comment showing its commands
with no payload hands over nothing of what it shows. A reviewer handed none
is told so. What the
repository configures is named command by command, or plainly as nothing,
since an empty configuration is no evidence that any check passed. The
reviewer is then taught the one declaration its final message carries, in
the very spellings the declaration's reader accepts -- the RUN block naming
the head it is handed, and the REUSED line only beside evidence it was handed
-- and told that a SHA, a count, or a command the orchestrator publishes
itself is no change to request, while genuine failures and inaccurate claims
still are. Last, it is taught the entry each failure gets in its findings:
opening on the failure's name -- a test's exact ID, a probe's scenario name,
or the check that failed where no test ID names it -- with the error,
expected and observed behavior, a reproduction a stdin command alone is not,
and the diagnostics it could not obtain. Entries written that way leave the
declaration reading exactly as the commands ran, and show as findings.
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
    review_findings,
    review_prompts,
    review_verification,
    review_verification_models,
)
from tests.support.fakes import FakeComment, make_issue
from tests.support.github import visible_evidence
from tests.workflow.engine import verification_record_test_support as _record_support
from tests.workflow.repo_values import _TEST_SPEC

LINT = "uv run ruff check orchestrator tests"

# Output spanning several lines, every one of which the quotation has to carry.
SUITE_OUTPUT = "collected 12 items\n\n12 passed in 0.4s"

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

# The labels a failure's entry is taught, its name first. Title case sets
# them apart from the declaration's uppercase step keywords.
LAYOUT = ("Failure", "Error", "Expected", "Observed", "Reproduce", "Unavailable")

TAUGHT_LABEL = re.compile(r"^  ([A-Z][a-z]+): <", re.MULTILINE)

# What the layout asks of each kind of failure, as the prompt words it.
DIAGNOSTICS = (
    ("a test by its exact ID", "named by its exact test ID as the runner reported it, parameters included"),
    ("a test rerun alone", "reproduced by a command that runs that test alone"),
    ("a probe by its scenario", "named by a descriptive scenario name saying what it exercises"),
    ("a probe by its snippet", "reproduced by a self-contained snippet in a code block below its Reproduce line"),
    ("a stdin command alone", "as `.venv/bin/python -`, reproduces nothing by itself"),
    ("expected against observed", "Write the Expected and Observed lines where the error alone does not explain"),
    (
        "scenarios sharing a command",
        (
            "Distinct scenarios are distinct entries, each with its own name, error, and reproduction, "
            "even where one command ran them all."
        ),
    ),
    ("a failure no test ID names", "is named by the check that failed, reported with its actual error"),
    ("no invented test ID", "never invent a test ID the runner did not report"),
    ("a missing diagnostic", "Write the Unavailable line only where a diagnostic is missing"),
    (
        "a failure missing a diagnostic",
        "still report the failure, saying what is missing rather than leaving the failure out or guessing",
    ),
    (
        "outside the declaration",
        (
            "These entries belong to the findings and never to the declaration: the declaration still lists "
            "each command exactly as you ran it"
        ),
    ),
)

PROBE = ".venv/bin/python -"

PARAMETRIZED = "tests/workflow/test_relabel.py::RelabelTest::test_reproves[lost-response]"

# A reviewer's findings in the taught layout: a parameterized test, two probes
# one stdin command ran, and a collection error with no test ID to give, above
# the declaration listing each command as it ran.
ENTRIES = f"""1. Reprove evidence when a relabel request fails.

   Failure: {PARAMETRIZED}
   Error: AssertionError: settled evidence revived after the report moved
   Reproduce: .venv/bin/python -m pytest '{PARAMETRIZED}'

   Failure: A failed relabel request revives settled evidence
   Error: AssertionError: the relabel failure path revived settled evidence
   Expected: the evidence is reproved before the attempt is released
   Observed: the attempt is released on evidence settled before the report moved
   Reproduce: `{PROBE}` reading this snippet on stdin:

   ```python
   from tests.workflow import relabel_support
   assert not relabel_support.revived(relabel_support.failed_relabel())
   ```

   Failure: A lost announcement revives settled evidence
   Error: AssertionError: the announcement failure path revived settled evidence
   Reproduce: `{PROBE}` reading this snippet on stdin:

   ```python
   from tests.workflow import relabel_support
   assert not relabel_support.revived(relabel_support.lost_announcement())
   ```

2. Make the new test module importable.

   Failure: pytest collection of tests/workflow/test_announce.py
   Error: ImportError: cannot import name 'announce' from 'orchestrator.workflow'
   Reproduce: .venv/bin/python -m pytest tests/workflow/test_announce.py
   Unavailable: the traceback above its last line, which the saved log cut short
"""

DECLARED = f"""
VERIFICATION: RUN {HEAD}
COMMAND: {_record_support.SUITE}
EXIT: 1
FAILED {PARAMETRIZED}
ERROR tests/workflow/test_announce.py
COMMAND: {PROBE}
EXIT: 1
AssertionError: the relabel failure path revived settled evidence
COMMAND: {PROBE}
EXIT: 1
AssertionError: the announcement failure path revived settled evidence
VERIFICATION: END
"""


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


def _reread(
    body: str, published: review_evidence_prompts.HandedEvidence,
) -> review_evidence_prompts.HandedEvidence | None:
    """What a reviewer is handed once the comment carrying `body` is re-read, as after a restart.

    The record is the one `published` settled; the artifact is whatever the
    comment reads back as now, and a comment that reads back as none hands
    nothing, as the validating stage hands nothing for it.
    """
    artifact = _artifacts.verification_artifact_from_comment(
        FakeComment(id=_record_support.ARTIFACT_COMMENT, body=body), bot_login=None,
    )
    if artifact is None:
        return None
    return review_evidence_prompts.HandedEvidence(published.current, artifact)


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

    def test_shown_evidence_hands_over_nothing(self) -> None:
        # The comment shows exactly the commands the record settled, under
        # the header naming their revision, but carries no hidden payload:
        # re-read, it is no artifact, so the reviewer is quoted none of what
        # it shows and taught no reuse of that revision.
        published = _handed(visible_evidence.SHOWN.commands)

        told = _block(_reread(visible_evidence.COMMENT, published))

        self.assertIn(f":content={published.revision}-->", visible_evidence.COMMENT)
        self.assertIn(NOTHING_HANDED, told)
        self.assertNotIn(published.revision, told)
        self.assertNotIn(REUSE, told)
        self.assertNotIn("1 failed, 11 passed", told)

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
    """The declaration a reviewer is taught, and the failure entries beside it, in the prompt it closes on."""

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

        self.assertIn(
            "  COMMAND: <the command itself, without the logging or status-capture plumbing "
            "you wrapped around it>\n"
            "  EXIT: <the command's own exit status, not that of logging or output processing you added>\n",
            prompt,
        )
        self.assertIn("an added `tail` or `head` can hide a failure", prompt)
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

    def test_failures_are_taught_named_entries(self) -> None:
        # Handed evidence or not, every failure gets an entry of its own that
        # opens on its name, and each kind of failure is told what names and
        # reproduces it -- a missing diagnostic said, never guessed.
        handed = _block(_handed())
        for name, told in (("handed", handed), ("nothing handed", _block())):
            with self.subTest(name):
                self.assertEqual(tuple(TAUGHT_LABEL.findall(told)), LAYOUT)
                self.assertLess(told.index(STILL_ACTIONABLE), told.index("  Failure: <the failure's name>\n"))
                self.assertEqual([what for what, phrase in DIAGNOSTICS if phrase not in told], [])

    def test_taught_entries_stay_findings(self) -> None:
        # Entries written as taught leave the declaration exactly as it ran --
        # one stdin command declared twice, as it ran twice -- and every name,
        # snippet, and missing diagnostic they carry is shown as findings.
        with patch.object(config, "VERIFY_COMMANDS", (_record_support.SUITE,)):
            prompt = review_prompts._build_review_prompt(
                _TEST_SPEC, make_issue(7, body="users want a foo flag"), "", [],
                review_prompts.ReviewHandover(subject=_record_support.SUBJECT),
            )
        declared = review_verification._parse_verification_outcome(
            f"{ENTRIES}{DECLARED}\nVERDICT: CHANGES_REQUESTED",
            review_verification_models._VerificationSubject(HEAD),
        )
        shown = review_findings._concise_findings(f"{ENTRIES}{DECLARED}")

        self.assertIn("every failure an item rests on entered under it in the layout described above", prompt)
        self.assertLess(prompt.index("  Failure: <"), prompt.rindex("VERDICT: CHANGES_REQUESTED"))
        self.assertIsInstance(declared, review_verification_models._FreshVerification)
        self.assertEqual(
            [(ran.command, ran.exit_status) for ran in declared.commands],
            [(_record_support.SUITE, 1), (PROBE, 1), (PROBE, 1)],
        )
        self.assertEqual([line for line in ENTRIES.splitlines() if line not in shown], [])


if __name__ == "__main__":
    unittest.main()
