# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A stranded pair's retry against the requirements baseline recorded before it, on a real repo, tick by tick.

A stage read an operator's bare continue before the pair was stranded, and
recorded the requirements baseline over it. The retry that answers the
stranded park is the attempt's only where that baseline is one the current
fingerprint reproduces -- which leaves the continue out -- over the thread up
to the park's notice. A baseline spelled any other way, as an earlier
producer that counted the continue spelled it, is neither recognized nor
folded into: the retry moves the watermark alone, and the adjudication parks
on the drift it reads rather than adjudicating over requirements nothing
shows unmoved. Both hold whether the retry lands before the handoff, or only
after a handoff whose tick was lost, when the dispatcher records it read.
"""
from __future__ import annotations

import unittest

from tests.git.base_sync.journey_adjudication_support import replies
from tests.git.base_sync.journey_assertions import ADJUDICATOR
from tests.git.base_sync.journey_handoff_support import spawned_roles
from tests.git.base_sync.journey_push_support import AFTER_THE_HANDOFF, crash_at
from tests.git.base_sync.journey_stranded_support import StrandedJourney, reads_a_bare_continue
from tests.workflow.engine.drift_test_support import continue_counting_hash

# The park a late adjudication takes over requirements that moved under its candidate.
PARK_CONTENT_DRIFT = "late_content_drift"

# The operator's reply that asks for a parked refresh's retry and nothing else.
RETRY = "please retry"

KEY_PARK_REASON = "park_reason"
KEY_WATERMARK = "last_action_comment_id"


class StrandedBaselineTest(StrandedJourney, unittest.TestCase):
    """The requirements baseline a stage recorded over a bare continue it read before the pair was stranded."""

    def test_a_read_continue_spends_the_retry(self) -> None:
        # The baseline leaves that control out, so it covers the thread up to
        # the park's notice: the retry is the attempt's, and the adjudication
        # runs with nobody resumed.
        reads_a_bare_continue(self)
        retry = self._answers_the_stranded_park(lost=False)

        self._ticks()

        self._assert_adjudicated_afresh(self.replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)

    def test_a_retry_after_a_lost_handoff_is_spent(self) -> None:
        # The same baseline, the retry written only after the handoff landed
        # and its tick was lost: the dispatcher records it read, and the
        # adjudication runs with nobody resumed.
        reads_a_bare_continue(self)
        retry = self._answers_the_stranded_park(lost=True)

        self._ticks()

        self._assert_adjudicated_afresh(self.replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)

    def test_an_earlier_spelling_parks_on_drift(self) -> None:
        # The same baseline, spelled as an earlier producer spelled it,
        # counting that continue. No current reading reproduces it, so nothing
        # shows what the developer worked against: the retry is spent on the
        # watermark alone, the value stays as recorded, and the adjudication
        # parks on the drift rather than adjudicating or resuming anybody.
        recorded = reads_a_bare_continue(self, spelled=continue_counting_hash)
        retry = self._answers_the_stranded_park(lost=False)

        self._ticks()

        self._assert_parked_on_drift(recorded, retry)

    def test_a_lost_tick_still_parks_on_drift(self) -> None:
        # The earlier spelling again, the retry written after a handoff whose
        # tick was lost: the dispatcher's write recognizes it no more than the
        # handoff's would have.
        recorded = reads_a_bare_continue(self, spelled=continue_counting_hash)
        retry = self._answers_the_stranded_park(lost=True)

        self._ticks()

        self._assert_parked_on_drift(recorded, retry)

    def _answers_the_stranded_park(self, *, lost: bool) -> int:
        """Strand the pair again over the baseline a case recorded, and answer its park with a retry; the reply's id.

        Where `lost`, the tick that hands the pair over is lost the moment
        that write has landed, before the retry is written.
        """
        self._strands()
        if lost:
            with crash_at(self._gh, AFTER_THE_HANDOFF), self.assertRaises(RuntimeError):
                self._ticks()
            self.assertEqual(self._holders(), (None, None, self.replay, self.replay))
        return replies(self, RETRY)

    def _assert_parked_on_drift(self, recorded: str, retry: int) -> None:
        """The adjudication parked on drift with the replay still its own, `recorded` kept, and `retry` read."""
        durable = self._durable()
        self.assertEqual(self._holders(), (None, None, self.replay, self.replay))
        self.assertEqual(spawned_roles(self), (ADJUDICATOR,))
        self.assertEqual(
            (durable.get(KEY_PARK_REASON), durable.get("user_content_hash")), (PARK_CONTENT_DRIFT, recorded),
        )
        self.assertGreaterEqual(durable.get(KEY_WATERMARK), retry)
