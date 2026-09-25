# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one validating tick hands between its owners.

Each carries something the owner downstream cannot re-derive. `_ReviewerRun`
holds the worktree the reviewer actually ran in and the round it ran as, so
the approval gate verifies the same checkout that was reviewed and the
feedback comment names the round the human sees on the PR -- and the subject
it was handed, the report included, so an approval is recorded against what
the reviewer read rather than against whatever is current once it returns.
`_ReviewerDecision`
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
reads a non-empty batch as "a human replied". Its mutators are what a route
owes the park it ends: clearing the flags, recording the frozen batch as
consumed through the ordinary pinned settlement, recording ONE answered
control comment and nothing else through the same settlement, and writing
down that a reply has bought a reviewer round the tick may not get to run. `_RequestedChanges` and
`_AwaitingDevAttempt` bracket the fix that follows a verdict: the first
freezes what the CHANGES_REQUESTED route needs, the second reports whether
the resume that ran was cut short by a live pause.

`_dev_fix_run` validates rather than carries. Both fix-disposition entry
points still accept the historical positional call, so it binds one of those
calls to a `_DevFixRun` and raises on an unknown keyword rather than
swallowing a mistyped `after_sha=`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_delivery as _delivery,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.implementing import resume_batch as _resume_batch
from orchestrator.workflow.stages.validating import state as _state
from orchestrator.workflow.state import WorkflowLabel


@dataclass(frozen=True)
class _ReviewerRun:
    wt: Path
    round_n: int
    pr_number: Any
    agent_result: AgentResult
    # The record of what this round's prompt quoted of the issue thread. A
    # reply that bought the round is recorded as read from THIS, never from
    # the batch a park froze for a developer prompt: the two are different
    # reads under different bounds, and a mark taken from the wider one
    # crosses words this reviewer's excerpt cut short.
    delivery: _delivery.PromptDeliverySnapshot
    # The pull request, head, requirements, and report this round's prompt
    # handed the reviewer, which is what an approval of it covers.
    subject: _review_subjects.ReviewSubject


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
    # The remote head this publication was proved ahead of, where the route
    # could take that proof. It is the head the push replaces, and the one the
    # gate is pinned to -- read from the ref the ahead/behind proof was taken
    # against rather than from the pull request afterwards, which is the
    # reading a head somebody moved in between would win.
    #
    # It is what the run began at only where the branch was in sync with its
    # pull request when the run started. A commit an earlier tick left on the
    # branch unpublished breaks that, whether this run committed on top of it
    # or committed nothing at all: the pull request is standing BELOW the head
    # in hand either way, and a lease named from that head would describe a
    # commit the pull request has never carried -- so every tick over such a
    # branch parks unmeasured and the accumulated code never goes out.
    published_head: str = ""
    # What the caller froze about the run, where the run is one this
    # disposition holds to the report contract. Named, the report is recorded
    # and published; unnamed, the run publishes code alone and this road says
    # nothing about a report.
    #
    # Every road that resumes a developer over an OPEN pull request names it:
    # the requirements-drift resume, the awaiting-human resume behind it, and
    # both halves of the reviewer-requested fix round -- the direct one the
    # `changes_requested` arc runs inline, and the resume the fixing handler
    # makes on the far side of a park.
    #
    # It carries the route, and then whatever that road could not leave
    # anywhere else. The requirements revision is the one the RUN was handed:
    # the fingerprint of the read its prompt was built from wherever that road
    # freezes one -- the drift resume and the batch resumes here -- because the
    # report is about the requirements that session saw rather than whatever
    # the issue says by the time the report reaches the pull request. `spends` and `watermarks` are the round, the
    # bookmarks and the readers a handover closes, frozen for the write that
    # settles the report: the one handover with no code in it passes no size
    # gate, so nothing else is left to carry them.
    handed: Any = None

    @property
    def entered_head(self) -> str:
        """The publication head this run's candidate is being pushed over.

        Named to the size gate so a pull request somebody pushed to WHILE the
        agent was out refuses the push instead of being overwritten by work
        built on the head it used to be on.

        The PROVED remote tip answers wherever the route took one, because
        that is the head the push replaces however the candidate came to be:
        a commit this run made, a commit an earlier tick stranded with this
        run committing nothing, and a commit this run made on top of one an
        earlier tick stranded are the same publication from the branch's side.
        Naming it is also what makes a pull request somebody moved between the
        proof and the push refuse rather than be adopted as the lease.

        The head this run BEGAN at answers only where no proof could be taken
        and the run committed -- a fetch that failed, a remote that moved, a
        divergence nothing could read. A fix round ordinarily starts with the
        branch in sync with its pull request, so that head is the publication
        the reviewer just read; where it is not, the gate compares the two and
        refuses, which is the same answer the unreadable proof deserves.
        """
        if not self.after_sha or self.after_sha == self.before_sha:
            return self.published_head
        return self.published_head or self.before_sha


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
        """End the park this context was built on, and what it stood over.

        A requirements edit the park interrupted is answered by the road that
        clears it, so the drift claim goes with the park rather than outliving
        it: left standing past a recovery that published the commit itself, it
        would read the next unrelated park's reply as the edit's continuation.
        The road that MEANS to continue reads the claim before its run, and
        the disposition behind it writes it again where the edit is still
        unanswered.
        """
        self.state.set("awaiting_human", False)
        self.state.set(_state._PARK_REASON, None)
        if self.state.get(_state._OPEN_DRIFT):
            self.state.set(_state._OPEN_DRIFT, None)

    def consume_comments(self) -> None:
        """Record the frozen batch as consumed, forward only.

        Through the batch, so a route that consumes without a dev run -- the
        reviewer respawn once its round has run, a collapse the reply
        releases -- settles exactly the batch it handled and no other cursor.
        """
        self.batch.settle()

    def consume_command(self, command) -> None:
        """Record THIS command's words as read, and nothing else at all.

        For a road that ANSWERED a control comment on the thread rather than
        handing it to anybody: the command may not come back forever, since
        the reply to it is already posted, but nothing else in the batch
        reached an agent. Not the requirements it arrived beside, which stay
        outstanding for the prompt that finally carries them -- and not the
        guidance somebody wrote beside it either, which is why every other
        comment goes in as an omission rather than being left out. Left out,
        a mark would cross them; held in, one written below the command stops
        the mark short of it and the words stay owed to a reader.

        What is marked delivered is the whole COMMENT, so a caller may only
        hand one whose whole body is the command
        (`awaiting._is_bare_command`). A command written inside a comment of
        guidance would be crossed with that guidance, which no prompt on this
        road has carried and the bounded round a grant buys may never quote.
        """
        answered = getattr(command, "id", None)
        _delivery.settle_delivery(
            self.state,
            replace(
                self.batch.delivery,
                requirements_revision=None,
                entries=tuple(
                    entry if entry.id == answered or entry.is_filtered
                    else entry.with_status(_delivery.STATUS_OMITTED)
                    for entry in self.batch.delivery.entries
                ),
            ),
        )

    def already_answered(self, command) -> bool:
        """Whether a post of ours already stands above this control comment.

        What keeps an answered command from coming back forever is normally
        the mark that crossed it, but a command standing above guidance
        nobody delivered -- or written inside a comment of it -- is answered
        with the mark held below both. Our own posts are the other record
        that it WAS answered: the id ledger names them, and one written after
        the command is this road's reply to it.

        Asked by the REFUSAL, whose own write follows the post it guards, so
        the post is a record of a decision this road really took. The grant
        cannot ask it: its notice goes out ahead of a reviewer whose run may
        be refused, and every later post of ours -- the run-limit park's own
        sentence, the receipt an agent-run grant earns -- would then read as
        the answer to a command still waiting to be honored.

        By id rather than by the marker our posts carry, because the question
        is which comment a post of ours came after -- a marker says only that
        we posted something, and the park's own notice carries one from
        before the command was written. A newer command is above every
        answer, so a corrected one is still answered; and while this park
        stands, the road that answers commands is the only one posting.
        """
        spoken = getattr(command, "id", 0)
        ours = frozenset(_comments._orchestrator_ids(self.state))
        return any(
            seen.id in ours and seen.id > spoken for seen in self.batch.read
        )

    def bought_a_round(self) -> None:
        """Write down that this reply bought a reviewer round.

        The round may not run on this tick: a report still owed holds the
        reviewer, and the run circuit can turn the launch away. The clear
        goes out regardless, so without this the next tick reads a park-free
        issue whose requirements the reply itself has moved, and hands a
        reviewer's retry to the developer. It also names the reply as the
        round's to settle, wherever that round finally runs.
        """
        self.state.set(
            _state._REVIEWER_OWES_A_ROUND, _state._ROUND_BOUGHT_BY_A_REPLY,
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
        "after_sha", "stage", "spends", "published_head", "handed",
    }
    if unknown:
        raise TypeError(f"unexpected fix-result option(s): {sorted(unknown)!r}")
    return state, _DevFixRun(
        worktree, agent_result, before_sha,
        fields.get("after_sha"), fields.get("stage"),
        fields.get("spends"), fields.get("published_head") or "",
        fields.get("handed"),
    )
