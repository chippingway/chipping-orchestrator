# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A correction's launch held to the issue as GitHub answers for it, and its daily retry paid once with its charge.

Asked of the dormant road's launch directly. A hold, a close, a relabel, an
edit, an issue GitHub would not answer for, a session pinned in place of the
saved one, or a comment moved under the tick invokes nothing: ahead of the
charge nothing is charged, and behind it the charge -- with the daily retry
that landed in its own write -- stands reserved for the same launch, which a
later ask starts without paying either again, in the same daily window or
the next. The charge's and the start's edits each ask the issue and the
comment once more immediately before they leave, so a hold landing during the
editor's own walk to the comment invokes nothing either, and a session pinned
while any check around the charge is out is never written back over. A spent
daily budget takes its retry-cap park instead, but only for an attempt the
comment still grants its launch, and only over the comment the tick read and
an issue still standing: one already started or resolved asks no retry at all,
a session pinned meanwhile or a hold during the park's edit is neither parked
over nor announced, and a park cleared or held while its notice reads the
thread is said to nobody. A recorded attempt whose saved session reads as an
option is never launched.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_records as _records,
)
from tests.workflow.stages.decomposition import (
    correction_launch_support as launch_support,
    correction_test_support as support,
)

_MEANWHILE = launch_support.Meanwhile
_RETRIES = launch_support.RETRIES
_WINDOW = "retry_window_start"

# What the correction's charge leaves counted: one run past its source, and two
# retries in a window that had counted one.
_CHARGED = support.SOURCE + 1
_PAID = 2

# A session a human pins in place of the saved one.
_REPINNED = "dec-by-hand"
_REPIN = partial(_MEANWHILE.rewrites, **{support.SESSION_PIN: _REPINNED})

# The issue fetches a launch's checks around its charge make.
_AROUND_THE_CHARGE = (
    launch_support.ON_THE_CHARGE,
    launch_support.AT_THE_CHARGE,
    launch_support.BEHIND_THE_CHARGE,
    launch_support.BEFORE_THE_START,
    launch_support.AT_THE_START,
)

# Moves landing ahead of the charge, by the issue fetch they land before -- or
# None, landed on the comment before the launch is asked, under the caller's reading.
_AHEAD = (
    ("a hold", _MEANWHILE.hold, 1),
    ("a close", _MEANWHILE.close, 1),
    ("a relabel", _MEANWHILE.relabel, 1),
    ("an edit", _MEANWHILE.edit, 1),
    ("an unread issue", _MEANWHILE.unreadable, 1),
    ("a session pinned meanwhile", _REPIN, 1),
    ("a hold at the charge's edit", _MEANWHILE.hold, launch_support.AT_THE_CHARGE),
    ("a comment moved under the tick", partial(_MEANWHILE.rewrites, operator_note="moved"), None),
)

# Moves landing behind the charge -- right behind it, or on the reading its start is written over.
_BEHIND = tuple(
    (f"{name} {place}", move, nth)
    for place, nth in (
        ("behind the charge", launch_support.BEHIND_THE_CHARGE),
        ("before the start", launch_support.BEFORE_THE_START),
        ("at the start's edit", launch_support.AT_THE_START),
    )
    for name, move in (
        ("a hold", _MEANWHILE.hold),
        ("an edit", _MEANWHILE.edit),
        ("a close", _MEANWHILE.close),
        ("an unread issue", _MEANWHILE.unreadable),
    )
)

# The strict editor's walks a launch makes -- ahead of the charge's edit and
# ahead of the start's -- beside the run count and reservation phase a hold
# landing during each leaves: nothing charged, or the charge kept reserved.
_WALKS = ((1, (support.SOURCE, "started")), (2, (_CHARGED, "reserved")))

# Moves landing ahead of a spent budget's park -- a session pinned while the
# issue is read, and a hold while the park's edit walks to the comment -- by
# the request they land on, beside the session they leave pinned.
_AHEAD_OF_THE_PARK = (
    ("a session pinned", launch_support.OnFetch.patch, 2, _REPIN, _REPINNED),
    ("a hold during the park's walk", launch_support.OnWalk.patch, 1, _MEANWHILE.hold, support.SESSION),
)

# Moves landing behind the landed park's notice read of its thread, beside the
# park reason and the session they leave.
_CLEARED = partial(
    _MEANWHILE.rewrites,
    awaiting_human=False,
    park_reason=None,
    retry_cap_notice=None,
    **{support.SESSION_PIN: _REPINNED},
)
_BEHIND_THE_PARK = (
    ("a hold", _MEANWHILE.hold, ("retry_cap", support.SESSION)),
    ("the park cleared and a session pinned", _CLEARED, (None, _REPINNED)),
    ("the comment replaced", launch_support.replaced, ("retry_cap", support.SESSION)),
)
_ON_THE_THREAD = partial(launch_support.OnFetch.patch, seam="comments_after")

# A saved session an option parser would take for a flag.
_UNSAFE = "--last"

# The park a spent budget takes, and the fields it is read back by beside the session.
_PARK = "park_reason"
_PARKED = (_PARK, support.SESSION_PIN)

# The lifetime ceiling the seeded source's charge spends, the park a launch
# refused on it takes, and moves landing around that park -- a session pinned
# during the check on the reading the charge is decided on, a hold while the
# park's edit walks to the comment, and a session pinned once the park landed,
# while its notice reads the thread -- beside the park and session they leave.
_LIFETIME = support.SOURCE
_LIMIT_PARK = "agent_run_limit"
_LIMIT_NOTICE_READ = 4
_AROUND_THE_LIMIT = (
    ("a session pinned", launch_support.OnFetch.patch, launch_support.ON_THE_CHARGE, _REPIN, (None, _REPINNED)),
    ("a hold during the park's walk", launch_support.OnWalk.patch, 1, _MEANWHILE.hold, (None, support.SESSION)),
    ("a session pinned behind the park", _ON_THE_THREAD, _LIMIT_NOTICE_READ, _REPIN, (_LIMIT_PARK, _REPINNED)),
)

# The ledger fields a launch charges.
_LEDGER = (support.USED, support.RESERVATION, support.OWED_STARTED, _RETRIES)


def _armed(**record) -> support.CorrectionWorld:
    """A world whose rejected run's attempt is armed, one retry counted in a window open now, read afresh."""
    window = {_WINDOW: launch_support.opened(0), _RETRIES: 1}
    world = support.seeded(**{**window, **record})
    world.arms()
    return world.restarted()


def _asked(world: support.CorrectionWorld, move, nth: int | None) -> tuple[launch_support.Runner, tuple]:
    """The launch asked over `world`, `move` landing before its `nth` issue fetch, or before it is asked.

    Answered with the runner and the ledger fields the comment carried before the launch was asked.
    """
    runner = launch_support.Runner(world)
    before = _ledger(world)
    if nth is None:
        move(_MEANWHILE(world))
        runner.launch()
        return runner, before
    with launch_support.OnFetch.patch(world, nth, move):
        runner.launch()
    return runner, before


def _ledger(world: support.CorrectionWorld, fields: tuple = _LEDGER) -> tuple:
    """What the comment's `fields` -- its ledger's unless named -- read as now."""
    return tuple(world.record().get(field) for field in fields)


def _spent(world: support.CorrectionWorld, patches, nth: int, move, limit: int = 0) -> list:
    """The launch asked over `world` under `limit`, `move` landing on the `nth` request `patches` counts.

    Answered with the processes invoked.
    """
    runner = launch_support.Runner(world, limit)
    with patches(world, nth, move):
        runner.launch()
    return runner.launches


class LaunchHoldTest(unittest.TestCase):
    """What lands around the launch's charge invokes nothing."""

    def test_a_move_ahead_charges_nothing(self) -> None:
        for name, *move in _AHEAD:
            with self.subTest(name):
                world = _armed()

                runner, before = _asked(world, *move)

                self.assertEqual(runner.launches, [])
                self.assertEqual(_ledger(world), before)
                self.assertEqual(world.reads().attempt, support.attempt(world), "the attempt stands as armed")

    def test_a_move_behind_keeps_the_charge(self) -> None:
        for name, *move in _BEHIND:
            with self.subTest(name):
                world = _armed()

                runner = _asked(world, *move)[0]

                reserved = world.record()
                self.assertEqual(runner.launches, [])
                self.assertEqual(reserved[support.RESERVATION], "reserved")
                self.assertEqual(reserved[support.USED], _CHARGED)
                self.assertEqual(reserved[_RETRIES], _PAID, "the daily retry landed in the reservation's write")
                self.assertNotIn(support.OWED_STARTED, reserved)

    def test_a_hold_during_the_walk_invokes_nothing(self) -> None:
        # A pause landing while the strict editor walks to the comment ahead
        # of the charge's or the start's edit is met by the question that
        # edit asks immediately before it leaves: nothing is sent, and no
        # process is invoked.
        for nth, ledger in _WALKS:
            with self.subTest(walk=nth):
                world = _armed()
                runner = launch_support.Runner(world)

                with launch_support.OnWalk.patch(world, nth, _MEANWHILE.hold):
                    runner.launch()

                self.assertEqual(runner.launches, [])
                self.assertEqual(_ledger(world)[:2], ledger)

    def test_an_unsafe_session_launches_nothing(self) -> None:
        # A recorded attempt whose saved session reads as an option -- a
        # record and its pin edited by hand -- is never launched: nothing is
        # charged, and no other conversation is resumed in its place.
        world = support.seeded(**{support.SESSION_PIN: _UNSAFE})
        unsafe = support.source(world, session=_UNSAFE)
        world.arms(unsafe)
        runner = launch_support.Runner(world.restarted())
        before = _ledger(world)

        runner.launch(_records.CorrectionAttempt(unsafe))

        self.assertEqual(runner.launches, [])
        self.assertEqual(_ledger(world), before)

    def test_a_replaced_comment_invokes_nothing(self) -> None:
        # A human posts the record, the same payload, as a new pinned comment
        # while the charge's or the start's edit is out: the comment read
        # again before the edit leaves is no longer the one it was decided
        # on, so nothing is sent or invoked and the caller is withheld.
        for nth in (launch_support.AT_THE_CHARGE, launch_support.AT_THE_START):
            with self.subTest(fetch=nth):
                world = _armed()

                runner = _asked(world, launch_support.replaced, nth)[0]

                self.assertEqual(runner.launches, [])
                self.assertTrue(world.state.withheld)

    def test_a_session_pinned_meanwhile_is_kept(self) -> None:
        # A human pins another session while a check of the issue around the
        # charge is out: the charge and the start land only over the readings
        # they were decided on, so the pin is never written back over and the
        # conversation it replaced is never resumed.
        for nth in _AROUND_THE_CHARGE:
            with self.subTest(fetch=nth):
                world = _armed()

                runner = _asked(world, _REPIN, nth)[0]

                self.assertEqual(runner.launches, [])
                self.assertEqual(world.record()[support.SESSION_PIN], _REPINNED)


class LaunchBudgetTest(unittest.TestCase):
    """The launch's daily retry is paid once, with its charge, and a spent budget parks it."""

    def test_a_reserved_launch_is_paid_once(self) -> None:
        # A hold behind the charge leaves it reserved; once lifted, the same
        # launch starts on that charge in the same window or the next, with
        # neither the charge nor the daily retry paid again -- a retry paid
        # in the next window would count one there, not the two counted.
        for name, rolled in (("the same window", 0), ("the next window", 2)):
            with self.subTest(name):
                world = _armed()
                _asked(world, _MEANWHILE.hold, launch_support.BEHIND_THE_CHARGE)
                _MEANWHILE(world).lift()
                world.moves(**{_WINDOW: launch_support.opened(rolled)})

                later = launch_support.Runner(world.restarted())
                later.launch()

                self.assertEqual(len(later.launches), 1)
                self.assertEqual(_ledger(world), (_CHARGED, "started", support.SOURCE, _PAID))
                self.assertEqual(later.world.state.get(_RETRIES), _PAID, "nor staged for the caller's write")

    def test_a_spent_budget_parks_on_the_retry_cap(self) -> None:
        world = _armed(**{_RETRIES: launch_support.DAILY})
        runner = launch_support.Runner(world)

        launched = runner.launch()

        self.assertIsNone(launched)
        self.assertEqual(runner.launches, [])
        self.assertEqual(world.record()[_PARK], "retry_cap")
        self.assertEqual(world.record()[support.USED], support.SOURCE, "nothing charged")
        self.assertEqual(len(world.github.posted_comments), 1, "said once")

    def test_nothing_parks_over_a_move(self) -> None:
        # The park is written only over the comment the tick read and only
        # while the issue stands as its edit leaves: a pin moved, or a hold
        # during its walk, leaves nothing parked or said.
        for name, *moved, session in _AHEAD_OF_THE_PARK:
            with self.subTest(name):
                world = _armed(**{_RETRIES: launch_support.DAILY})

                launches = _spent(world, *moved)

                self.assertEqual(launches, [])
                self.assertIsNone(world.record().get(_PARK))
                self.assertEqual(world.record()[support.SESSION_PIN], session)
                self.assertEqual(len(world.github.posted_comments), 0)
                self.assertTrue(world.state.withheld)

    def test_nothing_is_said_behind_a_move(self) -> None:
        # The park landed, and its notice reads the thread: it is posted only
        # where the issue and then the comment still stand, so a hold leaves
        # the notice owed, and a park a human cleared, beside the session
        # they pinned, is kept and announced to nobody.
        for name, move, left in _BEHIND_THE_PARK:
            with self.subTest(name):
                world = _armed(**{_RETRIES: launch_support.DAILY})

                _spent(world, _ON_THE_THREAD, launch_support.THE_NOTICE_READ, move)

                self.assertEqual(_ledger(world, _PARKED), left)
                self.assertEqual(len(world.github.posted_comments), 0)

    def test_an_unowed_attempt_asks_no_retry(self) -> None:
        # The day's budget spent by the launch already made, or over an
        # attempt already resolved: the comment grants no launch, so the
        # budget is never asked and no retry-cap park is written or said.
        for name, spent in (("a started attempt", self._started), ("a resolved attempt", self._resolved)):
            with self.subTest(name):
                world = spent()
                before = world.snapshot()[:2]
                again = launch_support.Runner(world)

                again.launch()

                self.assertEqual(again.launches, [])
                self.assertEqual(world.snapshot()[:2], before, "nothing written")
                self.assertIsNone(world.record().get(_PARK))
                self.assertEqual(len(world.github.posted_comments), 0)

    def _started(self) -> support.CorrectionWorld:
        """A world whose attempt's launch already ran on the day's last retry, read afresh."""
        world = _armed(**{_RETRIES: launch_support.DAILY - 1})
        first = launch_support.Runner(world)
        first.launch()
        self.assertEqual(len(first.launches), 1)
        return world.restarted()

    def _resolved(self) -> support.CorrectionWorld:
        """A world whose attempt was exhausted with the day's budget spent, read afresh."""
        world = _armed(**{_RETRIES: launch_support.DAILY})
        world.asks(_checkpoint.exhaust, support.attempt(world))
        return world.restarted()


class LifetimeLimitTest(unittest.TestCase):
    """A launch a spent lifetime ledger refuses parks on `agent_run_limit`, only over the reading it was refused on."""

    def test_a_spent_ledger_parks_once(self) -> None:
        world = _armed()
        runner = launch_support.Runner(world, _LIFETIME)

        runner.launch()

        self.assertEqual(runner.launches, [])
        self.assertEqual(_ledger(world, _PARKED), (_LIMIT_PARK, support.SESSION))
        self.assertEqual(world.record()[support.USED], support.SOURCE, "nothing charged")
        self.assertEqual(len(world.github.posted_comments), 1, "said once")

    def test_nothing_is_said_over_a_move(self) -> None:
        # The park is held to the reading the charge was refused on, as the
        # charge would have been: a session pinned while the issue was asked
        # behind that reading, or a hold during the park's own walk to the
        # comment, parks nothing, and one pinned once the park landed is
        # announced to nobody -- the pin kept as it stands, the caller withheld.
        for name, *moved, left in _AROUND_THE_LIMIT:
            with self.subTest(name):
                world = _armed()

                launches = _spent(world, *moved, limit=_LIFETIME)

                self.assertEqual(launches, [])
                self.assertEqual(_ledger(world, _PARKED), left)
                self.assertEqual(len(world.github.posted_comments), 0)
                self.assertTrue(world.state.withheld)


if __name__ == "__main__":
    unittest.main()
