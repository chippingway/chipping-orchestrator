# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks that can clear without anyone commenting.

A push that lost a race and an agent killed by its own timeout are both
conditions the next tick can simply re-attempt, but neither produces the human
reply the awaiting-human resume waits for. Without a silent retry the issue
sits parked forever on a failure that already went away.

So the recovery runs quietly and answers in one of three words. It must not
spawn an agent or post anything -- the caller owns the visible side, so a tick
that is still stuck produces no churn at all. It IS allowed to move the review
round, and it is the only writer permitted to while the park flags are still
set: a timeout that had already committed gets its push finished here, and
that landed commit is a head the reviewer has not seen.

`push_failed` and `agent_timeout` are the two that actually touch git;
the reviewer-side reasons clear on sight, because there is no dev work to
finish, only a reviewer to re-spawn. Every probe fails closed to `"stuck"` --
a missing worktree, a dirty tree, an unreadable `pre_dev_fix_sha`, a push that
fails again -- since leaving the park standing costs a poll and publishing
blind costs the PR.

`_recovery_followup_comment` is the one sentence a healed park owes the thread,
and it is decided here because the pair it is keyed by -- the reason parked and
the word the probe answered with -- is this module's own vocabulary. Choosing
the text is all that happens: the caller that clears the flags is what posts
it, so the probe stays as quiet as its contract says and a tick that is still
stuck still says nothing at all. The mention that filed the park is what earns
the reply, so a park with no `last_action_comment_id` behind it answers None --
nothing was said, so nothing needs taking back -- and so does a reason/outcome
pair the table does not name, rather than guess at wording for it.

"At most once per episode" is answered from the thread rather than from pinned
state, because the post and the write that clears the park cannot be made one
operation: a process that dies between them leaves GitHub holding a comment
that no local record knows about, and any receipt written beside the clear
dies with it. So the follow-up carries `_RECOVERY_FOLLOWUP_MARKER` and the next
attempt looks for it among the comments past `last_action_comment_id` -- the
park's own mention id, which is what scopes the search to THIS episode, since a
later park stamps a higher watermark and cannot be silenced by an older
follow-up sitting below it. A forged marker costs its author the notification
they would have been spared anyway, which is why the cheap check is the right
one here.
"""
from __future__ import annotations

from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)
from orchestrator.workflow.stages.validating import (
    rounds as _rounds,
    state as _state,
)

# Stamped on every follow-up so a later tick can recognize one it posted even
# when the pinned write that was supposed to record it never landed. An HTML
# comment, so it is invisible in the rendered issue thread.
_RECOVERY_FOLLOWUP_MARKER = "<!--orchestrator-recovery-followup-->"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# The clause each (park reason, recovery outcome) pair earns in the follow-up.
# Keyed by both because the same word means different work depending on what
# parked: a `pushed` that finishes a `push_failed` is the retry the operator
# was pinged about, while a `pushed` that finishes an `agent_timeout` is a
# commit the killed run had already made.
_RECOVERY_DETAILS = MappingProxyType({
    (_state._REASON_PUSH_FAILED, _state._OUTCOME_PUSHED):
        "the failed push was retried and succeeded",
    (_state._REASON_AGENT_TIMEOUT, _state._OUTCOME_PUSHED):
        "the commit the timed-out run had already made was pushed",
    (_state._REASON_AGENT_TIMEOUT, _state._OUTCOME_CLEARED):
        "the timed-out run had left nothing to publish",
    (_state._REASON_REVIEWER_TIMEOUT, _state._OUTCOME_CLEARED):
        "the reviewer is being re-spawned",
    (_state._REASON_REVIEWER_FAILED, _state._OUTCOME_CLEARED):
        "the reviewer is being re-spawned",
})


def _recover_failed_push(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> str:
    """Retry a push the previous tick could not land, through the gate.

    The commit is one an earlier tick already measured, so the ordinary answer
    here is the approval bypass: the gate recognizes the commit it approved
    and has still to push and hands it straight back. What the call buys is
    the case that bypass does not cover -- a developer who committed again
    since, or a pull request that moved or closed under the park -- and the
    push named and pinned by what came back.

    The debt is spent on the push that pays it. Without that the approval
    outlives the publication it was recorded for and freezes this branch out
    of the pre-tick base refresh for the rest of the issue's life, with the
    recovery that would have dropped it already finished.
    """
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if not worktree.exists():
        return _state._OUTCOME_STUCK
    # No commit is named, because this recovery read none: the park says a
    # push failed, and which commit it was for lives on the approval the gate
    # recognizes for itself.
    return _publish_recovered_fix(
        _late_records._gate(gh, spec, issue, state, worktree),
    )


def _recover_timed_out_fix(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> str:
    """Publish a commit the timeout killed the disposition before it saw.

    The one road to a published pull request that never reached the gate: the
    park was taken because the run timed out, so nothing measured the commit
    it turned out to have made. Pushing it from here would grow the pull
    request by an unadjudicated diff -- the exact publication the gate exists
    to stop -- so the reading happens before the push, with no developer
    having run on this tick.
    """
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if (
        not worktree.exists()
        or _worktree_status._worktree_dirty_files(worktree)
    ):
        return _state._OUTCOME_STUCK
    before_sha = state.get(_state._PRE_DEV_FIX_SHA)
    if not isinstance(before_sha, str):
        return _state._OUTCOME_STUCK
    current_sha = _verification_probes._head_sha(worktree)
    if not current_sha or current_sha == before_sha:
        state.set(_state._PRE_DEV_FIX_SHA, None)
        return _state._OUTCOME_CLEARED
    recovered = _publish_recovered_fix(
        # The commit this recovery read and is publishing AS the timed-out
        # run's. The gate proves the checkout again, and something landing
        # between the two reads would otherwise be measured, pushed, and
        # receipted here as the work that run left behind.
        _late_records._gate(gh, spec, issue, state, worktree), current_sha,
        # The head the killed run began at, which is the head its pull request
        # was standing on: the branch is in sync with its publication when a
        # fix round opens. Named, a pull request somebody pushed to while that
        # run was out refuses this push rather than being overwritten by work
        # built on the head it used to be on.
        before_sha,
    )
    if recovered == _state._OUTCOME_PUSHED:
        state.set(_state._PRE_DEV_FIX_SHA, None)
    return recovered


def _publish_recovered_fix(
    gate: _late_gate_models._Gate, candidate: str = "", entered_head: str = "",
) -> str:
    """Measure a commit a park left unpublished, then push what it earned.

    The tail both recoveries share, because the question they ask is the same
    one: a commit is sitting on this branch that the pull request does not
    carry, and what decides whether it may join it is what the pull request
    would come to with it. No developer ran on either tick, so the reading is
    taken as a reconciliation -- a head that is not the commit the record
    names is a checkout something moved, not a run's output.

    `entered_head` is the head the publication was standing on before the
    work being published was made, where the caller can name one. The timed-out
    recovery can: the run it is finishing began on a branch in sync with its
    pull request, and the anchor it left behind is that head -- so a pull
    request somebody pushed to while that run was out refuses this push
    instead of being overwritten by a commit built on the head it used to be
    on. The failed-push recovery names none, and needs none: its commit was
    already measured against a publication whose head the approval records,
    and that recorded head is what its push is pinned to.

    `candidate` is the commit the CALLER read and is publishing as, where it
    read one. The timed-out recovery does: it compares the head against the
    pre-run SHA to decide there is anything to publish at all, and between
    that reading and the proof the gate takes the worktree is writable -- so a
    commit landing in the window would be measured, pushed, and receipted as
    the work the killed run left. Named, the two are one decision and a
    checkout standing anywhere else refuses. The failed-push recovery names
    none: it read no head, and the commit it owes a push for is the one the
    approval on the record already identifies.

    The push is named and pinned by what the gate handed back, and the debt it
    pays is spent on it: an approval that outlives the publication it was
    recorded for freezes this branch out of the pre-tick base refresh with the
    recovery that would have dropped it already finished.

    The round rides that same write and is counted NOWHERE else here, which is
    what makes a recovery that runs twice count once. This tick has no run
    behind it, so the value it would compute is read off the counter itself --
    and a retry over a publication that is already settled would read a
    counter the tick which settled it has already moved. The gate is silent on
    exactly that reading, so leaving the count to it is what ties the round to
    the push that earned it rather than to the poll that noticed.

    WHICH round is `rounds`', not this owner's. A publication an `in_review`
    requirements edit already reset the budget for spends none of it: the park
    this retry is clearing is what delayed that same publication, so counting
    it here would leave an edit whose push landed a tick late one round short
    of the edit whose push landed at once. Every other park leaves a commit no
    reviewer has read, which is the event the count is for.
    """
    branch = _naming._resolve_branch_name(
        gate.state, gate.spec, gate.issue.number,
    )
    owed = _rounds._spends_for_an_owed_publication(gate.state)
    published = _late_push._publishes(
        gate, branch,
        _late_gate_models._Entered(
            reconciling=True,
            spends=owed,
            candidate=candidate,
            head=entered_head,
        ),
    )
    if published.held:
        # The park the gate took mutates state in memory, and no caller of a
        # held recovery writes it: they clear nothing and announce nothing,
        # which is right, and would leave a posted notice with the OLD reason
        # and watermark still durable -- so the same retry fires next tick and
        # the human is asked again.
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return _state._OUTCOME_HELD
    if not published.landed:
        return _state._OUTCOME_STUCK
    return _state._OUTCOME_PUSHED


def _try_recover_validating_transient_park(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> str:
    """Quietly attempt to clear a transient validating park.

    Returns one of:
      * ``"stuck"`` -- the underlying condition has not resolved; caller
        leaves the park flags in place and returns silently.
      * ``"held"`` -- the size gate took the candidate this retry was about,
        so nothing was published and the tick is over. The gate has already
        parked the issue or handed it to the adjudication and written its own
        state, so the caller clears nothing, announces nothing, and moves no
        label: a follow-up would say a recovery happened and a relabel would
        move the issue off the state the gate just put it in.
      * ``"cleared"`` -- the park can be cleared, but nothing new
        landed on the PR (reviewer-only crash, or a dev-timeout that
        had not actually produced a commit). Caller clears the flags
        and stays on `validating` so the reviewer reruns.
      * ``"pushed"`` -- a dev fix was finished off during recovery
        (a deferred push of `push_failed`, or the trailing push of an
        `agent_timeout` that had committed before being killed).
        Caller clears the flags, resets stale approval state, and
        stays on `validating` so the reviewer re-evaluates the new
        head.

    Must not spawn the agent or post issue/PR comments -- the caller owns
    the visible side of the recovery so a still-stuck tick produces no
    churn.

    The helper IS allowed to update review-round bookkeeping when a fix
    landed during recovery (e.g. an agent_timeout where the dev had
    actually committed before timing out, and we finish the push here).
    Callers should not mutate the round themselves; this is the only
    write path while the park flags are still set.
    """
    park_reason = state.get(_state._PARK_REASON)
    if park_reason == _state._REASON_PUSH_FAILED:
        return _recover_failed_push(gh, spec, issue, state)
    if park_reason in (_state._REASON_REVIEWER_TIMEOUT, _state._REASON_REVIEWER_FAILED):
        return _state._OUTCOME_CLEARED
    if park_reason == _state._REASON_AGENT_TIMEOUT:
        return _recover_timed_out_fix(gh, spec, issue, state)
    return _state._OUTCOME_STUCK


def _episode_already_announced(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """True when this park episode's follow-up is already on the thread.

    Read rather than remembered: a tick whose pinned write failed after
    GitHub accepted the comment leaves no local trace of it, so the thread
    past `last_action_comment_id` is the only record that survives. Scoped to
    the episode by that same watermark -- the id of the mention this park was
    filed with -- so an older follow-up sitting below it cannot silence a
    later park's.
    """
    watermark = state.get(_LAST_ACTION_COMMENT_ID)
    return any(
        _RECOVERY_FOLLOWUP_MARKER in (issue_comment.body or "")
        for issue_comment in gh.comments_after(issue, watermark)
    )


def _recovery_followup_comment(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    park_reason: object,
    outcome: str,
) -> str | None:
    """The follow-up a park that just healed itself owes the issue, or None.

    `last_action_comment_id` is the evidence that a HITL mention was posted:
    `_park_awaiting_human` stamps it at the comment it just left, so a park
    carrying none never pinged anybody and closing a loop nobody was in would
    be pure churn. The text carries no @mention for the same reason -- the
    point is to retire the alarming last word on the thread, not to notify a
    second time.

    Returns None for a reason/outcome pair `_RECOVERY_DETAILS` does not name,
    so a park reason added to `_VALIDATING_TRANSIENT_PARK_REASONS` later
    stays silent until someone writes the sentence that describes it, and None
    again when `_episode_already_announced` finds this episode's follow-up
    already posted. The thread read runs last, so only a tick that has both a
    mention to retire and words for what healed pays for it.
    """
    if state.get(_LAST_ACTION_COMMENT_ID) is None:
        return None
    detail = _RECOVERY_DETAILS.get((park_reason, outcome))
    if detail is None:
        return None
    if _episode_already_announced(gh, issue, state):
        return None
    return (
        f":arrows_counterclockwise: Recovered automatically: {detail}; "
        f"processing resumed. No action needed.\n\n{_RECOVERY_FOLLOWUP_MARKER}"
    )
