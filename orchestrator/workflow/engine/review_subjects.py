# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one automated review is about, and what an approval of it covers.

A reviewer reads four things at once: the pull request, the commit it stands
on, the requirements revision it was handed, and the developer report it was
handed beside the diff. Any of them can move while the others stand still -- a
report-only fix round puts a new report on the very commit the last reviewer
approved -- so a verdict is recorded against all four, and nothing keyed on a
commit alone may stand in for a review of a report that commit has since
acquired.

Two records, written by the validating stage and read wherever an approval is
about to be acted on. `review_subject` is the subject the latest reviewer was
handed, put down beside the reviewer spec before the spawn so an operator can
read which report a round saw. `review_approved_subject` is the subject the
latest approval covers, written once the local verify gate has passed, and
the approval RETIRES the ready ping and the final-docs verdict an earlier
approval left: both are keyed on the head alone, so on an unchanged commit they
would advertise the new report as already reviewed, documented, and announced.

`approval_covers_current` is the question every later reader asks: whether the
report this issue records as current is still the one the approval was given.
It compares the pinned records and reads nothing from GitHub -- an edit of the
report comment in place is `stages/validating/review_coverage.py`'s to find.
An approval with no record at all covers only an issue that has no report
either: one approved before the record existed, over a pull request that has
since settled a report, is an approval nothing says was of that report, so the
issue goes back for a review that is. A record present in any shape its reader
refuses covers nothing, so a hand edit sends the issue back to a reviewer
rather than past one.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The subject the latest reviewer was handed.
REVIEW_SUBJECT = "review_subject"

# The subject the latest approval covers.
APPROVED_SUBJECT = "review_approved_subject"

_PR = "pr"

_SHA = "sha"

_REQUIREMENTS = "requirements"

_REPORT_REVISION = "report_revision"

_REPORT_CONTENT = "report_content"

_PR_NUMBER = "pr_number"

# The two head-keyed stamps an approval retires: the final-docs verdict the
# in_review merge gate reads a head as documented by, and the head it last
# pinged a human for.
_DOCS_VERDICT = "docs_verdict"

_READY_PING_SHA = "ready_ping_sha"


@dataclass(frozen=True)
class ReviewReport:
    """The complete developer report one reviewer is handed, as re-read.

    `text` is the whole settled revision -- never an excerpt -- and the members
    beside it say what that report claims to be about, so the prompt can tell
    the reviewer where the branch or the requirements have moved past it.
    """

    text: str
    report_revision: int
    content_revision: str
    source_sha: str
    requirements_revision: str
    location: ReportLocation


@dataclass(frozen=True)
class ReviewSubject:
    """The pull request, head, requirements, and report one review is of.

    `report` is None for an issue that has never settled a developer report,
    which is every pull request opened before reports were published; such a
    subject is still a subject, and a report settling later is a change to it.
    """

    pr_number: int | None
    commit: str
    requirements_revision: str
    report: ReviewReport | None = None

    @property
    def report_identity(self) -> tuple:
        """The pull request and the report revision, as an approval compares them."""
        if self.report is None:
            return (self.pr_number, None, None)
        return (
            self.pr_number,
            self.report.report_revision,
            self.report.content_revision,
        )

    def recorded(self) -> dict:
        """The pinned object this subject is written as."""
        _, revision, digest = self.report_identity
        return {
            _PR: self.pr_number,
            _SHA: self.commit,
            _REQUIREMENTS: self.requirements_revision,
            _REPORT_REVISION: revision,
            _REPORT_CONTENT: digest,
        }


def record_reviewed(state: PinnedState, subject: ReviewSubject) -> None:
    """Stage the subject a reviewer is about to be handed; the caller writes."""
    state.set(REVIEW_SUBJECT, subject.recorded())


def record_approved(state: PinnedState, subject: ReviewSubject) -> None:
    """Stage the subject an approval covers, and retire the stamps it replaces.

    The docs verdict and the ready ping are each keyed on a head, and a new
    approval can be of the head they already name. Left standing, the verdict
    would let the merge gate read the head as documented before this
    approval's docs pass ran, and the ping would keep that gate silent over the
    report the approval was for. Each is dropped only where it is set, so an
    issue that never carried one is not given the key. The caller writes.
    """
    state.set(APPROVED_SUBJECT, subject.recorded())
    for stamp in (_DOCS_VERDICT, _READY_PING_SHA):
        if state.get(stamp) is not None:
            state.set(stamp, None)


def approval_covers_current(state: PinnedState) -> bool:
    """Whether the recorded approval was given the report recorded as current.

    With no approval record at all, only where no report is recorded either
    -- claimed, readable or not -- since an approval nothing identifies may
    have been of any report, or of none. Otherwise the pull request and the
    report revision have to agree -- no report on either side is agreement,
    one report on one side is not -- and an unreadable record on either side
    agrees with nothing.
    """
    if not state.carries(APPROVED_SUBJECT):
        return not _settlement.carries_settled_record(state)
    approved = state.get(APPROVED_SUBJECT)
    if not isinstance(approved, dict):
        return False
    covered = _identity_of(approved)
    return covered is not None and covered == _current_identity(state)


def _identity_of(recorded: dict) -> tuple | None:
    """The pull request and report revision one recorded subject names, or None.

    Both report members absent together is a subject with no report; one
    without the other, or either in a shape its writer never spells, is damage.
    """
    pr_number = _payloads.as_identity(recorded.get(_PR))
    raw_revision = recorded.get(_REPORT_REVISION)
    raw_digest = recorded.get(_REPORT_CONTENT)
    if raw_revision is None and raw_digest is None:
        return (pr_number, None, None)
    revision = _record_values.as_recorded_number(raw_revision)
    digest = _payloads.as_hex(raw_digest, _formats.DIGEST_LENGTHS)
    if not revision or not digest:
        return None
    return (pr_number, revision, digest)


def _current_identity(state: PinnedState) -> tuple | None:
    """The pull request and the report recorded as current, or None for damage.

    Asked of the settled records as CLAIMS first, for the reason every guard
    over them is: a record nobody can read is not an issue without a report,
    and read as one it would match an approval that saw none. A current report
    about another pull request than the one pinned is no report of this one.
    """
    pr_number = _payloads.as_identity(state.get(_PR_NUMBER))
    if not _settlement.carries_settled_record(state):
        return (pr_number, None, None)
    current = _settlement.read_current_report(state)
    if current is None or current.subject.pr_number != pr_number:
        return None
    return (pr_number, current.report_revision, current.content_revision)
