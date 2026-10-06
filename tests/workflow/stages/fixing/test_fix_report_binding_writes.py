# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round's recovered report whose binding or post did not land, and the tick it ends.

A round whose process ended between its push and the report's binding leaves a
delivery the next fixing tick re-proves and binds, ahead of any scan. That
binding is a guarded commit: a comment another road moved under it refuses it,
and an edit GitHub took and never confirmed leaves nobody able to say what the
comment carries. Either way the tick ends right there and says nothing -- no
notice, no park, no write -- so what the other road wrote stands, and the round
is finished on a later tick from the same record, with no developer run and no
second report. A post GitHub took and never answered while another road wrote
the comment ends it the same way: the comment is asked again behind the post,
and the recovery writes nothing back over what that road wrote.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from tests.workflow import fix_report_crashes as crashes, fix_reports as world
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING

ISSUE = 1_795

PR = 17_950

RUN_AGENT = "run_agent"

# The request a published report goes out as, and the lifetime run ledger a
# launch is charged to.
POST = "publish_developer_report"

RUNS_USED = "agent_runs_used"

REVIEW_ROUND = "review_round"

# Verification evidence another road settles while the binding is out.
_EVIDENCE_FIELD = "verification_evidence_current"

_EVIDENCE = MappingProxyType({_EVIDENCE_FIELD: {"revision": 3}})


class UnlandedBindingTest(unittest.TestCase, world._FixReportMixin):
    """The recovered binding refused or left unconfirmed, and what the tick leaves."""

    def test_an_unconfirmed_binding_ends_the_tick(self) -> None:
        # GitHub took the binding and its answer never came back, and evidence
        # lands right behind it. The tick says and writes nothing more; the
        # reconciliation ahead of the next handler publishes the transaction
        # that binding left, and that handler hands the round back -- one
        # report, at the run's own revision, with no developer run.
        said = self._recorded_unbound()
        self.github.pinned_failures.lost.add(ISSUE)
        with commit_support.behind(self.github, self.issue, commit_support.EDIT, **_EVIDENCE):
            recovered = self.parked_resume(world.reported(), committed=False)
        self.github.pinned_failures.lost.discard(ISSUE)

        self._assert_silent(recovered, said)
        self.assertIsNotNone(self.records()["pending"])
        self._assert_finished_next()

    def test_a_moved_comment_ends_the_tick(self) -> None:
        # Another road writes over the comment once the binding has read it,
        # so its edit is refused. The tick says and writes nothing more, and
        # the next one binds the same delivery afresh and finishes the round.
        said = self._recorded_unbound()
        with commit_support.under_the_edit(self.github, self.issue, **_EVIDENCE):
            recovered = self.parked_resume(world.reported(), committed=False)

        self._assert_silent(recovered, said)
        self.assertIsNotNone(self.records()["delivered"])
        self._assert_finished_next()

    def test_a_lost_post_beside_others_ends_the_tick(self) -> None:
        # The binding lands, the post goes out and its answer is lost, and
        # evidence lands behind it. The tick ends without writing its state
        # back over that evidence, having charged nothing; the reconciliation
        # ahead of the next handler finds the report by its receipt and
        # settles it, and that handler hands the round back.
        said = self._recorded_unbound()
        charged = self.pinned().get(RUNS_USED)
        self.github.report_failures.lost.add(PR)
        with commit_support.behind(self.github, self.issue, POST, **_EVIDENCE):
            recovered = self.parked_resume(world.reported(), committed=False)
        self.github.report_failures.lost.discard(PR)

        recovered[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (
                len(self.issue.comments),
                len(self.published_reports()),
                self.records()["pending"].report_revision,
                self.pinned()[REVIEW_ROUND],
                self.pinned().get(_EVIDENCE_FIELD),
                self.github.label_history[-1],
            ),
            (said, 1, self.revision, 0, _EVIDENCE[_EVIDENCE_FIELD], (ISSUE, LABEL_FIXING)),
        )
        self._assert_finished_next()
        self.assertEqual(self.pinned().get(RUNS_USED), charged)

    def _recorded_unbound(self) -> int:
        """A round whose process ended between its push and its binding; the comments said so far.

        The revision the round's report was recorded at is kept as `revision`,
        which is the one any later tick has to publish it at.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        with crashes.dying_before_the_binding():
            self.parked_resume(world.reported(), committed=False)
        self.revision = self.records()["delivered"].report_revision
        return len(self.issue.comments)

    def _assert_silent(self, mocks, said: int) -> None:
        """Nobody run, nothing said or published, the round unspent, and the other road's evidence kept."""
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (
                len(self.issue.comments),
                len(self.published_reports()),
                self.pinned()[REVIEW_ROUND],
                self.pinned().get(_EVIDENCE_FIELD),
                self.github.label_history[-1],
            ),
            (said, 0, 0, _EVIDENCE[_EVIDENCE_FIELD], (ISSUE, LABEL_FIXING)),
        )

    def _assert_finished_next(self) -> None:
        """The next tick finishes the round off the same record, the evidence still kept."""
        self.reconcile()
        finished = self.parked_resume(world.reported(), committed=False)

        finished[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (
                len(self.published_reports()),
                self.records()["current"].report_revision,
                self.pinned()[REVIEW_ROUND],
                self.pinned().get(_EVIDENCE_FIELD),
                self.github.label_history[-1],
            ),
            (1, self.revision, 1, _EVIDENCE[_EVIDENCE_FIELD], (ISSUE, LABEL_VALIDATING)),
        )


if __name__ == "__main__":
    unittest.main()
