# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What may have ended between this tick's readings and the push it is about.

The initial publication's own barrier, asked immediately before the transport
and nowhere else in that owner. Everything above the push spends a run, a
reading, or a proof, and each of those is time a poll on another worker can
find the world changing under -- so this is the last point at which either
answer is still true.

Two endings. A close a poll LATCHED, which is the process-wide reading the
issue object cannot give: the object is the snapshot the tick opened with, and
a close landing since is one only the latch knows. And the PULL REQUEST this
push would join -- the one a caller PROVED where it holds one, and otherwise
the one the record names. Reuse is a lookup by BRANCH, so a pull request that
ended in the window answers nothing to it, a second one is opened over the
work, and `pr_number` is overwritten with it: the pointer to whatever a human
just decided is gone.

One ending is not an ending for this push, and it is the reason this is an
owner rather than an open-state check. A merged `discussion` plan is an
AGREEMENT: the humans read a design and said build it, and the stage ahead of
here lets such a tick carry on for exactly that reason -- finalizing on it
would close the issue `done` with no developer having run. What it licenses is
an implementation with a pull request of its own, so the plan is not something
this push joins and never something it may be held back by.

A record that NAMES a pull request and cannot produce one is the third answer
and refuses outright. Absent is an issue that has published nothing, which is
what this seam's own first push is for; a field that is there and will not type
is the record disagreeing with itself, and read as an absence it would buy
exactly the push this owner exists to withhold.

Refusing writes nothing. The commit stays in the worktree, the record stays as
it stands, and the next poll asks the same question of the same durable state.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.stages.discussion.state import (
    _PLAN_PATH as _DISCUSSION_PLAN_PATH,
    _PLAN_SHA as _DISCUSSION_PLAN_SHA,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_overflow as _overflow,
    models as _models,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _ended_before_the_push(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    approved: _models._ApprovedWork,
) -> bool:
    """Whether the work this push is about ended while the tick was working.

    Two endings, asked immediately before the transport because that is the
    only point at which either answer is still true: everything above spends a
    run, a reading, or a proof that a poll on another worker can find the world
    changing under.

    The PULL REQUEST is the one this push would JOIN, which is whichever of two
    the tick has: the one a caller established for itself, where it hands one
    in, and otherwise the one the record names -- the `discussion` stage's plan
    pull request sitting on the very ref the dev commits went to, or this
    stage's own from a round that crashed before its relabel. Both are reused
    rather than opened, and the reuse is a lookup by BRANCH: one that ended
    between the tick's first reading and here answers nothing to that lookup,
    so a second pull request is opened over the work and `pr_number` is
    overwritten with it -- which is how the pointer to what a human just
    closed is lost. An issue that records none is the first publication, which
    has nothing to have ended and spends no request. A plan the humans have
    SETTLED is the one ending that is not an ending for this push, and
    `_publication_is_over` beside this owns why.

    Read fail-CLOSED, like every reading standing immediately before an effect
    nothing can undo: what refusing costs is the poll that asks again, and what
    falling through costs is a branch and a pull request nobody asked for.

    A record that names a pull request and cannot produce one refuses ahead
    of both, and telling that from an ABSENT field is the whole of why it is
    read three ways rather than typed. Absent is an issue with nothing
    published -- the first push of all, and the window before the relabel
    that records what it opened -- so there is no publication for this
    barrier to hold it to. A field that is there and will not type is the
    record disagreeing with itself, and every identity in this domain is read
    fail-closed, so it comes back as no identity: skipped for that, a push
    onto a pull request somebody has just closed goes out as though the issue
    never had one, and a second pull request is opened over the work.

    The CLOSE is asked last and of the process-wide latch rather than of the
    issue object, which is the snapshot the tick opened with. Last because the
    reading above it is a request: a close landing while that request is in
    flight would be answered one push too late by a latch read before it, and
    this one costs nothing, so the cheap answer gets the final word.
    """
    recorded = _late_gate_models._RecordedPublication.named_by(
        state.get(_state._PR_NUMBER),
    )
    if recorded.damaged:
        log.warning(
            "issue=#%d records a pull request this build cannot read as an "
            "identity; refusing the push rather than publishing as though the "
            "issue had never opened one",
            issue.number,
        )
        return True
    number = approved.delivered_pr or recorded.number
    if number and _publication_is_over(
        gh, issue, state, number, proved=bool(approved.delivered_pr),
    ):
        return True
    if not _observations.close_observed(spec.slug, issue.number):
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed before its branch was pushed; "
        "refusing the push rather than putting work on an issue nobody wants",
        spec.slug, issue.number,
    )
    return True


def _publication_is_over(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    number: int,
    proved: bool,
) -> bool:
    """Whether the pull request this push would join has ended.

    One reading rather than a question per fact, because the two answers are
    read off the same object: whether it is still open, and -- where it is not
    -- whether it is the `discussion` stage's PLAN rather than a publication
    of this stage's.

    That carve-out is the whole reason this is not a bare open-state check. A
    merged plan is an agreement, not a delivery: the humans read a design and
    said build it, and the stage ahead of this one lets such a tick carry on
    for exactly that reason -- finalizing on it would close the issue `done`
    with no developer ever having run. The implementation it licenses gets a
    pull request of its OWN, so an ended plan is not something this push joins
    and never something it may be held back by. A plan somebody closed
    unmerged reads the same way here and is answered the same way it is above:
    the tick carries on, and what to do about a design nobody accepted is the
    stage question, not the transport's.

    A pull request this host could not READ is refused ahead of both, and the
    record does not save it. What the carve-out is about is a plan the humans
    have SETTLED, and settled is a thing only a reading establishes: the
    record says which pull request is the design, never what anybody has done
    with it. Carved out on the record alone, a request that failed would
    publish onto whatever it was hiding -- and what refusing instead costs is
    the poll that asks again, where a readable plan gets the carve-out it is
    owed.

    `proved` says the number was established by the caller rather than read
    off the record. Nothing established that way can be a plan -- what a
    caller proves is that the branch is already standing on the candidate,
    which no plan publication produces -- so the carve-out, which exists to
    tell a recorded number apart, is not offered to it at all.
    """
    reading = _overflow._PublicationReading.taken(gh, number)
    if reading.refusal is not None:
        log.warning(
            "issue=#%d could not read pull request #%d before the push that "
            "would join it; refusing rather than publishing onto whatever a "
            "request that failed was hiding",
            issue.number, number,
        )
        return True
    if reading.state == _overflow._OPEN:
        return False
    if not proved and _is_the_discussion_plan(state, reading):
        log.info(
            "issue=#%d records plan PR #%d, which the humans have settled; "
            "publishing the implementation onto a pull request of its own",
            issue.number, number,
        )
        return False
    log.warning(
        "issue=#%d records pull request #%d, which has ended; refusing the "
        "push rather than publishing onto a publication nobody can join",
        issue.number, number,
    )
    return True


def _is_the_discussion_plan(
    state: _pinned_state.PinnedState,
    reading: _overflow._PublicationReading,
) -> bool:
    """Whether the pull request just read is the design, not an implementation.

    The same two records the stage's own terminals tell them apart by, asked
    of the reading already in hand rather than of a second fetch. A live
    `discussion_plan_path` says so outright; past the handoff that retires it,
    `discussion_plan_sha` is what the plan publication put on that pull
    request, and a head still standing there is one nothing of this stage's
    has pushed over.

    Asked only of a reading that CAME BACK, which the caller checks first: a
    request that failed establishes neither record's question, and a plan is
    told apart by what the humans did rather than by what the comment says is
    recorded. A reading that came back naming no head answers on the path
    record alone -- while that record stands nothing of this stage has
    pushed, so the pull request is the plan whatever its tip turns out to be.
    """
    if state.get(_DISCUSSION_PLAN_PATH):
        return True
    plan_sha = state.get(_DISCUSSION_PLAN_SHA)
    return bool(plan_sha) and reading.head == plan_sha
