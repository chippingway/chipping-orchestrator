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
from tests.workflow.git_owners import seam_patch


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
