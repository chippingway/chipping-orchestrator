# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can finish on `REPORT: READY` exactly as an initial implementation can --
and when it does, the round owes a publication this tick cannot guarantee: the
push can fail, the post can fail, the process can die between them.

So the ROUTE bookkeeping such a round owes does not close here. It is recorded
on the transaction the report goes out as and settled by the write that
completes it, whichever tick makes that. The consumption is the other half and
goes the other way: it is applied into the state before any of it, so whichever
durable write happens next carries it -- a crash between the two would leave
the feedback unread and pay a second developer to answer the same prompt.

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

from orchestrator.github.pinned_state import MAX_PINNED_BODY as _MAX_PINNED_BODY
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_transaction as _report_transaction,
)
from orchestrator.workflow.stages.fixing import resume as _resume
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.report_values import _recovered_report
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_crash_support as crash,
    report_settlement_support as recovery,
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
INLINE_FEEDBACK_ID = support.INLINE_FEEDBACK_ID
IN_REVIEW = support.IN_REVIEW
ISSUE = support.ISSUE
IssueScenario = support.IssueScenario
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_IDS = support.PENDING_FIX_ISSUE_IDS
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PR_HEAD_SHA = support.PR_HEAD_SHA
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PR_LAST_REVIEW_COMMENT_ID = support.PR_LAST_REVIEW_COMMENT_ID
PR_LAST_REVIEW_SUMMARY_ID = support.PR_LAST_REVIEW_SUMMARY_ID
PUSH_BRANCH = support.PUSH_BRANCH
REVIEW_ROUND = support.REVIEW_ROUND
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_FixingFixtureMixin = support._FixingFixtureMixin
_agent = support._agent
_reported = support.fixtures._reported
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone

AUTHORIZATION = "authorized: go ahead and vendor the parser"

# Where the four readers stand before the round, so "held" and "settled" are
# both concrete numbers rather than the absence of a key.
SEEDED_READERS = MappingProxyType({
    LAST_ACTION_COMMENT_ID: HISTORICAL_COMMENT_ID,
    PR_LAST_COMMENT_ID: INITIAL_PR_COMMENT_WATERMARK,
    PR_LAST_REVIEW_COMMENT_ID: 0,
    PR_LAST_REVIEW_SUMMARY_ID: 0,
})

# The route bookkeeping a fix round freezes onto its record: the bookmarks the
# consumed batch clears and the reviewer round it lands on. Only the write that
# completes the publication may apply them.
FROZEN_SPENDS = (
    (PENDING_FIX_AT, None),
    (PENDING_FIX_ISSUE_MAX_ID, None),
    (PENDING_FIX_ISSUE_IDS, None),
    (REVIEW_ROUND, 0),
)

# The one report this build refuses to RECORD: past anything a pinned comment
# can carry, which is the road that parks the run for a human with nothing left
# to carry what it consumed.
_AT_LENGTH = "the change, at length. "
_PAST_ANY_COMMENT = _MAX_PINNED_BODY // len(_AT_LENGTH) + 1
_OVERSIZED_BODY = _AT_LENGTH * _PAST_ANY_COMMENT
_OVERSIZED_REPORT = f"REPORT: READY\n{_OVERSIZED_BODY}\nREPORT: END"

# A location shaped the way the contract spells one, naming a comment this pull
# request does not carry: what those cases are about is the ROAD a verified
# outcome takes, and a location nothing can confirm keeps the publication
# itself out of the way of that question.
# A human reply that lands after the crash, which is what turns the stalled
# issue back into an ordinary fix round.
LATER_COMMENT_ID = TRIGGER_ID + 1
LATER_COMMENT = "one more thing: rename the helper"

_ABSENT_COMMENT = 999
_UNCONFIRMABLE = hashlib.sha256(b"a report nobody posted").hexdigest()


def _keeps_the_replay_state(pinned_data) -> bool:
    """Whether the batch and round an owed publication replays from stand."""
    return (
        pinned_data.get(PENDING_FIX_ISSUE_MAX_ID) == TRIGGER_ID
        and pinned_data.get(REVIEW_ROUND) == 1
    )


def _verified(slug: str) -> str:
    """A run's last message asserting its report is already on the PR."""
    return (
        f"REPORT: VERIFIED https://github.com/{slug}/pull/{support.PR_NUMBER}"
        f"#issuecomment-{_ABSENT_COMMENT} sha256:{_UNCONFIRMABLE}"
    )


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

    def _tick(self, seeded, *, head: str = PR_HEAD_SHA, **run_options):
        """One fixing tick with a developer standing by, unspawned if sound.

        The checkout is real, because what the recovery re-proves is exactly
        that: a tree it can read, a head it can name, and the pull request
        standing on it. `head` is what that checkout answers -- the pull
        request's own commit for a push that landed, and anything else for a
        commit a crash left unpublished.
        """
        run_options.setdefault("head_shas", (head, head))
        with (
            recovery.on_a_real_checkout(
                support.worktree_paths, support.WORKTREE_PATH,
            ),
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
        ):
            return self._run_fixing(
                seeded.github,
                seeded.issue,
                run_agent=_agent(session_id=DEV_SESSION),
                **run_options,
            )

    def _pinned(self, seeded) -> dict:
        """What this issue's pinned comment says after the tick."""
        return seeded.github.pinned_data(ISSUE)

    def _record(self, seeded):
        """This issue's pinned record, as the report readers take it."""
        return seeded.github.read_pinned_state(seeded.issue)

    def _reports_posted(self, seeded) -> int:
        """How many reports reached the pull request."""
        return len(seeded.github.posted_pr_comments)

    def _went_back_to_review(self, seeded) -> bool:
        """Whether the reviewer was handed the head back."""
        return (ISSUE, VALIDATING) in seeded.github.label_history


class FixingReportSettlementTest(unittest.TestCase, _ReportRoundMixin):
    """What a reporting fix round closes, and when it is allowed to close it."""

    def test_a_published_report_settles(self) -> None:
        # The report reaches the pull request on this very tick, so the write
        # that completes the transaction is the one that advances the readers
        # and drops the bookmarks -- and only then does the reviewer get the
        # head back.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue)

        pinned_data = self._pinned(seeded)
        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_AT))
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)
        self.assertTrue(self._went_back_to_review(seeded))

    def test_an_owed_report_holds_the_round(self) -> None:
        # The post never landed, so the transaction still owes the pull
        # request its report -- and it is carrying BOTH groups until it does.
        # The replay source is intact, the reviewer has not been sent a head
        # whose report nothing carries, and the readers have not moved: a
        # batch recorded as answered for a report no reviewer has is exactly
        # what keeping the two together prevents.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, publishes=False)

        pinned_data = self._pinned(seeded)
        owed = _record_state.read_pending_report(
            self._record(seeded),
        )
        self.assertEqual(owed.watermarks, crash.consumed_pairs(seeded.issue, SEEDED_READERS, TRIGGER_ID))
        self.assertEqual(
            dict(owed.spends),
            dict(_resume._spends_fix_round(
                self._record(seeded), True,
            ).fields),
        )
        self.assertEqual(
            pinned_data.get(PR_LAST_COMMENT_ID), INITIAL_PR_COMMENT_WATERMARK,
        )
        self.assertTrue(_keeps_the_replay_state(self._pinned(seeded)))
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))

    def test_an_owed_report_keeps_the_bookmarks(self) -> None:
        # The bounce publishes the commit a failed push stranded and binds the
        # report to it -- and the post fails. The round is NOT spent and the
        # bookmarks are NOT cleared: an outstanding publication replays from
        # them, and the write that completes the transaction is what closes
        # them once the report is really there.
        seeded = self._seed_round()
        seeded.github.report_failures.refused.add(support.PR_NUMBER)
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            spends=FROZEN_SPENDS,
        )

        self._tick(
            seeded, head=SHA_AFTER, branch_ahead_behind=(1, 0),
        )

        self.assertTrue(_record_state.carries_pending_report(
            self._record(seeded),
        ))
        self.assertTrue(_keeps_the_replay_state(self._pinned(seeded)))
        self.assertFalse(self._went_back_to_review(seeded))

    def test_the_recovery_settles_it(self) -> None:
        # The recovery is the dispatcher's own guard, and what it settles is
        # the record THIS round wrote -- not pairs a fixture chose. Once the
        # post lands, the same two groups reach the pinned comment.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)
        state = self._record(seeded)

        with recovery.republishing_world(
            seeded.github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
        ):
            _report_transaction._reconciles_pending_report(
                seeded.github, _TEST_SPEC, seeded.issue, VALIDATING, state,
            )

        pinned_data = self._pinned(seeded)
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

        pinned_data = self._pinned(seeded)
        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertTrue(self._went_back_to_review(seeded))

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
                self._record(seeded),
            )
            or _record_state.carries_pending_report(
                self._record(seeded),
            ),
        )
        self.assertNotIn((ISSUE, IN_REVIEW), seeded.github.label_history)

    def test_a_failed_push_keeps_the_record(self) -> None:
        # Nothing was published, so the report is still ahead of this issue
        # rather than behind it: the record keeps both groups, the readers do
        # not move, and the bounce that republishes this commit is what binds
        # the report and lets the settlement close them.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, push_branch=False)

        pinned_data = self._pinned(seeded)
        self.assertEqual(
            pinned_data.get(PR_LAST_COMMENT_ID), INITIAL_PR_COMMENT_WATERMARK,
        )
        self.assertEqual(
            pinned_data.get(LAST_ACTION_COMMENT_ID), HISTORICAL_COMMENT_ID,
        )
        self.assertTrue(
            _delivery_state.carries_delivered_report(
                self._record(seeded),
            ),
        )
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertFalse(self._went_back_to_review(seeded))

    def test_the_bounce_binds_a_stranded_report(self) -> None:
        # The bounce is the one tick that republishes the commit a failed
        # push stranded, so it is the only road that can turn the delivery
        # that push left into a transaction anything could finish.
        seeded = IssueScenario(*self._seed(
            pr=self._open_pr(), extra_state=dict(SEEDED_READERS),
        ))
        state = self._record(seeded)
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

        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertTrue(self._went_back_to_review(seeded))

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

        pinned_data = self._pinned(seeded)
        self.assertNotIn((ISSUE, IN_REVIEW), seeded.github.label_history)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(self._reports_posted(seeded), 0)

class FixingReportRefusalTest(unittest.TestCase, _ReportRoundMixin):
    """The readings a report may not be published over."""

    def test_a_misread_contract_publishes_nothing(self) -> None:
        # The sharpest version of the miss: a report AND an `ACK:`, from a run
        # that also committed. Left to the publication tail it pushes the
        # commit and relabels with no report on the pull request at all.
        seeded = self._seed_round()

        mocks = self._round(
            seeded.github, seeded.issue,
            message=f"{_reported('fixed')}\n\nACK: nothing to change",
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(self._reports_posted(seeded), 0)
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))

    def test_an_unreadable_head_publishes_nothing(self) -> None:
        # A HEAD nobody could read comes back empty, and read as "nothing to
        # publish" it would bind the report against whatever head the
        # preflight happened to see.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue, head_shas=(SHA_BEFORE, ""),
        )

        self.assertEqual(self._reports_posted(seeded), 0)
        self.assertFalse(self._went_back_to_review(seeded))

    def test_an_unreadable_tree_publishes_nothing(self) -> None:
        # `_worktree_dirty_files` answers an empty list for a status nobody
        # could read, which is indistinguishable from a clean tree. Asked
        # through `is_clean` instead, an unread checkout is what it is: work
        # nobody can see the shape of, and no report goes out over it.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue,
            head_shas=(SHA_BEFORE, SHA_BEFORE),
            tree_readable=False,
        )

        self.assertEqual(self._reports_posted(seeded), 0)
        self.assertFalse(self._went_back_to_review(seeded))

    def test_an_unrecordable_report_consumes(self) -> None:
        # A report past what the pinned comment holds parks the run for a
        # human, and nothing is carrying its consumed pairs -- so this road
        # closes them itself. Left open, the next tick reads the same feedback
        # as fresh, clears the very park just taken, and pays a second
        # developer with no human having said a word.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue,
            message=_OVERSIZED_REPORT,
            head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))
        mocks = self._tick(seeded)
        mocks[RUN_AGENT].assert_not_called()

    def test_an_ack_cannot_answer_an_owed_report(self) -> None:
        # The debt an earlier tick left is read off the RECORD, not off this
        # run. Read off the run, a plain `ACK:` would clear the bookmarks and
        # return the pull request to review as needing nothing -- while the
        # report it owes is still on the pinned comment and nothing has gone
        # out. There is no report here either, so the round parks instead.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )
        crash.later_comment(seeded.issue, LATER_COMMENT_ID, LATER_COMMENT)

        # A real checkout, standing ahead of the pull request: the recovery
        # declines it without parking (the bounce still republishes such a
        # commit), so this case is about the ACK road and not about that one.
        with recovery.on_a_real_checkout(
            support.worktree_paths, support.WORKTREE_PATH,
        ):
            mocks = self._round(
                seeded.github, seeded.issue,
                message="ACK: nothing to change here",
                head_shas=(SHA_AFTER,) * 4,
            )

        mocks[RUN_AGENT].assert_called_once()
        self.assertNotIn((ISSUE, IN_REVIEW), seeded.github.label_history)
        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))
        self.assertTrue(_keeps_the_replay_state(self._pinned(seeded)))

    def test_the_park_write_carries_the_settlement(self) -> None:
        # The park is durable the moment it is written, and what it writes has
        # to already say the batch was consumed. Applied in a write of its own
        # afterwards, a crash in between leaves the feedback unread -- and the
        # next tick clears the very park just taken and spawns a second
        # developer over the same prompt with no human having said anything.
        seeded = self._seed_round()
        written = []

        with crash.recorded_writes(seeded.github, written):
            self._round(
                seeded.github, seeded.issue,
                message=_OVERSIZED_REPORT,
                head_shas=(SHA_BEFORE, SHA_BEFORE),
            )

        parked = [
            state_data for state_data in written
            if state_data.get(PARK_REASON)
            == _report_delivery.UNDELIVERABLE_REPORT
        ]
        self.assertTrue(parked)
        self.assertEqual(parked[0].get(PR_LAST_COMMENT_ID), TRIGGER_ID)

    def test_a_head_the_pr_lacks_publishes_nothing(self) -> None:
        # The checkout is clean and did not move, and it is still not standing
        # on what the pull request carries: the report would describe work the
        # remote does not have.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue, head_shas=(SHA_AFTER, SHA_AFTER),
        )

        self.assertEqual(self._reports_posted(seeded), 0)
        self.assertFalse(self._went_back_to_review(seeded))


class FixingReportRecoveryTest(unittest.TestCase, _ReportRoundMixin):
    """A report a crash left recorded and unbound, on the tick that follows."""

    def test_a_pre_push_crash_keeps_the_report(self) -> None:
        # The commit that crash left is not on the pull request, so there is
        # nothing to bind and nothing to prove -- and the readers stay exactly
        # where they were, because what moves them is the write that completes
        # a publication. The record keeps both groups for that write, and the
        # round the rescan below runs binds it rather than relabelling past
        # it. (The cost of holding the readers back is that this window
        # re-delivers the batch once; the report is not lost by it.)
        seeded = self._seed_round()
        # An older round's receipt, naming the very commit the pull request
        # is standing on. Read as proof that THIS report's run pushed, it
        # would publish a report about work that never left the checkout.
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            landed=PR_HEAD_SHA, spends=FROZEN_SPENDS,
        )

        self._tick(seeded, head=SHA_AFTER)

        pinned_data = self._pinned(seeded)
        self.assertTrue(_delivery_state.carries_delivered_report(
            self._record(seeded),
        ))
        self.assertEqual(self._reports_posted(seeded), 0)
        self.assertFalse(self._went_back_to_review(seeded))
        # The round the record froze is untouched, and so is the replay source
        # an outstanding publication rebuilds its batch from.
        self.assertTrue(_keeps_the_replay_state(pinned_data))

    def test_a_post_push_crash_publishes_the_report(self) -> None:
        # A tree it can read, a head it can name, and the pull request
        # standing on it: that is the proof the push landed, and the report it
        # is about can be bound and posted with no developer run at all. The
        # round the record froze is settled with it, and the recovered route
        # is FINISHED -- handed back to the reviewer rather than left on
        # `fixing` under a route the settlement has just cleared.
        seeded = self._seed_round()
        # The standing receipt names some other commit, as it does on every
        # tick that did not push: what the binding is held to is the commit
        # this call proved, never the one the record happens to remember.
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            landed=SHA_AFTER, spends=FROZEN_SPENDS,
        )

        mocks = self._tick(seeded)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertTrue(self._went_back_to_review(seeded))
        self.assertIsNone(self._pinned(seeded).get(PENDING_FIX_AT))

    def test_a_checkoutless_report_parks_for_a_human(self) -> None:
        # With the worktree gone there is nothing left to republish and
        # nothing left to prove: the commit the report describes is either on
        # the pull request already or gone with the checkout, and no reading
        # on this host can say which. Said once, the issue waits -- rather
        # than every tick finding no feedback, no checkout and an owed report
        # and quietly doing nothing with any of them.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            spends=FROZEN_SPENDS,
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                seeded.github, seeded.issue,
                run_agent=_agent(session_id=DEV_SESSION),
                head_shas=(SHA_BEFORE, SHA_BEFORE),
            )

        mocks[RUN_AGENT].assert_not_called()
        pinned_data = self._pinned(seeded)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), _report_delivery.UNDELIVERABLE_REPORT)
        self.assertEqual(len(seeded.github.posted_comments), 1)

    def test_a_later_comment_binds_the_report(self) -> None:
        # The crash left a commit the push never carried and a report nobody
        # bound; then a human comments. The round that answers them pushes
        # that commit, and its own reply carries no report -- so the record on
        # the comment is the only one there is, and the push it just earned is
        # the publication it was waiting for. Read off THIS run instead, the
        # bookmarks would be spent, the issue relabelled, and the report left
        # orphaned with nothing to bind it to.
        #
        # What the binding then finds is the reply itself: a report written
        # against the issue as it stood before that comment does not answer
        # the issue as it stands now, so the engine leaves it owed and the
        # drift road resumes the developer for it. Owed is the point -- it is
        # a transaction something comes back for, where a delivery nothing
        # bound is not.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            spends=FROZEN_SPENDS,
        )
        crash.later_comment(seeded.issue, LATER_COMMENT_ID, LATER_COMMENT)

        # One head, answered to every probe this tick takes: the recovery's
        # own reading, the two the resume brackets its run with, and the
        # publication's.
        mocks = self._tick(
            seeded, head_shas=(SHA_AFTER,) * 6,
            branch_ahead_behind=(1, 0), push_branch=True,
        )

        mocks[RUN_AGENT].assert_called_once()
        self.assertTrue(_record_state.carries_pending_report(
            self._record(seeded),
        ))
        self.assertFalse(_delivery_state.carries_delivered_report(
            self._record(seeded),
        ))
        # Nothing was spent and nobody was handed the head while it stands.
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertTrue(_keeps_the_replay_state(self._pinned(seeded)))

    def test_a_settled_round_finishes_first(self) -> None:
        # The reconciliation ahead of every handler completes the transaction
        # and lets the tick carry on, and the write it made closed this
        # route's bookkeeping. Carrying on, the rescan would read the comment
        # that landed since under a route the settlement has just closed --
        # an in_review batch answered as a validating one, where an ordinary
        # `ACK:` is refused instead of returning the pull request to review.
        # So the round is finished first and the tick ends.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)
        crash.later_pr_comment(
            seeded.github.get_pr(support.PR_NUMBER),
            LATER_COMMENT_ID, LATER_COMMENT,
        )

        with recovery.republishing_world(
            seeded.github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
        ):
            _report_transaction._reconciles_pending_report(
                seeded.github, _TEST_SPEC, seeded.issue, VALIDATING,
                self._record(seeded),
            )
            mocks = self._tick(seeded, head=SHA_AFTER)

        # No developer answered the later comment on the tick that settled the
        # report, and the issue is back with the reviewer under the round the
        # settlement closed.
        mocks[RUN_AGENT].assert_not_called()
        self.assertTrue(self._went_back_to_review(seeded))

    def test_a_dirty_checkout_parks_for_a_human(self) -> None:
        # A tree this host PROVED dirty is the other refusal nothing takes
        # back: the republishing bounce declines a dirty checkout exactly as
        # the recovery does, so the two decline together and every poll finds
        # no feedback, no publishable checkout and an owed report. Said once,
        # the issue waits for the hand that can clean it.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            spends=FROZEN_SPENDS,
        )

        mocks = self._tick(seeded, dirty_files=("stray.py",))

        mocks[RUN_AGENT].assert_not_called()
        pinned_data = self._pinned(seeded)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(
            pinned_data.get(PARK_REASON),
            _report_delivery.UNDELIVERABLE_REPORT,
        )
        self.assertEqual(len(seeded.github.posted_comments), 1)

    def test_an_unposted_report_holds_the_tick(self) -> None:
        # The binding landed and the post did not, so a transaction is owed.
        # Nothing may relabel past it: the bookmarks it replays from are the
        # ones the bounce would otherwise clear on its way to `validating`,
        # leaving a reviewer reading a head no report describes.
        seeded = self._seed_round()
        seeded.github.report_failures.refused.add(support.PR_NUMBER)
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )

        self._tick(seeded)

        self.assertTrue(_record_state.carries_pending_report(
            self._record(seeded),
        ))
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertTrue(_keeps_the_replay_state(self._pinned(seeded)))



if __name__ == "__main__":
    unittest.main()
