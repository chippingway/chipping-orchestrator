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

Four records rather than one, because they answer different questions and have
different lifetimes. A DELIVERED report is a completed run's own output, written
before the code it reports on is published and holding everything about the
report that no pull request is needed to say. A PENDING transaction is that same
report bound to the publication it goes onto: it carries everything a later tick
needs to finish what a run that is gone began, and it is dropped the moment it
settles. A CURRENT report is what the pull request carries now, and it outlives
every transaction that put one there. A HANDOFF is the receipt that one
transaction finished, and it is what makes a replay a no-op instead of a second
report on one commit.

The subject is spelled apart from the transaction because it is the whole of
what a completion has to prove AGAIN. A report is about one repository, one pull
request, one branch, one commit, and the requirements revision the run was
actually handed -- and every one of those can move while the transaction is
outstanding. Frozen here, a moved head, a replaced pull request, or an edited
issue is a disagreement a completion can see rather than a publication it makes
anyway. The requirements revision in particular is the one the run was
given, never the one that happens to be current when publication finally
succeeds: stamping a delayed report with a later hash would claim it answered an
edit it never saw.

`HandedRun` beside them is no record at all: it is what a caller tells the
recording about the run -- the road it came down, the requirements revision it
was handed where the caller took a snapshot, and the route bookkeeping the
handover owes where no size gate behind the caller will carry it -- and only the
delivered report built from it reaches the comment.

Every record is additive. An issue that carries none of these keys reads back as
no delivered report, no transaction, no current report, and no handoff, which is
exactly what every issue predating them says without a migration having reached
it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.state import WorkflowLabel

# The report a completed run wrote, before any pull request carries the code it
# is about, and dropped by the write that binds it to one.
DELIVERED_REPORT = "developer_report_delivery"

# The transaction this issue has outstanding, dropped the moment it settles.
PENDING_REPORT = "developer_report_pending"

# The report the pull request carries now, which outlives every transaction.
CURRENT_REPORT = "developer_report_current"

# The receipt that one transaction finished, which is what makes a replay a
# no-op rather than a second report on the same commit.
REPORT_HANDOFF = "developer_report_handoff"

# Whether the transaction that handoff describes was a FIXING round's, which is
# the one thing its settlement cannot do for itself: move a label. It is spelled
# here rather than on the stage that reads it because every settlement writes it
# -- raised by a fixing record's own frozen spends, and retired by every other,
# so the mark and the handoff beside it are always about one transaction.
SETTLED_ROUND = "fixing_round_settled"


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
class DeliveredReport:
    """One completed run's report, recorded before its code is published.

    Everything the RUN settles and nothing the publication does. A report is
    written by a session that ends with the tick, and the code it is about has
    still to pass the size gate and reach a remote -- so what a pull request
    would add to it (which repository, which number, which branch, which
    commit) is unknowable here, while the report text, the revision it is,
    the route that produced it, and the requirements the run was handed are
    settled and cannot be recovered from anywhere else.

    `requirements_revision` is the one member of a subject that belongs to the
    run rather than to the publication, and it is frozen here for the reason
    it is frozen on a transaction: it is the issue content this run was
    actually given, and a report delayed past an edit may not be stamped as
    answering one it never saw.

    `receipt` and `report_revision` are minted with the record, so a
    transaction bound later is the same transaction a retry would find its own
    comment by. Every other member is what the transaction carries unchanged,
    `spends` included: the round and bookmarks the handover this report
    completes owes, frozen by the caller for the settlement to close where
    nothing between the run and that write would have.
    """

    receipt: str
    report_revision: int
    mode: ReportMode
    route: WorkflowLabel
    requirements_revision: str
    report: str = ""
    location: ReportLocation | None = None
    content_revision: str = ""
    watermarks: tuple = ()
    spends: tuple = ()


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

    `mode` is which road settled it, because the digest means a different thing
    on each: a verified location IS the text that hashes to it, while a
    published comment is that text under a header of ours, and a comment cut
    down to the bare text hashes the same. None is a settlement written before
    the member existed, which a reread holds to the stricter reading.
    """

    subject: ReportSubject
    report_revision: int
    content_revision: str
    location: ReportLocation
    mode: ReportMode | None = None


@dataclass(frozen=True)
class ReportHandoff:
    """The receipt one finished transaction leaves behind.

    Small on purpose: what it has to answer is whether THIS transaction is
    already done, and the receipt is the whole of that question. The commit and
    the revision travel beside it so an operator reading the comment can say
    which handoff it is without correlating it against a record that is gone.

    `settled_under` is the workflow label the issue was carrying when the
    settlement landed, and it is the one thing about a completion that no other
    record can reconstruct afterwards. The reconciliation runs ahead of every
    handler on every non-terminal label, so a transaction can settle somewhere
    its own route's stage is not looking -- and a route whose bookkeeping
    includes a hand-back that stage has to make needs to know whether the stage
    was ever there. None is a settlement written before the member existed,
    which every reader holds to the stricter reading.
    """

    receipt: str
    pr_number: int
    report_revision: int
    source_sha: str
    settled_under: WorkflowLabel | None = None


@dataclass(frozen=True)
class HandedRun:
    """The road a run came down, and what the caller froze for it.

    A caller that snapshots what it gave the run names that revision here, and
    the record is stamped with the snapshot rather than with whatever the
    pinned baseline says by the time the report is recorded. A resume the drift
    check launched was handed the content that check hashed; nothing written to
    the baseline after the spawn is anything that session saw, so reading it
    back later could stamp an older report with a newer hash. Empty reads the
    pinned baseline, which is what the check ahead of every other spawn leaves
    for the run behind it.

    `spends` is the route bookkeeping the handover this report completes owes
    -- the reviewer round it lands on, the bookmarks it closes, and any MARK
    that write is to leave for a tick which can do what it cannot -- frozen by
    the caller as `((field, value), ...)` and carried onto the transaction, so
    the write that finally settles the report is one that closes them too. It is
    what a road with no size gate behind it needs: a report delivered with no
    code in it passes no gate, so the caller's own write is the only other
    thing that could carry the round, and a crash in the window between the two
    would leave a handover nothing was counted for. Re-applied from the frozen
    pair rather than recomputed, so a settlement a crash hid and a later tick
    replays counts once. Empty is every road whose bookkeeping is already
    durable elsewhere.

    `watermarks` is the input this run actually consumed, in the same shape and
    for the same reason: a round answering feedback may not record that feedback
    as read until the report answering it reaches the pull request, so the
    readers travel with the report and move in the write that settles it. Empty
    is every road that settles what it delivered for itself, because what it
    delivered is answered whatever the report does.
    """

    route: WorkflowLabel
    requirements_revision: str = ""
    spends: tuple = ()
    watermarks: tuple = ()
