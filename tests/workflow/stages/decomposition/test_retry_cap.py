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
from tests.workflow.fixtures import LABEL_READY, _agent, _iso_hours_ago
from tests.workflow.stages.decomposition import retry_cap_support as support

CONTINUE_COMMAND = support.CONTINUE_COMMAND
ISSUE_NUMBER = support.ISSUE_NUMBER
KEY_AWAITING_HUMAN = support.KEY_AWAITING_HUMAN
KEY_CONTINUED = support.KEY_CONTINUED
KEY_PARK_REASON = support.KEY_PARK_REASON
KEY_RETRY_CAP_NOTICE = support.KEY_RETRY_CAP_NOTICE
KEY_RETRY_CAP_STAGE = support.KEY_RETRY_CAP_STAGE
RUN_AGENT = support.RUN_AGENT

HELD_TICKS = 3

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
        self.assertIsNone(
            mocks[RUN_AGENT].call_args.kwargs.get("resume_session_id"),
        )
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


if __name__ == "__main__":
    unittest.main()
