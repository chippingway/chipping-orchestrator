# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resolving a decomposer manifest correction: exhausted once spent, retired only on evidence, never armed again.

A correction's own rejected answer exhausts the attempt it was bought by, and
no invocation the exhausted attempt covers -- the correction's, the source's,
any charged before it resolved -- arms another, however often it is offered;
a later rejected run charged above it earns its own. A start nobody can
account for is exhausted with no correction named. Retirement takes evidence
that the context moved, held to that evidence through its commit, and a
reading nobody can read proves nothing. Every resolution keeps the counters,
pins, and fields beside it as the comment carries them, and asking again sends
nothing.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.engine.pinned_commit_models import CommitRefusal
from orchestrator.workflow.engine.report_record_values import MAX_RECORDED_NUMBER
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_records as _records,
    correction_standing as _standing,
)
from tests.workflow.stages.decomposition import correction_test_support as support

_STATUS = support.STATUS
_REFUSAL = support.REFUSAL
_STAGE = support.STAGE
_STANDING = support.STANDING
_READING = _standing.CorrectionReading
_CORRECTED = support.SOURCE + 1
_LATER_RUN = support.SOURCE + 2

# What the run circuit's start of the attempt's launch and that run's
# accounting leave on the ledger.
_STARTED = MappingProxyType({
    support.OWED_STARTED: support.SOURCE,
    support.USED: _CORRECTED,
    support.METERED: _CORRECTED,
})

# Run ledgers no floor can be read off, each laid over a started launch: a
# charge count that reads as none, and a usage meter beside it that does; a
# count below the charge the owed start records, or below one a usage receipt
# covers; and an owed start that reads as no count.
_UNCOUNTED = (
    MappingProxyType({support.USED: "unreadable"}),
    MappingProxyType({support.USED: None}),
    MappingProxyType({support.METERED: "four"}),
    MappingProxyType({support.USED: support.SOURCE, support.METERED: support.SOURCE}),
    MappingProxyType({
        support.OWED_STARTED: support.SOURCE - 1,
        support.USED: support.SOURCE,
        support.METERED: support.SOURCE,
        support.RECEIPTS: {"floor": support.SOURCE, "recent": [[_CORRECTED, "0000000000000005"]]},
    }),
    MappingProxyType({support.OWED_STARTED: None}),
)

# A run count past what a record holds, beside evidence that retires the attempt.

_PAST_CEILING = MappingProxyType({support.USED: MAX_RECORDED_NUMBER + 1, support.BASELINE: support.EDITED})

# Readings that prove the context an attempt was armed under moved.
_EVIDENCE = (
    {support.BASELINE: support.EDITED},
    {support.SESSION_PIN: None},
    {support.COMMAND_PIN: "claude"},
)

# Readings that prove nothing: the context standing, or nothing readable in its place.
_NO_EVIDENCE = (
    {},
    {support.BASELINE: "not a digest"},
    {support.BASELINE: None},
    {support.SESSION_PIN: 7},
    {support.SESSION_PIN: "decomposer\nsession"},
    {support.COMMAND_PIN: ""},
)


def _armed(**fields) -> support.CorrectionWorld:
    """A world whose rejected run's attempt is armed, with `fields` landed behind it by another road."""
    world = support.seeded()
    world.arms()
    if fields:
        world.moves(**fields)
    return world.restarted()


def _corrected(world: support.CorrectionWorld) -> None:
    """The attempt's launch starts at its owed count and is accounted, as the circuit and the checkpoint leave it."""
    world.moves(**_STARTED)
    world.state = world.restarted().state


def _exhausts(world: support.CorrectionWorld, ordinal: int | None = None):
    """Ask for the seeded attempt to be exhausted, naming the correction charged at `ordinal` where one is."""
    correction = None if ordinal is None else support.invocation(world, ordinal)
    return world.asks(_checkpoint.exhaust, support.attempt(world), correction)


def _retires(world: support.CorrectionWorld):
    """Ask for the seeded attempt to be retired."""
    return world.asks(_checkpoint.retire, support.attempt(world))


def _resolved(world: support.CorrectionWorld, stage: _STAGE, floor: int, ordinal: int | None = None):
    """The seeded attempt resolved at `stage` under `floor`, naming the correction charged at `ordinal` where one is."""
    correction = None if ordinal is None else support.invocation(world, ordinal)
    return support.attempt(world).resolved(stage, floor, correction)


class ExhaustionTest(unittest.TestCase):
    """A spent attempt covers every charge it was spent across."""

    def test_a_rejected_correction_exhausts_the_chain(self) -> None:
        world = _armed()
        _corrected(world)
        before = world.record()

        outcome = _exhausts(world, _CORRECTED)

        exhausted = _resolved(world, _STAGE.EXHAUSTED, _CORRECTED, _CORRECTED)
        self.assertEqual(outcome.status, _STATUS.LANDED)
        self.assertEqual(outcome.reading, _READING(_STANDING.EXHAUSTED, exhausted))
        self.assertEqual(world.record(), {**before, support.FIELD: exhausted.spelled()})
        own = world.restarted().arms(support.source(world, _CORRECTED))
        self.assertEqual(world.restarted().arms().refusal, _REFUSAL.SUPERSEDED)
        self.assertEqual(own.refusal, _REFUSAL.SUPERSEDED, "the correction's own answer arms nothing")

    def test_a_later_rejected_run_earns_its_own(self) -> None:
        world = _armed()
        _corrected(world)
        _exhausts(world, _CORRECTED)
        world.moves(**{support.USED: _LATER_RUN, support.METERED: _LATER_RUN})

        outcome = world.restarted().arms(support.source(world, _LATER_RUN))

        self.assertEqual(outcome.status, _STATUS.LANDED)
        later = support.attempt(world, _LATER_RUN)
        self.assertEqual(outcome.reading, _READING(_STANDING.ELIGIBLE, later))

    def test_repeated_resolutions_send_nothing(self) -> None:
        world = _armed()
        _corrected(world)
        _exhausts(world, _CORRECTED)
        before = world.snapshot()

        again = _exhausts(world)
        retired = _retires(world)

        self.assertEqual(again.status, _STATUS.STANDING)
        self.assertEqual(again.reading.standing, _STANDING.EXHAUSTED)
        self.assertEqual((retired.status, retired.refusal), (_STATUS.REFUSED, _REFUSAL.RESOLVED))
        self.assertEqual(world.snapshot(), before)

    def test_an_unnamed_start_is_exhausted(self) -> None:
        # The run ledger shows the launch started and nothing returned to name
        # it: the attempt is spent, never retried.
        world = _armed(**{support.OWED_STARTED: support.SOURCE, support.USED: _CORRECTED})
        self.assertEqual(world.reads().standing, _STANDING.STARTED)

        outcome = _exhausts(world)

        unnamed = _resolved(world, _STAGE.EXHAUSTED, _CORRECTED)
        self.assertEqual(outcome.reading, _READING(_STANDING.EXHAUSTED, unnamed))
        self.assertIsNone(world.record()[support.FIELD]["correction"])

    def test_resolutions_hold_to_the_recorded_ceiling(self) -> None:
        # A run count past what a record holds resolves under the widest floor
        # one holds, covering every source a record could name; a correction
        # charged past it would be no record at all, and is refused unwritten.
        world = _armed(**_PAST_CEILING)
        before = world.snapshot()
        unrecordable = _exhausts(world, MAX_RECORDED_NUMBER + 1)
        self.assertEqual(world.snapshot(), before)

        retired = _retires(world)
        exhausted = _exhausts(_armed(**{support.USED: MAX_RECORDED_NUMBER + 1}))

        self.assertEqual(unrecordable.refusal, _REFUSAL.UNRECORDABLE)
        self.assertEqual(retired.reading.attempt.floor, MAX_RECORDED_NUMBER)
        self.assertEqual(exhausted.reading.attempt.floor, MAX_RECORDED_NUMBER)
        self.assertEqual(_records.read(world.state).stage, _STAGE.RETIRED)

    def test_an_uncounted_ledger_exhausts_nothing(self) -> None:
        # The meter alone is only a floor of what was spent, so the correction
        # charged above it is bounded by nothing: the exhaustion is refused, and
        # once the count reads again its own answer still arms nothing and the
        # exhaustion covers it.
        for damage in _UNCOUNTED:
            with self.subTest(damage=damage):
                world = _armed(**{**_STARTED, **damage})
                refused = _exhausts(world)
                world.moves(**_STARTED)
                world.state = world.restarted().state
                rearmed = world.arms(support.source(world, _CORRECTED))
                exhausted = _exhausts(world, _CORRECTED)
                self.assertEqual(refused.refusal, _REFUSAL.UNCOUNTED)
                self.assertFalse(refused.reading.grants)
                self.assertEqual(rearmed.refusal, _REFUSAL.UNRESOLVED)
                self.assertEqual(exhausted.reading.attempt.floor, _CORRECTED)

    def test_exhaustion_refusals(self) -> None:
        world = _armed()
        _corrected(world)
        unrelated = (
            support.invocation(world, support.SOURCE),
            support.invocation(world, _CORRECTED, comment=1),
            support.invocation(world, _CORRECTED, cycle=1),
        )
        for correction in unrelated:
            with self.subTest(correction=correction):
                outcome = world.asks(_checkpoint.exhaust, support.attempt(world), correction)
                self.assertEqual(outcome.refusal, _REFUSAL.UNRELATED)
        absent = world.asks(_checkpoint.exhaust, support.attempt(world, _LATER_RUN))
        self.assertEqual(absent.refusal, _REFUSAL.ABSENT)
        self.assertEqual(world.reads().standing, _STANDING.STARTED)


class RetirementTest(unittest.TestCase):
    """A pending attempt is retired only over a reading that proves its context moved."""

    def test_evidence_retires_the_attempt(self) -> None:
        for evidence in _EVIDENCE:
            with self.subTest(evidence=evidence):
                world = _armed(**evidence)
                outcome = _retires(world)
                retired = _resolved(world, _STAGE.RETIRED, support.SOURCE)
                self.assertEqual(outcome.reading, _READING(_STANDING.RETIRED, retired))
                self.assertEqual(_retires(world).status, _STATUS.STANDING)
                self.assertEqual(world.restarted().arms().refusal, _REFUSAL.SUPERSEDED)

    def test_no_evidence_retires_nothing(self) -> None:
        for reading in _NO_EVIDENCE:
            with self.subTest(reading=reading):
                world = _armed(**reading)
                before = world.snapshot()
                outcome = _retires(world)
                self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, _REFUSAL.NO_EVIDENCE))
                self.assertEqual(world.snapshot(), before)

    def test_evidence_put_back_refuses_the_retirement(self) -> None:
        world = _armed(**{support.BASELINE: support.EDITED})
        with support.interfering(world, **{support.BASELINE: support.REQUIREMENTS}):
            outcome = _retires(world)

        self.assertEqual(outcome.refusal, CommitRefusal.PREREQUISITE_CHANGED)
        self.assertTrue(world.state.withheld)
        self.assertEqual(world.reads().standing, _STANDING.ELIGIBLE)

    def test_an_uncounted_ledger_retires_nothing(self) -> None:
        # Evidence of a moved context retires nothing no readable count covers:
        # the attempt stays pending, and once the count and the pin read again
        # the correction's own answer arms nothing.
        for damage in _UNCOUNTED:
            with self.subTest(damage=damage):
                world = _armed(**{**_STARTED, **damage, support.SESSION_PIN: None})
                before = world.snapshot()
                refused = world.asks(_checkpoint.retire, support.attempt(world))
                self.assertEqual(world.snapshot(), before)
                world.moves(**{**_STARTED, support.SESSION_PIN: support.SESSION})
                rearmed = world.restarted().arms(support.source(world, _CORRECTED))
                self.assertEqual(refused.refusal, _REFUSAL.UNCOUNTED)
                self.assertEqual(rearmed.refusal, _REFUSAL.UNRESOLVED)
                self.assertEqual(world.reads().standing, _STANDING.STARTED)

    def test_a_started_attempt_retires_above_it(self) -> None:
        # A launch that may still be running belongs to the attempt it was
        # bought by: the floor covers it, so its answer arms nothing.
        world = _armed(**{support.BASELINE: support.EDITED})
        _corrected(world)

        _retires(world)

        self.assertEqual(_records.read(world.state).floor, _CORRECTED)
        rearmed = world.restarted().arms(support.source(world, _CORRECTED))
        self.assertEqual(rearmed.refusal, _REFUSAL.SUPERSEDED)


if __name__ == "__main__":
    unittest.main()
