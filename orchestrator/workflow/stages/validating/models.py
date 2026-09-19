# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one validating tick hands between its owners.

Each carries something the owner downstream cannot re-derive. `_ReviewerRun`
holds the worktree the reviewer actually ran in and the round it ran as, so
the approval gate verifies the same checkout that was reviewed and the
feedback comment names the round the human sees on the PR. `_ReviewerDecision`
folds the parsed verdict together with the run, and its `feedback` falls back
to the agent's last message so a reviewer that put its reasoning above the
VERDICT line still reaches the dev. `_DevFixRun` carries `before_sha` -- the
pre-agent HEAD is the only thing that tells a commit this run produced from
one already on the branch -- an optional `after_sha` for the caller that
has already read it, and, for a requirements-drift resume, what that resume
was handed, which its report is stamped with.

`_AwaitingValidation` is the awaiting-human context: it snapshots the park
reason and the one frozen reply batch every route through that park reads --
`implementing/resume_batch.py`'s, so the batch the decisions are made from is
the batch the dev resume behind them delivers and settles. The orchestrator's
own comments are out of it by recorded id, and a body carrying the hidden
marker that no id vouches for is out beside them, because every helper here
reads a non-empty batch as "a human replied". Its two mutators are the pair
every route owes: clearing the flags, and recording the frozen batch as
consumed through the ordinary pinned settlement. `_RequestedChanges` and
`_AwaitingDevAttempt` bracket the fix that follows a verdict: the first
freezes what the CHANGES_REQUESTED route needs, the second reports whether
the resume that ran was cut short by a live pause.

`_dev_fix_run` validates rather than carries. Both fix-disposition entry
points still accept the historical positional call, so it binds one of those
calls to a `_DevFixRun` and raises on an unknown keyword rather than
swallowing a mistyped `after_sha=`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.stages.implementing import resume_batch as _resume_batch
from orchestrator.workflow.stages.validating import state as _state
from orchestrator.workflow.state import WorkflowLabel


@dataclass(frozen=True)
class _ReviewerRun:
    wt: Path
    round_n: int
    pr_number: Any
    agent_result: AgentResult


@dataclass(frozen=True)
class _ReviewerDecision:
    run: _ReviewerRun
    verdict: str
    body: str

    @property
    def feedback(self) -> str:
        return (
            self.body.strip()
            or (self.run.agent_result.last_message or "").strip()
        )


@dataclass(frozen=True)
class _DevFixRun:
    worktree: Path
    agent_result: AgentResult
    before_sha: str
    after_sha: str | None = None
    # The state this run belongs to, where the caller relabelled the issue
    # remotely in the same tick. Named rather than read back, because the
    # size gate reading the label off an issue object the relabel did not go
    # through would freeze the state the issue has LEFT -- and a settled
    # adjudication continues at whatever the record names. The reviewer's
    # `CHANGES_REQUESTED` route is the one that flips before it publishes;
    # every other reaches this with the label already current and names none.
    stage: WorkflowLabel | None = None
    # The round bookkeeping this route owes if the size gate HOLDS the fix.
    # The hold relabels to the adjudication, so a caller that counted after
    # the call would lose the count to a crash in that window -- and no later
    # tick counts it, because the settlement pushes the accepted commit itself
    # and the resumed route finds nothing left to publish. Handed in, it rides
    # the gate's own durable write, ahead of the label it moves.
    spends: Any = None
    # The remote head a STRANDED publication was proved ahead of, where this
    # run committed nothing and what is being published is a commit an earlier
    # tick left on the branch. It is the head that push replaces, and the one
    # the gate is pinned to -- read from the ref the ahead/behind proof was
    # taken against rather than from the pull request afterwards, which is the
    # reading a head somebody moved in between would win.
    stranded_head: str = ""
    # The route and requirements revision a requirements-drift resume was
    # handed, where the run is one. Named, the disposition holds the run to the
    # report contract and publishes what it reported; the revision is the
    # snapshot the drift check took before the spawn, because the report is
    # about the requirements that session saw rather than whatever the issue
    # says by the time the report reaches the pull request. Every other fix
    # route names none and publishes code alone.
    handed: Any = None

    @property
    def entered_head(self) -> str:
        """The publication head this run's own commit was made on top of.

        Named to the size gate so a pull request somebody pushed to WHILE the
        agent was out refuses the push instead of being overwritten by work
        built on the head it used to be on. A fix round starts with the branch
        in sync with its pull request -- the reviewer just read that head --
        so the head this run began at is the head the publication was standing
        on, and the gate compares the two rather than adopting whichever one
        it happens to read afterwards.

        Where this run committed nothing and what is being published is a
        commit an earlier tick stranded on the branch, the head is the remote
        tip that publication was proved ahead of: the branch this push
        replaces is that one, and naming it is what makes a pull request
        somebody moved between the proof and the push refuse rather than be
        adopted as the lease.
        """
        if not self.after_sha or self.after_sha == self.before_sha:
            return self.stranded_head
        return self.before_sha


@dataclass(frozen=True)
class _RequestedChanges:
    gh: _client.GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: _pinned_state.PinnedState
    decision: _ReviewerDecision


@dataclass(frozen=True)
class _AwaitingValidation:
    gh: _client.GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: _pinned_state.PinnedState
    park_reason: Any
    batch: _resume_batch._ReplyBatch

    @classmethod
    def build(
        cls, gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
    ) -> _AwaitingValidation:
        return cls(
            gh,
            spec,
            issue,
            state,
            state.get(_state._PARK_REASON),
            _resume_batch._freeze(gh, issue, state),
        )

    @property
    def comments(self) -> tuple:
        """The fresh trusted replies, which is what "a human replied" means."""
        return self.batch.comments

    def clear_park(self) -> None:
        self.state.set("awaiting_human", False)
        self.state.set(_state._PARK_REASON, None)

    def consume_comments(self) -> None:
        """Record the frozen batch as consumed, forward only.

        Through the batch, so a route that consumes without a dev run -- the
        review-cap command, the reviewer respawn, a collapse the reply
        releases -- settles exactly the batch it handled and no other cursor.
        """
        self.batch.settle()


@dataclass(frozen=True)
class _AwaitingDevAttempt:
    run: _DevFixRun
    paused: bool


def _dev_fix_run(context_args: tuple, fields: dict) -> tuple[_pinned_state.PinnedState, _DevFixRun]:
    if len(context_args) != 4:
        raise TypeError("expected state, worktree, result, and before_sha")
    state, worktree, agent_result, before_sha = context_args
    unknown = set(fields) - {
        "after_sha", "stage", "spends", "stranded_head", "handed",
    }
    if unknown:
        raise TypeError(f"unexpected fix-result option(s): {sorted(unknown)!r}")
    return state, _DevFixRun(
        worktree, agent_result, before_sha,
        fields.get("after_sha"), fields.get("stage"),
        fields.get("spends"), fields.get("stranded_head") or "",
        fields.get("handed"),
    )
