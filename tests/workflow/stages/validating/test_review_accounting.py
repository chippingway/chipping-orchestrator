# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reviewer round's rereads and writes make of the usage its own run accounted, and a hand edit beside it.

The round's reviewer is accounted as it returns: the accounting checkpoint
lands the run on the comment and lays the totals onto the round's state as the
comment's. Every reading the round takes afterwards may be measured from one
taken before that -- the reading its subject was resolved over -- so a total
the state and the comment both moved since is no two moves to add up: the
comment's is the newer, whatever an operator's hand edit of the comment left
there. A hand edit is the one writer besides the round itself a writer claim
leaves, so it is what moves the comment under the round here. And the return's
own write owns no total, so it lands over whatever the comment carries then,
counting the run neither again nor back.
"""
from __future__ import annotations

import itertools
import unittest
from types import MappingProxyType

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    invocations as _invocations,
    report_records as _records,
    usage_checkpoint as _usage_checkpoint,
)
from orchestrator.workflow.stages.validating import review_comment as _review_comment, review_writes as _review_writes
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import accounted

ISSUE = 1_821

RUNS = "issue_agent_runs"

TOKENS = "issue_total_tokens"

# What the comment carried when the round's subject was resolved over it.
_RESOLVED = MappingProxyType({
    _records.CURRENT_REPORT: {"revision": 1},
    RUNS: 3,
    TOKENS: 300,
    "review_round": 1,
})

# The runs the comment counts once the round's own reviewer is accounted.
_ACCOUNTED_RUNS = _RESOLVED[RUNS] + 1

# The tokens the round's own reviewer reported, and the session it ran as.
_REVIEWER_TOKENS = 20
_REVIEWER_SESSION = "rev-sess"
_SESSION = "last_review_session_id"

# What an operator's hand edit left behind the reviewer's accounting -- the
# totals corrected to count a run the orchestrator never saw, or a total
# spelled as no writer spells it -- and the totals the round's state and the
# comment carry behind a reread; and the records beside it, standing or the
# report record the same edit rewrote.
_CORRECTED = MappingProxyType({RUNS: 5, TOKENS: 370})
_MISSPELLED = MappingProxyType({RUNS: 5, TOKENS: "lots"})
_BESIDE = (
    ("corrected totals", _CORRECTED, ((5, 370), (5, 370))),
    ("a misspelled total", _MISSPELLED, ((5, "lots"), (5, "lots"))),
)
_RECORDS = (
    ("over records that stand", MappingProxyType({}), True),
    ("over a rewritten report record", MappingProxyType({_records.CURRENT_REPORT: {"revision": 2}}), False),
)


class ReviewerAccountingTest(unittest.TestCase):
    """The reviewer's own accounting, and a hand edit beside it, each kept once through the round's merges."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE)
        self.github.add_issue(self.issue)

    def test_a_reread_carries_the_comments_totals(self) -> None:
        # Measured from the reading the subject was resolved over, both the
        # state and the comment moved the totals since -- the state by the
        # reviewer's own accounting, the comment by that and whatever a hand
        # edit left behind it. The reread carries the comment's, never the
        # state's added to them, whether the records stood or moved.
        for beside, records in itertools.product(_BESIDE, _RECORDS):
            with self.subTest(beside[0], records=records[0]):
                self.setUp()
                state, resolved_over = self._accounted_round()
                self._hand_edit({**beside[1], **records[1]})

                reread = _review_comment._records_stand(
                    self.github, self.issue, state, resolved_over, persisted=True,
                )

                self.assertIs(reread.stood, records[2])
                self.assertEqual(self._carried(state), beside[2])

    def test_the_return_keeps_the_comments_totals(self) -> None:
        # An operator corrects the totals by hand behind the reread: the
        # return's write lands over the correction, its own records beside it,
        # the reviewer's run counted neither again nor back, and the state then
        # reads as the comment does.
        state, resolved_over = self._accounted_round()
        _review_comment._records_stand(self.github, self.issue, state, resolved_over, persisted=True)
        state.set(_SESSION, _REVIEWER_SESSION)
        self._hand_edit(_CORRECTED)

        landed = _review_writes.lands(self.github, self.issue, state, _review_writes.RETURN)

        pinned = self.github.pinned_data(ISSUE)
        self.assertEqual((landed, pinned[_SESSION]), (True, _REVIEWER_SESSION))
        self.assertEqual(_totals(pinned), _totals(_CORRECTED))
        self.assertEqual(state.state_data, pinned)

    def _accounted_round(self) -> tuple[PinnedState, dict]:
        """The round's state once its reviewer is accounted, and the reading its subject was resolved over."""
        self.github.seed_state(self.issue, **_RESOLVED)
        state = self.github.read_pinned_state(self.issue)
        resolved_over = dict(state.state_data)
        returned = AgentResult(
            session_id=_REVIEWER_SESSION,
            last_message="VERDICT: APPROVED",
            exit_code=0,
            timed_out=False,
            stdout="",
            stderr="",
            usage=UsageMetrics(backend="codex", input_tokens=_REVIEWER_TOKENS, cost_source="no-usage"),
            invocation=_invocations.minted(state, ISSUE),
        )
        outcome = _usage_checkpoint.checkpoint(self.github, self.issue, state, returned)
        self.assertTrue(outcome.settled)
        self.assertEqual(accounted(state.state_data), (_ACCOUNTED_RUNS, 1))
        return state, resolved_over

    def _carried(self, state: PinnedState) -> tuple:
        """The totals `state` carries, and the ones the comment does."""
        return _totals(state.state_data), _totals(self.github.pinned_data(ISSUE))

    def _hand_edit(self, fields) -> None:
        """An operator's hand edit of `fields` over the comment as it stands, made with the orchestrator's own login."""
        other = self.github.read_pinned_state(self.issue)
        other.state_data.update(fields)
        self.github.write_pinned_state(self.issue, other)


def _totals(record) -> tuple:
    """The run and token totals `record` carries."""
    return record.get(RUNS), record.get(TOKENS)


if __name__ == "__main__":
    unittest.main()
