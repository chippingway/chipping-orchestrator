# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The world a held report publication is finished in.

A fixing round whose report GitHub refused leaves a transaction the tick after
it has to complete, and what that tick reads before it may is a whole world: the
pull request standing on the commit the report is about, a clean checkout still
on it, and a remote that agrees. They are answered together here because the
recovery refuses on any one of them, so a case that moved none of them is
asserting a settlement rather than a refusal.

What a settlement LEAVES is here too, and it is a different fixture: the current
report a finished transaction records outlives every transaction after it, so an
issue carrying one says only that some round once published a report.
"""

from __future__ import annotations

import contextlib
import hashlib
import tempfile
from pathlib import Path
from unittest import mock

from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_records as _records,
    report_settlement_state as _settlement,
    report_transaction as _report_transaction,
)
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import _TEST_SPEC

# The comment an older round's report was published as, for the record that
# outlives the transaction that put it there.
_PUBLISHED_REPORT = 4242

# The mark a fixing report transaction's own settlement raises, which is the
# whole of what says a round closed while its label never moved.
SETTLED_ROUND = "fixing_round_settled"

# What the in_review route writes when it opens a fix round: the route
# discriminator and the bookmarks naming the batch that started it.
_PENDING_FIX_AT = "pending_fix_at"
_PENDING_FIX_ISSUE_MAX_ID = "pending_fix_issue_max_id"
_PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
_OPENED_AT = "2026-05-24T00:00:00+00:00"
_FIXING = "workflow:fixing"

# The reviewer round a fix loop opens on, which an owed publication may not
# spend until its report is really on the pull request.
_REVIEW_ROUND = "review_round"

# A location shaped the way the contract spells one, naming a comment no pull
# request carries, and a digest nothing can be read back at. What a case built
# on them is about is the ROAD a verified outcome takes, so the publication
# itself is kept out of the way of that question.
_ABSENT_COMMENT = 999
_UNCONFIRMABLE = hashlib.sha256(b"a report nobody posted").hexdigest()


def keeps_the_replay_state(pinned_data, *, bookmarked: int) -> bool:
    """Whether the batch and round an owed publication replays from stand."""
    return (
        pinned_data.get(_PENDING_FIX_ISSUE_MAX_ID) == bookmarked
        and pinned_data.get(_REVIEW_ROUND) == 1
    )


def verified_report(slug: str, pr_number: int) -> str:
    """A run's last message asserting its report is already on the PR."""
    return (
        f"REPORT: VERIFIED https://github.com/{slug}/pull/{pr_number}"
        f"#issuecomment-{_ABSENT_COMMENT} sha256:{_UNCONFIRMABLE}"
    )


def records_a_settled_report(seeded, *, head: str, clears=()) -> None:
    """Record a report an EARLIER round published, as a settlement leaves it.

    Written through the engine's own writer, so a case built on it is about a
    record this build really produces: replaced rather than retired by the next
    settlement, and carrying no word at all about which round put it there or
    whether that round is over.

    `clears` are the pinned fields the case wants gone beside it -- what a
    manual relabel onto `workflow:fixing` leaves behind is neither route's own
    anchor, which is exactly the shape a reading off this record would misread.
    """
    state = seeded.github.read_pinned_state(seeded.issue)
    pr_number = state.get("pr_number")
    _settlement.record_current_report(state, _records.CurrentReport(
        subject=_records.ReportSubject(
            repo_slug=seeded.github.repo_slug,
            pr_number=pr_number,
            branch=state.get("branch"),
            source_sha=head,
            requirements_revision=(
                _content_hash._compute_user_content_hash(seeded.issue, ())
            ),
        ),
        report_revision=1,
        content_revision=hashlib.sha256(b"an earlier round").hexdigest(),
        location=ReportLocation(
            pr_number=pr_number, comment_id=_PUBLISHED_REPORT,
        ),
        mode=_records.ReportMode.PUBLISH,
    ))
    for cleared in clears:
        state.set(cleared, None)
    seeded.github.write_pinned_state(seeded.issue, state)


def opens_a_later_round(seeded, *, bookmarked: int | None = None) -> None:
    """Put this issue back on `workflow:fixing`, as a route or a human would.

    `bookmarked` is what the in_review route writes when it hands a pull
    request to `fixing`: the discriminator that says whose round this is, and
    the bookmark naming the batch a retry would replay. A case needs it where
    what it is about is a raised mark belonging to an OLDER settlement, because
    a newer round writing an anchor the settlement had cleared is one of the
    things that says so.

    None is the other road entirely -- a human relabel, which writes no anchor
    at all. That is the one shape no other state on the comment tells from a
    round whose report has just settled, since the settlement cleared both
    anchors and dropped the transaction itself; only the label that settlement
    recorded itself under still says where it happened.
    """
    if bookmarked is not None:
        state = seeded.github.read_pinned_state(seeded.issue)
        state.set(_PENDING_FIX_AT, _OPENED_AT)
        state.set(_PENDING_FIX_ISSUE_MAX_ID, bookmarked)
        state.set(_PENDING_FIX_ISSUE_IDS, [bookmarked])
        seeded.github.write_pinned_state(seeded.issue, state)
    seeded.github.apply_foreign_label(seeded.issue, _FIXING)


def settles_elsewhere(seeded, *, under: str, head: str) -> None:
    """Settle this issue's outstanding transaction under another label.

    The reconciliation runs ahead of every handler on every non-terminal label,
    so a fixing round that left `workflow:fixing` with its publication still
    owed settles where the issue has got to -- and the mark it raises is then
    standing on a comment no fixing tick is reading.
    """
    seeded.github.apply_foreign_label(seeded.issue, under)
    pr_number = seeded.github.read_pinned_state(seeded.issue).get("pr_number")
    with republishing_world(seeded.github, pr_number=pr_number, head=head):
        _report_transaction._reconciles_pending_report(
            seeded.github, _TEST_SPEC, seeded.issue, under,
            seeded.github.read_pinned_state(seeded.issue),
        )


@contextlib.contextmanager
def republishing_world(github, *, pr_number: int, head: str):
    """The tick after a held publication, over a world that holds.

    The push landed before the post was refused, so GitHub is served the pull
    request standing on `head` and this host still has the checkout that made
    it. The comment the retry posts is accepted this time: whatever refused the
    first one is cleared here, since what the case is about is the settlement
    the second one reaches.
    """
    github.report_failures.refused.clear()
    published = github.get_pr(pr_number)
    published.head.sha = head
    published.commit_shas = (head,)
    # Every git reading the report evidence takes, answered from one pair.
    with tempfile.TemporaryDirectory() as checkout, contextlib.ExitStack() as seams:
        seams.enter_context(seam_patch(
            "_worktree_path", lambda *_args: Path(checkout),
        ))
        seams.enter_context(seam_patch(
            "_worktree_status", lambda *_args: _WorktreeStatus(readable=True),
        ))
        seams.enter_context(seam_patch("_head_sha", lambda *_args: head))
        seams.enter_context(seam_patch(
            "_authed_fetch", lambda *_args, **_fields: mock.Mock(returncode=0),
        ))
        seams.enter_context(seam_patch(
            "_branch_divergence",
            lambda *_args: _BranchDivergence(tip=head, readable=True),
        ))
        yield


@contextlib.contextmanager
def on_a_real_checkout(worktree_paths, attribute: str):
    """A tick whose worktree probe answers a directory that is really there.

    What every report road re-proves is the checkout, so a case about one has to
    have one: the default probe names a path no host holds, which is the answer
    this owner's own missing-worktree case is about.
    """
    with tempfile.TemporaryDirectory() as checkout, mock.patch.object(
        worktree_paths, attribute, return_value=Path(checkout),
    ):
        yield
