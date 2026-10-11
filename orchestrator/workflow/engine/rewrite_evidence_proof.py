# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's evidence proved again, and the last word on its route over everything that moves.

The evidence policy proves a binding before a run and proves it again behind
one (`rewrite_evidence`), and a recovery takes up a decision an earlier finish
captured only once it proves again (`rewrite_finish_captured`). Both read the
world afresh rather than off the tick's own reading (`proves_again`): the issue
is fetched again, since the one a finish holds carries the title and body read
when the tick began, and the pinned comment is read again, and the whole proof
(`verification_proof.binding_verdict`) is taken over them. An issue or a
pinned comment nobody could read again HOLDS. The proof reads the pull request
first and stops at a reading nobody could take, so a proof that holds is
answered beside the review and report records the comment it read carries
(`verification_proof.recorded_verdict`): a subject or settled report that
moved is movement, whatever went unanswered.

That proof makes requests of its own -- the pull request, the branch fetch,
the settled report re-read -- and so does the finish behind it: the evidence
write, a failure notice's conversation read and post. Anything read before one
of them can have moved while it was answered. So every route the evidence
step takes that carries or follows a recorded decision ends in one last word
(`last_word`), asked once nothing else is left to request -- a captured
transaction's behind whatever stopped it, a write refused or a hold for want
of room included. Only a fresh decision held before its write, or whose write
did not land, ends without it, having recorded nothing this tick knows of.
The last word reads everything that moves again in one fixed order:
the network first -- the remote branch the head landed on, the base, and,
over the issue and pinned comment fetched once more, the issue's requirements
and the review and report records the transaction is bound to -- and then the
readings no request answers, behind every one that did: the checkout's own
head and the configuration. The remote branch and the checkout are two
readings, the checkout read whatever the remote's came to, and the records are
compared on their own, whatever the proof before them could read. Every
reading is taken, and none masks another: the last word
answers with the first that establishes movement and the first that holds the
route, side by side, so a reading nobody could take never hides one that read
something move. A remote branch or a checkout read off the landed head
(`LEFT_THE_LANDING`) both holds the route -- the landing it would finish is no
longer the one in front of it, and the next tick's recovery classifies the
branch afresh -- and establishes movement; a remote branch nobody could read,
or a checkout whose head would not prove, only HOLDS, leaving a transaction to
be proved again. Requirements, review or report records, or a configuration
that moved DEFER, establishing movement under the transaction the route would
carry. The remote branch and the
checkout are read only for a route that carries or follows a recorded decision
or ran the configured commands; one that ran nothing and recorded nothing has
nothing the landing could have moved under.

The base is read through `standing_refusal`, also before a run starts or a
carry is recorded, so no command runs on a head already off its base and no
carry is made for one -- one whose recorded tip a refusal for good blanked
among them. The finish counts the landed head
against the base as its tick fetched it, and routes a head the base has
advanced past to another rebase instead of to review (`rewrite_finish`), but
evidence decided for the head rests on the base as much as on the head. The
reading is the git owner's
(`git/base_sync/rewrite_facts._standing_on_the_remote_base`), over the base tip
the attempt recorded its replay as made onto
(`git/base_sync/attempt_records._recorded_onto`):

- A remote base gone elsewhere since the head was counted (`BASE_MOVED`), or
  a reading nobody could take, HOLDS. Nothing is routed and the attempt
  stands: the next tick's fetch counts the head again, and a head the base
  advanced past is continued to the next rebase, which replaces it. A base
  read elsewhere is movement established, as a landing off its head is, so
  the last word's caller abandons a transaction the route would carry besides
  (`rewrite_finish_captured.stands_before_the_route`); an unread base proves
  no movement and leaves it to be proved again.
- A counted base that is not the recorded tip -- rewound or repointed under
  the head after the rebase -- DEFERS, and so does an attempt that recorded no
  tip at all, since nothing then proves which base the head was replayed
  onto. No later tick changes either answer, so the decision is refused for
  good: nothing is run or recorded for the head, a captured decision is
  abandoned, and the fresh reviewer owes the evidence.

Two remote readings cannot be taken at one instant, so the network part of the
last word is ordered rather than atomic, and the writes the route itself makes
behind it are not read past. What moves there is no evidence anyone settles:
the retirement behind the route is decided on every record the evidence is
bound through (`rewrite_finish_writes.FINISH`), and the dispatcher's
reconciliation proves a recorded transaction whole again before it publishes
it (`verification_transaction`).
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import attempt_records as _attempt_records, rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_proof as _proof,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.engine.verification_subject import requirements_verdict

log = logging.getLogger("orchestrator.workflow")

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_UNREAD = _evidence_models.ReportEvidence(
    _HOLD, "the issue or its pinned comment could not be read again to prove the evidence",
)

_UNREADABLE = "issue=#%d could not read %s again to prove the evidence of %s"

_RECONFIGURED = _evidence_models.ReportEvidence(
    _DEFER, "the verification configuration moved while the evidence was proved again",
)

_UNREAD_REMOTE = _evidence_models.ReportEvidence(
    _HOLD, "the remote branch the rebased head landed on could not be read again",
)

_UNREAD_CHECKOUT = _evidence_models.ReportEvidence(
    _HOLD, "the checkout's head could not be proved again",
)

# A checkout or remote branch off the head that landed: the landing the route
# would finish is no longer the one in front of it.
LEFT_THE_LANDING = _evidence_models.ReportEvidence(
    _HOLD, "the checkout or the remote branch is no longer on the rebased head",
)

# What the last word's requests heard: the remote branch's head, then the
# base's refusal and what the issue and its pinned comment, read again, refuse.
_Heard = tuple[
    str | None,
    tuple[_evidence_models.ReportEvidence | None, ...],
]

# A remote base read somewhere else than the tip the head was counted against:
# movement established, as a landing off its head is, rather than a reading
# nobody could take.
BASE_MOVED = _evidence_models.ReportEvidence(
    _HOLD, "the base moved after the rebased head was counted against it",
)

# The holds that read movement rather than a reading that did not happen.
_MOVEMENT = (LEFT_THE_LANDING, BASE_MOVED)

# What the last word comes to: the first reading of movement, and the first
# reading that holds the route.
Word = tuple[_evidence_models.ReportEvidence | None, _evidence_models.ReportEvidence | None]

_REFUSALS = MappingProxyType({
    _BaseStanding.MOVED: BASE_MOVED,
    _BaseStanding.UNREAD: _evidence_models.ReportEvidence(
        _HOLD, "the base the rebased head was counted against could not be read again",
    ),
    _BaseStanding.DROPPED: _evidence_models.ReportEvidence(
        _DEFER, "the base is no longer the tip the rebased head was replayed onto",
    ),
    _BaseStanding.UNPROVEN: _evidence_models.ReportEvidence(
        _DEFER, "the attempt recorded no base tip its replay was made onto",
    ),
})


def proves_again(finish: LandedFinish, binding: _records.EvidenceBinding) -> _evidence_models.ReportEvidence:
    """The whole proof of `binding` over the issue and pinned comment read afresh, or the HOLD nobody could read.

    A proof that holds on a reading nobody could take stopped there, so the
    records the pinned comment carries are asked beside it
    (`verification_proof.recorded_verdict`), and a refusal of theirs -- a
    review subject or settled report that moved -- is the answer instead:
    movement those records establish is never hidden behind a request that
    went unanswered.
    """
    read = _reads_again(finish)
    if read is None:
        return _UNREAD
    issue, state = read
    reading = _proof.ProofReading(finish.gh, finish.spec, issue, state)
    found = _proof.binding_verdict(reading, binding)
    if not found.holds:
        return found
    return _proof.recorded_verdict(state, binding) or found


def standing_refusal(finish: LandedFinish) -> _evidence_models.ReportEvidence | None:
    """Why `finish`'s landed head no longer stands on the base its replay was made onto, or None where it does."""
    standing = _rewrite_facts._standing_on_the_remote_base(
        finish.spec,
        _worktree_paths._worktree_path(finish.spec, finish.issue.number),
        finish.landed.candidate,
        _attempt_records._recorded_onto(finish.state),
    )
    return _REFUSALS.get(standing)


def last_word(
    finish: LandedFinish,
    binding: _records.EvidenceBinding | None = None,
    *,
    landing: bool = True,
    earlier: _evidence_models.ReportEvidence | None = None,
) -> Word:
    """What everything that moves under `finish`'s route reads as now, behind every request: `(moved, held)`.

    `binding` is the transaction the route would carry, None where it carries
    none, and `landing` whether the remote branch and the checkout are read
    again too -- for a route that carries or follows a recorded decision.
    `earlier` is a verdict the caller already read the transaction with -- a
    proof of it again -- which is sorted first, beside the rest. The network
    is read first and the local readings last (`_answers_locally`), so
    nothing read before a request is taken on trust behind it.

    Every reading is taken and none masks another. `moved` is the first that
    establishes that something the route rests on moved -- every refusal that
    defers, and the two holds that read movement, a landing off its head and
    a base read elsewhere (`_MOVEMENT`) -- and a transaction the route would
    carry can never be taken again after it. `held` is the first that holds
    the route: a reading nobody could take, or one of those two. Either is
    None where no reading says so.
    """
    answered = _answers_locally(finish, binding, _hears(finish, binding, landing), landing)
    found = [refused for refused in (earlier, *answered) if refused and not refused.proved]
    movements = (refused for refused in found if not refused.holds or refused in _MOVEMENT)
    holds = (refused for refused in found if refused.holds)
    return next(movements, None), next(holds, None)


def _hears(finish: LandedFinish, binding: _records.EvidenceBinding | None, landing: bool) -> _Heard:
    """Every request the last word makes, in its order: the remote branch, the base, and the issue and its comment.

    The issue and its pinned comment are read again for a transaction the
    route would carry, and both are asked of it: the requirements over the
    issue, and the review and report records over the comment
    (`verification_proof.recorded_verdict`), whatever any other reading came to.
    """
    remote = None
    if landing:
        remote = branch_transport._remote_branch_read(
            finish.spec,
            _worktree_paths._worktree_path(finish.spec, finish.issue.number),
            finish.landed.candidate.branch,
        ).sha
    base = standing_refusal(finish)
    if binding is None:
        return remote, (base,)
    read = _reads_again(finish)
    if read is None:
        return remote, (base, _UNREAD)
    issue, state = read
    return remote, (
        base,
        requirements_verdict(issue, state, binding.target.publication.requirements_revision),
        _proof.recorded_verdict(state, binding),
    )


def _answers_locally(
    finish: LandedFinish, binding: _records.EvidenceBinding | None, heard: _Heard, landing: bool,
) -> tuple[_evidence_models.ReportEvidence | None, ...]:
    """The readings no request answers, behind every one that did -- the checkout's own head, the configuration.

    Then every verdict in its order, None for each reading that refused
    nothing: the remote branch, the checkout, the base, the requirements and
    the records, the configuration.
    """
    remote, asked = heard
    landed = _landing_refusals(finish, remote) if landing else (None, None)
    reconfigured = binding is not None and binding.context_revision != _proof.configured_context_revision()
    return *landed, *asked, _RECONFIGURED if reconfigured else None


def _landing_refusals(
    finish: LandedFinish, remote: str | None,
) -> tuple[_evidence_models.ReportEvidence | None, _evidence_models.ReportEvidence | None]:
    """The remote branch, as heard, and the checkout, read now, each against the landed head.

    Two readings, each refused on its own: a remote branch nobody could read
    says nothing about the checkout, which is read whatever the branch's
    reading came to, so a checkout that moved is never hidden behind it. A
    reading that did not happen -- the branch unread, or a checkout head the
    proof could not name, which reads as "" -- holds without establishing
    movement, as the evidence policy holds a reading nobody took; only a head
    read somewhere else is the landing left.
    """
    checkout = _rewrite_facts._reads_the_checkout(
        finish.spec, _worktree_paths._worktree_path(finish.spec, finish.issue.number),
    ).head
    if remote is None:
        branch = _UNREAD_REMOTE
    else:
        branch = None if remote == finish.head else LEFT_THE_LANDING
    if not checkout:
        return branch, _UNREAD_CHECKOUT
    return branch, None if checkout == finish.head else LEFT_THE_LANDING


def _reads_again(finish: LandedFinish) -> tuple[Issue, PinnedState] | None:
    """The issue as GitHub carries it now and its pinned comment read over it, or None where either would not read."""
    try:
        issue = finish.gh.get_issue(finish.issue.number)
    except Exception:
        log.exception(_UNREADABLE, finish.issue.number, "the issue", finish.head)
        return None
    try:
        state = finish.gh.read_pinned_state(issue)
    except Exception:
        log.exception(_UNREADABLE, finish.issue.number, "its pinned comment", finish.head)
        return None
    return (issue, state) if state.parsed else None
