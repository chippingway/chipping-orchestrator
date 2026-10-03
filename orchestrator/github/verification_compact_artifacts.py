# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The compact verification artifact format: a concise summary over hidden evidence.

What a reader sees is what the evidence amounts to rather than the evidence:
whether the recorded checks passed, failed, or never ran, the revision of the
artifact and of its evidence, who witnessed the checks, and the commit they
ran on beside the head the artifact answers for. The commands themselves,
every exit status, and each whole transcript travel in the hidden payload
`verification_payloads` encodes, so a pull request's conversation does not
scroll past every transcript, while a reader that needs the evidence -- a
reviewer handed it after a restart -- decodes exactly what was recorded.

The three outcomes are told apart in words. Passing is at least one check,
every one exiting 0; failing is any check that did not; and evidence of no
check at all is said to be no evidence, never left as a blank that could pass
for a run that succeeded. Evidence carried onto a head it did not run on says
so too: that head is an equivalent-tree carry, and the checks ran on the
tested commit and nowhere else, so a carry never reads as a run on the commit
it was carried to.

The payload sits in an HTML comment of its own, between the summary and the
header `verification_artifacts` closes every body with. The codec escapes both
angle brackets, so nothing in it ends that comment early, renders a
transcript's tail as visible text, or opens a marker of ours. Its opener is
also what tells this format from the legacy one
(`verification_legacy_artifacts`): no command that format showed could carry
a marker of ours, so no comment it published carries this one.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from orchestrator.github import (
    comments as _comments,
    verification_evidence as _evidence,
    verification_payloads as _payloads,
)

if TYPE_CHECKING:
    from orchestrator.github.verification_artifacts import VerificationArtifact

_HIDDEN_OPENER = "<!--orchestrator-verification-evidence "

_HIDDEN_EVIDENCE = f"{_HIDDEN_OPENER}{{payload}}-->"

# The payload is taken up to the first angle bracket, which the codec never
# writes, so the comment's own terminator is the one that closes it.
_HIDDEN_PAYLOAD = re.compile(f"{re.escape(_HIDDEN_OPENER)}(?P<payload>[^<>]*)-->")

_SUMMARY = (
    "### :microscope: Workflow verification artifact, revision {revision}\n\n"
    "{status}\n\n"
    "- **Source:** {source}\n"
    "- **Evidence revision:** `sha256:{content}`\n"
    "- **Tested commit:** `{tested}` (tree `{tree}`)\n"
    "- **Target head:** {head}\n\n"
    "Every recorded command, its exit status, and its complete output are kept "
    "in this comment's hidden evidence payload. This artifact supersedes every "
    "lower-numbered verification artifact on this pull request."
)

_PASSED = ":heavy_check_mark: **Passed:** {total} of {total} recorded checks exited 0."

_FAILED = ":x: **Failed:** {failed} of {total} recorded checks did not exit 0."

_ABSENT = (
    ":warning: **Not verified:** no check ran, so this artifact records that "
    "absence and is not evidence that anything passed."
)

_SOURCE: Mapping[_evidence.EvidenceSource, str] = MappingProxyType({
    _evidence.EvidenceSource.ORCHESTRATOR_EXECUTED: (
        ":robot: orchestrator-executed. This orchestrator ran the checks itself "
        "and observed the status each exited with."
    ),
    _evidence.EvidenceSource.REVIEWER_REPORTED: (
        ":eyes: reviewer-reported. A reviewer run reported the checks; this "
        "orchestrator did not observe them run."
    ),
})

# What the summary says of the head the artifact answers for: the commit the
# checks ran on, or -- for evidence carried forward -- a different commit
# proved to carry the same tree, which the checks never ran on.
_TESTED_HEAD = "`{head}`, the tested commit itself."

_CARRIED_HEAD = (
    "`{head}`, an equivalent-tree carry: a different commit proved to carry "
    "the same tree. The checks ran on the tested commit, not on this head."
)

_SEPARATOR = "\n\n"


def summary(artifact: VerificationArtifact) -> str:
    """The visible lines `artifact` is published as: its outcome, revisions, witness, and provenance."""
    head = _TESTED_HEAD if artifact.tested_sha == artifact.target_head else _CARRIED_HEAD
    return _SUMMARY.format(
        revision=artifact.artifact_revision,
        status=_status(artifact.commands),
        source=_SOURCE[artifact.source],
        content=artifact.content_revision,
        tested=artifact.tested_sha,
        tree=artifact.tested_tree,
        head=head.format(head=artifact.target_head),
    )


def canonical_body(artifact: VerificationArtifact) -> str:
    """The one body this format spells `artifact` as, however long it comes out.

    The payload is encoded first, so evidence with no revision to name is
    `ArtifactRefusedError` -- the codec's refusal -- before the summary would
    name one.
    """
    hidden = _HIDDEN_EVIDENCE.format(payload=_payloads.encode_evidence(artifact.commands))
    return _SEPARATOR.join((
        summary(artifact), hidden, artifact.header, _comments.ORCHESTRATOR_COMMENT_MARKER,
    ))


def carries_hidden_evidence(body: str) -> bool:
    """Whether `body` claims this format, by the payload comment no legacy artifact carries."""
    return _HIDDEN_OPENER in body


def commands_in(body: str, header_at: int) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """The commands the payload ahead of the header at `header_at` decodes to, or None for anything else.

    Only a candidate, as every reading of a body is: the caller spells the
    whole artifact again and keeps it only when that comes back byte for byte.
    """
    hidden = _HIDDEN_PAYLOAD.search(body, 0, header_at)
    if hidden is None:
        return None
    return _payloads.decode_evidence(hidden["payload"])


def _status(commands: tuple[_evidence.VerifiedCommand, ...]) -> str:
    """Whether the recorded checks passed, failed, or never ran, by their own exit statuses."""
    if not commands:
        return _ABSENT
    failed = sum(1 for ran in commands if ran.exit_status != 0)
    if failed:
        return _FAILED.format(failed=failed, total=len(commands))
    return _PASSED.format(total=len(commands))
