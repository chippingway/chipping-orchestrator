# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent spawn budget an initial decomposition parks on, and what lifts it.

Three promises are pinned here. A park nobody has answered stops the tick and
keeps the issue exactly as it arrived -- through repeated polls, a restart, an
edited body, a kill switch, and the clock running past the window. A trusted
`/orchestrator continue` buys one attempt and no more. And the sentence the
park owes the thread reaches it once, whichever way the tick that took the
park failed to say it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.workflow.fixtures import LABEL_READY, _agent, _iso_hours_ago
from tests.workflow.stages.decomposition import (
    correction_tick_support as _corrected,
    parked_decomposition_support as _parked,
    retry_cap_support as support,
)

CONTINUE_COMMAND = support.CONTINUE_COMMAND
ISSUE_NUMBER = support.ISSUE_NUMBER
KEY_AWAITING_HUMAN = support.KEY_AWAITING_HUMAN
KEY_CONTINUED = support.KEY_CONTINUED
KEY_PARK_REASON = support.KEY_PARK_REASON
KEY_RETRY_CAP_NOTICE = support.KEY_RETRY_CAP_NOTICE
KEY_RETRY_CAP_STAGE = support.KEY_RETRY_CAP_STAGE
KEY_USER_CONTENT_HASH = "user_content_hash"
RUN_AGENT = support.RUN_AGENT

HELD_TICKS = 3

# Each reply a parked edit's read holds when the budget refuses its fresh
# spawn, and whether the write behind the park's notice is lost: guidance, the
# same guidance with that write repaired on the next tick, and a bare
# continuation written before the park's question.
FROZEN_CAP_CASES = (
    (_parked.REPLY, False),
    (_parked.REPLY, True),
    (CONTINUE_COMMAND, False),
)

# What the issue reads as once the attempt a command bought has been spent:
# no park, the grant emptied rather than dropped, one spawn charged to the
# window the continuation opened, and the words that bought it consumed.
GRANT_SPENT = MappingProxyType({
    KEY_AWAITING_HUMAN: False,
    KEY_PARK_REASON: None,
    KEY_CONTINUED: 0,
    support.KEY_RETRY_COUNT: 1,
    support.KEY_LAST_ACTION_COMMENT_ID: support.COMMAND_COMMENT_ID,
})


class StandingParkTest(unittest.TestCase, support._RetryCapParkCase):
    """What a park nobody has answered outlives."""

    def test_repeated_ticks_hold_it_and_write_nothing(self) -> None:
        # Every tick re-reads the issue, so each of these is the restart the
        # next process would be -- and each one refuses on the record it finds
        # rather than on anything the tick before it left in memory.
        self._park()

        for _ in range(HELD_TICKS):
            mocks = self._tick()

        self._assert_held(mocks)
        # The refusals are countable: an operator reading the stream sees a
        # park that goes on refusing rather than a workflow that went quiet.
        self.assertEqual(
            self._phases(), (support.PHASE_STANDING,) * HELD_TICKS,
        )

    def test_it_keeps_what_the_issue_arrived_with(self) -> None:
        # The park is asked ahead of the drift reset, so a body edited while
        # the issue is stopped does not wipe the manifest, orphan the children
        # already open on GitHub, or retire the locked decomposer session --
        # and the pull request and the finished late cycle stay recorded too.
        self._park(**support.CARRIED_STATE)
        self.issue.body = support.EDITED_BODY

        mocks = self._tick()

        self._assert_held(mocks)

    def test_only_the_command_lifts_it(self) -> None:
        # The generic resume reads any trusted reply as the answer its park
        # was waiting for. This park is waiting on a human deciding to spend
        # more of this issue's day on it, which "any update?" does not say --
        # and an outsider saying it buys agent time on somebody else's word.
        for reply in (
            support.trusted("any update?"),
            support.outsider(CONTINUE_COMMAND),
        ):
            with self.subTest(author=reply.user.login):
                self._park(reply)

                with patch.object(
                    config, "ALLOWED_ISSUE_AUTHORS", (support.TRUSTED_AUTHOR,),
                ):
                    mocks = self._tick()

                self._assert_held(mocks)

    def test_a_reply_over_its_baseline_is_no_answer(self) -> None:
        # Measured against the baseline recorded before it, a trusted reply is
        # no edit: it is exactly what an ordinary park's resume would deliver
        # to the locked session. The park is asked ahead of that resume, so it
        # resumes nothing here either.
        self._park(support.trusted(support.GUIDANCE), **support.CARRIED_STATE)
        self.standing["user_content_hash"] = _content_hash._compute_user_content_hash(self.issue, set(), comments=[])
        self.github.seed_state(ISSUE_NUMBER, **self.standing)

        mocks = self._tick()

        self._assert_held(mocks)

    def test_the_clock_does_not_lift_it(self) -> None:
        # The window is a budget window, not a parole hearing: a notice that
        # asked for a human is not answered by the day passing it.
        self._park(retry_window_start=_iso_hours_ago(support.ELAPSED_HOURS))

        mocks = self._tick()

        self._assert_held(mocks)

    def test_an_unreadable_thread_holds_it(self) -> None:
        # A read that failed establishes nothing, and the two failures are not
        # symmetric: a park held one poll too long is answered by the next
        # read, while a grant handed out on a thread nobody could read spends
        # an attempt no human asked for.
        self._park(commanded=True)

        with patch.object(
            self.github, "comments_after", side_effect=RuntimeError,
        ):
            mocks = self._tick()

        self._assert_held(mocks)

    def test_the_kill_switch_does_not_lift_it(self) -> None:
        # `DECOMPOSE=off` clears decomposer-side park flags on its way to
        # implementation, which on this park would be a setting change
        # resuming a workflow that stopped for a human. Nothing is decomposed
        # while it holds either, so the switch loses nothing by waiting.
        self._park()

        with patch.object(config, "DECOMPOSE", False):
            mocks = self._tick()

        self._assert_held(mocks)


class ContinuationTest(unittest.TestCase, support._RetryCapParkCase):
    """The one answer that lifts the park, and what it buys."""

    def test_a_trusted_command_buys_a_fresh_spawn(self) -> None:
        self._park(commanded=True)

        mocks = self._tick(_agent(last_message=support.SINGLE_MANIFEST))

        # A fresh conversation rather than a resume: the park was taken by the
        # spawn gate, so what it owes the issue is the spawn it refused.
        mocks[RUN_AGENT].assert_called_once()
        launch = mocks[RUN_AGENT].call_args
        self.assertIsNone(launch.kwargs["options"].resume_session_id)
        pinned = self._pinned()
        self.assertEqual(
            {key: pinned.get(key) for key in GRANT_SPENT},
            dict(GRANT_SPENT),
        )
        self.assertNotIn(KEY_RETRY_CAP_STAGE, pinned)
        self.assertIn((ISSUE_NUMBER, LABEL_READY), self.github.label_history)
        self.assertEqual(self._phases(), (support.PHASE_CONTINUED,))

    def test_a_command_beside_guidance_still_counts(self) -> None:
        # A decision that arrives with an explanation is still the decision,
        # and the explanation reaches the fresh decomposer through the prompt
        # it is spawned on rather than being refused for arriving together.
        self._park(
            support.trusted(f"{support.GUIDANCE}\n\n{CONTINUE_COMMAND}"),
        )

        mocks = self._tick(_agent(last_message=support.SINGLE_MANIFEST))

        mocks[RUN_AGENT].assert_called_once()
        self.assertIn(support.GUIDANCE, mocks[RUN_AGENT].call_args.args[1])
        self.assertEqual(self._pinned().get(KEY_CONTINUED), 0)

    def test_the_attempt_it_buys_is_the_only_one(self) -> None:
        # One command, one spawn. The body edit below is the road that clears
        # a park and spawns in the same tick, so it is where a grant read as a
        # fresh day rather than as a single attempt would show: the gate meets
        # a spent grant and parks the issue again instead of paying for a
        # second decomposer nobody asked for.
        self._park(commanded=True)
        self._tick(_agent(last_message=support.DECOMPOSER_QUESTION))
        self.issue.body = support.EDITED_BODY

        mocks = self._tick()

        mocks[RUN_AGENT].assert_not_called()
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(pinned.get(KEY_PARK_REASON), support.PARK_RETRY_CAP)
        said = self._said()
        self.assertIn(support.DRIFT_SENTENCE, said[-2])
        self.assertIn(support.CAP_SENTENCE, said[-1])

    def test_a_spawn_with_no_id_retires_the_old(self) -> None:
        # What the attempt buys is a fresh conversation, and a spawn pins an
        # id of its own only when the backend hands one back -- so a question
        # or a timeout that surfaced none would leave the id the park was
        # taken with standing, and the reply to it would resume the
        # conversation that ran out of budget. The locked spec is not a
        # transcript, so it stays.
        self._park(
            commanded=True,
            decomposer_agent=support.BACKEND_CLAUDE,
            decomposer_session_id=support.OLD_SESSION,
        )

        self._tick(
            _agent(session_id="", last_message=support.DECOMPOSER_QUESTION),
        )

        self.assertIsNone(
            self._pinned().get(support.KEY_DECOMPOSER_SESSION_ID),
        )
        # What the reply to that question is handed: the backend this issue is
        # locked to, and no conversation to replay.
        locked = self._locked_session()
        self.assertEqual(locked.spec, support.BACKEND_CLAUDE)
        self.assertIsNone(locked.session_id)

    def test_a_declined_run_leaves_it_unspent(self) -> None:
        # The grant is durable before the agent starts and the spend is not,
        # so a run a mid-flight `paused` declines costs the issue nothing: the
        # attempt is still where the human put it, and the next tick takes it.
        self._park(commanded=True)
        paused = support.PausedDuringRun(self.issue)

        self._tick(paused)

        self.assertEqual(paused.calls, 1)
        pinned = self._pinned()
        self.assertEqual(pinned.get(KEY_CONTINUED), 1)
        self.assertEqual(pinned.get(support.KEY_RETRY_COUNT), 0)
        self.assertEqual(self.github.label_history, [])


class OwedNoticeTest(unittest.TestCase, support._RetryCapParkCase):
    """What the park owes the thread, said once however it was stranded."""

    def test_a_command_before_the_notice_is_no_answer(self) -> None:
        # The tick that took this park could not post its sentence, so the
        # thread has never been told why the issue stopped. Saying it moves
        # the boundary a reply is measured against, exactly as every other
        # park in this repository does -- a command written before the
        # question was asked is not an answer to it, and the park stands.
        self._park(commanded=True, retry_cap_notice=support.NOTICE)

        mocks = self._tick()

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(len(self._said()), 1)
        self.assertIn(support.NOTICE, self._said()[0])
        pinned = self._pinned()
        self.assertEqual(pinned.get(KEY_PARK_REASON), support.PARK_RETRY_CAP)
        self.assertNotIn(KEY_RETRY_CAP_NOTICE, pinned)
        self.assertEqual(
            self._phases(),
            (support.PHASE_DELIVERED, support.PHASE_STANDING),
        )

    def test_a_failed_read_does_not_free_a_command(self) -> None:
        # The replay reads the thread to see whether the sentence is already
        # on it, and a request that failed leaves the park unexplained. A
        # second read taken in the same tick can succeed where the first did
        # not, and the command it would find was written before the question
        # was ever asked -- so the tick holds on the obligation instead.
        self._park(commanded=True, retry_cap_notice=support.NOTICE)
        flaky = support.FirstReadFails(self.github)

        with patch.object(self.github, "comments_after", flaky):
            mocks = self._tick()

        self._assert_held(mocks)
        self.assertEqual(flaky.calls, 1)
        self.assertEqual(self._phases(), (support.PHASE_STANDING,))

    def test_a_notice_on_the_thread_is_reconciled(self) -> None:
        # The other failure: the post landed and the write recording it did
        # not, so the issue claims a sentence it already carries. It is
        # repaired rather than repeated -- and the command written UNDER it is
        # a real answer, taken by the same tick that repairs the record.
        self._park(
            support.our_notice(),
            commanded=True,
            retry_cap_notice=support.NOTICE,
        )

        mocks = self._tick(_agent(last_message=support.SINGLE_MANIFEST))

        self.assertNotIn(support.NOTICE, "".join(self._said()))
        mocks[RUN_AGENT].assert_called_once()
        pinned = self._pinned()
        self.assertNotIn(KEY_RETRY_CAP_NOTICE, pinned)
        self.assertEqual(pinned.get(KEY_CONTINUED), 0)
        self.assertEqual(
            self._phases(),
            (support.PHASE_RECONCILED, support.PHASE_CONTINUED),
        )


class _LosesTheNoticeWrite:
    """The pinned writer, losing once the write that records a retry-cap park's notice as said."""

    def __init__(self, write) -> None:
        self._write = write
        self.lost = False

    def __call__(self, issue, state):
        parked = state.get(KEY_PARK_REASON) == support.PARK_RETRY_CAP
        if parked and not state.get(KEY_RETRY_CAP_NOTICE) and not self.lost:
            self.lost = True
            raise RuntimeError("502")
        return self._write(issue, state)


class FrozenSpawnCapTest(unittest.TestCase, _parked._ParkedDecompositionCase):
    """A spent budget refusing the fresh decomposition a parked edit buys, over the replies that edit's read held.

    No run read those replies, so the park stops short of them -- through the
    repair of a lost write as much as through its own notice -- and none of
    them, a bare continuation among them, answers it: they were written before
    its question. The trusted continuation written after its notice moves no
    boundary and buys a fresh spawn that quotes them whole, consumed only by
    a run that read them.
    """

    def test_a_capped_fresh_spawn_keeps_the_reply(self) -> None:
        for reply, loses in FROZEN_CAP_CASES:
            with self.subTest(reply=reply, loses_the_notice_write=loses):
                self._park()
                with patch.object(config, "MAX_RETRIES_PER_DAY", 1):
                    self._reply(reply)
                    self.issue.body = _parked.EDITED_BODY
                    self._refuse_and_hold(loses=loses)
                    self._reply(CONTINUE_COMMAND)
                    bought = _parked.decomposer_run()
                    self._tick(bought)
                quoted, session = _parked.launched(bought)
                self.assertIsNone(session, "the bought attempt is a fresh session")
                self.assertIn(reply, quoted)
                self.assertIn(_parked.EDITED_BODY, quoted)

    def test_a_continuation_quotes_the_reply_whole(self) -> None:
        # The attempt is spent on the reply the park held, quoted whole however
        # long -- on the continuation's own tick, or on the next one where a
        # mid-run pause declined that tick's run and left the attempt unspent
        # -- and its settlement carries the boundary over it under the
        # baseline it read, so the tick behind the run's park answers nothing.
        for declined in (False, True):
            with self.subTest(declined=declined):
                command = self._continue_over(_parked.LONG_REPLY, declined=declined)
                bought = _parked.decomposer_run(_parked.INVALID_MANIFEST)

                self._tick(bought)

                quoted, session = _parked.launched(bought)
                self.assertEqual((session, _parked.LONG_REPLY in quoted), (None, True))
                self.assertGreaterEqual(self._pinned()[support.KEY_LAST_ACTION_COMMENT_ID], command.id)
                self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], self._requirements())
                self.assertTrue(self._ticks_quietly(), "the run's park left nothing to answer")

    def test_a_held_continuation_consumes_nothing(self) -> None:
        # Each is a run the bought spawn launched without the decomposer
        # reading the reply the park held, so the reply stays past the
        # boundary under the baseline the edit was measured against.
        for name, record_edit, runner_for, run_options in _parked.HELD_RUNS:
            with self.subTest(name):
                self._continue_over(_parked.REPLY)
                if record_edit is not None:
                    self._edit_record(*record_edit)

                self._tick(runner_for(self.issue), **run_options)

                held = _parked.read_through(self._pinned())
                self.assertEqual(held, (self.floor, self.baseline))

    def _continue_over(self, reply: str, *, declined: bool = False):
        """Park, hold `reply` under the spent budget refusing the edit beside it, and continue: the command.

        Where `declined`, a mid-run `paused` declines the run the
        continuation's own tick launches, and that hold is lifted behind it.
        """
        self._park()
        self._reply(reply)
        self.issue.body = _parked.EDITED_BODY
        with patch.object(config, "MAX_RETRIES_PER_DAY", 1):
            self._refuse_and_hold(loses=False)
        command = self._reply(CONTINUE_COMMAND)
        if declined:
            self._tick(_parked.PausedWhileOut(self.issue))
            self.assertEqual(self._pinned()[KEY_CONTINUED], 1, "the declined run spent no attempt")
            lifted = support.PAUSED_LABEL
            self.issue.labels = [label for label in self.issue.labels if label.name != lifted]
        return command

    def _ticks_quietly(self) -> bool:
        """Whether one more tick launches nothing."""
        quiet = _parked.decomposer_run()
        self._tick(quiet)
        return not quiet.called

    def _edit_record(self, key: str, edited) -> None:
        """Rewrite one field of the issue's own pinned comment, in place."""
        state = self.github.read_pinned_state(self.issue)
        state.set(key, edited)
        self.github.write_pinned_state(self.issue, state)

    def _refuse_and_hold(self, *, loses: bool) -> None:
        """The tick the spent budget refuses the fresh spawn on, and a quiet one behind it the park holds.

        The write behind the park's notice is lost where `loses`, so the tick
        behind it repairs that write. Neither tick runs anything or moves the
        boundary over the replies, and the baseline stays the one the edit
        was measured against.
        """
        refused = _parked.decomposer_run()
        if loses:
            losing = _LosesTheNoticeWrite(self.github.write_pinned_state)
            with patch.object(self.github, "write_pinned_state", side_effect=losing), self.assertRaises(RuntimeError):
                self._tick(refused)
        else:
            self._tick(refused)
        self._tick(refused)
        self.assertEqual(
            (refused.call_count, *_parked.read_through(self._pinned())),
            (0, self.floor, self.baseline),
        )



class CorrectionCapTest(unittest.TestCase, _corrected.CorrectionTickCase):
    """A manifest correction is a retry the daily budget pays for, and the continuation keeps what it always bought.

    The rejected run spends the last slot, so its correction takes the
    retry-cap park instead, said once. The trusted continuation retires the
    session that correction was saved under -- so the attempt is retired, never
    launched -- and buys the fresh decomposition it always bought, spending
    the one attempt it granted and nothing more.
    """

    def test_a_capped_correction_is_retired(self) -> None:
        with patch.object(config, "MAX_RETRIES_PER_DAY", 1):
            self._capped()
            self.reply(CONTINUE_COMMAND)
            bought = self.decomposer(_corrected.SINGLE)

            self.tick(bought)

        self.assertEqual(len(bought.launches), 1)
        self.assertIsNone(bought.launches[0].resumed, "the continuation buys a fresh conversation")
        self.assertEqual(self.stage(), _corrected.RETIRED)
        self.assertEqual(self.pinned()[KEY_CONTINUED], 0)
        self.assertEqual(self.runs(), 2)
        self.assertEqual(self.label(), LABEL_READY)

    def _capped(self) -> None:
        """A rejected run that spent the last slot, its correction parked on the cap, and a quiet tick behind it."""
        self.opened()
        rejected = self.decomposer(_corrected.UNLISTED)
        self.tick(rejected)
        quiet = self.decomposer(_corrected.LISTED)
        self.tick(quiet)
        self.assertEqual(len(rejected.launches) + len(quiet.launches), 1)
        self.assertEqual(self.pinned()[KEY_PARK_REASON], support.PARK_RETRY_CAP)
        self.assertEqual(self.stage(), _corrected.PENDING)
        self.assertEqual(len(self.said()), 1, "the retry-cap park is said once")


if __name__ == "__main__":
    unittest.main()
