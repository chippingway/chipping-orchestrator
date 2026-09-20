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

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_transaction as _report_transaction,
)
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
    resume as _resume,
)
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.report_values import _recovered_report
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_settlement_support as recovery,
)

AUTHORIZATION = "authorized: go ahead and vendor the parser"

# A location shaped the way the contract spells one, naming a comment this
# pull request does not carry: what the case is about is the ROAD a verified
# outcome takes, and a location nothing can confirm keeps the publication
# itself out of the way of that question.
_ABSENT_COMMENT = 999
_UNCONFIRMABLE = hashlib.sha256(b"a report nobody posted").hexdigest()


def _verified(slug: str) -> str:
    """A run's last message asserting its report is already on the PR."""
    return (
        f"REPORT: VERIFIED https://github.com/{slug}/pull/{support.PR_NUMBER}"
        f"#issuecomment-{_ABSENT_COMMENT} sha256:{_UNCONFIRMABLE}"
    )

AWAITING_HUMAN = support.AWAITING_HUMAN
CHECK_SUCCESS = support.CHECK_SUCCESS
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
HISTORICAL_COMMENT_ID = support.HISTORICAL_COMMENT_ID
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
IN_REVIEW = support.IN_REVIEW
IssueScenario = support.IssueScenario
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

class _ReportRoundMixin(_FixingFixtureMixin):
    """One fix round whose developer finishes on a report outcome."""

    def _seed_round(self):
        """A `fixing` issue on the in_review route, one reply unread."""
        return IssueScenario(*self._seed(
            pr=self._open_pr(),
            issue_comments=[FakeComment(
                id=TRIGGER_ID,
                body=AUTHORIZATION,
                user=FakeUser(support.ALICE),
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )],
            extra_state=dict(SEEDED_READERS),
        ))

    def _round(
        self,
        github,
        issue,
        *,
        publishes: bool = True,
        message: str = "",
        **run_options,
    ):
        """One fixing tick whose developer finishes on a `REPORT: READY`.

        `publishes=False` is GitHub refusing the comment, named the way the
        double names it, so what the case is about is a post that landed
        nothing rather than a seam a test replaced.
        """
        if not publishes:
            github.report_failures.refused.add(support.PR_NUMBER)
        run_options.setdefault("head_shas", (SHA_BEFORE, SHA_AFTER))
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            return self._run_fixing(
                github,
                issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=message or _reported("fixed"),
                ),
                **run_options,
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

class FixingReportSettlementTest(unittest.TestCase, _ReportRoundMixin):
    """What a reporting fix round closes, and when it is allowed to close it."""

    def test_a_published_report_settles(self) -> None:
        # The report reaches the pull request on this very tick, so the write
        # that completes the transaction is the one that advances the readers
        # and drops the bookmarks -- and only then does the reviewer get the
        # head back.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue)

        pinned_data = seeded.github.pinned_data(ISSUE)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_AT))
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)
        self.assertIn((ISSUE, VALIDATING), seeded.github.label_history)

    def test_an_owed_report_holds_the_round(self) -> None:
        # The post never landed, so the transaction still owes the pull
        # request its report. Everything the round would have closed is on
        # that record and nowhere else: the readers have not moved, the
        # replay source is intact, and the reviewer has not been sent a head
        # whose report nothing carries.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, publishes=False)

        pinned_data = seeded.github.pinned_data(ISSUE)
        owed = _record_state.read_pending_report(
            seeded.github.read_pinned_state(seeded.issue),
        )
        self.assertEqual(owed.watermarks, self._consumed(seeded.issue))
        self.assertEqual(
            dict(owed.spends),
            dict(_resume._spends_fix_round(
                seeded.github.read_pinned_state(seeded.issue), True,
            ).fields),
        )
        self.assertEqual(
            {reader: pinned_data.get(reader) for reader in SEEDED_READERS},
            SEEDED_READERS,
        )
        self.assertEqual(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 1)
        self.assertNotIn((ISSUE, VALIDATING), seeded.github.label_history)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))

    def test_the_recovery_settles_it(self) -> None:
        # The recovery is the dispatcher's own guard, and what it settles is
        # the record THIS round wrote -- not pairs a fixture chose. Once the
        # post lands, the same two groups reach the pinned comment.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)
        state = seeded.github.read_pinned_state(seeded.issue)

        with recovery.republishing_world(
            seeded.github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
        ):
            _report_transaction._reconciles_pending_report(
                seeded.github, _TEST_SPEC, seeded.issue, VALIDATING, state,
            )

        pinned_data = seeded.github.pinned_data(ISSUE)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)


class FixingReportOutcomeTest(unittest.TestCase, _ReportRoundMixin):
    """Which road each report outcome a fix round can reach takes."""

    def test_a_report_only_round_publishes(self) -> None:
        # The prompt asks for exactly this: an item wanting report content
        # only is answered in the report, with no commit for it. Read as an
        # ordinary no-commit reply it would park as a question and the report
        # would sit unpublished behind a human's answer.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, head_shas=(SHA_BEFORE, SHA_BEFORE))

        pinned_data = seeded.github.pinned_data(ISSUE)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertIn((ISSUE, VALIDATING), seeded.github.label_history)

    def test_a_verified_report_reports(self) -> None:
        # The second outcome is an assertion about a report already on the
        # pull request, and it reaches the same road: recorded, then held
        # against the location it names. What it may never be is read as the
        # ordinary no-commit reply its unchanged HEAD makes it look like.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue,
            message=_verified(seeded.github.repo_slug),
            head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

        self.assertTrue(
            _delivery_state.carries_delivered_report(
                seeded.github.read_pinned_state(seeded.issue),
            )
            or _record_state.carries_pending_report(
                seeded.github.read_pinned_state(seeded.issue),
            ),
        )
        self.assertNotIn((ISSUE, IN_REVIEW), seeded.github.label_history)

    def test_a_failed_push_settles_here(self) -> None:
        # Nothing was published, so nothing bound the record: it is a
        # delivery, and the reconciliation reads pending transactions only.
        # Left holding the consumption it would hand the same feedback to a
        # second developer on the very next tick, so this road closes it here
        # and leaves the report on the comment for the bounce to bind.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, push_branch=False)

        pinned_data = seeded.github.pinned_data(ISSUE)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertTrue(
            _delivery_state.carries_delivered_report(
                seeded.github.read_pinned_state(seeded.issue),
            ),
        )
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertNotIn((ISSUE, VALIDATING), seeded.github.label_history)

    def test_the_bounce_binds_a_stranded_report(self) -> None:
        # The bounce is the one tick that republishes the commit a failed
        # push stranded, so it is the only road that can turn the delivery
        # that push left into a transaction anything could finish.
        seeded = IssueScenario(*self._seed(
            pr=self._open_pr(), extra_state=dict(SEEDED_READERS),
        ))
        state = seeded.github.read_pinned_state(seeded.issue)
        for recorded, delivered in _recovered_report(seeded.issue).items():
            state.set(recorded, delivered)
        seeded.github.write_pinned_state(seeded.issue, state)

        with (
            tempfile.TemporaryDirectory() as checkout,
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(
                support.worktree_paths, support.WORKTREE_PATH,
                return_value=Path(checkout),
            ),
        ):
            self._run_fixing(
                seeded.github, seeded.issue,
                run_agent=_agent(session_id=DEV_SESSION),
                head_shas=(SHA_AFTER, SHA_AFTER),
                branch_ahead_behind=(1, 0),
            )

        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertIn((ISSUE, VALIDATING), seeded.github.label_history)

    def test_a_report_beside_an_ack(self) -> None:
        # The reply reached for the report contract and missed -- an `ACK:`
        # line beside a report is the commonest miss. Read on its weakest
        # half it would return the pull request to review as needing no
        # change while the report the developer wrote is dropped unread, so
        # it takes the one road left: the park that asks a human.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue,
            message=f"{_reported('fixed')}\n\nACK: nothing to change",
            head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

        pinned_data = seeded.github.pinned_data(ISSUE)
        self.assertNotIn((ISSUE, IN_REVIEW), seeded.github.label_history)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(len(seeded.github.posted_pr_comments), 0)

if __name__ == "__main__":
    unittest.main()
