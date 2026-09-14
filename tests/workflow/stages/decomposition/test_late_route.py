# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which of the two questions a `decomposing` tick is about.

The label is shared. An issue that has still to be decomposed reaches the
initial decomposer, and one whose committed implementation was measured past
the ceiling reaches the late coordinator instead -- and nothing below that
route runs for it, because the candidate it is about lives in the developer's
own worktree rather than in the scratch checkout the initial decomposer needs.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.config import settings as config
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_coordinator as _late_coordinator,
    late_hold as _late_hold,
    models as _models,
    run as _run,
)
from orchestrator.workflow.stages.decomposition.late_result_models import (
    _LateAdjudicationRun,
    _LateDisposition,
    _LateRun,
)
from orchestrator.workflow.stages.implementing import handler as _implementing
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_IMPLEMENTING
from tests.workflow.stages.decomposition import (
    late_test_support as late_support,
)
from tests.workflow.stages.decomposition.late_test_support import (
    LATE_ISSUE_NUMBER,
    seed_late_issue,
    seeded_late_issue,
)

_ADJUDICATE = "_adjudicate_late_generation"

_PREPARE_RUN = "_prepare_decomposer_run"

_HANDLE_IMPLEMENTING = "_handle_implementing"

_KEY_CANDIDATE_SHA = "late_candidate_sha"

_KEY_ADDITIONS = "late_additions"

_SET_WORKFLOW_LABEL = "set_workflow_label"

_GET_ISSUE = "get_issue"

_DECOMPOSE = "DECOMPOSE"

_EDIT_PR_BODY = "edit_pr_body"

_KEY_PR_NUMBER = "pr_number"

_KEY_PARK_REASON = "park_reason"

_PARK_HOLD_FAILED = "late_plan_pr_hold_failed"

_WORKFLOW_LOG = "orchestrator.workflow"

_ERROR = "ERROR"


def _stale_label_client(case, github):
    """Make this client behave the way the real one does around a relabel.

    PyGithub's `set_labels` writes the label and leaves the object it was
    called on exactly as it was, so an issue relabelled mid-tick goes on
    reporting the label it arrived with until something fetches it again. The
    fake mutates in place instead, which hides the whole failure -- so the
    write is neutered here and `get_issue` answers with a distinct object
    carrying the label the write made durable.
    """
    refreshed = make_issue(LATE_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    patchers = (
        patch.object(github, _SET_WORKFLOW_LABEL, MagicMock()),
        patch.object(github, _GET_ISSUE, MagicMock(return_value=refreshed)),
    )
    for patcher in patchers:
        case.addCleanup(patcher.stop)
        patcher.start()
    return refreshed


def _decided() -> _LateAdjudicationRun:
    """One finished adjudication, as the coordinator reports it."""
    return _LateAdjudicationRun(
        disposition=_LateDisposition.DECIDED,
        generation=LateGeneration(),
        run=_LateRun(),
    )


class _RouteCase:
    """One `decomposing` tick, and the issue shapes a case drives it with."""

    def _tick(self, github, issue) -> None:
        """One `decomposing` tick over the issue a case seeded."""
        _run._handle_decomposing(github, _TEST_SPEC, issue)

    def _settled(self):
        """An issue whose revision came back under the ceiling."""
        seeded = seeded_late_issue()
        github = seeded[0]
        github.seed_state(
            LATE_ISSUE_NUMBER,
            **late_support.generation_state(
                late_support.late_generation(
                    additions=late_support.UNDERSIZED_ADDITIONS,
                ),
            ),
        )
        return seeded


class LateRouteTest(_RouteCase, unittest.TestCase):
    """A live generation owns the whole tick; nothing else notices it."""

    def test_a_live_generation_is_adjudicated(self) -> None:
        github, issue = seeded_late_issue()
        adjudicated = MagicMock(return_value=_decided())
        prepared = MagicMock()

        with patch.object(_late_coordinator, _ADJUDICATE, adjudicated), patch.object(_run, _PREPARE_RUN, prepared):
            self._tick(github, issue)

        adjudicated.assert_called_once()
        self.assertIs(adjudicated.call_args.args[2], issue)
        prepared.assert_not_called()

    def test_a_settled_candidate_goes_to_implementing(self) -> None:
        # A revision a human's guidance bought came back under the ceiling, so
        # the size question is ANSWERED and the label names no work left. The
        # initial decomposer would re-plan an implementation that is already
        # written; publication is what it is owed. The real coordinator runs
        # here, because "not an adjudication" is exactly the answer this route
        # has to tell apart from "never entered the gate".
        github, issue = self._settled()
        prepared = MagicMock()
        handled = MagicMock()

        with patch.object(_run, _PREPARE_RUN, prepared), patch.object(_implementing, _HANDLE_IMPLEMENTING, handled):
            self._tick(github, issue)

        prepared.assert_not_called()
        handled.assert_called_once()
        self.assertIn(
            (LATE_ISSUE_NUMBER, LABEL_IMPLEMENTING), github.label_history,
        )

    def test_a_settled_candidate_keeps_its_record(self) -> None:
        # The record is what makes the handoff recoverable, so it survives it:
        # it is the only thing saying this issue's size question was asked and
        # answered, and dropping it here would leave a `decomposing` issue the
        # initial decomposer could not tell from one that never entered the
        # gate. Retiring it is the implementing gate's own step, taken ahead of
        # the push it licenses.
        github, issue = self._settled()

        with patch.object(_implementing, _HANDLE_IMPLEMENTING):
            self._tick(github, issue)

        pinned = github.pinned_data(LATE_ISSUE_NUMBER)
        self.assertEqual(
            pinned[_KEY_CANDIDATE_SHA], late_support.CANDIDATE_SHA,
        )
        self.assertEqual(
            pinned[_KEY_ADDITIONS], late_support.UNDERSIZED_ADDITIONS,
        )

    def test_a_refused_label_repeats_the_handoff(self) -> None:
        # The crash boundary: the label write is what makes another handler
        # read the issue, and one that never lands leaves the tick where it
        # started. Because the record is still there, the next tick reaches
        # the same handback rather than the decomposer.
        github, issue = self._settled()
        refused = MagicMock(side_effect=RuntimeError("label write refused"))

        with patch.object(github, _SET_WORKFLOW_LABEL, refused), self.assertRaises(RuntimeError):
            self._tick(github, issue)

        prepared = MagicMock()
        handled = MagicMock()
        with patch.object(_run, _PREPARE_RUN, prepared), patch.object(_implementing, _HANDLE_IMPLEMENTING, handled):
            self._tick(github, issue)

        prepared.assert_not_called()
        handled.assert_called_once()

    def test_a_restarted_cycle_is_decomposed(self) -> None:
        # A restart's fresh cycle carries an identity and no candidate at all,
        # and it IS waiting to be decomposed -- which is why the handback is
        # read off the measurement rather than off the record being present.
        github = FakeGitHubClient()
        issue = seed_late_issue(
            github,
            LateGeneration(
                cycle_id=late_support.CYCLE_ID,
                root_issue=late_support.ROOT_ISSUE,
            ),
        )
        prepared = MagicMock(
            return_value=_models._DecomposerRunPlan(agent_result=None),
        )

        with patch.object(_run, _PREPARE_RUN, prepared):
            self._tick(github, issue)

        prepared.assert_called_once()

    def test_no_generation_falls_through(self) -> None:
        # The coordinator is asked of every tick, because the reconciliations
        # it opens with are owed by exactly the records the gates below it
        # route past. On an issue that never entered the size gate it answers
        # immediately, and the initial decomposition proceeds -- so this one
        # runs the real coordinator rather than a stand-in for it.
        github = FakeGitHubClient()
        issue = seed_late_issue(github, LateGeneration())
        prepared = MagicMock(
            return_value=_models._DecomposerRunPlan(agent_result=None),
        )

        with patch.object(_run, _PREPARE_RUN, prepared):
            self._tick(github, issue)

        prepared.assert_called_once()



class LateSettledHandoffTest(unittest.TestCase):
    """What the settled handback owes the pull requests before it hands on.

    A revision that came back under the ceiling leaves this label the way an
    accepted verdict does, and owes the same two reconciliations: this
    generation put a "do not merge" notice on the plan pull request and holds
    the only copy of the description it displaced, and `pr_number` still names
    whichever change the issue carried into the gate. The retirement one step
    later reads a record about SIZE and knows nothing about either, so what is
    not settled here is settled by nobody.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.generation = late_support.late_generation(
            additions=late_support.UNDERSIZED_ADDITIONS,
            plan_pr_number=late_support.PLAN_PR_NUMBER,
            plan_pr_body=late_support.PLAN_PR_BODY,
        )
        self.issue = late_support.seed_late_issue(
            self.github, self.generation,
            pr_number=late_support.PLAN_PR_NUMBER,
        )
        self.plan_pr = late_support.seed_plan_pr(
            self.github, body=_late_hold._hold_body(self.generation),
        )

    def test_the_hold_comes_off_the_plan_pr(self) -> None:
        # Left standing, the notice is a "do not merge" on a change a human
        # can still merge -- and the only copy of the description it displaced
        # goes with the record the retirement drops a moment later, so nothing
        # is left that could put it back.
        self._handed_on()

        self.assertEqual(self.plan_pr.body, late_support.PLAN_PR_BODY)
        self.assertNotIn(
            late_support.HOLD_MARKER_PREFIX, self.plan_pr.body,
        )

    def test_a_settled_plan_pr_is_dropped(self) -> None:
        # A plan pull request a human merged while the revision ran carries
        # none of this candidate, and carried into `implementing` it ends the
        # issue as `done` on a design -- with the revised implementation never
        # published.
        self.plan_pr.merged = True

        self._handed_on()

        self.assertIsNone(
            self.github.pinned_data(LATE_ISSUE_NUMBER).get(_KEY_PR_NUMBER),
        )

    def test_a_refused_release_hands_nothing_on(self) -> None:
        # The release is asked before anything else moves, so a refusal
        # leaves the generation exactly as it arrived: still settled, still
        # under `decomposing`, and reaching the same handback next tick.
        handled = MagicMock()
        refused = patch.object(
            self.github, _EDIT_PR_BODY, side_effect=RuntimeError,
        )

        with (
            refused,
            patch.object(_implementing, _HANDLE_IMPLEMENTING, handled),
            self.assertLogs(_WORKFLOW_LOG, level=_ERROR),
        ):
            _run._handle_decomposing(self.github, _TEST_SPEC, self.issue)

        handled.assert_not_called()
        self.assertEqual(self.github.label_history, [])
        pinned = self.github.pinned_data(LATE_ISSUE_NUMBER)
        self.assertEqual(pinned.get(_KEY_PARK_REASON), _PARK_HOLD_FAILED)
        self.assertEqual(
            pinned[_KEY_CANDIDATE_SHA], late_support.CANDIDATE_SHA,
        )

    def _handed_on(self) -> None:
        """One `decomposing` tick, with the implementing handler stubbed."""
        with patch.object(_implementing, _HANDLE_IMPLEMENTING, MagicMock()):
            _run._handle_decomposing(self.github, _TEST_SPEC, self.issue)


class LateHandoffTest(_RouteCase, unittest.TestCase):
    """The relabel a handoff makes, and the read it owes the handler."""

    def test_the_handoff_reads_the_issue_again(self) -> None:
        # A label write does not refresh the object it was made against, so
        # the one this tick holds still reports `decomposing`. The handler it
        # falls into ends in a relabel of its own, and the transition guard
        # reads that against whatever the issue says it currently is: handed
        # the stale object it sees an edge the graph does not declare, and
        # under `enforce` it raises -- after the branch is pushed and the pull
        # request is open.
        github, issue = self._settled()
        handled = MagicMock()
        refreshed = _stale_label_client(self, github)

        with patch.object(_implementing, _HANDLE_IMPLEMENTING, handled):
            self._tick(github, issue)

        self.assertIs(handled.call_args.args[2], refreshed)

    def test_the_disabled_route_reads_it_again(self) -> None:
        # The kill-switch handoff is the same relabel and the same stale
        # object, so it is refetched for the same reason.
        github = FakeGitHubClient()
        issue = seed_late_issue(github, LateGeneration())
        handled = MagicMock()
        refreshed = _stale_label_client(self, github)

        with patch.object(config, _DECOMPOSE, False), patch.object(_implementing, _HANDLE_IMPLEMENTING, handled):
            self._tick(github, issue)

        self.assertIs(handled.call_args.args[2], refreshed)

    def test_an_unreadable_refetch_stops_the_tick(self) -> None:
        # The label is already durable, so the next tick dispatches this issue
        # on a freshly read object. Running the handler on the stale one is
        # the single thing that must not happen.
        github, issue = self._settled()
        handled = MagicMock()

        with (
            patch.object(github, _GET_ISSUE, side_effect=RuntimeError("gone")),
            patch.object(_implementing, _HANDLE_IMPLEMENTING, handled),
        ):
            self._tick(github, issue)

        handled.assert_not_called()


if __name__ == "__main__":
    unittest.main()
