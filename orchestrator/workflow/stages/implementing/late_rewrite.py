# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Enter a squash on its publication and publish the commit the rewrite makes.

The switch governs measurement entry, while every push keeps its terminal
barrier. Resumes name their recorded candidate, and a proved rollback drops
its abandoned approval, transfer permission, and collapse claim together.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    collapses as _collapses,
    rewrite_values as _rewrite_values,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_collapse_state as _late_collapse_state,
    late_freeze as _freeze,
    late_overflow as _overflow,
    late_push as _push,
    late_squash_proof as _late_squash_proof,
    late_transfer as _transfer,
)
from orchestrator.workflow.stages.implementing.late_gate_models import _Entered, _Gate, _PublicationEntry

log = logging.getLogger("orchestrator.workflow")


def _switched_off(gate: _Gate) -> bool:
    """Whether the switch keeps this squash out of the gate entirely.

    A squash is NEW work by the switch's own definition: the commit it
    publishes is one it makes itself, out of commits a reviewer approved. So
    an install with `DECOMPOSE=off` freezes no entry: no pull request is read
    for the measurement and nothing parks over one. The barrier immediately
    before the push reads the recorded pull request on every install, and this
    question does not reach it -- what a setting about measurement may not buy
    is a force-push onto work somebody merged.

    It is the gate's own question, asked HERE rather than left to the reading
    inside the call, because this seam reaches that reading twice and the
    first of the two is the pull-request read the switch is supposed to save.
    The subject it is asked over answers `answering` False, which is what a
    squash is: no developer ran on the tick, and nothing on the record asked
    for this commit to be read.

    A record already in the gate, and a commit an approval still owes a push,
    are work the switch has nothing left to say about either way.
    """
    return _freeze._outside_the_gate(
        gate, _late_state.read_late_generation(gate.state),
    )


def _entered_rewrite(
    gate: _Gate, expected: str, candidate: str = "",
) -> _PublicationEntry:
    """The publication a squash may rewrite, or the reason it may not.

    Asked before the reset that destroys the branch locally, so a pull request
    nothing can be published onto costs the caller a refusal rather than a
    rewrite it then has to roll back.

    `expected` is the pre-squash head this stage read and will lease its
    force-push against, checked against the head the publication is standing
    on exactly as every other caller's is: the two are one fact, and a squash
    taken over a branch somebody pushed to would rewrite their work away.

    `candidate` is the commit the caller means to publish, and only a caller
    that already HAS one names it: a squash about to be made names nothing,
    because the object does not exist yet. A resumed one does, and naming it
    is what lets the entry recognize a pull request standing on the rewritten
    commit as this issue's own push having landed -- the receipt dates that
    tip to this attempt -- rather than as a remote somebody else moved. Read
    without it, the tick that pushed and died before its record would be
    refused by the very reading that exists to finish it.

    Where the switch keeps this squash out of the gate, nothing is read and
    nothing can refuse: what comes back names only the head the caller
    established, which is what the force-push behind it is pinned to. An
    install with `DECOMPOSE=off` therefore squashes and pushes under the lease
    this stage read for itself, and under no other claim about the remote --
    which is the second answer that makes skipping the reading safe here, and
    the one the caller beside this has not got.
    """
    if _switched_off(gate):
        return _PublicationEntry(published_sha=expected)
    return _proved_publication(gate, expected, candidate)


def _proved_publication(
    gate: _Gate, expected: str, candidate: str = "",
) -> _PublicationEntry:
    """The same reading, taken whatever the switch says.

    The entry above may be skipped because a push follows it: a remote
    somebody else moved rejects the lease, so the switch costs such an install
    a reading it has a second answer to. The recovery's hand-back has no push
    at all -- it drops the record of a rewrite that never ran and reports the
    branch exactly as it found it -- so a reading skipped there is the last
    thing between a pull request that moved and `documenting` having the
    issue.

    `DECOMPOSE=off` buys an install a gate that measures nothing and
    adjudicates nothing. It was never a licence to hand the next stage a
    branch whose publication has left, so this road asks whatever it is set
    to.
    """
    entry = _overflow._frozen_entry(
        gate,
        _Entered(
            head=expected, candidate=candidate, reconciling=True,
        ),
    )
    if not entry.is_frozen:
        log.error(
            "issue=#%d cannot squash onto the pull request it already has "
            "(%s); leaving the approved commits on the branch",
            gate.issue.number, entry.refusal,
        )
    return entry


def _publishes_rewrite(
    gate: _Gate,
    branch: str,
    entry: _PublicationEntry,
    squashed: str,
    collapsed: _late_collapse_state._Collapsed,
) -> _push._PushedCandidate:
    """Measure the squashed commit, then publish what it earned.

    The one call every gated push goes through, handed the head this stage
    established: the entry re-freezes over it, the checkout is proved to be
    standing on the commit the squash just made, the diff from the frozen base
    to it is counted, and only a candidate at or under the ceiling is pushed
    -- named against that commit and pinned to the frozen head.

    `reconciling` is what this call is: no developer ran on this tick, so a
    checkout that is not on the squashed commit is something that moved rather
    than a run's fresh output, and it is refused rather than measured as new
    work. It says nothing about the switch, which is asked against the
    narrower `answering` -- and a squash never is one: the commit it publishes
    is one it makes itself, out of commits a reviewer approved.

    `entry` is what the caller froze before it rewrote anything. It is not
    handed to the gate -- the entry inside the call is the one the record
    carries -- but the head it names is, so both readings are pinned to the
    same fact and the second cannot silently freeze a publication the first
    would have refused.

    `squashed` is asked twice, and the second is the binding one. The gate
    proves HEAD for itself and a first generation has no record to prove it
    against, so handed a checkout something moved between the squash and the
    freeze it would measure and publish the replacement as if it were the
    squash. Naming the commit closes that: the gate refuses a checkout it was
    not handed, before anything is persisted or pushed. The reading before the
    call is the cheap half -- it refuses without spending the pull-request
    read the entry costs.

    `collapsed` is what the plan read before the reset: the head the squash
    replaced, and the merge base it was read over. Together they turn the pair
    of commits into the pair of CONTRIBUTIONS the gate needs to recognize a
    change it has already adjudicated, and they are the caller's because only
    that plan still holds them -- the head is off the branch by the time this
    runs and the base is not derivable from the object that replaced it.
    """
    if not _late_squash_proof._standing_on_the_squash(gate, squashed):
        return _push._PushedCandidate(held=True)
    return _push._publishes(
        gate, branch,
        _Entered(
            head=entry.published_sha,
            reconciling=True,
            # The commit the squash made, so the gate measures and publishes
            # THAT rather than whatever the checkout became between the two
            # reads. Bound here, a move in that window is refused before
            # anything is persisted or pushed rather than noticed after.
            candidate=squashed,
            rewrite=_rewritten(entry, squashed, collapsed),
        ),
    )


def _rewritten(
    entry: _PublicationEntry,
    squashed: str,
    collapsed: _late_collapse_state._Collapsed,
) -> _rewrite_values.LateRewrite:
    """What this squash replaced, and the publication it replaced it on.

    Everything a transfer could be granted on and nothing this owner decides.
    The commit it REPLACED is the plan's own pre-squash head, and the head the
    force-push is LEASED against is the tip the entry froze -- two facts, not
    one spelling of the same one. The entry checks them against each other and
    admits one carve-out: a tip a durable record says this issue's own push
    put there is accepted even where the caller began somewhere else, which is
    the window a tick that pushed and died before its record leaves. Read off
    the entry alone, the commit this squash collapsed would then be recorded
    as some other one -- and a transfer is granted on the exemption naming
    exactly what was collapsed.

    Both contributions are read over the same merge base, because a squash
    moves neither end of the branch's fork point: it rewrites what sits on top
    of it.

    Handed over whether or not this issue has an exemption to carry, since
    only the gate holds the record that would say -- and empty of everything
    where the switch kept the squash out of the gate, whose entry names a head
    and no publication at all.
    """
    return _rewrite_values.LateRewrite(
        kind=_rewrite_values.LateRewriteKind.SQUASH,
        from_sha=collapsed.head,
        from_base_sha=collapsed.base_sha,
        to_sha=squashed,
        to_base_sha=collapsed.base_sha,
        pr_number=entry.pr_number,
        source_stage=entry.stage,
        lease=entry.published_sha,
    )


def _forgets_the_rollback(gate: _Gate, restored: str) -> None:
    """Drop a debt the rollback above just threw the commit away for.

    The gate approves the squashed commit before it is pushed and records it
    as one still owed a publication. A push that is then refused rolls the
    branch back to the pre-squash head, so that commit is not on this branch
    any more and only the reflog still has it.

    Left standing, it is a debt nothing can pay and everything trips over: the
    reconciliation ahead of every handler finds an approval whose commit the
    checkout is not on and stops the tick for a publication that is never
    coming, poll after poll. An approval whose commit was abandoned is
    superseded, which has always been one of the three things that drops one
    -- so the owner doing the abandoning is the one that drops it.

    The permission a refused rewrite held goes in the same write, and for the
    same reason: it was granted for a commit that is not on this branch any
    more either. The exemption itself needs no repair -- the grant never moved
    it -- so what is left over is a claim about a push that will never
    happen.

    And so does the record of the collapse itself, which is the claim the
    reset has just made false: the branch is standing on the head that record
    says was rewritten, so nothing is part-way through any more. Left there it
    would describe a squash to a later tick that reads the very branch it was
    about and finds the commits still on it.

    Made durable HERE rather than left for the caller's own write, because
    what it answers for has already happened: the branch is back on the
    pre-squash head, and a process that died before that write would come back
    to exactly the debt this exists to prevent.
    """
    owed = _late_approval_reading._approved_commit(gate.state) != restored
    if owed:
        _late_approval_state._forget_approval(gate.state)
    carried_back = _transfer._abandoned_authorization(gate, restored)
    collapsed = _late_collapse_state._claims_a_collapse(gate.state)
    if collapsed:
        _late_collapse_state._forgets_the_collapse(gate.state)
    if not (owed or carried_back or collapsed):
        return
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _resumed_entry(
    gate: _Gate,
    recorded: _collapses.LateCollapse,
    squashed: str,
) -> _PublicationEntry:
    """The publication an interrupted squash's own push is still owed.

    The same entry a fresh squash freezes, taken over the head the RECORD
    names rather than one this tick read: the commits that head reached are
    off the branch, so nothing in the checkout could say what the force-push
    behind this rewrite is leased against.

    The commit is named, which a fresh squash cannot do -- its object does not
    exist yet -- and naming it is what makes the far side of the window
    recoverable: a pull request already standing on the rewritten commit is
    this issue's own push having landed, dated to this attempt by the receipt
    beside it, and the entry admits it rather than refusing it as a remote
    somebody moved.

    Refuses on exactly the terms every other entry does, and the caller is
    handed the reason: a pull request a human closed while the process was
    down, a remote off both heads this collapse accounts for, a tree that
    stopped being provably clean.
    """
    log.info(
        "issue=#%d resumes the squash it recorded over %s: %d commits are "
        "already collapsed into %s and the publication is owed",
        gate.issue.number, recorded.head, recorded.count, squashed,
    )
    return _entered_rewrite(
        gate, _late_squash_proof._leased_head(gate, recorded, squashed), candidate=squashed,
    )
