# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late adjudication settles and persists before it spawns anything."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import retry_budget as _retry_budget
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
    LateVerdict,
)
from orchestrator.workflow.stages.decomposition import (
    late_coordinator as _coordinator,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import STAGE_DECOMPOSING
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_run_support import (
    HoldSnapshot,
    LateCase,
    SpawnSnapshot,
    WorktreeSeed,
    adjudicate,
    agent_reply,
)

FUTURE_WINDOW = "2999-01-01T00:00:00+00:00"

# A budget in force, so what the gate charges is read against a cap of its own
# rather than against whatever the environment configures.
BOUNDED_CAP = 3

# One attempt bought by a continuation and not yet spent.
GRANTED = 1

# The three records that are not a live oversized candidate: an issue that
# never entered the gate, one measured under its ceiling, and a cancelled
# cycle, which is cleanup-only.
_NOT_LATE_CASES = (
    ("never entered the gate", LateGeneration()),
    ("measured under its ceiling", _support.late_generation(
        additions=_support.UNDERSIZED_ADDITIONS,
    )),
    ("cancelled cycle", _support.late_generation(cancelled=True)),
)

WORKFLOW_LOG = "orchestrator.workflow"

ERROR = "ERROR"


class _MergedDuringRun:
    """A human merging the held plan PR while the agent is still running."""

    def __init__(self, plan_pr, agent_result) -> None:
        self._plan_pr = plan_pr
        self._agent_result = agent_result

    def __call__(self, *_args, **_kwargs):
        self._plan_pr.merged = True
        self._plan_pr.head.sha = _support.MERGED_SHA
        return self._agent_result


class _RefusedFirstWrite:
    """A pinned write that refuses once, the way an oversized payload does.

    Only the first one: the write that would preserve a plan PR's body is the
    large one, and the park that follows it writes a comment-sized payload
    that GitHub takes.
    """

    def __init__(self, github) -> None:
        self._write = github.write_pinned_state
        self._refused = False

    def __call__(self, issue, state):
        if self._refused:
            return self._write(issue, state)
        self._refused = True
        raise RuntimeError("payload too large")


class NotLateTest(unittest.TestCase):
    """An issue with no live oversized generation is nobody's to adjudicate."""

    def test_nothing_is_spawned_or_written(self) -> None:
        for name, generation in _NOT_LATE_CASES:
            with self.subTest(case=name):
                github = FakeGitHubClient()

                outcome, spawn = adjudicate(
                    github, _support.seed_late_issue(github, generation),
                )

                self.assertEqual(
                    outcome.disposition, _LateDisposition.NOT_LATE,
                )
                spawn.assert_not_called()
                self.assertEqual(github.write_state_calls, 0)


class HoldBeforeSpawnTest(LateCase, unittest.TestCase):
    """The plan PR is settled before an agent is ever started."""

    def setUp(self) -> None:
        super().setUp()
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(
            self.github,
            _support.late_generation(),
            pr_number=_support.PLAN_PR_NUMBER,
            **{_support.KEY_PLAN_PATH: _support.PLAN_PATH},
        )
        self.plan_pr = _support.seed_plan_pr(self.github)

    def test_the_hold_lands_before_the_agent_runs(self) -> None:
        recorder = HoldSnapshot(self.github)

        with patch.object(self.github, "edit_pr_body", recorder):
            self._adjudicate(agent_reply(_support.SPLIT_REPLY))

        self.assertEqual(
            [held.get(_support.KEYS.plan_pr_body) for held in recorder.snapshots],
            [_support.PLAN_PR_BODY],
        )
        self.assertNotIn(_support.PLAN_PR_BODY, self.plan_pr.body)

    def test_a_failed_hold_parks_without_spawning(self) -> None:
        refused = patch.object(
            self.github, "edit_pr_body", side_effect=RuntimeError,
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            outcome, spawn = self._adjudicate()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertTrue(self._pinned().get(_support.KEYS.awaiting))
        self.assertEqual(
            self._pinned().get(_support.KEYS.phase), LatePhase.HOLDING_PLAN_PR,
        )
        # The gate still precedes the pre-spawn write, so a run that never
        # happened leaves no record claiming it did.
        self.assertNotIn(_support.KEYS.source_sha, self._pinned())

    def test_an_unpersisted_hold_parks_unspawned(self) -> None:
        # A write that does not land leaves no preserved body, so there is no
        # hold to take -- and no agent may run against a pull request a human
        # still sees as an unmarked, ready change.
        refused = patch.object(
            self.github,
            "write_pinned_state",
            _RefusedFirstWrite(self.github),
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            outcome, spawn = self._adjudicate()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(self.plan_pr.body, _support.PLAN_PR_BODY)

    def test_an_unholdable_body_parks_every_tick(self) -> None:
        # The failure this leaves unreachable: a body that fits the comment
        # exactly, held, and then a pre-spawn write GitHub refuses -- which
        # would strand the pull request held, announce nothing, and raise
        # again on every retry.
        self.plan_pr.body = "p" * _late_session.MAX_RECORDED_BODY

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                with self.assertLogs(WORKFLOW_LOG, level=ERROR):
                    parked, unspawned = self._adjudicate()

                self.assertEqual(parked.disposition, _LateDisposition.PARKED)
                unspawned.assert_not_called()
                self.assertEqual(self.github.edited_pr_bodies, [])
                self.assertTrue(self._pinned().get(_support.KEYS.awaiting))

    def test_a_failed_hold_records_its_failure(self) -> None:
        refused = patch.object(
            self.github, "edit_pr_body", side_effect=RuntimeError,
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            self._adjudicate()

        recorded = self._events_named(_support.EVENT_LATE_FAILURE)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(
            recorded[0].get("failure"), LateFailure.PLAN_PR_HOLD_FAILED,
        )
        self.assertEqual(recorded[0].get("stage"), STAGE_DECOMPOSING)

    def test_a_merge_mid_run_re_anchors_nothing(self) -> None:
        # The pull request is settled by a human; the commit under
        # adjudication is not, and stays the evidence every later step reads.
        merged = _MergedDuringRun(self.plan_pr, agent_reply(_support.SPLIT_REPLY))

        self._adjudicate(merged)

        self.assertEqual(self._pinned().get(_support.KEYS.candidate_sha), _support.CANDIDATE_SHA)
        self.assertEqual(self._pinned().get(_support.KEYS.base_sha), _support.BASE_SHA)
        self.assertEqual(self._pinned().get(_support.KEYS.source_sha), _support.CANDIDATE_SHA)


class SpawnPersistenceTest(LateCase, unittest.TestCase):
    """What is durable before the run, and what the run adds to it."""

    def test_the_run_is_recorded_before_the_spawn(self) -> None:
        recorder = SpawnSnapshot(self.github, agent_reply(_support.SPLIT_REPLY))

        self._adjudicate(recorder)

        self.assertEqual(len(recorder.snapshots), 1)
        recorded = recorder.snapshots[0]
        self.assertEqual(recorded.get(_support.KEYS.role), _support.ROLE_DECOMPOSER)
        self.assertEqual(
            recorded.get(_support.KEYS.agent), config.DECOMPOSE_AGENT_SPEC,
        )
        self.assertEqual(recorded.get(_support.KEYS.source_sha), _support.CANDIDATE_SHA)
        self.assertEqual(recorded.get(_support.KEYS.run_generation), 1)
        self.assertEqual(recorded.get(_support.KEYS.phase), LatePhase.ADJUDICATING)
        self.assertNotIn(_support.KEYS.verdict, recorded)
        # The identity is durable before the agent starts; the retry slot it
        # holds is not, so a run this tick then declines costs nothing.
        self.assertNotIn(_support.KEYS.retry_count, recorded)

    def test_a_grant_is_unspent_before_the_spawn(self) -> None:
        # The attempt a human bought is charged by the same gate the counters
        # are, so the pre-spawn write has to leave it as it found it too --
        # a run this tick then declines must not spend a continuation nobody
        # got an answer for.
        self.issue = _support.seed_late_issue(
            self.github, _support.late_generation(), retry_cap_continued=GRANTED,
        )
        recorder = SpawnSnapshot(self.github, agent_reply(_support.SPLIT_REPLY))

        self._adjudicate(recorder)

        self.assertEqual(recorder.snapshots[0].get(_support.KEYS.retry_grant), GRANTED)
        # The run that finished is what makes the spend durable.
        self.assertEqual(self._pinned().get(_support.KEYS.retry_grant), 0)

    def test_the_refund_covers_every_charged_field(self) -> None:
        # The set the pre-spawn write puts back has to mirror what the shared
        # gate writes, both roads through it: a field charged here and not
        # refunded there is spent by a run the tick goes on to decline.
        for grant in ({}, {_support.KEYS.retry_grant: GRANTED}):
            with self.subTest(grant=grant):
                state = self.github.read_pinned_state(self.issue)
                state.data.update(grant)
                before = dict(state.data)

                with patch.object(
                    config, "MAX_RETRIES_PER_DAY", BOUNDED_CAP,
                ):
                    _retry_budget._consume_retry_slot(
                        state, stage=STAGE_DECOMPOSING,
                    )

                self.assertLessEqual(
                    {
                        name for name, charge in state.data.items()
                        if before.get(name) != charge
                    },
                    set(_coordinator._ACCOUNTING_FIELDS),
                )

    def test_it_spends_the_shared_retry_and_usage(self) -> None:
        self._adjudicate(agent_reply(_support.SPLIT_REPLY))

        self.assertEqual(self._pinned().get(_support.KEYS.retry_count), 1)
        self.assertEqual(self._pinned().get(_support.KEYS.agent_runs), 1)

    def test_an_exhausted_budget_parks_unspawned(self) -> None:
        self.issue = _support.seed_late_issue(
            self.github,
            _support.late_generation(),
            retry_count=config.MAX_RETRIES_PER_DAY,
            retry_window_start=FUTURE_WINDOW,
        )

        outcome, spawn = self._adjudicate()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertTrue(self._pinned().get(_support.KEYS.awaiting))
        # The gate still precedes the pre-spawn write, so a run that never
        # happened leaves no record claiming it did.
        self.assertNotIn(_support.KEYS.source_sha, self._pinned())

    def test_a_missing_worktree_parks_unspawned(self) -> None:
        # The frozen commit is evidence this host either holds or does not;
        # re-running the developer is not a substitute for it.
        outcome, spawn = self._adjudicate(
            worktree=WorktreeSeed(exists=False),
        )

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertIn("not on this host", self.github.posted_comments[-1][1])

    def test_a_recorded_answer_is_not_paid_for_twice(self) -> None:
        self._adjudicate(agent_reply(_support.SPLIT_REPLY))

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(outcome.run.source_sha, _support.CANDIDATE_SHA)
        # Rebuilt from the record, so the caller acts on the same answer the
        # first tick got rather than on a second run's.
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.SPLIT)


class FrozenEvidenceTest(unittest.TestCase):
    """A generation is proved complete before anything acts on it."""

    def test_incomplete_evidence_parks_untouched(self) -> None:
        # Everything past this gate is derived from the record: the prompt
        # names both commits, the hold marks a PR in the generation's name,
        # and the verdict is reported under its identities. A missing one
        # produces a diff against nothing and a record two sinks refuse --
        # after the run has been paid for.
        cases = (
            ("no frozen base", _support.late_generation(base_sha="")),
            ("no frozen candidate", _support.late_generation(candidate_sha="")),
            ("no root issue", _support.late_generation(root_issue=0)),
            # A record about a different issue: positive, well-shaped, and
            # not this issue's. Acting on it would show the agent a prompt
            # naming two issues, mark a pull request in a foreign
            # generation's name, and file the verdict against the issue it
            # names rather than the one it ran on.
            (
                "another issue's record",
                _support.late_generation(current_issue=_support.LATE_ISSUE_NUMBER + 1),
            ),
        )
        for name, generation in cases:
            with self.subTest(case=name):
                github = FakeGitHubClient()
                issue = _support.seed_late_issue(
                    github, generation, pr_number=_support.PLAN_PR_NUMBER,
                    **{_support.KEY_PLAN_PATH: _support.PLAN_PATH},
                )
                _support.seed_plan_pr(github)

                self._assert_refused(github, issue)

    def test_an_unshowable_pair_parks_untouched(self) -> None:
        # Well-shaped is not the same as HERE. Both commits are proved in the
        # candidate's own checkout before the plan PR is held or an agent is
        # started: a candidate this host cannot peel is work made somewhere
        # else, and a base it does not hold makes the `git diff <base>...
        # <candidate>` the prompt names unresolvable -- so the run would be
        # paid for and its verdict would be an answer about nothing.
        cases = (
            ("no candidate object", WorktreeSeed(candidate_object=False)),
            ("no base object", WorktreeSeed(base_object=False)),
        )
        for name, seed in cases:
            with self.subTest(case=name):
                github = FakeGitHubClient()
                issue = _support.seed_late_issue(
                    github, _support.late_generation(), pr_number=_support.PLAN_PR_NUMBER,
                    **{_support.KEY_PLAN_PATH: _support.PLAN_PATH},
                )
                _support.seed_plan_pr(github)

                self._assert_refused(
                    github, issue, worktree=seed,
                    said="is not on this host",
                )

    def test_an_unshowable_pair_is_reported(self) -> None:
        github = FakeGitHubClient()
        issue = _support.seed_late_issue(github, _support.late_generation())

        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            adjudicate(
                github, issue, worktree=WorktreeSeed(candidate_object=False),
            )

        failures = [
            record for record in github.recorded_events
            if record.get("event") == _support.EVENT_LATE_FAILURE
        ]
        self.assertEqual(len(failures), 1)

    def _assert_refused(
        self, github, issue, worktree=None, said="cannot be adjudicated",
    ) -> None:
        """Nothing is spawned, and no pull request is touched."""
        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            outcome, spawn = adjudicate(github, issue, worktree=worktree)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertEqual(github.edited_pr_bodies, [])
        self.assertTrue(
            github.pinned_data(issue.number).get(_support.KEYS.awaiting),
        )
        self.assertIn(said, github.posted_comments[-1][1])


class MutationGuardTest(LateCase, unittest.TestCase):
    """The read-only promise is proved, not taken on the prompt's word.

    The late adjudicator reads the frozen candidate in the developer's own
    worktree, and the CLI it runs under can write there whatever the prompt
    says. A verdict from a run that moved the candidate is worth nothing next
    to the candidate.
    """

    def test_a_moved_head_refuses_the_verdict(self) -> None:
        self._refused(WorktreeSeed(head=_support.MERGED_SHA))

        self.assertIn(_support.CANDIDATE_SHA, self.github.posted_comments[-1][1])

    def test_an_unreadable_head_is_refused(self) -> None:
        # Proving nothing is the same answer as proving it moved: what a
        # later step would publish is unproven either way.
        self._refused(WorktreeSeed(head=""))

    def test_changes_left_behind_are_refused(self) -> None:
        self._refused(WorktreeSeed(dirty=("whatever.py",)))

    def test_an_unreadable_tree_is_refused(self) -> None:
        self._refused(WorktreeSeed(readable=False))

    def _refused(self, seed) -> None:
        """Run against `seed` and assert the verdict was not accepted."""
        outcome, _ = self._adjudicate(agent_reply(_support.SPLIT_REPLY), worktree=seed)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertNotIn(_support.KEYS.verdict, self._pinned())
        self.assertTrue(self._pinned().get(_support.KEYS.awaiting))
        self.assertIn("read-only", self.github.posted_comments[-1][1])


if __name__ == "__main__":
    unittest.main()
