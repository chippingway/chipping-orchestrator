# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Turning a confirmed design into a plan PR, in a re-runnable order.

What arrives here is a commit `artifact` has already read the branch for, and
what leaves is a pull request the humans can decide. The order is what makes
the step survivable, and it opens with a durable marker naming the tip about to
be published. That write is what makes the step ATTRIBUTABLE as well:
everything after it can leave the world changed, so a later tick finding this
branch mid-publication knows the commit is one this stage began publishing
rather than one that merely looks like a plan -- and `recovery` is what comes
back for it.

Then the push, and a failed one parks without opening anything, so nothing
records a PR that does not exist. The PR is next and is reused if one is
already open on the branch, which is what a tick that died between `open_pr`
and the pinned write recovers through -- it re-derives the same artifact from
the same branch and finds its own PR rather than 422-ing on a duplicate. The
records are staged last and go down in one write, which is also what retires
the marker, so an issue never carries half a publication.

Ahead of the whole of it is the question `settled_prs` answers, because a
commit the humans have already merged, closed, or written their own work on top
of is one with nothing left to push -- and pushing anyway would recreate a
branch a merge deleted or send the older SHA over what they wrote. A window
nobody could see into is neither answer, and it stops the publication where it
stands with the marker written and nothing else.
"""
from __future__ import annotations

import logging

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.workflow.stages.discussion import (
    artifact as _artifact,
    models as _models,
    plan_pr as _plan_pr,
    publication_parks as _publication_parks,
    records as _records,
    settled_prs as _settled_prs,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _publish_plan_if_committed(
    run: _models._DiscussionRun,
) -> _models._PlanArtifact | None:
    """Publish the plan a round of this stage just committed, or refuse it.

    `None` means the tick is finished here: the plan is on a PR, or the push
    that would have put it there failed and said so. Anything else comes back
    as the artifact that was refused, because what "a commit on this branch"
    means depends on where it was found -- mid-disposition, or left behind by
    a round that never reported -- and the caller is the one that can say
    which.

    Both callers reach this with the commit already attributable and with no
    publication in flight: one is the round that made it reporting on itself,
    the other a tick finding the anchor of a round that opened and never
    disposed of what it did. An issue with a marker on it never gets here --
    `recovery._settle_pending_publication` answers first, and answers for the
    branch whatever it finds there.
    """
    artifact = _artifact._plan_artifact(run)
    if not artifact.publishable:
        return artifact
    _publish_plan(run, artifact)
    return None


def _publish_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    """Record the attempt, push, open or reuse the PR, and record the result.

    The marker is written durably first because everything after it can leave
    the world changed: a tick that dies past this point has a tip a later one
    can recognize as its own. It costs one write per publication, which is
    once per issue, and it carries whatever the round staged beside it -- the
    records those staged values describe are the ones this call is about to
    make, so persisting them here rather than at the park is no loss.

    The rest is the re-runnable order: a failed push parks with nothing opened,
    and the PR is found before it is opened, so the window between the two
    writes leaves a PR the next tick adopts. What the humans do inside that
    window is asked FIRST, ahead of the marker: a pull request already carrying
    this commit -- merged, or open with their own work on top of it -- is a
    publication with nothing left to push, and pushing anyway would either
    recreate a branch a merge deleted or send the older SHA over what they
    wrote.

    What is pushed is the SHA the artifact was read at, never `HEAD`. The
    reading and the push are separate git invocations, and anything that moves
    the branch between them -- another tick, an operator, a stray agent --
    would otherwise publish a commit no check ever saw while the records named
    the one that passed.

    Nothing is pushed at all without a session to attribute it to. The body's
    whole job is to say which conversation produced this plan, and a recorded
    id is what makes that answerable: a round resuming one is pinned to it
    before it spawns, and a round opening one records what it opened. Neither
    holds when a backend hands no id back, or when a fresh round is cut short
    before it can say -- and a plan published under an unknown session is one
    a reviewer cannot trace to the discussion that agreed it.

    And nothing is pushed over a remote branch this publication cannot account
    for. The lease is pinned to the tip the remote was observed at rather than
    left to the push's own read, because the push's read would adopt whatever
    it found as the value it may overwrite -- so a retry of a publication that
    crashed would send its older validated commit straight over an update
    somebody made to the branch in between, and the reviewer's own commit would
    be gone with no record that it existed.

    That reading comes AFTER the marker, not before it, because its refusal is
    one an operator is expected to answer. The reply that answers it retries the
    publication, and the only thing that carries a reply there is the marker: an
    issue parked on this refusal without one has no publication in flight and no
    round open, and the park's own reason suppresses the repair request too --
    so the thread would go quiet and neither a push nor an agent would run
    again.

    A window nobody could see INTO is the third answer that question has, and
    it stops the publication where it stands. Read as "no pull request carries
    this", a failed commit-list read has the push recreate a branch a merge
    deleted and ask for a second pull request against a design already in the
    base -- and where the humans amended the plan before merging it, that
    second one proposes taking their amendment back out. So the marker is
    written and nothing else is: the tick that asks again is one poll away, and
    the write is what carries the round's own records there, since a round
    holding its session id only in memory would come back unattributable.
    """
    landed = _settled_prs._settled_plan_pr(run, artifact, artifact.head_sha)
    if landed is _pr_reads.PR_LOOKUP_UNREADABLE:
        _hold_unreadable_plan_pr(run, artifact)
        return
    if landed is not None:
        _records._record_landed_plan(run, artifact, landed)
        return
    if not _marked_publication(run, artifact):
        return
    lease = _permitted_lease(run, artifact)
    if lease is None:
        return
    pushed = _branch_transport._push_branch(
        run.spec,
        artifact.worktree,
        artifact.branch,
        force_with_lease=lease,
        revision=artifact.head_sha,
    )
    if not pushed:
        _publication_parks._park_failed_plan_push(run, artifact)
        return
    plan_pr = _plan_pr._reuse_or_open_plan_pr(run, artifact)
    _records._record_published_plan(run, artifact, plan_pr.number)
    _publication_parks._park_published_plan(run, artifact, plan_pr.number)


def _marked_publication(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> bool:
    """Record the attempt durably, or refuse a plan with no session to name.

    The refusal comes first because it is the one an operator answers with a
    reset rather than a retry: the remedy is a fresh round under a session a
    reviewer can follow, so a marker left standing would have every reply
    republish the same unattributable commit and say so again.

    Everything past the write can leave the world changed -- the remote is
    asked, the branch is pushed, the PR is opened -- and the marker is what
    lets a later tick tell a commit this stage began publishing from one it
    merely found on the branch.

    The park reason goes with it, because a retry arrives here under
    `discussion_push_failed` and this write has already consumed the reply that
    asked for the retry. That reason is a request to an operator, so the
    recovery path refuses to resume a publication carrying it -- and with the
    reply spent, nothing else would either: a crash straight after this write
    would leave the plan waiting for a human to say the same thing twice. So the
    reason becomes what is actually true for the length of the attempt, and
    whichever way the attempt ends writes its own over it.

    A marker already standing on this exact tip, under that same reason, is
    this record and not a stale one, so the write is skipped. What that costs
    is nothing -- every ending of the attempt writes its own state anyway -- and
    what it saves is an edit of the pinned comment on every poll of a
    publication that is holding for a read GitHub keeps refusing. The reason is
    part of the test rather than decoration: a marker sitting under
    `discussion_push_failed` is a park an operator answered, and that write has
    to happen so the reply is spent.
    """
    if not _plan_pr._attributable_plan(run, artifact):
        return False
    marked = run.state.get(_state._PUBLISHING_SHA) == artifact.head_sha
    if marked and run.state.get(
        _state._PARK_REASON,
    ) == _state._DISCUSSION_PUBLISHING:
        return True
    run.state.set(_state._PUBLISHING_SHA, artifact.head_sha)
    run.state.set(_state._PARK_REASON, _state._DISCUSSION_PUBLISHING)
    run.gh.write_pinned_state(run.issue, run.state)
    return True


def _hold_unreadable_plan_pr(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    """Stop a publication that cannot be told from one already finished.

    Nothing is pushed, nothing is opened, and nothing is said on the thread:
    a commit list GitHub declined to serve is a transient failure, and a park
    would put a request to a human on an issue whose only problem is that one
    read has to be taken again. The tick after this one takes it.

    The marker is written all the same, and it is the whole point of stopping
    here rather than simply returning. It is what a later tick recognizes this
    tip by, and its write is what persists whatever the round staged -- the
    session id above all, which a fresh round holds only in memory until
    something writes: lost, the retry finds a valid plan it cannot attribute
    and refuses it as unpublishable.
    """
    log.warning(
        "issue=#%s holding the publication of %s: GitHub could not say "
        "whether %s is already on a pull request for %s",
        run.issue.number, artifact.plan_path, artifact.head_sha,
        artifact.branch,
    )
    _marked_publication(run, artifact)


def _permitted_lease(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> str | None:
    """What this push may overwrite on the remote, or None having said why not.

    The tip it returns becomes the push's lease, which is what makes the answer
    hold: the check and the push are two commands, and a lease pinned to the
    tip that was checked refuses if anything moves the branch between them.
    Left to the push's own read, the lease would be whatever the remote had
    become -- the exact value that lets a retry overwrite it.

    What makes a tip publishable is not which record names it but whether this
    commit CONTAINS it. A branch the remote does not have yet is the ordinary
    first publication and there is nothing to contain. Otherwise the commit
    being published has to descend from what is there, which is true of a
    publication being replayed after a crash (the tip is the commit itself) and
    of an inherited PR branch a discussion was held on top of (the plan sits on
    that tip). A lease cannot stand in for that: it proves only that the ref has
    not moved since it was read, not that what is on it survives the push -- so
    an agent that reset an inherited branch to base and committed the plan there
    would pass every other check and delete the PR's history.

    Answering that takes the tip itself and not merely its id, so the fetch is
    part of the question here as it is in every other reading of a remote tip.
    An id git cannot resolve is refused as a divergence, and a tip that is only
    unfetched is the ordinary state of a branch somebody else has pushed to --
    so a branch this commit really does descend from would otherwise park on a
    reading never taken.

    Anything else parks and says what is there: a human amending the plan on its
    PR, a stray push, a rewritten remote, or a tip nothing could bring here.
    """
    remote_tip = _branch_transport._remote_branch_tip(
        run.spec, artifact.worktree, artifact.branch,
    )
    if remote_tip is None:
        _publication_parks._park_diverged_plan_branch(run, artifact, remote_tip)
        return None
    if not remote_tip:
        return remote_tip
    if _artifact._readable_remote_tip(
        run, artifact, remote_tip,
    ) and _verification_probes._commit_contains(
        artifact.worktree, remote_tip, artifact.head_sha,
    ):
        return remote_tip
    _publication_parks._park_diverged_plan_branch(run, artifact, remote_tip)
    return None
