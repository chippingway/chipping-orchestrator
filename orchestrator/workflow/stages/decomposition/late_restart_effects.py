# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deliver restart notices and establish the fresh workflow label.

The cycle receipt deduplicates announcements after a crash. A label put
on by another writer is reapplied so its provenance separates the restart
from the predecessor terminal.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    comments as _comments,
)
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")


# Stamped on the notice one restart leaves on the issue thread. Scoped to the
# cycle the restart MINTS, because that is the episode the notice announces: a
# second restart of the same issue is a different cycle and owes its own
# sentence, and an unscoped marker would read the first one's notice as the
# second's. An HTML comment, so it is invisible in the rendered thread.
_RESTART_MARKER = (
    "<!--orchestrator-late-restart:issue={issue}:cycle={cycle}-->"
)

_RESTART_NOTICE = (
    ":arrows_counterclockwise: **Restarting.** `rejected` was removed from "
    "this issue, which is what authorizes a fresh attempt after late-split "
    "cycle {predecessor} was cancelled. Cycle {cycle} starts from nothing on "
    "`{label}`.\n\nThe cancelled cycle carries over no session, pull request, "
    "branch, child issue, snapshot, or measurement -- what is kept is this "
    "thread and what the issue has already spent.\n\n{marker}"
)


def _effects(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """The two external halves, in the order a human reads them.

    Both take the target off the RECORD rather than off the setting, so a
    restart begun under one `DECOMPOSE` value and resumed under the other
    finishes the label its own notice already announced.
    """
    target = generation.restart_target
    _announced(gh, issue, state, generation, target)
    _relabelled(gh, issue, target)


def _announced(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
    target: str,
) -> None:
    """Say once, on the thread, which cycle this issue is starting over as.

    Proved from the thread rather than from a record, because the comment and
    the write that would record it cannot be made one operation: a crash
    between them would say it twice. The marker is scoped to the cycle being
    minted, so a later restart of the same issue still gets its own sentence.

    A notice a PREVIOUS pass posted is adopted rather than merely recognized,
    and that is the whole reason this reads the comment rather than a boolean.
    Posting tracks the id on the in-memory record alone; the write that would
    make it durable is the retirement two steps below, so a pass whose relabel
    or retirement then failed left the id nowhere at all -- and the marker
    suppresses the repost that would have tracked it again. The bounded id
    ledger is what every later "is this comment ours" reading is taken
    against, and the projection keeps exactly that list, so a fresh cycle
    would otherwise wake up unable to recognize the comment announcing it.
    """
    marker = _restart_marker(issue.number, generation.restart_cycle_id)
    said = _notice_on_the_thread(gh, issue, marker)
    if said is None:
        _comments._post_issue_comment(gh, issue, state, _RESTART_NOTICE.format(
            predecessor=generation.restart_predecessor,
            cycle=generation.restart_cycle_id,
            label=target,
            marker=marker,
        ))
        return
    _tracked(state, said)


def _tracked(state: _pinned_state.PinnedState, said: Any) -> None:
    """Put a notice an earlier pass posted back on the bounded id ledger.

    Guarded on the ledger it is joining, because the tracker appends: a pass
    that adopted the same notice and then failed at the label again would
    otherwise spend one of the ledger's bounded slots per visit, evicting the
    ids of real comments to record one id repeatedly.
    """
    said_id = getattr(said, "id", None)
    if said_id is None:
        return
    if int(said_id) in _comments._orchestrator_ids(state):
        return
    _comments._track_orchestrator_comment(state, int(said_id))


def _relabelled(gh: _client.GitHubClient, issue: Issue, target: str) -> None:
    """Put the issue in the state the marker named, as this workflow's write.

    Written GUARDED, because it is a transition the graph declares: the
    unlabeled state a restart is entered from names both labels a restart may
    apply, which is exactly the edge an operator's removal of `rejected`
    opens.

    An issue already wearing the target is left alone where THIS orchestrator
    is the one that applied it -- a re-set costs a write and a second
    `stage_enter` on a state the issue never re-entered, and that is exactly
    the state a crash between the label and the retirement leaves behind.

    Where somebody else applied it, the label is not what this write is for.
    A restart's own application is the bot-authored event that separates one
    cycle's terminal from the next's, and the ending beside this owner reads
    the newest such application as its last-resort proof that a `rejected` it
    has no record of ever landed. A cycle minted over a hand-applied target
    leaves the PREVIOUS cycle's `rejected` standing as the newest, so the next
    unlabeled cancellation would adopt a terminal it never reached and restart
    on a removal nobody made. The name is therefore re-applied rather than
    accepted, and the label history is asked ONLY here -- a paginated walk,
    reached on the one pass that finds the target already in place.
    """
    if gh.workflow_label(issue) != target:
        gh.set_workflow_label(issue, target)
        return
    if gh.last_workflow_label_applied(issue) == target:
        return
    _reapplied(gh, issue, target)


def _reapplied(gh: _client.GitHubClient, issue: Issue, target: str) -> None:
    """Make a target somebody else applied this orchestrator's own write.

    Cleared and set rather than set again, because what is missing is the
    EVENT rather than the label: GitHub records an application only for a name
    that arrives, so writing the one already there would separate nothing.

    Nothing is lost in the window between the two writes. The marker is
    durable and answers the authorization for itself, so a tick that dies with
    the issue unlabeled re-enters this restart and applies the target from the
    ordinary side. A history that could not be read falls here too, for the
    same reason every other reading of it fails closed: one pair of label
    writes is what an answer nothing could establish costs.
    """
    log.warning(
        "issue=#%d already wears %r, and this orchestrator is not what "
        "applied it; putting the label back as its own write, so the fresh "
        "cycle is separated from its predecessor's terminal",
        issue.number, target,
    )
    gh.set_workflow_label(issue, None)
    gh.set_workflow_label(issue, target)


def _restart_marker(issue_number: int, cycle_id: Any) -> str:
    """The receipt one restart's notice on the thread is stamped with."""
    return _RESTART_MARKER.format(issue=issue_number, cycle=cycle_id)


def _notice_on_the_thread(
    gh: _client.GitHubClient, issue: Issue, marker: str,
) -> Any | None:
    """This restart's own notice where the thread already carries it.

    The comment rather than the fact of it, because an adopted notice owes the
    ledger its id. Both halves of "ours" are still required of it -- the
    cycle-scoped marker and the author -- so a marker anybody can paste
    silences nothing and adopts nothing.

    Walked whole rather than from a watermark: the projection behind this
    drops every watermark the cancelled cycle kept, and a restart resumed
    after one landed would be reading from a mark that is no longer there.
    """
    bot_login = getattr(gh, "_bot_login", None)
    for posted in gh.comments_after(issue, None):
        if _github_comments.carries_own_marker(
            (posted,), marker, bot_login=bot_login,
        ):
            return posted
    return None
