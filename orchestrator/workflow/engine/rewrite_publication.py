# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ordinary publication of a clean automatic PR base rewrite, from its candidate to its finish.

A rebase that returned cleanly has left a candidate in the checkout, and this
is the workflow's road from that candidate to the issue's next stage. The git
owner reads it (`git/base_sync/rewrite_facts.py`) -- the head the replay
produced and the anchor it replaced, the tree, the checkout's status, the base
it sits over, and where the remote has the branch -- and every decision about
it is made here, in the order the auto rebase has always kept:

- A head nobody can name parks for a human with the checkout reset onto the
  anchor, and a rebase that moved nothing drops the attempt and leaves the
  label as it is. Neither leaves a replay standing, so both come before the
  replay is recorded.
- The replay is recorded before the first step that can leave it standing,
  and a checkout git names uncommitted paths in is reset, cleaned, and parked
  rather than published.
- The size gate and the transfer permit rule on the candidate before anything
  is pushed (`stages/implementing/late_push.py`): they hold it, hand it to an
  adjudication, or -- where the permit refuses -- measure it cumulatively like
  any other candidate. The push they license is the git owner's publication of
  exactly that candidate under its original lease
  (`git/base_sync/rewrite_transport.py`), which reads the checkout and the
  remote once more first; the gate asks whether the publication ended between
  that reading and the push. A remote that reading finds already on the
  candidate is proved there by a push leased to the candidate itself rather
  than taken on the reading's word. The receipt, the debt it settles, the
  exemption it rotates, and the proof of the checkout behind it stay the
  gate's own, as for every other publication onto an open pull request.
- A publication that sent nothing or did not land -- a moved checkout, base,
  or remote, a rejected lease -- resets the checkout onto the anchor and parks
  for a human. One that landed is handed to the one finish every landing gets
  (`rewrite_finish`), which owns the report debt, the notice and the event, the
  route, and the attempt's retirement.

Run under the issue writer claim the base refresh (`base_refresh`) takes
before the issue is read and holds through the route; the finish asks for none
of its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestrator.git.base_sync import (
    attempts as _attempts,
    guards as _guards,
    rewrite_facts as _rewrite_facts,
    rewrite_transport as _rewrite_transport,
    transfer_evidence as _transfer_evidence,
)
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.base_sync.rewrite_handoffs import (
    _LandedRewrite,
    _RewriteAttempt,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import rewrite_finish as _finish
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_publication as _late_publication,
    late_push as _late_push,
    late_records as _late_records,
)

log = logging.getLogger("orchestrator.workflow")


def publishes(context: _AutoRebaseContext, anchor: str) -> None:
    """Publish the candidate a clean rebase of `anchor` left in the checkout, and finish what landed.

    A gate that held the candidate -- parked it, or handed it to an
    adjudication -- owns the issue from there, so nothing is announced or
    routed; its park's flags are written as the gate left them.
    """
    candidate = _prepared(context, anchor)
    if not _gateable(context, candidate):
        return
    push = CandidatePush(candidate)
    published = _late_push._publishes(
        _late_records._gate(context.gh, context.spec, context.issue, context.state, context.worktree),
        candidate.branch,
        _entered(context, candidate),
        transport=push,
    )
    if published.held:
        context.gh.write_pinned_state(context.issue, context.state)
        return
    landing = push.landing
    if landing is None or not published.landed:
        _guards._park_failed_auto_rebase_push(context, anchor, candidate.branch)
        return
    _finish.finalizes(LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=landing,
        label=context.label,
        lag=context.behind,
    ))


@dataclass
class CandidatePush:
    """The push a gated publication of one candidate makes, and what it came to.

    The git owner's publication of exactly `candidate`, leased to the anchor
    it replaced, in the two steps the gate asks its ending barrier between:
    the checkout and the remote read again as the push will find them, then
    the push. The gate was entered on that candidate and refuses a checkout it
    cannot prove standing on it, so every answer it lets through names this
    commit -- the one its receipt is settled for. The retry of a replay an
    interrupted tick never published (`rewrite_retry`) pushes through the same
    transport, so the two roads cannot come to publish a candidate differently.

    A remote that reading finds already on the candidate is sent nothing, and
    it is not taken on that reading's word either: a foreign push can overtake
    it before the settlement, so it is proved at the remote first, by a push
    leased to the candidate itself that git answers only while the branch is
    still there. `landing` is what the publication came to, None until it is
    read for, and it is the record the finish is handed.
    """

    candidate: _RewriteCandidate
    landing: _LandedRewrite | None = None

    def reads(
        self,
        gate: _late_gate_models._Gate,
        _branch: str,
        _published: _late_publication._PublishedCandidate,
    ) -> bool:
        """Read the checkout and the remote again; whether the candidate may be pushed or proved."""
        self.landing = _rewrite_transport._refused_before_the_push(
            gate.spec, gate.worktree, self.candidate,
        )
        return self.landing is None or self.landing.refusal is _RewriteRefusal.PUBLISHED

    def pushes(
        self,
        gate: _late_gate_models._Gate,
        _branch: str,
        _published: _late_publication._PublishedCandidate,
    ) -> bool:
        """Publish the candidate, or prove the remote still stands on it; whether it does."""
        sends = (
            _rewrite_transport._pushes_the_candidate if self.landing is None
            else _rewrite_transport._proves_the_landing
        )
        self.landing = sends(gate.spec, gate.worktree, self.candidate)
        return self.landing.landed


def _prepared(context: _AutoRebaseContext, anchor: str) -> _RewriteCandidate:
    """Read the candidate the rebase of `anchor` left, for the attempt pinned before git ran.

    The branch is resolved the way every push and recovery of this issue
    resolves it, so the candidate names the branch the gate freezes its entry
    on and the debt behind the landing names too.
    """
    attempt = _RewriteAttempt(anchor=anchor, pr_number=context.pr_number, stage=context.label)
    branch = _naming._resolve_branch_name(context.state, context.spec, context.issue.number)
    return _rewrite_facts._prepares_the_candidate(context.spec, context.worktree, attempt, branch)


def _gateable(context: _AutoRebaseContext, candidate: _RewriteCandidate) -> bool:
    """Whether `candidate` goes on to the gate; where not, the attempt is ended or parked here.

    The replay is recorded between the two answers that end the whole attempt
    and the first that can leave a rewritten branch behind. A checkout git
    named uncommitted paths in is the dirty park whatever else the candidate
    says, since those paths would ride the push; every other refusal is the
    gate's to rule on first and the publication's to refuse after it.
    """
    anchor = candidate.original_head
    refusal = candidate.refusal
    if refusal is _RewriteRefusal.UNREADABLE_HEAD:
        _guards._park_unreadable_post_rebase_head(context, anchor)
        return False
    if refusal is _RewriteRefusal.UNMOVED:
        _guards._finish_noop_auto_rebase(context)
        return False
    _attempts._records_the_replay(context, candidate.rewritten_head)
    dirty = candidate.checkout.status.paths
    if dirty:
        _guards._park_dirty_auto_rebase(context, anchor, list(dirty))
        return False
    return True


def _entered(
    context: _AutoRebaseContext, candidate: _RewriteCandidate,
) -> _late_gate_models._Entered:
    """The terms the gate is entered on: the anchor, the candidate, and what the rebase replaced.

    The anchor is the head the pull request stood on and the lease, and the
    candidate is the commit the gate proves the checkout to -- named, so a
    checkout that moved between the reading and the gate's is refused before
    anything reaches the remote. No developer ran on this tick, which is what
    `reconciling` says. The rewrite is the evidence a transfer permit is
    granted on, assembled by the git owner that reads it; a permit that refuses
    leaves the candidate to the cumulative measurement.
    """
    anchor = candidate.original_head
    rewritten = candidate.rewritten_head
    return _late_gate_models._Entered(
        head=anchor,
        reconciling=True,
        candidate=rewritten,
        rewrite=_transfer_evidence._rewritten_by_the_rebase(context, anchor, rewritten),
    )
