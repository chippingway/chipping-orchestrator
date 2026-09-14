# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Live and recovered evidence for a conflict rebase's exact rewritten pairs.

Live evidence freezes the original head and its fork point. Recovery uses
the pinned replay record and requires its lease, publication, and output
commit to match before the gate may consider moving an exemption.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.late_split import (
    payloads as _payloads,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    replay_records as _replay_records,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _replayed(
    spec: _config_models.RepoSpec, worktree: Path, head: str,
) -> _models._Replayed:
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
        return _models._Replayed()
    return _models._Replayed(
        head=head,
        base_sha=_publication_probes._fork_point(spec, worktree, head),
    )


def _rewritten(
    ctx: _models._ConflictContext,
    worktree: Path,
    replayed: _models._Replayed,
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
    recorded = _replay_records._read_replay(ctx.state)
    if recorded is None or recorded.to_sha != recovered:
        return None
    if recorded.from_sha != lease:
        return None
    if recorded.pr_number != _payloads.as_identity(pr_number):
        return None
    return _rewritten(
        ctx, worktree,
        _models._Replayed(head=recorded.from_sha, base_sha=recorded.from_base_sha),
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
    recorded = _replay_records._read_replay(ctx.state)
    if recorded is None:
        return False
    head = getattr(getattr(pr, "head", None), "sha", None) or ""
    if not head or recorded.from_sha != head:
        return False
    if recorded.pr_number != _payloads.as_identity(getattr(pr, "number", None)):
        return False
    return recorded.to_sha == _verification_probes._head_sha(worktree)
