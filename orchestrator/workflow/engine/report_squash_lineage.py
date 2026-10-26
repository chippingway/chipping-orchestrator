# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the settled report's approved commit is the one this orchestrator squashed into the head a rewrite replaced.

An approval's squash moves the pull request off the commit the settled report
is about onto one with the same tree, and an automatic base rebase, or the
docs commit a final-docs pass publishes on it, can then move it again. The
rewrite debt that leaves (`report_rewrite_debt`) names the squash as the head
it replaced, while `developer_report_current`
still names the approved commit before the squash. Neither record is wrong,
and neither is rewritten here: the report is an account of the commit it
names, and the debt of the head the rebase actually replaced. What is missing
is the link between them, and this owner proves it (`lineage_verdict`), so
that a fresh report of the rewritten head can be asked for without a human.
Reading it changes nothing: no record is relabelled, written, or dropped.

The link is the approval squash's own durable record. Every carry of
verification evidence onto a head it did not run on is recorded by that
squash alone (`verification_carry_forward`, `stages/validating/squash_evidence.py`),
in the write settling its handoff, once it proved that the approved commit and
the head it published read as one tree and that the review carried is the
approved one, unchanged. Its binding keeps every half of that: the commit that
was tested -- the approved one, which the approved subject is about -- and its
tree, the head the squash published, the pull request and branch, and the
approved subject's report revision, digest, and requirements. A carry is read
wherever this issue still keeps it -- owed, current, or in the bounded
history, whatever retired it -- through the evidence domain's own readers,
since what is asked is what the squash did, never whether its evidence still
answers for anything: neither the verification context nor the artifact is
read. That freshness is the evidence domain's, and nothing here feeds it.

PROVED only where all of it agrees. The rewrite debt reads whole, names the
pull request the issue pins and the head that pull request stands on, and is
on the settled report's pull request and branch. A recorded carry is of that
settled report EXACTLY -- the commit it is about, its revision and digest,
and the requirements it was written against -- on the same repository, pull
request, and branch, onto the very head the debt says its rewrite replaced.
And this repository, read again in the issue's checkout, still holds both
commits as the one tree the carry recorded. Equal trees alone are not it,
nor is ancestry, nor the squash's temporary `late_collapse_*` recovery
fields, which are read nowhere here. A debt a later base advance retargeted
still names the squash as the head it replaced, so the proof stands for the
latest head it names.

Anything short of that DEFERS, which proves nothing and leaves the caller
where it would be without this owner: no debt or settled report that reads,
a debt about another pull request, branch, or head, an older or later report
than the one the squash carried, requirements that differ, no carry at all,
or a commit whose tree differs from the one recorded. A reading nobody could
take HOLDS -- a checkout not on this host, or a commit git would not read --
for the caller to interpret.

The validating report hold (`stages/validating/report_refresh.py`) is its
consumer. It asks only where `RewriteDebt.owes_a_refresh` leaves the settled
report to this proof (`squashed`) -- a report of neither head the debt names,
on its pull request and branch, against the requirements the issue carries
now -- and reads PROVED as a settled report the debt is owed a fresh report
of `head` for, once that report re-reads intact at its location. DEFER leaves
the stale report to the reviewer road's refusal, as though nothing had asked,
and a HOLD holds the reviewer with no developer run, for the next tick to read
again.

The half of that proof no debt is needed for -- a carry EXACTLY of a named
review onto a named head, on the settled report's pull request and branch,
and both commits read again as the tree it recorded -- is asked on its own as
well (`squash_verdict`), with the same verdicts. The debt's proof names the
review of the settled report itself, so its rule is the one above; the
final-documentation proof (`final_docs_proof`) names the approved subject its
completion records, which holds the head a documenting pass was entered on to
the approved commit it may stand in for -- under the requirements that
approval was given, which for a round an operator's grant bought are the
thread through that grant rather than the ones the report was written against.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_records as _report_records,
    report_rewrite_debt as _rewrite_debt,
    report_settlement_state as _settlement,
    verification_record_state as _evidence_record_state,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
    verification_world as _world,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.review_subjects import ReviewReport, ReviewSubject

_PROVED = ReportEvidence(ReportEvidenceVerdict.PROVED)

_UNRECORDED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "no rewrite debt and settled report both read",
)

_UNEXPLAINED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the rewrite debt is not about the pinned pull request, its head, and the settled report's branch",
)

_UNSQUASHED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "no recorded approval squash carried the settled report onto the head it is asked about",
)

_RETREED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the approved commit and the squash no longer read as the tree the squash recorded",
)

_NO_CHECKOUT = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "the checkout the squash's trees are read in is not on this host",
)

_UNREAD_TREE = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "the approved commit or the squash could not be read",
)


def lineage_verdict(
    spec: _config_models.RepoSpec, issue_number: int, state: PinnedState, head: str,
) -> ReportEvidence:
    """Whether `state`'s settled report was squashed by this orchestrator into the head its rewrite debt replaced.

    `head` is the commit the pinned pull request stands on, which the debt
    has to name as the head its rewrite published. PROVED where the pinned
    records agree and the checkout of `issue_number` reads both commits as
    the recorded tree; DEFER for no proof; HOLD for a tree nobody could read.
    The carry is held to the review of the settled report itself
    (`_reported_review`).
    """
    debt = _rewrite_debt.read_rewrite_debt(state)
    settled = _settlement.read_current_report(state)
    if debt is None or settled is None:
        return _UNRECORDED
    explained = (_rewrite_debt.pinned_pull_request(state), head, settled.subject.pr_number, settled.subject.branch)
    if explained != (debt.pr_number, debt.rewritten_head, debt.pr_number, debt.branch):
        return _UNEXPLAINED
    return squash_verdict(spec, issue_number, state, debt.previous_head, _reported_review(settled))


def squash_verdict(
    spec: _config_models.RepoSpec, issue_number: int, state: PinnedState, squash: str, review: dict,
) -> ReportEvidence:
    """Whether the commit `review` is about is the one this orchestrator's approval squash published `squash` over.

    `review` is the recorded review subject the carry has to answer for,
    exactly as `review_subjects` spells it: the review of the settled report
    itself for `lineage_verdict`, and the approved subject a final-docs
    completion records for `final_docs_proof` -- whose requirements, for a
    round an operator's grant bought, are the thread through that grant, past
    the ones the report was written against. A carry `state` keeps of exactly
    that review onto `squash`, tested on the commit the review is about,
    under its requirements, on the settled report's repository, pull request,
    and branch (`_is_the_squash`), and the checkout of `issue_number` reading
    both commits as the tree a carry recorded. PROVED, DEFER, or HOLD as
    `lineage_verdict` answers them -- DEFER too where no settled report reads.
    """
    settled = _settlement.read_current_report(state)
    approved = ReviewSubject.commit_recorded_in(review)
    carried = () if settled is None else _carries(state)
    trees = {binding.tested_tree for binding in carried if _is_the_squash(binding, settled, squash, review)}
    if not (trees and approved):
        return _UNSQUASHED
    return _trees_verdict(_worktree_paths._worktree_path(spec, issue_number), approved, squash, trees)


def _reported_review(settled: _report_records.CurrentReport) -> dict:
    """The review subject of `settled` itself: about its own commit, under the requirements it was written against."""
    reported = settled.subject
    return ReviewSubject(
        pr_number=reported.pr_number,
        commit=reported.source_sha,
        requirements_revision=reported.requirements_revision,
        report=ReviewReport(
            text="",
            report_revision=settled.report_revision,
            content_revision=settled.content_revision,
            source_sha=reported.source_sha,
            requirements_revision=reported.requirements_revision,
            location=settled.location,
        ),
    ).recorded()


def _carries(state: PinnedState) -> Iterator[_evidence_records.EvidenceBinding]:
    """The binding of every evidence record `state` keeps that carried a run onto a head it did not run on.

    The transaction owed, the current evidence, and every history entry, each
    read by its own reader, so a record nobody can read -- a history that
    will not read included -- is no carry.
    """
    kept = (
        _evidence_record_state.read_pending_evidence(state),
        _evidence_settlement.read_current_evidence(state),
        *(_evidence_settlement.read_evidence_history(state) or ()),
    )
    for record in kept:
        if record is not None and record.binding.tested_sha != record.binding.target.target_head:
            yield record.binding


def _is_the_squash(
    binding: _evidence_records.EvidenceBinding,
    settled: _report_records.CurrentReport,
    squash: str,
    review: dict,
) -> bool:
    """Whether `binding` is the approval squash's carry of `review` onto `squash`.

    The review is the one the carry answers for, exactly, and about the
    commit that was tested, which only the approval squash's carry records;
    the carry answers for `squash` on the settled report's repository, pull
    request, and branch, under the requirements that review was given.
    """
    reported = settled.subject
    carried = binding.target.publication
    return (
        carried.repo_slug, carried.pr_number, carried.branch, carried.source_sha,
        carried.requirements_revision, binding.tested_sha, binding.target.subject,
    ) == (
        reported.repo_slug, reported.pr_number, reported.branch, squash,
        ReviewSubject.requirements_recorded_in(review), ReviewSubject.commit_recorded_in(review), review,
    )


def _trees_verdict(worktree: Path, approved: str, squash: str, trees: set[str]) -> ReportEvidence:
    """Whether `worktree` reads `approved` and `squash` as one of the `trees` a carry recorded.

    Each commit is read as the evidence proof reads one (`verification_world.tree_of`):
    a commit in its own right, never a tag peeling to one, and its full tree.
    """
    if not worktree.exists():
        return _NO_CHECKOUT
    approved_tree = _world.tree_of(worktree, approved)
    squash_tree = _world.tree_of(worktree, squash)
    if not (approved_tree and squash_tree):
        return _UNREAD_TREE
    if approved_tree != squash_tree or approved_tree not in trees:
        return _RETREED
    return _PROVED
