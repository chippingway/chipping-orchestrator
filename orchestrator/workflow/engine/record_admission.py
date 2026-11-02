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
`written`, which tells this write's landing from an earlier one. A step that
decided its whole state on the comment as it last synced with it, and may not
put back a field anyone wrote since, asks `strictly_written`, which lands only
over that very comment -- and, where it names what else the write rests on,
only while that still stands immediately before the edit leaves, the comment
read once more behind it (`stands`).

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

import json
import logging
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github import edit_questions as _edit_questions, pinned_refusal as _pinned_refusal
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedEdit, PinnedState

log = logging.getLogger("orchestrator.workflow")

# What else a strict write rests on, asked immediately before its edit leaves.
_Still = Callable[[], bool]

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


def strictly_written(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    still: _Still | None = None,
) -> bool:
    """Write `state` whole only while the comment still reads as `state` last synced with it; whether it landed.

    The strict edit (`GitHubStateMixin.edit_pinned_state`) sends nothing over
    a comment another writer -- a human or another road -- moved since, and a
    write nobody confirmed may have landed either way, so each, like every
    other edit that did not land, leaves `state` withheld from every
    whole-state write behind it, for a later reading to settle. A state that
    synced with no comment has nothing to be held to, and is withheld too.

    `still` is what else the write rests on -- the issue's controls, say --
    asked behind the editor's walk to the comment and immediately before the
    edit leaves (`github/edit_questions`), and the comment read once more
    behind it (`stands`): a hold, a comment written, or the comment replaced
    by another -- the same payload under a new id included -- landing while the
    walk or `still`'s own requests were out holds the edit with nothing sent.
    """
    if state.synced is None:
        state.withheld = True
        return False
    asked = nullcontext() if still is None else _edit_questions.asked_before_the_edit(
        _BeforeTheEdit(gh, issue, state, still),
    )
    with asked:
        edited = gh.edit_pinned_state(issue, state, over=json.loads(state.synced))
    if edited is not PinnedEdit.EDITED:
        state.withheld = True
        return False
    state.synced = json.dumps(state.state_data, sort_keys=True)
    return True


def stands(gh: GitHubClient, issue: Issue, state: PinnedState, still: _Still | None = None) -> bool:
    """Whether what `state` was last read or written as still stands: `still` first, then the comment read once more.

    The comment, read last, has to be comment `state.comment_id` still,
    reading as `state.synced`: its identity is asked beside its payload, since
    a comment a human posted in place of that one carries no record of what
    was written over it, however alike the two read. One moved or replaced
    withholds `state` from every whole-state write behind it; one nobody
    could read answers False and proves nothing either way.
    """
    if still is not None and not still():
        return False
    try:
        fresh = gh.read_pinned_state(issue)
    except Exception:
        log.exception("issue=#%d its pinned comment could not be read again; holding what rests on it", issue.number)
        return False
    synced = state.synced
    same = synced is not None and fresh.comment_id == state.comment_id
    if same and fresh.reads_as(json.loads(synced)):
        return True
    log.info("issue=#%d its pinned comment moved or was replaced since it was read; holding it", issue.number)
    state.withheld = True
    return False


@dataclass(frozen=True)
class _BeforeTheEdit:
    """The question a strict edit of `state` asks immediately before it leaves (`edit_questions`)."""

    gh: GitHubClient
    issue: Issue
    state: PinnedState
    still: _Still

    def __call__(self, read: _edit_questions.Spelling, candidate: _edit_questions.Spelling) -> bool:
        """Whether the edit sending `candidate` over `read` -- the comment as `state` synced with it -- may leave."""
        return stands(self.gh, self.issue, self.state, self.still)


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
