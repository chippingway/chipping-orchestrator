# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the checkout holds, and whose the commit on it is.

The reading is taken once rather than as two questions asked in either order,
because the second is only answerable while the first says the checkout can be
read at all. A tree `git status` could not report on and a `HEAD` that would
not resolve are each a checkout nothing has been established about, and what
sits behind the moved question is a publication: empty compares unequal to
every anchor there is, so the reading nobody could take would answer "a round
committed here" the loudest of any.

What follows it is an ownership question, and it is the same question on both
roads in. A moved tip says only that the branch is no longer where this stage's
last round opened it; it does not say who put the commit there. The open-round
record is what says that, because it is written durably before the spawn and
cleared by every park: true of exactly the rounds a crash or a mid-run pause
left unreported, and false of the commit an issue arrived carrying from a stage
it passed through before an operator relabeled it here. Reading the second as
the first would put a commit no conversation here ever saw onto a plan PR under
this stage's own session.

A commit this stage owns is settled exactly as the round that made it would
have settled it -- the agreed plan published, anything else parked with what
the branch actually carries -- and one it does not own is reported instead. The
two roads differ only in what that report costs: under a park this stage wrote,
the paths and the reset command are already on the thread, so a tree that was
wrong before the reply arrived is not described to the humans a second time.
"""
from __future__ import annotations

from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.workflow.stages.discussion import (
    checkout_parks as _checkout_parks,
    models as _models,
    publication as _publication,
    publication_parks as _publication_parks,
    round_evidence as _round_evidence,
    state as _state,
)


def _checkout_reading(run: _models._DiscussionRun) -> _models._CheckoutReading:
    """What the checkout is, and whether the round that opened on it moved it.

    One reading rather than two questions asked in either order, because the
    second is only answerable while the first says the checkout can be read at
    all -- and because both of its failures collapse to the same handling. A
    tree `git status` could not report on and a `HEAD` that would not resolve
    are each a checkout nothing has been established about, and what sits
    behind the moved question is a publication: empty compares unequal to every
    anchor there is, so an unread `HEAD` answers "a round committed here" and
    the commit the branch arrived carrying goes out under this stage's name.

    So the anchor is only asked of a readable tree, an unanswerable reading is
    reported as an unreadable checkout, and `moved` is never true on either.
    Both roads behind it publish or park over what it finds, so the branch and
    a tree at the issue's path are admitted first (`naming.BranchRefused`).
    """
    _naming._resolve_branch_name(run.state, run.spec, run.issue.number)
    _worktree_creation._retained_checkout(run.spec, run.issue.number)
    state = _round_evidence._stranded_worktree_state(run)
    moved = (
        _round_evidence._round_anchor_moved(run) if state.readable else None
    )
    if moved is None:
        return _models._CheckoutReading(state=_round_evidence._UNREADABLE_TREE)
    return _models._CheckoutReading(state=state, moved=moved)


def _settle_commit_under_park(
    run: _models._DiscussionRun, *, already_asked: bool,
) -> None:
    """Settle a commit this stage owns, or report the one it merely found.

    A park normally means this stage's round is over, so what appeared on the
    branch afterwards was put there by something else -- and a design nobody
    argued out is not one to open a PR for on a human's next reply, least of
    all on a reply that rejects it. Two records say otherwise, and they are
    the two ways this stage can be mid-something under a park.

    A publication in flight is one of them, and by the time anything reaches
    here it has already answered for the branch either way: the caller asks it
    ahead of every local reading, since it is finished when the tip is still
    the commit it named -- one whose push failed and is being retried by this
    reply, or one whose PR was opened by a tick that died before recording it,
    where reporting a violation would tell an operator to reset away a plan a
    pull request may already be open against -- and refused when the tip is
    anything else, since a commit that turned up over an unfinished publication
    is no more this stage's than one that turned up over a park.

    An open round is the second record, and the one left to read here: a
    resumed round runs with the previous park still durable, so one that
    committed the agreed plan and was then paused or cut short is judged the
    same way `_settle_moved_checkout` judges the crash it recovers.
    """
    if _state._round_in_flight(run.state):
        _settle_recovered_commit(run)
        return
    if not already_asked:
        _checkout_parks._park_blocked_resume(
            run, _round_evidence._CLEAN_TREE,
        )


def _settle_moved_checkout(run: _models._DiscussionRun) -> None:
    """Settle a checkout that has moved off the anchor, by who moved it.

    The anchor says only that the tip is not where this stage's last round
    opened it; it does not say whose commit is there. The open-round record is
    what says that, and it has to be read here as well as under a park, because
    "no discussion park" is not the same as "no park at all". Pinned state
    outlives a relabel: an issue can arrive here awaiting a human under
    ANOTHER stage's park, carrying this stage's anchor and session id from a
    conversation that finished, with that stage's own agent commit on the
    branch. Read as a round of this stage that never reported, a commit made
    there -- by a `question` agent that wrote the one path this stage
    publishes, say -- goes onto a plan PR under a session that never saw it.

    So the same ownership test applies to both: a commit is this stage's to
    publish when one of its rounds was in flight, and somebody else's
    otherwise. The flag is written durably before the spawn and cleared by
    every park, so it is true of exactly the rounds a crash or a mid-run pause
    left unreported -- which are the ones this recovery exists for.
    """
    if _state._round_in_flight(run.state):
        _settle_recovered_commit(run)
        return
    _checkout_parks._park_foreign_commit(run)


def _settle_recovered_commit(run: _models._DiscussionRun) -> None:
    """Publish or refuse the commit a round left with no disposition of its own.

    The round that made it was withheld mid-run or cut short before it could
    say what it had done, so this tick says it instead -- and it says the same
    thing that round would have: the agreed plan is published, and anything
    else parks with what the branch actually carries. Either way no new round
    opens over the top of the commit.
    """
    unpublishable = _publication._publish_plan_if_committed(run)
    if unpublishable is not None:
        _publication_parks._park_recovered_commit(run, unpublishable)
