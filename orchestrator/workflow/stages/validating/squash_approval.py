# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the approval a recorded squash was begun under still stands behind publishing it.

A squash is begun only under an approval, staged with the subject it covers
and the claim on the evidence it was proved over in the write that records
the collapse (`approval._squashes_the_approval`). Whatever publishes that
collapse publishes under that approval and nothing else, and a publication
cannot be taken back once it lands, so the approval is held to the
publication before anything goes out rather than only to the relabel behind
it.

Two roads publish it. The recovery of the squash itself, in this stage's
handler (`collapse._finished_collapse`), resumes the push. And the
publication reconciliation the dispatcher asks ahead of every handler pays a
debt, or settles a frozen pair, the squash's size gate recorded before its
push (`stages/implementing/late_reconcile.py`) -- the same push, made before
this stage's handler is reached, and from whichever stage the issue is
labelled when it does. So the question is asked on both: by that recovery,
and by the dispatcher directly ahead of that reconciliation on every label it
publishes from (`holds_the_dispatch`).

The approval stands behind the collapse only while its review subject reads
whole and names the head the collapse was planned over, the evidence its
claim names is proved still standing (`approved_evidence.stands`) -- the claim
read whole, naming the current record exactly with no revision past it, under
the configured verification context, and its artifact still the passing one
that settled -- and the subject it covers still stands: the report it was
given still the current one and reading at its location as it settled
(`review_coverage._approval_stands`), and the issue, read afresh, still
carrying the requirements it was given (`review_coverage._requirements_stand`).
These are the readings every road moving an approval on takes, short of where
the pull request stands. Nothing else stands in for it: a record missing,
`null`, or unreadable, a subject of another commit, evidence no longer
standing, a report or requirements nobody approved, or a collapse record that
will not read whole, which no approval can be bound to.
Nor does where the pull request seems to stand. A reading of it is no proof
the push would publish nothing, and the lease behind the push is taken from
a reading of its own, so a push whose landing nothing proves is a new
publication like any other.

A landing that IS proved needs no approval, because finishing it publishes
nothing: this issue's own receipt names the commit it pushed from the head
the collapse was planned over onto the pull request it records, the checkout
stands on exactly that commit, and no approval or uncounted generation owes
a push of its own (`late_squash_proof._receipted_landing`). The proof is a
reading of a writable checkout, so the commit it proved is what the recovery
is handed (`allowance`) and bound to (`_Gate.no_op_of`): a checkout off it is
refused before anything publishes, and the recovery enters and leases its push
on that very commit, so a remote anywhere else refuses it. It finishes the
bookkeeping -- the notice, the watermarks, the
end of the record -- while the move past `validating` stays held on the
approval's own reading (`approval._persists_then_relabels`), so the next tick
hands the head to a fresh review rather than advancing an approval that does
not stand.

Work that has ended -- a closed issue, or a recorded pull request merged or
closed -- is the stage terminal's, asked ahead of everything that would hold
the tick, and nothing publishes onto it either
(`late_terminal._work_has_ended`). Anything else that does not stand behind
the collapse publishes nothing: the collapse record and every other record
are kept, and the issue parks under `squash_failed`, once
(`review_parks.parks_the_failed_squash`); every tick asks again and mentions
nobody twice. Evidence nobody could read holds the tick for the next to ask
again.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow import transitions as _transitions
from orchestrator.workflow.engine import review_subjects as _review_subjects
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
    late_squash_proof as _late_squash_proof,
    late_terminal as _late_terminal,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    handoff as _handoff,
    review_coverage as _review_coverage,
    review_parks as _review_parks,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_AWAITING_HUMAN = "awaiting_human"

# What the park asks of a human, worded as the notices of the squash's own
# refusals are.
_UNAPPROVED_RESUMPTION = (
    "squash-on-approval was not resumed: this issue records a squash an "
    "earlier tick began, and the approval it was begun under does not stand "
    "behind publishing it -- its review subject or evidence claim is missing, "
    "`null`, or unreadable, the subject names another commit than the head "
    "the record names, the evidence it was proved over no longer stands, or "
    "the record of the squash itself will not read -- so nothing was pushed "
    "and the PR was not relabeled. Nothing was discarded: the commits that "
    "squash was begun over are reachable from the head the record names. "
    "Reconcile the branch and the record by hand (or restore what the approval "
    "rests on) and the next tick answers from what it finds."
)


def holds_the_dispatch(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, label: str | None, state: PinnedState,
) -> bool:
    """Whether the dispatcher stops this tick, ahead of the publication reconciliation, for a collapse nothing backs.

    Asked on every label the reconciliation publishes onto a pull request
    from (`transitions.publishes_onto_a_pull_request`), since a relabel moves
    the issue and not the debt the squash left, and answered as the recovery
    answers it (`allowance`), measured from the comment as the dispatcher read
    it. A landing the receipt proves lets the tick on: it owes the
    reconciliation nothing, and the recovery behind it proves it again and is
    bound to what it proves then. A claimed squash over a record or a checkout
    no live work may use holds the tick with nothing parked (`_admitted`) --
    save over work that has ended, which goes on to the stage terminal as it
    does from `allowance`, and whose teardown keeps whatever the record pins
    that is not the issue's current branch.
    """
    if not _transitions.publishes_onto_a_pull_request(label):
        return False
    if _collapses.carries_pending_collapse(state) and not _admitted(spec, issue, state):
        return not _late_terminal._work_has_ended(gh, issue, state)
    held = _handoff._Held(None, comment=dict(state.state_data))
    return allowance(gh, spec, issue, state, held) is None


def allowance(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, held: _handoff._Held,
) -> str | None:
    """What a claimed squash may publish this tick: None where nothing, the tick held or parked.

    "" where nothing binds it: no collapse claimed, an approval standing
    behind the one claimed, or work that has ended, which is the stage
    terminal's. A commit where no approval stands and this issue's receipt
    proves its push already landed: the one commit the recovery may publish,
    as a no-op leased on itself (`_Gate.no_op_of`). `held` is what a park's
    write is measured from (`handoff._Held`): the recovery holds no verdict.
    """
    if not _collapses.carries_pending_collapse(state):
        return ""
    collapse = _collapses.read_pending_collapse(state)
    stands = collapse is not None and _approval_stands(gh, issue, state, collapse.head)
    if stands or _late_terminal._work_has_ended(gh, issue, state):
        return ""
    landed = _receipted_landing(gh, spec, issue, state, collapse)
    if landed:
        return landed
    if stands is None:
        log.info(
            "issue=#%d could not read what the approval behind its recorded squash "
            "rests on; holding its publication for a later tick", issue.number,
        )
        return None
    parked = state.get(_state._PARK_REASON) == _state._REASON_SQUASH_FAILED
    if not (parked and state.get(_AWAITING_HUMAN)):
        log.warning(
            "issue=#%d records a squash no approval stands behind publishing; "
            "parking rather than publishing it", issue.number,
        )
        _review_parks.parks_the_failed_squash(gh, issue, state, _UNAPPROVED_RESUMPTION, held)
    return None


def _admitted(spec: _config_models.RepoSpec, issue: Issue, state: PinnedState) -> bool:
    """Whether a claimed squash may be answered at all: its record's branch and the tree at its path the issue's own.

    The squash is published on that branch from that tree, and the park the
    answer can take speaks for both, so a record naming no branch live work
    may use, or a tree there on any other branch, is answered by nothing:
    the refusal has been said where it was met (`naming.BranchRefused`), and
    the dispatcher holds the tick with nothing posted or parked.
    """
    if _naming._admitted_branch(state, spec, issue.number) is None:
        log.warning(
            "issue=#%d records no branch live work may use; parking and publishing "
            "nothing for the squash it records", issue.number,
        )
        return False
    try:
        _worktree_creation._retained_checkout(spec, issue.number)
    except _naming.BranchRefused:
        return False
    return True


def _receipted_landing(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    collapse: _collapses.LateCollapse | None,
) -> str:
    """The commit this issue's receipt proves `collapse`'s push already landed, over the checkout at its path; or ""."""
    if collapse is None:
        return ""
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    landed = _late_squash_proof._receipted_landing(_late_records._gate(gh, spec, issue, state, worktree), collapse)
    if landed:
        log.info(
            "issue=#%d records a squash no approval stands behind whose push its own receipt proves "
            "landed as %s; finishing only that commit as the leased no-op it is, with the move past it "
            "left to a fresh review", issue.number, landed,
        )
    return landed


def _approval_stands(gh: GitHubClient, issue: Issue, state: PinnedState, planned: str) -> bool | None:
    """Whether the recorded approval, of `planned`, still stands on its evidence, report, and requirements.

    None where any of them could not be read.
    """
    subject = state.get(_review_subjects.APPROVED_SUBJECT)
    if _review_subjects.ReviewSubject.identity_recorded_in(subject) is None:
        return False
    if _review_subjects.ReviewSubject.commit_recorded_in(subject) != planned:
        return False
    stands = _approved_evidence.stands(gh, state)
    if stands:
        stands = _review_coverage._approval_stands(gh, state)
    if stands:
        stands = _review_coverage._requirements_stand(gh, issue, state)
    return stands
