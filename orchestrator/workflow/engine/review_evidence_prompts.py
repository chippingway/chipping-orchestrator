# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a fresh reviewer is handed, and the declaration it closes with.

A reviewer is told four things about verification beside the report it
reviews. First the workflow evidence that is CURRENT for the very subject it
is handed, where there is any: the artifact the pull request carries, re-read
and quoted whole -- its summary, then every command with its exit status and
complete output -- under the revision a reuse has to name, and never
evidence about another head, report, or requirements revision, which is
evidence about something nobody is asking this reviewer to approve. The
comment shows the summary alone, so the commands are the ones the re-read
decoded out of its hidden payload, or read off the visible section of an
artifact published before evidence was hidden: complete either way, and
after a restart as much as before one. Which evidence that is, and the proof
that it covers the subject, belong to the validating stage
(`stages/validating/review_evidence.py`); this owner renders what it is
handed, and says which of the commands it lists did not exit 0 --
about those commands alone, since the evidence does not say whether they are
the ones this repository requires. Then what this repository configures as its
verification -- the commands, or the plain statement that none are configured,
since an empty `VERIFY_COMMANDS` is not evidence that anything passed. Then the
one declaration its final message has to carry -- a RUN block naming the head
it is handed, or, only where it was handed evidence, the REUSED line naming
that evidence's exact revision -- spelled from `review_verification_models`,
the same source the parser reads.

Last, the policy that is the other half of why the evidence is handed at all.
The orchestrator publishes what a reviewer declares, so a reviewer holding
valid evidence for the commit it reviews has nothing left for a developer or a
human to copy into the pull request description: a request to transcribe a
commit id, a count, or a command is a round nobody needed. What the evidence
cannot answer -- a check that failed, verification the change still lacks, a
report claiming what did not happen, evidence about another subject -- stays a
change to request.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator import config
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    review_verification_models as _verification_models,
    verification_records as _records,
)

_EVIDENCE_POLICY = (
    "An approval is acted on only when the evidence it declares -- commands "
    "you ran, or current evidence you reuse -- lists at least one command, "
    "every listed command exited 0, and every configured command is among "
    "them exactly as written; further commands beside those are allowed. An "
    "approval without such evidence is parked rather than approved. The orchestrator publishes "
    "the evidence you declare on the pull request itself, so while valid "
    "evidence covers the commit under review do NOT request changes merely to "
    "have a developer or a human copy a commit SHA, a test count, or a command "
    "into the pull request description or the report. A check that failed, "
    "verification the change still needs, a report claiming something that "
    "did not happen, and evidence about another commit or subject remain "
    "changes to request."
)

# What separates an artifact's summary from the commands quoted under it.
_SUMMARY_BREAK = "\n\n"


@dataclass(frozen=True)
class HandedEvidence:
    """The current workflow evidence one reviewer is handed, as re-read.

    `current` is the record its settlement left; `artifact` is that evidence
    re-read at the comment the record names. The caller proved both current
    for the subject the reviewer is handed before building this.
    """

    current: _records.CurrentEvidence
    artifact: VerificationArtifact

    @property
    def revision(self) -> str:
        """The digest a reviewer names to reuse this evidence."""
        return self.current.content_revision


def _verification_block(
    handed: HandedEvidence | None, subject: _review_subjects.ReviewSubject | None,
) -> str:
    """Everything a reviewer of `subject` is told about verification, in the order it is read.

    The subject's head is the commit a RUN block has to name; a reviewer
    handed no subject is told to name the one it checked out.
    """
    return "\n\n".join((
        _evidence_block(handed),
        _configured_block(),
        _declaration_contract(handed, "" if subject is None else subject.commit),
        _EVIDENCE_POLICY,
    ))


def _evidence_block(handed: HandedEvidence | None) -> str:
    """The current evidence quoted whole, or the note that none covers this subject."""
    if handed is None:
        return (
            "Workflow verification evidence:\nNo current workflow verification "
            "evidence covers this subject, so run the verification yourself."
        )
    current, artifact = handed.current, handed.artifact
    quoted = _quoted(f"{artifact.summary}{_SUMMARY_BREAK}{artifact.evidence}")
    return (
        f"Workflow verification evidence (revision `{_verification_models._REVISION_PREFIX}"
        f"{handed.revision}`, re-read in full by the orchestrator from PR "
        f"#{artifact.pr_number}, comment {current.comment_id}). It is the "
        "current evidence for exactly the head, requirements, and report above, "
        f"and {_commands_status(artifact)}:\n\n{quoted}"
    )


def _quoted(text: str) -> str:
    """`text` as a blockquote with every line quoted, whatever ends it.

    Split on every line ending rather than on the newline alone, as the
    artifact format's own fence check reads a transcript: a transcript may
    carry a bare carriage return, and the words after one start a line of
    their own wherever the prompt is shown -- left unquoted, they would read
    as the prompt's own text rather than the evidence's. Each line keeps the
    ending it had, so the quote less its prefixes is the artifact exactly.
    """
    return "".join(f"> {line}" for line in text.splitlines(keepends=True))


def _commands_status(artifact: VerificationArtifact) -> str:
    """What the commands the artifact lists say, by their own exit statuses.

    Only about those commands: whether they are the ones this repository
    configures is the configuration's question, told apart below.
    """
    if not artifact.commands:
        return "it lists no command, so it is not evidence that anything passed"
    failed = ", ".join(
        f"`{ran.command}` (exit {ran.exit_status})"
        for ran in artifact.commands if ran.exit_status != 0
    )
    if not failed:
        return "every command it lists exited 0"
    return f"these commands it lists did NOT exit 0: {failed}"


def _configured_block() -> str:
    """What this repository configures as its verification."""
    commands = tuple(config.VERIFY_COMMANDS)
    if not commands:
        return (
            "This repository configures no verification commands "
            "(`VERIFY_COMMANDS` is empty), so no particular command is required "
            "and nothing the orchestrator runs is evidence that any check passed: "
            "run the checks this repository's own documentation requires of a change."
        )
    listed = ", ".join(f"`{command}`" for command in commands)
    return (
        "This repository's configured verification commands "
        f"(`VERIFY_COMMANDS`) are, in order: {listed}. An approval's "
        "declaration has to list each of them exactly as written here, with "
        "the exit status it returned, or reuse evidence that does; further "
        "commands may be listed beside them."
    )


def _declaration_contract(handed: HandedEvidence | None, commit: str) -> str:
    """The declaration a reviewer's final message has to carry above its verdict.

    The REUSED form is taught only beside evidence handed over, since a reuse
    of anything else -- a reviewer handed none included -- is read as stale.
    """
    models = _verification_models
    head = f"`{commit}`" if commit else "the commit `git rev-parse HEAD` names"
    named = commit or "<full commit id>"
    contract = (
        "Declare the verification this review relies on in your final message, "
        "ABOVE the VERDICT line, with every marker line alone on its own line "
        "and outside any code block. For commands you ran yourself in this "
        f"worktree on {head}:\n\n"
        f"  {models._VERIFICATION_RUN_MARKER} {named}\n"
        f"  {models._COMMAND_PREFIX} <the exact command line>\n"
        f"  {models._EXIT_PREFIX} <the exit status it returned>\n"
        "  <any output you quote, as plain lines with no code fences>\n"
        f"  {models._VERIFICATION_END_MARKER}\n\n"
        f"Repeat the {models._COMMAND_PREFIX} and {models._EXIT_PREFIX} lines, "
        "with any output below them, for every command in the order you ran "
        "them. List only commands you actually ran, each with the status it "
        "really returned; never estimate a result or copy one from the report."
    )
    if handed is None:
        return contract
    return (
        f"{contract}\n\nOr, where the current evidence above covers what this "
        "change requires, reuse it instead of running it again, naming exactly "
        f"its revision:\n\n  {models._VERIFICATION_REUSED_MARKER} "
        f"{models._REVISION_PREFIX}{handed.revision}"
    )
