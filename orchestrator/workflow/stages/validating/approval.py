# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Everything an approved review still has to survive before it hands off.

The reviewer's verdict is not the last gate. The local verify run comes first
so an obviously-broken branch never reaches `in_review`, where the next reader
is a human deciding whether to merge; a default-empty `VERIFY_COMMANDS`
short-circuits to ok, and a failure parks in `validating` with a durable
reason rather than advancing. The squash follows, and its failure parks
WITHOUT relabeling on purpose -- the original commits are still on the branch,
and only a human can decide whether to keep the history or force it flat. The
notice it parks with says which of the four places the failure left the branch
in, because the errand differs: the approved commits at HEAD, the approved
commits off the tip and in the reflog behind a recorded head, the approved
commits still in the branch's own history under work committed on top of them,
or a reading that placed them nowhere at all.

The ordering inside the handoff matters too. The squash notice is posted
BEFORE `handoff` is asked to seed the watermarks, so that its own id lands in
the recorded orchestrator set and the seed walk steps past it; the reverse
order would hand in_review an informational post as fresh human PR feedback
and wake the dev on it.

A notice that was OWED and did not post is the one step that stops the
handoff, and what stops it is the record. The count that notice is worded
from lives on the pinned comment and nowhere else, so dropping it there would
put the announcement beyond every later tick; kept, the next tick's recovery
finds the collapse the remote already carries, republishes it as the leased
no-op it is, and words the notice again.

The relabel goes to `documenting`, not straight to `in_review`: the final docs
pass runs against the approved head, and everything seeded here survives that
hop. It goes LAST, behind the pinned write rather than ahead of it, because
the record of an unfinished collapse ends in that write: past the relabel the
issue belongs to a stage that never runs this recovery, so a process dying
between the two would leave a claim standing that nothing there would ever
answer -- and the watermarks the same write carries would be lost with it.

That write does not leave the boundary empty, though, because the relabel can
fail on its own. What it ends is the CLAIM; what it leaves is the commit the
move is owed over, and the route ahead of the next reviewer reads that and
moves the label rather than running a second review over a branch already
approved, squashed, and published. The record of it is dropped behind the
label, in a write of its own.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.publication import models as _publication, squash as _squash
from orchestrator.git.verification import runner as _verify_runner
from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import comments as _comments, guards as _guards
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    handoffs as _late_handoffs,
)
from orchestrator.workflow.stages.validating import (
    handoff as _handoff,
    models as _models,
    state as _state,
    verify as _verify,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The pull request this issue's work is on, read off the pinned comment rather
# than off a reviewer run: the tail below is reached with one behind it and
# without, and the record is the same either way.
_PR_NUMBER = "pr_number"

# The park flag both roads here read and write, spelled beside the pull
# request for the same reason: the tail below is reached from a reviewer's
# approval and from a recovery a park is already standing over.
_AWAITING_HUMAN = "awaiting_human"

# Where a failed squash left the branch, spelled as the park comment reads it:
# what an operator does next differs entirely by which of the four it is.
_LEFT_INTACT = (
    "the original commits are still on the branch and the PR was not "
    "relabeled. Manual intervention needed (squash + force-push by hand, or "
    "set `SQUASH_ON_APPROVAL=off` and re-run the reviewer)."
)


_LEFT_COLLAPSED = (
    "this issue records a squash it could not finish, so the branch is NOT "
    "standing on the commits the reviewer approved and the PR was not "
    "relabeled. Nothing was discarded -- that history is still reachable from "
    "the head the record names, in the reflog. Reconcile the branch (or "
    "repair the pinned comment) and the next tick finishes the recorded "
    "squash; `SQUASH_ON_APPROVAL=off` does not undo one that already ran."
)


_LEFT_BURIED = (
    "this issue records a squash it could not finish and the branch has grown "
    "PAST the head that record names, so nothing was rewritten and the PR was "
    "not relabeled. The commits the reviewer approved are still in this "
    "branch's own history, under whatever was committed on top of them -- not "
    "in the reflog. Reconcile the branch (or repair the pinned comment) and "
    "the next tick answers from what it finds."
)


_LEFT_UNKNOWN = (
    "nothing here can say where that leaves the branch -- the record it "
    "carries, the head that record names, or the head the checkout is "
    "standing on is not one this tick could account for -- so the commits the "
    "reviewer approved are neither shown to be at HEAD nor shown to be off "
    "it, and the PR was not relabeled. Nothing was discarded and nothing was "
    "pushed. Reconcile the checkout (or repair the pinned comment) and the "
    "next tick answers from what it finds; `SQUASH_ON_APPROVAL=off` does not "
    "undo a squash that already ran."
)


# The notice each of the four readings earns. Spelled as a mapping rather
# than a chain of tests, because the reading is the squash owner's and this
# stage's only job with it is to say the right sentence.
_LEFT = MappingProxyType({
    _publication.BRANCH_INTACT: _LEFT_INTACT,
    _publication.BRANCH_COLLAPSED: _LEFT_COLLAPSED,
    _publication.BRANCH_BURIED: _LEFT_BURIED,
    _publication.BRANCH_UNKNOWN: _LEFT_UNKNOWN,
})


def _squash_notice_posted(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    pr_number,
    squashed_count: int,
) -> bool:
    """Tell the pull request how much history the force-push replaced.

    Nothing is owed where nothing was collapsed, which is every branch that
    reached approval with one commit on it -- and every tick that finished a
    collapse an earlier one already announced. An issue with no pull request
    has nowhere to say it.

    A post that fails answers False rather than being swallowed, because the
    count behind it is recoverable state: it is on the pinned record of the
    collapse, and the caller keeps that record rather than dropping it over an
    announcement that never went out.
    """
    if pr_number is None or squashed_count <= 1:
        return True
    try:
        _comments._post_pr_comment(
            gh, int(pr_number), state,
            f":package: squashed {squashed_count} commits to 1",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post squash notice to PR #%s; leaving the "
            "collapse recorded so a later tick can announce it",
            issue.number, pr_number,
        )
        return False
    return True


def _park_squash_failure(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    error,
    standing: str = _publication.BRANCH_INTACT,
) -> None:
    """Park a squash that failed, saying where it left the branch.

    No two of the four are the same place and a human acts on the difference.
    The ordinary failure aborts before anything destructive or restores what
    it rewound, so the commits the reviewer approved are on the branch and
    squashing by hand starts from them. A failure taken over a collapse this
    tick could not finish leaves the branch standing on the squash -- the
    approved history is in the reflog and on the remote, not at HEAD -- so an
    operator told to squash it by hand would be looking for commits that are
    not there. A branch that grew PAST the recorded head is neither: nothing
    was rewritten, so those commits are in its own history under the work on
    top of them, and the reflog sentence would send that operator straight
    past them. And a failure the squash owner could not place at all says so,
    since named as any of the others it points somewhere nothing established.
    """
    if _parked_on_the_squash(state):
        # The notice is already on the thread and the condition behind it is
        # one only a human ends. The recovery retries every tick, so a fresh
        # mention here would be one per poll for an answer nobody can give
        # any faster.
        gh.write_pinned_state(issue, state)
        return
    left = _LEFT[standing]
    _guards._park_awaiting_human(
        gh,
        issue,
        state,
        f"{config.HITL_MENTIONS} squash-on-approval failed ({error}); {left}",
        reason=_state._REASON_SQUASH_FAILED,
    )
    # Re-set behind the guard, which clears whatever reason it found: this one
    # is durable, and it is what a later tick's re-entry is recognized by.
    state.set(_state._PARK_REASON, _state._REASON_SQUASH_FAILED)
    gh.write_pinned_state(issue, state)


def _parked_on_the_squash(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue is already parked on a squash that would not go."""
    return bool(
        state.get(_AWAITING_HUMAN)
        and state.get(_state._PARK_REASON) == _state._REASON_SQUASH_FAILED,
    )


def _squashed_and_handed_off(gate, branch: str) -> None:
    """Squash what the branch carries and hand the issue on, or stop.

    The whole of what an approval owes past the reviewer, and the whole of
    what a collapse an earlier tick did not finish owes without one: the same
    squash call, the same notice, the same watermarks, the same write, the
    same relabel. Both roads reach it because the answer is about the BRANCH
    rather than about which reading sent them -- a recovery that finished a
    landed collapse owes the pull request exactly the announcement the tick
    that made it would have posted, and the label it never moved.

    The subject the size gate decides about, and the branch the rewrite
    lands on, are handed in rather than rebuilt: each road already holds
    every part of them, and the checkout in particular is one only that road
    may decide -- a recovery reads the worktree where it stands and rebuilds
    it only where it is absent.

    The squash is reached on every approval, whatever `SQUASH_ON_APPROVAL`
    says. The switch decides whether a NEW collapse is made and the squash
    owner asks it there: a collapse an earlier tick already made has to be
    finished either way, and an issue with nothing recorded costs an install
    with the switch off no probe, no reading, and no write.

    The last two steps are ordered and neither is optional. The pinned write
    ends the collapse record and lands BEFORE the relabel, since past the
    label the issue belongs to a stage that never runs the squash recovery --
    and what it leaves in that record's place is the commit the relabel is
    owed over, so a move that does not land is the next tick's to make rather
    than the next reviewer's to re-review. And a notice this squash OWED and
    could not post stops the handoff outright: the count it is worded from
    lives on that record, so it is kept, the label stays, and the next tick
    finishes the collapse the remote already carries and announces it then.

    A park this recovery took over an earlier attempt ends here too. Reached
    from the recovery road, the issue may be standing on one -- the branch was
    reconciled or the comment repaired, and the retry is what proves it -- and
    an `awaiting_human` carried past the relabel would hold the issue in
    `documenting` over a condition nobody is waiting on any more.
    """
    gh, issue, state = gate.gh, gate.issue, gate.state
    squashed = _squash._squash_and_force_push(gate, branch)
    if squashed.held:
        # The gate owns the issue from here, and it owns it in one of two
        # shapes. Routed, the squashed commit is on the branch, the label is
        # the adjudication's, and an authorized settlement publishes it -- so a
        # `_park_squash_failure` over that would post a notice about a failure
        # that did not happen and put `awaiting_human` on an issue an agent is
        # about to run for. PARKED, the gate has already worded the notice its
        # own reading earned and left the flags in memory for whoever ran it.
        # The write is this caller's either way: the routed hold made its own
        # and this one changes nothing, while the park has nothing behind it
        # to carry the flags to the pinned comment -- and an issue left with a
        # frozen candidate, no `awaiting_human`, and no `park_reason` is one
        # every later tick re-runs the reviewer on.
        gh.write_pinned_state(issue, state)
        return
    if not squashed.success:
        _park_squash_failure(
            gh, issue, state, squashed.error, standing=squashed.standing,
        )
        return
    pr_number = state.get(_PR_NUMBER)
    if not _squash_notice_posted(gh, issue, state, pr_number, squashed.count):
        # The notice this collapse owed did not go out, and the count behind
        # it is on the record the next tick would drop. Keep it, persist what
        # did land, and leave the label here: the recovery republishes the
        # commit the remote already carries and words the notice again.
        gh.write_pinned_state(issue, state)
        return
    # Behind the notice on purpose: the snapshot the seed is read off carries
    # the notice's own id, so the walk steps past it. Seeded ahead of the post
    # instead, that notice would reach in_review as fresh human PR feedback
    # and wake the dev on an informational orchestrator post.
    _handoff._seed_in_review_handoff_watermarks(gh, issue, state, pr_number)
    # A squash that finished ends the park it took: the branch is published
    # and the label is about to move, so an `awaiting_human` carried into
    # `documenting` would hold an issue over a condition that is answered.
    state.set(_AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    _persists_then_relabels(gh, issue, state, squashed.sha)


def _persists_then_relabels(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, sha,
) -> None:
    """Land everything this handoff owes durably, and only then move the label.

    The rewrite is over and announced, so what stays on the comment is not a
    claim any more but the commit the move behind this write is owed over.
    Dropped outright, a relabel that does not land would leave an issue on
    `validating` with nothing saying a squash ever ran -- and the next tick
    spawns a second reviewer over a branch this stage already published.

    Everything the caller staged rides the same write: the watermarks seeded
    behind the notice, and the end of a park this recovery may have taken over
    an earlier attempt.
    """
    _collapses.settle_pending_collapse(state, sha)
    gh.write_pinned_state(issue, state)
    _hands_to_documenting(gh, issue, state)


def _hands_to_documenting(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    """Move the label a finished handoff owes, and end the record of it.

    The last step of both roads, and the only one with nothing durable behind
    it: the notice, the watermarks, and the settled record all landed in the
    write ahead of this call. What that write left is the commit this move is
    owed over, so a relabel that does not land is not raised past here -- the
    tick ends, and the recovery ahead of the next reviewer moves the label
    instead of a second review being run over a published branch. Raised, the
    same state would reach the tick loop as a failed issue and the retry would
    be the reviewer's.

    The record goes in a write of its own, BEHIND the label rather than ahead
    of it, because it is the label that it is about. Nothing else reads it: an
    approval that collapsed nothing leaves none, and there is nothing to end
    or to write there.
    """
    try:
        gh.set_workflow_label(issue, WorkflowLabel.DOCUMENTING)
    except Exception:
        log.exception(
            "issue=#%s could not relabel to documenting behind a finished "
            "squash; leaving the handoff recorded for the next tick",
            issue.number,
        )
        return
    if not _late_handoffs.read_settled_handoff(state):
        return
    _late_handoffs.clear_settled_handoff(state)
    gh.write_pinned_state(issue, state)


def _finalize_validating_approval(
    gate, reviewer_run: _models._ReviewerRun, branch: str,
) -> None:
    """Finalize an approved review: verify gate, approval comment, optional
    squash, in_review handoff watermarks, then relabel to `documenting`.

    The verify gate is the first gate after the reviewer so an obviously-broken
    branch never reaches `in_review` (GitHub CI still runs against the PR for
    the human merging it). Default-empty `VERIFY_COMMANDS` short-circuits to
    "ok". A failed / timed-out command or a dirty tree left behind parks
    awaiting_human in `validating` with a stable `park_reason`. A failed
    squash / force-push also parks and STAYS in `validating` (no relabel), and
    its notice says which of the two places it left the branch: the original
    commits, or a collapse an earlier tick could not finish. On success the
    (possibly squashed) head routes through `documenting` for a final docs
    pass before in_review picks up; the watermarks, approval, and squash
    comment seeded here are preserved across the documenting hop.

    The squash and everything behind it are the tail beside this one, because
    a collapse an earlier tick did not finish owes the same steps with no
    reviewer having run: what the branch is owed does not depend on which
    reading sent the tick -- which is why the gate and the branch arrive here
    already built, from whichever road did the deciding.
    """
    gh, issue, state = gate.gh, gate.issue, gate.state
    verify = _verify_runner._run_verify_commands(
        reviewer_run.wt, config.VERIFY_COMMANDS, config.VERIFY_TIMEOUT,
    )
    if verify.status != "ok":
        _verify._park_verify_failure(gh, issue, state, verify)
        gh.write_pinned_state(issue, state)
        return
    _handoff._post_approval_comment(gh, issue, state, reviewer_run)
    _squashed_and_handed_off(gate, branch)
