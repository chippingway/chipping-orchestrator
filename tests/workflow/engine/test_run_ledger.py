# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The lifetime agent-run ledger: what an issue is allowed, and what it spent.

Four promises are pinned here, each one something a reader of the ledger is
written on: a count that starts from the legacy meter rather than from zero
and never reads below it, a count that only ever goes up -- including while
the ceiling is off -- an allowance the issue's own record governs where it
carries one, and a reservation whose two phases survive the trip through a
pinned comment as the wire strings live issues carry.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.github.pinned_state import (
    PinnedState,
    pinned_state_body,
    pinned_state_from_comment,
)
from orchestrator.workflow.engine import run_ledger as _run_ledger
from tests.support.fakes import FakeComment, FakeUser

_CONFIGURED = 50

_ISSUE_NUMBER = 1540

_BOT_LOGIN = "orchestrator"

_LEGACY_RUNS = "issue_agent_runs"

_ALLOWANCE = _run_ledger.AGENT_RUN_ALLOWANCE

_USED = _run_ledger.AGENT_RUNS_USED

_RESERVATION = _run_ledger.AGENT_RUN_RESERVATION

_FINGERPRINT = _run_ledger.AGENT_RUN_FINGERPRINT

_RESERVED = _run_ledger.RunPhase.RESERVED

_STARTED = _run_ledger.RunPhase.STARTED

# What one issue has already spent when a case starts, and what the charge
# under test makes of it.
_SPENT = 6

_CHARGED = 7

# The launch a charge is taken for, and one that is not it.
_LAUNCH = "a3f1"

_OTHER_LAUNCH = "b7c2"

# A count each meter carries when the two disagree.
_AHEAD = 9

_BEHIND = 4

# A ceiling narrower than what the issue has already spent, so the remainder
# under it has to floor rather than go negative.
_NARROW = 3

_OVERSPENT = 8

# What a hand edit, an older binary, or a truncated write can leave in a field
# this owner reads as a number. `True` is in the list because it is an `int`
# in this language, and reading it as one would count a run nobody ran.
_UNREADABLE_COUNTS = (True, -1, 2.5, "7", None, [3])

# The same, for the field naming a phase: a spelling no binary wrote, one a
# newer one might, and four that are not phases at all -- the unhashable one
# among them because an enum lookup is a mapping read before it is anything
# else, and a list there must read as no phase rather than raise.
_UNREADABLE_PHASES = ("", "running", 3, None, True, ["reserved"])

# The same, for the field naming which launch holds a charge: only a non-empty
# string names one, and everything else leaves a charge nothing can match.
_UNREADABLE_LAUNCHES = ("", 7, None, ["a3f1"])


def _state(**fields) -> PinnedState:
    return PinnedState(comment_id=1, data=dict(fields))


def _read(state: PinnedState, *, configured: int = _CONFIGURED):
    """One ledger read under a pinned setting, so no env override reaches it."""
    with patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", configured):
        return _run_ledger._read_ledger(state)


def _reserve(
    state: PinnedState,
    *,
    configured: int = _CONFIGURED,
    fingerprint: str = _LAUNCH,
):
    with patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", configured):
        return _run_ledger._reserve_run(state, fingerprint)


class LegacyMeterTest(unittest.TestCase):
    """An issue that predates the ledger keeps what it has already spent."""

    def test_a_missing_count_seeds_from_legacy(self) -> None:
        # Started at zero instead, an in-flight issue would be handed a whole
        # fresh lifetime by the arrival of the ledger that bounds it.
        ledger = _read(_state(**{_LEGACY_RUNS: _SPENT}))

        self.assertEqual(ledger.used, _SPENT)
        self.assertEqual(ledger.remaining, _CONFIGURED - _SPENT)

    def test_the_legacy_meter_is_a_floor(self) -> None:
        # Both meters count real agent runs on this issue, so the larger is
        # the one that loses none -- whichever of the two wrote last.
        ledger = _read(_state(**{_USED: _BEHIND, _LEGACY_RUNS: _AHEAD}))

        self.assertEqual(ledger.used, _AHEAD)

    def test_the_own_count_wins_where_ahead(self) -> None:
        # It charges the launch rather than the parsed exit, so it holds the
        # runs whose usage never parsed and the legacy meter never saw.
        ledger = _read(_state(**{_USED: _AHEAD, _LEGACY_RUNS: _BEHIND}))

        self.assertEqual(ledger.used, _AHEAD)

    def test_a_charge_leaves_the_legacy_alone(self) -> None:
        # The legacy meter has its own writer and its own receipt to render;
        # the ledger reads it and never writes it.
        state = _state(**{_LEGACY_RUNS: _SPENT})

        ledger = _reserve(state)

        self.assertEqual(state.get(_USED), _CHARGED)
        self.assertEqual(state.get(_LEGACY_RUNS), _SPENT)
        self.assertEqual(ledger.used, _CHARGED)

    def test_a_damaged_meter_counts_nothing(self) -> None:
        # A count nothing can read must not strand an issue behind a crash on
        # every poll, and the meter beside it still answers.
        for damaged in _UNREADABLE_COUNTS:
            with self.subTest(damaged=damaged):
                ledger = _read(_state(**{
                    _USED: damaged, _LEGACY_RUNS: _BEHIND,
                }))

                self.assertEqual(ledger.used, _BEHIND)

    def test_neither_meter_is_no_spend(self) -> None:
        ledger = _read(_state())

        self.assertEqual(ledger.used, 0)
        self.assertEqual(ledger.remaining, _CONFIGURED)


class AllowanceTest(unittest.TestCase):
    """Which ceiling an issue is held to, and what is left under it."""

    def test_no_allowance_uses_the_setting(self) -> None:
        ledger = _read(_state())

        self.assertEqual(ledger.configured, _CONFIGURED)
        self.assertEqual(ledger.allowance, _CONFIGURED)
        self.assertFalse(ledger.unlimited)

    def test_the_issues_own_allowance_governs(self) -> None:
        # A per-issue allowance is a decision somebody took about this issue;
        # re-reading the global where it is spent would make that decision
        # worth whatever the global had become since.
        ledger = _read(_state(**{_ALLOWANCE: _NARROW}))

        self.assertEqual(ledger.configured, _CONFIGURED)
        self.assertEqual(ledger.allowance, _NARROW)

    def test_a_damaged_allowance_uses_the_setting(self) -> None:
        for damaged in _UNREADABLE_COUNTS:
            with self.subTest(damaged=damaged):
                ledger = _read(_state(**{_ALLOWANCE: damaged}))

                self.assertEqual(ledger.allowance, _CONFIGURED)

    def test_the_remainder_floors_at_nothing(self) -> None:
        # A count past the allowance is an ordinary reading -- runs spent
        # under a wider ceiling, or under none -- and what is left is nothing.
        ledger = _read(_state(**{
            _ALLOWANCE: _NARROW, _USED: _OVERSPENT,
        }))

        self.assertEqual(ledger.remaining, 0)

    def test_unlimited_reports_no_remainder(self) -> None:
        # The issue's own recorded `0` and the setting's say the same thing --
        # same unit, both places -- and a ceiling there is none of has no
        # remainder a reader could compare against zero and refuse on.
        readings = (
            (_state(**{_ALLOWANCE: 0}), _CONFIGURED),
            (_state(**{_USED: _OVERSPENT}), 0),
        )
        for state, configured in readings:
            with self.subTest(configured=configured):
                ledger = _read(state, configured=configured)

                self.assertTrue(ledger.unlimited)
                self.assertIsNone(ledger.remaining)

    def test_what_a_spent_allowance_reads_as(self) -> None:
        # The one question a reader about to spend a run asks, and the one
        # answer an unlimited ceiling never gives however much it has run.
        cases = (
            (_CONFIGURED, _SPENT, False),
            (_CONFIGURED, _CONFIGURED, True),
            (_NARROW, _OVERSPENT, True),
            (0, _OVERSPENT, False),
        )
        for allowance, used, expected in cases:
            with self.subTest(allowance=allowance, used=used):
                state = _state(**{_ALLOWANCE: allowance, _USED: used})

                self.assertIs(_read(state).spent, expected)

    def test_a_wider_ceiling_returns_no_spend(self) -> None:
        # Widening the setting hands back allowance, never spend: the runs are
        # still counted, and only the remainder under them moves.
        widened = _read(_state(**{_USED: _OVERSPENT}), configured=_AHEAD)

        self.assertEqual(widened.used, _OVERSPENT)
        self.assertEqual(widened.remaining, _AHEAD - _OVERSPENT)


class ChargeTest(unittest.TestCase):
    """What one charge does: it goes up, it names its launch, it stays put."""

    def test_an_unlimited_ceiling_keeps_counting(self) -> None:
        # Unlimited means nothing turns a run away; it does not mean the runs
        # stopped, and a meter that paused would report every issue that ran
        # while it was off as having spent nothing once it came back on.
        state = _state()

        _reserve(state, configured=0)
        _run_ledger._settle_run(state)
        _reserve(state, configured=0)

        self.assertEqual(state.get(_USED), 2)

    def test_settling_keeps_the_charge(self) -> None:
        state = _state()
        _reserve(state)

        _run_ledger._settle_run(state)

        self.assertEqual(state.get(_USED), 1)
        self.assertNotIn(_RESERVATION, state.data)
        self.assertNotIn(_FINGERPRINT, state.data)

    def test_a_charge_records_its_launch(self) -> None:
        # Charged ahead of the spawn, so a run that crashed, timed out, or was
        # killed mid-flight is still a run this issue spent.
        state = _state()

        ledger = _reserve(state)

        self.assertEqual(ledger.reservation, _RESERVED)
        self.assertEqual(ledger.used, 1)
        self.assertEqual(ledger.fingerprint, _LAUNCH)
        self.assertTrue(ledger.pending_for(_LAUNCH))

    def test_only_the_launch_that_paid_reuses_it(self) -> None:
        # A charge another road recorded is one this launch never paid for,
        # and spending it would leave the ledger claiming a run it did not buy.
        ledger = _reserve(_state())

        self.assertFalse(ledger.pending_for(_OTHER_LAUNCH))

    def test_a_started_charge_is_no_longer_pending(self) -> None:
        # Past the start marker a process may have run, and nothing on the
        # issue can say it did not -- so the charge is spent, not standing.
        state = _state()
        _reserve(state)
        _run_ledger._start_reserved_run(state)

        self.assertFalse(_read(state).pending_for(_LAUNCH))

    def test_a_reservation_moves_to_started(self) -> None:
        state = _state()
        _reserve(state)

        self.assertTrue(_run_ledger._start_reserved_run(state))
        self.assertEqual(_read(state).reservation, _STARTED)

    def test_a_start_with_no_charge_refuses(self) -> None:
        # The charge is what a reservation stands for, so one minted at the
        # spawn would be a launch nothing paid for.
        state = _state()

        self.assertFalse(_run_ledger._start_reserved_run(state))
        self.assertEqual(state.data, {})


class WireContractTest(unittest.TestCase):
    """The names and values live issues already carry."""

    def test_an_unknown_phase_is_no_launch(self) -> None:
        # A phase a newer binary wrote, or a hand edit: a reader must not act
        # on a claim about a launch it cannot interpret.
        for damaged in _UNREADABLE_PHASES:
            with self.subTest(damaged=damaged):
                state = _state(**{_RESERVATION: damaged})

                self.assertIsNone(_read(state).reservation)
                self.assertFalse(_run_ledger._start_reserved_run(state))

    def test_an_unreadable_launch_is_no_launch(self) -> None:
        # A hand edit or an older binary leaves a charge nothing can match, so
        # the next launch pays for itself rather than claiming it.
        for damaged in _UNREADABLE_LAUNCHES:
            with self.subTest(damaged=damaged):
                state = _state(**{
                    _RESERVATION: _RESERVED, _FINGERPRINT: damaged,
                })

                ledger = _read(state)

                self.assertIsNone(ledger.fingerprint)
                self.assertFalse(ledger.pending_for(_LAUNCH))

    def test_the_field_and_phase_spellings(self) -> None:
        self.assertEqual(
            (_ALLOWANCE, _USED, _RESERVATION, _FINGERPRINT),
            (
                "agent_run_allowance",
                "agent_runs_used",
                "agent_run_reservation",
                "agent_run_fingerprint",
            ),
        )
        self.assertEqual(
            [phase.value for phase in _run_ledger.RunPhase],
            ["reserved", "started"],
        )

    def test_the_projected_group_is_two_facts(self) -> None:
        # What a projection keeps is what is true about the ISSUE. The launch
        # is not: a projection rebuilds an issue that has none.
        self.assertEqual(_run_ledger.PROJECTED_KEYS, (_ALLOWANCE, _USED))

    def test_a_ledger_round_trips_on_the_wire(self) -> None:
        # The whole ledger goes out as JSON and comes back as the same
        # snapshot, so nothing it writes depends on the in-memory object that
        # wrote it -- which is every tick after the one that charged the run.
        written = _state(**{_ALLOWANCE: _AHEAD})
        charged = _reserve(written)
        _run_ledger._start_reserved_run(written)

        restored = _read(self._reparsed(written))

        self.assertEqual(restored.allowance, charged.allowance)
        self.assertEqual(restored.used, charged.used)
        self.assertEqual(restored.reservation, _STARTED)
        self.assertEqual(restored.fingerprint, _LAUNCH)
        self.assertEqual(restored.remaining, _AHEAD - 1)

    def test_a_phase_is_written_as_its_string(self) -> None:
        state = _state()
        _reserve(state)

        body = pinned_state_body(state.data)

        self.assertIn('"agent_run_reservation": "reserved"', body)

    def _reparsed(self, state: PinnedState) -> PinnedState:
        comment = FakeComment(
            id=state.comment_id,
            body=pinned_state_body(state.data),
            user=FakeUser(_BOT_LOGIN),
        )
        return pinned_state_from_comment(
            comment, trusted_login=_BOT_LOGIN, issue_number=_ISSUE_NUMBER,
        )


if __name__ == "__main__":
    unittest.main()
