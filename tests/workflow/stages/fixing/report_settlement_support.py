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
from types import SimpleNamespace

from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.workflow.git_owners import seam_patch

# The pinned field a recorded, unbound report stands on.
_DELIVERED_REPORT = "developer_report_delivery"


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
        "_authed_fetch": lambda *_args, **_fields: SimpleNamespace(returncode=0),
        "_branch_divergence": lambda *_args: _BranchDivergence(
            tip=head, readable=True,
        ),
    }


def recorded_delivery(github, issue, consumed, *, landed: str = "") -> None:
    """A report an earlier tick recorded and a crash left unbound.

    Spelled the way that tick would have written it: the report, and the input
    its run consumed riding the same record. `landed` is the code-publication
    receipt a crash AFTER the push leaves behind, and its absence is the crash
    before one.
    """
    state = github.read_pinned_state(issue)
    state.set(_DELIVERED_REPORT, {
        "receipt": f"issue-{issue.number}-report-1",
        "revision": 1,
        "requirements": _content_hash._compute_user_content_hash(issue, ()),
        "mode": "publish",
        "route": "workflow:fixing",
        "watermarks": [list(pair) for pair in consumed],
        "spends": [],
        "report": "the run that answered this feedback reported it.",
    })
    if landed:
        _publication_state._record_publication(
            state, landed, "", _pull_number(github, issue),
        )
    github.write_pinned_state(issue, state)


def _pull_number(github, issue) -> int:
    """The pull request this issue's pinned record names."""
    return github.read_pinned_state(issue).get("pr_number")
