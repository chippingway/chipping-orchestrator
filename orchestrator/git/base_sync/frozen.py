# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which records hold a per-issue checkout still, and for how long.

The refresh runs before any handler does, over every worktree that survived
the previous tick, so a record written by a stage that has not run yet is the
only thing standing between `origin/<base>` and a branch somebody is mid-way
through deciding about. What this owner is, is the list of those records and
the rule each one ends by -- because a freeze with no end is a branch that
never sees its base again.

Most of them end by being SPENT: the step that consumes the record drops it,
so the freeze lasts exactly as long as the question it belongs to -- the terms
a squash records before it rewrites the branch among them, dropped by whatever
finishes or undoes that collapse. Three do not, and they are the reason this
is an owner rather than a tuple. An
exemption and a publication record are invalidated by the head moving off them
rather than by any write, so what answers for those is the checkout itself --
and, since neither is ever dropped, how long the STAGE that reads them keeps
the issue, which the `refresh_selection` owner asks beside this one. And two
PARKS freeze a branch with no record the list can find: a size reading nobody
could take, whenever the refusal came before a commit could be named, and an
implementer timeout, whose watermark is a commit that has not been made yet.
Both are answered by the reason the park carries.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.git.base_sync.state import _PENDING_PUSH_SHA, log
from orchestrator.git.verification import probes as _probes
from orchestrator.github import pinned_state as _pinned_state

# Every record that freezes a branch on its own, whatever the labels and flags
# beside it say: the tip a read-only relabel handed over and has not spent, the
# two a discussion tick leaves while it is mid-flight, the two groups the late
# size gate is deciding by, and the terms of a squash it is mid-way through. They are spelled here the way every pinned
# key this package reads is -- what this gate pins down is how the refresh
# reads state written by stages it never calls into, so a shared constant would
# let a rename pass unnoticed on the side that has to keep understanding it.
# The two discussion records do not depend on `awaiting_human`: an opening
# round leaves the issue unparked by design, so the park read beside this one
# would never see them.
#
# The two late records are the sharpest of the five, because their whole point
# is that a recorded commit is the evidence. An adjudication names one commit,
# measures it against one base, shows an agent the diff between them, and
# publishes or preserves exactly that commit several ticks later; a rebase in
# any of those gaps moves the branch off the SHA every one of those steps acts
# on -- and the reconciliation that noticed would park rather than substitute
# whatever HEAD had become. The candidate is dropped by the write that ends the
# generation, and the approved commit by whichever handoff spends it -- the
# publication that hands the issue to review, or the recovery that republishes
# it -- so both freezes end with the question they belong to, and every field
# written beside either goes with it.
#
# The approved commit picks the candidate's freeze up exactly where it ends. It
# is written by the same write that APPROVES a candidate for publication -- the
# retirement a small one earns, and the exemption an authorized settlement
# records --
# and the push it licenses runs after that write, so without this the one gap
# left open would be the one where nothing else on the issue names the work at
# all. Past the push its freeze is also the remedy for the park that refuses an
# unpublishable checkout: what settles that park is an operator putting the
# worktree back, and a rebase between their `git checkout` and the tick that
# would have noticed moves the head off that commit again, leaving the park
# with nothing to recover on.
#
# Both are read as GROUPS rather than as the two commits alone, and that is
# what a partial record is answered by. Every key in either group goes down in
# one durable write, so a comment carrying part of one is a comment something
# edited -- and the owner that notices parks the issue rather than acting on
# it. That owner runs at dispatch, which is AFTER this. Held only by the
# commit, a reading whose candidate a hand edit took would be rebased and
# force-pushed while it still named the base it was measured from, the ceiling
# it was measured against, the count, and the publication it was entered on --
# every one of which the retry is bound to -- and a lease with no approval
# beside it names the head a push was owed against and nothing else. So the
# branch is frozen for anything the damage read would refuse, and the park
# lands on a checkout still standing where the record says it is.
_LATE_READING_KEYS: tuple[str, ...] = (
    "late_cycle_id",
    "late_generation",
    "late_root_issue",
    "late_current_issue",
    "late_candidate_sha",
    "late_base_sha",
    "late_threshold",
    "late_additions",
    "late_phase",
    "late_post_publication",
    "late_source_stage",
    "late_published_pr_number",
    "late_published_sha",
)


# The head an approval pins its push against, named on its own because one
# reader asks it for its VALUE rather than for being there: it is the single
# late field this domain can recognize as its own work, since an auto rebase
# pins its anchor before git runs and enters the gate on that same head.
_LATE_APPROVAL_LEASE = "late_approved_lease"


_LATE_APPROVAL_KEYS: tuple[str, ...] = (
    "late_approved_sha",
    _LATE_APPROVAL_LEASE,
)


_FROZEN_BY_KEYS: tuple[str, ...] = (
    "read_only_baseline_sha",
    "discussion_round_open",
    "discussion_publishing_sha",
)


# The late groups, and the one difference in how they are read: a key CARRIED
# at all holds the branch, whatever value it carries. That is the damage
# guard's own test, and the two have to agree or the freeze covers less than
# the refusal it exists to make reachable -- a count of `0` is what a
# candidate adding nothing really measures to, a ceiling of `0` is one an
# operator can configure, and a marker reading `false` is what a hand edit
# leaves. Read for truth, each of those is a record this refresh cannot vouch
# for and rebases anyway, while the dispatcher parks a tick later on a branch
# that has already moved.
_LATE_CLAIM_KEYS: tuple[str, ...] = (
    _LATE_READING_KEYS + _LATE_APPROVAL_KEYS
)


# The terms a squash-on-approval records before it destroys the evidence of
# itself: the head it is collapsing, the base it is collapsing over, and how
# many commits go in. They are the sharpest freeze here, because what they
# describe is a branch mid-rewrite -- and the recovery that finishes one
# proves the commit on the branch carries the tree the recorded head left,
# which is what a squash produces and what a rebase destroys. Rebased inside
# that window the collapse is gone, the record describes objects the branch no
# longer relates to, and the tick that would have finished it refuses instead
# -- with the pull request still standing on the history the record says was
# collapsed, and the rebase already force-pushed over it.
#
# The freeze ends by being SPENT, like the reading and the approval above:
# whatever ends the collapse drops the record in the same breath -- the reset
# a rollback made, the reset that never ran, and the approval handoff's own
# write past a landed push.
#
# It is read for the key being PRESENT rather than for the value under it, and
# that is a stricter test than the group above uses. A pinned comment is JSON,
# so a member can be there and `null` -- a hand edit, or an older binary -- and
# the squash's own reader counts exactly that as a claim it must refuse rather
# than resume. The two have to agree: read for a value, this refresh would
# rebase a branch the squash then declines to touch, and the collapse would be
# stranded on a checkout something rewrote underneath it.
_LATE_COLLAPSE_KEYS: tuple[str, ...] = (
    "late_collapse_head",
    "late_collapse_base_sha",
    "late_collapse_count",
)

# The two records the list above cannot cover, because no write is guaranteed
# to end either. `late_exempt_sha` names the commit an authorized settlement
# accepted -- it says that commit needs no measuring EVER, which is what stops
# the gate reading it past the same ceiling and adjudicating it again forever
# -- and it is deliberately never cleared at all. `implementing_published_sha`
# names the commit this stage last pushed, which is what has a tick whose
# relabel did not land finish the handoff rather than re-decide a branch that
# is already on the remote, and it is overwritten by the next publication
# rather than spent. A rebase while the checkout stands on either is what
# would undo them: the commit is gone, and what the gate reads is a rewrite it
# never decided about.
#
# The approval above is the same window read from a third place and NOT a
# duplicate: `late_approved_sha` is what says a push is owed, so it freezes by
# its presence and is spent by the push it waits for. These two outlive it,
# which is exactly why presence cannot be their test -- every issue that ever
# earned a verdict, or ever published, would be out of the base refresh for
# the rest of its life. They are read the way the GATE reads them instead:
# this checkout is standing on the commit, or there is nothing here left to
# protect. The `refresh_selection` owner beside this one asks the other half,
# which is whether the stage that has to act on the commit still has the issue.
_HEAD_HELD_KEYS: tuple[str, ...] = (
    "late_exempt_sha",
    "implementing_published_sha",
)


# The park a size gate takes on a reading it could not complete. It is here as
# a park rather than as a record because the sharpest of those refusals has no
# record to leave: a revision that would not resolve names no commit, so
# nothing goes on the pinned comment for the list above to find, and the
# branch would be rebased under a park whose whole promise is that the commit
# is still where the developer left it. The retry is bound to what the
# checkout holds -- the exact pair where one was frozen, and a refusal to
# substitute anything where one was not -- and a rewrite in between is what
# makes both unanswerable: the frozen commit is gone, and the checkout the
# refusal was protecting is standing on the base.
#
# A reading lost to the TRANSPORT reaches this reason only once the gate has
# spent the three tries it takes quietly, and what holds the branch through
# those ticks is the reading group above rather than anything here: each of
# those misses writes the frozen candidate back -- with the base beside it
# wherever the reading got that far -- and those are the keys on that list.
# The count it increments is not one of them, and neither is the step a notice
# named. Those two say what happened to a READING; a freeze is held by the
# commits, which are what a rebase takes away and what the retry has to find
# still standing. It is the same division as the paragraph above draws --
# what this reason covers is the refusals that leave no pair to find, and none
# of those is retried quietly at all, because a candidate this host does not
# hold and a diff nothing here can pin answer a second reading exactly as they
# answered the first.
#
# It ends the way every other park does, by being answered, and which road
# does the asking is what says how long the freeze has to hold. PAST
# publication the reconciliation ahead of every handler re-measures the exact
# pair once a poll whatever the park says, so a remote that comes back
# settles it with nothing said on the thread -- and the checkout has to be
# standing where the record left it for every one of those readings, not
# merely for the one that took the park. BEFORE it nothing retakes the
# reading at all: the park owns the tick, and what re-enters the gate is a
# human's own trusted bare continue, however many polls later that is. Either
# window ends the same way if the branch is rewritten inside it -- the frozen
# commit is gone, and the reading that would have ended the park has nothing
# left to take. The retry either takes the reading, hands the issue to the
# developer, or takes the park again with the reason it fails for now.
_MEASUREMENT_PARK_REASON = "late_measurement_failed"

# The park an implementer timeout leaves, and the one record here that names a
# commit which does not exist yet. `pre_implement_sha` is the tip the run
# STARTED at, kept so the next tick can tell a commit a descendant the timeout
# cleanup raced finished writing -- the #77 shape -- from the carried-over
# commits already on the branch. Every reading of it is a comparison against
# what the checkout has become since.
#
# Which is exactly what a rebase destroys, and destroys most sharply on the
# commonest shape of this park: a run that timed out having committed nothing
# leaves a branch with nothing ahead of base, so a base that advances
# fast-forwards the checkout straight onto the new tip. The head has moved and
# no developer wrote anything, and a recovery reading the difference alone
# would take the base branch for a late-landing commit and publish it as this
# issue's implementation -- a branch and a pull request with no diff in them.
# The proof beside that reading refuses it, and this is the other half: a park
# whose whole promise is that the commit is where the developer left it may
# not have the branch rewritten under it.
#
# It closes the pre-PR half of a hole the PR-aware route never had: that route
# stands down on every `awaiting_human` park whose reason it does not own, so
# a timeout park on an issue with a pull request was already safe. The park
# this is about is the commonest one WITHOUT a pull request -- a first
# implementing run killed before it published anything -- which is precisely
# the route that had nothing asking.
#
# It ends the way the reading park does: the recovery publishes what it
# found, hands the issue to the developer on a human's reply, or leaves the
# park exactly where it is.
_TIMEOUT_PARK_REASON = "agent_timeout"

_PARKED_ON_A_COMMIT: tuple[str, ...] = (
    _MEASUREMENT_PARK_REASON,
    _TIMEOUT_PARK_REASON,
)


def _held_records(state: _pinned_state.PinnedState) -> tuple[str, ...]:
    """The records on this issue that freeze its branch by their presence.

    The three read for what they HOLD are records whose value is the claim --
    a tip, a round, a publication in flight -- and each is cleared to `None`
    by the step that spends it. The late groups are read for the key being
    there AT ALL, which is how the guard that refuses a partial one reads
    them: the two agree, so nothing this refresh rebases is something that
    guard would go on to park.

    The collapse group is read one step stricter still -- the key being on the
    comment at all, `null` included -- because the squash's own reader counts
    a member spelled that way as a claim it refuses to resume. Anything this
    refresh rebased there would be a branch that owner then declines to touch.
    It is also the one group nothing sets aside: the carve-out below is for an
    approval that is this refresh's OWN interrupted work, and a collapse is
    another owner's -- a rebase under one is exactly what it exists to stop.
    """
    held = tuple(key for key in _FROZEN_BY_KEYS if state.get(key))
    held += _late_claims(state)
    return held + tuple(
        key for key in _LATE_COLLAPSE_KEYS if key in state.data
    )


def _late_claims(state: _pinned_state.PinnedState) -> tuple[str, ...]:
    """The late keys holding this branch, which the reconciliation spends.

    The one part of the list above an owner AHEAD of every stage handler
    answers: the dispatcher's reconciliation measures a frozen pair and pays an
    approved push before any handler is reached, so a hold that keeps the
    handlers back still leaves these something to end them.
    """
    return tuple(
        key for key in _claimed_by(state) if state.get(key) is not None
    )


def _claimed_by(state: _pinned_state.PinnedState) -> tuple[str, ...]:
    """Which late keys freeze this branch, given what else is pinned beside them.

    Every one of them, except in the single case where the approval standing
    here is this refresh's OWN interrupted work. An auto rebase pins its
    recovery anchor before git runs, rebases, and enters the size gate on that
    same head -- which records the rebased commit as one still owed a push,
    durably, before the push goes out. A process that dies in that window
    comes back to both records at once, and the approval reading alone freezes
    the branch out of the very recovery the anchor exists for: the reconciliation
    ahead of the next handler would land the push, and nothing would ever clear
    the anchor, reset the review round, or route the reviewer at the rewritten
    head.

    So the approval is set aside for exactly that shape, and the shape is
    narrow: an anchor still pinned, and an approval leased to it. Nothing else
    writes either -- the anchor is this owner's domain and no stage handler
    runs while one is outstanding -- and a group too damaged to show its lease
    fails the test and keeps the freeze, which is the answer a record nobody
    can vouch for has to get.

    The reading group is never set aside. A generation the gate froze and did
    not answer is a question no push settles, so a branch carrying one stays
    still whatever else is pinned beside it.
    """
    anchor = state.get(_PENDING_PUSH_SHA)
    if anchor and state.get(_LATE_APPROVAL_LEASE) == anchor:
        return _LATE_READING_KEYS
    return _LATE_CLAIM_KEYS


def _awaits_a_commit_of_its_own(state: _pinned_state.PinnedState) -> bool:
    """Whether a park about this branch's own commit holds it still.

    Read as parks rather than as records, and both halves are asked: the
    reason alone is durable across the write that clears the flag beside it,
    and a spent one left behind would freeze a branch nothing is waiting on.

    The two are together because what they are waiting for is the same thing
    seen from either side of it -- a commit that was made and could not be
    read, and a commit that may still be being written -- and a rebase is what
    takes it away from both. Neither can be answered from a record the list
    above would find: one refused before any commit could be named, and the
    other names the tip the run started at rather than anything it produced.
    """
    if not state.get("awaiting_human"):
        return False
    return state.get("park_reason") in _PARKED_ON_A_COMMIT


def _stands_on_a_decided_commit(
    worktree: Path, issue_number: int, state: _pinned_state.PinnedState,
) -> bool:
    """Whether a commit already decided about is what this checkout is on.

    The one freeze that asks the checkout rather than the record, and the
    reason is that the records it is about are never retired.

    Asked only of an issue carrying one, and answered the way the gate answers
    it. A value that is not the head protects nothing any more -- the
    developer has committed since, and what the gate will measure is that new
    work -- and a value that is not an object id at all is no record to either
    reader. A head that cannot be READ is the one case that holds the branch
    anyway: a checkout this process cannot ask about is not one to rewrite.
    """
    decided = tuple(key for key in _HEAD_HELD_KEYS if state.get(key))
    if not decided:
        return False
    head = _probes._head_sha(worktree)
    if not head:
        log.debug(
            "issue=#%d records %s and its head cannot be read; skipping base "
            "sync rather than rewriting a checkout nobody can ask about",
            issue_number, ", ".join(decided),
        )
        return True
    standing = [key for key in decided if state.get(key) == head]
    if not standing:
        log.debug(
            "issue=#%d records %s and stands on %s, so those cover nothing "
            "here and base sync proceeds",
            issue_number, ", ".join(decided), head,
        )
        return False
    log.debug(
        "issue=#%d stands on %s, which %s names; skipping base sync",
        issue_number, head, ", ".join(standing),
    )
    return True
