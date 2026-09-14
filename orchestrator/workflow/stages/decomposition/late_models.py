# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-cycle orchestration context, owner readings, held pull requests, and staged parks.

The context carries the frozen generation through one tick while recording
which park and publication effects are still owed. The values beside it
keep unreadable owners, displaced holds, and staged notices distinct.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.models import LateGeneration


class _OwnerState(Enum):
    """What a fresh read said about the issue an adjudication belongs to.

    Three answers rather than two, because "could not ask" is not "still
    open". A run finishes minutes to hours after the issue was fetched, and
    everything a verdict earns -- a publication, a snapshot, a supersession,
    an activation -- is an effect on an issue somebody may have closed in
    between. `UNREADABLE` is what the tick fails closed to: it costs one
    poll, while treating it as open costs work done on an issue nobody wants.
    """

    OPEN = "open"
    CLOSED = "closed"
    UNREADABLE = "unreadable"



@dataclass(frozen=True)
class _HeldPr:
    """One pull request a hold is taken on, read once and under one guard.

    A PyGithub pull request is lazy: the object a fetch returns has asked
    GitHub nothing, and the request that can fail is the FIRST attribute read.
    A caller that guarded only the fetch would therefore guard almost nothing
    -- the failure lands later, on the head, the state, or the body, in the
    middle of deciding whether to replace a human's description.

    So every field a decision is made on is read where the fetch is guarded
    and carried here as a plain value. What is left of the pull request is the
    handle the edit is made against, and that write has a guard of its own.
    """

    pull_request: object
    number: int
    body: str
    head_sha: str
    pr_state: str


@dataclass(frozen=True)
class _HeldPrHold:
    """What reconciling the cycle-marked hold left behind.

    `held` and `failed` are not opposites. A generation with no reusable open
    pull request to mark is neither -- there is nothing to hold and nothing
    went wrong -- and the caller spawns exactly as it would have.

    `displaced` is the third answer, and it is the one that looks like the
    second and is not: an open pull request this generation DID hold, wearing
    a description a human wrote over the notice. Their words are left
    alone -- overwriting them is what the release below already refuses -- but
    the change is now mergeable with nothing on it saying an adjudication is
    open, which is exactly the state the hold exists to prevent. So it stops a
    spawn as `failed` does, while a result already recorded may still be
    settled: settling releases a hold that is already gone, and starting a new
    agent would leave a human free to merge under it.
    """

    generation: LateGeneration
    held: bool = False
    failed: bool = False
    displaced: bool = False


@dataclass(frozen=True)
class _StagedPark:
    """A park recorded but not yet said out loud.

    What every exit a COMPLETED run takes hands forward. The park itself has
    to be durable before anything is posted -- a comment GitHub refuses would
    otherwise take the run's result down with it and buy a second run of an
    agent that already finished -- and the owner read between the write and
    the notice is what decides whether the notice is owed at all, since
    nothing is said to a thread whose issue this tick could not prove is open.
    """

    message: str
    reason: str


@dataclass
class _LateContext:
    """The one tick a late adjudication runs inside.

    Mutable in six fields. `generation` is replaced as each step persists
    what it reached, so every owner after that step reads the record the pinned
    comment now holds rather than the one the tick opened on. `retired_park`
    is what this tick cleared, kept because clearing a park is not the same as
    the human it named never having been told: a park retired here and re-taken
    for the same reason is the same park, and repeating its notice would say
    the same thing to the same thread again.

    `answering` is set by the step that reopens a categorized question and read
    by the spawn several steps later: a run carrying a human's answer RESUMES
    the conversation that asked, rather than opening a fresh one that would
    have to be told what it had asked before it could be told the answer. It
    rides the tick rather than the pinned comment because it is a fact about
    this call and not about the issue -- and a tick that dies before the spawn
    simply pays for a fresh conversation, which still reads the answer in the
    thread its prompt quotes.

    `staged_park` is the fourth: the notice a park this tick recorded still
    owes the issue, held between the durable write and the owner read that
    decides whether it may be posted. It rides the tick for the same reason
    `answering` does -- a tick that dies before releasing it leaves the park
    itself standing, and whatever re-takes that park announces it then.

    `already_published` is the sixth, and it is the answer to the one window an
    authorized settlement cannot repair from the record alone. The push that
    decision licenses happens before the relabel and the retirement, so a
    tick that died in between comes back to a live generation whose pull
    request is standing on the accepted candidate rather than on the head the
    reading was frozen at. That is this settlement's own push having landed,
    not somebody else's -- and the proof reads it where the pull request is
    read, several steps before the push it makes unnecessary.

    `displaced_hold` is the fifth, and it travels the length of the call: the
    hold is reconciled at the top and what it found only matters at the spawn,
    several steps down. An open pull request whose notice a human removed may
    not have an agent started under it, but may still have an answer this
    issue already recorded settled -- so the fact is carried rather than acted
    on where it is learned.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    generation: LateGeneration
    retired_park: str | None = None
    answering: bool = False
    staged_park: _StagedPark | None = None
    displaced_hold: bool = False
    already_published: bool = False
