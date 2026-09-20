# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The world a held report publication is finished in.

A fixing round whose report GitHub refused leaves a transaction the tick after
it has to complete, and what that tick reads before it may is a whole world:
the pull request standing on the commit the report is about, a clean checkout
still on it, and a remote that agrees. They are answered together here because
the recovery refuses on any one of them, so a case that moved none of them is
asserting a settlement rather than a refusal.

What a settlement LEAVES is here too, and it is a different fixture: the
current report a finished transaction records outlives every transaction after
it, so an issue carrying one says only that some round once published a report.
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
)
from tests.workflow.git_owners import seam_patch

# The comment an older round's report was published as, for the record that
# outlives the transaction that put it there.
_PUBLISHED_REPORT = 4242

# The mark a fixing report transaction's own settlement raises, which is the
# whole of what says a round closed while its label never moved.
SETTLED_ROUND = "fixing_round_settled"

# A location shaped the way the contract spells one, naming a comment no pull
# request carries, and a digest nothing can be read back at. What a case built
# on them is about is the ROAD a verified outcome takes, so the publication
# itself is kept out of the way of that question.
_ABSENT_COMMENT = 999
_UNCONFIRMABLE = hashlib.sha256(b"a report nobody posted").hexdigest()


def verified_report(slug: str, pr_number: int) -> str:
    """A run's last message asserting its report is already on the PR."""
    return (
        f"REPORT: VERIFIED https://github.com/{slug}/pull/{pr_number}"
        f"#issuecomment-{_ABSENT_COMMENT} sha256:{_UNCONFIRMABLE}"
    )


def records_a_settled_report(seeded, *, head: str, clears=()) -> None:
    """Record a report an EARLIER round published, as a settlement leaves it.

    Written through the engine's own writer, so a case built on it is about a
    record this build really produces: replaced rather than retired by the
    next settlement, and carrying no word at all about which round put it
    there or whether that round is over.

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


@contextlib.contextmanager
def republishing_world(github, *, pr_number: int, head: str):
    """The tick after a held publication, over a world that holds.

    The push landed before the post was refused, so GitHub serves the pull
    request standing on `head` and this host still has the checkout that made
    it. The comment the retry posts is accepted this time: whatever refused
    the first one is cleared here, since what the case is about is the
    settlement the second one reaches.
    """
    github.report_failures.refused.clear()
    _stands_on(github.get_pr(pr_number), head)
    with tempfile.TemporaryDirectory() as checkout, contextlib.ExitStack() as seams:
        for owner, reading in _readings(Path(checkout), head).items():
            seams.enter_context(seam_patch(owner, reading))
        yield


def _stands_on(published, head: str) -> None:
    """Serve this pull request as the landed push left it."""
    published.head.sha = head
    published.commit_shas = (head,)


def _readings(checkout: Path, head: str) -> dict:
    """Every git reading the report evidence takes, answered from one pair."""
    return {
        "_worktree_path": lambda *_args: checkout,
        "_worktree_status": lambda *_args: _WorktreeStatus(readable=True),
        "_head_sha": lambda *_args: head,
        "_authed_fetch": lambda *_args, **_fields: mock.Mock(returncode=0),
        "_branch_divergence": lambda *_args: _BranchDivergence(
            tip=head, readable=True,
        ),
    }


@contextlib.contextmanager
def on_a_real_checkout(worktree_paths, attribute: str):
    """A tick whose worktree probe answers a directory that is really there.

    What every report road re-proves is the checkout, so a case about one has
    to have one: the default probe names a path no host holds, which is the
    answer this owner's own missing-worktree case is about.
    """
    with tempfile.TemporaryDirectory() as checkout, mock.patch.object(
        worktree_paths, attribute, return_value=Path(checkout),
    ):
        yield
