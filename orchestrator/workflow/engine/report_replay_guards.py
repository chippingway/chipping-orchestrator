# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a record and the settlement beside it are talking about one thing.

A receipt names a transaction, and on every record this workflow writes it names
it uniquely. But the receipt is one field on a comment a human can edit and an
older binary may have written, so a reader that acted on it alone would be
trusting the one member it is least able to check.

Two questions follow from that, and they fail in opposite directions. A handoff
carrying this receipt is the evidence a transaction already finished -- so
believed too readily it DROPS a pending record whose report was never published,
and the report is lost with it. A current report already recorded is the
evidence something newer is on the pull request -- so ignored, a stale record
settles over it and the pull request's newest report is replaced by an older
one.

A third question stands ahead of both and does not involve the receipt at all:
whether the two settled records agree with EACH OTHER. They are written in one
write off one pending record, so the pull request, the revision and the commit
are copied into both -- and a pair that disagrees is one nothing here produced,
whichever transaction's receipt it happens to carry. Asked only under a
matching receipt it would be no question at all for the commonest shape: an
older handoff beside a current report is never compared against the record in
hand, so a disagreement there would be replaced by the next settlement rather
than seen.

Neither answers with a repair. What they answer is whether the records agree,
and a caller that finds they do not stops rather than choosing between them:
these are shapes nothing here produces, so the two of them disagreeing is a
human's to look at.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_records as _records,
    report_settlement_state as _settlement,
)

# Why a settled pair cannot be acted on, in the words its park quotes. Both
# sentences live here rather than beside the park, because what they describe is
# this owner's own judgement of the two records.
UNREADABLE_COMPANIONS = (
    "the record of what the pull request already carries, or of the last "
    "handoff, cannot be read"
)

DISAGREEING_COMPANIONS = (
    "the report recorded as the pull request's own and the last handoff name "
    "different publications"
)


def damaged_companions(state: PinnedState) -> str:
    """Which way the settled pair is damaged, or "" when it is sound.

    Asked before anything is proved, because both companions are things a
    settlement WRITES OVER. A damaged current report waved through as an
    absence is replaced the moment the next transaction settles -- after its
    report has been posted, so the evidence an operator would have repaired it
    from is gone. A damaged handoff waved through is a completed transaction
    nobody can recognize, and the next tick publishes its report again.

    Two ways, and they need telling apart because they ask a human for
    different repairs. A record CLAIMED and unreadable is a field to restore. A
    pair that reads and contradicts ITSELF is two records that cannot both be
    right, and nothing here may choose between them.

    Answered about the pair alone, with no reference to the transaction in hand
    or to any receipt. That is what makes it worth asking at all for the
    commonest shape: a settlement under a PREVIOUS transaction's receipt is
    never compared against the record being reconciled, so a disagreement there
    would otherwise be replaced by the very next settlement rather than seen.
    """
    if not _settlement.carries_settled_record(state):
        return ""
    current = _settlement.read_current_report(state)
    handoff = _settlement.read_handoff(state)
    if current is None or handoff is None:
        return UNREADABLE_COMPANIONS
    return DISAGREEING_COMPANIONS if companions_disagree(current, handoff) else ""


def settles_this_transaction(
    handoff: _records.ReportHandoff,
    current: _records.CurrentReport | None,
    pending: _records.PendingReport,
) -> bool:
    """Whether a handoff under this receipt is really about this transaction.

    Every member of the handoff, because the receipt is what brought the two
    together and so is the one field that cannot corroborate itself. A handoff
    naming another pull request, another commit, or another revision under the
    same receipt is not this transaction's completion -- and read as one, the
    pending record is dropped as already finished while its report has never
    been published.

    The CURRENT report is asked beside it, because the two are written in one
    write and a handoff without one is a settlement that never happened. Read
    on the handoff alone, a receipt matching with no report recorded drops the
    pending record and leaves the pull request carrying nothing -- the exact
    outcome the whole transaction exists to prevent.

    That report is held to the pending record's WHOLE subject rather than to
    the pull request and revision it shares with the handoff. The subject is
    what the settlement copies across verbatim, so every member of it agrees on
    a pair this build wrote -- and the three the handoff cannot carry are
    exactly the ones nothing else here would catch: a current report naming
    another branch, another repository, or another requirements revision reads
    as this transaction's completion on the two fields it does share, and drops
    a pending record whose report was never published.
    """
    if current is None:
        return False
    if current.subject != pending.subject:
        return False
    if current.report_revision != pending.report_revision:
        return False
    return (
        handoff.pr_number == pending.subject.pr_number
        and handoff.report_revision == pending.report_revision
        and handoff.source_sha == pending.subject.source_sha
    )


def companions_disagree(
    current: _records.CurrentReport | None,
    handoff: _records.ReportHandoff | None,
) -> bool:
    """Whether the two settled records contradict each other.

    Asked of any readable pair, whatever receipt it carries, because the two
    are written in ONE write off ONE pending record: the pull request, the
    revision, and the commit are copied into both, so a pair that disagrees on
    any of them is not a settlement this build made.

    Nothing here can tell which of the two to believe, and both answers lose
    something. Taken from the handoff, a transaction is recognized as finished
    whose report the current record says is about some other publication.
    Taken from the current report, a transaction is settled OVER -- replacing
    that record after the new report is posted, which is when the evidence an
    operator would have repaired it from is gone.

    Asked ahead of the receipt comparison rather than beside it, because the
    older-receipt pair is where this is the only question there is: a handoff
    from a previous transaction is never compared against the record in hand,
    so a pair left disagreeing would be silently replaced by the very next
    settlement.
    """
    if current is None or handoff is None:
        return False
    return (
        current.subject.pr_number != handoff.pr_number
        or current.report_revision != handoff.report_revision
        or current.subject.source_sha != handoff.source_sha
    )


def supersedes_the_record(
    current: _records.CurrentReport | None, pending: _records.PendingReport,
) -> bool:
    """Whether the report already recorded is newer than this transaction's.

    Settling a transaction replaces the current report, so a record whose
    revision does not move that number forward would put an OLDER report on the
    pull request's own record of what it carries -- and the next reviewer would
    be handed it.

    Scoped to the pull request the current report is about, since a record for
    some other pull request says nothing about this one's revisions. A
    transaction whose receipt the handoff beside it already names is a replay
    and is answered before this is asked, so what reaches here claiming a
    revision that is not forward is a record nothing here wrote.
    """
    if current is None:
        return False
    if current.subject.pr_number != pending.subject.pr_number:
        return False
    return current.report_revision >= pending.report_revision
