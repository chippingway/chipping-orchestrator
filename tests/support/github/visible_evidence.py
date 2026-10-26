# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A comment of ours showing a verification artifact's evidence in view, with no hidden payload.

Literal text, spelled the way an earlier build published artifacts before
their evidence was hidden: a prose preamble naming the witness and the
identity, a rule, the one command with its exit status and transcript, and
then the very header and marker an artifact closes on, its digest taken over
exactly that command. It shows `SHOWN` and nothing else, yet carries no
payload, so it has to read back as no artifact at all -- never as `SHOWN`.
"""
from __future__ import annotations

from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from tests.support.github.factories import make_verification_artifact

# The pull request the comment is on.
_PR_NUMBER = 12

# A reviewer-reported run of the suite that exited 1, revision 2 on that pull
# request, on the very head it answers for.
SHOWN = make_verification_artifact(
    _PR_NUMBER,
    source=EvidenceSource.REVIEWER_REPORTED,
    target_head="3f786850e387550fdab836ed7e6dc881de23001b",
    artifact_revision=2,
    receipt="issue-7-verification-2",
    commands=(
        VerifiedCommand("uv run pytest tests", 1, "collected 12 items\n\n1 failed, 11 passed in 0.4s"),
    ),
)

COMMENT = (
    "### :microscope: Workflow verification artifact, revision 2\n"
    "\n"
    ":eyes: **Reviewer-reported evidence.** A reviewer run reported the commands below; "
    "this orchestrator did not observe them run.\n"
    "\n"
    "Repository `chippingway/chipping-orchestrator`, pull request #12. Evidence about "
    "commit `3f786850e387550fdab836ed7e6dc881de23001b` (tree "
    "`4b825dc642cb6eb9a060e54bf8d69288fbee4904`), gathered under verification context "
    "revision `verify.v1-9f86d081`, for review subject "
    "`1f40fc92da241694750979ee6cf582f2d5d7d28e` against requirements revision "
    "`9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08`. This pull "
    "request's head was `3f786850e387550fdab836ed7e6dc881de23001b` when this artifact was "
    "written.\n"
    "\n"
    "It supersedes every lower-numbered verification artifact on this pull request, which "
    "remain here only as history. It summarizes no developer run and replaces none: the "
    "developer report on this pull request keeps its own source identity, and the "
    "description is untouched.\n"
    "\n"
    "---\n"
    "\n"
    "`uv run pytest tests` -- exit 1\n"
    "\n"
    "```text\n"
    "collected 12 items\n"
    "\n"
    "1 failed, 11 passed in 0.4s\n"
    "```\n"
    "\n"
    "<!--orchestrator-verification-artifact:receipt=issue-7-verification-2:pr=12:"
    "revision=2:source=reviewer-reported:repository=chippingway/chipping-orchestrator:"
    "tested=3f786850e387550fdab836ed7e6dc881de23001b:"
    "tree=4b825dc642cb6eb9a060e54bf8d69288fbee4904:"
    "head=3f786850e387550fdab836ed7e6dc881de23001b:"
    "subject=1f40fc92da241694750979ee6cf582f2d5d7d28e:"
    "requirements=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08:"
    "context=verify.v1-9f86d081:"
    "content=c134d844af5f61df988633536e9084ef604fc6b1dab130d5e7bf9ae8ea3e9953-->\n"
    "\n"
    "<!--orchestrator-comment-->"
)
