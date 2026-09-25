# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow verification artifact a pull request carries, as one comment.

An artifact is the workflow's own evidence about a tested tree. It is
published as a comment of its own, beside the developer report rather than
inside it and never into the description: the report is what a developer run
said and keeps its own source identity, and the description carries the
closing reference, the attribution line, and whatever anybody has written
since. Nothing here rewrites either, so an artifact adds evidence without
taking a sentence away from anybody.

Each artifact says what it is evidence ABOUT and what it is evidence FROM.
About: the repository and pull request, the commit and tree the commands ran
on, the head that pull request carried when the artifact was written, the
review subject and requirements revision it answers for, and the revision of
the verification context it ran under -- four object ids rather than one,
because evidence carried forward, the round it answers, and the head that has
moved since are three different commits, and an artifact that named only one
of them could be read as current when it is not. From: the witness, stated in
the first visible lines, since a reader deciding what to trust reads the
rendered comment rather than the hidden header.

Artifacts accumulate. Each carries its own revision, so several on one commit
read as an ordered history: a later one supersedes its predecessors and leaves
them exactly where they are. The hidden header repeats the whole identity
beside the transaction's receipt and the digest of the evidence, and the
ordinary orchestrator marker closes the body, so every reader that already
passes over our comments passes over this one too -- which is what keeps a
generated artifact from ever being read back as a human's fresh feedback.

A comment is an artifact only when it is OURS and re-renders byte for byte
from the identity and evidence it claims. The header is an HTML comment
anybody can paste, and a maintainer can edit a comment that stays attributed
to us, so neither the marker nor the author proves an artifact alone. One that
does not fit in a comment is refused rather than cut: a truncated transcript
published under the header would read as the whole of what ran.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.github import (
    comments as _comments,
    developer_reports as _reports,
    verification_evidence as _evidence,
)
from orchestrator.github.pinned_state import MAX_PINNED_BODY

# What a thread is searched for when a transaction asks whether its artifact
# already landed. The delimiter after the receipt closes it, so a receipt that
# is a prefix of another does not claim the other's comment.
_RECEIPT_SCOPE = "<!--orchestrator-verification-artifact:receipt={receipt}:"

_HEADER = _RECEIPT_SCOPE + (
    "pr={pr}:revision={revision}:source={source}:repository={repository}"
    ":tested={tested}:tree={tree}:head={head}:subject={subject}"
    ":requirements={requirements}:context={context}:content={content}-->"
)

_CLAIMED_HEADER = re.compile(
    "<!--orchestrator-verification-artifact"
    ":receipt=(?P<receipt>[A-Za-z0-9_.-]+):pr=(?P<pr>[0-9]+)"
    ":revision=(?P<revision>[0-9]+):source=(?P<source>[a-z-]+)"
    ":repository=(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    ":tested=(?P<tested>[0-9a-f]+):tree=(?P<tree>[0-9a-f]+)"
    ":head=(?P<head>[0-9a-f]+):subject=(?P<subject>[0-9a-f]+)"
    ":requirements=(?P<requirements>[A-Za-z0-9_.-]+)"
    ":context=(?P<context>[A-Za-z0-9_.-]+):content=[0-9a-f]+-->",
)

# How each identity field has to be spelled for the header to carry it
# verbatim: no delimiter, no comment terminator, and one spelling per value.
_COUNT = re.compile("[1-9][0-9]*")
_OBJECT_ID = re.compile("[0-9a-f]{40}|[0-9a-f]{64}")
_TOKEN = re.compile("[A-Za-z0-9_.-]{1,128}")
_REPOSITORY = re.compile("[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")

# Every identity field, the type it is, and how it has to be spelled.
_CARRIABLE = (
    ("repository", "repository", str, _REPOSITORY),
    ("pull request number", "pr_number", int, _COUNT),
    ("artifact revision", "artifact_revision", int, _COUNT),
    ("tested commit", "tested_sha", str, _OBJECT_ID),
    ("tested tree", "tested_tree", str, _OBJECT_ID),
    ("target head", "target_head", str, _OBJECT_ID),
    ("review subject", "review_subject", str, _OBJECT_ID),
    ("requirements revision", "requirements_revision", str, _TOKEN),
    ("verification context revision", "context_revision", str, _TOKEN),
    ("receipt", "receipt", str, _TOKEN),
)

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

# What closes the visible identity and opens the evidence. The reader cuts the
# evidence out on it, so it is the one place the two halves of a body meet.
_PREAMBLE_END = "\n\n---\n\n"

_PREAMBLE = (
    "### :microscope: Workflow verification artifact, revision {revision}\n\n"
    "{witness}\n\n"
    "Repository `{repository}`, pull request #{pr}. Evidence about commit "
    "`{tested}` (tree `{tree}`), gathered under verification context revision "
    "`{context}`, for review subject `{subject}` against requirements revision "
    "`{requirements}`. This pull request's head was `{head}` when this artifact "
    "was written.\n\n"
    "It supersedes every lower-numbered verification artifact on this pull "
    "request, which remain here only as history. It summarizes no developer "
    "run and replaces none: the developer report on this pull request keeps "
    "its own source identity, and the description is untouched."
) + _PREAMBLE_END

_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class VerificationArtifact:
    """One complete verification artifact and the identity it is published under.

    `receipt` names the publication transaction. A retry of that transaction
    carries the same receipt and finds whatever an earlier attempt landed,
    while a later artifact on the same commit is another transaction, with a
    receipt and a revision of its own.

    `commands` is published in the order given; the header's digest is taken
    over exactly their rendering, so an artifact reads back equal to the one
    that was posted.

    Refused at construction rather than at publication, so no reading of a
    record can hand a caller an artifact the header could not have carried.
    """

    repository: str
    pr_number: int
    source: _evidence.EvidenceSource
    tested_sha: str
    tested_tree: str
    target_head: str
    review_subject: str
    requirements_revision: str
    context_revision: str
    artifact_revision: int
    receipt: str
    commands: tuple[_evidence.VerifiedCommand, ...] = ()

    def __post_init__(self) -> None:
        refusal = _refusal(self)
        if refusal is not None:
            raise _evidence.ArtifactRefusedError(refusal)

    @property
    def receipt_scope(self) -> str:
        """The header prefix every comment published for this transaction carries."""
        return _RECEIPT_SCOPE.format(receipt=self.receipt)

    @property
    def evidence(self) -> str:
        """The commands and results this artifact reports, rendered."""
        return _evidence.render_commands(self.commands)

    @property
    def content_revision(self) -> str:
        """The revision of this artifact's evidence: the SHA-256 of its exact bytes.

        What a caller hands a reviewer to name the evidence it was shown, and
        what the header carries so a reader can tell the evidence apart from
        the identity wrapped around it.
        """
        return _reports.content_digest(self.evidence)

    @property
    def preamble(self) -> str:
        """The visible lines this artifact opens with: who witnessed what, about what."""
        return _PREAMBLE.format(
            witness=_WITNESS[self.source],
            revision=self.artifact_revision,
            repository=self.repository,
            pr=self.pr_number,
            tested=self.tested_sha,
            tree=self.tested_tree,
            context=self.context_revision,
            subject=self.review_subject,
            requirements=self.requirements_revision,
            head=self.target_head,
        )

    @property
    def header(self) -> str:
        """The hidden line this artifact ends with: its whole identity and its digest."""
        return _HEADER.format(
            receipt=self.receipt,
            pr=self.pr_number,
            revision=self.artifact_revision,
            source=self.source.value,
            repository=self.repository,
            tested=self.tested_sha,
            tree=self.tested_tree,
            head=self.target_head,
            subject=self.review_subject,
            requirements=self.requirements_revision,
            context=self.context_revision,
            content=self.content_revision,
        )


def render_verification_artifact(artifact: VerificationArtifact) -> str:
    """The one comment body `artifact` is published as.

    `ArtifactRefusedError` when that body would not fit in one comment, raised
    before any request is made: GitHub refuses the write, and an excerpt short
    enough to be accepted is not the evidence.
    """
    body = (
        f"{artifact.preamble}{artifact.evidence}{_SEPARATOR}"
        f"{artifact.header}{_SEPARATOR}{_comments.ORCHESTRATOR_COMMENT_MARKER}"
    )
    if len(body) > MAX_PINNED_BODY:
        raise _evidence.ArtifactRefusedError(
            f"the artifact renders to {len(body)} characters, past the "
            f"{MAX_PINNED_BODY} one comment holds",
        )
    return body


def verification_artifact_from_comment(
    comment: Any, *, bot_login: str | None,
) -> VerificationArtifact | None:
    """The artifact one pull-request comment is, or None when it is not one of ours.

    Ours by author, and an artifact by exact re-rendering: the identity and the
    evidence are read back out of the body and rendered again, and anything but
    the same body -- an edited command, a stale digest, a witness swapped for
    the other one, text appended after the marker, a transcript cut short -- is
    not an artifact. Nor is one whose header claims a number of more digits
    than Python converts, which no rendering wrote. A client with no login of
    its own takes the content alone, the same fallback `authored_by_us` takes.

    Every one of those answers None. This is the question asked OF somebody
    else's comment, on a thread anybody can post to, so nothing a comment says
    about itself may leave by an exception -- including the claim that
    reconstructs past what a comment holds, which a body short enough to have
    been posted still makes once its preamble is gone.
    """
    body = getattr(comment, "body", None)
    if not isinstance(body, str) or len(body) > MAX_PINNED_BODY:
        return None
    claimed = _CLAIMED_HEADER.search(body)
    if claimed is None or not _comments.authored_by_us(comment, bot_login=bot_login):
        return None
    artifact = _claimed_artifact(claimed, body)
    if artifact is None:
        return None
    try:
        rendered = render_verification_artifact(artifact)
    except _evidence.ArtifactRefusedError:
        return None
    return artifact if rendered == body else None


def _claimed_artifact(
    claimed: re.Match, body: str,
) -> VerificationArtifact | None:
    """The artifact a body claims to be, before anything checks that it is one.

    None when nothing could be built at all: a witness this format does not
    name, a count too long to convert, an evidence section no rendering wrote,
    or an identity the header could carry but this format refuses.
    """
    fields = claimed.groupdict()
    try:
        return VerificationArtifact(
            repository=fields["repository"],
            pr_number=int(fields["pr"]),
            source=_evidence.EvidenceSource(fields["source"]),
            tested_sha=fields["tested"],
            tested_tree=fields["tree"],
            target_head=fields["head"],
            review_subject=fields["subject"],
            requirements_revision=fields["requirements"],
            context_revision=fields["context"],
            artifact_revision=int(fields["revision"]),
            receipt=fields["receipt"],
            commands=_evidence.commands_from(_evidence_in(body, claimed.start())),
        )
    except ValueError:
        # A refusal, which is one, or a value no rendering could have written.
        return None


def _evidence_in(body: str, header_at: int) -> str:
    """The evidence section one body carries, cut where the two halves meet.

    `ValueError` when the body opens with no preamble at all, which is the
    same answer every other unreadable claim gets.
    """
    opens_at = body.index(_PREAMBLE_END) + len(_PREAMBLE_END)
    return body[opens_at:header_at].removesuffix(_SEPARATOR)


def _refusal(artifact: VerificationArtifact) -> str | None:
    """Why `artifact` cannot be published as it stands, or None when it can.

    An identity field has to be of its own type and spelled so the header
    carries it verbatim, the witness has to be one this format names, and the
    commands have to be the ones their own type already vouched for.
    """
    uncarriable = [
        field_name
        for field_name, attribute, expected, spelling in _CARRIABLE
        if not _spelled(getattr(artifact, attribute), expected, spelling)
    ]
    if uncarriable:
        return f"the {uncarriable[0]} cannot be carried in an artifact header"
    if not isinstance(artifact.source, _evidence.EvidenceSource):
        return "the evidence source is not a witness this format names"
    if not isinstance(artifact.commands, tuple) or not all(
        isinstance(ran, _evidence.VerifiedCommand) for ran in artifact.commands
    ):
        return "the artifact does not carry a tuple of reported commands"
    return None


def _spelled(claimed: Any, expected: type, spelling: re.Pattern) -> bool:
    """Whether one identity field is its own type and spelled the one way.

    `bool` is excluded from every count, since it is an `int` Python would
    render as `True` and no header ever carried.
    """
    if isinstance(claimed, bool) or not isinstance(claimed, expected):
        return False
    return spelling.fullmatch(str(claimed)) is not None
