# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval whose push never happened, paid before the stage runs.

The window the frozen pair cannot cover, one step past it. A candidate the
gate measures at or under the ceiling is APPROVED and its generation retired
in a single durable write, deliberately and before the push -- so a tick that
dies past that write leaves no record to reconcile from and an approval naming
a commit the pull request never received.

Nothing on the stage below reads it. `validating` spawns a reviewer over the
head the pull request already has, the merge gate behind that offers a human a
pull request the work is not on, and the docs pass commits on top of a branch
review never saw. So the debt is paid HERE, ahead of every handler, under the
id the gate decided about and the head it decided against -- both of which
live only on the approval by then.
"""
from __future__ import annotations

import logging

from orchestrator.config import settings as config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow import transitions as _transitions
from orchestrator.workflow.late_split import (
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_parks as _parks,
    late_push as _push,
    late_records as _records,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"


# Why a checkout cannot pay the debt standing on this issue. Each is spelled
# as the park comment reads it, because what an operator has to put back
# differs by which of the three it is.
_ABSENT_CHECKOUT = "the checkout that commit was made in is not on this host"


_UNREADABLE_CHECKOUT = (
    "the checkout that commit was made in cannot say what it is standing on"
)


_MOVED_CHECKOUT = "the checkout is standing on `{head}` instead"


_UNREACHABLE_DEBT_PARK = (
    "{mentions} this issue's committed candidate was measured and allowed to "
    "join its pull request, and the push that would have put it there never "
    "happened -- and it cannot be made from here, because {refusal}. So the "
    "pull request does not carry `{candidate}` and no stage has been run over "
    "it: a reviewer would vote on a head nobody adjudicated. Restore the "
    "checkout to that commit -- or repair the pinned comment if the work is "
    "gone -- and the next tick publishes it, without re-running any agent."
)


# What a debt this tick could not pay is reported as.
_UNPUBLISHED_DEBT = (
    "the commit an approval owes a push for could not be pushed onto pull "
    "request #{number}"
)


# The park a publication that missed leaves, and the flag standing beside it.
# Spelled here rather than imported from the four stage packages that write it,
# for the reason `late_records` keeps route bookkeeping out of this domain: a
# stage's own vocabulary stays that stage's to describe.
_PUSH_FAILED = "push_failed"


_AWAITING_HUMAN = "awaiting_human"


_UNPUBLISHED_DEBT_PARK = (
    "{mentions} this issue's committed candidate was measured and allowed to "
    "join its pull request, and the push that would have put it there never "
    "landed -- so the pull request has not received it and no stage has been "
    "run over it. A push refused here is usually the lease doing its job, "
    "which means something landed on that pull request while the publication "
    "was outstanding. Reconcile the branch with what landed and `{candidate}` "
    "is published from there, without re-running any agent."
)


def _owes_a_published_push(
    label: WorkflowLabel | None, state: PinnedState,
) -> bool:
    """Whether a stage is holding an approval whose push never happened.

    The window the frozen pair cannot cover, and it opens one step later. A
    candidate the gate measures small is APPROVED and its generation retired
    in one durable write, deliberately and before the push -- so a tick that
    dies past that write leaves nothing on the record to reconcile from and an
    approval naming a commit the pull request never received. The stage below
    reads none of it: `validating` spawns a reviewer over the head it already
    has, and the merge gate behind that offers a human a pull request the work
    is not on.

    The LEASE is what says this is one of these. It is written only where the
    approval was taken over a pull request the remote already carries, so an
    implementing-seam approval -- whose push opens the pull request and reads
    the remote for itself -- is not one and is left to the publication that
    owns it.

    Neither is an issue under the adjudication, whatever it records. An
    authorized settlement approves the commit it publishes and settles it
    from there, holding the evidence for exactly as long as that takes; a
    reconciliation stepping in front of that would push under a lease the
    settlement is still reconciling.

    Every other label answers True, and the payment behind this is what says
    whether the stage may make it. That split is deliberate: a debt this owner
    could not pay and did not SEE is a stage running over a publication the
    approved commit never reached, which is the one outcome the whole
    reconciliation exists to prevent.
    """
    if label is None or label == WorkflowLabel.DECOMPOSING:
        return False
    return bool(
        _parks._approved_commit(state) and _parks._approved_lease(state),
    )


def _unpayable_debt(gate: _late_gate_models._Gate, approved: str) -> str:
    """Why this approval cannot be paid from here, or "" where it can.

    An approval is a claim about ONE commit, so the only checkout it can be
    paid from is the one standing on it. Three readings say it is not, and
    every one of them is evidence rather than an absence: a checkout this host
    does not have, one whose head nothing could read, and one standing
    somewhere else.

    The commit is handed IN rather than read here, because the reading this
    proof takes and the one the gate takes behind it have to be about the same
    approval -- and it is the caller that names it to the gate.

    None of them lets the stage run. The debt says a commit the pull request
    does NOT carry was measured and allowed to join it, so a handler run
    behind any of these works from a publication the approved work is not on
    -- the reviewer votes on a head nobody adjudicated, the merge gate offers
    a human that head, and the docs pass commits on top of it. Which of the
    three it is changes only what the operator has to put back, so the refusal
    names it and stops.

    A branch some owner deliberately moved OFF the approved commit is not one
    of these, and never reaches here: an approval whose commit was abandoned
    is superseded, and the owner doing the abandoning drops it -- the auto
    rebase's own reset does exactly that when its push is refused.
    """
    if not gate.worktree.exists():
        return _ABSENT_CHECKOUT
    proved = _measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    if not proved.is_frozen:
        return _UNREADABLE_CHECKOUT
    if proved.sha == approved:
        return ""
    return _MOVED_CHECKOUT.format(head=proved.sha)


_MOVED_STAGE_DEBT = (
    "the stage it was approved on publishes onto a pull request and this "
    "issue is on `{label}`, which does not"
)


_MOVED_STAGE_DEBT_PARK = (
    "{mentions} this issue's committed candidate was measured and allowed to "
    "join its pull request, the push that would have put it there never "
    "happened, and the label has since moved to `{label}` -- a stage with no "
    "pull request to publish onto. So the debt cannot be paid from here and "
    "the stage may not run either: it would work from a publication that "
    "never received `{candidate}`. Put the label back on the stage the "
    "approval was taken on and the next tick publishes it, without re-running "
    "any agent."
)


def _moved_stage_debt(
    gate: _late_gate_models._Gate, label: WorkflowLabel | None,
) -> bool:
    """Stop a tick whose debt belongs to a stage the label has left.

    The stages a debt may be paid from are the exact five the gate takes an
    issue out of, read off the transition graph's own predicate rather than
    off "has an edge to the adjudication" -- which `workflow:ready`,
    `workflow:blocked`, and `workflow:umbrella` all have for reasons of their
    own, none of them a pull request. Paid from one of those, the push would
    go onto a branch that stage knows nothing about and the handler behind it
    would be dispatched over the result.

    So the tick stops rather than the debt being ignored: an approval standing
    here says a commit the pull request does NOT carry was measured and
    allowed to join it, and no stage may run over that -- whichever label the
    issue is wearing by now.

    Announced ONCE, for the reason every refusal in this owner is: nothing
    this process can repair is behind it -- a human moved the label, and only
    a human can put it back -- so a fresh mention every poll would be one
    nobody can answer any faster.
    """
    log.error(
        "issue=#%d owes a push onto a pull request and is labelled %r, which "
        "publishes onto none; refusing to publish or to run its stage",
        gate.issue.number, label,
    )
    if gate.state.get(_state._PARK_REASON) == _parks.PARK_MEASUREMENT_FAILED:
        return True
    _parks._parked(
        gate, _records._reportable(gate, _late_state.read_late_generation(
            gate.state,
        )),
        _MOVED_STAGE_DEBT.format(label=label),
        _MOVED_STAGE_DEBT_PARK.format(
            mentions=config.HITL_MENTIONS,
            label=label,
            candidate=_parks._approved_commit(gate.state),
        ),
    )
    gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _publishes_the_debt(
    gate: _late_gate_models._Gate, label: WorkflowLabel | None,
) -> bool:
    """Pay an approval the tick that took it never got to, before the stage.

    Nothing is measured again: the gate already ruled on this commit and the
    record that said so is gone, so what is owed is the push under the id it
    decided about and the head it decided against. Both come off the approval,
    which is the only place either still exists.

    False is the debt paid -- the pull request carries the commit, the receipt
    is written, and the handler runs behind it over the same world the tick
    that approved it would have handed over. Everything else stops the tick: a
    hold is the gate's own, a push that did not land leaves the approval
    standing for the retry, and a checkout that cannot pay it at all is a
    human's to put back. None of the three lets the stage run over a
    publication the commit never reached.

    The approved commit is read ONCE and handed to both steps. The proof above
    and the gate below each take their own reading of the checkout's head, and
    between the two the worktree is writable -- so a commit landing in that
    window would pass a proof taken against the approval and then be measured,
    pushed, and receipted by a gate that was told to publish whatever it found.
    Named, the two are one decision: the gate refuses a checkout standing
    anywhere but on the commit this debt is for, and the approval is left
    exactly as it is for the retry.

    What the route still owed is restored with it and closed BY the landing.
    There is no run behind this tick to re-derive a reviewer round, a consumed
    fix batch, or a docs receipt from, and no later tick goes back for them:
    the caller whose push failed parked and returns to a stage that
    short-circuits on the park. So the obligations the approval carried past
    its own retirement ride the receipt's write, and the transient park that
    failed push left goes with them -- the condition it names is over the
    moment the commit reaches the pull request, and a park nobody clears is an
    issue waiting on a human for a failure that has already healed.
    """
    if not _transitions.publishes_onto_a_pull_request(label):
        return _moved_stage_debt(gate, label)
    approved = _parks._approved_commit(gate.state)
    unpayable = _unpayable_debt(gate, approved)
    if unpayable:
        return _unreachable_debt(gate, unpayable)
    log.info(
        "issue=#%d records a commit an approval owes a push for and no "
        "generation to reconcile it from; publishing it before the stage runs",
        gate.issue.number,
    )
    published = _push._publishes(
        gate,
        _naming._resolve_branch_name(
            gate.state, gate.spec, gate.issue.number,
        ),
        _late_gate_models._Entered(
            reconciling=True,
            # The approval IS the reading this call is answering, so the
            # switch has nothing left to say about the commit it names.
            answering=True,
            # The head the approval was frozen against. The generation that
            # froze the pull request's head was retired by the write that
            # approved the commit, so re-reading it would answer with wherever
            # that pull request has moved to since.
            head=_parks._approved_lease(gate.state),
            # The commit the approval is FOR, which is the only one this push
            # may publish: the debt was granted about it, the receipt will
            # name it, and a checkout something moved past the proof above is
            # refused rather than published in its place.
            candidate=approved,
            # This tick has no caller behind it to close any of that once
            # the call returns, and the landing is what closes it -- in the
            # same durable write the receipt rides, since a crash between the
            # two would leave the publication recorded and the round it spent
            # not.
            spends=_owed_by_the_route(gate.state),
        ),
    )
    if published.landed:
        return False
    if published.held or _unpublished_debt(gate):
        gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _owed_by_the_route(state: PinnedState) -> _late_gate_models._Spends:
    """What the tick that approved this commit still owes, plus its park.

    The route bookkeeping comes off the record, where the write that granted
    the approval left it: a reviewer round a fix spends, the bookmarks a
    consumed batch clears, the head a finished docs pass produced. Restored
    rather than re-derived, because no developer ran on this tick and nothing
    else on the issue remembers what its caller was part-way through.

    The park is the other half of the same recovery and is spelled here rather
    than on the record, because it is not something a route DECLARED -- it is
    what the unfinished publication itself left behind. An approval standing
    beside a park is always that: this reconciliation runs ahead of every
    handler, so a debt never survives into a later tick's park -- the only way
    the two are on one comment is that the tick which took the approval could
    not finish the publication and stopped for a human. A push that missed
    parks `push_failed`, and a checkout that moved or dirtied around one that
    landed parks `late_candidate_moved`; both name a condition a landed
    republication has just ended, and the steps ahead of it prove exactly
    that -- the checkout is on the approved commit, its tree is provably
    clean, the pull request carries the commit, and the checkout is still on
    it afterwards.

    Applied only where the push LANDS, since the pairs travel to the write the
    receipt makes and nothing applies them otherwise. So a tick that misses
    again leaves the park exactly as it found it.
    """
    owed = _late_state.read_late_spends(state)
    if not state.get(_AWAITING_HUMAN):
        return _late_gate_models._Spends(fields=owed)
    return _late_gate_models._Spends(fields=(
        *owed,
        (_AWAITING_HUMAN, False),
        (_state._PARK_REASON, None),
    ))


def _unreachable_debt(gate: _late_gate_models._Gate, unpayable: str) -> bool:
    """Stop a tick whose approved commit this checkout cannot publish.

    Announced ONCE. The condition is not one this process can repair -- the
    commit is on a host this one is not, or behind a checkout an operator has
    to restore -- so a fresh notice every poll would be a mention nobody can
    answer any faster. A park already standing for the same reading is left
    exactly as it is.
    """
    if gate.state.get(_state._PARK_REASON) == _parks.PARK_MEASUREMENT_FAILED:
        log.warning(
            "issue=#%d still owes a push it cannot make (%s); holding the "
            "tick without a second notice",
            gate.issue.number, unpayable,
        )
        return True
    _parks._parked(
        gate, _records._reportable(gate, _late_state.read_late_generation(
            gate.state,
        )),
        unpayable,
        _UNREACHABLE_DEBT_PARK.format(
            mentions=config.HITL_MENTIONS,
            candidate=_parks._approved_commit(gate.state),
            refusal=unpayable,
        ),
    )
    gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _unpublished_debt(gate: _late_gate_models._Gate) -> bool:
    """Park a debt this tick was allowed to pay and could not, once.

    The approval and its lease are left exactly as they are, which is what
    makes the retry free: it asks for the same commit against the same head.
    What may not happen meanwhile is the stage, which would work from a pull
    request the commit never joined.

    A park already standing for this is left EXACTLY as it is, and that is the
    whole of what this tick does about it. The ordinary way to reach here is
    the second poll of a push that keeps missing: the caller whose own push
    failed parked `push_failed`, this retry asks for the same commit against
    the same head, and it misses again. A fresh mention there is one nobody
    can answer any faster -- and rewriting the reason would replace a
    transient park the stage recoveries retry with one only a human clears,
    so the issue would stop healing itself the moment it started failing.

    So the first miss on an unparked issue -- a crash between a failed push
    and the caller's own park -- is announced under that same transient
    reason, and every miss after it is silent. True where the pinned comment
    has something new on it, so a silent retry costs no write either.
    """
    if gate.state.get(_state._PARK_REASON) == _PUSH_FAILED:
        log.warning(
            "issue=#%d still owes a push onto pull request #%s that will not "
            "land; holding the tick without a second notice",
            gate.issue.number,
            _payloads.as_identity(gate.state.get(_state._PR_NUMBER)),
        )
        return False
    _parks._parked(
        gate, _records._reportable(gate, _late_state.read_late_generation(
            gate.state,
        )),
        _UNPUBLISHED_DEBT.format(
            number=_payloads.as_identity(gate.state.get(_state._PR_NUMBER)),
        ),
        _UNPUBLISHED_DEBT_PARK.format(
            mentions=config.HITL_MENTIONS,
            candidate=_parks._approved_commit(gate.state),
        ),
    )
    # The reason the stage recoveries know how to retry, rather than the
    # measurement park `_parked` writes: nothing here failed to READ anything
    # -- the reading is settled and the push is what missed -- and a transient
    # reason is what lets the route that owns this issue try again on its own.
    gate.state.set(_state._PARK_REASON, _PUSH_FAILED)
    return True
