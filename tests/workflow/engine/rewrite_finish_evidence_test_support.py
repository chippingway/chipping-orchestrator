# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite over settled evidence, driven whole through the finish every landing gets.

The evidence case (`rewrite_evidence_test_support`) put in review, with the
attempt an auto rebase pinned before git ran: the tested commit its anchor and
the head the case lands its replay. The finish is handed that landing as the
base refresh hands it -- the publication of this tick's own rebase, or a later
tick's recovery of a push it found standing -- so a case drives the debt and
the announcement, the evidence decision and the write behind it, the relabel,
and the retirement, through `rewrite_finish.finalizes` itself.

What a case reads back is what GitHub was left with (`rewrite_finish_readings`),
and what the pinned comment durably carried at the moment each relabel came
(`at_the_relabel`).
"""
from __future__ import annotations

from copy import copy
from dataclasses import replace

from orchestrator.git.base_sync.rewrite_handoffs import _PushOutcome
from orchestrator.workflow.engine import rewrite_finish as _finish
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    rewrite_evidence_test_support as rewrite_support,
    rewrite_finish_readings as _readings,
    verification_evidence_test_support as support,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.git_owners import seam_patch

# The round a reviewer already spent on the head the rewrite replaced, and
# one another road spends while a finish runs.
SPENT_ROUND = 3

_ANOTHER_ROUND = 4

# The label the issue wears when the base moves under its pull request.
REVIEWING = WorkflowLabel.IN_REVIEW

# What a recovery of a push an interrupted tick already landed hands the
# finish: the remote observed on the head, nothing sent.
FOUND = FinishRoad.RECOVERY


def attempt_record(anchor: str, head: str, pr_number: int, stage: WorkflowLabel) -> dict:
    """What an auto rebase of `anchor` pins before git runs, its replay onto `head` named, over a spent round."""
    return {
        _readings.KEY_PENDING_PUSH: anchor,
        _readings.KEY_REWRITE_PR: pr_number,
        _readings.KEY_REWRITE_STAGE: str(stage),
        _readings.KEY_REWRITE_SHA: head,
        _readings.KEY_REVIEW_ROUND: SPENT_ROUND,
    }


def spends_a_round(case) -> None:
    """Another road's spend of a review round on `case`'s issue, written over the comment as it stands.

    Raced past a finish's relabel, it refuses the retirement behind it, which
    is decided on the round.
    """
    spent = case.gh.read_pinned_state(case.issue)
    spent.set(_readings.KEY_REVIEW_ROUND, _ANOTHER_ROUND)
    case.gh.write_pinned_state(case.issue, spent)


class RewriteFinishCase(rewrite_support.RewriteEvidenceCase):
    """The evidence case in review, a rewrite of its tested commit about to land, and its finish."""

    def setUp(self) -> None:
        rewrite_support.RewriteEvidenceCase.setUp(self)
        # The evidence settled in `validating`, and the approval since moved
        # the issue on into review, where the base moved under it.
        self.issue.labels = [FakeLabel(str(REVIEWING))]
        self.durable: list[dict] = []
        self.gh.set_workflow_label = _DurableAtTheRelabel(self)

    def attempts(self, head: str) -> None:
        """Pin the attempt an auto rebase of the tested commit recorded, its replay onto `head` named.

        Onto the comment as it stands, and into the state the case holds, so
        a later whole-state write of that state keeps it.
        """
        self.rereads()
        for key, attempted in attempt_record(support.TESTED_SHA, head, support.PR_NUMBER, REVIEWING).items():
            self.state.set(key, attempted)
        self.gh.write_pinned_state(self.issue, self.state)

    def finishes(self, head: str, road: FinishRoad = FinishRoad.PUBLICATION) -> FinishOutcome:
        """Finish the landing onto `head` that `road` reached, over the issue as GitHub carries it now.

        A recovery observed the push standing and sent nothing; the
        publication sent it and saw it accepted.
        """
        outcome = _PushOutcome.OBSERVED if road is FOUND else _PushOutcome.ACCEPTED
        finish = LandedFinish(
            gh=self.gh,
            spec=_TEST_SPEC,
            issue=copy(self.issue),
            state=self.gh.read_pinned_state(self.issue),
            landed=replace(self._landing(head), outcome=outcome),
            label=self.gh.workflow_label(self.issue),
            road=road,
        )
        with self.seams(), seam_patch("_run_verify_commands", self._runs):
            return _finish.finalizes(finish)

    def at_the_relabel(self) -> tuple:
        """What the pinned comment durably carried at the one relabel a finish made (`readings.records`)."""
        self.assertEqual(len(self.durable), 1)
        return _readings.records(self.durable[0])

    def invalidated(self) -> tuple:
        """The history that indexes the settled evidence alone, invalidated."""
        return ((self.source.receipt, _readings.INVALIDATED),)

    def rereads(self) -> None:
        """Take up the pinned comment as GitHub carries it now, as another road writing it would first."""
        self.state = self.gh.read_pinned_state(self.issue)


class _DurableAtTheRelabel:
    """A relabel that remembers what the pinned comment durably said when it came.

    What a finish has made durable by then is what a process lost in the
    relabel comes back to, so it is the record the route is held to.
    """

    def __init__(self, case: RewriteFinishCase) -> None:
        self._case = case
        self._relabel = case.gh.set_workflow_label

    def __call__(self, issue, label) -> None:
        """Read the durable record, then apply the label."""
        self._case.durable.append(_readings.pinned(self._case))
        self._relabel(issue, label)
