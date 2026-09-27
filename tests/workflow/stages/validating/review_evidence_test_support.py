# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validating issue whose reviewer publishes, reuses, or lacks verification evidence.

Every case starts from the world a reviewer round normally meets: an open pull
request standing on the default head, the report its delivery published
settled on the pinned comment, a checkout that exists on this host, and a fake
repository reading every commit as one tree. In that world the proof that
settles a reviewer's declared commands, and the proof that hands the next
reviewer the evidence current for its subject, both pass -- so a case that
refuses one is visibly about the one thing it moved.

A tick is dispatched the way the dispatcher takes one: the evidence
reconciliation first, and the handler only where that does not hold the tick.
What a case reads back is read off the in-memory client (`review_evidence_readings`).
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import verification_transaction as _transaction
from orchestrator.workflow.stages.validating import handler as _validating
from tests.support.fakes import DEFAULT_PR_HEAD_SHA, FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, _agent, _PatchedWorkflowMixin, publishes_the_report
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.value_helpers import _issue_branch, _open_pr_for

ISSUE = 1_906

PR = 19_060

HEAD = DEFAULT_PR_HEAD_SHA

REVIEWER_SESSION = "rev-sess"

DEV_SESSION = "dev-sess"

RUN_AGENT = "run_agent"

VERIFY = "_run_verify_commands"

# The pinned records a case reads back, spelled as the comment spells them.
RETURNED_VERDICT = "review_returned_verdict"

APPROVED_SUBJECT = "review_approved_subject"

PENDING_EVIDENCE = "verification_evidence_pending"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

AGENT_RUNS_USED = "agent_runs_used"

REASON_UNVERIFIED = "reviewer_unverified"

# The suite a reviewer's declaration and an earlier transaction report, and
# what it printed.
SUITE = "uv run pytest tests"

SUITE_OUTPUT = "12 passed"

# The notices a case looks for on the pull request's thread and the issue's.
APPROVAL_NOTICE = "review approved"

UNVERIFIED_NOTICE = "approved without the verification evidence"

ARTIFACT_HEADING = "verification artifact"

# A checkout that exists on this host, which is all the evidence proof asks of
# the path; every git reading behind it is the fake repository's.
_EXISTING_WORKTREE = Path("/tmp")


def declared_run(head: str = HEAD, *, exit_status: int = 0, verdict: str = "APPROVED") -> str:
    """A reviewer's final message declaring one run of the suite on `head`."""
    return (
        "Reviewed the diff and the report.\n\n"
        f"VERIFICATION: RUN {head}\n"
        f"COMMAND: {SUITE}\n"
        f"EXIT: {exit_status}\n"
        f"{SUITE_OUTPUT}\n"
        "VERIFICATION: END\n\n"
        f"VERDICT: {verdict}"
    )


def declared_reuse(digest: str) -> str:
    """A reviewer's approving message reusing the evidence named by `digest`."""
    return (
        "The current evidence covers this head.\n\n"
        f"VERIFICATION: REUSED sha256:{digest}\n\n"
        "VERDICT: APPROVED"
    )


class ReviewEvidenceWorld(_PatchedWorkflowMixin):
    """An issue on `workflow:validating` whose next reviewer is about to be handed its report."""

    # The report is published here, once, so a case's own writes stay its own.
    delivers_a_report = False

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(
            _worktree_paths, "_worktree_path", return_value=_EXISTING_WORKTREE,
        ))
        self.seeds()

    def seeds(self) -> None:
        """The world afresh, for a case that walks several of them."""
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=LABEL_VALIDATING)
        self.github.add_issue(self.issue)
        self.github.seed_state(
            ISSUE,
            pr_number=PR,
            branch=_issue_branch(ISSUE),
            codex_session_id=DEV_SESSION,
            review_round=0,
        )
        self.pull_request = _open_pr_for(self.github, issue_number=ISSUE, pr_number=PR)
        publishes_the_report(self.github, self.issue)

    def dispatched(self, *agents, **run_options) -> dict:
        """One tick of the issue: the evidence reconciliation, then the handler behind it.

        `agents` are the runs the tick's spawns return, in order; a
        `run_agent` option stands in for the spawn itself instead.
        """
        run_options.setdefault(RUN_AGENT, list(agents))
        return self._run(self.reconciled, **run_options)

    def reconciled(self, *, handled: bool = True) -> None:
        """The evidence reconciliation, and the handler behind it where it does not hold."""
        held = _transaction._reconciles_pending_evidence(
            self.github,
            _TEST_SPEC,
            self.issue,
            self.github.workflow_label(self.issue),
            self.github.read_pinned_state(self.issue),
        )
        if handled and not held:
            _validating._handle_validating(self.github, _TEST_SPEC, self.issue)

    def reviewer(self, message: str):
        """A reviewer run that returns `message`."""
        return _agent(session_id=REVIEWER_SESSION, last_message=message)

    def pinned(self) -> dict:
        """The pinned comment as the next tick reads it."""
        return self.github.pinned_data(ISSUE)


class RefusesTheLaunchRead:
    """A pinned-comment read that fails once the issue carries `workflow:fixing`.

    The first read past that relabel is the developer launch's charge, so
    failing it is a process stopping between the relabel's write and the spawn:
    the launch is refused, and nothing past the relabel is written.
    """

    def __init__(self, case) -> None:
        self._case = case
        self._read = case.github.read_pinned_state
        self._failed = False

    def __call__(self, issue):
        if not self._failed and self._case.github.workflow_label(issue) == LABEL_FIXING:
            self._failed = True
            raise ConnectionError("the pinned comment could not be read")
        return self._read(issue)


def configured(*commands: str):
    """`VERIFY_COMMANDS` set to `commands` for the duration of a block."""
    return patch.object(config, "VERIFY_COMMANDS", commands)
