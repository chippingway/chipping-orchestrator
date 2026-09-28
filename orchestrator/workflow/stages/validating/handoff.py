# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an approved review posts on its pull request, what it seeds after, and what its writes are held to.

The three writes an approval puts on the thread are here -- the reviewer's
verdict, the squash notice, and the watermarks that follow that notice. The
watermarks are what keep the other two from being read back as human
feedback: in_review wakes on "PR feedback newer than the watermark", so an
approval that posted and seeded nothing would hand the next stage the
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

Every write an approval's tail makes -- the approval, its squash, the handoff
behind them, the park a failed squash takes -- follows requests of its own, and
each is held first to the report, evidence, and verdict records it was proved
over (`_holds_its_records`). Where they stand, the write is composed over the
comment read then: a field another road wrote meanwhile -- a round spent by a
reply -- is carried onto the state in hand rather than written back over. The
tail tells those apart from its own by the comment as it last read or wrote it
(`_Held`): another road's is a field the comment changed while the state in
hand did not, save the squash's own record of a collapse, which the squash
writes itself and drops only in memory for this tail's write to make durable.
Where the records moved, nothing the approval holds is written, but what every
post leaves on the ledger is owed all the same: the post is the
orchestrator's, and a prompt keeps an orchestrator comment only where that
ledger vouches for it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, report_record_state as _report_record_state
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
    watermarks as _watermarks,
)

log = logging.getLogger("orchestrator.workflow")

# The squash's own record of a collapse it began, which no other road's write
# puts on the comment: the squash writes it before it rewrites anything and
# drops it only in memory, leaving the drop to the tail's own write.
_SQUASH_RECORD = frozenset((
    _collapses.LATE_COLLAPSE_HEAD,
    _collapses.LATE_COLLAPSE_BASE_SHA,
    _collapses.LATE_COLLAPSE_COUNT,
))

# What every write the tail makes is held to: the report and returned-verdict
# records, and the verification evidence the approval was proved over.
_HELD_RECORDS = (*_review_comment._VERDICT_RECORDS, *_review_comment._EVIDENCE_RECORDS)


@dataclass
class _Held:
    """What an approval's tail holds across the requests and writes it makes.

    `verdict` is the returned verdict the approval behind the tail finishes,
    the only one any of its writes retires -- None on the recovery of a
    squash an earlier tick did not finish, which holds none. `comment` is the
    pinned comment as the tail last read or wrote it.
    """

    verdict: _verdicts.ReturnedVerdict | None
    comment: dict

    def wrote(self, state: PinnedState) -> None:
        """Take `state`, just written, as the comment the tail last wrote."""
        self.comment = dict(state.data)


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


def _squash_notice_posted(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pr_number,
    squashed_count: int,
) -> bool:
    """Tell the pull request how much history the force-push replaced.

    Nothing is owed where no history was replaced by less of it, which is
    every branch that reached approval with one commit on it -- whether that
    commit was left alone or rewritten to reference the pull request, since
    either way the branch carried one commit before and carries one now -- and
    every tick that finished a collapse an earlier one already announced. An
    issue with no pull request has nowhere to say it.

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


def _holds_its_records(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str, held: _Held,
) -> bool:
    """Whether the comment still carries the report, evidence, and verdict records `state` does.

    Asked ahead of each write an approval's tail makes behind requests of its
    own, `purpose` naming the write. Where the records stand, `state` is
    composed over the comment as read (`_carries_what_others_wrote`). Where
    they moved, nothing `state` holds is written over them; only the
    orchestrator comments `state` records and the comment does not -- the
    approval comment, the squash notice, a park notice posted on the way --
    are recorded over the comment as read. A comment that will not read, or
    has no room for them, is left as it stands.
    """
    durable = _review_comment._read(gh, issue, state, purpose)
    if durable is None:
        return False
    if not _review_comment._moved(durable.data, state.data, _HELD_RECORDS):
        _carries_what_others_wrote(state, durable.data, held)
        return True
    log.warning(
        "issue=#%s its pinned comment does not carry the developer report, "
        "verification evidence, or verdict records this tick holds, so it will "
        "not %s; recording only the comments it posted", issue.number, purpose,
    )
    posted = sorted(_comments._orchestrator_ids(state) - _comments._orchestrator_ids(durable))
    if not posted:
        return False
    for comment_id in posted:
        _comments._track_orchestrator_comment(durable, comment_id)
    if _report_record_state.fits_the_comment(durable.data):
        gh.write_pinned_state(issue, durable)
    else:
        log.error(
            "issue=#%s has no room on its pinned comment to record the "
            "comments its approval posted; leaving it as it stands", issue.number,
        )
    return False


def _carries_what_others_wrote(state: PinnedState, durable: dict, held: _Held) -> None:
    """Carry onto `state` every field another road wrote since `held` last saw the comment; this reading is then that.

    Another road's is a field the comment spells otherwise than it did while
    `state` still spells it as it did then; one `state` changed too is this
    tick's to write, and so is the squash's own record. Compared as the
    comment's JSON spells them (`review_comment._moved`).
    """
    theirs = _review_comment._moved(durable, held.comment, {*held.comment, *durable})
    ours = set(_review_comment._moved(state.data, held.comment, theirs))
    for field in set(theirs) - ours - _SQUASH_RECORD:
        written = durable.get(field, _review_comment._ABSENT)
        if written is _review_comment._ABSENT:
            state.data.pop(field, None)
        else:
            state.set(field, written)
    held.comment = dict(durable)


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
    non-orchestrator comment on either surface, and `_ratchet_watermark` never
    regresses a watermark a prior in_review tick already advanced. Stopping
    that early on an unread PR comment is deliberately allowed to leave the
    value below a reply the dev already answered: in_review reads the issue
    thread against `last_action_comment_id` too, so the reply stays consumed
    without this seed having to cross the PR comment to say so.

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
