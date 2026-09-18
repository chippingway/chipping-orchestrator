# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one write every ending of this stage reaches the issue through.

A discussion tick has exactly one kind of ending -- awaiting a human -- so what
differs between the endings is only what the comment says and which reason it
is recorded under. That reason is load-bearing beyond the message: the handler
reads its `discussion_` prefix back on the next tick to decide whose turn it
is, so a park that skipped this funnel would read as a park some other stage
wrote and earn a second round over the top of the first. Stamping it here
rather than at each ending is what makes that structural instead of a rule the
three park owners beside this module have to remember.

The funnel exists because the shared park helper clears `park_reason`: the
stage-specific reason has to be restored after it and persisted, which is also
where the round's staged records finally land.

It is where the record a park emits picks up its identifiers too, and for the
same reason the reason is stamped here: the endings differ in what they say and
in what they found, never in whose conversation they belong to. Assembling that
payload at each of them would be one copy per ending of an answer pinned state
already holds once.

What that payload will and will not call this stage's own is the whole of the
care in it. A pinned pull request number is not evidence of a plan -- an issue
relabeled here from a PR stage arrives carrying its dev's -- and the artifact
commit is recorded under two keys that can both be standing at once, only one
of which is a claim about what this tick is doing.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.discussion import models as _models, state as _state


def _park_discussion(
    run: _models._DiscussionRun, message: str, *, reason: str,
) -> None:
    """Park the issue awaiting human under the discussion-stage reason.

    The shared park helper clears `park_reason`, so this funnel restores the
    stage-specific one and persists the completed state mutation -- the single
    durable write every route in this stage reaches the issue through.

    It also stamps `last_action_comment_id` at the id of the notice it just
    posted, which this funnel restores for the same kind of reason. That stamp
    is right for a stage whose park ENDS the exchange, but a discussion's park
    is an invitation to answer it, and minutes of agent run separate the thread
    the round read from the thread the notice lands on top of. Anything posted in that
    window -- a human's second thought, an outsider's comment the allowlist may
    later admit -- would be recorded as read by a round that never saw it, and
    nothing here reads a comment twice. What the round did read it has already
    staged, so restoring the value this call was entered with is exactly the
    ceiling to keep. The comment just posted needs no watermark to be skipped:
    `_new_trusted_replies` knows the stage's own messages by id and marker.
    """
    consumed_through = run.state.get(_state._LAST_ACTION_COMMENT_ID)
    _guards._park_awaiting_human(
        run.gh, run.issue, run.state, message,
        reason=reason,
        **_discussion_correlation(run),
    )
    run.state.set(_state._PARK_REASON, reason)
    run.state.set(_state._LAST_ACTION_COMMENT_ID, consumed_through)
    # A park IS the report a round owes, so it is what ends the window the
    # open flag marks. Cleared here rather than at each ending, because every
    # one of them lands on this funnel and a flag left standing would have the
    # next tick attribute somebody else's commit to a round already answered.
    run.state.set(_state._ROUND_OPEN, None)
    run.gh.write_pinned_state(run.issue, run.state)


def _discussion_correlation(run: _models._DiscussionRun) -> dict[str, Any]:
    """The bounded identifiers a discussion park reports beside its reason.

    Every one of them is a structured identifier the tick already holds -- the
    road it took, the role its agent answers under, the conversation this
    issue's discussion belongs to, and the pull request and commit a
    publication has already written down. Nothing is read out of what the agent
    said: the reason is already this stage's own closed vocabulary, while a
    payload assembled from a round's analysis would carry the design argument
    itself into the audit log and the analytics sink both.

    A `None` is a field this issue has never held, and both sinks drop it. That
    is most of what a park here reports: the parks taken before a round has ever
    run carry no session and no artifact at all -- which is exactly the
    difference an operator counting these needs the record to show rather than
    a null to be read around.
    """
    return _guards._screened_correlation({
        "route": run.route,
        "agent_role": _state._DECOMPOSER_ROLE,
        "session_id": run.state.get(_state._DISCUSSION_SESSION_KEY) or None,
        "pr_number": _plan_pr_number(run.state),
        "sha": _artifact_sha(run.state),
    })


def _plan_pr_number(state: PinnedState) -> int | None:
    """The pull request this conversation's plan is on, and only ever that one.

    A bare `pr_number` is not this stage's to report. An issue relabeled here
    from a PR stage arrives carrying its dev's, which is precisely why the
    round gate reads the pair rather than the number -- and a park correlated
    to that number would name a pull request this conversation never opened
    and has agreed nothing on, in the one sink an operator goes to to find out
    which waits belong to which work. So the pair is asked for exactly as
    `_plan_published` asks it, and a round opened on an inherited branch
    reports no number at all.
    """
    if not _state._plan_published(state):
        return None
    return _guards._safe_int(state.get(_state._PR_NUMBER))


def _artifact_sha(state: PinnedState) -> str | None:
    """The commit this stage's artifact stands on, in flight or published.

    A marker standing answers first, because it is the only one of the two
    that is a claim about now: it names the commit a publication is in the
    middle of, and the parks that find it standing are the ones whose whole
    subject is that commit -- a push that failed, a lease the remote refused,
    a tip the branch has moved off. Each of them asks an operator to restore
    or go looking for exactly the SHA it names.

    Which matters because the two records really can both be standing. The
    implementing handoff retires `discussion_plan_path` and deliberately KEEPS
    `discussion_plan_sha`, since that commit is what answers for the pull
    request once the path is gone. An issue relabeled back here therefore
    opens its next round with a previous plan's commit still pinned, and a
    publication of the NEW one, read off the settled record, would park
    quoting the old -- pointing the operator at a commit the remedy has
    nothing to do with.

    The settled record answers wherever no marker stands, which includes the
    publication that has just finished: the write that records a plan retires
    the marker in the same breath.
    """
    return (
        state.get(_state._PUBLISHING_SHA)
        or state.get(_state._PLAN_SHA)
        or None
    )
