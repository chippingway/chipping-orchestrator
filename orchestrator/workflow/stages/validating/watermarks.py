# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The walk an approval's in_review watermarks are seeded off.

`handoff` is what writes them; this owner answers the one question that write
is made from -- how far past the leading run of the orchestrator's own
comments a watermark may go.

in_review wakes on "PR feedback newer than the watermark" and pings a human
that the PR is ready for merge. So the value answered here decides two ways
to be wrong: too low replays the orchestrator's own pickup ping, "PR opened",
approval, and squash notices as human feedback and resumes the dev on them;
too high advertises the PR as ready over a human comment nobody read. The
walk therefore advances only through the leading run of orchestrator-authored
comments plus the issue-thread ids a dev resume already consumed, and stops at
the first comment that is neither. A bare `/orchestrator add-agent-runs` is
walked past as well: it is an operator control, never feedback, and a grant can
leave it unread above the reply its park interrupted.

Self-authorship is decided by recorded id OR by the hidden body marker,
because either alone is wrong in a way that loses feedback: the id set is
bounded and evicts, and a login check would drop a human reviewer who shares
the PAT's account. The pickup comment is the boundary the walk starts from --
everything older ON THE ISSUE THREAD is chatter the dev agent already saw at
spawn -- and its absence is answered by refusing to advance at all. The pull
request is outside that boundary: one a plan handoff reused or a human opened
carries conversation numbered below the pickup that no spawn ever quoted, so
being old is no evidence there that anybody read it.

Stopping is allowed to strand the value low, and that is the half this owner
does not have to solve. The walk stops at the first unseen human comment on
EITHER surface, so an unread PR-conversation comment numbered below a reply
the dev already answered holds the seed underneath both -- and in_review then
reads the issue thread against `last_action_comment_id` as well
(`in_review/surfaces.py`), which is what drops the answered reply without a
watermark having to hide the PR comment to do it.

`_ratchet_watermark` closes the loop with the value already persisted: an
earlier in_review tick may have advanced past feedback the dev has since
fixed, and the seed walk deliberately stops short of it, so the two are
combined by max rather than overwritten. It answers rather than writes too --
the caller in `handoff` is what puts the result on the pinned comment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    run_grant_request as _run_grant_request,
)


def _watermark_comment_pairs(
    issue_comments: list, pr_comments: list,
) -> list[tuple[Any, bool]]:
    return sorted(
        [(comment, True) for comment in issue_comments]
        + [(comment, False) for comment in pr_comments],
        key=lambda pair: pair[0].id,
    )


def _is_orchestrator_comment(comment, orchestrator_ids: set[int]) -> bool:
    return (
        comment.id in orchestrator_ids
        or _comments._ORCH_COMMENT_MARKER in (getattr(comment, "body", None) or "")
    )


@dataclass
class _WatermarkWalker:
    orchestrator_ids: set[int]
    pickup_comment_id: int
    consumed_through: int | None
    watermark: int | None = None
    seen_self: bool = False

    def consume(self, comment, is_issue_thread: bool) -> bool:
        is_self = _is_orchestrator_comment(comment, self.orchestrator_ids)
        # Both exemptions below are the issue thread's alone. The spawn quotes
        # that thread, and `_resume_developer_on_human_reply` reads only it, so
        # a comment on the pull request is vouched for by neither -- the PR may
        # be one a plan handoff reused or a human opened, carrying conversation
        # numbered below the pickup that no prompt has ever included.
        pre_pickup = (
            is_issue_thread
            and not self.seen_self
            and comment.id < self.pickup_comment_id
        )
        already_consumed = (
            is_issue_thread
            and self.consumed_through is not None
            and comment.id <= self.consumed_through
        )
        if is_self:
            self.watermark = comment.id
            self.seen_self = True
        elif (
            pre_pickup
            or already_consumed
            or _run_grant_request._is_bare_command(comment)
        ):
            self.watermark = comment.id
        else:
            return False
        return True


def _seed_watermark_past_self(
    issue_thread_comments: list,
    pr_conversation_comments: list,
    orchestrator_ids: set[int],
    pickup_comment_id: int | None,
    consumed_through: int | None = None,
) -> int | None:
    """Seed the in_review handoff watermark.

    Walk comments oldest-to-newest across both surfaces (issue thread and
    PR conversation share the IssueComment id space, so a single watermark
    covers both). The pickup comment is the boundary: everything before
    `pickup_comment_id` ON THE ISSUE THREAD is pre-pickup chatter the dev
    agent already saw at spawn, so it can be advanced past -- a
    PR-CONVERSATION comment that old is not, since the pull request may be one
    a plan handoff reused or a human opened and no spawn quotes it. From the
    pickup forward, advance
    through the contiguous run of orchestrator-authored comments AND
    through any ISSUE-THREAD comment with id <= `consumed_through` (already
    fed to the dev agent via a prior `_resume_developer_on_human_reply`
    call during implementing/validating), stopping at the first
    not-yet-consumed non-orchestrator comment. This preserves human
    feedback posted during validating that the dev has not yet seen. The
    replay of what the dev HAS consumed is answered twice over: here, by
    walking past it, and again by the in_review and fixing scans, which drop
    issue-thread comments at or below `last_action_comment_id` whatever this
    walk settled on -- so a walk stopped low by an unread PR comment costs
    nothing. A bare
    `/orchestrator add-agent-runs` is walked past on either surface: it is a
    control, never feedback, and a grant can leave one unread.

    Neither the pickup boundary nor `consumed_through` is applied to
    PR-conversation comments, for one reason: nothing that sets either has
    read that surface. The spawn quotes the issue thread, and
    `last_action_comment_id` only records issue-thread ids fed via
    `_resume_developer_on_human_reply` (validating/implementing watch the
    issue thread only). So a PR-conversation comment numbered below the
    pickup, or below a later-consumed issue-thread reply, has NOT been seen
    by the dev and must surface on the next in_review tick. Folding either
    check across both surfaces would let the in_review HITL ready-ping
    advertise the PR as ready for human merge over unread PR-conversation
    feedback.

    Identification of orchestrator-authored content is by exact comment id
    (recorded when the orchestrator posted the comment) OR by the hidden
    body marker `_ORCH_COMMENT_MARKER` -- mirroring the in_review feedback
    filter. The id-only check would mis-treat a bot comment whose id was
    evicted from the bounded `orchestrator_comment_ids` cap (or never
    persisted due to a state-write race) as a human comment, stopping the
    walker early and stranding the watermark at a low value: the next
    in_review tick would then re-scan the same orchestrator content on
    every poll (the in_review filter still drops it via the marker, but
    the walker should not amplify that cost), and once a real human
    comment lands ABOVE the orchestrator backlog the seed walker would
    keep yielding a stale watermark indefinitely. The login-based check
    would also drop comments authored by a human reviewer who shares the
    PAT's GitHub account -- a common deployment shape -- causing real
    review feedback to be silently dropped and the PR to be pinged ready
    for human merge over it.

    Returns None when the pickup id is unknown (legacy state from a deploy
    that pre-dates pickup-id tracking, or a manually-relabeled issue) or
    when the surface has no orchestrator-authored content. The caller then
    defaults the watermark to 0 so the in_review legacy migration cannot
    advance past historical content; the orchestrator_comment_ids id-set
    filter in `_handle_in_review` drops recorded bot comments at scan time.
    """
    if pickup_comment_id is None:
        # Legacy state without a pickup anchor: refuse to advance. We
        # cannot tell pre-pickup chatter (safe to skip) from human feedback
        # posted during implementing/validating (must preserve), and
        # dropping a human comment is the unsafe direction.
        return None
    # Tag each comment with its surface so the walk below can apply
    # `consumed_through` to the issue thread only.
    comment_pairs = _watermark_comment_pairs(
        issue_thread_comments, pr_conversation_comments,
    )
    if not any(
        _is_orchestrator_comment(comment, orchestrator_ids)
        for comment, _ in comment_pairs
    ):
        return None
    walker = _WatermarkWalker(
        orchestrator_ids, pickup_comment_id, consumed_through,
    )
    for comment, is_issue_thread in comment_pairs:
        if not walker.consume(comment, is_issue_thread):
            break
    return walker.watermark


def _latest_pr_comment_ids(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState
) -> tuple[int | None, int | None]:
    """Return (issue-comment watermark, review-comment watermark) seeded only
    past leading orchestrator-authored comments on the issue thread + PR.

    The second value is always None: the orchestrator never posts inline PR
    review comments, so there is no leading self-run to advance past on
    that surface, and `orchestrator_comment_ids` records IDs in the
    IssueComment namespace only -- feeding it to `_seed_watermark_past_self`
    against the PullRequestComment namespace would falsely treat a human
    inline comment whose numeric id collides with a recorded bot id as
    self-authored, advancing the watermark past the human's feedback. The
    `handoff` caller defaults the inline-review watermark to 0 when this
    returns None so the in_review legacy migration cannot then advance past
    human inline feedback either.
    """
    orchestrator_ids = _comments._orchestrator_ids(state)
    # `last_action_comment_id` doubles as a "consumed through" marker:
    # both park comments and post-resume bumps land here, so any issue
    # comment with id <= this value has either been posted by the
    # orchestrator (filtered by `orchestrator_comment_ids`) or already
    # been fed to the dev session (must not replay).
    # Keep the surfaces separate -- `consumed_through` only applies to the
    # issue thread (the surface `_resume_developer_on_human_reply` watches
    # during implementing/validating). Folding both into one list and
    # applying `c.id <= consumed_through` uniformly would silently advance
    # the watermark past unread PR-conversation feedback whose id happens
    # to be lower than a later-consumed issue-thread reply, letting the
    # in_review HITL ready-ping advertise the PR as ready for human
    # merge over the human's PR comment.
    issue_thread = list(gh.comments_after(issue, None))
    pr_conversation = list(gh.pr_conversation_comments_after(pr, None))
    return (
        _seed_watermark_past_self(
            issue_thread, pr_conversation,
            orchestrator_ids, _state_int(state, "pickup_comment_id"),
            consumed_through=_state_int(state, "last_action_comment_id"),
        ),
        None,
    )


def _state_int(state: PinnedState, key: str) -> int | None:
    state_value = state.get(key)
    return state_value if isinstance(state_value, int) else None


def _ratchet_watermark(prev, seeded):
    """Combine a previously-persisted in_review watermark with a freshly-seeded
    one, never moving backward.

    A prior in_review tick may have already advanced the persisted watermark
    past PR feedback the dev has since fixed; `_seed_watermark_past_self` stops
    at the first post-pickup human comment, so without the max() that consumed
    comment would replay as "new". Returns the max of the two when both are
    present, the one that exists otherwise, or 0 when neither does -- 0 means
    "scan all from the beginning" and marks the surface as already seeded so the
    in_review legacy migration does not advance past historical human feedback.
    """
    if isinstance(prev, int):
        return prev if seeded is None else max(seeded, prev)
    return 0 if seeded is None else seeded
