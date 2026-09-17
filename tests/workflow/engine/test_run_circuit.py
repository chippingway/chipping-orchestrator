# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The charge a launch takes at the boundary a process is invoked from.

Five promises are pinned here, each one something the lifetime ceiling above
this owner is worth nothing without: a charge that is durable before the
process exists, a crash window a later launch can recognize, a refusal that
invokes nothing at all, a caller whose own staged fields are not published by
somebody else's write, and a run whose ending -- exception, interruption, or
an ordinary exit -- never hands the charge back.
"""
from __future__ import annotations

import unittest

from tests.workflow.engine import (
    run_budget_test_support as budget,
    run_circuit_test_support as support,
)


class ChargedLaunchTest(unittest.TestCase):
    """What an ordinary launch pays, and when it has paid it."""

    def test_the_charge_is_durable_before_the_process(self) -> None:
        # Charged behind the spawn instead, a run that crashed, timed out, or
        # was killed mid-flight would be one the ledger never saw.
        launch = support.run_launch(support.seeded())

        self.assertEqual(launch.invocations, 1)
        observed = launch.observed[0]
        self.assertEqual(observed[support.USED], 1)
        self.assertEqual(observed[support.RESERVATION], support.STARTED)
        self.assertEqual(observed[support.FINGERPRINT], support.fingerprint())
        self._assert_the_two_phases_were_written_apart(launch)
        self._assert_the_caller_was_handed_the_charge(launch)

    def test_an_unlimited_ceiling_still_charges(self) -> None:
        # The setting decides what to do about the total, not whether runs
        # happened: a meter that paused under it would report an issue that
        # ran all day as having spent nothing once it came back on.
        launch = support.run_launch(
            support.seeded(**{support.USED: 99}), allowance=0,
        )

        self.assertEqual(launch.invocations, 1)
        self.assertEqual(launch.spent, 100)
        self.assertFalse(launch.durable.get(support.AWAITING_HUMAN))

    def _assert_the_two_phases_were_written_apart(self, launch) -> None:
        # The window between them is the only thing a later tick can tell a
        # launch that never ran from one that did by.
        self.assertEqual(
            launch.phases, [support.RESERVED, support.STARTED],
        )

    def _assert_the_caller_was_handed_the_charge(self, launch) -> None:
        # Without it the handler's own write at the end of the run would put
        # the count back the way its read found it, and the issue would have
        # paid for a run its ledger no longer records.
        self.assertEqual(launch.state.get(support.USED), 1)
        self.assertEqual(
            launch.state.get(support.RESERVATION), support.STARTED,
        )


class CrashWindowTest(unittest.TestCase):
    """Which standing charge a launch may run on, and which it may not."""

    def test_a_charge_this_launch_took_is_reused(self) -> None:
        # A tick that died between the two writes left a run charged and
        # never spawned; paying again would spend a lifetime on crashes.
        launch = support.run_launch(support.seeded(**{
            support.USED: 1,
            support.RESERVATION: support.RESERVED,
            support.FINGERPRINT: support.fingerprint(),
        }))

        self.assertEqual(launch.invocations, 1)
        self.assertEqual(launch.spent, 1)
        self.assertEqual(launch.phases, [support.STARTED])

    def test_a_start_marker_charges_a_new_attempt(self) -> None:
        # Past that marker a process may have run and nothing on the issue can
        # say it did not, so the next launch pays for itself.
        launch = support.run_launch(support.seeded(**{
            support.USED: 1,
            support.RESERVATION: support.STARTED,
            support.FINGERPRINT: support.fingerprint(),
        }))

        self.assertEqual(launch.spent, 2)
        self.assertEqual(
            launch.phases, [support.RESERVED, support.STARTED],
        )

    def test_another_launchs_charge_is_not_claimed(self) -> None:
        # A charge some other road recorded is one this launch never paid
        # for, and the ledger would stop recording what each run cost.
        launch = support.run_launch(support.seeded(**{
            support.USED: 1,
            support.RESERVATION: support.RESERVED,
            support.FINGERPRINT: support.OTHER_LAUNCH,
        }))

        self.assertEqual(launch.spent, 2)
        self.assertEqual(
            launch.durable[support.FINGERPRINT], support.fingerprint(),
        )

    def test_a_resumed_session_is_its_own_launch(self) -> None:
        # The fingerprint is what a request IS, so a resume of a session the
        # charge was never taken under does not inherit it.
        launch = support.run_launch(
            support.seeded(**{
                support.USED: 1,
                support.RESERVATION: support.RESERVED,
                support.FINGERPRINT: support.fingerprint(),
            }),
            resume_session_id="sess-earlier",
        )

        self.assertEqual(launch.spent, 2)


class RefusedLaunchTest(unittest.TestCase):
    """The three refusals, and the one process none of them invokes."""

    def test_a_spent_allowance_invokes_nothing(self) -> None:
        launch = support.run_launch(
            support.seeded(**{support.USED: 1}), allowance=1,
        )

        self.assertEqual(launch.invocations, 0)
        self.assertEqual(launch.spent, 1)
        self.assertEqual(launch.events(support.EVENT_AGENT_SPAWN), [])
        self.assertEqual(launch.events(support.EVENT_AGENT_EXIT), [])
        self._assert_it_reads_as_a_run_that_never_ran(launch)
        self._assert_it_parks_and_says_so(launch)

    def test_a_refused_charge_invokes_nothing(self) -> None:
        # A spawn the ledger would never see is exactly the run the ceiling
        # above exists to stop an issue repeating.
        launch = support.seeded()
        launch.gh.refuse_write()

        support.run_launch(launch)

        self.assertEqual(launch.invocations, 0)
        self.assertEqual(launch.durable, {})
        self.assertIsNone(launch.state.get(support.USED))

    def test_a_refused_start_keeps_the_charge(self) -> None:
        # The charge landed, so the caller carries it and the next launch of
        # the same request runs on it rather than paying twice.
        launch = support.seeded()
        launch.gh.refuse_write(after=1)

        support.run_launch(launch)

        self.assertEqual(launch.invocations, 0)
        self.assertEqual(launch.durable[support.RESERVATION], support.RESERVED)
        self.assertEqual(launch.state.get(support.USED), 1)

    def test_an_unusable_pinned_read_invokes_nothing(self) -> None:
        # A request that failed leaves no count to charge against, and a
        # comment that will not parse reads back as an issue that has spent
        # nothing -- charging on it would hand out a whole fresh lifetime.
        for refusal in ("unreadable", "unparsed"):
            with self.subTest(refusal=refusal):
                launch = support.seeded()
                setattr(launch.gh, refusal, True)

                support.run_launch(launch)

                self.assertEqual(launch.invocations, 0)
                self.assertEqual(launch.gh.writes, [])
                self.assertTrue(launch.answer.interrupted)

    def _assert_it_reads_as_a_run_that_never_ran(self, launch) -> None:
        # Interrupted, so every spawning handler returns without writing
        # durable state for it -- and never invoked, which is what the roads
        # that read the worktree ahead of that guard have to be able to tell:
        # a killed run may have written, and this one cannot have.
        self.assertFalse(launch.answer.invoked)
        self.assertTrue(launch.answer.interrupted)
        self.assertIsNone(launch.answer.session_id)
        self.assertEqual(
            launch.answer.exit_code, support.NO_PROCESS_EXIT_CODE,
        )
        self.assertFalse(launch.answer.timed_out)

    def _assert_it_parks_and_says_so(self, launch) -> None:
        # The park is durable before a word of it is said, and the caller
        # keeps it too -- a handler that writes anyway must not undo it.
        self.assertTrue(launch.durable[support.AWAITING_HUMAN])
        self.assertEqual(
            launch.durable[support.PARK_REASON],
            support.PARK_AGENT_RUN_LIMIT,
        )
        self.assertTrue(launch.state.get(support.AWAITING_HUMAN))
        self.assertTrue(launch.events(support.RUN_LIMIT_EVENT))


class ChargeRecordTest(unittest.TestCase):
    """What the budget stream is told, and which ticks tell it nothing.

    The record is tied to the write that makes a transition durable, so the
    stream counts what an issue actually spent rather than what a tick tried
    to spend on it.
    """

    def test_a_launch_records_charge_and_spawn(self) -> None:
        launch = support.run_launch(support.seeded())

        recorded = budget.audited(launch.gh)
        self.assertEqual(
            budget.phases(recorded), [budget.RESERVED, budget.STARTED],
        )
        for one in recorded:
            with self.subTest(phase=one[budget.PHASE]):
                self.assertEqual(one[budget.STAGE], support.STAGE)
                self.assertEqual(one[budget.AGENT_ROLE], support.ROLE)
                self.assertEqual(one[budget.USED], 1)
                self.assertEqual(
                    one[budget.REMAINING], support.ALLOWANCE - 1,
                )

    def test_a_reused_charge_records_the_start(self) -> None:
        # A tick that died between the two writes already reported the
        # reservation it took; the launch coming back pays for no new run, so
        # a second one would report a charge nothing was charged.
        launch = support.run_launch(support.seeded(**{
            support.USED: 1,
            support.RESERVATION: support.RESERVED,
            support.FINGERPRINT: support.fingerprint(),
        }))

        self.assertEqual(
            budget.phases(budget.audited(launch.gh)), [budget.STARTED],
        )

    def test_a_second_launch_is_a_second_reservation(self) -> None:
        # The fingerprint is stable across ticks so a standing charge can be
        # recognized and reused; the price of that is the SAME shape being
        # charged again once the launch it named has started. Two charges have
        # to stay two things a consumer can join separately.
        launch = support.relaunched(support.seeded())

        recorded = budget.audited(launch.gh)
        self.assertEqual(budget.phases(recorded), [
            budget.RESERVED, budget.STARTED, budget.RESERVED, budget.STARTED,
        ])
        charges = [
            {one[budget.RESERVATION_ID] for one in recorded[:2]},
            {one[budget.RESERVATION_ID] for one in recorded[2:]},
        ]
        # Each charge names itself the same from both of its phases, and no
        # two charges name themselves alike.
        self.assertEqual([len(named) for named in charges], [1, 1])
        self.assertNotEqual(charges[0], charges[1])

    def test_a_write_nobody_took_records_nothing(self) -> None:
        # Nothing about the issue changed, so there is no transition to
        # report -- and a record of one would be a run the ledger never saw.
        launch = support.seeded()
        launch.gh.refuse_write()

        support.run_launch(launch)

        self.assertEqual(budget.audited(launch.gh), [])

    def test_a_refused_start_records_the_charge(self) -> None:
        launch = support.seeded()
        launch.gh.refuse_write(after=1)

        support.run_launch(launch)

        self.assertEqual(
            budget.phases(budget.audited(launch.gh)), [budget.RESERVED],
        )

    def test_a_spent_ceiling_records_what_it_stopped(self) -> None:
        # The park says where the issue stopped; only this record says which
        # launch it stopped, which is what an operator needs to see whether a
        # ceiling is turning reviews away or first attempts.
        launch = support.run_launch(
            support.seeded(**{support.USED: 1}), allowance=1,
        )

        recorded = budget.audited(launch.gh)
        self.assertEqual(budget.phases(recorded), [budget.EXHAUSTED])
        self.assertEqual(recorded[0][budget.STAGE], support.STAGE)
        self.assertEqual(recorded[0][budget.AGENT_ROLE], support.ROLE)
        self.assertEqual(recorded[0][budget.REASON], budget.ALLOWANCE_SPENT)
        self.assertNotIn(budget.RESERVATION_ID, recorded[0])

    def test_a_park_already_standing_records_nothing(self) -> None:
        # An exhausted issue meets this refusal on every launch it has left,
        # so a record per meeting would report one ending as a stream of them.
        launch = support.run_launch(
            support.seeded(**{
                support.USED: 1,
                support.AWAITING_HUMAN: True,
                support.PARK_REASON: support.PARK_AGENT_RUN_LIMIT,
            }),
            allowance=1,
        )

        self.assertEqual(budget.audited(launch.gh), [])


class CallerStateTest(unittest.TestCase):
    """What the charge carries onto the caller's object, and what it leaves."""

    def test_a_staged_field_is_not_published(self) -> None:
        # A reviewer spec, a moved watermark, a session about to be replaced:
        # those belong to the handler's own write at the END of the run, which
        # is where it decides whether they are kept at all.
        launch = support.seeded()
        launch.state.set("review_agent", "codex:gpt-5")

        support.run_launch(launch)

        self.assertNotIn("review_agent", launch.durable)
        self.assertEqual(launch.state.get("review_agent"), "codex:gpt-5")
        self.assertEqual(launch.state.get(support.USED), 1)

    def test_only_the_charge_comes_back(self) -> None:
        # A durable field the caller never read is not this write's to hand
        # over: the caller's copy may hold a staged edit of the same field,
        # and the charge is not the write that decides it.
        launch = support.seeded(decomposer_agent="codex")
        launch.state.data.pop("decomposer_agent")

        support.run_launch(launch)

        self.assertNotIn("decomposer_agent", launch.state.data)
        self.assertEqual(launch.state.get(support.USED), 1)


class FinishedRunTest(unittest.TestCase):
    """Every ending a launched process can have keeps the run it spent."""

    def test_a_runner_exception_keeps_the_charge(self) -> None:
        # It propagates for the per-issue tick catch above to log, and the
        # charge is already durable because it was taken before the spawn.
        launch = support.seeded()

        with self.assertRaises(RuntimeError):
            support.run_launch(launch, outcome=RuntimeError("codex blew up"))

        self.assertEqual(launch.spent, 1)
        self.assertEqual(launch.durable[support.RESERVATION], support.STARTED)

    def test_a_killed_run_still_counts_as_invoked(self) -> None:
        # The shutdown sweep kills a process that existed and may have written
        # before it died, so what it left is read the way it always was.
        launch = support.run_launch(
            support.seeded(),
            outcome=support.agent_result(
                exit_code=support.INTERRUPTED_EXIT_CODE, interrupted=True,
            ),
        )

        self.assertTrue(launch.answer.invoked)

    def test_an_interrupted_run_keeps_the_charge(self) -> None:
        # The handler returns without writing pinned state, so the charge has
        # to be durable already or a shutdown kill would be a free run.
        launch = support.run_launch(
            support.seeded(),
            outcome=support.agent_result(
                exit_code=support.INTERRUPTED_EXIT_CODE,
                session_id=None,
                interrupted=True,
            ),
        )

        self.assertTrue(launch.answer.interrupted)
        self.assertEqual(launch.spent, 1)
        self.assertEqual(launch.durable[support.RESERVATION], support.STARTED)
