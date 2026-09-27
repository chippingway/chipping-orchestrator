# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a fresh reviewer is handed, and the declaration it closes with.

A reviewer is told three things about verification beside the report it
reviews. First the workflow evidence that is CURRENT for the very subject it
is handed, where there is any: the artifact the pull request carries, re-read
and quoted whole with the revision a reuse has to name, and never evidence
about another head, report, or requirements revision, which is evidence about
something nobody is asking this reviewer to approve. Then what this repository
configures as its verification -- the commands, or the plain statement that
none are configured, since an empty configuration is not evidence that
anything passed. Last, the one declaration its final message has to carry,
spelled from `review_verification_models`, the same source the parser reads.

The policy paragraph is the other half of why the evidence is handed at all.
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
    messages as _messages,
    review_subjects as _review_subjects,
    review_verification_models as _verification_models,
    verification_records as _records,
)

_EVIDENCE_POLICY = (
    "An approval is acted on only when its declaration lists commands that all "
    "exited 0, or reuses current evidence whose commands all exited 0; an "
    "approval without one is not approved. The orchestrator publishes the "
    "evidence you declare on the pull request itself, so while that evidence "
    "covers the commit under review do NOT request changes merely to have a "
    "developer or a human copy a commit SHA, a test count, or a command into "
    "the pull request description or the report. A check that failed, "
    "verification the change still needs, a report claiming something that did "
    "not happen, and evidence about another commit or subject remain changes "
    "to request."
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


def _verification_block(
    handed: HandedEvidence | None, subject: _review_subjects.ReviewSubject | None,
) -> str:
    """Everything a reviewer of `subject` is told about verification.

    The subject's head is the commit a declaration of commands has to name;
    a reviewer handed no subject is told to name the one it checked out.
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
    passed = (
        "every command it lists exited 0" if current.passed
        else "it does NOT show every required command passing"
    )
    quoted = _messages._as_blockquote(artifact.preamble + artifact.evidence)
    return (
        f"Workflow verification evidence (revision `{_verification_models._REVISION_PREFIX}"
        f"{handed.revision}`, re-read in full by the orchestrator from PR "
        f"#{artifact.pr_number}, comment {current.comment_id}). It is the "
        "current evidence for exactly the head, requirements, and report above, "
        f"and {passed}:\n\n{quoted}"
    )


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


def _declaration_contract(handed: HandedEvidence | None, commit: str) -> str:
    """The declaration a reviewer's final message has to carry above its verdict."""
    head = f"`{commit}`" if commit else "the commit `git rev-parse HEAD` names"
    named = commit or "<full commit id>"
    contract = (
        "Declare the verification this review relies on in your final message, "
        "ABOVE the VERDICT line, with every marker line alone on its own line "
        "and outside any code block. For commands you ran yourself in this "
        f"worktree on {head}:\n\n"
        f"  {_verification_models._VERIFICATION_RUN_MARKER} {named}\n"
        f"  {_verification_models._COMMAND_PREFIX} <the exact command line>\n"
        f"  {_verification_models._EXIT_PREFIX} <the exit status it returned>\n"
        "  <any output you quote, as plain lines with no code fences>\n"
        f"  {_verification_models._VERIFICATION_END_MARKER}\n\n"
        f"Repeat the {_verification_models._COMMAND_PREFIX} and "
        f"{_verification_models._EXIT_PREFIX} lines, with any output below them, "
        "for every command in the order you ran them. List only commands you "
        "actually ran, each with the status it really returned; never estimate "
        "a result or copy one from the report."
    )
    if handed is None:
        return contract
    return (
        f"{contract}\n\nOr, where the current evidence above covers what this "
        "change requires, reuse it instead of running it again:\n\n"
        f"  {_verification_models._VERIFICATION_REUSED_MARKER} "
        f"{_verification_models._REVISION_PREFIX}{handed.revision}"
    )
