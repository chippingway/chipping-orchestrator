# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one committed candidate the size gate's tests measure.

A gate run is an implementing tick whose worktree already carries commits, so
no agent is spawned and the whole tick is the publication seam: whatever the
measurement seeds say is what the candidate is, and what the tick did with it
is the only thing left to assert.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    lineage as _lineage,
    phases as _late_phases,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    LABEL_IMPLEMENTING,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
    _stand_opened_prs_on_the_push,
)

GATE_ISSUE_NUMBER = 300
GATE_THRESHOLD = 4000
SMALL_ADDITIONS = 12
OVERSIZED_ADDITIONS = 9123

# The lifetime ledger a gate run is asked under, in both readings that could
# change what a commit-id decision means: runs to spare, and none left. The
# gate spawns nothing either way, so a case naming one is naming the state the
# ISSUE is in rather than a run it is about to pay for.
GATE_ALLOWANCE = 4

LEDGERS = MappingProxyType({
    "some": {
        _run_ledger_values.AGENT_RUN_ALLOWANCE: GATE_ALLOWANCE,
        _run_ledger_values.AGENT_RUNS_USED: 1,
    },
    "none": {
        _run_ledger_values.AGENT_RUN_ALLOWANCE: GATE_ALLOWANCE,
        _run_ledger_values.AGENT_RUNS_USED: GATE_ALLOWANCE,
    },
})

CHILD_ROOT_ISSUE = 7
CHILD_PARENT_ISSUE = 8
CHILD_DEPTH = 2
CHILD_SCOPE = "the slice this child owns"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
COUNT_ADDED_LINES = "_count_added_lines"
FREEZE_BASE_COMMIT = "_freeze_base_commit"
BASE_OBJECT_PRESENT = "_base_object_present"
WORKTREE_PATH = "_worktree_path"

SET_LABEL = "set_workflow_label"
# The client call one step past the push, which is where a snapshot sees what
# the tick made durable BEFORE it published rather than after.
FIND_OPEN_PR = "find_open_pr"

# The two things a refusal says out loud, wrapped where a case has to know
# what the pinned comment already carried when one of them went out.
POST_COMMENT = "comment"
EMIT_EVENT = "emit_event"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"

EVENT_LATE_MEASUREMENT = "late_measurement"
EVENT_LATE_FAILURE = "late_failure"

KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_BASE_SHA = "late_base_sha"
KEY_THRESHOLD = "late_threshold"
KEY_ADDITIONS = "late_additions"
# What a reading the transport lost leaves on the pair it was owed for: the
# readings lost in a row, and -- once one of them has been announced -- the
# step the notice on the thread named.
KEY_MISS_COUNT = "late_measurement_miss_count"
KEY_MEASUREMENT_FAILURE = "late_measurement_failure"
KEY_PHASE = "late_phase"
KEY_CYCLE_ID = "late_cycle_id"
KEY_GENERATION = "late_generation"
KEY_ROOT_ISSUE = "late_root_issue"
KEY_CURRENT_ISSUE = "late_current_issue"
KEY_LINEAGE_DEPTH = "late_lineage_depth"
KEY_SCOPE = "late_scope"
KEY_EXEMPT_SHA = "late_exempt_sha"

# The park an adjudicated candidate is held on while nothing says a human
# authorized publishing it: its own reason, because what ends it is a named
# command rather than another reading or another look at the checkout.
PARK_UNAUTHORIZED_EXEMPTION = "late_unauthorized_exemption"

KEY_RETIRED_CYCLE = "late_retired_cycle_id"

PHASE_MEASURING = "measuring"

TRUSTED_AUTHOR = "alice"
PRIOR_ACTION_COMMENT_ID = 900
REPLY_COMMENT_ID = 1100
BARE_CONTINUE = "/orchestrator continue"
# The session a resume continues, seeded so a resumed run is the pinned
# one rather than a fresh spawn.
DEV_SESSION = "sess-1"
# A directory the recovery's existence probe finds, standing in for the
# checkout the recorded commit lives in.
TEMP_WORKTREE_ROOT = Path("/tmp")


def recorded_generation(*, dropping: str = "", **overrides) -> dict:
    """The pinned fields a generation this gate froze round-trips through.

    `dropping` takes one of them back off the written comment afterwards,
    which is the only way a damaged identity can be seeded: a generation with
    no cycle writes nothing at all, so the record goes down whole and is then
    damaged the way a real one gets damaged.
    """
    recorded = PinnedState(data={})
    _late_state.write_late_generation(
        recorded,
        LateGeneration(**{
            "cycle_id": 1,
            "generation": 1,
            "root_issue": GATE_ISSUE_NUMBER,
            "current_issue": GATE_ISSUE_NUMBER,
            "lineage_depth": 0,
            "candidate_sha": MEASURED_CANDIDATE_SHA,
            "base_sha": MEASURED_BASE_SHA,
            "threshold": GATE_THRESHOLD,
            "phase": _late_phases.LatePhase.MEASURING,
            **overrides,
        }),
    )
    if dropping:
        recorded.data.pop(dropping, None)
    return recorded.data


def recorded_ancestry() -> dict:
    """The pinned fields a child born of a late split carries."""
    recorded = PinnedState(data={})
    _lineage.write_late_ancestry(
        recorded,
        _ancestry.LateAncestry(
            root_issue=CHILD_ROOT_ISSUE,
            lineage_depth=CHILD_DEPTH,
            parent_issue=CHILD_PARENT_ISSUE,
            cycle_id=3,
            generation=1,
            base_branch="main",
            scope=CHILD_SCOPE,
        ),
    )
    return recorded.data


class _RecordAtHandoff:
    """What the pinned comment says at the moment one client call is made.

    Each of these calls is an effect a crash boundary sits behind -- the label
    that hands the issue to another stage, the pull-request lookup one step
    past the push -- so this reads DURABLE state as it stands then, not the
    tick's in-memory copy, which would show writes no process had made yet.
    """

    def __init__(self, github, method: str = SET_LABEL) -> None:
        self.pinned: dict = {}
        self._github = github
        self._method = method
        self._wrapped = getattr(github, method)

    def __call__(self, *called, **options):
        self.pinned = dict(
            self._github.pinned_data(GATE_ISSUE_NUMBER),
        )
        return self._wrapped(*called, **options)

    def held(self):
        """Patch the call this records, for the duration of one tick."""
        return patch.object(self._github, self._method, self)


class _PublicationAssertions:
    """What the tick did with the branch, and what it paid for."""

    def _assert_published(self, mocks) -> None:
        mocks[PUSH_BRANCH].assert_called_once()

    def _assert_held(self, mocks) -> None:
        """Nothing published: no push, no pull request."""
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.opened_prs, [])

    def _assert_no_agent(self, mocks) -> None:
        """Nothing was re-run: the reading is what a retry buys."""
        mocks[RUN_AGENT].assert_not_called()

    def _assert_charged_nothing(self, ledger) -> None:
        """The issue is exactly as far through its lifetime as it was.

        The gate is a reading rather than a run, so no path through it may
        move the count -- least of all on the issue that has none left, where
        a charge taken here would be one nothing spawned.
        """
        self.assertEqual(
            self._pinned().get(_run_ledger_values.AGENT_RUNS_USED),
            ledger[_run_ledger_values.AGENT_RUNS_USED],
        )

    def _assert_resumed(self, mocks) -> None:
        """The developer ran, which is what guidance buys."""
        mocks[RUN_AGENT].assert_called_once()


class _MeasurementAssertions:
    """What the tick read about the candidate, and what it recorded."""

    def _assert_measured(self, mocks) -> None:
        mocks[COUNT_ADDED_LINES].assert_called_once()

    def _assert_unmeasured(self, mocks) -> None:
        mocks[COUNT_ADDED_LINES].assert_not_called()

    def _assert_parked(self) -> None:
        pinned = self._pinned()
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)

    def _assert_announced(self, failure) -> None:
        """One mention, naming the step, over a record that already says so.

        The record is half of the assertion because it is what makes the
        mention the only one: the poll after this reads that field back and
        holds its tick silently where it finds the step it stopped at.
        """
        self.assertEqual(len(self.github.posted_comments), 1)
        mention = self.github.posted_comments[0][1]
        self.assertIn(config.HITL_MENTIONS, mention)
        self.assertIn(failure, mention)
        self.assertEqual(
            self._pinned()[KEY_MEASUREMENT_FAILURE], failure,
        )

    def _assert_missed(self, count: int = 1) -> None:
        """One reading the transport lost, counted and otherwise unsaid.

        The count is the whole of what a miss inside the bound leaves: the
        step it stopped at is said to the log and to both streams and to no
        human, so nothing on the issue says one is waiting and the next tick
        re-reads the same pair by itself.
        """
        pinned = self._pinned()
        self.assertEqual(pinned[KEY_MISS_COUNT], count)
        self.assertNotIn(KEY_MEASUREMENT_FAILURE, pinned)
        self.assertFalse(pinned.get(AWAITING_HUMAN))
        self.assertIsNone(pinned.get(PARK_REASON))
        self.assertEqual(self.github.posted_comments, [])

    def _assert_frozen(self, additions=None) -> None:
        """The pair this gate froze, as the pinned comment holds it back."""
        pinned = self._pinned()
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertEqual(pinned[KEY_PHASE], PHASE_MEASURING)
        self.assertEqual(pinned.get(KEY_ADDITIONS), additions)


class _GateCase(
    _PublicationAssertions, _MeasurementAssertions, _PatchedWorkflowMixin,
):
    """One implementing tick whose candidate is already committed.

    Everything past `setUp` reads the issue in hand rather than the number
    that one seeds, so a case whose issue is a child a real split created --
    an issue whose number nothing can know in advance -- inherits the whole of
    this without re-stating it.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(GATE_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(GATE_ISSUE_NUMBER)

    def _seed(self, **state) -> None:
        """Replace this issue's pinned state with the one a test is about."""
        self.github.seed_state(self.issue.number, **state)

    def _reply(self, body: str) -> None:
        """Add one trusted human comment past the consumed watermark."""
        self.issue.comments.append(
            FakeComment(REPLY_COMMENT_ID, body, user=FakeUser(TRUSTED_AUTHOR)),
        )

    def _run_gate(self, worktree: Path = TEMP_WORKTREE_ROOT, **run_options):
        """Run one tick in a checkout the gate's own probes can find.

        The path is patched for every gate run rather than for the few that
        ask about it, because a recorded candidate is reconciled against the
        checkout BEFORE anything spawns: a test seeding one over a worktree
        that does not exist is seeding a state the tick is right to park on,
        and would be asserting on that park instead of on the gate.
        """
        run_options.setdefault("has_new_commits", True)
        run_options.setdefault("run_agent", _agent(last_message="implemented"))
        opened_before = len(self.github.opened_prs)
        with patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=worktree,
        ):
            mocks = self._run_implementing(
                self.github, self.issue, **run_options,
            )
        _stand_opened_prs_on_the_push(self.github, mocks, opened_before)
        return mocks

    def _pinned(self) -> dict:
        return self.github.pinned_data(self.issue.number)

    def _records(self, family: str) -> list[dict]:
        return [
            record for record in self.github.recorded_events
            if record.get("event") == family
        ]


class _ParkedRetryCase(_GateCase):
    """A measurement park, and the tick a human's reply to it drives."""

    def _park(self, reply: str) -> None:
        """Seed the park a measurement that could not be taken leaves."""
        self._park_state(reply, **recorded_generation())

    def _park_without_a_record(self, reply: str = BARE_CONTINUE) -> None:
        """The same park, taken before any pair could be frozen."""
        self._park_state(reply)

    def _park_after_misses(self, lost: int, announced=None) -> None:
        """The same park, over a pair that has lost `lost` readings in a row.

        Lost to the TRANSPORT, since that is the only step the bound counts:
        a record carrying misses of any other kind is one no retry wrote.
        `announced` is the step a notice on the thread already named, which
        only a pair whose bound has run out carries -- a quiet miss tells
        nobody anything, so it leaves that field exactly as it found it.
        """
        self._park_state(reply=BARE_CONTINUE, **recorded_generation(
            measurement_miss_count=lost, measurement_failure=announced,
        ))

    def _park_state(self, reply: str, **recorded) -> None:
        """Seed one measurement park and the human reply answering it."""
        self._seed(**{
            AWAITING_HUMAN: True,
            PARK_REASON: PARK_MEASUREMENT_FAILED,
            LAST_ACTION_COMMENT_ID: PRIOR_ACTION_COMMENT_ID,
            "dev_agent": "codex",
            "dev_session_id": DEV_SESSION,
            **recorded,
        })
        self._reply(reply)
