# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a reset's own record reads under the run, retired before the reset goes on, whatever git answers.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed, its run settled under the anchor -- or only captured, the
finish dying at its artifact's post -- and the finish killed before its
announcement. The next tick cannot fetch the branch, and another road writes
the report the run answers for at another revision while that fetch fails.
The abort records its reset first by blanking the attempt's base tip, a write
that lands over the comment read with the report moved; the report is put
back right behind it, and git then refuses the reset, which stages the tip
back for the park that keeps the attempt. The movement the record read is
retired before the reset is let go on: the run is abandoned or invalidated
whole, its revision and binding kept, so neither the tip put back nor the
report restored revives it. Where that retirement does not land -- every write
behind the blank refused -- nothing is reset or parked, the blank standing as
the record of that movement, and the next recovery reads it and invalidates
the run whole with the attempt's release.

A base tip the tick read blank is held to the comment read afresh too: put
back by another road while the fetch fails, it refuses the record, so no
reset is made that nothing records, and the next tick records the reset and
makes it.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
)

# The report record the run is bound to, and the seams a case stands in for.
_REPORT = "developer_report_current"

_FETCHES = "_authed_fetch"

_GIT = "_git_hardened"


def _refuses_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, refusing every reset, noted in `asked`, and running every other command."""
    if verb == "reset":
        asked.append(verb)
        return subprocess.CompletedProcess([verb, *args], 1, "", "reset refused")
    return live(verb, *args, **options)


def _notes_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, run as it is, every reset noted in `asked`."""
    if verb == "reset":
        asked.append(verb)
    return live(verb, *args, **options)


class RecordedMoveTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What a landed reset record read moving is retired before a reset git refuses puts the base tip back."""

    def test_a_refused_reset_revives_nothing(self) -> None:
        # Settled or only captured, the run is retired whole before the reset,
        # and the attempt is kept on its anchor for the park behind the reset
        # git refused.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._recovers_over_a_moved_report()

                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))

    def test_an_unlanded_retirement_keeps_the_blank(self) -> None:
        # Every write behind the blank is refused, so the run's retirement does
        # not land: no reset is made and nothing parked, the run current beside
        # its blank tip, and the next recovery, writes landing again, reads that
        # blank and invalidates the run whole with the attempt's release.
        settled = self.settles_then_dies()[1]
        self._recovers_over_a_moved_report(refusing=True)

        standing = self.pinned_fields(guarded.AWAITING, readings.KEY_REWRITE_BASE)
        self.assertEqual((standing, self._resets), ((None, None), []))
        self.assertEqual(readings.pinned_records(self)[1], settled)
        self.gh.pinned_failures.refused.discard(git_support.ISSUE)
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()
        self.assert_invalidated(settled)
        self.assert_released()

    def _recovers_over_a_moved_report(self, *, refusing: bool = False) -> None:
        """A recovery over a failed fetch and a refused reset, the report moved behind the fetch, back behind the blank.

        `refusing` has GitHub refuse every pinned-comment write behind the blank.
        """
        self._held = [self.pinned_fields(_REPORT)[0]]
        self._taken = False
        self._refusing = refusing
        self._resets = []
        with (
            patch.object(branch_transport, _FETCHES, self._moves_the_report),
            patch.object(self.gh, "edit_pinned_state", partial(self._puts_the_report_back, self.gh.edit_pinned_state)),
            patch.object(commands, _GIT, partial(_refuses_the_reset, getattr(commands, _GIT), self._resets)),
        ):
            self.recovers()
        self.assertEqual((self._taken, self._held), (True, []))

    def _moves_the_report(self, spec, ref: str, **options):
        """The branch's fetch, failing, the report written at another revision behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and not self._taken:
            self._taken = True
            report = self._held[0]
            self._writes_the_report({**report, "revision": report["revision"] + 1})
        return fetched

    def _puts_the_report_back(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the report written back right behind the edit blanking the base tip."""
        answered = live(issue, staged, **options)
        read = options["over"].get(readings.KEY_REWRITE_BASE)
        if read and not staged.get(readings.KEY_REWRITE_BASE) and self._held:
            self._writes_the_report(self._held.pop())
            if self._refusing:
                self.gh.pinned_failures.refused.add(issue.number)
        return answered

    def _writes_the_report(self, report) -> None:
        """Write `report` as the run's report record, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        state.set(_REPORT, report)
        self.gh.write_pinned_state(self.issue, state)



class BlankTipTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A base tip the tick read blank is held to the comment read afresh before the reset goes on."""

    def test_a_tip_put_back_holds_the_reset(self) -> None:
        # The tick reads the attempt's base tip blank, and another road puts it
        # back while the fetch fails: the record is refused, so no reset is made
        # that nothing records; the next tick records the reset, makes it, and
        # releases the attempt with the run invalidated whole.
        settled = self.settles_then_dies()[1]
        self._tip = [self.pinned_fields(readings.KEY_REWRITE_BASE)[0]]
        self._writes_the_tip(None)
        resets: list = []
        with (
            patch.object(branch_transport, _FETCHES, self._puts_the_tip_back),
            patch.object(commands, _GIT, partial(_notes_the_reset, getattr(commands, _GIT), resets)),
        ):
            self.recovers()
            self.assertEqual((resets, self._tip), ([], []))
            self.assertIsNotNone(self.pinned_fields(readings.KEY_REWRITE_BASE)[0])
            self.recovers()

        self.assertEqual(resets, ["reset"])
        self.assert_invalidated(settled)
        self.assert_released()

    def _puts_the_tip_back(self, spec, ref: str, **options):
        """The branch's fetch, failing, the tip held written back behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and self._tip:
            self._writes_the_tip(self._tip.pop())
        return fetched

    def _writes_the_tip(self, tip) -> None:
        """Write `tip` as the attempt's base tip, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_REWRITE_BASE, tip)
        self.gh.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
