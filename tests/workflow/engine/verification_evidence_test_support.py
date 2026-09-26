# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue that owes verification evidence, and the world it is reconciled in.

The default world is the one evidence is recorded in: an open pull request on
the recorded branch standing on the tested commit, a remote branch and a
checkout standing there too, a repository that reads that commit's tree, a
settled developer report the review subject names, configured verification
matching the context the run recorded, and an issue whose requirements are the
ones the evidence was bound to. Each case moves exactly one of those, so what a
refusal is about is the thing the case changed.

Every git reading the proof takes is answered from one `EvidenceWorld`, owned
by `verification_world_fixture` beside this.
"""
from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import (
    pinned_state as _pinned_state,
    verification_artifacts as _artifacts,
    verification_evidence as _evidence,
)
from orchestrator.workflow.engine import (
    report_records as _report_records,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_transaction as _transaction,
)
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.engine import verification_report_fixture as _report, verification_world_fixture as _world
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING
from tests.workflow.git_owners import seam_patch

ISSUE_NUMBER = 7

PR_NUMBER = 12

BRANCH = _world.BRANCH

TESTED_SHA = _world.TESTED_SHA

TESTED_TREE = _world.TESTED_TREE

SQUASHED_SHA = _world.SQUASHED_SHA

REBASED_SHA = _world.REBASED_SHA

REBASED_TREE = _world.REBASED_TREE

SUITE = "uv run pytest tests"

# The ledger of comments this orchestrator posted.
LEDGER = "orchestrator_comment_ids"

WORKFLOW_LOG = "orchestrator.workflow"


class VerificationEvidenceCase:
    """An issue on a settled developer report, owing or holding evidence."""

    def setUp(self) -> None:
        worktrees = contextlib.ExitStack()
        self.addCleanup(worktrees.close)
        self.world = _world.EvidenceWorld(
            Path(worktrees.enter_context(tempfile.TemporaryDirectory())),
        )
        worktrees.enter_context(patch.object(config, "VERIFY_COMMANDS", (SUITE,)))
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_VALIDATING)
        self.pull_request = FakePR(
            number=PR_NUMBER, head_branch=BRANCH, head=FakePRRef(sha=TESTED_SHA),
        )
        self.gh = FakeGitHubClient([self.issue])
        self.gh.add_pr(self.pull_request)
        self.state = _pinned_state.PinnedState(
            comment_id=1, state_data={"pr_number": PR_NUMBER},
        )
        self.subject = _report.settles_report(self, 1)

    def binding(self, **overrides) -> _records.EvidenceBinding:
        """A fresh run's binding: tested on the head it answers for, any member replaced.

        It answers for the subject the settled report's reviewer was handed.
        """
        bound = {
            "target": _records.EvidenceTarget(
                publication=_report_records.ReportSubject(
                    repo_slug=self.gh.repo_slug,
                    pr_number=PR_NUMBER,
                    branch=BRANCH,
                    source_sha=TESTED_SHA,
                    requirements_revision=self.subject.requirements_revision,
                ),
                subject=self.subject.recorded(),
            ),
            "source": _evidence.EvidenceSource.ORCHESTRATOR_EXECUTED,
            "tested_sha": TESTED_SHA,
            "tested_tree": TESTED_TREE,
            "context_revision": _proof.configured_context_revision(),
        }
        return _records.EvidenceBinding(**(bound | overrides))

    def record(
        self, binding: _records.EvidenceBinding | None = None, exit_status: int = 0,
    ) -> _records.PendingEvidence:
        """Mint, stage, and persist one transaction, as a producer does."""
        ran = _evidence.VerifiedCommand(
            command=SUITE, exit_status=exit_status, output="12 passed",
        )
        pending = _record_state.mint_pending_evidence(
            self.state, ISSUE_NUMBER, binding or self.binding(), (ran,),
        )
        self.assertTrue(_record_state.record_pending_evidence(self.state, pending))
        self.gh.write_pinned_state(self.issue, self.state)
        return pending

    def reconcile(self) -> bool:
        """Run the dispatcher's evidence guard over the persisted comment."""
        self.state = self.gh.read_pinned_state(self.issue)
        with self.seams():
            return _transaction._reconciles_pending_evidence(
                self.gh, _TEST_SPEC, self.issue, self.gh.workflow_label(self.issue), self.state,
            )

    @contextlib.contextmanager
    def seams(self):
        """The git readings the proof takes, answered from `self.world`."""
        with contextlib.ExitStack() as seams:
            seams.enter_context(seam_patch("_worktree_path", lambda *_args: self.world.path))
            seams.enter_context(seam_patch("_authed_fetch", self.world.fetch))
            seams.enter_context(seam_patch("_branch_divergence", self.world.divergence))
            seams.enter_context(seam_patch("_commit_present", self.world.commit_present))
            seams.enter_context(seam_patch("_tree_sha", self.world.tree_sha))
            yield

    def moves_the_head(self, head: str) -> None:
        """Stand the pull request, its branch, and the checkout on `head`."""
        self.pull_request.head.sha = head
        self.world.remote = _world.standing_on(head)

    def artifacts(self) -> list:
        """Every verification artifact on the pull request, oldest first."""
        readings = [
            _artifacts.verification_artifact_from_comment(
                posted, bot_login=self.gh._bot_login,
            )
            for posted in self.pull_request.issue_comments
        ]
        return [found for found in readings if found is not None]


def logged_refusal(logged) -> str:
    """Everything one `assertLogs` block captured, as one text to search."""
    return "\n".join(logged.output)
