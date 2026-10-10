# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue holding settled evidence, a base rewrite landed over it, and the run its policy may make.

The issue is the evidence fixture's (`verification_evidence_test_support`):
a settled developer report about the tested commit, reviewed, and current
evidence of the configured suite settled over it. The rewrite replaced that
commit with one the case names -- the squash, whose tree is the tested one,
or the rebase over a moved base, whose tree is not -- and landed: the pull
request, the remote branch, and the checkout stand on it, and the landing
reads both trees as the git owners would have read them.

The finish is handed its own copy of the issue, as the tick read it, so the
issue the case holds stands for the one on GitHub: an edit to it is one the
copy the finish holds does not show, the way a fetched issue's title and body
stay as they were read.

The verify runner is the one seam the policy's run passes through, answered
by a recording double: it runs nothing, records what it was handed, reads the
head and tree the checkout stands on, and answers with the transcript the case
set. `checked_out` is a commit the checkout stood on instead as the run began,
back where the remote stands before anything is read again, and `during` is
what another road does while the commands run.
"""
from __future__ import annotations

from copy import copy

from orchestrator.git.base_sync.rewrite_handoffs import (
    _CheckoutReading,
    _LandedRewrite,
    _PushOutcome,
    _RewriteAttempt,
    _RewriteCandidate,
)
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification import models as _verify_models
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    rewrite_evidence as _rewrite_evidence,
)
from orchestrator.workflow.engine.rewrite_evidence_models import RewriteEvidence
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_report_fixture as _report,
    verification_world_fixture as _world,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.git_owners import seam_patch

LINT = "uv run ruff check orchestrator tests"

# What the suite prints on the rewritten head: passing, and not the
# transcript its settled evidence carries.
FRESH_OUTPUT = "13 passed in 2.10s"

FAILED_OUTPUT = "FAILED tests/test_widget.py::test_rebased - AssertionError\n1 failed, 12 passed"

FAILED_EXIT = 1


class RewriteEvidenceCase(support.VerificationEvidenceCase):
    """Current evidence on the tested commit, and a landed rewrite of it to decide over."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.source = self.record()
        self.reconcile()
        self.handed: list[tuple[str, ...]] = []
        self.exits: dict[str, int] = {}
        self.outputs: dict[str, str] = {}
        self.during = _unmoved
        self.checked_out: str | None = None

    def rewrites(self, head: str, *, reported: bool = True, reviewed: bool = True, revision: int = 2) -> None:
        """Land the rewrite onto `head`, and settle report `revision` about it that a reviewer is handed.

        `reported` False leaves the report refresh unsettled, and `reviewed`
        False settles it with no reviewer handed it yet.
        """
        self.moves_the_head(head)
        if reported:
            _report.settles_report(self, revision, _report.LATER_REPORT_TEXT, reviewed=reviewed, head=head)
        self.gh.write_pinned_state(self.issue, self.state)

    def approves_the_tested_head(self) -> None:
        """Record the approval of the review the current evidence answers for, as an approval would."""
        self.state.set(_review_subjects.APPROVED_SUBJECT, self.subject.recorded())
        self.gh.write_pinned_state(self.issue, self.state)

    def edits_the_report(self) -> None:
        """Rewrite by hand the comment the report the issue settled last was published as."""
        settled_at = _report_settlement.read_current_report(self.state).location.comment_id
        edited = next(posted for posted in self.pull_request.issue_comments if posted.id == settled_at)
        edited.body = "Rewritten by hand."

    def decide(self, head: str) -> RewriteEvidence:
        """What the policy decides for the landing onto `head`, over the issue as it reads now."""
        finish = LandedFinish(
            gh=self.gh,
            spec=_TEST_SPEC,
            issue=copy(self.issue),
            state=self.gh.read_pinned_state(self.issue),
            landed=self._landing(head),
            label=self.gh.workflow_label(self.issue),
        )
        with self.seams(), seam_patch("_run_verify_commands", self._runs):
            return _rewrite_evidence.decides(finish)

    def _runs(self, _worktree, commands: tuple[str, ...], timeout: int) -> _verify_models.VerifyResult:
        """The run of `commands` the case set, on the head the checkout stands on as it starts."""
        self.handed.append(commands)
        head = self.checked_out or self.world.remote.tip
        tree = self.world.trees[head]
        self.during(self)
        attempted = []
        for command in commands:
            exit_status = self.exits.get(command, 0)
            attempted.append(_verify_models.VerifyCommandOutcome(
                command=command,
                status=_verify_models.VERIFY_STATUS_OK if exit_status == 0 else _verify_models.VERIFY_STATUS_FAILED,
                exit_code=exit_status,
                output=self.outputs.get(command, f"{command}: ok"),
                head_before=head,
                head_after=head,
                tree_before=tree,
                tree_after=tree,
            ))
            if exit_status:
                break
        return _recorded(commands, timeout, (head, tree), tuple(attempted))

    def _landing(self, head: str) -> _LandedRewrite:
        """The landed rewrite of the tested commit onto `head`, made under the label the issue wears.

        The checkout read `head` as the tree this world gives it, level with
        its base, which the policy never reads.
        """
        candidate = _RewriteCandidate(
            attempt=_RewriteAttempt(
                anchor=support.TESTED_SHA, pr_number=support.PR_NUMBER, stage=self.gh.workflow_label(self.issue),
            ),
            branch=support.BRANCH,
            original_tree=support.TESTED_TREE,
            checkout=_CheckoutReading(
                head=head,
                tree=self.world.trees.get(head, ""),
                status=_WorktreeStatus(readable=True),
                base=_world.standing_on(head),
            ),
            remote=_RefRead(sha=support.TESTED_SHA),
        )
        return _LandedRewrite(candidate=candidate, outcome=_PushOutcome.ACCEPTED, remote=_RefRead(sha=head))


def _unmoved(_case: RewriteEvidenceCase) -> None:
    """Nothing another road does while the commands run."""


def _recorded(
    commands: tuple[str, ...],
    timeout: int,
    tested: tuple[str, str],
    attempted: tuple[_verify_models.VerifyCommandOutcome, ...],
) -> _verify_models.VerifyResult:
    """The runner's record of `attempted`, refused at its last command unless every one passed."""
    terminal = attempted[-1]
    refused = {}
    if terminal.status != _verify_models.VERIFY_STATUS_OK:
        refused = {"command": terminal.command, "exit_code": terminal.exit_code, "output": terminal.output}
    return _verify_models.VerifyResult(
        status=terminal.status,
        commit=tested[0],
        tree_identity=tested[1],
        configured_commands=commands,
        attempted_commands=attempted,
        timeout=timeout,
        context_revision=_verify_models._context_revision(commands, timeout),
        **refused,
    )
