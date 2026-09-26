# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One developer report's whole life on an open pull request, a tick at a time.

The fix-loop world walked through the dispatcher rather than a handler at a
time: the pull request carries the report it was opened with, a human edits the
requirements, and every tick after that is `_route_issue_to_handler` over
whatever label the issue carries by then. So the reconciliation that finishes an
outstanding report runs ahead of the stage exactly as it does on a live host,
and nothing passes between ticks but the issue, its pull request and the pinned
comment.

Every agent the walk pays for is staged up front, in the order the workflow has
to ask for them, and each one records what it was handed as it is spawned. A
tick that spawns a run the walk never staged fails there and then; one that
spawns a staged run early or out of turn leaves a record a case reads back --
the role that was staged, the round the issue stood on, the prompt, and whether
the pull request was still owed a report.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github import developer_reports as _developer_reports
from orchestrator.observability.usage import metrics as _usage_metrics
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    report_delivery as _report_delivery,
)
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as _crashes,
    fix_reports as _fix_world,
)
from tests.workflow.engine import usage_frames as _usage_frames
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    REVIEW_APPROVED_MESSAGE,
    REVIEW_CHANGES_REQUESTED_MESSAGE,
    _agent,
)

ISSUE = 1_798

PR = 17_980

# The requirements the human rewrites the issue to once the pull request is
# open, which is what the first developer run of the walk is resumed on.
EDITED_REQUIREMENTS = "The criteria the pull request was opened against have moved."

DRIFT_REPORT = "Answers the edited criteria in the pushed commit; the suite passes."

# What the first reviewer asks for, which only the report can answer, and the
# report that answers it on the commit the pull request already carries.
REPORT_REQUEST = _fix_world.REPORT_ONLY_FEEDBACK

FINAL_REPORT = "Ran `uv run pytest tests` on the same commit; every check passes."

# A human's comment on the pull request, landing while the developer is out
# writing that report. Nothing before the approval is answering it, so it is
# the stage the approved pull request reaches that has to.
LATER_FEEDBACK = "Please mention the flaky retry in the description as well."

LATER_FEEDBACK_ID = _drift_world.LATER_COMMENT_ID

DOCS_UNCHANGED = "The documentation already describes it.\n\nDOCS: NO_CHANGE"

FEEDBACK_ACK = "ACK: the report already covers the retry."

# How the drift report's post is left unconfirmed: GitHub refused it, or took it
# and the response never came back.
REFUSED = "refused"

ACCEPTED = "accepted"

# The other places the report-only round can be interrupted: on the relabel
# that hands the round back for review, which it takes ahead of the binding --
# and on that one AND the relabel the recovery then hands the round back with,
# which it takes after the write that retires the settled-round mark.
RELABEL = "relabel"

RELABELS = "relabels"

# The two roles a walk stages runs for.
DEVELOPER = "developer"

REVIEWER = "reviewer"

# The backend the walk's reviewers run under, pinned so the usage each one
# reports is parsed the same way on every host.
_REVIEW_BACKEND = "codex"

# What is left once the report-only round has been handed back: the fresh
# reviewer, the docs pass, `in_review` reading the human's comment, and the
# fixing round that answers it.
_CLOSING_TICKS = 4


@dataclass(frozen=True)
class Spawn:
    """One agent the walk paid for, and the issue as it stood at the spawn."""

    role: str
    backend: str
    prompt: str
    owed: bool
    review_round: int


class _Staged:
    """One run the walk pays for, recording what it was handed.

    `during` is what happens while the agent is out, after the spawn was
    recorded and before its reply reaches the stage -- a human commenting, or
    GitHub starting to answer the report's post differently.
    """

    def __init__(self, case, role: str, reply: str, *during) -> None:
        self._case = case
        self._role = role
        self._reply = reply
        self._during = during

    def __call__(self, backend, prompt, *_called, **_options):
        state = self._case.github.read_pinned_state(self._case.issue)
        self._case.spawns.append(Spawn(
            role=self._role,
            backend=backend,
            prompt=prompt,
            owed=_report_delivery.owes_a_report(state),
            review_round=state.get("review_round"),
        ))
        for change in self._during:
            change()
        session = (
            _fix_world.REVIEWER_SESSION if self._role == REVIEWER
            else _fix_world.DEV_SESSION
        )
        return _agent(
            session_id=session, last_message=self._reply, stdout=stdout_of(backend),
        )


def stdout_of(backend: str) -> str:
    """The usage frames a run under `backend` prints: one turn, fixed tokens."""
    if backend == _REVIEW_BACKEND:
        return _usage_frames._codex_stdout_no_model()
    return _usage_frames._claude_stdout()


def tokens_of(backend: str) -> int:
    """The tokens one run under `backend` adds to the issue's pinned total."""
    usage = _usage_metrics.parse_agent_usage(backend, stdout_of(backend))
    return sum((
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
    ))


def _unanswered(github, how: str) -> tuple:
    """What GitHub starts doing to report posts while a run is out, by `how`.

    Nothing, for an interruption that is not the post's own.
    """
    failures = github.report_failures
    unanswered = {REFUSED: failures.refused, ACCEPTED: failures.lost}.get(how)
    if unanswered is None:
        return ()
    return (partial(unanswered.add, PR),)


def _answered(github) -> None:
    """GitHub answers report posts again."""
    github.report_failures.refused.clear()
    github.report_failures.lost.clear()


class _ReportLifecycle(_fix_world._FixReportMixin):
    """The walk, and what a case reads back once it has ended.

    `drift` names how the drift report's publication is interrupted and
    `round_` how the report-only round's is; every tick in between is a plain
    dispatch with nothing staged but the runs.
    """

    def walk(self, drift: str, round_: str) -> None:
        """Walk the issue from the requirements edit to the answered feedback."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.spawns = []
        self._runs = MagicMock(side_effect=_fix_world._Runs(
            _Staged(
                self, DEVELOPER, _drift_world.reported(DRIFT_REPORT),
                *_unanswered(self.github, drift),
            ),
            _Staged(
                self, REVIEWER, f"{REPORT_REQUEST}\n\n{REVIEW_CHANGES_REQUESTED_MESSAGE}",
            ),
            _Staged(
                self, DEVELOPER, _drift_world.reported(FINAL_REPORT),
                partial(_fix_world.published_report, self, LATER_FEEDBACK),
                *_unanswered(self.github, round_),
            ),
            _Staged(self, REVIEWER, REVIEW_APPROVED_MESSAGE),
            _Staged(self, DEVELOPER, DOCS_UNCHANGED),
            _Staged(self, DEVELOPER, FEEDBACK_ACK),
        ))
        _drift_world.edits(self, EDITED_REQUIREMENTS)
        with patch.object(config, "REVIEW_AGENT", _REVIEW_BACKEND):
            self._resumes_on_the_edit(drift)
            self._reports_on_the_same_commit(round_)
            for _ in range(_CLOSING_TICKS):
                self._tick()

    def reports(self) -> list:
        """Every developer report the pull request carries, oldest first."""
        read = (
            _developer_reports.developer_report_from_comment(
                posted, bot_login=self.github._bot_login,
            )
            for posted in self.pull_request.issue_comments
        )
        return [report for report in read if report is not None]

    def _resumes_on_the_edit(self, drift: str) -> None:
        """The drift resume, and the tick a refused report holds on its own."""
        self._tick()
        if drift == REFUSED:
            self._tick()
        _answered(self.github)

    def _reports_on_the_same_commit(self, round_: str) -> None:
        """The review that asks for the report, and the round that writes it.

        Cut short on its relabel, the round leaves its report unbound on
        `workflow:fixing`, and the tick after it is the one that finishes it --
        or, cut short on its own hand-back too, leaves the round settled and
        handed back on the comment with the label still unmoved, for the tick
        after that.
        """
        if round_ not in {RELABEL, RELABELS}:
            self._tick()
            _answered(self.github)
            return
        with _crashes.dying_before_the_relabel(self):
            self._tick()
        if round_ == RELABELS:
            with _crashes.dying_before_the_relabel(self):
                self._tick()
        self._tick()

    def _tick(self) -> None:
        """One whole dispatched tick, over whatever label the issue carries."""
        self._ticked(self._dispatched, self._runs)

    def _dispatched(self, github, issue, *, run_agent, **run_options):
        return self._run(
            partial(
                _issue_processing._route_issue_to_handler,
                github, _TEST_SPEC, issue, github.workflow_label(issue),
            ),
            run_agent=run_agent,
            **run_options,
        )
