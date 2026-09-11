# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a guarded verdict earns, once the owner has been read again.

The step between `late_verdict`, which decides what a reply MEANS, and the
transactions that act on it. Nothing reaches those transactions except through
here, and nothing reaches here without a fresh owner read behind it: the
coordinator takes that read on every completed run and only calls this owner
when it came back open, so every branch below may assume the issue is still
there.

The announcement a question owes the issue is made here rather than where the
question was recorded, and that is the whole reason it moved: the record has
to go out before anything is said, and the owner read has to go out between
them, so a question is not posted to a thread somebody closed while the agent
was still answering it. It is the only external effect a question earns --
no publication, no snapshot, no supersession, no activation.

A `split` is handed on rather than acted on. Creating children, taking the
snapshot they are cut from, and superseding the pull request its work is on are
one transaction and belong together; what this owner owes it is the guarantee
it cannot check for itself -- that the outcome it is given was re-checked
against an owner read taken after the agent finished.

A `single` earns a PARK, and that park is `late_unsplit`'s beside this. It is
the adjudicator answering that this change stays one change, which is the one
answer this mode may not act on: the ceiling exists so unreviewed bulk does
not reach a pull request, and an agent proposing to publish past it is the
thing being guarded against rather than the grounds for waiving the guard. So
the issue stops, and everything a human would decide against is left exactly
where the adjudication put it.

Unless a human has already decided. The one thing that turns that park into a
publication is an operator's own authorization of this exact candidate, proved
and recorded by `late_authorize` before this owner is reached -- so the
question asked here is of the RECORD rather than of a reply, and a tick that
died between the two finishes the settlement from what the write left. What
follows is that settlement.

This owner keeps the ORDER of it while the steps themselves are owned beside
it: `late_reconcile` takes the hold off and settles which pull request the
issue records, `late_verdict_push` makes the push a candidate measured past
publication earns, and `late_handback` hands the label on and retires the
cycle. Nothing in this mode makes the decision the road starts from -- a
verdict is not one -- which is why the road is entered from a human's command
and from nothing else.

The settlement writes an EXEMPTION: a durable record that this exact commit
has been adjudicated, or the gate would measure the same candidate past the
same ceiling and adjudicate it again forever. The exemption names the measured
commit and only it -- work committed after the verdict is work nobody
adjudicated, and the gate measures it as the fresh candidate it is.

Beside it goes the IDENTITY of what that commit contributes: the frozen pair
the adjudication was taken between and the canonical digest of the
contribution between them, derived from the pinned pair the decomposer
inspected rather than from a checkout that has been writable throughout. It is
written here because this is the last owner holding that pair -- the
retirement a few steps down takes it off the record -- and a reading that
could not be taken leaves the exact exemption standing on its own.

A candidate nothing had published earns only that. It is already committed in
the developer's own worktree, and the ordinary `implementing` publication the
issue is handed back to is what pushes it, opens or reuses its pull request,
and hands it to review. A candidate measured against a pull request the remote
ALREADY carries earns the push as well, and the stage it is handed back to is
the one the record names rather than `implementing`.

Never a snapshot. A snapshot exists so children can be cut from a candidate
that is about to be superseded, and an accepted candidate is superseded by
nothing -- it publishes as itself, from the branch it is already on.

The order is chosen so every window a crash can land in is one the next tick
repairs. The hold is released first, while nothing else has moved. The
exemption is written next -- with the identity of what it contributes and the
commit a push is still owed for beside it -- and the generation is still live
behind them, so the issue is still an adjudication in flight. Then the push,
then the label, and only after that is the generation cleared: a `decomposing`
issue with no generation on it is one the INITIAL decomposer would pick up and
re-decompose, and an issue back on its own stage with a live generation is one
the relabel guard puts back and this tick re-settles.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split import exemption as _exemption
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_authorize as _late_authorize,
    late_handback as _late_handback,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_reconcile as _late_reconcile,
    late_unsplit as _late_unsplit,
    late_verdict as _late_verdict,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _GuardedSplit,
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)
from orchestrator.workflow.stages.implementing import late_parks as _gate_parks

log = logging.getLogger("orchestrator.workflow")


def _settle_adjudication(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Act on what one guarded run left, if it left a verdict at all.

    A completion that decided nothing -- a timeout, an unusable reply, an
    outcome too large to record -- has already parked itself and reaches here
    only so the owner read in front of it was taken. There is nothing to
    settle, and it is handed straight back.

    The result of one that DID decide is already durable by the time this
    runs; that is `late_verdict`'s contract, and it is what makes the
    fail-closed read in front of this affordable: a tick that stops there has
    lost a GitHub read and not an agent run.

    A `single` is the one verdict whose answer depends on something other than
    the verdict. Its park is what an adjudicator's answer alone earns, and the
    settlement below is what an operator's authorization of this exact
    candidate earns -- asked of the durable record rather than of the reply
    that wrote it, so a tick that died between the two finishes rather than
    asking a human who has already decided.
    """
    adjudication = finished.adjudication
    if finished.disposition != _LateDisposition.DECIDED or adjudication is None:
        return finished
    if adjudication.verdict == LateVerdict.QUESTION:
        _late_verdict._announce(context, adjudication)
        return finished
    if adjudication.verdict == LateVerdict.SPLIT:
        return _handed_split(context, finished)
    if _late_authorize._publishes_unsplit(context):
        return _reconcile_single(context, finished)
    return _late_unsplit._parked_single(context, finished)


def _handed_split(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Report a split the owner read cleared, for the transaction to take.

    Nothing is created, snapshotted, or superseded here. What travels is the
    generation as the guard left it and the manifest the verdict decided on,
    so the transaction acts on the exact answer that was guarded rather than
    re-reading a pinned comment that has moved on since.
    """
    log.info(
        "issue=#%d late generation %d split into %d children is cleared to "
        "run: its owner was open when the adjudication finished",
        context.issue.number,
        context.generation.generation,
        len(finished.adjudication.children),
    )
    return replace(
        finished,
        generation=context.generation,
        guarded_split=_GuardedSplit(
            generation=context.generation,
            children=finished.adjudication.children,
        ),
    )


def _reconcile_single(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Exempt exactly the authorized commit and hand the candidate back.

    Two reconciliations first, and the second is the one a search by branch and
    open state cannot make: the hold comes off the pull request it marked, and
    the pull request this issue RECORDS is settled against the measured commit,
    so what the handoff names is a change the accepted candidate is actually
    in. Everything durable goes out in one write ahead of the label that hands
    it on, since the label is what makes another stage read it.

    Never a snapshot. A snapshot is what children are cut from when the
    candidate they came out of is about to be superseded, and an accepted
    candidate supersedes nothing: it publishes as itself, from the branch it
    is already committed on, so preserving a copy of it would create an
    obligation with nothing on the other end.

    The owner is asked between every one of the steps that follow, and these
    are the barriers in this mode that protect the RECORD rather than an
    effect: the last write drops the cycle entirely, and the sweep that should
    end a cancelled one reads that cycle to decide anything is owed. So a close
    latched during the hold release, the pull-request lookup, the exemption
    write, or the handoff label stops here -- not one step later, where the
    generation the durable receipt would be adopted against no longer exists.

    Latch-only, like the create and the spawn: the claim a full guard writes
    would name `owner_check` over the boundary this tick reached.
    """
    reconciled = (
        _late_reconcile._released_hold(context)
        and _late_reconcile._reconciled_pr(context)
    )
    if not reconciled:
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    ended = _handed_back(context)
    if ended is not None:
        return _late_outcome._finished(context, ended)
    return replace(
        finished,
        disposition=_LateDisposition.SETTLED,
        generation=context.generation,
    )


def _handed_back(context: _LateContext) -> _LateDisposition | None:
    """Record the exemption, hand the label on, and retire the cycle.

    Three requests in the one order a crash in them is safe in, with the
    latch asked between each: the exemption is what stops the gate measuring
    the same commit again, the label is what makes another stage read it, and
    the retirement is what says this issue has no late question left. None is
    reached over a close somebody observed.

    The exemption is joined by the commit the handoff is owed a publication
    for, and the pair is what makes the retirement behind them survivable. An
    exemption says a commit needs no measuring; it does not say the issue is
    still waiting for it to be pushed, and past the retirement the generation
    that did say so is gone. A tick that died in that window would leave an
    `implementing` issue whose branch carries an adjudicated commit and whose
    record names none, so a replacement host -- rebuilding the checkout from
    the base or the plan pull request -- would publish that head or spawn a
    second developer over an implementation a human has already ruled on.
    Recorded, the implementing gate proves the commit before anything runs and
    parks for the checkout instead.

    The identity of what that commit CONTRIBUTES rides the same write, and has
    to: the retirement behind these steps takes the frozen pair off the
    record, and past it nothing on the issue could say which base the accepted
    work was measured over. Where the reading could not be taken there is
    simply none, and the exact commit is exempt on its own as it is with one.
    """
    stopped = _late_owner._latch_stops(context)
    if stopped is not None:
        return stopped
    _exemption.record_exemption(
        context.state, context.generation.candidate_sha,
    )
    _recorded_identity(context)
    _recorded_debt(context)
    _late_park_state._persist(context)
    stopped = _late_owner._latch_stops(context)
    if stopped is not None:
        return stopped
    return _late_handback._continued(context)


def _recorded_identity(context: _LateContext) -> None:
    """Record WHAT was accepted, beside the commit it was accepted on.

    Taken over the frozen pair this adjudication was run against -- the base
    the generation was measured from and the candidate the verdict named --
    and never over the checkout's head or a base read now. The worktree is
    writable for the whole of an adjudication, so what it stands on says
    nothing about what a human ruled on; the pinned pair is what the
    decomposer was pointed at, and it is the only thing the digest may be
    taken between.

    A reading that could not be taken records nothing at all, which is the
    same answer a comment older than this group gives. The exemption is
    already durable beside it and covers the exact commit either way, so what
    an absent identity costs a later tick is the transfer and never the
    decision a human has already made -- and where an earlier candidate left
    an identity of its own, the exemption write immediately ahead of this
    dropped it with the commit it described.

    A pair this record cannot name, and a checkout that is not there, are the
    same answer for the same reason. Both are proved long before a verdict is
    settled, so what the guard is really standing in front of is a teardown
    racing this tick -- and running git in a directory that has gone would
    raise here, between the exemption write and the debt beside it.
    """
    generation = context.generation
    worktree = _worktree_paths._worktree_path(
        context.spec, context.issue.number,
    )
    frozen = generation.base_sha and generation.candidate_sha
    if not (frozen and worktree.exists()):
        return
    contribution = _fingerprint._fingerprint_contribution(
        worktree, generation.base_sha, generation.candidate_sha,
    )
    if not contribution.is_fingerprinted:
        log.warning(
            "issue=#%d settles the accepted candidate %s with no semantic "
            "identity (%s); only the exact commit is exempt",
            context.issue.number,
            generation.candidate_sha,
            contribution.failure,
        )
        return
    _exemption.record_semantic_identity(
        context.state,
        base_sha=contribution.base_sha,
        candidate_sha=contribution.candidate_sha,
        fingerprint=contribution.digest,
    )


def _recorded_debt(context: _LateContext) -> None:
    """Record the push this handoff owes, or drop one already paid.

    The approval says a commit is owed a publication and no other may be
    pushed in its place, which is exactly what a retry finishing an
    interrupted settlement does NOT owe: the pull request is already standing
    on that commit. Recording it there would leave a debt nothing will ever
    pay -- the push is skipped -- and a debt on the record freezes this
    branch out of the pre-tick base refresh for the rest of the issue's life.

    What the debt RESTS on is the adjudication, and it is recorded rather than
    left to be inferred. This write and the exemption beside it go down in one
    breath, so the approval is that adjudication wearing another field and is
    worth exactly what the exemption is worth -- while a reader that guessed
    from the records standing around it would answer the same for a debt this
    gate's own count earned on an issue that happens to carry an exemption.
    """
    if context.already_published:
        _gate_parks._forget_approval(context.state)
        return
    _gate_parks._approve(
        context.state,
        context.generation.candidate_sha,
        _settled_lease(context),
        _gate_parks.LateApprovalBasis.ADJUDICATION,
    )


def _settled_lease(context: _LateContext) -> str:
    """The head the publication this verdict was taken over is pinned to.

    The retirement takes the generation -- and the head it froze -- off the
    record, and the push the handoff licenses runs in another stage entirely.
    Without this the publication would read the remote for itself, which is
    right for a candidate nothing has published and wrong for one adjudicated
    against a pull request that already exists: between the proof a moment ago
    and the push, that pull request can move, and an unpinned force-push adopts
    whoever landed as the lease.

    Empty for a pre-publication verdict, whose push has no pull request to be
    pinned to and correctly takes its own reading.
    """
    if not context.generation.has_publication_context:
        return ""
    return context.generation.published_sha
