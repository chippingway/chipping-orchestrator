# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records only `validating` answers, and the tick that hands them back.

A `validating` approval retires its own returned verdict ahead of the relabel
that brings the issue here, and drops its own squash handoff
(`late_collapse_handoff_sha`) in a write BEHIND that relabel. So either one
still standing when a documenting tick runs is that write having failed, or
another road's record put down while the relabel ran -- and nothing here can
tell which, or act on either.

So the tick sends the issue back before anything else runs, and writes
nothing: the recovery ahead of the reviewer answers a handoff over the head it
names, and a waiting verdict holds the label for the road that finishes it.
Ended here instead, another road's handoff would lose the check its recovery
makes; and a record carried past this stage would answer a later return to
`validating` by relabelling the unchanged head straight back, so the review
that return asks for would never run.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.engine import review_subjects as _review_subjects
from orchestrator.workflow.late_split import handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.support.fakes import DEFAULT_PR_HEAD_SHA
from tests.workflow.fixtures import _agent
from tests.workflow.stages.documenting.documenting_scenario_test_support import (
    _ParkedDocumentingFixture,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    AWAITING_HUMAN,
    PARK_AGENT_QUESTION,
    RUN_AGENT,
    VALIDATING,
)

HANDOFF_KEY = _late_handoffs.LATE_COLLAPSE_HANDOFF

LABEL_DOCUMENTING = "workflow:documenting"

# The requirements revision the later round was handed.
REQUIREMENTS_REVISION = "abababab" * 8

# A later round's change request, of the head the pull request stands on.
_LATER_VERDICT = _verdicts.ReturnedVerdict(
    1,
    _verdicts.CHANGES_REQUESTED,
    _review_subjects.ReviewSubject(
        _ParkedDocumentingFixture.pr_number, DEFAULT_PR_HEAD_SHA, REQUIREMENTS_REVISION,
    ).recorded(),
    "A later round's feedback.",
).recorded()

# What `validating` can leave standing here, by the key it stands under.
_OWED = MappingProxyType({
    HANDOFF_KEY: DEFAULT_PR_HEAD_SHA,
    _verdicts.RETURNED_VERDICT: _LATER_VERDICT,
})

# The seams a documenting tick reaches past the hand-back: a push that lands
# and a branch in sync with its remote, so a tick that hands nothing back runs
# exactly as it would without one.
_DOCS_TICK = MappingProxyType({
    "push_branch": True,
    "head_shas": [],
    "branch_ahead_behind": (0, 0),
})


class HandBackTest(
    unittest.TestCase,
    _ParkedDocumentingFixture,
):
    """What a documenting tick does with a record `validating` still owes an answer."""

    def test_what_validating_owes_goes_back_to_it(self) -> None:
        for key, record in _OWED.items():
            with self.subTest(key):
                gh, issue = self._seeded(**{AWAITING_HUMAN: False, key: record})

                mocks = self._docs_tick(gh, issue)

                mocks[RUN_AGENT].assert_not_called()
                self.assertEqual(
                    (gh.label_history, gh.pinned_data(self.issue_number).get(key), gh.write_state_calls),
                    ([(self.issue_number, VALIDATING)], record, 0),
                )

    def test_an_ordinary_tick_moves_nothing(self) -> None:
        # The cost is one look at the pinned comment: an issue whose approval
        # retired its own records reaches this stage exactly as it always
        # did, and a parked tick still writes nothing and stays here.
        gh, issue = self._seeded(park_reason=PARK_AGENT_QUESTION)

        self._docs_tick(gh, issue)

        self.assertEqual((gh.write_state_calls, gh.label_history), (0, []))

    def test_the_recovery_answers_the_handoff(self) -> None:
        # Handed back, the record reaches the recovery ahead of the reviewer,
        # which spends it only under an approval still covering the head it
        # names. This comment records none, so the record is dropped and the
        # review runs, rather than the label going straight back here.
        gh, issue = self._seeded(
            review_round=0, **{AWAITING_HUMAN: False, HANDOFF_KEY: DEFAULT_PR_HEAD_SHA},
        )
        self._docs_tick(gh, issue)

        mocks = self._run_validating(gh, issue, run_agent=_agent())

        mocks[RUN_AGENT].assert_called_once()
        self.assertNotIn((self.issue_number, LABEL_DOCUMENTING), gh.label_history)
        self.assertNotIn(HANDOFF_KEY, gh.pinned_data(self.issue_number))

    def _docs_tick(self, gh, issue):
        """One documenting tick over the seeded comment."""
        return self._run_documenting(gh, issue, run_agent=_agent(), **_DOCS_TICK)


if __name__ == "__main__":
    unittest.main()
