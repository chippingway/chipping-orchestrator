# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which fresh replies on a parked thread are a human's answer to the park.

Several roads read a parked `implementing` thread in one tick, one after the
other: the measurement park's retry, the parked-`/orchestrator continue`
classifier, the quiet timeout recovery, and the resume behind all of them,
which delivers whatever they leave. Each of the first three asks a question of
the fresh replies -- is every one of them a bare command, is there any at all
-- and hands the tick on by the answer, and the resume's frozen batch asks the
same questions again before it spends anything. So the answer comes off ONE
list, cut here, and no road may read a wider or narrower one: a reply counted
on one side of the hand-off and missing on the other is a tick each road
leaves to the next, on every poll, with nothing retried, refused, or said.

`prompt_delivery`'s classification is the first cut -- the trust filter, the
pinned comment by identity, our own posts by recorded id, and a body carrying
our marker that the ledger cannot vouch for -- and a bare
`/orchestrator add-agent-runs` is the second. That command is a control the
run-limit hold has already answered, with its receipt on the thread, and the
grant that answers it may leave it unread: the park it lifts interrupted a
reply below it, and a watermark is one number, so the command above that reply
stays past the mark with it. It is still there when the run the grant bought
parks again. Counted by one road, a later `/orchestrator continue` is mixed
with it and passed through; dropped by the next, the same continue is bare and
reserved -- and the park stands forever.

The authorization park reads its thread by a different first cut -- the id
ledger alone, so a marker somebody pasted is still a reply that demotes the
command under it -- and asks it for the LAST reply rather than for all of
them. The second cut is this one all the same, on that road and on the
freeze's copy of its question: an answered grant read as the last word would
hide the command written above it on one side and not the other.
"""
from __future__ import annotations

from collections.abc import Iterable

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_delivery as _delivery,
    run_grant_request as _run_grant_request,
)
from orchestrator.workflow.stages.implementing import state as _state


def _answering(read: Iterable) -> list:
    """The comments of one read that are not an already-answered control.

    Order is kept, since the authorization park's reading takes the last.

    Only the bare command comes out, for the reason the drift hash drops only
    it: words written beside the command are guidance, and the resume that
    feeds them to a developer is what they are owed.
    """
    return [
        seen for seen in read
        if not _run_grant_request._is_bare_command(seen)
    ]


def _fresh_replies(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> list:
    """The replies past the park's watermark a resume would deliver.

    Read by the pinned comment's identity, as the frozen batch is: a reply
    quoting the state marker is a reply, and a road that could not see it
    would decide over the words meant to end the park.
    """
    return _answering(_delivery.human_replies(
        gh.comments_after(
            issue, state.get(_state._LAST_ACTION_COMMENT_ID),
            state_comment_id=state.comment_id,
        ),
        frozenset(_comments._orchestrator_ids(state)),
        state_comment_id=state.comment_id,
    ))
