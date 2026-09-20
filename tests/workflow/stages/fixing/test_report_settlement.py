# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can finish on `REPORT: READY` exactly as an initial implementation can --
and when it does, the round owes a publication this tick cannot guarantee: the
push can fail, the post can fail, the process can die between them.

So what the round consumed and what its route spent do NOT close here. They are
recorded ON the transaction the report goes out as, and settled by the write
that completes it, whichever tick makes it. Settled directly instead, a crash
in that window leaves the feedback answered and the round spent for a report
nobody published, and the `pending_fix_*` replay source gone with them.

Every other outcome -- the `ACK:`, the question, the timeout -- writes no
report and closes its own bookkeeping directly, which `test_feedback.py`
beside this covers.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_transaction as _report_transaction,
)
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
    resume as _resume,
)
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_settlement_support as recovery,
)

AUTHORIZATION = "authorized: go ahead and vendor the parser"

AWAITING_HUMAN = support.AWAITING_HUMAN
CHECK_SUCCESS = support.CHECK_SUCCESS
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
HISTORICAL_COMMENT_ID = support.HISTORICAL_COMMENT_ID
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PR_LAST_REVIEW_COMMENT_ID = support.PR_LAST_REVIEW_COMMENT_ID
PR_LAST_REVIEW_SUMMARY_ID = support.PR_LAST_REVIEW_SUMMARY_ID
REVIEW_ROUND = support.REVIEW_ROUND
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_FixingFixtureMixin = support._FixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone

_reported = support.fixtures._reported

# Where the four readers stand before the round, so "held" and "settled" are
# both concrete numbers rather than the absence of a key.
SEEDED_READERS = MappingProxyType({
    LAST_ACTION_COMMENT_ID: HISTORICAL_COMMENT_ID,
    PR_LAST_COMMENT_ID: INITIAL_PR_COMMENT_WATERMARK,
    PR_LAST_REVIEW_COMMENT_ID: 0,
    PR_LAST_REVIEW_SUMMARY_ID: 0,
})

class FixingReportSettlementTest(unittest.TestCase, _FixingFixtureMixin):
    """What a reporting fix round closes, and when it is allowed to close it."""

    def test_a_published_report_settles_the_round(self) -> None:
        # The report reaches the pull request on this very tick, so the write
        # that completes the transaction is the one that advances the readers
        # and drops the bookmarks -- and only then does the reviewer get the
        # head back.
        github, issue = self._seed_round()

        self._round(github, issue)

        pinned_data = github.pinned_data(ISSUE)
        self.assertEqual(len(github.posted_pr_comments), 1)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_AT))
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)
        self.assertIn((ISSUE, VALIDATING), github.label_history)

    def test_an_owed_report_holds_the_round(self) -> None:
        # The post never landed, so the transaction still owes the pull
        # request its report. Everything the round would have closed is on
        # that record and nowhere else: the readers have not moved, the
        # replay source is intact, and the reviewer has not been sent a head
        # whose report nothing carries.
        github, issue = self._seed_round()

        self._round(github, issue, publishes=False)

        pinned_data = github.pinned_data(ISSUE)
        owed = _record_state.read_pending_report(
            github.read_pinned_state(issue),
        )
        self.assertEqual(owed.watermarks, self._consumed(issue))
        self.assertEqual(
            dict(owed.spends),
            dict(_resume._spends_fix_round(
                github.read_pinned_state(issue), True,
            ).fields),
        )
        self.assertEqual(
            {reader: pinned_data.get(reader) for reader in SEEDED_READERS},
            SEEDED_READERS,
        )
        self.assertEqual(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 1)
        self.assertNotIn((ISSUE, VALIDATING), github.label_history)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))

    def test_the_recovery_settles_what_was_held(self) -> None:
        # The recovery is the dispatcher's own guard, and what it settles is
        # the record THIS round wrote -- not pairs a fixture chose. Once the
        # post lands, the same two groups reach the pinned comment.
        github, issue = self._seed_round()
        self._round(github, issue, publishes=False)
        state = github.read_pinned_state(issue)

        with recovery.republishing_world(
            github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
        ):
            _report_transaction._reconciles_pending_report(
                github, _TEST_SPEC, issue, VALIDATING, state,
            )

        pinned_data = github.pinned_data(ISSUE)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)

    def _seed_round(self):
        """A `fixing` issue on the in_review route, one reply unread."""
        return self._seed(
            pr=self._open_pr(),
            issue_comments=[FakeComment(
                id=TRIGGER_ID,
                body=AUTHORIZATION,
                user=FakeUser(support.ALICE),
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )],
            extra_state=dict(SEEDED_READERS),
        )

    def _round(self, github, issue, *, publishes: bool = True):
        """One fixing tick whose developer finishes on a `REPORT: READY`.

        `publishes=False` is GitHub refusing the comment, named the way the
        double names it, so what the case is about is a post that landed
        nothing rather than a seam a test replaced.
        """
        if not publishes:
            github.report_failures.refused.add(support.PR_NUMBER)
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            return self._run_fixing(
                github,
                issue,
                run_agent=_agent(
                    session_id=DEV_SESSION, last_message=_reported("fixed"),
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

    def _consumed(self, issue) -> tuple:
        """What this round's batch comes to, off the owner that derives it.

        Built from the reply itself through the stage's own delivery owner
        rather than spelled out, so the case is about the pairs the round
        recorded being the pairs this stage derives -- not about a tuple a
        fixture chose that both sides happen to match.
        """
        seeded = PinnedState(state_data=dict(SEEDED_READERS))
        batch = _models._FixingFeedback(
            issue_thread=[
                seen for seen in issue.comments if seen.id == TRIGGER_ID
            ],
            pr_conversation=[],
            review_comments=[],
            review_summaries=[],
        )
        return _feedback._consumed_delivery(seeded, batch).consumed_pairs(seeded)


if __name__ == "__main__":
    unittest.main()
