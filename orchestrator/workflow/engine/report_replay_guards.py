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

Neither answers with a repair. What they answer is whether the records agree,
and a caller that finds they do not stops rather than choosing between them:
these are shapes nothing here produces, so the two of them disagreeing is a
human's to look at.
"""
from __future__ import annotations

from orchestrator.workflow.engine import report_records as _records


def settles_this_transaction(
    handoff: _records.ReportHandoff, pending: _records.PendingReport,
) -> bool:
    """Whether a handoff under this receipt is really about this transaction.

    Every member, because the receipt is what brought the two together and so
    is the one field that cannot corroborate itself. A handoff naming another
    pull request, another commit, or another revision under the same receipt is
    not this transaction's completion -- and read as one, the pending record is
    dropped as already finished while its report has never been published.
    """
    return (
        handoff.pr_number == pending.subject.pr_number
        and handoff.report_revision == pending.report_revision
        and handoff.source_sha == pending.subject.source_sha
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
