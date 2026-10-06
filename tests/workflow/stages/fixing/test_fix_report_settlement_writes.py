# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round's report whose settlement did not land as sent, and the ticks that finish it.

A round that answers its feedback with a report records it, binds it, posts it,
and settles it in one guarded commit that spends the round, advances the reader
the round consumed, and raises the mark the hand-back is taken on. Where GitHub
takes that commit and its answer never comes back, or another road moves the
comment under its edit, the tick ends right there with the report on the pull
request and nothing relabelled. The dispatcher's reconciliation ahead of the
next handler settles whatever is still owed -- finding the report by its
receipt rather than posting it again -- and the fixing handler hands the round
back off the mark: one report, one round, the reader advanced once, and no
developer run.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import report_records as _records
from tests.workflow import fix_reports as world
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING

ISSUE = 1_796

PR = 17_960

RUN_AGENT = "run_agent"

REVIEW_ROUND = "review_round"

PR_LAST_COMMENT_ID = "pr_last_comment_id"

SETTLED_ROUND = _records.SETTLED_ROUND

# The record a report owed and not yet settled is read back as.
PENDING = "pending"

# Verification evidence another road settles while the settlement is out.
_EVIDENCE_FIELD = "verification_evidence_current"

_EVIDENCE = MappingProxyType({_EVIDENCE_FIELD: {"revision": 3}})


class UnlandedSettlementTest(unittest.TestCase, world._FixReportMixin):
    """The round's post or settlement unconfirmed or refused, and the ticks that finish it once."""

    def test_a_lost_post_finishes_once(self) -> None:
        # GitHub took the report's post and its answer never came back, so the
        # tick ends with the transaction owed and nothing spent. The
        # reconciliation finds the post by its receipt and settles it, and
        # the handler hands the round back.
        answered = self._reported_round(_LostPost)

        self.assertEqual(
            (
                self.records()[PENDING].report_revision,
                self.pinned()[REVIEW_ROUND],
                self.github.label_history[-1],
            ),
            (self.revision, 0, (ISSUE, LABEL_FIXING)),
        )
        self._assert_finished_next(answered)

    def test_an_unconfirmed_settlement_finishes_once(self) -> None:
        # The settlement landed and its answer was lost: the round is spent,
        # the reader advanced and the mark raised, and the label never moved.
        # The reconciliation finds nothing owed, and the handler hands the
        # round back off the mark without a run or a second report.
        answered = self._reported_round(_LostSettlement)

        self.assertEqual(
            (
                self.records()[PENDING],
                self.pinned()[REVIEW_ROUND],
                self.pinned()[SETTLED_ROUND],
                self.github.label_history[-1],
            ),
            (None, 1, True, (ISSUE, LABEL_FIXING)),
        )
        self._assert_finished_next(answered)

    def test_a_moved_comment_finishes_once(self) -> None:
        # Another road settles evidence under the settlement's edit, so the
        # edit is refused: the report is on the pull request and nothing is
        # spent. The reconciliation settles it beside that evidence, finding
        # the report by its receipt, and the handler hands the round back.
        answered = self._reported_round(_MovedUnderTheSettlement)

        self.assertEqual(
            (
                self.records()[PENDING].report_revision,
                self.pinned()[REVIEW_ROUND],
                self.pinned().get(_EVIDENCE_FIELD),
                self.github.label_history[-1],
            ),
            (self.revision, 0, _EVIDENCE[_EVIDENCE_FIELD], (ISSUE, LABEL_FIXING)),
        )
        self._assert_finished_next(answered)
        self.assertEqual(self.pinned().get(_EVIDENCE_FIELD), _EVIDENCE[_EVIDENCE_FIELD])

    def _reported_round(self, during) -> int:
        """A round that reports, its publication met by `during`; the reply it answered.

        The revision the round's report was recorded at is kept as `revision`,
        which is the one every later tick has to settle it at.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        with during(self):
            self.parked_resume(world.reported(), committed=False)
        self.assertEqual(len(self.published_reports()), 1)
        records = self.records()
        self.revision = (records[PENDING] or records["current"]).report_revision
        return max(reply.id for reply in self.issue.comments)

    def _assert_finished_next(self, answered: int) -> None:
        """The next tick finishes the round: one report at the round's revision, one round, and no run."""
        self.reconcile()
        finished = self.parked_resume(world.reported(), committed=False)

        finished[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (
                len(self.published_reports()),
                self.records()[PENDING],
                self.records()["current"].report_revision,
                self.pinned()[REVIEW_ROUND],
                self.pinned().get(PR_LAST_COMMENT_ID),
                self.pinned().get(SETTLED_ROUND),
                self.github.label_history[-1],
            ),
            (1, None, self.revision, 1, answered, None, (ISSUE, LABEL_VALIDATING)),
        )


class _LostPost:
    """GitHub landing the report's post and losing its answer, for as long as it stands."""

    def __init__(self, case) -> None:
        self._lost = case.github.report_failures.lost

    def __enter__(self) -> None:
        self._lost.add(PR)

    def __exit__(self, *raised) -> None:
        self._lost.discard(PR)


class _OnTheSettlement:
    """The strict pinned edits a tick makes, with something done to the one that settles a report.

    Told apart by the handoff it writes: only a settlement writes one, and the
    comment already carries the opening report's.
    """

    def __init__(self, case) -> None:
        self.case = case
        self.lost = case.github.pinned_failures.lost
        self._edits = case.github.edit_pinned_state
        self._patched = patch.object(case.github, "edit_pinned_state", self)

    def __call__(self, issue, state, **options):
        """Make the edit, met as this case meets it where it writes a new handoff."""
        standing = self.case.pinned().get(_records.REPORT_HANDOFF)
        if state.get(_records.REPORT_HANDOFF) == standing:
            return self._edits(issue, state, **options)
        self.meets()
        answered = self._edits(issue, state, **options)
        self.lost.discard(ISSUE)
        return answered

    def __enter__(self) -> None:
        self._patched.start()

    def __exit__(self, *raised) -> None:
        self._patched.stop()

    def meets(self) -> None:
        """What happens to the comment as the settlement's edit is sent."""


class _LostSettlement(_OnTheSettlement):
    """The settlement landing, and its answer lost."""

    def meets(self) -> None:
        """Lose the answer to the edit about to be sent; the strict edit reports that rather than raising."""
        self.lost.add(ISSUE)


class _MovedUnderTheSettlement(_OnTheSettlement):
    """Another road writing evidence over the comment once the settlement has read it."""

    def meets(self) -> None:
        """Have another road write its evidence, which the edit then finds moved."""
        commit_support.another_road(self.case.github, self.case.issue, **_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
