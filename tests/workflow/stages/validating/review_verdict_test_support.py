# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validating issue whose reviewer returned, and the disposition its verdict is handed to.

The world is the one a reviewer round normally meets: an open pull request on
the default head, the report its delivery published settled on the pinned
comment, a checkout this host holds, and a fake repository reading every
commit as one tree, under a configuration that requires the suite. In it the
proof that settles a reviewer's declared commands passes, so a case that
refuses one is visibly about the one thing it moved.

No live reviewer round hands its result to the disposition service yet, so a
case returns one the way the round will: the subject resolved and recorded as
the launch and the return record it, the launch charged, the reviewer's usage
folded once, and the parsed verdict handed to `review_disposition`. Every later
tick is dispatched as the dispatcher takes one -- the evidence reconciliation,
then the handler -- and read back through `review_verdict_readings`.

What another road does between two of a tick's requests is spelled here too
(`AnotherRoadBehind`): a push, or a later report settling, behind the one
request a case is about.
"""
from __future__ import annotations

from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    prompt_context as _prompt_context,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.validating import (
    handler as _validating,
    models as _models,
    review_disposition as _disposition,
    review_evidence as _review_evidence,
    review_records as _review_records,
    review_report as _review_report,
)
from tests.support.fakes import DEFAULT_PR_HEAD_SHA, FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _PatchedWorkflowMixin, _reported, publishes_the_report
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC
from tests.workflow.value_helpers import _issue_branch, _open_pr_for

ISSUE = 1_990

PR = 19_900

HEAD = DEFAULT_PR_HEAD_SHA

# A commit a push moves the pull request onto, which nobody reviewed.
OTHER_HEAD = "0123456789abcdef0123456789abcdef01234567"

DEV_SESSION = "dev-sess"

REVIEWER_SESSION = "rev-sess"

RUN_AGENT = "run_agent"

# The pinned records a case reads back, spelled as the comment spells them.
RETURNED_VERDICT = "review_returned_verdict"

PENDING_EVIDENCE = "verification_evidence_pending"

PARK_REASON = "park_reason"

AGENT_RUNS_USED = "agent_runs_used"

# The tokens the reviewer's usage reports, folded once.
REVIEWER_TOKENS = 120

# The suite the configuration requires, and what the reviewer's run printed.
SUITE = "uv run pytest tests"

SUITE_OUTPUT = "12 passed"

REQUESTED = "1. The suite fails on the empty configuration; handle it."

# The full tree every commit in the fake checkout reads as.
TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# A checkout this host holds, which is all the evidence proof asks of the path.
_EXISTING_CHECKOUT = _FAKE_WT.parent


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


def developer():
    """The developer run a handed change request is answered by."""
    return _agent(session_id=DEV_SESSION, last_message=_reported("fixed"))


def replies(case, text: str) -> None:
    """The issue author's reply on `case`'s issue thread, below everything posted on it so far."""
    author = FakeUser(case.issue.user.login)
    case.issue.comments.append(FakeComment(
        id=case.github._next_comment_id(case.issue), body=text, user=author,
    ))


def pushes(case) -> None:
    """Another road's push, standing `case`'s pull request on a head nobody reviewed."""
    case.pull_request.head.sha = OTHER_HEAD


class AnotherRoadBehind:
    """A client request behind which, the first time `when` says, `road` does another road's work."""

    def __init__(self, case, request: str, when, road) -> None:
        self._case = case
        self._name = request
        self._request = getattr(case.github, request)
        self._when = when
        self._road = road
        self._done = False

    def __call__(self, target, asked):
        answered = self._request(target, asked)
        if not self._done and self._when(asked):
            self._done = True
            self._road(self._case)
        return answered

    def returning(self, message: str) -> dict:
        """The tick in which a reviewer returned `message`, over a client carrying this request."""
        with patch.object(self._case.github, self._name, self):
            return self._case.returns(message)


class ReviewVerdictWorld(_PatchedWorkflowMixin):
    """An issue on `workflow:validating` whose reviewer is about to return."""

    # The report is published here, once, so a case's own writes stay its own.
    delivers_a_report = False

    def setUp(self) -> None:
        self.enterContext(seam_patch("_worktree_path", lambda *_args: _EXISTING_CHECKOUT))
        self.enterContext(seam_patch("_tree_sha", lambda *_args: TREE))
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", (SUITE,)))
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=LABEL_VALIDATING)
        self.github.add_issue(self.issue)
        self.github.seed_state(
            ISSUE, pr_number=PR, branch=_issue_branch(ISSUE), codex_session_id=DEV_SESSION, review_round=0,
        )
        self.pull_request = _open_pr_for(self.github, issue_number=ISSUE, pr_number=PR)
        publishes_the_report(self.github, self.issue)

    def returns(self, message: str, **run_options) -> dict:
        """One tick in which a reviewer returned `message` and its verdict was disposed of."""
        run_options.setdefault(RUN_AGENT, [])
        return self._run(partial(self._disposes, message), **run_options)

    def dispatched(self, *agents, **run_options) -> dict:
        """One later tick: the evidence reconciliation, then the handler behind it."""
        run_options.setdefault(RUN_AGENT, list(agents))
        return self._run(self.reconciled, **run_options)

    def pinned(self) -> dict:
        """The pinned comment as the next tick reads it."""
        return self.github.pinned_data(ISSUE)

    def handed(self, state):
        """The subject a reviewer round is handed now, recorded on `state` as its launch records it."""
        delivered = _prompt_context._delivered_thread(self.github, self.issue, state)
        handover = _review_report._resolves_the_subject(self.github, self.issue, state, PR, delivered)
        _review_records._records_the_launch(state, handover.subject)
        return handover

    def reconciled(self, *, handled: bool = True) -> None:
        """The evidence reconciliation, and the validating handler where it does not hold."""
        held = _transaction._reconciles_pending_evidence(
            self.github, _TEST_SPEC, self.issue,
            self.github.workflow_label(self.issue), self.github.read_pinned_state(self.issue),
        )
        if handled and not held:
            _validating._handle_validating(self.github, _TEST_SPEC, self.issue)

    def _disposes(self, message: str) -> None:
        """The returned round, as the live one records it, handed to the disposition."""
        state = self.github.read_pinned_state(self.issue)
        handover = self.handed(state)
        # The launch's lifetime charge, which the live round's run circuit takes.
        state.set(AGENT_RUNS_USED, (state.get(AGENT_RUNS_USED) or 0) + 1)
        _review_records._records_the_return(
            state, UsageMetrics(backend="codex", input_tokens=REVIEWER_TOKENS), REVIEWER_SESSION, handover.subject,
        )
        verdict, body = _completion_verdicts._parse_review_verdict(message)
        run = _models._ReviewerRun(
            wt=_FAKE_WT,
            round_n=state.get("review_round"),
            pr_number=PR,
            agent_result=_agent(session_id=REVIEWER_SESSION, last_message=message),
            delivery=None,
            subject=handover.subject,
            resolved_over=handover.resolved_over,
            evidence=_review_evidence.handed_evidence(self.github, _TEST_SPEC, self.issue, state, handover.subject),
        )
        _disposition.disposes_of_the_verdict(
            self.github, _TEST_SPEC, self.issue, state, _models._ReviewerDecision(run, verdict, body),
        )
