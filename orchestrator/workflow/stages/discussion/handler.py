# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One `discussion` tick, in the order its questions have to be asked.

Whether the conversation is over comes first, and `terminal` is what answers
it. Once the humans have confirmed a design and this stage has published the
plan they confirmed, the issue is with them on a pull request, and what that
pull request has become is the whole of what a tick may do next: no round is
opened over the top of it and no agent is spawned, whether the plan merged,
was turned down, or is still being read. That gate reads the publication's own
record rather than the bare `pr_number`, since an issue relabeled here from a
PR stage arrives carrying its dev's -- and it answers for a closed issue too,
which is why it runs ahead of the publication recovery below it rather than
beside the parks.

A publication that started and did not finish comes next, ahead of the
turn-taking below it, because the answer that would otherwise carry a tick this
far is already spent: the write that records a publication in flight persists
what the round staged, the consumed reply included. An issue whose publication
crashed after that point is parked with nothing unread, so waiting for a reply
would mean waiting for a human to say the same thing twice.

Whose turn it is comes next, and a park THIS stage wrote is what settles it:
the round already posted is on the thread waiting for the humans to answer it
by number, so the tick has nothing to OPEN. What it has instead is a reply to
look for, and only a trusted comment past the consumed watermark makes it this
stage's turn again -- an untrusted one may neither steer the agent nor be
recorded as read, and no comment at all leaves the durable state exactly as the
park left it. A park any other stage wrote is not this stage's turn to wait on
-- pinned state outlives a relabel, so an issue an operator moves here from a
parked stage arrives awaiting a reply nobody will send it here, and reading
`awaiting_human` alone would leave it inert for good.

What the last round left comes next, and on an issue this stage has not parked
it is asked in three parts. A commit found against the anchor a round opened
with is settled now because the alternative is the next round adopting it as
its own baseline -- and whose it is the anchor cannot say, so `settlement` is
what stands between publishing the plan a round of this stage left behind and
reporting a commit somebody else put there. Then uncommitted work, because
preparing the checkout is destructive: `_ensure_worktree` would recreate the
tree over changes that are the only record of what an unfinished run was
doing. A tree that could not be READ counts with them, and for the sharper
version of the same reason: nothing has been established about it, and the
recreation behind this question does not wait to be told twice. It is asked
FIRST of the three, because the commit question is a comparison and this read
supplies one of its ends -- an unresolvable `HEAD` comes back empty, compares
unequal to every anchor, and would have the commit already on the branch
published as this stage's own.

A parked issue with a reply asks both of those too, and answers them
differently: it holds silently instead of parking. The park that left the tree
in that state already carries the paths and the reset command, so a second copy
of that message on every reply would bury the one an operator has to act on --
and the reply stays unconsumed, so it is still waiting the tick after they
reset. What runs there FIRST is the publication attempt, ahead of both, and for
a sharper reason than convenience: the reply into a failed push is the only
thing that ever resumes one, and the marker is the sole record of it that
survives a host losing the checkout and the local ref. Read locally that state
is indistinguishable from nothing having happened, so an issue whose plan is
already on the remote would open another round -- and the write that opens one
retires the marker. The same order also keeps a tick that died between opening
the plan PR and recording it from being answered with instructions to reset the
published commit away.

Everything else is the round and its disposition, in that order and nothing
after it. This stage never reaches a developer or a reviewer, and the one thing
it can publish is the plan the humans confirmed: the design is not settled until
they say so on the thread, so what a tick can produce is an analysis to reply
to, a park to reply into, or -- once -- the agreed plan on a PR. The worktree
the round ran in survives every one of those exits, because the tree the
discussion read is the tree the next round and the operator both look at. The
one thing that ever takes it down is the terminal above, and only once the
plan PR is gone: what the tree holds is what that pull request is open
against.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.stages.discussion import (
    checkout_parks as _checkout_parks,
    outcomes as _outcomes,
    recovery as _recovery,
    run as _run,
    session as _session,
    settlement as _settlement,
    state as _state,
    terminal as _terminal,
)
from orchestrator.workflow.stages.discussion.models import _DiscussionRun


def _run_discussion_round(
    run: _DiscussionRun, replies: list | None = None,
) -> None:
    """Open one round and publish whatever it turns out to have left."""
    round_result = _run._open_discussion_round(run, replies)
    outcome = _outcomes._assess_discussion_outcome(run, round_result)
    if outcome.park_reason is not None:
        _outcomes._route_discussion_outcome(run, round_result, outcome)


def _resume_parked_discussion(run: _DiscussionRun) -> None:
    """Answer the humans' reply to the parked round, or leave it parked.

    A tick nobody has answered is a no-op in the strict sense -- nothing
    spawned, nothing posted, no durable write -- so a parked discussion costs
    one comment read a tick and keeps waiting exactly as its park left it.
    """
    new_replies = _session._new_trusted_replies(run)
    if not new_replies:
        return
    if _hold_resume_for_repair(run, new_replies):
        return
    _run_discussion_round(run, new_replies)


def _hold_resume_for_repair(
    run: _DiscussionRun, replies: list,
) -> bool:
    """True when no round may open on this checkout as it stands.

    A publication this stage began is settled before anything local is read,
    because the marker is the only record of one that survives a host having
    lost the checkout AND the local ref. This is where a failed push is
    retried -- the recovery at the top of the tick steps around that park on
    purpose, so nothing else brings one here -- and "the push failed" is a claim
    about the request, not about the remote: the branch may well be published.
    Locally that state reads as nothing at all -- no tree, no branch, an anchor
    nothing has moved off -- so gating the settle on the anchor lets the reply
    open a round instead, and the write that opens one retires the marker. The
    plan is then on the remote with no PR, no record, and nothing left that
    knows to look for it.

    A commit is settled next: the branch may be carrying the agreed plan, in
    which case the reply publishes it rather than earning an answer. Everything
    else is said once and then held quietly. The park written here is itself a
    repair request, so the reply after it changes nothing on the thread -- and a
    park that ALREADY carried those instructions (this issue is sitting on the
    commit or dirty-tree park that reported the violation in the first place) is
    not repeated at all. Only a tree that went wrong under a clean park owes the
    humans an explanation, and without one they would answer the frontier and
    get silence.

    The reply survives every one of these paths but the push that takes it: no
    round opens, so nothing consumes it, and the park preserves the ceiling the
    last round read through. Repairing the tree -- or the push -- is the whole
    of what an operator has to do; the answer they already wrote is picked up on
    the next tick.
    """
    already_asked = _state._repair_already_requested(run.state)
    if _recovery._settle_pending_publication(run, tuple(replies)):
        return True
    checkout = _settlement._checkout_reading(run)
    if checkout.moved:
        _settlement._settle_commit_under_park(
            run, already_asked=already_asked,
        )
        return True
    if checkout.state.readable and not checkout.state.paths:
        return False
    if not already_asked:
        _checkout_parks._park_blocked_resume(run, checkout.state)
    return True


def _handle_discussion(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> None:
    """Open the discussion, answer the humans in it, or wait on them."""
    discussion_run = _DiscussionRun.start(gh, spec, issue)
    if _terminal._drain_discussion_terminals(discussion_run):
        return
    if _recovery._finish_interrupted_publication(discussion_run):
        return
    if _state._parked_by_discussion(discussion_run.state):
        _resume_parked_discussion(discussion_run)
        return
    checkout = _settlement._checkout_reading(discussion_run)
    if checkout.moved:
        _settlement._settle_moved_checkout(discussion_run)
        return
    if not checkout.state.readable or checkout.state.paths:
        _checkout_parks._park_stranded_worktree(discussion_run, checkout.state)
        return
    _run_discussion_round(discussion_run)
