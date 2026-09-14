# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one discussion tick hands between its owners.

`_DiscussionRun` bundles the four handles a tick is driven by so the owners
never re-read pinned state: the session id the spawn retains, the usage the
assessment folds, and the park the routing publishes all have to land on the
one `state` object the handler read at the top, or the single write at the end
drops whichever mutation was made against a second copy.

`_DiscussionSession` is the agent identity one round runs under, carried as the
full configured spec rather than a bare backend so that what is pinned on the
issue and what the command line actually was cannot disagree, and beside it the
conversation that spec is mid-way through. The two travel together because a
resume needs both and neither survives being re-derived: the spec says which
backend the session id is even valid on, so reading one from pinned state and
the other from the current config would hand a live conversation to a CLI that
never opened it. It is a plain carrier because which identity applies is a
property of the issue, not of the class: `run` reads the pinned one back when
there is one, and only an issue that has never spawned falls through to the
current config -- which is also the only issue whose session id is absent
rather than merely unreturned.

`_DiscussionRound` carries the finished run beside the HEAD the checkout was
sitting on when the round opened, because "did this agent commit?" is not a
question the worktree can answer on its own: the issue may have arrived here
from a PR stage with commits already on its branch, and a base-relative probe
would read those as this round's work.

`_DiscussionPrompt` pairs what a round is asked with the replies asking it has
therefore consumed, because the two are one decision made once. A full-context
round reads the thread to build its text and the ceiling it may record from the
same snapshot; splitting them would let a comment land between two reads, reach
the agent through one, and stay above the watermark set by the other -- and a
stage that reads no comment twice would then send it again next tick.

`_DiscussionOutcome` is what the assessment decided, so the routing publishes
it without re-deriving anything: the park to post, plus the response or the
dirty paths that park's comment quotes.

`_PlanArtifact` is one read of what the branch is carrying, taken before
anything is pushed, and it travels whole because the answer and the reasons for
it are needed together: `publishable` decides, and the same paths are what the
refusal quotes back to the human. The checkout and the branch ride with it for
the same reason the probes were run against them -- a publication pushes the
tree it inspected, and re-deriving either between the check and the push would
mean the two could name different things.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents import AgentResult
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


@dataclass(frozen=True)
class _DiscussionRun:
    """The stable inputs one discussion-stage tick is driven by."""

    gh: GitHubClient
    spec: config.RepoSpec
    issue: Issue
    state: PinnedState

    @classmethod
    def start(
        cls, gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
    ) -> _DiscussionRun:
        return cls(gh=gh, spec=spec, issue=issue, state=gh.read_pinned_state(issue))


@dataclass(frozen=True)
class _DiscussionSession:
    """The agent identity one discussion round runs and is recorded under."""

    agent_spec: str
    backend: str
    extra_args: tuple[str, ...]
    session_id: str | None


@dataclass(frozen=True)
class _DiscussionRound:
    """One finished agent round and the checkout it started from."""

    agent_result: AgentResult
    head_before: str


@dataclass(frozen=True)
class _DiscussionPrompt:
    """What one round is asked, and the replies that asking has consumed."""

    text: str
    consumed: tuple


@dataclass(frozen=True)
class _CheckoutReading:
    """What one tick found in the checkout before it decided anything.

    The pair travels together because neither half is worth acting on alone:
    `moved` is what a publication follows, and it is only ever true of a
    `state` that could be read -- an unresolvable `HEAD` compares unequal to
    every anchor, so a checkout nothing could be established about would
    otherwise be the one most likely to answer "a round committed here".
    """

    state: _WorktreeStatus
    moved: bool = False


@dataclass(frozen=True)
class _DiscussionOutcome:
    """The park a finished run earned, and what its comment quotes."""

    park_reason: str | None
    response: str = ""
    dirty_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PlanArtifact:
    """What the branch is carrying, judged against what may be published.

    Every field is filled at the one site that probes for it -- none of them
    defaults -- because each is a way the publication can be wrong and a
    default would be this stage deciding one of them without asking.
    """

    branch: str
    worktree: Path
    plan_path: str
    head_sha: str
    head_attached: bool
    base_sha: str
    tree_readable: bool
    plan_in_head: bool
    dirty_files: tuple[str, ...]
    changed_paths: tuple[str, ...]

    @property
    def publishable(self) -> bool:
        """True when the branch is the plan file and nothing besides.

        Seven conditions, and each one is a way the branch can look right and
        not be. The tip has to have been read at all, since it is the commit
        the push names -- publishing "whatever HEAD is by then" is exactly what
        a validated artifact must not do. HEAD also has to BE the branch: a
        commit made on a detached HEAD, or on some other ref, is one the push
        would send to `refs/heads/<branch>` while the local branch stayed where
        it was -- and everything downstream reads that branch. The records
        would name a commit its own ref does not carry, the relabel guard would
        convict the stale tip of being unreviewed work, and a checkout rebuilt
        from that ref would come back without the plan. Nothing here advances a
        ref an agent left behind, so what is published is what the branch is
        on. The base has to have been read too,
        and from the remote: a diff is only as good as the commit it measures
        from, and the local ref that names the base is one the agent's own
        worktree could have moved. The tree has to have been READ, since an
        unreadable one is not a clean one and a push may not rest on a probe
        that never ran. It has to be clean, because uncommitted work beside the
        plan is work the PR would not show. The base-relative diff has to be exactly the one path,
        because a second plan, a missing one, or any code or configuration
        change is a round that did something other than write down what was
        agreed. And the plan has to actually BE in HEAD: deleting a plan the
        base branch already carries changes exactly that path too, and
        publishing a deletion as the agreed design is the same mistake as
        publishing no plan at all.
        """
        return all((
            self.head_sha,
            self.head_attached,
            self.base_sha,
            self.tree_readable,
            self.plan_in_head,
            not self.dirty_files,
            self.changed_paths == (self.plan_path,),
        ))
