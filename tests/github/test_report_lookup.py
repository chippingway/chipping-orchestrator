# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a developer-report reading says about the thing it found.

A reading is one moment. Its presence, the object that answered it, and that
object's identity are all taken then -- which is what makes the identity part
of the reading rather than a question two callers can get different answers to.

The publication road is why that matters. It asks twice: once to record the
comment in this orchestrator's own ledger, and once to record where the settled
report sits. `found` is an object GitHub handed back, so on a worker that has
not completed it the id is a request -- and a request can fail once and succeed
the next time it is made. Answered afresh to each caller, the ledger would be
written from one answer and the settlement from the other, leaving a report
recorded as published at a comment nothing recorded posting: the drift hash and
every feedback scan would then read this orchestrator's own text back as a
human's fresh comment on the thread.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pull_request_reports import ReportLookup, ReportPresence
from tests.support.fakes import FakeComment

_GITHUB_LOG = "orchestrator.github"

_WARNING = "WARNING"

_LANDED_ID = 4242

# What a read GitHub would not answer raises.
_REFUSED = "GitHub did not answer the read"


class _FlakyComment:
    """A comment whose id fails the first time it is asked and answers after."""

    def __init__(self) -> None:
        self.reads = 0

    @property
    def id(self) -> int:
        """Raise the way a completion that failed does, then answer."""
        self.reads += 1
        if self.reads == 1:
            raise RuntimeError(_REFUSED)
        return _LANDED_ID


class LandedIdentityTest(unittest.TestCase):
    """The id of what a reading found is resolved once, when it is taken."""

    def test_a_reading_names_what_it_found(self) -> None:
        found = FakeComment(id=_LANDED_ID, body="a report")

        self.assertEqual(
            ReportLookup(ReportPresence.PRESENT, found).landed_id, _LANDED_ID,
        )

    def test_a_reading_that_found_nothing_is_none(self) -> None:
        self.assertIsNone(ReportLookup(ReportPresence.ABSENT).landed_id)

    def test_a_flaky_id_is_never_asked_a_second_time(self) -> None:
        # The regression. Asked afresh by each caller, this object answers
        # None to the first and an id to the second -- so the ledger and the
        # settlement on the publication road would disagree about which
        # comment the report landed as, and one of them would be empty.
        flaky = _FlakyComment()

        with self.assertLogs(_GITHUB_LOG, _WARNING):
            reading = ReportLookup(ReportPresence.PRESENT, flaky)

        self.assertEqual([reading.landed_id, reading.landed_id], [None, None])
        self.assertEqual(flaky.reads, 1)

    def test_a_later_reading_asks_again(self) -> None:
        # Read once PER READING, not once ever: the retry that follows a
        # failed read takes a reading of its own, and this one answers.
        flaky = _FlakyComment()

        with self.assertLogs(_GITHUB_LOG, _WARNING):
            ReportLookup(ReportPresence.PRESENT, flaky)

        self.assertEqual(
            ReportLookup(ReportPresence.PRESENT, flaky).landed_id, _LANDED_ID,
        )


if __name__ == "__main__":
    unittest.main()
