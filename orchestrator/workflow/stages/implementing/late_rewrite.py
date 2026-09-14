# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push a squash-on-approval makes over the branch it just rewrote.

The tenth seam that publishes onto a pull request the remote already carries,
and it goes through the whole gate like the other nine. What it publishes is a
NEW object: a squash collapses the approved commits into one commit that did
not exist when any earlier push was measured, so that commit is the candidate
-- proved, frozen against the base the remote names now, counted, and either
pushed or held. Measuring the head it replaces instead would gate one commit
and publish another.

The count it earns is ordinarily the count the last gated push already
answered, because the tree is the same tree. Ordinarily is not always: the
BASE moves, and a base that advanced since that push changes what this branch
adds to it. That is the reading this seam exists to take -- it is the last
push before a human is asked to merge, so a pull request that has crossed the
ceiling since anyone looked would otherwise reach the merge button
unadjudicated.

A candidate the RECORD names ends the tick without a rollback. Past the
ceiling the gate has moved the issue to `workflow:decomposing` and an
authorized settlement publishes the squash from the branch; short of a count
the
pair is one the reconciliation ahead of the next handler owes a reading, and
that reading can only be taken in the checkout it was frozen on. Either way
restoring the pre-squash head would leave a record naming a commit this branch
no longer has -- adjudicated over a commit nobody has, or refused by every
later tick as a candidate that moved. The same holds for a push that landed
and for a checkout something committed over: in each the squash is somebody's
and a reset is the destructive step.

A REFUSED one is the opposite and is told apart from all of them, because the
squash there is a local commit nobody measured, nobody published, and nothing
recorded -- an entry that could not prove itself deliberately persists none.
Left on the branch it is the ONE commit a retry finds, which takes the
nothing-to-squash road and reports success without measuring or pushing
anything -- so the approved work reaches the merge button neither counted nor
on the remote. `_rewrite_stands` is what the caller asks before it decides.

The entry is asked TWICE, and the first time is not redundant. A pull request
nothing could read, one a human closed mid-review, a dirty tree, or a head
that moved out from under the reading are all answerable while the branch is
still intact, and asking them there is what keeps a doomed publication from
costing a rewrite and a rollback to learn about. Closing a pull request does
not move its branch, so that first reading is also the only thing standing
between a `--force-with-lease` and a publication nobody can merge.

What the squash also carries into the gate is the before-state it destroyed.
The head the pull request was standing on, the merge base the plan was
collapsed onto, and the commit that came out are the whole of the evidence
`late_transfer` grants a transfer on -- so a squash of the exact commit an
adjudication accepted can be recognized as the same contribution rather than
measured past the same ceiling and adjudicated a second time. Nothing here
decides that; what this owner owes it is the pair of pairs, taken before the
reset, that no reading past the rewrite could produce. The rollback is the
other end of the same obligation: a push the remote refuses puts the branch
back onto the commit the exemption never left -- the grant records a
PERMISSION and moves nothing, and only the receipt of a landed push spends it
-- so what the reset owes is dropping the permission it will never spend.

The before-state is said out loud first, and that is what makes the rotation
recoverable at all. The rewrite destroys the only evidence of what it was
about, so the head it is collapsing, the base it is collapsing over, and how
many commits go in go onto the pinned comment BEFORE the reset -- and a tick
that comes back to a one-commit branch reads them rather than guessing. What
it does with them is resume: the same leased publication the squash would have
made, entered on the head this collapse accounts for, handed the same
before-state, and finished with the count only the record still holds. Nothing
is squashed again, and an already-landed one is finished as the leased no-op
it is rather than remeasured or readjudicated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestrator.config import settings as config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    formats as _formats,
    rewrite_values as _rewrite_values,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_freeze as _freeze,
    late_gate_models as _late_gate_models,
    late_overflow as _overflow,
    late_parks as _parks,
    late_push as _push,
    late_records as _records,
    late_transfer as _transfer,
)

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"


# How a squash can fail to be the thing this owner publishes. Each is spelled
# as the park comment reads it, because what an operator has to reconcile
# differs by which side of the push it was noticed on.
_MOVED_CHECKOUT = (
    "the squash made `{squashed}` and the checkout stands on `{head}`"
)


_MOVED_SQUASH_PARK = (
    "{mentions} the reviewer approved this pull request and the orchestrator "
    "squashed its commits, but the checkout it squashed in is not the one the "
    "squash left behind: {refusal}. Something committed over the worktree "
    "while the publication was being made, so nothing has been handed on -- "
    "and the branch is left exactly as it was found rather than reset, since "
    "whatever moved it made a commit nobody here can account for. Reconcile "
    "the worktree with what landed and the next tick squashes afresh."
)


@dataclass(frozen=True)
class _Collapsed:
    """What the plan taken before the reset says this squash replaced.

    The two facts the rewrite destroys and nothing past it can recover: the
    head that was collapsed, and the merge base it was read over. They travel
    together because they are one reading -- the plan takes both while the
    branch is still intact -- and as a record rather than as two arguments so
    the seam that hands them over cannot transpose them.

    Empty for a caller with no plan behind it, which is what a squash the
    switch kept out of the gate has: nothing is measured there and no transfer
    is decided, so there is no before-state for either to be about.
    """

    head: str = ""
    base_sha: str = ""


def _switched_off(gate: _late_gate_models._Gate) -> bool:
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
    gate: _late_gate_models._Gate, expected: str, candidate: str = "",
) -> _late_gate_models._PublicationEntry:
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
        return _late_gate_models._PublicationEntry(published_sha=expected)
    return _proved_publication(gate, expected, candidate)


def _proved_publication(
    gate: _late_gate_models._Gate, expected: str, candidate: str = "",
) -> _late_gate_models._PublicationEntry:
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
        _late_gate_models._Entered(
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
    gate: _late_gate_models._Gate,
    branch: str,
    entry: _late_gate_models._PublicationEntry,
    squashed: str,
    collapsed: _Collapsed,
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
    if not _standing_on_the_squash(gate, squashed):
        return _push._PushedCandidate(held=True)
    return _push._publishes(
        gate, branch,
        _late_gate_models._Entered(
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
    entry: _late_gate_models._PublicationEntry,
    squashed: str,
    collapsed: _Collapsed,
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


def _rewrite_stands(gate: _late_gate_models._Gate, squashed: str) -> bool:
    """Whether a HELD squash must be left on the branch it rewrote.

    A hold is not one state. Three of its shapes leave the squashed commit
    somebody's, and in each the reset the caller would otherwise take is the
    destructive step:

    * the push LANDED and only the handoff was held -- the receipt names the
      squash, so the remote carries it and a reset would take the branch off
      a commit the pull request has;
    * a DEBT names it -- the approval says this commit is owed a push and no
      other may be pushed in its place, so a reset would leave the
      reconciliation ahead of every later handler asking for a checkout back
      for work only the reflog still has;
    * the RECORD names it -- any live generation whose candidate is the
      squash, not merely an oversized one. Past the ceiling the adjudication
      owns it and an authorized settlement publishes it from this branch;
      short of a count the pair is one the reconciliation ahead of the next
      handler owes a reading, and that reading can only be taken in the
      checkout it was frozen on -- put back, the record names a commit the
      branch no longer has, and every later tick refuses it as a candidate
      that moved instead of measuring it again;
    * the checkout is not the squash at all -- something committed over it --
      and a reset would destroy work nobody here can account for.

    Everything else is a reading that refused before it froze anything: a pull
    request a human closed mid-rewrite, a head somebody moved under it, an
    approval nothing could pin. Those persist no record -- an entry that could
    not prove itself deliberately writes none -- so nothing names the squash,
    and leaving it on the branch is what makes the retry find ONE commit, take
    the nothing-to-squash road, and report success without measuring or
    pushing anything -- so the approved work reaches the merge button neither
    counted nor on the remote. Put back, the retry finds the commits it was
    approved with and squashes, measures, and publishes them afresh.

    The two questions are one rule read from its ends: the branch may go back
    only where nothing durable is left pointing at what is on it.

    The checkout is proved again here rather than taken from the reading
    before the push, and the two guard different steps: that one decides
    whether to PUBLISH, and a whole gated push stands between it and the
    reset this one decides.
    """
    if _named_by(gate.state, squashed):
        return True
    proved = _measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    return not (proved.is_frozen and proved.sha == squashed)


def _named_by(state, squashed: str) -> bool:
    """Whether this record names the squash as work something still owns.

    Three fields, because three different things point at a commit and each
    outlives the step that wrote it: the receipt says the remote has it, the
    approval says a push is owed for it, and a live generation says a reading
    is about it. Any one of them left naming a commit the branch no longer has
    is a record every later tick trips over -- so the reset is the destructive
    step wherever one of them answers.

    Asked as a group rather than one at a time because they are written by
    different owners in different orders, and a road that lost a write can
    leave any subset of them down: a transfer whose grant landed and whose
    push was refused has the approval naming the squash while the receipt
    still names the head it replaced.
    """
    named = (
        _parks._published_commit(state),
        _parks._approved_commit(state),
        _late_state.read_late_generation(state).candidate_sha,
    )
    return bool(squashed) and squashed in named


def _standing_on_the_squash(gate: _late_gate_models._Gate, squashed: str) -> bool:
    """Whether the checkout is still the commit the squash just made.

    Proved rather than read: a revision this host cannot peel is not a head
    that matches anything. A checkout standing somewhere else is not rolled
    back to the pre-squash head either -- whatever moved it committed
    something, and a reset would destroy work nobody here can account for. It
    parks with the branch exactly as it was found.
    """
    proved = _measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    if proved.is_frozen and proved.sha == squashed:
        return True
    return _refuses_the_squash(
        gate,
        _MOVED_CHECKOUT.format(
            squashed=squashed, head=proved.sha or "an unreadable head",
        ),
    )


def _refuses_the_squash(gate: _late_gate_models._Gate, refusal: str) -> bool:
    """Park a squash whose checkout is not the commit it was handed, and stop.

    Reported and parked the way every other reading this gate could not take
    is, so an operator sees one shape for "the checkout is not what this was
    about" whichever side of the push it was noticed on. The flags are left in
    memory for the caller that ran this to persist, exactly as the gate's own
    parks are.
    """
    log.error(
        "issue=#%d cannot publish the squash it made (%s); refusing to hand a "
        "checkout nobody squashed to the pull request",
        gate.issue.number, refusal,
    )
    _parks._parked(
        gate, _records._reportable(gate, _late_state.read_late_generation(
            gate.state,
        )),
        refusal,
        _MOVED_SQUASH_PARK.format(
            mentions=config.HITL_MENTIONS, refusal=refusal,
        ),
    )
    return False


def _forgets_the_rollback(gate: _late_gate_models._Gate, restored: str) -> None:
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
    owed = _parks._approved_commit(gate.state) != restored
    if owed:
        _parks._forget_approval(gate.state)
    carried_back = _transfer._abandoned_authorization(gate, restored)
    collapsed = _claims_a_collapse(gate.state)
    if collapsed:
        _forgets_the_collapse(gate.state)
    if not (owed or carried_back or collapsed):
        return
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _records_the_collapse(
    gate: _late_gate_models._Gate, head: str, base_sha: str, count: int,
) -> str:
    """Say what this squash is about to collapse, durably, before it does.

    The one write that has to happen while the branch can still describe
    itself. A squash replaces the commits a reviewer approved with a single
    object carrying the same tree, so past the reset the head it replaced is
    off the branch, the count is gone with the commits it counted, and what is
    left looks exactly like a branch nobody ever squashed. A process that dies
    in that window comes back to a one-commit branch, a remote still standing
    on the head it replaced, and nothing on the comment saying a rewrite was
    begun -- and the retry takes the nothing-to-squash road and reports
    success without measuring or pushing anything.

    So the terms go down first. They are what a later tick tells an
    interrupted rotation from a finished one BY, and they are the whole of
    what it may take on trust: everything else the resumed publication needs
    is asked again of the world it is about.

    A write GitHub refuses is answered by NOT rewriting. The staged payload is
    put back exactly as it was found and the caller is handed the reason, so
    the approved commits stay on the branch and the next tick squashes them
    afresh -- rather than a collapse being made that nothing on the comment
    could ever account for.

    Answers with the refusal, or "" where the terms are durable.
    """
    before = dict(gate.state.data)
    try:
        _collapses.record_pending_collapse(
            gate.state, head=head, base_sha=base_sha, count=count,
        )
    except _formats.InvalidLateValue as refused:
        return f"the squash could not be recorded before it ran ({refused})"
    try:
        gate.gh.write_pinned_state(gate.issue, gate.state)
    except Exception:
        log.warning(
            "issue=#%d could not record the squash it was about to make of "
            "%s; leaving the approved commits on the branch",
            gate.issue.number, head, exc_info=True,
        )
        gate.state.data.clear()
        gate.state.data.update(before)
        return "the squash could not be recorded before it ran"
    return ""


def _claims_a_collapse(state) -> bool:
    """Whether this comment claims a squash somebody may not have finished.

    Presence rather than readability, which is the difference the caller acts
    on: a comment carrying no claim has nothing to recover, and one carrying a
    claim this build cannot read has a branch nobody can account for. Read
    through the fail-closed reader alone, the second would be waved past as
    the first -- and the branch it is about is the one that looks like it has
    nothing to squash.

    It is also what a failure asks before it words a human's notice: an issue
    still claiming a collapse is one whose branch may be standing on it rather
    than on the commits a reviewer approved.
    """
    return _collapses.carries_pending_collapse(state)


def _recorded_collapse(state) -> _collapses.LateCollapse | None:
    """The squash this issue began and may not have finished, or None."""
    return _collapses.read_pending_collapse(state)


def _forgets_the_collapse(state) -> None:
    """Drop the record of a squash nothing is waiting on any more.

    Staged rather than persisted, and every caller of it has a durable write
    of its own behind it: the reset a rollback made, the reset that never ran,
    the fresh terms the next squash records, and the write the approval handoff
    makes once its notice has gone out. A process dying before one of those
    comes back to a record still standing over a branch the recovery reads
    again and answers the same way -- an already-published collapse is
    finished a second time as the leased no-op it is, and an untouched branch
    is squashed afresh.

    Taken over the pinned STATE rather than over a gate, because the owner
    that finally drops one is the stage handoff, which has no candidate to
    build a gate around: past the push there is nothing left to decide about.
    """
    _collapses.clear_pending_collapse(state)


def _collapse_of(
    head: str, base_sha: str, count: int,
) -> _collapses.LateCollapse:
    """The three facts a squash destroys, as the record every owner holds one.

    Built here rather than by the caller that took them, so the plan a fresh
    squash makes and the record a resumed one reads back are the same shape
    all the way down: the head that is being collapsed, the base it is
    collapsed over, and how many commits go in. The publication tail past the
    reset is handed one of these whichever of the two produced it, and nothing
    below has to know which.
    """
    return _collapses.LateCollapse(
        head=head, base_sha=base_sha, count=count,
    )


def _resumed_entry(
    gate: _late_gate_models._Gate,
    recorded: _collapses.LateCollapse,
    squashed: str,
) -> _late_gate_models._PublicationEntry:
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
        gate, _leased_head(gate, recorded, squashed), candidate=squashed,
    )


def _leased_head(
    gate: _late_gate_models._Gate,
    recorded: _collapses.LateCollapse,
    squashed: str,
) -> str:
    """The head a resumed collapse is entered on, of the two it may be.

    The recorded head is the ordinary one: the collapse was made over it, the
    pull request is still standing there, and the force-push that finishes the
    rotation is what moves it.

    The SQUASH itself is the other, and only where a durable receipt says this
    issue's own push put it there -- the commit recorded as published, dated
    to this attempt by the head it replaced. That is the window a tick that
    pushed and died before its handoff leaves: the remote already carries the
    rewrite, so entering on the head it moved off would refuse the very
    publication this recovery exists to finish, and the retry would remeasure
    a squash the pull request already has. Entered on the commit instead, the
    publication is the leased no-op it should be and the handoff behind it
    finishes with the count only the record still holds.

    The receipt alone would not say it. It is never cleared, so it goes on
    naming a commit this stage pushed rounds ago; what dates it to THIS
    collapse is the head it was pinned to, which is the head the record says
    was rewritten.
    """
    if _already_published(
        gate.state, recorded.head, squashed,
        _parks._recorded_pull_request(gate.state),
    ):
        return squashed
    return recorded.head


def _already_published(
    state, replaced: str, squashed: str, pull_request: int,
) -> bool:
    """Whether a durable receipt says this issue's push put the squash out.

    The receipt, the head it was pinned to, and the pull request it went onto,
    asked as one question, because none answers it alone: a receipt is never
    cleared, so on its own it goes on naming a commit this stage pushed rounds
    ago; a head with no receipt beside it names no push at all; and the two
    together still say nothing about WHICH publication received the commit, so
    a branch pushed from that head onto a pull request since closed and
    REPLACED by another on the same ref answers for both. All three date one
    push to one collapse -- the commit that went out, from the head this record
    says was rewritten, onto the publication the caller is proving against.

    Two owners ask it and they are the two ends of the same window. The entry
    a resume freezes is taken over the rewritten commit where this answers
    yes, since the pull request is already standing there. And a push that
    then does NOT go out may not put the branch back there: the remote carries
    the commit, so a reset would take the checkout off it and the count the
    handoff still owes a notice would go with the record.
    """
    return _parks._publication_from(
        state, replaced, pull_request,
    ) == squashed
