# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a pull request carries, as one self-proving comment.

A report is published as a comment of its own and never folded into the pull
request's description. The description is shared ground: it carries the
`Resolves #N` that closes the issue on merge, the attribution line a reuse reads
back, a legacy `_Last agent message:_` tail nothing can tell apart from words a
human added under it, and whatever anybody has written since. A rewrite from a
snapshot loses every change made after the snapshot was read, so a report is
appended beside the description and every earlier report stays where it is.

Each comment says what it reports on -- the commit, the requirements revision
the developer run was handed, and its own revision -- and what it supersedes, so
several reports on one commit read as an ordered history rather than as
duplicates. The hidden header repeats that identity beside the transaction's
receipt and the digest of the text, and the ordinary orchestrator marker closes
the body, so every reader that already passes over our comments passes over
this one too.

A comment is a report only when it is OURS and re-renders byte for byte from the
identity and text it claims. The header is an HTML comment anybody can paste,
and a maintainer can edit a comment that stays attributed to us, so neither the
marker nor the author proves a report alone. A report that does not fit in one
comment is refused rather than cut: a truncated excerpt published under the
header would be indistinguishable from the complete report it stood for.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from orchestrator.github import comments as _comments
from orchestrator.github.pinned_state import MAX_PINNED_BODY

# What a thread is searched for when a transaction asks whether its report
# already landed. The delimiter after the receipt closes it, so a receipt that
# is a prefix of another does not claim the other's comment.
_RECEIPT_SCOPE = "<!--orchestrator-developer-report:receipt={receipt}:"

_HEADER = _RECEIPT_SCOPE + (
    "pr={pr}:revision={revision}:commit={commit}"
    ":requirements={requirements}:content={content}-->"
)

_CLAIMED_HEADER = re.compile(
    "<!--orchestrator-developer-report:receipt=(?P<receipt>[A-Za-z0-9_.-]+)"
    ":pr=(?P<pr>[0-9]+):revision=(?P<revision>[0-9]+):commit=(?P<commit>[0-9a-f]+)"
    ":requirements=(?P<requirements>[A-Za-z0-9_.-]+):content=[0-9a-f]+-->",
)

# How each identity field has to be spelled for the header to carry it
# verbatim: no delimiter, no comment terminator, and one spelling per value.
_COUNT = re.compile("[1-9][0-9]*")
_COMMIT = re.compile("[0-9a-f]{40}|[0-9a-f]{64}")
_TOKEN = re.compile("[A-Za-z0-9_.-]{1,128}")

_PREAMBLE = (
    "### :memo: Developer report, revision {revision}\n\n"
    "Reports on commit `{commit}` against requirements revision "
    "`{requirements}`. It supersedes any agent message in this pull "
    "request's description and every lower-numbered developer report on "
    "this pull request, which remain here only as history.\n\n"
    "---\n\n"
)

_SEPARATOR = "\n\n"


class ReportRefusedError(ValueError):
    """A developer report this format will not publish, and why."""


@dataclass(frozen=True)
class DeveloperReport:
    """One complete developer report and the identity it is published under.

    `receipt` names the publication transaction. A retry of that transaction
    carries the same receipt and finds whatever an earlier attempt landed,
    while a later report on the same commit is another transaction, with a
    receipt and a revision of its own.

    `text` is published verbatim -- the header's digest is taken over exactly
    it -- so a report reads back equal to the one that was posted.

    Refused at construction rather than at publication, so no reading of a
    record can hand a caller a report the header could not have carried.
    """

    pr_number: int
    source_sha: str
    requirements_revision: str
    report_revision: int
    receipt: str
    text: str

    def __post_init__(self) -> None:
        refusal = _refusal(self)
        if refusal is not None:
            raise ReportRefusedError(refusal)

    @property
    def receipt_scope(self) -> str:
        """The header prefix every comment published for this transaction carries."""
        return _RECEIPT_SCOPE.format(receipt=self.receipt)


def content_digest(text: str) -> str:
    """The content revision of `text`: the SHA-256 of its exact UTF-8 bytes.

    Exact, because it is what a reread is compared against: a digest that
    forgave whitespace or line endings would call a location somebody edited
    the revision somebody else verified.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_developer_report(report: DeveloperReport) -> str:
    """The one comment body `report` is published as.

    `ReportRefusedError` when that body would not fit in one comment, raised
    before any request is made: GitHub refuses the write, and an excerpt short
    enough to be accepted is not the report.
    """
    body = "".join((
        _preamble(report.report_revision, report.source_sha, report.requirements_revision),
        report.text,
        _SEPARATOR,
        _HEADER.format(
            receipt=report.receipt,
            pr=report.pr_number,
            revision=report.report_revision,
            commit=report.source_sha,
            requirements=report.requirements_revision,
            content=content_digest(report.text),
        ),
        _SEPARATOR,
        _comments.ORCHESTRATOR_COMMENT_MARKER,
    ))
    if len(body) > MAX_PINNED_BODY:
        raise ReportRefusedError(
            f"the report renders to {len(body)} characters, past the "
            f"{MAX_PINNED_BODY} one comment holds",
        )
    return body


def developer_report_from_comment(
    comment: Any, *, bot_login: str | None,
) -> DeveloperReport | None:
    """The report one pull-request comment is, or None when it is not one of ours.

    Ours by author, and a report by exact re-rendering: the identity and text
    are read back out of the body and rendered again, and anything but the same
    body -- an edited sentence, a stale digest, text appended after the marker,
    an excerpt cut short -- is not a report. Nor is one whose header claims a
    number of more digits than Python converts, which no rendering wrote. A
    client with no login of its own takes the content alone, the same fallback
    `authored_by_us` takes.
    """
    body = getattr(comment, "body", None)
    if not isinstance(body, str) or len(body) > MAX_PINNED_BODY:
        return None
    claimed = _CLAIMED_HEADER.search(body)
    if claimed is None or not _comments.authored_by_us(comment, bot_login=bot_login):
        return None
    preamble = _preamble(claimed["revision"], claimed["commit"], claimed["requirements"])
    try:
        report = DeveloperReport(
            pr_number=int(claimed["pr"]),
            source_sha=claimed["commit"],
            requirements_revision=claimed["requirements"],
            report_revision=int(claimed["revision"]),
            receipt=claimed["receipt"],
            text=body[len(preamble):claimed.start()].removesuffix(_SEPARATOR),
        )
    except ValueError:
        # A refusal, which is one, or a count too long to convert.
        return None
    return report if render_developer_report(report) == body else None


def _refusal(report: DeveloperReport) -> str | None:
    """Why `report` cannot be published as it stands, or None when it can.

    An identity field has to be of its own type and spelled so the header
    carries it verbatim. The text has to say something, and may not carry a
    receipt marker of ours: a thread is searched for receipts by substring, so
    a report quoting one would read to that search as the step it names.
    """
    uncarriable = [
        field_name
        for field_name, claimed, expected, spelling in (
            ("pull request number", report.pr_number, int, _COUNT),
            ("report revision", report.report_revision, int, _COUNT),
            ("source commit", report.source_sha, str, _COMMIT),
            ("requirements revision", report.requirements_revision, str, _TOKEN),
            ("receipt", report.receipt, str, _TOKEN),
        )
        if isinstance(claimed, bool)
        or not isinstance(claimed, expected)
        or spelling.fullmatch(str(claimed)) is None
    ]
    if uncarriable:
        return f"the {uncarriable[0]} cannot be carried in a report header"
    if not isinstance(report.text, str) or not report.text.strip():
        return "the report has no text"
    if _comments.carries_reserved_marker(report.text):
        return "the report text carries a receipt marker of this orchestrator's"
    return None


def _preamble(revision: int | str, commit: str, requirements: str) -> str:
    """The visible lines a report opens with: what it covers and what it supersedes."""
    return _PREAMBLE.format(revision=revision, commit=commit, requirements=requirements)
