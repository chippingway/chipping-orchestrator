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
pinned comment nobody could read again HOLDS.

That proof makes requests of its own -- the pull request, the branch fetch,
the settled report re-read -- and so does the finish behind it: the evidence
write, a failure notice's conversation read and post. Anything read before one
of them can have moved while it was answered. So every route the evidence
step takes ends in one last word (`last_word`), asked once nothing else is
left to request, which reads everything that moves again in one fixed order:
the network first -- the remote branch the head landed on, the base, and the
issue's requirements over the issue fetched once more -- and then the readings
no request answers, behind every one that did: the checkout's own head and the
configuration. Its verdicts come in the same order. A remote branch or a
checkout off the landed head (`LEFT_THE_LANDING`) HOLDS: the landing the route
would finish is no longer the one in front of it, and the next tick's recovery
classifies the branch afresh. Requirements or a configuration that moved DEFER,
refusing the transaction the route would carry. The remote branch and the
checkout are read only for a route that carries or follows a recorded decision
or ran the configured commands; one that ran nothing and recorded nothing has
nothing the landing could have moved under.

The base is read through `standing_refusal`, also before a run starts so no
command runs on a head already off its base. The finish counts the landed head
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

_RECONFIGURED = _evidence_models.ReportEvidence(
    _DEFER, "the verification configuration moved while the evidence was proved again",
)

_UNREAD_REMOTE = _evidence_models.ReportEvidence(
    _HOLD, "the remote branch the rebased head landed on could not be read again",
)

# A checkout or remote branch off the head that landed: the landing the route
# would finish is no longer the one in front of it.
LEFT_THE_LANDING = _evidence_models.ReportEvidence(
    _HOLD, "the checkout or the remote branch is no longer on the rebased head",
)

# What the last word's requests heard: the remote branch's head, the base's
# refusal, and the requirements' refusal.
_Heard = tuple[
    str | None, _evidence_models.ReportEvidence | None, _evidence_models.ReportEvidence | None,
]

# A remote base read somewhere else than the tip the head was counted against:
# movement established, as a landing off its head is, rather than a reading
# nobody could take.
BASE_MOVED = _evidence_models.ReportEvidence(
    _HOLD, "the base moved after the rebased head was counted against it",
)

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
    """The whole proof of `binding` over the issue and pinned comment read afresh, or the HOLD nobody could read."""
    issue = _fetches(finish)
    if issue is None:
        return _UNREAD
    try:
        state = finish.gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment again to prove the evidence of %s",
            finish.issue.number, finish.head,
        )
        return _UNREAD
    if not state.parsed:
        return _UNREAD
    return _proof.binding_verdict(_proof.ProofReading(finish.gh, finish.spec, issue, state), binding)


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
    finish: LandedFinish, binding: _records.EvidenceBinding | None = None, *, landing: bool = True,
) -> _evidence_models.ReportEvidence | None:
    """Why `finish`'s landed head may not route with what its evidence step left, read behind every request; or None.

    `binding` is the transaction the route would carry, None where it carries
    none, and `landing` whether the remote branch and the checkout are read
    again too -- for a route that carries or follows a recorded decision. The
    network is read first and the local readings last (`_answers_locally`),
    so nothing read before a request is taken on trust behind it.
    """
    return _answers_locally(finish, binding, _hears(finish, binding, landing), landing)


def _hears(finish: LandedFinish, binding: _records.EvidenceBinding | None, landing: bool) -> _Heard:
    """Every request the last word makes, in its order: the remote branch, the base, and the requirements."""
    remote = None
    if landing:
        worktree = _worktree_paths._worktree_path(finish.spec, finish.issue.number)
        remote = branch_transport._remote_branch_read(finish.spec, worktree, finish.landed.candidate.branch).sha
    base = standing_refusal(finish)
    if binding is None:
        return remote, base, None
    issue = _fetches(finish)
    if issue is None:
        return remote, base, _UNREAD
    return remote, base, requirements_verdict(issue, finish.state, binding.target.publication.requirements_revision)


def _answers_locally(
    finish: LandedFinish, binding: _records.EvidenceBinding | None, heard: _Heard, landing: bool,
) -> _evidence_models.ReportEvidence | None:
    """The readings no request answers, behind every one that did -- the checkout's own head, the configuration.

    Then the verdicts in their order: the landing, the base, the
    requirements, the configuration.
    """
    remote, base, asked = heard
    landed = _landing_refusal(finish, remote) if landing else None
    refused = landed or base or asked
    if refused is None and binding is not None and binding.context_revision != _proof.configured_context_revision():
        return _RECONFIGURED
    return refused


def _landing_refusal(finish: LandedFinish, remote: str | None) -> _evidence_models.ReportEvidence | None:
    """Why the remote branch, as heard, and the checkout, read now, are not both on the landed head; or None."""
    if remote is None:
        return _UNREAD_REMOTE
    checkout = _rewrite_facts._reads_the_checkout(
        finish.spec, _worktree_paths._worktree_path(finish.spec, finish.issue.number),
    ).head
    return None if {remote, checkout} == {finish.head} else LEFT_THE_LANDING


def _fetches(finish: LandedFinish) -> Issue | None:
    """The issue as GitHub carries it now, or None where it would not read."""
    try:
        return finish.gh.get_issue(finish.issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be read again to prove the evidence of %s", finish.issue.number, finish.head,
        )
        return None
