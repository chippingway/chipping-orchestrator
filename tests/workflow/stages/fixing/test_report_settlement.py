# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can finish on `REPORT: READY` exactly as an initial implementation can --
and when it does, the round owes a publication this tick cannot guarantee: the
push can fail, the post can fail, the process can die between them.

So neither group such a round owes closes here. Both are recorded on the
transaction the report goes out as -- the pairs its run consumed and the
reviewer round its route spends -- and the write that completes that publication
is the one that applies them, whichever tick makes it. Settled here instead, a
crash in that window leaves feedback recorded as answered for a report no
reviewer has, with the replay source cleared along with it.

The mark beside them is what the settlement leaves for the tick that has to hand
the round back, since the one thing that write cannot do is move a label.

Every other outcome -- the `ACK:`, the question, the timeout -- writes no report
and settles its own consumption directly, ahead of the disposition, which
`test_feedback.py` beside this covers.
"""

from __future__ import annotations

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
from orchestrator.workflow.stages.fixing import (
    reporting as _reporting,
    resume as _resume,
)
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.report_values import _recovered_report
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_crash_support as crash,
    report_settlement_support as recovery,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    spawned_nobody,
)

AWAITING_HUMAN = support.AWAITING_HUMAN
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
FIXING = support.FIXING
HISTORICAL_COMMENT_ID = support.HISTORICAL_COMMENT_ID
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
IN_REVIEW_LABEL = support.IN_REVIEW_LABEL
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

# A human reply that lands after the crash, which is what turns the stalled
# issue back into an ordinary fix round. Numbered clear of the pinned record's
# own comment, which the fixture puts directly above the seeded thread: a reply
# sharing that id is the pinned comment to every reader here, so a case about
# fresh input would be asserting nothing.
LATER_COMMENT_ID = support.HUMAN_REPLY_ID
LATER_COMMENT = "one more thing: rename the helper"

# What a round parks under when the push it made did not land.
_PUSH_FAILED = support.PARK_PUSH_FAILED


def _settles_elsewhere(seeded, *, under: str) -> None:
    """Settle this issue's outstanding transaction under another label.

    The reconciliation runs ahead of every handler on every non-terminal label,
    so a fixing round that left `workflow:fixing` with its publication still
    owed settles where the issue has got to -- and the mark it raises is then
    standing on a comment no fixing tick is reading.
    """
    seeded.github.apply_foreign_label(seeded.issue, under)
    with recovery.republishing_world(
        seeded.github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
    ):
        _report_transaction._reconciles_pending_report(
            seeded.github, _TEST_SPEC, seeded.issue, under,
            seeded.github.read_pinned_state(seeded.issue),
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
        # whose report nothing carries, and the readers have not moved: a batch
        # recorded as answered for a report no reviewer has is exactly what
        # keeping the two together prevents.
        seeded = self._seed_round()

        self._round(seeded.github, seeded.issue, publishes=False)

        pinned_data = self._pinned(seeded)
        owed = _record_state.read_pending_report(self._record(seeded))
        self.assertEqual(
            owed.watermarks,
            crash.consumed_pairs(seeded.issue, SEEDED_READERS, TRIGGER_ID),
        )
        self.assertEqual(
            dict(owed.spends),
            dict(_reporting._closes_the_round(_resume._spends_fix_round(
                self._record(seeded), True,
            ))),
        )
        self.assertEqual(
            pinned_data.get(PR_LAST_COMMENT_ID), INITIAL_PR_COMMENT_WATERMARK,
        )
        self.assertTrue(recovery.keeps_the_replay_state(
            pinned_data, bookmarked=TRIGGER_ID,
        ))
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
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )

        self._tick(seeded, head=SHA_AFTER, branch_ahead_behind=(1, 0))

        self.assertTrue(_record_state.carries_pending_report(
            self._record(seeded),
        ))
        self.assertTrue(recovery.keeps_the_replay_state(
            self._pinned(seeded), bookmarked=TRIGGER_ID,
        ))
        self.assertFalse(self._went_back_to_review(seeded))

    def test_the_recovery_settles_it(self) -> None:
        # The reconciliation is the dispatcher's own guard, and what it settles
        # is the record THIS round wrote -- not pairs a fixture chose. Once the
        # post lands, the same two groups reach the pinned comment.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)

        with recovery.republishing_world(
            seeded.github, pr_number=support.PR_NUMBER, head=SHA_AFTER,
        ):
            _report_transaction._reconciles_pending_report(
                seeded.github, _TEST_SPEC, seeded.issue, FIXING,
                self._record(seeded),
            )

        pinned_data = self._pinned(seeded)
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 0)

    def test_a_settled_round_finishes_first(self) -> None:
        # The reconciliation ahead of every handler completes the transaction
        # and lets the tick carry on, and the write it made closed this route's
        # bookkeeping. Carrying on, the rescan would read the comment that
        # landed since under a route the settlement has just closed -- an
        # in_review batch answered as a validating one, where an ordinary
        # `ACK:` is refused instead of returning the pull request to review. So
        # the round is finished first and the tick ends.
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
                seeded.github, _TEST_SPEC, seeded.issue, FIXING,
                self._record(seeded),
            )
            mocks = self._tick(seeded, head=SHA_AFTER)

        # No developer answered the later comment on the tick that settled the
        # report, and the issue is back with the reviewer under the round the
        # settlement closed.
        spawned_nobody(mocks)
        self.assertTrue(self._went_back_to_review(seeded))
        # The mark that said so is retired with the relabel, so the round it
        # finished cannot be finished again over a later one's feedback.
        self.assertFalse(self._pinned(seeded).get(recovery.SETTLED_ROUND))


class FixingStaleSettlementTest(unittest.TestCase, _ReportRoundMixin):
    """A mark that cannot be about the round in hand finishes nothing."""

    def test_a_mark_left_elsewhere_finishes_no_round(self) -> None:
        # A fixing round can leave `workflow:fixing` with its transaction still
        # outstanding -- a silent validating-route recovery does exactly that
        # -- and the reconciliation ahead of EVERY handler settles it wherever
        # the issue has got to. The mark that settlement raises is then
        # standing on a comment no fixing tick is reading, waiting for
        # whichever round comes next. Read as that round's own, it hands the
        # issue straight back to the reviewer and the feedback the round was
        # opened over is never scanned.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)
        _settles_elsewhere(seeded, under=VALIDATING)
        self.assertTrue(self._pinned(seeded).get(recovery.SETTLED_ROUND))

        # A LATER round opens over a reply of its own, the way the in_review
        # route opens one: its own bookmarks, and the label back on `fixing`.
        crash.later_comment(seeded.issue, LATER_COMMENT_ID, LATER_COMMENT)
        recovery.opens_a_later_round(seeded, bookmarked=LATER_COMMENT_ID)

        mocks = self._round(
            seeded.github, seeded.issue,
            message="which of the two parsers did you mean?",
            head_shas=(SHA_AFTER, SHA_AFTER),
        )

        # The developer answers the reply this round is about, and the mark the
        # older settlement left is retired rather than spent on it.
        self.assertIn(LATER_COMMENT, only_prompt(mocks))
        self.assertFalse(self._pinned(seeded).get(recovery.SETTLED_ROUND))

    def test_an_anchorless_move_finishes_no_round(self) -> None:
        # The same leftover mark, on the one road no anchor catches: a human
        # moves the issue back to `workflow:fixing` by hand, so nothing writes
        # a route anchor and nothing owes a report. Every reading on the
        # comment then looks exactly like a round whose report has just settled
        # -- the settlement cleared the anchors and dropped the transaction
        # itself. What tells them apart is the label that settlement recorded
        # itself under, and this one was not `fixing`.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)
        _settles_elsewhere(seeded, under=VALIDATING)
        crash.later_comment(seeded.issue, LATER_COMMENT_ID, LATER_COMMENT)
        recovery.opens_a_later_round(seeded)

        mocks = self._round(
            seeded.github, seeded.issue,
            message="which of the two parsers did you mean?",
            head_shas=(SHA_AFTER, SHA_AFTER),
        )

        self.assertIn(LATER_COMMENT, only_prompt(mocks))
        self.assertFalse(self._pinned(seeded).get(recovery.SETTLED_ROUND))

    def test_a_historical_report_answers_nothing(self) -> None:
        # A settled report is REPLACED rather than retired, and the publication
        # receipt beside it is persistent, so a pull request standing on the
        # commit one names says only that some round once published it. Read as
        # proof that a round has just settled, this manual relabel onto
        # `workflow:fixing` -- which carries neither route's own anchor --
        # would be bounced straight back to the reviewer with the reply it was
        # moved here to answer never scanned.
        seeded = self._seed_round()
        recovery.records_a_settled_report(
            seeded, head=PR_HEAD_SHA,
            clears=(PENDING_FIX_AT, PENDING_FIX_ISSUE_MAX_ID),
        )

        mocks = self._round(
            seeded.github, seeded.issue,
            message="which of the two parsers did you mean?",
            head_shas=(PR_HEAD_SHA, PR_HEAD_SHA),
        )

        # One developer, handed the authorization this tick was moved here to
        # answer, and no bounce to the reviewer over its head.
        self.assertIn(AUTHORIZATION, only_prompt(mocks))
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))


class FixingReportOutcomeTest(unittest.TestCase, _ReportRoundMixin):
    """Which road each report outcome a fix round can reach takes."""

    def test_a_report_only_round_publishes(self) -> None:
        # The prompt asks for exactly this: an item wanting report content only
        # is answered in the report, with no commit for it. Read as an ordinary
        # no-commit reply it would park as a question and the report would sit
        # unpublished behind a human's answer.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue, head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

        pinned_data = self._pinned(seeded)
        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(pinned_data.get(LAST_ACTION_COMMENT_ID), TRIGGER_ID)
        self.assertIsNone(pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        self.assertTrue(self._went_back_to_review(seeded))

    def test_a_verified_report_reports(self) -> None:
        # The second outcome is an assertion about a report already on the pull
        # request, and it reaches the same road: recorded, then held against
        # the location it names. What it may never be is read as the ordinary
        # no-commit reply its unchanged HEAD makes it look like.
        seeded = self._seed_round()

        self._round(
            seeded.github, seeded.issue,
            message=recovery.verified_report(
                seeded.github.repo_slug, support.PR_NUMBER,
            ),
            head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

        self.assertTrue(_report_delivery.owes_a_report(self._record(seeded)))
        self.assertNotIn((ISSUE, IN_REVIEW_LABEL), seeded.github.label_history)

    def test_a_failed_push_spawns_no_second_developer(self) -> None:
        # The readers a settlement would move are held back until the
        # publication lands, so the batch this round's report was written over
        # still reads as unread. Taken for fresh input, the next tick clears
        # the park nobody answered and pays a second developer to write a
        # second report over the identical prompt -- and the tick after that
        # does it again, for as long as the push keeps failing.
        seeded = self._seed_round()
        with recovery.on_a_real_checkout(
            support.worktree_paths, support.WORKTREE_PATH,
        ):
            self._round(
                seeded.github, seeded.issue, push_branch=False,
                head_shas=(SHA_BEFORE, SHA_AFTER, SHA_AFTER),
            )
            parked = self._pinned(seeded)

            mocks = self._round(
                seeded.github, seeded.issue, push_branch=False,
                head_shas=(SHA_AFTER,) * 4,
            )

        # The first tick parked without moving a reader; the second answers
        # nobody and leaves that park exactly where it found it.
        self.assertEqual(parked.get(PARK_REASON), _PUSH_FAILED)
        self.assertEqual(
            parked.get(PR_LAST_COMMENT_ID), INITIAL_PR_COMMENT_WATERMARK,
        )
        spawned_nobody(mocks)
        pinned_data = self._pinned(seeded)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), _PUSH_FAILED)

    def test_a_refused_post_spawns_no_developer(self) -> None:
        # The same rule where no park was taken at all: a landed push whose
        # post GitHub refused leaves a transaction the reconciliation retries
        # and nothing for a developer to do. Read off the readers alone, the
        # batch that transaction's report answers reads as unread, and every
        # poll spawns a round over it.
        seeded = self._seed_round()
        self._round(seeded.github, seeded.issue, publishes=False)

        mocks = self._round(seeded.github, seeded.issue, publishes=False)

        spawned_nobody(mocks)
        self.assertTrue(_record_state.carries_pending_report(
            self._record(seeded),
        ))
        self.assertTrue(recovery.keeps_the_replay_state(
            self._pinned(seeded), bookmarked=TRIGGER_ID,
        ))
        self.assertFalse(self._went_back_to_review(seeded))

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
        self.assertTrue(_delivery_state.carries_delivered_report(
            self._record(seeded),
        ))
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertFalse(self._went_back_to_review(seeded))

    def test_the_bounce_binds_a_stranded_report(self) -> None:
        # The bounce is the one tick that republishes the commit a failed push
        # stranded, so it is the only road that can turn the delivery that push
        # left into a transaction anything could finish.
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


class FixingReportRefusalTest(unittest.TestCase, _ReportRoundMixin):
    """The readings a report may not be published over."""

    def test_a_misread_contract_publishes_nothing(self) -> None:
        # The reply reached for the report contract and missed -- an `ACK:`
        # line beside a report is the commonest miss. Read on its weakest half
        # it would return the pull request to review as needing no change while
        # the report the developer wrote is dropped unread, so it takes the one
        # road left: the park that asks a human. This run also COMMITTED, which
        # is the sharpest version -- left to the publication tail it pushes
        # that commit and relabels with no report on the pull request at all.
        seeded = self._seed_round()

        mocks = self._round(
            seeded.github, seeded.issue,
            message=f"{_reported('fixed')}\n\nACK: nothing to change",
        )

        pinned_data = self._pinned(seeded)
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((ISSUE, IN_REVIEW_LABEL), seeded.github.label_history)
        self.assertFalse(self._went_back_to_review(seeded))
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(self._reports_posted(seeded), 0)

    def test_an_unprovable_checkout_publishes_nothing(self) -> None:
        # Every reading the report-only road takes is POSITIVE, because no
        # absence proves the pull request already carries this code. A HEAD
        # nobody could read comes back empty; a status nobody could read names
        # no dirty file, which is what a clean tree names too; and a head the
        # pull request is not standing on is work the remote does not have.
        # Read as "nothing to publish", each would bind the report against
        # whatever head the preflight happened to see.
        unprovable = {
            "an unreadable head": ((SHA_BEFORE, ""), {}),
            "an unreadable tree": (
                (SHA_BEFORE, SHA_BEFORE), {"tree_readable": False},
            ),
            "a head the pull request lacks": ((SHA_AFTER, SHA_AFTER), {}),
        }
        for refusal, (heads, world) in unprovable.items():
            with self.subTest(refusal=refusal):
                seeded = self._seed_round()

                self._round(
                    seeded.github, seeded.issue, head_shas=heads, **world,
                )

                self.assertEqual(self._reports_posted(seeded), 0)
                self.assertFalse(self._went_back_to_review(seeded))

    def test_an_unrecordable_report_consumes(self) -> None:
        # A report past what the pinned comment holds parks the run for a
        # human, and nothing is carrying its consumed pairs -- so this road
        # closes them itself, in the park's OWN durable write. Left for a write
        # afterwards, a crash in between leaves the feedback unread, and the
        # next tick reads it as fresh, clears the very park just taken, and
        # pays a second developer with no human having said a word.
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
        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))
        spawned_nobody(self._tick(seeded))

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
        self.assertNotIn((ISSUE, IN_REVIEW_LABEL), seeded.github.label_history)
        self.assertTrue(self._pinned(seeded).get(AWAITING_HUMAN))
        self.assertTrue(recovery.keeps_the_replay_state(
            self._pinned(seeded), bookmarked=TRIGGER_ID,
        ))


class FixingReportRecoveryTest(unittest.TestCase, _ReportRoundMixin):
    """A report a crash left recorded and unbound, on the tick that follows."""

    def test_a_pre_push_crash_keeps_the_report(self) -> None:
        # The commit that crash left is not on the pull request, so there is
        # nothing to bind and nothing to prove -- and the readers stay exactly
        # where they were, because what moves them is the write that completes
        # a publication. The record keeps both groups for that write, and the
        # round the rescan below runs binds it rather than relabelling past it.
        # (The cost of holding the readers back is that this window
        # re-delivers the batch once; the report is not lost by it.)
        seeded = self._seed_round()
        # An older round's receipt, naming the very commit the pull request is
        # standing on. Read as proof that THIS report's run pushed, it would
        # publish a report about work that never left the checkout.
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
        self.assertTrue(recovery.keeps_the_replay_state(
            pinned_data, bookmarked=TRIGGER_ID,
        ))

    def test_a_post_push_crash_publishes_the_report(self) -> None:
        # A tree it can read, a head it can name, and the pull request standing
        # on it: that is the proof the push landed, and the report it is about
        # can be bound and posted with no developer run at all. The round the
        # record froze is settled with it, and the recovered route is FINISHED
        # -- handed back to the reviewer rather than left on `fixing` under a
        # route the settlement has just cleared.
        seeded = self._seed_round()
        # The standing receipt names some other commit, as it does on every
        # tick that did not push: what the binding is held to is the commit
        # this call proved, never the one the record happens to remember.
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID,
            landed=SHA_AFTER, spends=FROZEN_SPENDS,
        )

        mocks = self._tick(seeded)

        spawned_nobody(mocks)
        self.assertEqual(self._reports_posted(seeded), 1)
        self.assertTrue(self._went_back_to_review(seeded))
        self.assertIsNone(self._pinned(seeded).get(PENDING_FIX_AT))

    def test_a_checkoutless_report_parks_for_a_human(self) -> None:
        # With the worktree gone there is nothing left to republish and
        # nothing left to prove: the commit the report describes is either on
        # the pull request already or gone with the checkout, and no reading on
        # this host can say which. Said once, the issue waits -- rather than
        # every tick finding no feedback, no checkout and an owed report and
        # quietly doing nothing with any of them.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )

        # No `on_a_real_checkout`: the default probe names a path no host
        # holds, which is the reading this case is about.
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                seeded.github, seeded.issue,
                run_agent=_agent(session_id=DEV_SESSION),
                head_shas=(SHA_BEFORE, SHA_BEFORE),
            )

        self._parked_unpublishable(seeded, mocks)

    def test_a_dirty_checkout_parks_for_a_human(self) -> None:
        # A tree this host PROVED dirty is the other refusal nothing takes
        # back: the republishing bounce declines a dirty checkout exactly as
        # the recovery does, so the two decline together and every poll finds
        # no feedback, no publishable checkout and an owed report. Said once,
        # the issue waits for the hand that can clean it.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )

        self._parked_unpublishable(
            seeded, self._tick(seeded, dirty_files=("stray.py",)),
        )

    def test_a_later_comment_binds_the_report(self) -> None:
        # The crash left a commit the push never carried and a report nobody
        # bound; then a human comments. The round that answers them pushes that
        # commit, and its own reply carries no report -- so the record on the
        # comment is the only one there is, and the push it just earned is the
        # publication it was waiting for. Read off THIS run instead, the
        # bookmarks would be spent, the issue relabelled, and the report left
        # orphaned with nothing to bind it to.
        #
        # What the binding then finds is the reply itself: a report written
        # against the issue as it stood before that comment does not answer the
        # issue as it stands now, so the engine leaves it owed and the drift
        # road resumes the developer for it. Owed is the point -- it is a
        # transaction something comes back for, where a delivery nothing bound
        # is not.
        seeded = self._seed_round()
        crash.recorded_delivery(
            seeded, SEEDED_READERS, TRIGGER_ID, spends=FROZEN_SPENDS,
        )
        crash.later_comment(seeded.issue, LATER_COMMENT_ID, LATER_COMMENT)

        # One head, answered to every probe this tick takes: the recovery's own
        # reading, the two the resume brackets its run with, and the
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
        self.assertTrue(recovery.keeps_the_replay_state(
            self._pinned(seeded), bookmarked=TRIGGER_ID,
        ))

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
        self.assertTrue(recovery.keeps_the_replay_state(
            self._pinned(seeded), bookmarked=TRIGGER_ID,
        ))

    def _parked_unpublishable(self, seeded, mocks) -> None:
        """The one announcement a definite refusal earns, and no developer."""
        spawned_nobody(mocks)
        pinned_data = self._pinned(seeded)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(
            pinned_data.get(PARK_REASON),
            _report_delivery.UNDELIVERABLE_REPORT,
        )
        self.assertEqual(len(seeded.github.posted_comments), 1)


if __name__ == "__main__":
    unittest.main()
