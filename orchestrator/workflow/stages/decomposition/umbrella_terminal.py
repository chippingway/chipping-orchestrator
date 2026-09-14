# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Umbrella resolution receipts, cycle retirement, and final issue closure.

Published late splits deduplicate their resolution by cycle and generation.
Retirement preserves outstanding resource and consumer obligations, and
closure follows the done label.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    issue_usage as _issue_usage,
)
from orchestrator.workflow.late_split import endings as _endings, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# Stamped into the sentence a resolved umbrella says, so a terminal refused
# after that sentence went out does not say it again on the next poll. Scoped
# to the exact cycle and generation, because the thread outlives both: an
# operator who takes a settled cancellation's terminal off starts a fresh
# cycle on the same issue, and a receipt naming only the issue would silence
# the sentence that cycle owes its humans. An HTML comment, so it is
# invisible in the rendered thread.
_RESOLVED_MARKER = (
    "<!--orchestrator-umbrella-resolved:issue={issue}"
    ":cycle={cycle}:generation={generation}-->"
)


def _retired_cycle(state: PinnedState) -> LateGeneration:
    """Drop the identity of a cycle that finished, keeping what it recorded.

    The two ledgers are the only thing carried across, exactly as the
    authorized settlement's own retirement carries them: an obligation does
    not stop being owed because the identity written beside it was cleared,
    and the receipts naming the children this split made are what a restart
    reads. What goes is the cycle a close would have ended -- which is the
    whole point of doing it HERE, one write before the terminal label: past
    this there is no live cycle under `done` for anything to have to find.

    The generation it dropped travels back, because the write that makes it
    durable is a request and the barrier behind that request needs something
    to put back.
    """
    live = _late_state.read_late_generation(state)
    _late_state.write_late_generation(state, LateGeneration(
        obligations=live.obligations,
    ))
    if live.is_present:
        _endings.record_retired_cycle(state, live.cycle_id)
    return live


def _resolution_said(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Say once that every child resolved, with what the issue cost.

    Gated on the stamp, which is what a resumed terminal has instead of
    memory: a pass that died between this comment and the write that records
    it says it again, and one that died after that write does not. That is
    every umbrella there has ever been, and it stays exactly that.

    A post-publication split's is gated on the THREAD as well, and only that
    one. What the second gate covers is a window only that road has: the
    barrier immediately in front of the retirement write can refuse a terminal
    whose sentence has already gone out, and an umbrella held on a reopened
    pull request would otherwise repeat itself on every poll for as long as a
    human took to settle it. Nothing refuses the others there, so none of them
    pays for a comment listing or carries a receipt nothing would read.

    Walked whole rather than from a watermark, for the reason the split's own
    announcement is: this post moves every watermark the mode keeps past
    itself, so a bounded scan would start above the very comment it looks for.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.publication.is_complete:
        _comments._post_issue_comment(
            gh, issue, state, _resolution_body(state),
        )
        return
    marker = _resolved_marker(issue, generation)
    if _resolution_on_thread(gh, issue, marker):
        return
    _comments._post_issue_comment(
        gh, issue, state, f"{_resolution_body(state)}\n\n{marker}",
    )


def _resolution_body(state: PinnedState) -> str:
    """The sentence a resolved umbrella owes its thread, and what it cost."""
    close_body = ":white_check_mark: all children resolved; closing umbrella issue."
    verdict = _issue_usage._format_issue_usage_verdict(state)
    if not verdict:
        return close_body
    return f"{close_body}\n\n{verdict}"


def _resolved_marker(issue: Issue, generation: LateGeneration) -> str:
    """The receipt this cycle's resolution sentence carries."""
    return _RESOLVED_MARKER.format(
        issue=issue.number,
        cycle=generation.cycle_id,
        generation=generation.generation,
    )


def _resolution_on_thread(
    gh: GitHubClient, issue: Issue, marker: str,
) -> bool:
    """Whether THIS cycle has already said its children all resolved.

    Ours, because an HTML comment is invisible in the rendered thread and
    anybody could otherwise post the marker that silences the one sentence
    saying this issue is finished.
    """
    return _github_comments.carries_own_marker(
        gh.comments_after(issue, None),
        marker,
        bot_login=getattr(gh, "_bot_login", None),
    )


def _finished_umbrella(gh: GitHubClient, issue: Issue) -> None:
    """Hand a resolved umbrella its terminal label and close it.

    Both are asked of a record that already says the terminal is due, so
    either can be repeated: a pass that died before the label leaves an owner
    the sweep and the umbrella poll both finish from here, and one that died
    before the close leaves an open `done` issue a human can see.
    """
    gh.set_workflow_label(issue, WorkflowLabel.DONE)
    _closed_umbrella(issue)


def _closed_umbrella(issue: Issue) -> None:
    """Close the issue an umbrella's terminal has just resolved."""
    try:
        issue.edit(state="closed")
    except Exception:
        log.exception(
            "issue=#%s could not close umbrella after children done",
            issue.number,
        )
