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
one already on the branch -- and an optional `after_sha` for the caller that
has already read it.

`_AwaitingValidation` is the awaiting-human context: it snapshots the park
reason and the trusted comments that arrived since the last consumed one, and
its two mutators are the pair every route through that park owes -- clearing
the flags, and ratcheting `last_action_comment_id` past the comments it just
fed to an agent. Reading both once at build time is what keeps the three
decision helpers agreeing on the same batch. The orchestrator's own comments
are dropped from that batch by recorded id AND by the hidden body marker,
because every helper here reads a non-empty batch as "a human replied": a
comment this process posted and then failed to record -- the pinned write that
would have named it never landed -- is still ours, and the marker is what says
so when the id ledger cannot. `_RequestedChanges` and
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
from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import comments as _comments
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
    comments: list

    @classmethod
    def build(
        cls, gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
    ) -> _AwaitingValidation:
        # Filtered by recorded id AND by `_ORCH_COMMENT_MARKER`, the same
        # pair `_rescan_fixing_feedback` uses and for the same two reasons:
        # the id ledger is capped and evicts on long-lived issues, and a
        # comment posted by a tick whose pinned write then failed was never
        # recorded at all. Either one left in reads as a human reply.
        orchestrator_ids = _comments._orchestrator_ids(state)
        unread = [
            issue_comment
            for issue_comment in gh.comments_after(
                issue, state.get("last_action_comment_id"),
            )
            if issue_comment.id not in orchestrator_ids
            and _comments._ORCH_COMMENT_MARKER not in (issue_comment.body or "")
        ]
        return cls(
            gh,
            spec,
            issue,
            state,
            state.get(_state._PARK_REASON),
            _github_comments.filter_trusted(unread),
        )

    def clear_park(self) -> None:
        self.state.set("awaiting_human", False)
        self.state.set(_state._PARK_REASON, None)

    def consume_comments(self) -> None:
        self.state.set(
            "last_action_comment_id",
            max(comment.id for comment in self.comments),
        )


@dataclass(frozen=True)
class _AwaitingDevAttempt:
    run: _DevFixRun
    paused: bool


def _dev_fix_run(context_args: tuple, fields: dict) -> tuple[_pinned_state.PinnedState, _DevFixRun]:
    if len(context_args) != 4:
        raise TypeError("expected state, worktree, result, and before_sha")
    state, worktree, agent_result, before_sha = context_args
    unknown = set(fields) - {
        "after_sha", "stage", "spends", "stranded_head",
    }
    if unknown:
        raise TypeError(f"unexpected fix-result option(s): {sorted(unknown)!r}")
    return state, _DevFixRun(
        worktree, agent_result, before_sha,
        fields.get("after_sha"), fields.get("stage"),
        fields.get("spends"), fields.get("stranded_head") or "",
    )
