# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frozen records one implementing tick hands between its owners.

Each one exists because a value has to survive a boundary the spawn cannot see
across. `_PreparedDevRun` carries `before_sha` -- the pre-agent HEAD -- from
whoever started the run to whoever disposes it, because that watermark is the
only thing that tells a commit produced by THIS run from one already on the
branch, and the record of what a fresh spawn's prompt quoted, for the road
that has a requirements edit to settle against it. `_AgentWork` and `_PRWork` carry the worktree (and, once pushed, the
branch) so the publication owner never re-derives either. `_DevSession` and
`_DevResumePlan` freeze the locked spec, backend, args, and session id together
with the fresh-spawn decision, so a resume cannot half-rotate a session.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine.prompt_delivery import PromptDeliverySnapshot

# What one fresh spawn answers with: the run, the live-pause decision read
# after it, and the record of the conversation its prompt quoted.
_SpawnedRun = tuple[AgentResult, bool, PromptDeliverySnapshot]


@dataclass(frozen=True)
class _PreparedDevRun:
    agent_result: AgentResult
    before_sha: str | None
    paused: bool
    worktree: Path
    # True when no agent ran and the result was synthesized from commits the
    # worktree already held. The disposition cannot infer this from the tree:
    # a recovered run publishes work whose HEAD moved on some earlier tick,
    # which looks exactly like a live run that answered without committing.
    recovered: bool = False
    # What a FRESH spawn's prompt quoted of the issue thread, for the road
    # that has something to settle against it. None everywhere else: a resume
    # settles the frozen batch it was given, and a recovered publication
    # quoted nobody.
    delivery: PromptDeliverySnapshot | None = None

    @classmethod
    def from_spawn(
        cls, spawned: _SpawnedRun, before_sha: str | None, worktree: Path,
    ) -> _PreparedDevRun:
        """One fresh spawn's result, pause decision, and delivered prompt."""
        agent_result, paused, delivery = spawned
        return cls(
            agent_result, before_sha, paused, worktree, delivery=delivery,
        )


@dataclass(frozen=True)
class _AgentWork:
    agent_result: AgentResult
    worktree: Path


@dataclass(frozen=True)
class _RecoveredWork(_AgentWork):
    """Committed work a RECOVERY is reconciling, not a run's fresh output.

    A distinct type rather than a flag beside the worktree, because it is a
    claim about the TICK rather than about the checkout -- and the checkout
    cannot say it. No developer ran on the paths that build one: they answer a
    reading a previous tick recorded, so a head that has moved is not fresh
    output to be measured in the recorded candidate's place, and the
    `DECOMPOSE` bypass would be answering a question the gate already asked.
    Everything else about it is ordinary committed work, which is why it IS
    one rather than merely resembling one.

    `candidate_sha` is the commit the recovery PROVED the checkout on before
    it built this, and it travels for the reason the approved work below
    carries one: the gate reads the head again for itself, and the worktree is
    writable in between. A commit landing in that window is a different
    candidate -- measured there, pushed there, and recorded there -- while the
    reading that licensed the recovery was about another one. Named, the gate
    refuses it before anything is persisted or pushed. Empty where the caller
    proved nothing, which leaves the head this gate reads as the whole of the
    answer.
    """

    candidate_sha: str = ""


@dataclass(frozen=True)
class _ApprovedWork(_AgentWork):
    """A committed candidate the size gate let through, and which commit it is.

    The SHA travels because the next step is a PUSH and the gate's answer was
    about one object id: it proved that commit, measured that commit, and
    recorded that commit. `HEAD` between the reading and the write is not
    necessarily the same commit -- another tick, an operator, or a descendant
    the timeout cleanup raced can move it -- so a publication that carried
    only permission would publish work no measurement ever saw. Empty where
    the GATE proved nothing, which is a candidate the switch kept out of it --
    and there the publication resolves the checkout's own head instead, so
    what goes out is still named against one commit.
    """

    candidate_sha: str = ""
    # The pull request the gate PROVED is already standing on that commit,
    # where it proved one. The barrier before the push re-reads whichever pull
    # request the push would land on, and where the number was proved rather
    # than read off the record there is nothing for the `discussion` plan
    # carve-out to be about: a proof is that the branch stands on the
    # candidate, which no plan publication can produce. The push it licenses
    # moves nothing, so the number also pins both halves of the bookkeeping
    # behind it -- the lease, which is the candidate itself, and the pull
    # request the relabel hands on. Zero is every caller that proved none, and
    # there the record's own `pr_number` is what gets re-read.
    delivered_pr: int = 0


@dataclass(frozen=True)
class _PRWork(_AgentWork):
    branch: str
    # The pull request this publication is finishing the bookkeeping for,
    # where a reading proved the branch is already standing on the commit.
    # Named rather than looked up again, because the answer that admitted the
    # candidate proved THAT pull request: a second lookup a moment later can
    # find it closed and open another over the same work.
    delivered_pr: int = 0
    # The commit that pull request was proved standing on, which is what the
    # number is only half of: the bookkeeping writes a receipt naming this
    # commit and hands a reviewer that publication, so both have to still be
    # true together. A head somebody moved in the window leaves the receipt
    # naming work the branch no longer carries.
    delivered_sha: str = ""


@dataclass(frozen=True)
class _DevSession:
    spec: str
    backend: str
    extra_args: tuple[str, ...]
    session_id: str | None


@dataclass(frozen=True)
class _DevResumePlan:
    session: _DevSession
    fresh_spawn: bool
    resume_count: int
