# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hold every reading a dispatch acts on to pinned-state admission, and say a refusal locally.

The dispatcher admits the record its guards decide on under the issue's writer
claim (`stages/decomposition/late_relabel._dispatch_state`), and every stage
handler reads the comment again as it starts. The claim keeps every other
orchestrator writer off the issue, but not a human: a maintainer can edit the
comment between those two readings. A record admission refuses reads back
empty -- what an issue nobody has met reads as -- so a handler deciding on that
reading would greet, relabel, publish, or launch over a record nobody read.

So the handler's own reading is held to admission as well, and a refusal
abandons the handler where it stands: `admitted_state` raises
`github.pinned_refusal.RecordRefused`, which the dispatcher catches around the
handler it called (`issue_processing._route_issue_to_handler`), so no handler
grows a road of its own for it and a handler another one runs from inside --
`ready` handing on to `implementing` -- is abandoned with it. A record a human
edits after the handler's own reading is one the whole-state writer meets
instead, and the writer raises the same refusal with nothing written, so the
handler is abandoned at that write, before anything the write was for. Nothing
is reconciled or repaired: the next tick's dispatch refuses the issue again
until a human disposes of the record.

The writer still answers its other refusals -- a withheld state, a state the
next reading would refuse -- without raising, so a step whose effect rests on
a write -- an agent launched on its charge, a notice said for its park -- asks
`written`, which tells this write's landing from an earlier one.

A guarded commit answers a refused record too, as a refusal rather than a
raise, and a handler told that goes on to its own exit roads. The one exit
road that mutates an issue's artifacts whatever the handler concluded -- a
scratch checkout's teardown -- asks `teardown_admitted` at the effect itself,
so no road of the handler's in front of it decides whether the checkout stays.

Every refusal is said in one local line, naming the repository, the issue, the
comment, its admission status, and the version found against the one supported,
and never posted on the issue.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState

log = logging.getLogger("orchestrator.workflow")

# What a stage handler does with a reading admission refuses.
_HANDLER_ABANDONED = "abandoning the stage handler with nothing further done"

# What a teardown does with one.
_TEARDOWN_KEPT = "keeping the issue's checkout and branch for whoever disposes of the record"


def refuses(issue: Issue, state: PinnedState, outcome: str) -> bool:
    """Whether admission refused this reading of the issue's own comment, said locally with `outcome` where it did.

    A state that recorded nothing is admitted: an issue with no authenticated
    pinned comment is fresh work.
    """
    if state.supported:
        return False
    log.warning(
        "repo=%s issue=#%s pinned comment #%s is %s (found schema_version %r, supported %s: %s); %s",
        state.repo_slug, issue.number, state.comment_id, state.admission_status.value,
        state.found_version, state.supported_version, state.refusal_reason, outcome,
    )
    return True


def admitted_state(gh: GitHubClient, issue: Issue) -> PinnedState:
    """The pinned comment a stage handler starts on, raising `RecordRefused` where admission refuses it.

    Raised as `github.pinned_refusal.RecordRefused`, the class the writer
    raises over such a record, so the dispatcher catches one class.

    A read that fails raises as the handler's own read always has, so the
    dispatcher's per-issue isolation reports it.
    """
    state = gh.read_pinned_state(issue)
    if refuses(issue, state, _HANDLER_ABANDONED):
        raise _pinned_refusal.RecordRefused(
            f"issue #{issue.number} pinned comment #{state.comment_id} refused admission",
        )
    return state


def written(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Write `state` whole, and answer whether this write landed.

    The whole-state writer raises over a record admission refuses, and answers
    its other refusals -- a withheld state, a state the next reading would
    refuse -- by returning unchanged, so its return says nothing about whether
    it sent anything. What does is the mark it leaves only on a state it sent:
    `state.synced`, set to what the comment now carries. A state staged equal
    to what it last synced with already carries that mark, so it is cleared
    for this attempt and put back where the attempt did not set it -- a raise
    included, which propagates.
    """
    captured = state.synced
    state.synced = None
    try:
        gh.write_pinned_state(issue, state)
    except Exception:
        state.synced = captured
        raise
    if state.synced is None:
        state.synced = captured
        return False
    return True


def teardown_admitted(gh: GitHubClient, issue: Issue) -> bool:
    """Whether a scratch checkout's teardown may run: the issue's record, read now, is one admission takes.

    Asked at the effect rather than inferred from how the handler ended: the
    handler may have met a refused record by a road that answers rather than
    raises -- a guarded commit refused as unsupported -- and come to its exit as
    an ordinary one. A refusal keeps the checkout and its branch, said in the
    one local line. A read that fails proves no admission, and the run may
    already have met a refused record by that quiet road, so it keeps them too:
    the issue's next exit asks again.
    """
    try:
        state = gh.read_pinned_state(issue)
    except Exception:
        log.warning(
            "issue=#%s pinned comment could not be read before its checkout's teardown; %s",
            issue.number, _TEARDOWN_KEPT, exc_info=True,
        )
        return False
    return not refuses(issue, state, _TEARDOWN_KEPT)
