# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one conflict tick hands between its owners.

`_ConflictContext` is the tick itself. The rebase loop threads it through eight
owners, and bundling the four handles keeps each of them from re-reading pinned
state: the `conflict_round` bump, the label flip, and the audit event all have
to land on the same `state` object the handler read at the top, or a park and
the write that must accompany it would disagree.

`_WorktreeSync` is the worktree measured against the freshly fetched remote PR
head, and the three shapes it can take are the whole reconciliation decision --
in sync, ahead (a prior tick committed but never pushed), or behind (stale or
diverged, and refused).

`_DivergeDecision` is how the diverged-worktree guard answers without the
caller re-deriving it: `parked` says the tick is over, and `publish_lease`
carries the exact PR head validated as orchestrator-produced so the force-push
below leases against that SHA rather than whatever `ls-remote` reports later.

`_ConflictResumeRun` carries what a finished dev resume cannot re-derive: the
worktree it actually ran in (the resume may have re-created it), the result,
whether an operator paused mid-run, and -- on the body-edit road -- the record
of exactly what its prompt quoted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import prompt_delivery as _delivery


@dataclass(frozen=True)
class _ConflictContext:
    """The per-tick `resolving_conflict` handles, bundled so the rebase-loop
    helpers thread them as a single value instead of four positional
    arguments (mirrors fixing's `_FixingContext`)."""
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState


@dataclass(frozen=True)
class _WorktreeSync:
    """A PR worktree measured against its remote branch tip: the worktree
    path, the branch name, and how far HEAD is ahead / behind the freshly
    fetched `<remote>/<branch>` head."""
    worktree: Path
    branch: str
    ahead: int
    behind: int
    # The commit that fetched ref was AT, read from the same ref the counts
    # above were taken against. It travels with them because the counts are a
    # claim about it and nothing downstream can re-derive it: a push proved
    # against "ahead and not behind" is pinned to this exact head, and a
    # caller that dropped it would leave the gate reading the pull request
    # for itself and adopting whatever landed in between. Empty is a tip
    # nothing could read, which every reader treats as no head established.
    fetched_tip: str = ""


@dataclass(frozen=True)
class _DivergeDecision:
    """Verdict of the diverged-worktree guard: whether the tick parked, plus
    the force-publish lease pinned to a validated orchestrator-produced PR
    head when an already-rebased worktree may be force-published instead."""
    parked: bool
    publish_lease: str | None = None


@dataclass(frozen=True)
class _ConflictResumeRun:
    """The outputs of one locked dev resume in the rebase loop: the worktree
    the agent ran in (`_resume_dev_with_text` may re-create it), the agent
    result, and whether an operator paused mid-run.

    `delivered` is the record the body-edit road freezes with its prompt and
    settles once the run is back -- the comments that prompt quoted and the
    requirements revision the read they came from fingerprints to. It rides
    the run because it may not be re-derived after it: the thread moves while
    an agent is out, and a mark taken off the one it comes back to crosses
    replies nobody delivered. None on the two roads that freeze no record: the
    fresh conflict quotes no conversation at all, and a park's reply is
    consumed by the road that read it.
    """
    worktree: Path
    dev_result: AgentResult
    paused: bool
    delivered: _delivery.PromptDeliverySnapshot | None = None


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
