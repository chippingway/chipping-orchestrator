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
    verification_settlement_state as _settlement,
    verification_transaction as _transaction,
)
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.engine import (
    verification_record_test_support as _record_support,
    verification_report_fixture as _report,
    verification_world_fixture as _world,
)
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING
from tests.workflow.git_owners import seam_patch

ISSUE_NUMBER = _record_support.ISSUE_NUMBER

PR_NUMBER = _record_support.PR_NUMBER

BRANCH = _world.BRANCH

TESTED_SHA = _world.TESTED_SHA

TESTED_TREE = _world.TESTED_TREE

SQUASHED_SHA = _world.SQUASHED_SHA

REBASED_SHA = _world.REBASED_SHA

REBASED_TREE = _world.REBASED_TREE

TAG_SHA = _world.TAG_SHA

SUITE = _record_support.SUITE

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
            "context_revision": _proof.configured_context_revision(),
        }
        return _record_support.binding(**(bound | overrides))

    def record(
        self,
        binding: _records.EvidenceBinding | None = None,
        exit_status: int = 0,
        *,
        onto: _pinned_state.PinnedState | None = None,
    ) -> _records.PendingEvidence:
        """Mint, stage, and persist one transaction, as a producer does.

        Onto `self.state`, or onto `onto` -- another road's own reading of the
        comment, which leaves the reading a tick holds as it was.
        """
        state = self.state if onto is None else onto
        pending = _record_state.mint_pending_evidence(
            state, ISSUE_NUMBER, binding or self.binding(),
            (_record_support.ran(exit_status=exit_status),),
        )
        self.assertIsNotNone(pending)
        self.assertTrue(_record_state.record_pending_evidence(state, pending))
        self.gh.write_pinned_state(self.issue, state)
        return pending

    def reconcile(self, state: _pinned_state.PinnedState | None = None) -> bool:
        """Run the dispatcher's evidence guard over the persisted comment, or over `state`.

        `state` is a reading the tick took before another road wrote the comment.
        """
        self.state = self.gh.read_pinned_state(self.issue) if state is None else state
        with self.seams():
            return _transaction._reconciles_pending_evidence(
                self.gh, _TEST_SPEC, self.issue, self.gh.workflow_label(self.issue), self.state,
            )

    @contextlib.contextmanager
    def seams(self):
        """The git readings the proof takes, answered from `self.world`."""
        world = self.world
        answers = (
            ("_worktree_path", lambda *_args: world.path),
            ("_authed_fetch", world.fetch),
            ("_branch_divergence", world.divergence),
            ("_commit_present", world.commit_present),
            ("_tree_sha", world.tree_sha),
            ("_standing_on_the_remote_base", world.standing),
            ("_remote_branch_read", lambda *args: _world.remote_read(world, *args)),
            ("_reads_the_checkout", lambda *args: _world.checkout_of(world, *args)),
        )
        with contextlib.ExitStack() as seams:
            for seam, answer in answers:
                seams.enter_context(seam_patch(seam, answer))
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


def reading(case) -> _proof.ProofReading:
    """What a caller deciding on or relying on `case`'s evidence reads now."""
    return _proof.ProofReading(case.gh, _TEST_SPEC, case.issue, case.state)


def current_verdict(case):
    """What a reader relying on `case`'s current evidence is told now."""
    with case.seams():
        return _proof.current_evidence_verdict(reading(case))


def artifact_comment(case):
    """The comment `case`'s current evidence was published as."""
    comment_id = _settlement.read_current_evidence(case.state).comment_id
    return next(
        posted for posted in case.pull_request.issue_comments
        if posted.id == comment_id
    )


def posts_unsettled(case) -> _records.PendingEvidence:
    """Record newer, failing evidence and post its artifact, as a crash before its settlement leaves it."""
    newer = case.record(
        case.binding(source=_evidence.EvidenceSource.REVIEWER_REPORTED), exit_status=1,
    )
    case.gh.publish_verification_artifact(case.pull_request, newer.artifact)
    return newer


def logged_refusal(logged) -> str:
    """Everything one `assertLogs` block captured, as one text to search."""
    return "\n".join(logged.output)
