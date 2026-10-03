# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Verification artifact comments exactly as the format before hidden evidence published them.

Literal text, frozen from comments that format wrote, and never rendered by
the code under test: a legacy comment has to keep reading back as the
artifact it was posted as whatever the current writer does, so these cannot
be any writer's output. Each is `make_verification_artifact` on pull request
#12 with the members its name says, and its header names the evidence
revision that artifact was settled under.
"""
from __future__ import annotations

import hashlib

# The defaults: orchestrator-executed, revision 1, the suite and the linter
# both exiting 0, carried onto a head the commands never ran on.
CARRIED = (
    "### :microscope: Workflow verification artifact, revision 1\n"
    "\n"
    ":robot: **Orchestrator-executed evidence.** This orchestrator ran the commands below "
    "itself and observed the status each exited with.\n"
    "\n"
    "Repository `chippingway/chipping-orchestrator`, pull request #12. Evidence about "
    "commit `3f786850e387550fdab836ed7e6dc881de23001b` (tree "
    "`4b825dc642cb6eb9a060e54bf8d69288fbee4904`), gathered under verification context "
    "revision `verify.v1-9f86d081`, for review subject "
    "`1f40fc92da241694750979ee6cf582f2d5d7d28e` against requirements revision "
    "`9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08`. This pull "
    "request's head was `a94a8fe5ccb19ba61c4c0873d391e987982fbbd3` when this artifact was "
    "written: an equivalent-tree target, a different commit proved to carry the same tree "
    "`4b825dc642cb6eb9a060e54bf8d69288fbee4904`. The commands below ran on "
    "`3f786850e387550fdab836ed7e6dc881de23001b`, not on "
    "`a94a8fe5ccb19ba61c4c0873d391e987982fbbd3`; this evidence is carried onto it, not run "
    "there again.\n"
    "\n"
    "It supersedes every lower-numbered verification artifact on this pull request, which "
    "remain here only as history. It summarizes no developer run and replaces none: the "
    "developer report on this pull request keeps its own source identity, and the "
    "description is untouched.\n"
    "\n"
    "---\n"
    "\n"
    "`uv run pytest tests` -- exit 0\n"
    "\n"
    "`uv run ruff check orchestrator tests` -- exit 0\n"
    "\n"
    "```text\n"
    "All checks passed!\n"
    "```\n"
    "\n"
    "<!--orchestrator-verification-artifact:receipt=issue-7-verification-1:pr=12:"
    "revision=1:source=orchestrator-executed:repository=chippingway/chipping-orchestrator:"
    "tested=3f786850e387550fdab836ed7e6dc881de23001b:"
    "tree=4b825dc642cb6eb9a060e54bf8d69288fbee4904:"
    "head=a94a8fe5ccb19ba61c4c0873d391e987982fbbd3:"
    "subject=1f40fc92da241694750979ee6cf582f2d5d7d28e:"
    "requirements=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08:"
    "context=verify.v1-9f86d081:"
    "content=3008c727e9a0fd9254d4c1c223a2a808e47d293db9944c78333db619d5f9b7b8-->\n"
    "\n"
    "<!--orchestrator-comment-->"
)

# Revision 2: a reviewer-reported run of the suite that exited 1, on the very head it
# answers for.
FAILED = (
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

# Revision 3: the defaults with no command at all.
NOTHING_RAN = (
    "### :microscope: Workflow verification artifact, revision 3\n"
    "\n"
    ":robot: **Orchestrator-executed evidence.** This orchestrator ran the commands below "
    "itself and observed the status each exited with.\n"
    "\n"
    "Repository `chippingway/chipping-orchestrator`, pull request #12. Evidence about "
    "commit `3f786850e387550fdab836ed7e6dc881de23001b` (tree "
    "`4b825dc642cb6eb9a060e54bf8d69288fbee4904`), gathered under verification context "
    "revision `verify.v1-9f86d081`, for review subject "
    "`1f40fc92da241694750979ee6cf582f2d5d7d28e` against requirements revision "
    "`9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08`. This pull "
    "request's head was `a94a8fe5ccb19ba61c4c0873d391e987982fbbd3` when this artifact was "
    "written: an equivalent-tree target, a different commit proved to carry the same tree "
    "`4b825dc642cb6eb9a060e54bf8d69288fbee4904`. The commands below ran on "
    "`3f786850e387550fdab836ed7e6dc881de23001b`, not on "
    "`a94a8fe5ccb19ba61c4c0873d391e987982fbbd3`; this evidence is carried onto it, not run "
    "there again.\n"
    "\n"
    "It supersedes every lower-numbered verification artifact on this pull request, which "
    "remain here only as history. It summarizes no developer run and replaces none: the "
    "developer report on this pull request keeps its own source identity, and the "
    "description is untouched.\n"
    "\n"
    "---\n"
    "\n"
    "No verification command was configured, so none ran. This artifact records that "
    "absence and is not evidence that anything passed.\n"
    "\n"
    "<!--orchestrator-verification-artifact:receipt=issue-7-verification-3:pr=12:"
    "revision=3:source=orchestrator-executed:repository=chippingway/chipping-orchestrator:"
    "tested=3f786850e387550fdab836ed7e6dc881de23001b:"
    "tree=4b825dc642cb6eb9a060e54bf8d69288fbee4904:"
    "head=a94a8fe5ccb19ba61c4c0873d391e987982fbbd3:"
    "subject=1f40fc92da241694750979ee6cf582f2d5d7d28e:"
    "requirements=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08:"
    "context=verify.v1-9f86d081:"
    "content=051a7d9bacf4faa8ac9c87e4c02effb8ca47e054f04380c1be9d6a200715802b-->\n"
    "\n"
    "<!--orchestrator-comment-->"
)

# Where the visible identity ends and the evidence section begins, and where
# the evidence ends and the header begins.
_RULE = "\n\n---\n\n"
_HEADER = "\n\n<!--orchestrator-verification-artifact:"
_CARRIED_DIGEST = "3008c727e9a0fd9254d4c1c223a2a808e47d293db9944c78333db619d5f9b7b8"


def transcribing(output: str) -> str:
    """CARRIED's identity reporting one `check` that exited 0 printing `output`, as that format spelled it.

    Spelled from the frozen text rather than by any writer: the same preamble,
    an evidence section of the one command, and the header naming the SHA-256
    of exactly that section -- so a case can make the transcript as long as
    one comment holds.
    """
    evidence = f"`check` -- exit 0\n\n```text\n{output}\n```"
    digest = hashlib.sha256(evidence.encode()).hexdigest()
    preamble = CARRIED[:CARRIED.index(_RULE) + len(_RULE)]
    header = CARRIED[CARRIED.index(_HEADER):].replace(_CARRIED_DIGEST, digest)
    return f"{preamble}{evidence}{header}"
