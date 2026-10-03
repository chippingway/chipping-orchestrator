# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification artifact format that showed its evidence, read and never written.

Artifacts were once published with their evidence in view: a preamble naming
the witness and the whole identity in prose, a rule, and then every command
with its exit status and transcript, above the same hidden header and marker
the current format closes on. Pull requests still carry them, and evidence
settled on one stays settled -- its digest was taken over that very evidence
section, which is the spelling `verification_evidence` still hashes. So this
owner keeps the two things a reader needs of such a comment: the commands its
visible section reads back as, and the exact body that format spelled an
artifact as. Nothing publishes it.

Frozen rather than derived from the current writer. Every sentence below is
the text those comments were posted with, so rewording one to match the
current format would leave each historical comment re-rendering otherwise than
it reads, and so reading as no artifact at all. The format's own tests hold it
to comments spelled out literally for the same reason.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from orchestrator.github import comments as _comments, verification_evidence as _evidence

if TYPE_CHECKING:
    from orchestrator.github.verification_artifacts import VerificationArtifact

_WITNESS: Mapping[_evidence.EvidenceSource, str] = MappingProxyType({
    _evidence.EvidenceSource.ORCHESTRATOR_EXECUTED: (
        ":robot: **Orchestrator-executed evidence.** This orchestrator ran the "
        "commands below itself and observed the status each exited with."
    ),
    _evidence.EvidenceSource.REVIEWER_REPORTED: (
        ":eyes: **Reviewer-reported evidence.** A reviewer run reported the "
        "commands below; this orchestrator did not observe them run."
    ),
})

# What closed the visible identity and opened the evidence. The reader cuts the
# evidence out on it, so it is the one place the two halves of a body met.
_PREAMBLE_END = "\n\n---\n\n"

_PREAMBLE = (
    "### :microscope: Workflow verification artifact, revision {revision}\n\n"
    "{witness}\n\n"
    "Repository `{repository}`, pull request #{pr}. Evidence about commit "
    "`{tested}` (tree `{tree}`), gathered under verification context revision "
    "`{context}`, for review subject `{subject}` against requirements revision "
    "`{requirements}`. {head}\n\n"
    "It supersedes every lower-numbered verification artifact on this pull "
    "request, which remain here only as history. It summarizes no developer "
    "run and replaces none: the developer report on this pull request keeps "
    "its own source identity, and the description is untouched."
) + _PREAMBLE_END

_TESTED_HEAD = "This pull request's head was `{head}` when this artifact was written."

_CARRIED_HEAD = (
    "This pull request's head was `{head}` when this artifact was written: an "
    "equivalent-tree target, a different commit proved to carry the same tree "
    "`{tree}`. The commands below ran on `{tested}`, not on `{head}`; this "
    "evidence is carried onto it, not run there again."
)

_SEPARATOR = "\n\n"

# What one rendered command reads back as. Permissive on purpose: the exact
# re-render is what decides whether a body is an artifact at all, so this has
# only to recover what a rendering wrote. The transcript is taken up to the
# first line that opens with a fence, which is why no transcript may carry one.
_ENTRY = re.compile(
    r"`(?P<command>[^`\n\r]+)` -- exit (?P<exit_status>-?[0-9]+)"
    r"(?:\n\n```text\n(?P<output>.*?)\n```)?",
    re.DOTALL,
)


def canonical_body(artifact: VerificationArtifact) -> str:
    """The one body this format spelled `artifact` as, however long it comes out.

    Unbounded, as the current format's is: a comment is checked against it,
    and how long the current writer would make the same artifact is no
    question this answers.
    """
    return (
        f"{_preamble(artifact)}{artifact.evidence}{_SEPARATOR}"
        f"{artifact.header}{_SEPARATOR}{_comments.ORCHESTRATOR_COMMENT_MARKER}"
    )


def commands_in(body: str, header_at: int) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """The commands one body's visible evidence section reads back as, or None for anything else.

    The section runs from the rule closing the preamble to the header at
    `header_at`. What is recovered is only a candidate: the caller spells the
    whole artifact again and keeps it only when that comes back byte for
    byte. So a body with no preamble, and anything the entries read back as
    but a command this format would publish -- one quoting a receipt marker
    of ours, one claiming a status of more digits than Python converts -- is
    None here rather than a raise on a caller asking what a comment is.
    """
    preamble_end = body.find(_PREAMBLE_END)
    if preamble_end < 0:
        return None
    evidence = body[preamble_end + len(_PREAMBLE_END):header_at].removesuffix(_SEPARATOR)
    if evidence == _evidence.NOTHING_RAN:
        return ()
    try:
        return _entries_of(evidence)
    except ValueError:
        return None


def _preamble(artifact: VerificationArtifact) -> str:
    """The visible lines this format opened an artifact with: who witnessed what, about what."""
    head = _TESTED_HEAD if artifact.tested_sha == artifact.target_head else _CARRIED_HEAD
    return _PREAMBLE.format(
        witness=_WITNESS[artifact.source],
        revision=artifact.artifact_revision,
        repository=artifact.repository,
        pr=artifact.pr_number,
        tested=artifact.tested_sha,
        tree=artifact.tested_tree,
        context=artifact.context_revision,
        subject=artifact.review_subject,
        requirements=artifact.requirements_revision,
        head=head.format(
            head=artifact.target_head, tested=artifact.tested_sha, tree=artifact.tested_tree,
        ),
    )


def _entries_of(evidence: str) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """Each rendered entry off the front, or None at the first that is not one.

    Off the front rather than by splitting, since a transcript may carry
    anything a rendering could not have put between two entries.
    """
    found = []
    rest = evidence
    while rest:
        entry = _ENTRY.match(rest)
        if entry is None:
            return None
        found.append(_evidence.VerifiedCommand(
            command=entry["command"],
            exit_status=int(entry["exit_status"]),
            output=entry["output"] or "",
        ))
        rest = rest[entry.end():].removeprefix(_SEPARATOR)
    return tuple(found)
