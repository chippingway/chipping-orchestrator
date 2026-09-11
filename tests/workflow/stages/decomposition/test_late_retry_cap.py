# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent spawn budget a late adjudication parks on, and what lifts it.

Four promises are pinned here. A budget with nothing left in it parks the
issue before any agent starts, and the write that records the park carries
both the late record it stopped on and the sentence it owes the thread. A park
nobody has answered then stops every later tick and every restart where it
stands, keeping the frozen candidate, its held pull request, and the locked
run exactly as they arrived. A trusted `/orchestrator continue` buys one
attempt and no more. And each of those steps is countable on the shared
budget's own audit stream.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.fixtures import _iso_hours_ago
from tests.workflow.stages.decomposition import late_retry_cap_support as _support
from tests.workflow.stages.decomposition.late_content_support import (
    EDITED_BODY,
    HUMAN,
    OUTSIDER,
    PARK_NOTICE_ID,
)
from tests.workflow.stages.decomposition.late_retry_cap_support import (
    LateRetryCapCase,
    PausedDuringRun,
    UnreadableThread,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
    SPLIT_REPLY,
)

HELD_TICKS = 3

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"


class ExhaustionTest(LateRetryCapCase):
    """The write and the sentence a spent budget takes on the way out."""

    def test_it_parks_unspawned_and_says_so_once(self) -> None:
        # The gate refuses ahead of the pre-spawn record, so nothing claims an
        # attempt nobody made -- and the park is durable before a word of it
        # is said, since a notice on a thread no pinned state backs is one
        # nothing would ever reconcile.
        self._spend_the_budget()

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self._assert_reads_as(_support.PARKED_STATE)
        self.assertNotIn(KEYS.source_sha, self._pinned())
        self.assertEqual(len(self._bodies()), 1)
        self.assertIn(_support.CAP_SENTENCE, self._bodies()[0])

    def test_the_record_rides_the_same_write(self) -> None:
        # The reason the park is staged through this mode's own park owner:
        # the frozen candidate and the hold's record of the pull request it
        # stands under are what the refusal leaves standing, and a park
        # written past them would lose them or have to write them twice.
        self._spend_the_budget(**_support.HELD_PLAN_PR)

        self._tick()

        self._assert_reads_as({
            **_support.PARKED_STATE,
            KEYS.candidate_sha: CANDIDATE_SHA,
            KEYS.plan_pr_number: PLAN_PR_NUMBER,
            KEYS.plan_pr_body: PLAN_PR_BODY,
        })

    def test_the_refusal_names_the_spent_stage(self) -> None:
        # The budget is shared, so the label a parked issue wears is not
        # always the stage whose spawn ran out -- what the audit reports is
        # read off the park rather than off the label.
        self._spend_the_budget()

        self._tick()

        self.assertEqual(
            [
                (record["phase"], record["stage"])
                for record in self.github.recorded_events
                if record["event"] == _support.RETRY_CAP_EVENT
            ],
            [(_support.PHASE_DELIVERED, _support.STAGE_DECOMPOSING)],
        )


class StandingParkTest(LateRetryCapCase):
    """What a park nobody has answered outlives."""

    def test_repeated_ticks_hold_it_and_write_nothing(self) -> None:
        # Every tick re-reads the pinned comment, so each of these is the
        # restart the next process would be -- and each refuses on the record
        # it finds rather than on anything the tick before it left in memory.
        self._park()

        for _ in range(HELD_TICKS):
            spawn = self._tick()

        self._assert_held(spawn)
        # The refusals are countable: an operator reading the stream sees a
        # park that goes on refusing rather than an adjudication that went
        # quiet.
        self.assertEqual(self._phases(), (_support.PHASE_STANDING,) * HELD_TICKS)

    def test_it_keeps_what_the_issue_arrived_with(self) -> None:
        # The park is asked ahead of the evidence probe, the hold, and the
        # content settlement, so an edited body neither parks the candidate
        # nor resumes a developer, the pull request keeps the notice saying an
        # adjudication is running, and the locked late run stays pinned.
        self._park(**_support.CARRIED_STATE)
        self.issue.body = EDITED_BODY

        self._assert_held(self._tick())

        self.assertIn(PLAN_PR_BODY, self.plan_pr.body)

    def test_only_a_trusted_command_lifts_it(self) -> None:
        # This park is waiting on a human deciding to spend more of the
        # issue's day on the candidate, which "any update?" does not say --
        # and an outsider's copy of the command buys agent time on somebody
        # else's word.
        for reply in (_support.trusted("any update?"), _support.outsider(_support.CONTINUE_COMMAND)):
            with self.subTest(author=reply.user.login):
                self._park(reply)

                with patch.object(config, ALLOWED_AUTHORS, (HUMAN,)):
                    self._assert_held(self._tick())

    def test_the_clock_does_not_lift_it(self) -> None:
        # The window is a budget window, not a parole hearing: a notice that
        # asked for a human is not answered by the day passing it.
        self._park(**{KEYS.retry_window: _iso_hours_ago(_support.ELAPSED_HOURS)})

        self._assert_held(self._tick())

    def test_an_unreadable_thread_holds_it(self) -> None:
        # A read that failed establishes nothing, and the two failures are not
        # symmetric: a park held one poll too long is answered by the next
        # read, while a grant handed out on a thread nobody could read spends
        # an attempt no human asked for.
        self._park(commanded=True)
        refused = UnreadableThread()

        with patch.object(self.github, "comments_after", refused):
            self._assert_held(self._tick())

        self.assertEqual(refused.calls, 1)


class ContinuationTest(LateRetryCapCase):
    """The one answer that lifts the park, and what it buys."""

    def test_a_trusted_command_buys_a_fresh_run(self) -> None:
        self._park(commanded=True)

        outcome, spawn = self._run(SPLIT_REPLY)

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        # A fresh conversation rather than a resume: what the park owes the
        # issue is the spawn the budget refused.
        spawn.assert_called_once()
        self.assertIsNone(spawn.call_args.kwargs.get("resume_session_id"))
        self._assert_reads_as(_support.GRANT_SPENT)
        self.assertNotIn(_support.KEY_RETRY_CAP_STAGE, self._pinned())
        self.assertGreaterEqual(
            self._pinned()[_support.KEY_LAST_ACTION_COMMENT_ID], _support.ANSWER_ID,
        )
        self.assertEqual(self._phases(), (_support.PHASE_CONTINUED,))

    def test_a_command_beside_guidance_still_counts(self) -> None:
        # A decision that arrives with an explanation is still the decision,
        # and the explanation reaches the fresh adjudicator through the late
        # prompt rather than being refused for arriving together.
        self._park(_support.trusted(f"{_support.GUIDANCE}\n\n{_support.CONTINUE_COMMAND}"))

        spawn = self._tick()

        spawn.assert_called_once()
        self.assertIn(_support.GUIDANCE, spawn.call_args.args[1])
        self._assert_reads_as(_support.GRANT_SPENT)

    def test_the_attempt_it_buys_is_the_only_one(self) -> None:
        # One command, one adjudication. The unusable reply below parks for a
        # reason the next attempt supersedes, which is the road that retires a
        # park and re-spawns in the same tick -- so it is where a grant read
        # as a fresh day rather than as a single attempt would show.
        self._park(commanded=True)
        self._tick(_support.UNUSABLE_REPLY)
        self.assertEqual(self._pinned()[KEYS.park_reason], _support.PARK_UNPARSED)

        spawn = self._tick()

        spawn.assert_not_called()
        self._assert_reads_as(_support.PARKED_STATE)
        self.assertIn(_support.CAP_SENTENCE, self._bodies()[-1])

    def test_a_declined_run_leaves_it_unspent(self) -> None:
        # The grant is durable before the agent starts and the spend is not,
        # so a run a mid-run `paused` declines costs the issue nothing: the
        # attempt is still where the human put it, and the next tick takes it.
        self._park(commanded=True)

        outcome, _ = self._run(PausedDuringRun(self.issue))

        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self._assert_reads_as({
            **_support.GRANT_SPENT, KEYS.retry_count: 0, KEYS.retry_grant: 1,
        })
        self.assertEqual(self._bodies(), [])


class OwedNoticeTest(LateRetryCapCase):
    """What the park owes the thread, said once however it was stranded."""

    def test_a_refused_notice_stays_owed(self) -> None:
        # Nothing supersedes this park, so a sentence lost here is one nobody
        # would ever say: the obligation outlives the tick that failed to
        # discharge it, and the thread was told nothing.
        self._park_on_a_refused_notice()

        recorded = self._pinned().get(KEYS.park_notice, {})
        self._assert_reads_as(_support.PARKED_STATE)
        self.assertEqual(recorded.get("reason"), _support.PARKED_STATE[KEYS.park_reason])
        self.assertIn(_support.CAP_SENTENCE, recorded.get("message", ""))
        self.assertEqual(self._bodies(), [])

    def test_the_next_tick_says_what_the_park_is_for(self) -> None:
        self._park_on_a_refused_notice()

        spawn = self._tick()

        spawn.assert_not_called()
        self.assertEqual(len(self._bodies()), 1)
        self.assertIn(_support.CAP_SENTENCE, self._bodies()[0])
        self.assertNotIn(KEYS.park_notice, self._pinned())
        self.assertEqual(
            self._phases(), (_support.PHASE_DELIVERED, _support.PHASE_STANDING),
        )

    def test_a_command_before_the_notice_is_no_answer(self) -> None:
        # Saying the sentence moves the response boundary past everything
        # written under the old one, so a command that predates the question
        # is consumed by the delivery rather than read as an answer to it.
        self._park(commanded=True, **{KEYS.park_notice: _support.owed_notice()})

        spawn = self._tick()

        spawn.assert_not_called()
        self.assertEqual(len(self._bodies()), 1)
        # Verbatim: the thread is searched for exactly the sentence the park
        # recorded, so a delivery that reworded it would find nothing.
        self.assertIn(_support.NOTICE, self._bodies()[0])
        self._assert_reads_as(_support.PARKED_STATE)
        self.assertNotIn(KEYS.park_notice, self._pinned())
        self.assertEqual(
            self._phases(), (_support.PHASE_DELIVERED, _support.PHASE_STANDING),
        )

    def test_a_notice_on_the_thread_is_reconciled(self) -> None:
        # The other failure: the post landed and the write recording it did
        # not, so the record claims a sentence the issue already carries. It
        # is repaired rather than repeated -- and the command written UNDER it
        # is a real answer, taken by the same tick that repairs the record.
        self._park(
            _support.posted_notice(),
            _support.trusted(_support.CONTINUE_COMMAND),
            **{KEYS.park_notice: _support.owed_notice()},
        )

        spawn = self._tick()

        self.assertNotIn(_support.NOTICE, "".join(self._bodies()))
        spawn.assert_called_once()
        self.assertNotIn(KEYS.park_notice, self._pinned())
        self.assertEqual(
            self._phases(), (_support.PHASE_RECONCILED, _support.PHASE_CONTINUED),
        )

    def test_an_outsiders_copy_is_no_receipt(self) -> None:
        # The sentence carries no marker of its own, so anybody on a public
        # thread can paste it back. Read from anybody it would mark the notice
        # said, drag the watermark past whatever was written under it, and buy
        # an attempt off a command written before the human was ever told what
        # the issue had stopped for -- and nothing supersedes this park, so
        # nothing would ever say the sentence again.
        self._park(
            _support.posted_notice(login=OUTSIDER),
            _support.trusted(_support.CONTINUE_COMMAND),
            **{KEYS.park_notice: _support.owed_notice()},
        )

        spawn = self._tick()

        spawn.assert_not_called()
        self.assertIn(_support.NOTICE, self._bodies()[0])
        self._assert_reads_as(_support.PARKED_STATE)
        self.assertEqual(
            self._phases(), (_support.PHASE_DELIVERED, _support.PHASE_STANDING),
        )

    def test_the_repair_moves_the_boundary(self) -> None:
        # Both halves the failed write was carrying: the obligation dropped,
        # and the watermark ratcheted to the comment that really carried the
        # sentence rather than left at the id the park was taken under.
        self._park(_support.posted_notice(), **{KEYS.park_notice: _support.owed_notice()})
        self.assertEqual(
            self.standing[_support.KEY_LAST_ACTION_COMMENT_ID], PARK_NOTICE_ID,
        )

        self._tick()

        self.assertEqual(
            self._pinned()[_support.KEY_LAST_ACTION_COMMENT_ID], _support.DELIVERED_NOTICE_ID,
        )
        self.assertEqual(self._bodies(), [])
