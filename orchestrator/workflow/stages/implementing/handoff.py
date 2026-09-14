# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Handing a published implementation on: one write, then the label.

Reached only where the push landed, the pull request carries it, and the
checkout was proved twice over to still be the thing that was measured -- so
nothing here refuses and nothing here parks. What is left is a record to spend
and a claim to give up, in that order.

The record names `pr_number` AND `branch` together, because a state that
arrived without a branch (an awaiting-human resume that opened the pull request
without passing the fresh-spawn persist site) would leave the next tick's
branch resolution falling back to the legacy name while the live pull request
sits on the slug-namespaced one.

Resetting the counters belongs to that same write rather than sitting beside
it: the issue moved forward, so the review round, the retry budget, the
silent-park streak, and the timeout watermark are all spent, and any of them
left behind would mis-fire a later hop back into implementing.

WHEN this is reached is the publication owner's, which is once both proofs
taken around the push have passed. This owner decides only what the last write
says and what goes out after it.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import retry_values as _retry_values
from orchestrator.workflow.stages.discussion.state import (
    _PLAN_SHA as _DISCUSSION_PLAN_SHA,
)
from orchestrator.workflow.stages.implementing import (
    late_parks as _late_parks,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel


def _advance_to_validating(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, pr, branch: str
) -> None:
    """Record the published PR/branch, reset the per-PR budgets, and hand off
    to `validating`.

    The docs pass runs only as the final-docs handoff after the reviewer agent
    approves, so a fresh commit goes straight to validating.

    What this staged goes out DURABLY before the label does, and that ordering
    is the whole of why the write is here rather than left to the caller. The
    label is the last thing on this road that another stage reads, and past it
    the issue is no longer implementing's: nothing here runs on it again. So
    every record this line spends -- the plan SHA, the certified baseline, the
    handoff anchor, the three an authorization handoff carries while it is
    still in flight, and above all the commit an approval said was still owed
    a push -- has to be spent before the label, or a tick that died in between
    strands it on an issue that has moved on. A stranded approval is the
    sharpest: nothing under `validating` spends it, implementing never sees
    the issue again, and the record goes on freezing the branch out of the
    ordinary base refresh for the rest of the issue's life.

    The cost is one pinned write per publication, and the window it leaves is
    the one the commit this line records exists for. A relabel that failed --
    or a process that died between the two -- leaves an implementing issue
    whose branch is pushed and whose pull request is open, and whose every
    gate record is already spent. Read as work nobody has ruled on, that
    branch is measured again on the next tick, against a base that has moved
    or a ceiling that was retuned since, and an oversized answer would route
    it to adjudication with the push and the pull request already made. So the
    pushed commit goes down in this same write: the next tick recognizes it,
    publishes it without a reading, reuses the pull request that already
    carries it, and finishes the relabel this one could not.
    """
    state.set(_state._PR_NUMBER, pr.number)
    # Whatever this issue's recorded PR was before, it is an implementation's
    # now. The `discussion` stage records the commit its plan PR carried so
    # implementing's merged-PR terminal does not read a design being agreed to
    # as work having landed; that record is spent here. It is hygiene rather
    # than the guard itself -- the guard asks the PR's head, so it answers
    # right even for the tick that pushed and died before reaching this line.
    state.set(_DISCUSSION_PLAN_SHA, None)
    _spend_records_the_label_ends(state)
    # Persist the pushed branch alongside `pr_number` so the next tick's
    # `_resolve_branch_name` can recover it directly. Without this, a state
    # that lacked `branch` going in (e.g. an awaiting-human resume that opened
    # the PR here without first passing through the fresh-spawn branch-persist
    # site) would leave `pr_number` set with `branch` unset; the legacy-PR
    # fallback in `_resolve_branch_name` would then misroute every downstream
    # tick to `orchestrator/issue-<n>` while the live PR is on the
    # slug-namespaced branch this push just published.
    state.set(_state._BRANCH, branch)
    _reset_implementing_counters(state)
    gh.write_pinned_state(issue, state)
    gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)


def _spend_records_the_label_ends(state: _pinned_state.PinnedState) -> None:
    """Drop every record that stops being true the moment the label moves.

    The certified baseline and the anchor beside it say the relabel INTO this
    stage was accepted and nothing has published since, which stops being true
    on the line that calls this: the baseline is what freezes base sync for
    the branch, the anchor is what has the reconcile keep re-anchoring the
    checkout onto the plan pull request, and an issue leaving for `validating`
    still carrying them would take both with it.

    The other two are what an authorization handoff carries while it is in
    FLIGHT. They say a call into the publication seam has not come back yet,
    so the poll that finds them puts the park, its reason and its watermark
    back the way that call found them. Reaching here is that call having come
    back the one way it never has to: the branch is published and the label is
    about to move. Left set, an issue bounced into implementing again later
    would have a spent authorization park restored over it -- waiting on a
    command whose watermark was consumed before the push this write records,
    and holding a published implementation behind a decision nobody can make
    twice.

    The reading that handoff staged beside them is SPENT here rather than
    dropped, and that is the difference between the four and the fifth. Two of
    the seam's roads publish without ever reading the thread, so the reply
    that ended the park is still above the watermark on this line -- and past
    it the stage this issue moves to reads that reply as somebody's fresh
    feedback and pays for a developer to answer a command nothing there can
    act on.

    All five for the same reason, which is the reason they are settled HERE:
    nothing under `validating` drops any of them and implementing never sees
    the issue again on this road, so a record left standing is one nothing
    will ever come back for -- and a boundary applied after this write is one
    a crash in the window it opens loses for good.
    """
    state.set(_state._READ_ONLY_BASELINE_SHA, None)
    state.set(_state._HANDOFF_ANCHOR_SHA, None)
    state.set(_state._HELD_PUBLICATION, None)
    state.set(_state._HELD_PARK, None)
    _late_parks._spends_a_held_reading(state)


def _reset_implementing_counters(state: _pinned_state.PinnedState) -> None:
    # Reset the review counter every time we (re-)open a PR so the validating
    # handler starts fresh on the new branch state.
    state.set("review_round", 0)
    # Issue moved forward; reset the implementing retry budget so any future
    # bounce back into implementing (e.g. validating -> implementing in a
    # later stage) starts with a fresh window.
    state.set(_state._RETRY_COUNT, 0)
    state.set(_state._RETRY_WINDOW_START, None)
    # The attempts a continuation left go with the accounting they replaced:
    # they are what a human bought this issue under the budget just reset, and
    # kept past that they would hold a shipped issue to the grant rather than
    # to the budget it now has again.
    state.set(_retry_values.RETRY_CAP_CONTINUED, None)
    # The session just produced commits, so it isn't poisoned -- reset the
    # silent-park streak so a future blip doesn't tip an otherwise-healthy
    # session past the fresh-session threshold.
    state.set(_state._SILENT_PARK_COUNT, 0)
    # The commit shipped, so any agent-timeout park watermark is spent -- clear
    # it (and the stale reason) so it cannot linger into `validating` or
    # mis-fire the next-tick timeout recovery on a later implementing hop.
    if state.get(_state._PARK_REASON) == _state._AGENT_TIMEOUT:
        state.set(_state._PARK_REASON, None)
    state.set(_state._PRE_IMPLEMENT_SHA, None)
    # The commit an approval said was still owed a push: this IS that push,
    # so the debt is paid -- and the head it was pinned against with it, since
    # a lease outliving the publication it was frozen for would pin the next
    # one to a head this push has already moved. Spent here rather than after
    # the relabel because past the relabel the issue belongs to another stage,
    # and a record left behind would freeze this branch out of the base
    # refresh with nothing in implementing ever coming back to drop it.
    _late_parks._forget_approval(state)
