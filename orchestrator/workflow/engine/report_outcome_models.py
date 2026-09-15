# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a developer run may close with when its work carries a report.

The developer writes the completion report and the orchestrator publishes it,
so a finished run has exactly two successful ways to hand one over. A report
READY for publication carries its complete text between an opening and a
closing marker line, because only an explicit close shows the text was not cut
short. A report VERIFIED on the pull request carries no text at all -- only the
location the developer read and the revision it read there -- and is an
assertion for the orchestrator to re-read, never proof that anything is
published.

Everything else a run can end in is a refusal, and the refusals stay apart
because their callers route them differently: five are the run itself falling
short and are decided before its message is read, two are about the message of
a run that completed. The spellings live here so the prompts that teach them and
the parser that reads them name one source.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_REPORT_MARKER_PREFIX = "REPORT:"
_REPORT_READY_MARKER = f"{_REPORT_MARKER_PREFIX} READY"
_REPORT_END_MARKER = f"{_REPORT_MARKER_PREFIX} END"
_REPORT_VERIFIED_MARKER = f"{_REPORT_MARKER_PREFIX} VERIFIED"
_REVISION_PREFIX = "sha256:"
_PULL_REQUEST_URL_SHAPE = "https://github.com/<owner>/<repo>/pull/<number>"
_COMMENT_ANCHOR_SHAPE = "#issuecomment-<id>"


class _ReportRefusal(StrEnum):
    """Why a run earns no report outcome.

    The first five are the run not completing, in the order they are asked:
    never started, killed by the shutdown sweep, timed out, refused by its
    provider, exited nonzero. Whatever such a run's last message says, it is
    not a report anybody finished.

    The last two are the last message of a run that DID complete. `NO_MARKER`
    is every reply that never used the contract -- a question, a disagreement,
    an ordinary `ACK:`, prose saying nothing needed to change -- which the
    caller's own readers go on to tell apart. `MALFORMED` is a reply that
    reached for the contract and missed: an unclosed or empty block, text after
    the outcome, a location or revision out of shape, a stray marker line, a
    marker line that may render as code, or an `ACK:` beside it.
    """

    NOT_INVOKED = "not_invoked"
    INTERRUPTED = "interrupted"
    TIMED_OUT = "timed_out"
    PROVIDER_FAILURE = "provider_failure"
    NONZERO_EXIT = "nonzero_exit"
    NO_MARKER = "no_marker"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class _ReportLocation:
    """Where on a pull request the developer says it read the report.

    `slug` and `pull_number` are as the URL spelled them, for the caller to
    hold against the repository and pull request it expects. `comment_id` names
    a conversation comment on that pull request, or is None for its
    description.
    """

    slug: str
    pull_number: int
    comment_id: int | None = None


@dataclass(frozen=True)
class _ReadyReport:
    """The complete report text between the marker lines, for publication."""

    report: str


@dataclass(frozen=True)
class _VerifiedReport:
    """A report the developer asserts is already published at `location`.

    `revision` is the lowercase SHA-256 hex digest of the text it read there.
    Nothing about either has been checked: completing on this outcome is owed a
    fresh read of that location whose text still hashes to `revision`.
    """

    location: _ReportLocation
    revision: str


_ReportOutcome = _ReadyReport | _VerifiedReport | _ReportRefusal
