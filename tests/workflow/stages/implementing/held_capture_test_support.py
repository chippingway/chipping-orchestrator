# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One implementing issue whose developer reports while an operator pauses it, dispatched as a poll does.

Every tick is a whole dispatch (`issue_processing._process_issue`) over the
hermetic workflow seams: a clean checkout at the issue's own path, whose
push lands. The run an operator pauses the issue under applies `paused` to
the issue itself as it runs, so the dispatch that launched it passed the
hold and every fetch after it -- the live-pause guard's, the next poll's --
reads it. What a held return may leave is measured from the record as the
run was launched over it (`held_returns.Launched`).
"""
from __future__ import annotations

from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    content_hash as _content_hash,
    issue_processing as _issue_processing,
)
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    AGENT_RUN_WRITES,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    Launched,
    _PatchedWorkflowMixin,
)
from tests.workflow.repo_values import HEAD_AFTER_RUN, HEAD_BEFORE_RUN

ISSUE = 730
CAPTURED = _completion_records.DEVELOPER_COMPLETION
RUN_AGENT = "run_agent"

# The two controls an operator holds an issue with.
PAUSED = PAUSED_LABEL
BACKLOG = BACKLOG_LABEL

# The pull request the recovery opens: this client numbers them from 1.
OPENED_PR = 1

# The seams every tick runs over: a clean checkout at the issue's own path,
# whose push lands. The run left HEAD_AFTER_RUN, having started on
# HEAD_BEFORE_RUN.
_CHECKOUT = MappingProxyType({
    "dirty_files": (), "push_branch": True, "issue_checkout": _FAKE_WT,
})

# The one write a held return takes beside its charge and accounting: its capture.
_CAPTURE_WRITES = 1

# The pinned conversation a recovery settles.
SESSION_PIN = "dev_session_id"

# The requirements a road built here was frozen over, which nothing compares
# on the roads it is used on.
_REQUIREMENTS = "abababababababababababababababababababababababababababababababab"

# A conversation the record retired, which a run may still hand back.
RETIRED_SESSION = "sess-retired"

# A capture's stage, as its record spells it.
PENDING = "pending"
HANDED_OFF = "handed_off"
RETIRED = "retired"

# The commit a captured run left, and every head a recovery reads: that one.
SOURCE = HEAD_AFTER_RUN
LEFT = (SOURCE,)

# Every head a run that committed nothing reads.
UNMOVED = (HEAD_BEFORE_RUN,)

# A recorded developer report, as its publication heads it.
_REPORT_HEADING = "Developer report, revision {revision}"


def road(number: int, route: _routes.CompletionRoute = _routes.CompletionRoute.RESUME) -> CompletionRoad:
    """A road on issue `number`'s branch, launched on HEAD_BEFORE_RUN in the fake checkout, over `_REQUIREMENTS`."""
    handoff = _completion_records.CompletionHandoff(route, WorkflowLabel.IMPLEMENTING, _REQUIREMENTS)
    return CompletionRoad(handoff, RoadCheckout(_FAKE_WT, _naming._branch_name(_TEST_SPEC, number), HEAD_BEFORE_RUN))


def capture_of(record: dict) -> _completion_records.CompletionCapture | _completion_records.ResolvedCapture | None:
    """The capture a pinned record carries, read as its own reader reads it."""
    return _spelling.read_record(record.get(CAPTURED))


def _published_so_far(github) -> tuple[int, int, int]:
    """How many pull requests, relabels, and comments the issue's client has taken so far."""
    return len(github.opened_prs), len(github.label_history), len(github.posted_comments)


def retirement() -> dict:
    """The record retiring `RETIRED_SESSION`, as its writer spells it, with no fresh conversation owed."""
    return {"session_ids": [RETIRED_SESSION], "reason": "agent_session_limit", "recovery_pending": False}


class HeldCaptureTicks(_PatchedWorkflowMixin):
    """Whole dispatches of one implementing issue, its developer's run paused under it or not."""

    def seeded(self, **record):
        """The issue on `workflow:implementing`, pinned with `record` beside the requirements it reads as."""
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label=LABEL_IMPLEMENTING)
        github.add_issue(issue)
        github.seed_state(
            ISSUE, user_content_hash=_content_hash._compute_user_content_hash(issue, set()), **record,
        )
        return github, issue

    def dispatch(self, github, issue, run_agent, **seams):
        """Dispatch the issue once, as a poll does; the seams it ran over."""
        return self._run(
            partial(_issue_processing._process_issue, github, _TEST_SPEC, issue),
            run_agent=run_agent,
            **{**_CHECKOUT, **seams},
        )

    def held_mid_run(self, github, issue, finished, control: str = PAUSED, **seams) -> dict:
        """Dispatch a run an operator holds the issue under with `control`, finishing as `finished`; the record it left.

        The run is launched once, and its return held: nothing moved but the
        charge, its one accounted exit, and the capture beside them -- no
        pull request, label, comment, park, input, or session.
        """
        launched = Launched.over(github, ISSUE)
        before = _published_so_far(github)
        self._finished_mid_run = (issue, finished, FakeLabel(control))
        ran = self.dispatch(github, issue, MagicMock(side_effect=self._pauses_mid_run), **seams)
        ran[RUN_AGENT].assert_called_once()
        held = launched.held(
            self,
            github,
            ISSUE,
            writes=AGENT_RUN_WRITES + _CAPTURE_WRITES,
            beside=(CAPTURED,),
        )
        self.assertEqual(held[CAPTURED]["stage"], PENDING)
        self.assertEqual(_published_so_far(github), before)
        return held

    def held_ticks(self, github, issue) -> None:
        """Two dispatches while the issue stays held: neither runs anything nor writes anything."""
        for tick in ("first", "second"):
            with self.subTest(held_tick=tick):
                before = Launched.over(github, ISSUE)
                held = self.dispatch(github, issue, MagicMock())
                held[RUN_AGENT].assert_not_called()
                after = (github.pinned_data(ISSUE), github.write_state_calls)
                self.assertEqual(after, (before.record, before.writes))

    def unpaused(self, github, issue, **seams):
        """Take the control off and dispatch once, over the checkout the run left; no developer may run."""
        issue.labels.remove(self._finished_mid_run[-1])
        recovered = self.dispatch(
            github,
            issue,
            MagicMock(),
            **{"has_new_commits": True, "head_shas": LEFT, **seams},
        )
        recovered[RUN_AGENT].assert_not_called()
        return recovered

    def published(self, github, revision: int = 1) -> dict:
        """Assert one pull request opened and handed to review, carrying one report at `revision`; the record."""
        reports = [
            posted for posted in github.get_pr(OPENED_PR).issue_comments
            if _REPORT_HEADING.format(revision=revision) in posted.body
        ]
        opened = (len(github.opened_prs), len(reports))
        self.assertEqual(opened, (1, 1))
        self.assertIn((ISSUE, LABEL_VALIDATING), github.label_history)
        return github.pinned_data(ISSUE)

    def _pauses_mid_run(self, *_spawn, **_options):
        """The run an operator holds the issue under: the control applied as it runs, then what it finished as."""
        issue, finished, control = self._finished_mid_run
        issue.labels.append(control)
        return finished
