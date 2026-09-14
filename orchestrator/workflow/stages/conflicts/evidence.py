# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rebase this stage published tells the gate about what it replaced.

The exemption an adjudication leaves names the exact commit a human ruled on,
and a REBASE is one of the things this workflow does that turns that rule
against itself: the branch is replayed onto a base that has moved, the object
the reviewer's verdict was about stops existing on it, and the identical
change is measured past the same ceiling and adjudicated a second time. The
per-tick base refresh answers that for the rebase IT publishes. This owner is
here because the refresh does not drive `workflow:resolving_conflict`: the
replay a branch that has stopped merging cleanly needs is this stage's own,
and so is the account of what it replaced.

So the publication of a clean rebase hands the gate the before-state that
rebase destroyed, and `late_transfer` decides on it. What this owner builds is
that evidence and nothing else: it grants nothing, reads no record, and says
nothing about whether the contribution survived.

One caller builds that evidence from a reading of its own, and the reason no
other can is that no other knows what the commit it is publishing IS.
`publication._publish_clean_rebase` ran the replay itself, on this tick, over
a checkout it held still. Everything else this stage pushes is a commit
somebody ELSE made -- a resolution an agent authored over conflicted files,
the unpushed fix commits the `fixing` drift reroute sends over, whatever an
earlier tick left behind for the recovery to find -- and no reading off the
branch tells those apart from a replay.

So the replay writes itself DOWN, in the two steps its own shape forces. The
head it is about to replace, the fork point that head was read over, and the
pull request it is all being made against go down before the rebase runs --
the first two because the rebase destroys them, the third because `pr_number`
is a field a later tick can find pointing somewhere else and a rewrite is
evidence about ONE publication. The commit the replay produced is stamped on
once there is one, before the size gate is entered, because that is the field
a later tick matches the branch against -- and it is what makes a stale record
inert rather than dangerous: a group naming a commit this checkout is not
standing on describes a replay that is not what is in hand. The tick that
finds an unpushed replay is answered from that record; a commit no record
names is measured.

Two writes on one road, and both are spent only where an exemption could
actually be carried: a branch not standing on the commit this issue exempts
can never earn a transfer, so nothing there is worth a request.

Both ends are read as FORK POINTS rather than as the base branch's tip,
because the two contributions are read over different bases -- that is what a
rebase is -- and the pre-rebase one is gone from the branch the moment the
replay starts. The pre-rebase reading is therefore taken while the branch
still stands where it did, and the caller carries it across the rewrite.

The head the push is LEASED against and the head it replaced are one commit
here, which is what makes the evidence nameable at all: a rebase runs only
over a checkout this stage proved in sync with its remote, so the commit being
replayed is the commit the pull request is standing on. The squash seam is
where those two really part, and it hands them in separately for that reason.

A caller that cannot name every end gets nothing rather than a partial claim.
Evidence with a hole in it is evidence a later reader could not check, and the
answer to having none is the ordinary cumulative gate -- the same measurement
every install took before an exemption could move at all, and the same one a
replay that moved a byte gets, since it fingerprints to another contribution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    formats as _formats,
    payloads as _payloads,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class _Replayed:
    """What the reading taken before a rebase says it is about to replace.

    The commit the branch is standing on and the fork point that commit's
    contribution is read over, together because they are one reading and
    because a rebase destroys both: the head is off the branch once the replay
    lands, and the fork point it was read over is not derivable from the
    object that replaced it.

    Empty for a caller that could not take the reading, which is what a
    checkout whose head or whose merge base nothing could name leaves. The
    builder below turns that into no evidence rather than into a claim with a
    hole in it.
    """

    head: str = ""
    base_sha: str = ""


def _replayed(
    spec: _config_models.RepoSpec, worktree: Path, head: str,
) -> _Replayed:
    """Read the contribution a rebase replaces, while the branch still has it.

    Taken BEFORE the replay, by the caller that is about to run one and over
    the head that caller read for itself -- which is the commit the remote is
    standing on and the commit the force-push is leased against, since a
    rebase runs only over a checkout proved in sync with its remote. Read
    afterwards it would name whatever the replay produced, and the fork point
    behind it would be the base the branch has just moved ONTO.

    A head nothing could name is answered without asking git anything: the
    fork point of nothing is not a base, and a probe run for it would spend a
    process to say so.
    """
    if not head:
        return _Replayed()
    return _Replayed(
        head=head,
        base_sha=_publication_probes._fork_point(spec, worktree, head),
    )


def _rewritten(
    ctx: _models._ConflictContext,
    worktree: Path,
    replayed: _Replayed,
    rebased: str,
    pr_number,
) -> _rewrite_values.LateRewrite | None:
    """The evidence a replayed branch hands the gate, or None where it has none.

    Both pairs, the publication the rewrite was made against, and the head the
    push is pinned to. The fork point of the REBASED commit is read here
    rather than by the caller because it is the one end a reading taken now
    still answers for -- the branch is standing on it, having just been
    replayed onto it.

    The pull request is the one this tick read off the pinned comment, which
    is the field the gate checks the claim against: an entry is frozen for the
    number this issue RECORDS, and a claim naming a different one is a rewrite
    made against a publication this issue no longer has. Held to the shape an
    identity takes, since a value nothing can name a pull request by is no
    publication to scope an authorization to.

    The stage is this owner's own, spelled rather than read back off the
    issue. The label in hand was fetched when the tick began, and what makes
    naming it worth anything is precisely that the permit re-reads the issue
    and refuses where a human has moved it since.

    None wherever any one end is missing. A permit is granted on the whole of
    this record and refused the moment one field cannot be checked, so handing
    in a partial one would spend two fingerprints to reach the answer already
    known here -- and would hide the record a crashed grant left, which is
    what a caller with no evidence of its own is answered from instead.
    """
    number = _payloads.as_identity(pr_number)
    if not (number and rebased and replayed.head and replayed.base_sha):
        return None
    base_sha = _publication_probes._fork_point(ctx.spec, worktree, rebased)
    if not base_sha:
        return None
    return _rewrite_values.LateRewrite(
        kind=_rewrite_values.LateRewriteKind.CONFLICT_REBASE,
        from_sha=replayed.head,
        from_base_sha=replayed.base_sha,
        to_sha=rebased,
        to_base_sha=base_sha,
        pr_number=number,
        source_stage=WorkflowLabel.RESOLVING_CONFLICT,
        lease=replayed.head,
    )


@dataclass(frozen=True)
class _RecordedReplay:
    """What the pinned comment says one replay replaced, and what it produced.

    Read whole or not at all, like every other record in this domain: a group
    short of a member, or carrying a value no writer here would have written,
    describes a replay nothing can check and is answered as no record. What it
    costs to refuse one is the transfer, which the ordinary cumulative gate
    then measures for -- never a park.
    """

    from_sha: str = ""
    from_base_sha: str = ""
    to_sha: str = ""
    pr_number: int = 0


def _records_the_replay(
    ctx: _models._ConflictContext, replayed: _Replayed, pr_number,
) -> None:
    """Make what a rebase is about to replace durable, before it runs.

    The two facts the replay destroys, put where a LATER tick can read them: a
    crash between the rebase and the size gate leaves the replayed commit on
    the branch with nothing on the comment explaining it, and the tick that
    finds it there cannot tell a replay from a resolution an agent wrote.

    The PULL REQUEST goes down with them and for the same reason. A rewrite is
    evidence about one publication, and `pr_number` is a field a later tick can
    find pointing somewhere else -- a plan pull request merged and replaced, a
    hand edit, a reuse. Left to be read at recovery time, this branch's replay
    would be offered as a rewrite of whatever pull request the issue had come
    to record, and another open one standing on the same head would satisfy
    every check the permit makes.

    Written only for a branch standing on the commit this issue EXEMPTS, since
    that is the only branch a transfer could ever be granted for -- anywhere
    else the record would be a request spent to protect nothing. Written only
    where every end was read, for the reason a partial claim is refused
    everywhere else here.

    The commit the replay produces is not on it yet and cannot be: it does not
    exist until the rebase has run. `_records_the_replayed_commit` stamps it,
    and until it does this group names no replay any reader may act on.
    """
    number = _payloads.as_identity(pr_number)
    if not (number and replayed.head and replayed.base_sha):
        return
    if not _exemption_reading.is_exempt(ctx.state, replayed.head):
        return
    ctx.state.set(_state._REPLAY_FROM_SHA, replayed.head)
    ctx.state.set(_state._REPLAY_FROM_BASE_SHA, replayed.base_sha)
    ctx.state.set(_state._REPLAY_PR_NUMBER, number)
    ctx.state.set(_state._REPLAY_TO_SHA, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _records_the_replayed_commit(
    ctx: _models._ConflictContext, replayed: _Replayed, rebased: str,
) -> None:
    """Stamp the commit a replay produced onto the record it completes.

    The field a later tick matches the branch against, and the reason a stale
    record is inert rather than dangerous: a group naming a commit the checkout
    is not standing on describes a replay that is not the one in hand, so an
    agent's resolution and a rerouted fix commit are answered from nothing.

    Made durable BEFORE the size gate is entered, which is the whole point of
    the write: the window this record exists for is the one between the rebase
    and the permission that gate's own grant persists.

    Silent unless the group standing here is the one this replay began, so a
    tick whose branch was never exempt spends no request -- and a record some
    other head left is not completed with a commit it has nothing to do with.
    """
    if not rebased or not _began_this_replay(ctx.state, replayed):
        return
    ctx.state.set(_state._REPLAY_TO_SHA, rebased)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _forgets_the_replay(state: PinnedState) -> None:
    """Drop a replay record the publication behind it has spent.

    Staged rather than written, because every road that reaches it is already
    making a durable write of its own: a record left standing costs nothing --
    a later tick acts on it only where the branch is standing on the commit it
    names -- so it is cleared where clearing is free and never for its own
    request.
    """
    for key in _state._REPLAY_KEYS:
        state.set(key, None)


def _recovered(
    ctx: _models._ConflictContext,
    worktree: Path,
    lease: str,
    recovered: str,
    pr_number,
) -> _rewrite_values.LateRewrite | None:
    """The replay a recovery is finishing, from the record that replay left.

    A tick that finds a commit ahead of the pull request has no reading of its
    own that could say what that commit is, so it is answered from the account
    the replay wrote before it ran -- and only where that account is about the
    commit in hand: the head it says it replaced has to be the head this push
    is LEASED against, which is the tip the pull request is standing on, and
    the commit it says it produced has to be the one the checkout is on.

    The PUBLICATION comes off the record too, never off the comment this tick
    is reading. `pr_number` can be repointed between the rebase and here, and
    a rewrite is evidence about the one publication it was made against: read
    live, this replay would be offered as a rewrite of whatever pull request
    the issue records now, and another open one standing on the same head
    would pass the permit's every check and take the exemption. So the
    recorded number is what the evidence carries, and it has to be the one the
    issue still records -- where the two disagree the replay is about a
    publication this issue has moved off, and the answer is no evidence at
    all.

    Anything else is answered with nothing. A resolution an agent authored, a
    fix commit the `fixing` reroute sent over, a commit made on top of a
    replay, and a record left over from a round that ended some other way each
    fail one of these, and each is measured like any other candidate.
    """
    recorded = _read_replay(ctx.state)
    if recorded is None or recorded.to_sha != recovered:
        return None
    if recorded.from_sha != lease:
        return None
    if recorded.pr_number != _payloads.as_identity(pr_number):
        return None
    return _rewritten(
        ctx, worktree,
        _Replayed(head=recorded.from_sha, base_sha=recorded.from_base_sha),
        recovered, recorded.pr_number,
    )


def _replays_the_publication(
    ctx: _models._ConflictContext, worktree: Path, pr,
) -> bool:
    """Whether the record proves this diverged branch is a replay of that head.

    What lets a rebase past the refuse-and-park default. A replay DIVERGES the
    branch from the head it replaced -- that head stops being an ancestor, so
    the checkout comes back both ahead of the pull request and behind it --
    and that shape is the same one a stale checkout carrying somebody else's
    commit has. Nothing about the counts tells the two apart.

    The record does, and it is a stronger proof than the head-recognition one
    beside it: it names the head the replay was ABOUT to replace, the commit it
    produced, and the pull request it was made against, and all three went
    down before the rebase ran. A remote still standing on the head it names
    is a remote nobody has pushed to since, so the commits the force-push
    drops are exactly the ones this workflow replayed -- which is what a
    rebase is.

    All three are asked, and the checkout is read here rather than left to the
    push behind it: what this decides is whether a branch may be force-pushed
    over a publication it does not contain, so a record that describes some
    other replay, or a checkout standing on something else, may not buy that.

    Silent for every branch with no record, which is every branch this stage
    did not rebase for an adjudicated commit -- so the park stays exactly
    where it was for the stale and diverged checkouts it was written for.
    """
    recorded = _read_replay(ctx.state)
    if recorded is None:
        return False
    head = getattr(getattr(pr, "head", None), "sha", None) or ""
    if not head or recorded.from_sha != head:
        return False
    if recorded.pr_number != _payloads.as_identity(getattr(pr, "number", None)):
        return False
    return recorded.to_sha == _verification_probes._head_sha(worktree)


def _began_this_replay(state: PinnedState, replayed: _Replayed) -> bool:
    """Whether the group standing here is the one this replay just wrote."""
    recorded = _read_replay(state)
    return (
        recorded is not None
        and recorded.from_sha == replayed.head
        and recorded.from_base_sha == replayed.base_sha
    )


def _read_replay(state: PinnedState) -> _RecordedReplay | None:
    """The replay record on this comment, or None where there is none to read.

    Held to the shape each field takes for the reason every other pinned
    commit in this domain is: an abbreviation is not a commit, so a group
    carrying one describes a replay no later reader could check.

    The pair the replay came FROM and the pull request it was made against are
    what make a record readable at all -- without them there is nothing a
    reader could be about, and a number that cannot name a publication scopes
    no evidence to one. The commit it went TO is read the same way and comes
    back empty until the stamp lands, which is what leaves an unfinished
    record naming no branch: the caller acting on one asks for that commit by
    name and an empty answer matches nothing.
    """
    from_sha = state.get(_state._REPLAY_FROM_SHA)
    from_base_sha = state.get(_state._REPLAY_FROM_BASE_SHA)
    number = _payloads.as_identity(state.get(_state._REPLAY_PR_NUMBER))
    if not (number and _commit(from_sha) and _commit(from_base_sha)):
        return None
    to_sha = state.get(_state._REPLAY_TO_SHA)
    return _RecordedReplay(
        from_sha=from_sha,
        from_base_sha=from_base_sha,
        to_sha=to_sha if _commit(to_sha) else "",
        pr_number=number,
    )


def _commit(recorded) -> bool:
    """Whether one recorded end is a whole object id and not an abbreviation."""
    return _formats.is_hex_of(recorded, _formats.COMMIT_LENGTHS)
