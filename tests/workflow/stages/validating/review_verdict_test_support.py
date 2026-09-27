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
folded once, and the parsed verdict handed to `review_disposition`. No handler
finishes a verdict a tick left waiting yet either, so a later tick is the
dispatcher's evidence reconciliation and then the disposition's own entry for
a persisted verdict (`acts_on_the_verdict`), handed the verdict the comment
carries as the decision it was returned as. Both are read back through
`review_verdict_readings`.

What another road does between two of a tick's requests is spelled here too
(`AnotherRoadBehind`): a push, or a later report settling, behind the one
request a case is about.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    prompt_context as _prompt_context,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_disposition as _disposition,
    review_evidence as _review_evidence,
    review_records as _review_records,
    review_report as _review_report,
    review_verdicts as _verdicts,
)
from tests.support.fakes import DEFAULT_PR_HEAD_SHA, FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _PatchedWorkflowMixin, _reported, publishes_the_report
from tests.workflow.git_owners import GIT_SEAM_OWNERS, seam_patch
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


def pushes(case) -> None:
    """Another road's push, standing `case`'s pull request on a head nobody reviewed."""
    case.pull_request.head.sha = OTHER_HEAD


def returned_run(case, state, message: str) -> _models._ReviewerRun:
    """The run of a reviewer handed the subject standing now that returned `message`, launched on `state`."""
    delivered = _prompt_context._delivered_thread(case.github, case.issue, state)
    handover = case.handed(state, delivered)
    return _models._ReviewerRun(
        wt=_FAKE_WT,
        round_n=state.get("review_round"),
        pr_number=PR,
        agent_result=_agent(session_id=REVIEWER_SESSION, last_message=message),
        delivery=delivered,
        subject=handover.subject,
        resolved_over=handover.resolved_over,
        evidence=_review_evidence.handed_evidence(case.github, _TEST_SPEC, case.issue, state, handover.subject),
    )


def reconciles(case) -> bool:
    """The dispatcher's evidence reconciliation on `case`'s issue; whether it held the tick."""
    return _transaction._reconciles_pending_evidence(
        case.github, _TEST_SPEC, case.issue,
        case.github.workflow_label(case.issue), case.github.read_pinned_state(case.issue),
    )


class AnotherRoadBehind:
    """A request behind which, the `times`-th time `when` says, `road` does another road's work.

    The request is the client's where the client carries one of that name, and
    otherwise the git seam of that name on the owner defining it -- the tree
    read evidence is minted over, say. `when` is asked about the request's last
    positional argument: the state a write carries, the body a post carries,
    the location a reread asks about, the commit a tree read names.
    """

    def __init__(self, case, request: str, when, road, times: int = 1) -> None:
        self._case = case
        self._name = request
        self._owner = case.github if hasattr(case.github, request) else GIT_SEAM_OWNERS[request]
        self._request = getattr(self._owner, request)
        self._when = when
        self._road = road
        self._left = times

    def __call__(self, *asked, **named):
        answered = self._request(*asked, **named)
        if self._left and self._when(asked[-1]):
            self._left -= 1
            if not self._left:
                self._road(self._case)
        return answered

    def returning(self, message: str) -> dict:
        """The tick in which a reviewer returned `message`, over a client carrying this request."""
        with patch.object(self._owner, self._name, self):
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
        # The decision the last returned run was handed to the disposition as.
        self.decision: _models._ReviewerDecision | None = None

    def returns(self, message: str, **run_options) -> dict:
        """One tick in which a reviewer returned `message` and its verdict was disposed of."""
        run_options.setdefault(RUN_AGENT, [])
        return self._run(lambda: self._disposes(message), **run_options)

    def finishes(self, *agents, meanwhile=None, **run_options) -> dict:
        """One later tick: the evidence reconciliation, then the waiting verdict acted on where it does not hold.

        `meanwhile` is another road's work once the tick has read the comment
        it acts over.
        """
        run_options.setdefault(RUN_AGENT, list(agents))
        return self._run(lambda: self._finishes(meanwhile), **run_options)

    def pinned(self) -> dict:
        """The pinned comment as the next tick reads it."""
        return self.github.pinned_data(ISSUE)

    def handed(self, state, delivered=None):
        """The subject a reviewer round is handed now, recorded on `state` as its launch records it."""
        if delivered is None:
            delivered = _prompt_context._delivered_thread(self.github, self.issue, state)
        handover = _review_report._resolves_the_subject(self.github, self.issue, state, PR, delivered)
        _review_records._records_the_launch(state, handover.subject)
        return handover

    def _disposes(self, message: str) -> None:
        """The returned round, as the live one records it, handed to the disposition."""
        state = self.github.read_pinned_state(self.issue)
        run = returned_run(self, state, message)
        # The launch's lifetime charge, which the live round's run circuit takes.
        state.set(AGENT_RUNS_USED, (state.get(AGENT_RUNS_USED) or 0) + 1)
        _review_records._records_the_return(
            state, UsageMetrics(backend="codex", input_tokens=REVIEWER_TOKENS), REVIEWER_SESSION, run.subject,
        )
        verdict, body = _completion_verdicts._parse_review_verdict(message)
        self.decision = _models._ReviewerDecision(run, verdict, body)
        _disposition.disposes_of_the_verdict(self.github, _TEST_SPEC, self.issue, state, self.decision)

    def _finishes(self, meanwhile) -> None:
        """The verdict the comment carries, acted on over the run it was returned from."""
        if reconciles(self):
            return
        state = self.github.read_pinned_state(self.issue)
        if meanwhile is not None:
            meanwhile(self)
        waiting = _verdicts.read_returned_verdict(state)
        run = replace(self.decision.run, resolved_over=dict(state.data))
        decision = _models._ReviewerDecision(run, waiting.verdict, waiting.feedback)
        _disposition.acts_on_the_verdict(
            self.github, _TEST_SPEC, self.issue, state, _disposition.VerdictInHand(decision, waiting.evidence),
        )
