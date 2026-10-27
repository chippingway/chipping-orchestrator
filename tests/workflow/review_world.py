# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue on `workflow:validating` whose reviewer is about to run, in the world a review round normally meets.

An open pull request on the default head, the report its delivery published
settled on the pinned comment, a checkout this host holds, and a fake
repository reading every commit as one tree, under a configuration that
requires the suite. In it the proof that settles a reviewer's declared
commands passes, so a case that refuses one is visibly about the one thing it
moved.

No stage owns it: `validating`'s verdict and round worlds build on it, and so
does the approval journey that carries a case past that stage
(`approved_squash`). What a reviewer declares, what another road does to the
pull request meanwhile, and what the issue reads as afterwards -- the labels
it moved through, the artifacts on its pull request, what it has spent -- are
spelled here too.
"""
from __future__ import annotations

import operator
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import verification_artifacts as _artifacts
from tests.support.fakes import DEFAULT_PR_HEAD_SHA, FakeGitHubClient, make_issue
from tests.workflow.engine import usage_frames as _usage_frames
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _PatchedWorkflowMixin, publishes_the_report
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import BACKEND_CODEX, EXISTING_CHECKOUT
from tests.workflow.value_helpers import _issue_branch, _open_pr_for

ISSUE = 1_999

PR = 19_990

HEAD = DEFAULT_PR_HEAD_SHA

# A commit a push moves the pull request onto, which nobody reviewed.
OTHER_HEAD = "0123456789abcdef0123456789abcdef01234567"

DEV_SESSION = "dev-sess"

REVIEWER_SESSION = "rev-sess"

RUN_AGENT = "run_agent"

# The tokens the reviewer's usage reports, folded once.
REVIEWER_TOKENS = 120

# The suite the configuration requires, and what the reviewer's run printed.
SUITE = "uv run pytest tests"

SUITE_OUTPUT = "12 passed"

REQUESTED = "1. The suite fails on the empty configuration; handle it."

# The full tree every commit in the fake checkout reads as.
TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# The counters an issue's spending is read off: runs charged, runs folded, and tokens folded.
_SPENT = ("agent_runs_used", "issue_agent_runs", "issue_total_tokens")


def declared_run(
    *, exit_status: int = 0, verdict: str = "APPROVED", command: str = SUITE, output: str = SUITE_OUTPUT,
) -> str:
    """A reviewer's final message declaring one run of `command` on the head."""
    return (
        f"{REQUESTED}\n\n"
        f"VERIFICATION: RUN {HEAD}\n"
        f"COMMAND: {command}\n"
        f"EXIT: {exit_status}\n"
        f"{output}\n"
        "VERIFICATION: END\n\n"
        f"VERDICT: {verdict}"
    )


def reviewer(message: str):
    """A reviewer run returning `message`, whose output reports the world's reviewer tokens."""
    usage = _usage_frames._codex_stdout_no_model(input_tokens=REVIEWER_TOKENS, cached=0, output_tokens=0)
    return _agent(session_id=REVIEWER_SESSION, last_message=message, stdout=usage)


def pushes(case) -> None:
    """Another road's push, standing `case`'s pull request on a head nobody reviewed."""
    case.pull_request.head.sha = OTHER_HEAD


def stops_answering(case) -> None:
    """`case`'s pull-request thread stops answering, which proves nothing about what it carries."""
    case.github.report_failures.unreadable.add(PR)


def artifacts(case) -> list:
    """Every verification artifact on `case`'s pull request, oldest first."""
    readings = (
        _artifacts.verification_artifact_from_comment(posted, bot_login=case.github._bot_login)
        for posted in case.pull_request.issue_comments
    )
    return [found for found in readings if found is not None]


class ReviewWorld(_PatchedWorkflowMixin):
    """An issue on `workflow:validating` whose reviewer is about to be handed its pull request."""

    # The report is published here, once, so a case's own writes stay its own.
    delivers_a_report = False

    def setUp(self) -> None:
        # A checkout this host holds, which is all the evidence proof asks of the path.
        self.enterContext(seam_patch("_worktree_path", lambda *_args: EXISTING_CHECKOUT))
        self.enterContext(seam_patch("_tree_sha", lambda *_args: TREE))
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", (SUITE,)))
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=LABEL_VALIDATING)
        self.github.add_issue(self.issue)
        self.github.seed_state(
            ISSUE,
            pr_number=PR,
            branch=_issue_branch(ISSUE),
            dev_agent=BACKEND_CODEX,
            dev_session_id=DEV_SESSION,
            review_round=0,
            # The stretch the implementer's first spawn recorded: it quoted
            # the thread from its beginning, so every reply a resume settles
            # past it counts as delivered.
            delivered_after_comment_id=0,
            delivered_through_comment_id=0,
        )
        self.pull_request = _open_pr_for(self.github, issue_number=ISSUE, pr_number=PR)
        publishes_the_report(self.github, self.issue)

    def pinned(self) -> dict:
        """The pinned comment as the next tick reads it."""
        return self.github.pinned_data(ISSUE)

    def labels(self) -> tuple:
        """Every workflow label the issue was moved to, in order."""
        history = self.github.label_history
        return tuple(label for number, label in history if number == ISSUE)

    def spent(self) -> tuple:
        """Runs charged, runs folded, and tokens folded on the issue, an absent counter as 0."""
        pinned = self.pinned()
        return tuple(pinned.get(counter) or 0 for counter in _SPENT)

    def spent_since(self, before: tuple) -> tuple:
        """What the issue has spent since it had spent `before`, as `spent` reads it."""
        return tuple(map(operator.sub, self.spent(), before))
