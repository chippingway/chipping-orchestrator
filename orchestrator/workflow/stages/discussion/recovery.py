# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Carrying a publication a tick died in the middle of to an ending.

The marker a publication writes before it touches anything is what makes the
step re-runnable, and reading it is the whole of this owner's job. It names the
tip that was about to be published, and everything after that write can leave
the world changed -- the remote is asked, the branch is pushed, the PR is
opened -- so a later tick finding this branch mid-publication has to know
whether the commit on it is one this stage began publishing or one that merely
looks like a plan. The marker is what says so.

Once set it answers for the branch itself: the publication is resumed when the
tip is still the commit it named and that commit still validates, and refused
otherwise. What a MOVED tip can mean is the whole difficulty -- a publication
that merged elsewhere, an open one the humans pushed past, a branch an operator
reset, or a second plan-shaped commit nobody here began -- and telling those
apart takes the remote as well as the local reading, because a push sends the
SHA it validated rather than `HEAD` and can therefore land without the local
ref ever moving.

This runs ahead of the turn-taking gate in `handler`, which is why the batch
that drove the tick is handed in to be consumed here: the marker's write
persists whatever the round staged, the consumed watermark included, so an
issue whose publication crashed after that point is parked with no unread
answer and would otherwise wait for a human to say the same thing twice.
"""
from __future__ import annotations

import logging

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.workflow.stages.discussion import (
    artifact as _artifact,
    models as _models,
    publication as _publication,
    publication_parks as _publication_parks,
    records as _records,
    session as _session,
    settled_prs as _settled_prs,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _finish_interrupted_publication(run: _models._DiscussionRun) -> bool:
    """Settle a publication a tick died in the middle of, before anything else.

    It runs ahead of the turn-taking gate because the reply that would
    otherwise carry the tick there is already spent: the marker's write
    persists whatever the round staged, the consumed watermark included, so an
    issue whose publication crashed after that point is parked with no unread
    answer and would wait for a human to say something twice.

    A failed push is deliberately not resumed here. That park is a request to
    an operator, and retrying every tick would push at a remote already
    refusing us and comment each time it did; the reply to that park is what
    retries it, which is also the operator saying they fixed the reason.

    A retry already under way is a different state and resumes like any other:
    the write that begins one replaces that reason, precisely because it also
    spends the reply -- so what reaches here still carrying the failure is a
    publication nobody has taken up yet, and nothing else.
    """
    if run.state.get(_state._PARK_REASON) == _state._DISCUSSION_PUSH_FAILED:
        return False
    return _settle_pending_publication(run)


def _settle_pending_publication(
    run: _models._DiscussionRun, replies: tuple = (),
) -> bool:
    """Carry a publication THIS stage began to an ending, or answer False.

    False means there is no publication in flight and the caller's own reading
    of the branch is what applies. A marker, once set, answers for the branch
    itself -- it is finished when the tip is still the commit it named and that
    commit still validates, and refused otherwise.

    That tip is the whole of what this decides. Everything a MOVED one can mean
    -- a publication that merged elsewhere, a branch an operator reset, a
    second plan-shaped commit nobody here began -- is settled in
    `_settle_moved_marker` beside it.

    `replies` is the batch that drove this tick, and it is consumed by a push --
    only by a push. A retry that fails parks and would otherwise be asked for
    again by the same comment on the very next poll; a refusal leaves the answer
    where it is, since the reply is still waiting on a checkout the humans have
    to put back.
    """
    in_flight = run.state.get(_state._PUBLISHING_SHA)
    if not in_flight:
        return False
    artifact = _artifact._plan_artifact(run)
    if artifact.head_sha == str(in_flight) and artifact.publishable:
        _session._consume_replies(run, list(replies))
        _publication._publish_plan(run, artifact)
        return True
    return _settle_moved_marker(run, artifact, str(in_flight))


def _settle_moved_marker(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    in_flight: str,
) -> bool:
    """Decide a marker whose tip is no longer the commit it names.

    Refused rather than declined, because the alternatives all publish
    something nobody proved: a tip that has moved is a second plan-shaped
    commit this stage never began publishing, and letting the readings below
    take it for a round's own work would credit a design to a conversation that
    never agreed to one.

    That refusal is written once. Its own reason is what the repeat reads, so
    an operator who restores the commit the marker names finds it published on
    the next tick, and one who does not is not told again every poll. A branch
    reset back to the round's anchor is the second answer: it carries nothing
    to publish, so the marker is spent rather than enforced, and the
    conversation is free to continue from the reply that has been waiting on it.

    A publication that MERGED is settled before either of those, and settled by
    recording rather than by publishing. The checkout it is read from can be
    one rebuilt at base -- the merge deletes the branch, so a host that lost the
    worktree and the local ref has nowhere else to rebuild from -- and that tip
    is neither the commit the marker names nor the round's anchor. Left to the
    readings below it is a branch somebody moved, and the issue parks on that
    forever with no `pr_number` and no plan path ever written, while the plan
    it is parked about is in the base branch. So the pull request itself is
    asked for by commit, and finding it finishes the publication the crash
    interrupted. An OPEN one the humans have pushed past is the same answer for
    the same reason, and is settled in the same place.

    That question is the one this cannot proceed without an answer to. Both
    readings under it act on the marker -- one spends it, the other refuses on
    it for good -- and each is a claim about whether the plan was published
    that a failed commit-list read cannot support.

    The reset reading is a claim about the REMOTE, though, and only the remote
    can make it. The push names the commit it sends rather than `HEAD`, so a
    plan committed on a detached head goes out while the local ref never moves,
    and a restore later prefers that local ref over the head it just fetched --
    so a publication that landed and a publication that was reset away look the
    same from here. Spent on that reading, the plan stays open on a pull
    request nobody recorded and the conversation opens another round over the
    top of it. So the marker is only spent once the branch the remote holds can
    be shown not to carry the commit it names.

    A pull request the humans CLOSED without merging is the one answer that
    waits for that reading rather than preceding it, because it is the only one
    the reset can also explain. An operator answering the stale park may well
    close the stray pull request while they are resetting the branch, and a
    close read as a verdict there would finish the issue on debris they were
    tidying. So it is taken up only once the reset has been ruled out -- the
    branch is not back at the anchor, or the remote still carries the commit --
    and then it IS the verdict: the plan is out there, the humans turned it
    down, and `plan_terminal` finishes the issue `rejected` from the record
    this writes. Refused instead, the issue parks on a stale publication
    forever with no number, no label, no event, and no branch anything will
    reap, which is exactly what a reviewer who amends the plan and then closes
    it leaves behind.
    """
    landed = _settled_prs._settled_plan_pr(run, artifact, in_flight)
    if landed is _pr_reads.PR_LOOKUP_UNREADABLE:
        log.warning(
            "issue=#%s holding a publication in flight on %s: GitHub could "
            "not say whether it is already on a pull request",
            run.issue.number, in_flight,
        )
        return True
    if landed is not None and run.gh.pr_state(
        landed,
    ) != _settled_prs._CLOSED_PR_STATE:
        _records._record_landed_plan(run, artifact, landed)
        return True
    published = _publication_on_the_branch(run, artifact, in_flight)
    if not published and artifact.head_sha == str(
        run.state.get(_state._ROUND_SHA) or "",
    ):
        # The operator took the remedy and nothing of ours is on the remote to
        # outlive it: the branch is back at the tip the round opened on, so
        # there is no longer a commit to publish and the marker is spent.
        # Cleared rather than refused on, or the refusal would hold the
        # conversation shut against the reset it asked for -- and staged, so
        # whatever this tick writes next carries it.
        run.state.set(_state._PUBLISHING_SHA, None)
        return False
    if landed is not None:
        _records._record_landed_plan(run, artifact, landed)
        return True
    _refuse_stale_publication(run, artifact, in_flight, published)
    return True


def _publication_on_the_branch(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    in_flight: str,
) -> bool:
    """Whether the remote branch still carries the commit the marker names.

    Asked because a local reading cannot answer it. The commit may have been
    pushed from a checkout whose branch ref never moved -- the push sends the
    SHA it validated, not `HEAD` -- and it survives every local reset, every
    lost worktree, and every restore that comes back on the local ref instead
    of the fetched one. What is out there is what decides whether this stage
    may drop its record of a publication.

    True unless the remote can be SHOWN not to carry it, which is three
    different absences and one presence. A branch the remote does not have is
    the real absence: nothing of this stage's is published, and the marker is
    the caller's to spend -- the one way a deleted branch still means a
    published plan is a merge, and the caller has already recorded that pull
    request before anything reaches here. A tip equal to the commit itself
    needs nothing else asked. Any other tip is a branch that may have been
    moved past the plan -- a human amending their own design on its pull
    request does exactly that --
    so what settles it is whether the commit is still in that branch's history,
    which is a local question about an id that came off the remote. A remote
    that could not be asked, or a tip nothing could bring into this store,
    establishes nothing and answers True: a record dropped on a reading nobody
    could take is a plan nothing goes looking for again.
    """
    remote_tip = _branch_transport._remote_branch_tip(
        run.spec, artifact.worktree, artifact.branch,
    )
    if remote_tip is None:
        return True
    if not remote_tip:
        # A branch that is gone with a merge behind it has already been
        # answered by the caller, which records that pull request rather than
        # asking this. What is left is a branch nothing merged took: a push
        # that never landed, or a pull request somebody closed and cleaned up
        # after. Neither leaves anything on the remote, which is the reset
        # standing.
        return False
    if remote_tip == in_flight:
        return True
    if not _artifact._readable_remote_tip(run, artifact, remote_tip):
        return True
    return _verification_probes._commit_contains(
        artifact.worktree, in_flight, remote_tip,
    )


def _refuse_stale_publication(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    in_flight: str,
    published: bool,
) -> None:
    """Say once that the publication in flight can no longer be finished."""
    if run.state.get(_state._PARK_REASON) == _state._DISCUSSION_STALE_PUBLISH:
        return
    _publication_parks._park_stale_publication(
        run, artifact, in_flight, published,
    )
