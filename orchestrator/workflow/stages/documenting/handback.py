# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A docs pass that changed the pull request's content, handed back to `validating` for its report and a review.

The approval that moved the label here was of the head before the docs
commit, the evidence it rests on answers for that head, and the developer
report the pull request carries describes the work the reviewer saw. A pass
that published a docs commit -- a fresh push, commits an earlier tick left
unpushed, or the commit a `docs_settled_sha` receipt names, which the gate
let through or an authorized settlement published -- moves the pull request
onto content none of them is about. Handed to `in_review`, the ready ping
would offer a human a head nobody reviewed, verified, or reported on.

So the completion is one write that says so (`_hands_back_for_review`), landed
through the same checkpoint every completion lands through
(`handoff._completes`) and relabelled to `workflow:validating` only behind a
write GitHub confirmed. It stamps the head the pass published with no verdict,
since `in_review` reads a verdict as a head documented after its approval. It
records the report debt that head is owed (`report_rewrite_debt`), read off
the receipts the publication itself wrote and nothing else: the
code-publication receipt has to name the published commit on the pull request
the issue pins, and the head it replaced is the lease the gate recorded
beside the docs receipt (`docs_settled_lease`) -- which is what the settled
report, or the approval squash a proved lineage links it to, is about. The
code-publication receipt's own lease is never read for it, since any later
republication rewrites it: a recovery that pushes the docs commit again over
itself leaves it naming the docs commit, and a rewrite of a head onto itself
is no debt at all. A docs receipt with no readable lease beside it --
missing, `null`, or no commit id, none of which the gate writes -- is a
record something edited, and the hand-back holds over it with nothing
written, announced, or relabelled, the record left for a human to repair
rather than read off anything else or erased. It writes the
approval null, since no approval is of the docs commit, and retires the
current evidence into history as invalidated, keeping its whole binding, so a
squash's carry still proves that lineage (`report_squash_lineage`). That
retirement is required rather than best-effort, and measured over the whole
hand-back with the approval already cleared: a hand-back landed with the
evidence still current would leave the review it buys handed the evidence of
the head before it. And it marks the commit handed back
(`docs_handed_back_sha`). It spends one review round as well, since the
review it buys is one more the cap has to count: an approval spends none, so
a head approved and handed back without one would be reviewed again at the
same count, for as many docs changes as a pass makes. The write that records
the hand-back is the one that spends it, so it is spent exactly once however
the hand-back is retried. `validating`'s report hold then asks the developer
for a report of the published head with nobody involved
(`stages/validating/report_refresh.py`), the previous report and the commit it
was written about left as they are, and the reviewer runs once that report
settles, owing evidence of its own -- or parks `review_cap` where that round
was the last.

A receipt that proves no publication of the head records no debt and the pass
is handed back all the same, since the head still carries content no review
covered: the reviewer road then holds the report it finds to the head, as it
does for every head nobody proved this orchestrator's. A proved debt, or an
evidence retirement, the comment has no room for stops the handoff with
nothing announced or written, as a completion the comment has no room for
does, and the receipt standing over the published pass is what the next tick
finishes it from.

The marker is what lets the relabel survive a crash. The dispatcher holds
this stage while a report debt stands (`workflow/engine/dispatch_guards.py`),
so a write that landed with its relabel lost would hold the issue here for
good, its receipt already consumed. Where the debt still names exactly the
commit this stage marked, on the pull request the issue pins, the dispatcher
finishes that relabel instead (`_owes_the_relabel`); every other debt -- one
somebody else's push left, or one a later rewrite moved onto another head --
is held as before. A write that did not land leaves the receipt, and the next
tick hands the pass back from it, announcing it again.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_rewrite_debt as _rewrite_debt,
    report_rewrite_room as _rewrite_room,
    review_subjects as _review_subjects,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.documenting import handoff as _handoff, models as _models, state as _state
from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state
from orchestrator.workflow.stages.validating import rounds as _rounds, state as _validating_state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The completion of a pass handed back: the completion every pass lands, owning
# as well the report debt it records, the evidence it retires and the history
# that goes into, the approval it writes null, and the review round it spends,
# and decided as well on the debt it carries onto the published head and the
# round it counts from.
_HANDBACK = _handoff._COMPLETION.owning(
    _rewrite_debt.REWRITE_DEBT,
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _review_subjects.APPROVED_SUBJECT,
    _validating_state._REVIEW_ROUND,
).deciding_on(_rewrite_debt.REWRITE_DEBT, _validating_state._REVIEW_ROUND)

_HANDED_BACK_NOTICE = (
    "{notice}\n\nThe docs commit `{commit}` changed this pull request's content, so it goes back to "
    "`workflow:validating`: the developer reports on it, and a fresh review and verification follow "
    "before it is offered for merge."
)


def _hands_back_for_review(ctx: _models._DocumentingContext, checked_sha: str, notice: str) -> None:
    """Stamp the docs commit `checked_sha` a pass published, record what it invalidated, and hand it to `validating`.

    `notice` is what the pull request is told about the publication; the
    hand-back is said beneath it. The rewrite is read before the stamp, which
    consumes the receipt and the lease it is read off. A docs receipt naming
    `checked_sha` whose lease is damaged refuses the whole hand-back
    (`_lease_damaged`): nothing is written, announced, or relabelled, and the
    record is left as it stands for a human to repair. Writes pinned state
    otherwise; the caller returns unconditionally.
    """
    if _lease_damaged(ctx.state, checked_sha):
        ctx.state.withheld = True
        log.error(
            "issue=#%d the docs receipt for %s carries no readable `%s`, so the head its push replaced -- "
            "the head its report debt is owed from -- is unknown; holding the hand-back with the record "
            "left as it stands for a human to repair",
            ctx.issue.number, checked_sha, _state._SETTLED_DOCS_LEASE,
        )
        return
    rewrite = _published_docs_rewrite(ctx, checked_sha)
    _handoff._stamp_docs_verdict(ctx.state, checked_sha, None)
    if not _stages_the_handback(ctx, checked_sha, rewrite):
        ctx.state.withheld = True
        log.error(
            "issue=#%d published the docs commit %s and the report debt it is owed, or the evidence it "
            "retires, does not fit on the pinned state comment; announcing and relabelling nothing, for the "
            "next tick to read",
            ctx.issue.number, checked_sha,
        )
        return
    _handoff._completes(
        ctx, _HANDBACK, _HANDED_BACK_NOTICE.format(notice=notice, commit=checked_sha), WorkflowLabel.VALIDATING,
    )


def _stages_the_handback(
    ctx: _models._DocumentingContext, checked_sha: str, rewrite: _rewrite_debt.RewriteDebt | None,
) -> bool:
    """Stage the retirements, the report debt `rewrite`, the marker, and the round a published `checked_sha` owes.

    False for want of room: for a proved debt, or for the current evidence's
    retirement, the comment has no room for. The approval goes first, since
    writing it null only shrinks the comment, so both are measured over the
    comment it leaves. A receipt that proves no publication, and a standing
    claim the rewrite cannot be carried onto, record no debt and no marker,
    and the pass is handed back without them -- still spending the round,
    since the review it buys is owed either way.
    """
    state = ctx.state
    if state.get(_review_subjects.APPROVED_SUBJECT) is not None:
        state.set(_review_subjects.APPROVED_SUBJECT, None)
    if rewrite is None:
        log.warning(
            "issue=#%d the code-publication receipt does not prove the docs commit %s published; "
            "recording no report debt for it", ctx.issue.number, checked_sha,
        )
    elif _rewrite_debt.records_rewrite(state, rewrite):
        state.set(_state._HANDED_BACK_DOCS_SHA, checked_sha)
    elif _rewrite_room.outgrows_the_comment(state, rewrite):
        return False
    else:
        log.warning(
            "issue=#%d the report debt standing on PR #%d cannot be carried onto the docs commit %s; "
            "leaving it as it is", ctx.issue.number, rewrite.pr_number, checked_sha,
        )
    state.set(_validating_state._REVIEW_ROUND, _rounds._next_review_round(state))
    return _retires_the_evidence(state)


def _retires_the_evidence(state: PinnedState) -> bool:
    """Stage the current evidence retired into history as invalidated; False where the comment has no room for it.

    Measured over the whole hand-back staged before it, the approval already
    written null. The evidence keeps its whole binding as it goes, since a
    squash's carry is what proves a report of the approved commit links to
    the head the docs commit replaced. Required rather than best-effort: a
    hand-back that landed with the evidence still current would hand the
    reviewer of the docs commit evidence of the head before it, and the
    invalidation is what it owes. True where there is none to retire.
    """
    if state.get(_evidence_records.CURRENT_EVIDENCE) is None:
        return True
    return _evidence_settlement.retire_current_evidence(state)


def _published_docs_rewrite(
    ctx: _models._DocumentingContext, checked_sha: str,
) -> _rewrite_debt.RewriteDebt | None:
    """The rewrite the receipts prove the docs commit `checked_sha` was, or None.

    The code-publication receipt has to name `checked_sha` as the commit
    published onto the pull request the issue pins (`_publication_proved`),
    and the head it replaced is the lease the gate recorded beside the docs
    receipt naming it -- the head the pass was entered on, or the one an
    adjudication froze. The code-publication receipt's own lease is never
    read for it, since any later republication rewrites that, a recovery that
    pushes the docs commit over itself leaving it naming the docs commit; and
    a rewrite of a head onto itself is no debt. The branch is the one every
    push of this issue resolves.
    """
    state = ctx.state
    number = _publication_proved(state, checked_sha)
    previous = _payloads.as_hex(state.get(_state._SETTLED_DOCS_LEASE), _formats.COMMIT_LENGTHS)
    proved = (
        number,
        previous,
        previous != checked_sha,
        state.get(_state._SETTLED_DOCS_SHA) == checked_sha,
    )
    if not all(proved):
        return None
    return _rewrite_debt.RewriteDebt(
        pr_number=number,
        branch=_naming._resolve_branch_name(state, ctx.spec, ctx.issue.number),
        previous_head=previous,
        rewritten_head=checked_sha,
    )


def _publication_proved(state: PinnedState, checked_sha: str) -> int:
    """The pull request the code-publication receipt names `checked_sha` published onto, or 0 where it does not.

    Only the pull request the issue pins, and only a whole commit id, each
    read fail-closed.
    """
    number = _late_publication_state._recorded_pull_request(state)
    published = (
        checked_sha,
        _late_publication_state._published_commit(state) == checked_sha,
        _late_publication_state._published_pull_request(state) == number,
    )
    return number if all(published) else 0


def _lease_damaged(state: PinnedState, checked_sha: str) -> bool:
    """Whether the docs receipt naming `checked_sha` stands short of a readable lease.

    The gate writes the two in one write, and the stamp drops them together,
    so a receipt with no lease beside it -- missing, `null`, or no whole
    commit id -- is a record something edited, and the head its report debt
    is owed from cannot be read off it. Not current state to act on: the
    hand-back holds over it rather than recording a debt from anything else
    or erasing it. A receipt naming another commit, or none, is no claim
    about `checked_sha`.
    """
    if state.get(_state._SETTLED_DOCS_SHA) != checked_sha:
        return False
    return not _payloads.as_hex(state.get(_state._SETTLED_DOCS_LEASE), _formats.COMMIT_LENGTHS)


def _owes_the_relabel(state: PinnedState) -> bool:
    """Whether the report debt `state` carries is the one this stage's hand-back recorded, its relabel still owed.

    Asked by the dispatcher of an issue still labelled `workflow:documenting`.
    Only a debt that reads whole, names the pull request the issue pins, and
    names exactly the docs commit the hand-back marked: the write that records
    both is the hand-back's alone, so this is that write having landed with the
    relabel behind it lost. A debt on another head, another pull request, or
    nobody can read is not this stage's to send on.
    """
    debt = _rewrite_debt.read_rewrite_debt(state)
    marked = _payloads.as_hex(state.get(_state._HANDED_BACK_DOCS_SHA), _formats.COMMIT_LENGTHS)
    if debt is None or not marked:
        return False
    return (debt.pr_number, debt.rewritten_head) == (_rewrite_debt.pinned_pull_request(state), marked)
