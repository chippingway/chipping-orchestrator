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

Two records. `review_subject` is the subject a reviewer was handed, put down
beside the reviewer spec before the spawn so an operator can read which report
a round saw. `review_approved_subject` is the subject an approval covers,
written once the local verify gate has passed, and recording it RETIRES the
ready ping and the final-docs verdict an earlier approval left: both are keyed
on the head alone, so on an unchanged commit they would advertise the new
report as already reviewed, documented, and announced.

`approval_covers_current` is the question every reader of an approval asks:
whether the report this issue records as current is still the one the approval
was given. It compares the pinned records and reads nothing from GitHub, so a
report edited in place at its location is a question for a fresh reading of
that location, never for these records. An approval with no record at all
covers only an issue that has no report either: one approved before the record
existed, over a pull request that has since settled a report, is an approval
nothing says was of that report. A record present in any shape its reader
refuses covers nothing, so a hand edit is read as no approval rather than as
one.

These helpers are dormant: the validating stage spawns its reviewer without a
subject and acts on an approval without asking whether it covers the current
report, so nothing in production writes or reads either record.
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

# Every member a recorded subject carries, and nothing else.
_MEMBERS = frozenset((_PR, _SHA, _REQUIREMENTS, _REPORT_REVISION, _REPORT_CONTENT))

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

    `report` is None for a subject with no developer report: a pull request
    reviewed while none had settled on it. Such a record is still a subject,
    and a report settling after it is a change to it.
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

    @classmethod
    def identity_recorded_in(cls, recorded: object) -> tuple | None:
        """The pull request and report revision a `recorded` object names, or None.

        None wherever `_RecordedSubject.read` refuses the record, so an
        identity is only ever read off a subject whose every member reads.
        """
        whole = _RecordedSubject.read(recorded)
        if whole is None:
            return None
        return (whole.pr_number, whole.report_revision, whole.content_revision)

    @classmethod
    def requirements_recorded_in(cls, recorded: object) -> str | None:
        """The requirements revision a `recorded` object names, or None.

        None wherever `_RecordedSubject.read` refuses the record: requirements
        read off a subject short of its head or its report would be an
        approval's requirements nobody can say the approval was given.
        """
        whole = _RecordedSubject.read(recorded)
        return None if whole is None else whole.requirements_revision

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


@dataclass(frozen=True)
class _RecordedSubject:
    """Every member one recorded subject names, each read as its writer spells it."""

    pr_number: int | None
    commit: str
    requirements_revision: str
    report_revision: int | None
    content_revision: str | None

    @classmethod
    def read(cls, recorded: object) -> _RecordedSubject | None:
        """Every member a recorded subject names, read together, or None.

        Read whole or not at all, like every pinned record: exactly the members
        `ReviewSubject.recorded` writes, each in the shape it spells them -- a
        pull request that is a number or `null` for none, a requirements
        revision that is a whole digest or "", and the report's revision and
        digest, both `null` for a subject with no report. The head is read off
        the pull request, so a subject naming one names its whole commit id,
        and a subject naming none has "" for a head and no report either.
        Anything else -- a member missing or one nothing writes, a head that
        is no commit or none under a pull request, half a report -- is a
        truncation or a hand edit, and read as an approval it would stand
        behind a ping for a subject nobody can name.
        """
        if not isinstance(recorded, dict) or set(recorded) != _MEMBERS:
            return None
        whole = cls(
            pr_number=_payloads.as_identity(recorded[_PR]),
            commit=recorded[_SHA],
            requirements_revision=recorded[_REQUIREMENTS],
            report_revision=_record_values.as_recorded_number(recorded[_REPORT_REVISION]),
            content_revision=_payloads.as_hex(
                recorded[_REPORT_CONTENT], _formats.DIGEST_LENGTHS,
            ),
        )
        read_whole = (
            whole.pr_number is not None or recorded[_PR] is None,
            whole.requirements_revision == "" or _payloads.as_hex(
                whole.requirements_revision, _formats.DIGEST_LENGTHS,
            ),
            # Both report members read, or both are `null`.
            None not in (whole.report_revision, whole.content_revision)
            or (recorded[_REPORT_REVISION], recorded[_REPORT_CONTENT]) == (None, None),
            # Under no pull request, no head and no report read off one; under
            # one, its whole head.
            whole.commit == "" and whole.report_revision is None
            if whole.pr_number is None
            else _payloads.as_hex(whole.commit, _formats.COMMIT_LENGTHS),
        )
        return whole if all(read_whole) else None


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
    covered = ReviewSubject.identity_recorded_in(state.get(APPROVED_SUBJECT))
    return covered is not None and covered == _current_identity(state)


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
