# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one developer-report publication transaction is recorded as.

A developer run that finishes with a report leaves the orchestrator holding
work GitHub has not been told about: the report still has to reach the pull
request, and the route that produced it still owes its own bookkeeping. Neither
survives the process, so both go onto the pinned comment BEFORE anything is
published -- the report text whole, because a transaction recovered from a text
nobody kept would have to ask an agent to write it again, and a second run is
not the same report.

Three records rather than one, because they answer different questions and have
different lifetimes. A PENDING transaction is work outstanding: it carries
everything a later tick needs to finish what a run that is gone began, and it is
dropped the moment it settles. A CURRENT report is what the pull request carries
now, and it outlives every transaction that put one there. A HANDOFF is the
receipt that one transaction finished, and it is what makes a replay a no-op
instead of a second report on one commit.

The subject is spelled apart from the transaction because it is the whole of
what a completion has to prove AGAIN. A report is about one repository, one pull
request, one branch, one commit, and the requirements revision the run was
actually handed -- and every one of those can move while the transaction is
outstanding. Frozen here, a moved head, a replaced pull request, or an edited
issue is a disagreement the reconciliation can see rather than a publication it
makes anyway. The requirements revision in particular is the one the run was
given, never the one that happens to be current when publication finally
succeeds: stamping a delayed report with a later hash would claim it answered an
edit it never saw.

Every record is additive. An issue that carries none of these keys reads back as
no transaction, no current report, and no handoff, which is exactly what every
issue predating them says without a migration having reached it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.state import WorkflowLabel

# The transaction this issue has outstanding, dropped the moment it settles.
PENDING_REPORT = "developer_report_pending"

# The report the pull request carries now, which outlives every transaction.
CURRENT_REPORT = "developer_report_current"

# The receipt that one transaction finished, which is what makes a replay a
# no-op rather than a second report on the same commit.
REPORT_HANDOFF = "developer_report_handoff"


class ReportMode(StrEnum):
    """Which of the two things a transaction has left to do.

    PUBLISH carries the report text and owes GitHub a comment. VERIFY carries
    no text at all: the developer read a report somebody else published and
    what is owed is a fresh read of that exact location, whose content still
    has to hash to the revision it was verified at. The two are separate
    members rather than "text or no text" because what an empty text MEANS
    differs between them -- for one it is a record too damaged to act on, for
    the other it is the ordinary shape.
    """

    PUBLISH = "publish"
    VERIFY = "verify"


@dataclass(frozen=True)
class ReportSubject:
    """What a report is about, and the only place it may be published.

    Every member is frozen at the moment the transaction is recorded, because
    every one of them is something a later tick could otherwise read for
    itself and get a different answer from. `repo_slug` and `pr_number` are
    what keep a recovered transaction from publishing onto a pull request
    somebody opened in its place; `branch` is the other half of naming a
    publication, since a pull request standing on the commit says nothing
    about where the work would have been pushed; `source_sha` is the commit
    the report reports ON; and `requirements_revision` is the issue content
    the developer run was actually handed.
    """

    repo_slug: str
    pr_number: int
    branch: str
    source_sha: str
    requirements_revision: str


@dataclass(frozen=True)
class PendingReport:
    """One publication transaction, recorded before any of it happens.

    `receipt` names the transaction rather than the report: a retry carries
    the same receipt and finds whatever an earlier attempt landed, while a
    later report on the same commit is a transaction of its own with a receipt
    and a revision of its own.

    `report` is the complete text for a PUBLISH, empty for a VERIFY.
    `location` and `content_revision` are the other way round -- the exact
    place a VERIFY read its report and the digest it read there, and nothing
    for a PUBLISH.

    `watermarks` and `spends` are the bookkeeping this transaction owes if it
    completes, recorded here because the run that earned them is gone by the
    time anything can apply them: the feedback the run actually consumed, and
    the reviewer round or fix bookmarks its route closes. Both are
    `((field, value), ...)`, each pair bounded by the vocabulary its own
    reader holds, so a hand edit cannot turn a recovered transaction into a
    write into any field the workflow has.
    """

    receipt: str
    subject: ReportSubject
    report_revision: int
    mode: ReportMode
    route: WorkflowLabel
    report: str = ""
    location: ReportLocation | None = None
    content_revision: str = ""
    watermarks: tuple = ()
    spends: tuple = ()


@dataclass(frozen=True)
class CurrentReport:
    """The report a pull request carries now, whoever published it.

    Recorded so the reviewer handed a report is handed the one that is
    actually there, and so a later transaction can tell a report it superseded
    from one a human has edited since. `location` is exact in both halves --
    a comment id alone names a comment anywhere in the repository -- and
    `content_revision` is what a reread is compared against.
    """

    subject: ReportSubject
    report_revision: int
    content_revision: str
    location: ReportLocation


@dataclass(frozen=True)
class ReportHandoff:
    """The receipt one finished transaction leaves behind.

    Small on purpose: what it has to answer is whether THIS transaction is
    already done, and the receipt is the whole of that question. The commit and
    the revision travel beside it so an operator reading the comment can say
    which handoff it is without correlating it against a record that is gone.
    """

    receipt: str
    pr_number: int
    report_revision: int
    source_sha: str
