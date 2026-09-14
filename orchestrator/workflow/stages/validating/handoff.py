# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an approved review posts on its pull request, and what it seeds after.

Two of the three writes an approval puts on the thread are here -- the
reviewer's verdict, and the watermarks that follow the squash notice the
caller posts. The watermarks are what keep the other two from being read back
as human feedback: in_review wakes on "PR feedback newer than the watermark",
so an approval that posted and seeded nothing would hand the next stage the
orchestrator's own announcements as fresh review and wake the dev on them.

The seed is two owners because it answers two different questions. The
snapshot half is about a read that can fail: taken behind the notice so the
walk steps past the notice's own id, and abandoned outright where the pull
request will not answer, since in_review still has its legacy watermark to
fall back on and an approved branch may not be stranded on a read. The ratchet
half is reached only past that, and answers what each of the three watermarks
becomes against what is already persisted.

The approval comment is the one post nothing is owed for. It carries no count,
nothing later reads it back, and a thread that would not take it is no reason
to hold a verified branch out of `documenting` -- so its failure is logged and
the road carries on.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import (
    models as _models,
    watermarks as _watermarks,
)

log = logging.getLogger("orchestrator.workflow")


def _post_approval_comment(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
) -> None:
    if reviewer_run.pr_number is None:
        return
    try:
        _comments._post_pr_comment(
            gh,
            int(reviewer_run.pr_number),
            state,
            f":white_check_mark: {config.REVIEW_AGENT} review approved.",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post approval to PR #%s",
            issue.number,
            reviewer_run.pr_number,
        )


def _seed_in_review_handoff_watermarks(
    gh: GitHubClient, issue: Issue, state: PinnedState, pr_number,
) -> None:
    """Take the snapshot the seed below is read off, or leave it unseeded.

    The caller runs this BEHIND the squash notice, so the snapshot carries
    that notice's own id and the walk steps past it. Taken ahead of the post,
    the notice would land above every watermark seeded here and reach
    in_review as fresh human PR feedback, waking the dev on an informational
    orchestrator post.

    A `get_pr` that will not answer is not fatal. in_review falls back to its
    legacy watermark, so the snapshot is abandoned and nothing is seeded
    rather than an approved branch being stranded on a read.
    """
    if pr_number is None:
        return
    try:
        pr = gh.get_pr(int(pr_number))
    except Exception as error:  # noqa: BLE001 - an unreadable PR falls back to the legacy watermark
        # Surface the failure but skip the traceback -- it adds no signal.
        log.warning(
            "issue=#%s could not snapshot PR #%s for in_review "
            "handoff: %s", issue.number, pr_number, error,
        )
        return
    _seed_in_review_pr_watermarks(gh, issue, state, pr)


def _seed_in_review_pr_watermarks(
    gh: GitHubClient, issue: Issue, state: PinnedState, pr,
) -> None:
    """Park the three in_review watermarks past this snapshot's leading run of
    orchestrator-authored comments.

    The seed keeps `_handle_in_review` from replaying the orchestrator's own
    automated comments ("picking this up", "PR opened", the approval just
    posted, the squash notice) as fresh PR feedback once the debounce expires.
    Concurrent human feedback posted during the prior stage is preserved:
    `_latest_pr_comment_ids` stops the seed walk at the first unread
    non-orchestrator comment, and `_ratchet_watermark` never regresses a
    watermark a prior in_review tick already advanced.

    Inline review comments and review summaries live in namespaces the
    orchestrator never posts on, so the inline surface answers None and there
    is no seeded summary value; `_ratchet_watermark` defaults each to 0 so the
    in_review legacy migration treats them as already seeded and does NOT
    advance past human feedback submitted on those surfaces.
    """
    issue_wm, review_wm = _watermarks._latest_pr_comment_ids(gh, issue, pr, state)
    state.set(
        "pr_last_comment_id",
        _watermarks._ratchet_watermark(state.get("pr_last_comment_id"), issue_wm),
    )
    state.set(
        "pr_last_review_comment_id",
        _watermarks._ratchet_watermark(state.get("pr_last_review_comment_id"), review_wm),
    )
    state.set(
        "pr_last_review_summary_id",
        _watermarks._ratchet_watermark(state.get("pr_last_review_summary_id"), None),
    )
