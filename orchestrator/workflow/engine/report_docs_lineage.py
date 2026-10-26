# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the settled report's approved commit is what a final docs pass documented into the head a rewrite replaced.

A final docs pass that publishes a docs commit completes straight into
`in_review` and leaves the settled report as the approval left it: about the
commit the reviewer was handed, while the pull request stands on the docs
commit, which its completion records apart (`final_docs_records`). A rewrite
of that docs commit -- an automatic base rebase, a conflict resolution --
then records a debt naming the docs commit as the head it replaced
(`report_rewrite_debt`), a head the settled report is not about and no
approval squash's carry reaches. Neither record is wrong, and neither is
rewritten here. What is missing is the link between them, and this owner
proves it (`lineage_verdict`), so that a fresh report of the rewritten head can
be asked for without a human, as it is behind an approval squash
(`report_squash_lineage`). Reading it changes nothing.

The link is the completion itself, and every part of it is proved again
rather than read on its word. PROVED only where all of it agrees: the debt
reads whole, names the pull request the issue pins and the head it stands on,
and is on the settled report's pull request and branch; the completion reads
whole and names the debt's `previous_head` as the docs commit its pass
completed on, a head other than the one it was entered on
(`documented_into`); the approved subject it records covers the settled
report exactly -- its pull request, revision, and digest, about the very
commit the report is about; the head the pass was entered on is that approved
commit, or the squash an approval's own carry of that approved review proves
(`report_squash_lineage.squash_verdict`); and the docs commit has the entry
head in its history in this host's checkout. Anything short of that DEFERS,
and a reading nobody could take -- a checkout not on this host, a lineage git
would not answer -- HOLDS, for the caller to interpret as it interprets the
squash's own proof.

The validating report hold (`stages/validating/report_refresh.py`) is its
consumer, and asks it in place of the squash's proof wherever the debt's
`previous_head` is a completion's docs commit.

The docs commit is a rewrite of the head the settled report is about in its
own right, too, though the pass that published it recorded no debt for it: it
owed no review. Once the issue is back on `validating` for one all the same --
requirements that moved past the approval, a stale approval handed back from
`in_review`, a human's relabel -- the reviewer road would refuse that report
over the docs commit and park, so the report hold stages the debt the commit
leaves there, in the one stage that pays it (`documented_rewrite`): from the
head the pass was entered on onto the docs commit, as the squash's carry and
the debt's own reading then answer it.
"""
from __future__ import annotations

from orchestrator.config import models as _config_models
from orchestrator.git.verification import objects as _verification_objects
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    report_rewrite_debt as _rewrite_debt,
    report_settlement_state as _settlement,
    report_squash_lineage as _squash_lineage,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.review_subjects import ReviewSubject

_PROVED = ReportEvidence(ReportEvidenceVerdict.PROVED)

_UNEXPLAINED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "no rewrite debt about the pinned pull request, its head, and the settled report's branch reads",
)

_UNDOCUMENTED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "no final-documentation completion names the head the rewrite replaced as the docs commit it completed on",
)

_UNCOVERED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the approval the completion followed does not cover the settled report, about the commit it is about",
)

_UNDESCENDED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the docs commit does not descend from the head its pass was entered on",
)

_NO_CHECKOUT = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "the checkout the docs commit's lineage is read in is not on this host",
)

_UNREAD_DESCENT = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "whether the docs commit descends from the head its pass was entered on could not be read",
)


def documented_rewrite(state: PinnedState) -> _rewrite_debt.RewriteDebt | None:
    """The rewrite a final docs pass's docs commit is of the settled report's commit; None where none is owed.

    Only where no debt is claimed at all -- a standing claim is the debt's own
    to answer -- the completion reads whole and published a docs commit, and
    the approval it followed covers the settled report exactly. The rewrite
    runs from the head the pass was entered on to that docs commit, on the
    settled report's pull request and branch. Nothing is staged here: the
    caller holds it to the head the pull request stands on and records it.
    """
    if _rewrite_debt.carries_rewrite_debt(state):
        return None
    final = _final_docs.read_final_docs(state)
    settled = _settlement.read_current_report(state)
    if final is None or settled is None or final.final_head == final.entry_head:
        return None
    if not _covers(final, settled):
        return None
    return _rewrite_debt.RewriteDebt(
        pr_number=settled.subject.pr_number,
        branch=settled.subject.branch,
        previous_head=final.entry_head,
        rewritten_head=final.final_head,
    )


def documented_into(state: PinnedState, previous_head: str) -> _final_docs.FinalDocs | None:
    """The completion whose pass published `previous_head` as its docs commit, read whole; None where there is none.

    A completion that published nothing completed on the head it was entered
    on, which is the squash's own lineage to prove rather than this one's.
    """
    final = _final_docs.read_final_docs(state)
    if final is None or final.final_head != previous_head or final.final_head == final.entry_head:
        return None
    return final


def lineage_verdict(
    spec: _config_models.RepoSpec, issue_number: int, state: PinnedState, head: str,
) -> ReportEvidence:
    """Whether `state`'s settled report was documented by this orchestrator into the head its rewrite debt replaced.

    `head` is the commit the pinned pull request stands on, which the debt
    has to name as the head its rewrite published. PROVED, DEFER, or HOLD as
    `report_squash_lineage.lineage_verdict` answers them.
    """
    debt = _explained_debt(state, head)
    if debt is None:
        return _UNEXPLAINED
    final = documented_into(state, debt.previous_head)
    if final is None:
        return _UNDOCUMENTED
    if not _covers(final, _settlement.read_current_report(state)):
        return _UNCOVERED
    if final.entry_head != final.approved_commit:
        squashed = _squash_lineage.squash_verdict(spec, issue_number, state, final.entry_head, final.approved)
        if not squashed.proved:
            return squashed
    return _descent_verdict(spec, issue_number, final)


def _explained_debt(state: PinnedState, head: str) -> _rewrite_debt.RewriteDebt | None:
    """The debt `state` records over the pinned pull request's `head`, on the settled report's pull request and branch.

    None where no debt or settled report reads, or where the two disagree.
    """
    debt = _rewrite_debt.read_rewrite_debt(state)
    settled = _settlement.read_current_report(state)
    if debt is None or settled is None:
        return None
    explained = (_rewrite_debt.pinned_pull_request(state), head, settled.subject.pr_number, settled.subject.branch)
    recorded = (debt.pr_number, debt.rewritten_head, debt.pr_number, debt.branch)
    return debt if explained == recorded else None


def _covers(final: _final_docs.FinalDocs, settled) -> bool:
    """Whether the approval `final` followed is of the report `settled`: pull request, revision, digest, and commit."""
    covered = (*(ReviewSubject.identity_recorded_in(final.approved) or ()), final.approved_commit)
    reported = (settled.subject.pr_number, settled.report_revision, settled.content_revision)
    return covered == (*reported, settled.subject.source_sha)


def _descent_verdict(
    spec: _config_models.RepoSpec, issue_number: int, final: _final_docs.FinalDocs,
) -> ReportEvidence:
    """Whether the docs commit `final` completed on has the head its pass was entered on in its history."""
    worktree = _worktree_paths._worktree_path(spec, issue_number)
    if not worktree.exists():
        return _NO_CHECKOUT
    descends = _verification_objects._descends(worktree, final.entry_head, final.final_head)
    if descends is None:
        return _UNREAD_DESCENT
    return _PROVED if descends else _UNDESCENDED
