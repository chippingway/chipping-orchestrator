# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The world a held report publication is finished in.

A fixing round whose report GitHub refused leaves a transaction the tick after
it has to complete, and what that tick reads before it may is a whole world:
the pull request standing on the commit the report is about, a clean checkout
still on it, and a remote that agrees. They are answered together here because
the recovery refuses on any one of them, so a case that moved none of them is
asserting a settlement rather than a refusal.
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from unittest import mock

from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.pinned_state import PinnedState as _PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.workflow.git_owners import seam_patch

# The pinned field a recorded, unbound report stands on.
_DELIVERED_REPORT = "developer_report_delivery"

# The pinned field naming the pull request a receipt is recorded against.
_PR_NUMBER = "pr_number"


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


def recorded_delivery(
    github, issue, consumed, *, landed: str = "", spends=(),
) -> None:
    """A report an earlier tick recorded and a crash left unbound.

    Spelled the way that tick would have written it: the report, and the input
    its run consumed riding the same record. `landed` is the code-publication
    receipt a crash AFTER the push leaves behind, and its absence is the crash
    before one. `spends` is the route bookkeeping that round froze -- the fix
    bookmarks it clears and the reviewer round it lands on -- which only the
    write that completes the publication may apply.
    """
    state = github.read_pinned_state(issue)
    state.set(_DELIVERED_REPORT, {
        "receipt": f"issue-{issue.number}-report-1",
        "revision": 1,
        "requirements": _content_hash._compute_user_content_hash(issue, ()),
        "mode": "publish",
        "route": "workflow:fixing",
        "watermarks": [list(pair) for pair in consumed],
        "spends": [list(pair) for pair in spends],
        "report": "the run that answered this feedback reported it.",
    })
    if landed:
        _publication_state._record_publication(
            state, landed, "", state.get(_PR_NUMBER),
        )
    github.write_pinned_state(issue, state)


def consumed_pairs(issue, readers, comment_id: int) -> tuple:
    """What one issue-thread reply comes to, off the owner that derives it.

    Built from the reply itself through the stage's own delivery owner rather
    than spelled out, so a case is about the pairs a round recorded being the
    pairs this stage derives -- not about a tuple a fixture chose that both
    sides happen to match.
    """
    seeded = _PinnedState(state_data=dict(readers))
    batch = _models._FixingFeedback(
        issue_thread=[
            seen for seen in issue.comments if seen.id == comment_id
        ],
        pr_conversation=[],
        review_comments=[],
        review_summaries=[],
    )
    return _feedback._consumed_delivery(seeded, batch).consumed_pairs(seeded)


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
