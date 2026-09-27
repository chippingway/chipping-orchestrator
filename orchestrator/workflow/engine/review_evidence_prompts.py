# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a fresh reviewer is told about beside the report it reviews.

Two things. First the workflow evidence that is CURRENT for the very subject
the reviewer is handed, where there is any: the artifact the pull request
carries, re-read and quoted whole -- the witness's preamble and every command
with its exit status and output -- under the revision a reuse has to name, and
never evidence about another head, report, or requirements revision, which is
evidence about something nobody is asking this reviewer to approve. Which
evidence that is, and the proof that it covers the subject, belong to the
validating stage (`stages/validating/review_evidence.py`); this owner renders
what it is handed, and says which of the commands it lists did not exit 0 --
about those commands alone, since the evidence does not say whether they are
the ones this repository requires. Then what this repository configures as its verification --
the commands, or the plain statement that none are configured, since an empty
`VERIFY_COMMANDS` is not evidence that anything passed.

Nothing renders this yet: the reviewer prompt quotes the report alone until the
reviewer round hands evidence over and reads a declaration back.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator import config
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.workflow.engine import (
    review_verification_models as _verification_models,
    verification_records as _records,
)


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


def _verification_block(handed: HandedEvidence | None) -> str:
    """Everything a reviewer is told about verification: the evidence, then the configuration."""
    return f"{_evidence_block(handed)}\n\n{_configured_block()}"


def _evidence_block(handed: HandedEvidence | None) -> str:
    """The current evidence quoted whole, or the note that none covers this subject."""
    if handed is None:
        return (
            "Workflow verification evidence:\nNo current workflow verification "
            "evidence covers this subject, so run the verification yourself."
        )
    current, artifact = handed.current, handed.artifact
    quoted = _quoted(artifact.preamble + artifact.evidence)
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
            "(`VERIFY_COMMANDS` is empty), so nothing the orchestrator runs is "
            "evidence that any check passed: run the checks this repository's "
            "own documentation requires of a change."
        )
    listed = ", ".join(f"`{command}`" for command in commands)
    return (
        "This repository's configured verification commands "
        f"(`VERIFY_COMMANDS`) are, in order: {listed}."
    )
