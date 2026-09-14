# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The settled cancellation a restart is authorized over, and how it is routed.

Every case starts from the same shape -- an issue whose late cycle a close
ended, whose ending owes the remote nothing, and which an operator has
reopened and taken `rejected` off -- so it is built once here. The route is
the dispatcher's own, because the guard under test runs BEFORE a label becomes
a handler call and whether that handler was reached is what a case asserts on.

The pinned comment a case seeds is described here too: one key from every
family a restart drops beside the ones it keeps, so the projection is asserted
against a comment a live issue could really be carrying rather than against
the handful of keys the assertion happens to name.
"""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from unittest.mock import Mock, patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import endings as _endings, phases as _late_phases, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration, LateResource, LateResourceKind, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_terminal as _late_cancellation_terminal,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
    PLAN_PR_NUMBER,
    ROOT_ISSUE,
    late_generation,
)

WORKFLOW_LOG = "orchestrator.workflow"

# The one funnel every dispatched handler is called through.
_CALL_HANDLER = "_call_handler"

# The receipt step a crash is simulated by holding: the label lands and
# nothing records that it did.
_RECORDED = "_terminal_recorded"

# The cycle a restart of `CANCELLED` mints. Spelled from the recorded cycle
# rather than as a literal, since what a restart may name is exactly one more
# than the cycle in hand.
RESTART_CYCLE_ID = CYCLE_ID + 1

CANCELLED_AT = "2026-05-04T09:00:00+00:00"

HUMAN = "geserdugarov"
OUTSIDER = "passer-by"

# An issue number this record could not have been written on. A pinned comment
# is read off the issue it sits on, so a record naming another one is damage --
# and one naming no issue at all is a record the telemetry contract refuses.
FOREIGN_ISSUE = 1234

ANCESTRY_ROOT = 7

# The child a cancelled split created and recorded, whose receipt the ending
# discharges precisely so the terminal a restart reads is one it will accept.
CHILD_NUMBER = 91

# The prefix a restart's own notice on the thread is stamped with, which is
# what a case counts to prove the notice was said once.
RESTART_MARKER_PREFIX = "<!--orchestrator-late-restart:"

# The one obligation a cancellation can be left holding here. Its state is
# what tells a settled ending from one the cleanup path still owns.
SUPERSEDED_BRANCH = "orchestrator/issue-41"

KEY_RESTART_PENDING = "late_restart_pending"
KEY_RESTART_TARGET = "late_restart_target"
KEY_RESTART_CYCLE_ID = "late_restart_cycle_id"
KEY_RESTART_PREDECESSOR = "late_restart_predecessor"
KEY_CYCLE_ID = "late_cycle_id"
KEY_ROOT_ISSUE = "late_root_issue"
KEY_CURRENT_ISSUE = "late_current_issue"
KEY_ANCESTRY_ROOT = "late_ancestry_root_issue"
KEY_PLAN_PR_NUMBER = "late_plan_pr_number"
KEY_TERMINAL_CYCLE = "late_terminal_cycle_id"
KEY_TERMINAL_CONFIRMED = "late_terminal_confirmed"
KEY_ORCHESTRATOR_IDS = "orchestrator_comment_ids"

# The bare tag the workflow label a restart applies is recorded under.
DECOMPOSING_STAGE = "decomposing"

EVENT_LATE_RESTART = "late_restart"
EVENT_LATE_FAILURE = "late_failure"

# A cancelled cycle whose ending reconciled everything it took on: the state
# an operator is looking at when they decide to authorize a fresh attempt.
CANCELLED = replace(
    late_generation(resources=()).cancel(CANCELLED_AT),
    phase=_late_phases.LatePhase.CANCELLING,
)

# One pinned key from every family a restart drops: the sessions, the pull
# request and branch, the children and the dependency graph, the snapshot this
# issue was cut from, the exemption and the authorization that let one
# oversized candidate past the size gate, the parks, the drift baseline, the
# counters, the launch a charge was taken for, and the timestamps.
CARRIED_OVER = MappingProxyType({
    "dev_session_id": "dev-sess",
    "decomposer_session_id": "dec-sess",
    "late_session_id": "late-sess",
    "pr_number": 12,
    "branch": "orchestrator/issue-41-work",
    "children": [91, 92],
    "dep_graph": {"91": []},
    "expected_children_count": 2,
    "split_ledger_sealed": CYCLE_ID,
    KEY_ANCESTRY_ROOT: ANCESTRY_ROOT,
    "late_ancestry_snapshot_ref": (
        "refs/orchestrator/late-split/issue-7/cycle-1/gen-0"
    ),
    "late_exempt_sha": CANDIDATE_SHA,
    "late_override_candidate_sha": CANDIDATE_SHA,
    "awaiting_human": True,
    "park_reason": "late_question",
    "user_content_hash": "5f4dcc3b5aa765d61d8327deb882cf99",
    "retry_count": 3,
    "review_round": 2,
    "silent_park_count": 1,
    "pickup_comment_id": 900,
    "created_at": "2026-01-01T00:00:00+00:00",
    "last_agent_action_at": "2026-05-04T08:00:00+00:00",
    "agent_run_reservation": "started",
})

# The comment ids this issue's thread already carried, and what the projection
# keeps beside them.
SEEDED_COMMENT_IDS = (901, 902)

KEPT = MappingProxyType({
    KEY_ORCHESTRATOR_IDS: list(SEEDED_COMMENT_IDS),
    "issue_agent_runs": 4,
    "issue_total_tokens": 45200,
    "issue_total_cost_usd": 0.87,
    "issue_cost_sources": ["reported"],
    "agent_run_allowance": 60,
    "agent_runs_used": 5,
})


# The two shapes of damaged identity a restart repairs before it writes: one
# naming an issue this record cannot be on, and one naming no root the
# telemetry contract could join a record by.
DAMAGED_IDENTITIES = (
    replace(CANCELLED, current_issue=FOREIGN_ISSUE),
    replace(CANCELLED, root_issue=0),
)


# The obligation no ledger entry carries: a plan pull request this generation
# names and cannot show it ever held, since the number and the description it
# displaced are written as ONE thing. Only the cancellation's own reading
# reports it, and no pass can settle it -- a human repairs the record.
UNPROVABLE_HOLD = replace(CANCELLED, plan_pr_number=PLAN_PR_NUMBER)


# The obligation no ledger names yet: a cycle cancelled between the
# supersession of its plan PR and the write that records the branch that PR
# carried. The announcement's own receipt is the only thing saying the branch
# exists, so the ending DISCOVERS it rather than reading it -- which is why
# nothing may decide this cycle owes nothing before the ending has run.
ANNOUNCED = replace(CANCELLED, links_announced=True)

KEY_BRANCH = "branch"


def owing_cycle(
    owed: LateResourceState = LateResourceState.PENDING,
) -> LateGeneration:
    """The same cancellation with one obligation the remote still holds."""
    return CANCELLED.with_resource(LateResource(
        kind=LateResourceKind.BRANCH,
        target=SUPERSEDED_BRANCH,
        resource_state=owed,
    ))


def owing_child() -> LateGeneration:
    """The same cancellation with one child receipt still undischarged.

    The obligation the ENDING's reading walks past -- it lists branches, refs,
    and plan pull requests -- and only the domain's counts.
    """
    return CANCELLED.with_resource(LateResource(
        kind=LateResourceKind.CHILD,
        target=str(CHILD_NUMBER),
        resource_state=LateResourceState.PENDING,
    ))


def crashed_ending(case) -> None:
    """One closed owner whose terminal landed and was never recorded.

    The window neither half of the receipt covers: the label write returned
    and the process died before the write that would have said so.
    """
    case._seed(terminal=False)
    case.issue.closed = True
    with patch.object(_late_cancellation_terminal, _RECORDED, Mock()):
        case._reported_route()


def notice_id(case) -> int:
    """The id the one restart notice on this thread took."""
    return next(
        posted.id for posted in case.issue.comments
        if RESTART_MARKER_PREFIX in (posted.body or "")
    )


def records_named(case, family: str) -> list:
    """Every record of one family both sinks were handed."""
    return [
        record for record in case.github.recorded_events
        if record.get("event") == family
    ]


def fresh_state(**kept) -> dict:
    """What the pinned comment carries once a restart has retired its marker.

    Built from the record the domain projects rather than spelled as literals,
    so a case asserting the WHOLE comment is asserting what survived the
    projection rather than re-deriving the projection itself.
    """
    projected = PinnedState(data={})
    _late_state.write_late_generation(projected, LateGeneration(
        cycle_id=RESTART_CYCLE_ID,
        root_issue=ROOT_ISSUE,
        current_issue=LATE_ISSUE_NUMBER,
        lineage_depth=0,
        restart_predecessor=CYCLE_ID,
    ))
    return {**projected.data, **kept}


class RestartCase:
    """One reopened owner, and the tick that decides what it is."""

    def _seed(
        self,
        generation: LateGeneration = CANCELLED,
        *,
        label: str | None = None,
        author: str = HUMAN,
        terminal: bool = True,
        **extra_state,
    ) -> None:
        """Seed the issue an operator has taken `rejected` off.

        `label` seeds an issue that is somewhere else entirely -- because a
        human moved it, because a control label parks it, or because a restart
        applied its target and died before retiring the marker.

        `terminal` is the proof the ending records for a `rejected` it could
        see on the issue, and it is on by default because that is the state an
        operator removing the label is looking at. `terminal=False` is every
        issue that never got there: one whose workflow label a human stripped
        mid-cleanup, one whose terminal write GitHub refused, and one whose
        cancellation ended before this record existed at all.
        """
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            LATE_ISSUE_NUMBER, label=label, author=author,
        )
        self.github.add_issue(self.issue)
        recorded = PinnedState(data=dict(extra_state))
        _late_state.write_late_generation(recorded, generation)
        if terminal and generation.is_present:
            _endings.record_terminal(
                recorded, generation.cycle_id, confirmed=True,
            )
        self.github.seed_state(LATE_ISSUE_NUMBER, **recorded.data)

    def _route(self) -> Mock:
        """Route this issue the way a tick does, holding every handler call.

        Held at the one funnel every dispatch goes through rather than at the
        owner one label names, so a case asserts that NO handler ran rather
        than that one particular handler did not -- which is what a guard
        ahead of the table is about, and what covers the labels that name no
        handler at all.
        """
        label = self.github.workflow_label(self.issue)
        dispatched = Mock()
        with patch.object(_stage_targets, _CALL_HANDLER, dispatched):
            _issue_processing._route_issue_to_handler(
                self.github, _TEST_SPEC, self.issue, label,
            )
        return dispatched

    def _reported_route(self) -> Mock:
        """The same tick, where it is expected to say what it did."""
        with self.assertLogs(WORKFLOW_LOG):
            return self._route()

    def _pinned(self) -> dict:
        """What this issue's pinned comment records right now."""
        return self.github.pinned_data(LATE_ISSUE_NUMBER)

    def _notices(self) -> list:
        """Every restart notice this run left on the thread."""
        return [
            body for _, body in self.github.posted_comments
            if RESTART_MARKER_PREFIX in body
        ]

    def _notice_count(self) -> int:
        """How many restart notices this run left on the thread."""
        return len(self._notices())

    def _labels(self) -> tuple:
        """Every workflow label this run wrote on the issue."""
        return tuple(self.github.label_history)
