# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The walk every in_review watermark is seeded or initialized off.

`handoff` seeds the approval's watermarks with it, documenting's completion
ratchets through it, and in_review initializes a watermark it finds unset
with it (`in_review/watermarks.py`); this owner answers the one question all
three are made from -- how far a watermark may go without crossing feedback
no run received.

in_review wakes on "PR feedback newer than the watermark" and pings a human
that the PR is ready for merge. So the value answered here decides two ways
to be wrong: too low replays the orchestrator's own pickup ping, "PR opened",
approval, and squash notices as human feedback and routes the issue to
`fixing` over them; too high advertises the PR as ready over a human comment
nobody read. The walk therefore advances only through comments a record
proves nobody is owed, and stops at the first it cannot vouch for: a post
this orchestrator can prove it wrote, an issue-thread comment inside the
stretch of the thread developer prompts were handed (`engine/thread_delivery`:
above the newest comment the first prompt's bounded excerpt left out, through
the newest a prompt quoted), and a bare `/orchestrator add-agent-runs`, an
operator control rather than feedback, which a grant can leave unread above
the reply its park interrupted.

Nothing else is evidence. Age is not: the issue thread is crossed only as far
as that delivered stretch says, and the pull request not at all -- one a plan
handoff reused or a human opened carries conversation, numbered below the
pickup, that no prompt ever quoted. Nor is the reply boundary: a pickup or a
handoff stands it past the thread without handing it to anybody, a park
stamps it over what a human wrote while the agent was out, and a bounded
first prompt drops the oldest comments, which stay unread. A record carrying
no delivered stretch -- an issue a human labeled straight into a review
stage -- proves only the orchestrator's own posts and the controls, so the
walk stops at the first human comment and the scan behind it reads everything
from there.

The two surfaces cannot be read at one moment, so the snapshot itself is
bounded. A comment landing on the surface read first, after that read, is in
neither, while one numbered above it can land on the surface read second and
be in the snapshot -- a bare control typed into the pull request a moment
after a human's issue reply, say. A walk crossing that control would carry the
mark over the reply it never saw. So nothing is crossed above what the
snapshot proves complete (`thread_delivery.known_through`): the newest comment
the first read carries, or an id a record named before either read began,
since every comment numbered at or below one that already existed is in one
of the two reads.

Self-authorship is decided by recorded id OR by the hidden body marker,
because either alone is wrong in a way that loses feedback: the id set is
bounded and evicts, and a login check would drop a human reviewer who shares
the PAT's account.

Stopping is allowed to strand the value low, and that is the half this owner
does not have to solve. The walk stops at the first unseen human comment on
EITHER surface, so an unread PR-conversation comment numbered below a reply
the dev already answered holds the seed underneath both -- and in_review then
reads the issue thread against its delivered stretch as well
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
    thread_delivery as _thread_delivery,
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
    delivered: _thread_delivery.DeliveredThread
    known_through: int | None
    watermark: int | None = None

    def consume(self, comment, is_issue_thread: bool) -> bool:
        if self.known_through is None or comment.id > self.known_through:
            return False
        # The delivered stretch is the issue thread's alone. Every prompt it
        # records quotes that thread, so a comment on the pull request is
        # vouched for by nothing it says -- the PR may be one a plan handoff
        # reused or a human opened, carrying conversation numbered inside the
        # stretch that no prompt has ever included.
        already_delivered = is_issue_thread and self.delivered.covers(comment.id)
        if not (
            already_delivered
            or _is_orchestrator_comment(comment, self.orchestrator_ids)
            or _run_grant_request._is_bare_command(comment)
        ):
            return False
        self.watermark = comment.id
        return True


def _seed_watermark_past_self(
    issue_thread_comments: list,
    pr_conversation_comments: list,
    orchestrator_ids: set[int],
    delivered: _thread_delivery.DeliveredThread | None = None,
    known_through: int | None = None,
) -> int | None:
    """How far an in_review watermark may go over this snapshot, or None.

    Walk comments oldest-to-newest across both surfaces (issue thread and
    PR conversation share the IssueComment id space, so a single watermark
    covers both), advancing through the orchestrator's own posts, through any
    ISSUE-THREAD comment `delivered` covers (`thread_delivery.DeliveredThread`:
    quoted into a developer prompt already), and through a bare
    `/orchestrator add-agent-runs` on either surface, and stopping at the
    first comment that is none of them. This preserves human feedback posted
    during validating that no developer has seen, and context a bounded
    prompt left out. The replay of what the dev HAS consumed is answered twice
    over: here, by walking past it, and again by the in_review and fixing
    scans, which drop the issue-thread comments the stretch covers whatever
    this walk settled on -- so a walk stopped low by an unread PR comment
    costs nothing. None covers nothing.

    `delivered` is not applied to PR-conversation comments, for one reason:
    nothing that records it has read that surface. The spawn and the
    implementing and validating resumes quote the issue thread alone, so a
    PR-conversation comment numbered below a consumed issue-thread reply has
    NOT been seen by the dev and must surface on the next in_review tick.
    Folding the check across both surfaces would let the in_review HITL
    ready-ping advertise the PR as ready for human merge over unread
    PR-conversation feedback.

    Identification of orchestrator-authored content is by exact comment id
    (recorded when the orchestrator posted the comment) OR by the hidden
    body marker `_ORCH_COMMENT_MARKER` -- mirroring the in_review feedback
    filter. The id-only check would mis-treat a bot comment whose id was
    evicted from the bounded `orchestrator_comment_ids` cap as a human
    comment, stopping the walker early and stranding the watermark at a low
    value: the next in_review tick would then re-scan the same orchestrator
    content on every poll (the in_review filter still drops it via the
    marker, but the walker should not amplify that cost). The login-based
    check would also drop comments authored by a human reviewer who shares
    the PAT's GitHub account -- a common deployment shape -- causing real
    review feedback to be silently dropped and the PR to be pinged ready for
    human merge over it.

    `known_through` is how far the two reads together are proved complete
    (`thread_delivery.known_through`), and nothing above it is crossed
    whatever it is: a comment there may sit above one the surface read first
    never carried. None proves nothing complete, and the walk crosses
    nothing.

    Returns None when the walk crosses nothing -- a snapshot with no comments,
    or one whose oldest comment nothing vouches for. The caller then answers
    0 (`_ratchet_watermark`), which scans the surface from its beginning.
    """
    walker = _WatermarkWalker(
        orchestrator_ids, delivered or _thread_delivery.DeliveredThread(None, None), known_through,
    )
    for comment, is_issue_thread in _watermark_comment_pairs(
        issue_thread_comments, pr_conversation_comments,
    ):
        if not walker.consume(comment, is_issue_thread):
            break
    return walker.watermark


def _latest_pr_comment_ids(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState
) -> tuple[int | None, int | None]:
    """Return (issue-comment watermark, review-comment watermark) walked only
    past what the issue's records prove nobody is owed.

    The second value is always None: the orchestrator never posts inline PR
    review comments, so there is no leading self-run to advance past on
    that surface, and `orchestrator_comment_ids` records IDs in the
    IssueComment namespace only -- feeding it to `_seed_watermark_past_self`
    against the PullRequestComment namespace would falsely treat a human
    inline comment whose numeric id collides with a recorded bot id as
    self-authored, advancing the watermark past the human's feedback. The
    `handoff` caller turns that None into 0, a scan of the inline-review
    surface from its beginning.
    """
    orchestrator_ids = _comments._orchestrator_ids(state)
    # The delivered stretch is what the issue thread's developer prompts were
    # handed: a comment inside it has either been posted by the orchestrator
    # or already been fed to the dev session (must not replay), and one the
    # first prompt's bound cut stays outside it.
    # Keep the surfaces separate -- the stretch only applies to the issue
    # thread (the surface the spawn and the implementing and validating
    # resumes quote). Folding both into one list and applying it uniformly
    # would silently advance the watermark past unread PR-conversation
    # feedback whose id happens to be lower than a later-consumed issue-thread
    # reply, letting the in_review HITL ready-ping advertise the PR as ready
    # for human merge over the human's PR comment.
    delivered = _thread_delivery.DeliveredThread.read(state)
    # The issue thread is read FIRST, which is what `known_through` bounds the
    # snapshot by.
    issue_thread = list(gh.comments_after(issue, None))
    pr_conversation = list(gh.pr_conversation_comments_after(pr, None))
    return (
        _seed_watermark_past_self(
            issue_thread, pr_conversation, orchestrator_ids,
            delivered=delivered,
            known_through=_thread_delivery.known_through(issue_thread, *delivered.recorded(), *orchestrator_ids),
        ),
        None,
    )


def _ratchet_watermark(prev, seeded):
    """Combine a previously-persisted in_review watermark with a freshly-seeded
    one, never moving backward.

    A prior in_review tick may have already advanced the persisted watermark
    past PR feedback the dev has since fixed; `_seed_watermark_past_self` stops
    at the first human comment no delivery record covers, so without the max()
    that consumed comment would replay as "new". Returns the max of the two
    when both are present, the one that exists otherwise, or 0 when neither
    does -- 0 scans the surface from its beginning, the lower bound that
    crosses nothing, and marks it as initialized so no later tick takes it
    for one that still needs a walk.
    """
    if isinstance(prev, int):
        return prev if seeded is None else max(seeded, prev)
    return 0 if seeded is None else seeded
