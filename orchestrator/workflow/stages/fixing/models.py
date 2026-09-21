# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one fixing tick hands between its owners.

`_FixingContext` is the tick itself, and the PR inside it is the live one the
preflight fetched once at the top: re-reading it per owner would let the
terminal check, the drift comparison against `pr.head.sha`, and the conflict
notice come from three different fetches of a PR a human may be closing.

`_FixingFeedback` keeps all four surfaces apart and derives the two merged
readings from them, because the consumers need opposite shapes: the prompt
reads `all_items` in one order, while the settlement has to advance each
reader only to the max id consumed on the surface that reader owns. The issue
thread is held apart from the PR conversation for the settlement's sake --
GitHub numbers the two from one IssueComment id space, but only the thread is
what `last_action_comment_id` records as delivered, so a batch that had merged
them could not say which half that field may be advanced over.

`_ParkedFixingDecision` is how a parked tick answers without the caller having
to re-derive it: `stop` says the tick is fully handled, and `replay_batch`
carries the preserved feedback an accepted `/orchestrator continue` resumes on
instead of the per-tick rescan. It is a `_FixingFeedback` rather than one flat
list for the reason the rescan is: a replay is delivered, so it is settled --
and a batch that had flattened the reconstruction could not say which reader
owns which half of it, leaving the issue thread's own boundary behind on
exactly the replay that quoted it.

`_FixingResumeRun` carries what the disposition cannot re-derive after the run:
the worktree it actually ran in (the resolve may have recreated it), whether an
operator paused mid-run, the HEAD on both sides -- the only thing that
tells a pushed fix from a no-commit acknowledgement -- and whether the run
finished on a report, which three owners branch on and none of them may parse
for itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


@dataclass(frozen=True)
class _FixingFeedback:
    """One rescan, held per surface, with the merged readings derived.

    The four lists are what the settlement is taken from, one reader each.
    `issue_space` and `all_items` are views over them rather than members, so
    the batch a prompt quotes and the batch a settlement records cannot part
    company the way two separately-built lists can.
    """

    issue_thread: list
    pr_conversation: list
    review_comments: list
    review_summaries: list

    @property
    def issue_space(self) -> list:
        """Both IssueComment surfaces, in the one id order GitHub gave them."""
        return sorted(
            self.issue_thread + self.pr_conversation,
            key=lambda feedback_item: feedback_item.id,
        )

    @property
    def all_items(self) -> list:
        """Every unread item, in the order the dev prompt quotes them."""
        return (
            self.issue_space + self.review_comments + self.review_summaries
        )

    def merged_with(self, other: _FixingFeedback) -> _FixingFeedback:
        """Two readings of one round, joined on the surface each was read from.

        What a `/orchestrator continue` delivers is the preserved batch the
        park never answered AND the fresh feedback that arrived with the
        command, and what it consumed is both -- so they are joined per
        surface rather than concatenated. Flattened, the reconstruction's
        issue-thread half would settle whatever reader the merged list was
        attributed to, which is how the issue-action boundary gets left behind
        on the one road that replays across it.

        Each item once, in the id order GitHub gave them: the two readings
        overlap by construction, since a bookmarked comment still above the
        readers is in the reconstruction and in the rescan alike, and a
        prompt that quoted it twice would ask for it to be answered twice.
        """
        return _FixingFeedback(
            issue_thread=_joined(self.issue_thread, other.issue_thread),
            pr_conversation=_joined(
                self.pr_conversation, other.pr_conversation,
            ),
            review_comments=_joined(
                self.review_comments, other.review_comments,
            ),
            review_summaries=_joined(
                self.review_summaries, other.review_summaries,
            ),
        )


def _joined(read: list, also_read: list) -> list:
    """One surface's two readings, each item once and in id order."""
    by_id = {
        feedback_item.id: feedback_item
        for feedback_item in (*read, *also_read)
    }
    return [by_id[feedback_id] for feedback_id in sorted(by_id)]


def _no_fixing_feedback() -> _FixingFeedback:
    """The reading that found nothing, on every surface."""
    return _FixingFeedback(
        issue_thread=[],
        pr_conversation=[],
        review_comments=[],
        review_summaries=[],
    )


@dataclass(frozen=True)
class _ParkedFixingDecision:
    stop: bool
    replay_batch: _FixingFeedback | None = None


@dataclass(frozen=True)
class _StrandedPublication:
    """What the no-feedback bounce did with a commit an earlier run stranded.

    Three answers rather than two, because the bounce owes a different thing
    to each. A push earns the reviewer round the fresh head spends. Nothing to
    push is the ordinary case and costs no round. And HELD is neither: the
    size gate has already handed the issue to the adjudication under
    `workflow:decomposing`, so the bounce may not relabel over it or spend a
    round on a head the reviewer is not going to see.
    """

    pushed: bool = False
    held: bool = False


@dataclass(frozen=True)
class _FixingContext:
    """The per-tick `fixing` invocation handles, bundled so the parked-dispatch,
    validating-recovery, continue-command, resume, and reconcile helpers thread
    them as a single value instead of five positional arguments (mirrors
    validating's `_RequestedChanges`). `pr` is the live PR the preflight
    fetched this tick; not every consumer reads it.
    """
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    pr: Any


@dataclass(frozen=True)
class _FixingResumeRun:
    """The outcome of one locked dev resume: the worktree it ran in, the agent
    result, whether an operator paused mid-run, and the HEAD before/after.

    `reported` is the one reading of that result several owners here branch on
    -- the ACK fast path, the fork that withholds the delivery settlement, and
    the road the disposition's answer is read against -- so it is taken once,
    where the run is built, rather than by each of them parsing the message
    again and risking a different answer from one.
    """
    worktree: Path
    dev_result: AgentResult
    paused: bool
    before_sha: str | None
    after_sha: str | None
    reported: bool = False
