# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one candidate the authorization cases are all about.

A commit exempt on a record no operator authorization stands behind: the shape
an older binary left on a live issue, where a `single` verdict wrote the
exemption by itself before a human's own decision was required at publication.
Every case here starts from that comment and differs only in what the reading
of the candidate then says.

Beside the gate's own support module rather than inside it, because what these
seed is a different subject: that module is about what one committed candidate
earns from the size gate, and this is about what a record with nobody behind it
earns from the owner past it.
"""
from __future__ import annotations

from tests.workflow.fixtures import _legacy_exemption
from tests.workflow.stages.implementing.late_gate_test_support import (
    AWAITING_HUMAN,
    DEV_SESSION,
    KEY_EXEMPT_SHA,
    LAST_ACTION_COMMENT_ID,
    MEASURED_CANDIDATE_SHA,
    PARK_REASON,
    PARK_UNAUTHORIZED_EXEMPTION,
    PRIOR_ACTION_COMMENT_ID,
    _GateCase,
    recorded_generation,
)

# The terms an operator authorized one oversized publication on, which is the
# half of a bypass an exemption is not.
KEY_OVERRIDE_CANDIDATE_SHA = "late_override_candidate_sha"


class _LegacyExemptionCase(_GateCase):
    """A candidate exempt on a record no operator authorization stands behind."""

    def _seed_legacy(self, **extra) -> None:
        """The pinned comment that exemption leaves, and nothing beside it."""
        self._seed(**{**_legacy_exemption(), **extra})

    def _park_awaiting_authorization(self, reply: str = "", **recorded) -> None:
        """Seed the park an oversized one takes, and any reply to it.

        The generation carries the PAIR and no count, which is exactly what
        the park leaves: a record answering "oversized" is what this workflow
        means by an adjudication in flight, and the dispatcher puts
        `workflow:decomposing` back over one before any stage runs. So the
        reading is re-taken by the tick that acts, and a case that seeded one
        here would be seeding a park no poll of a real issue could survive.
        """
        self._seed(**{
            AWAITING_HUMAN: True,
            PARK_REASON: PARK_UNAUTHORIZED_EXEMPTION,
            LAST_ACTION_COMMENT_ID: PRIOR_ACTION_COMMENT_ID,
            "dev_agent": "codex",
            "dev_session_id": DEV_SESSION,
            **_legacy_exemption(),
            **recorded_generation(),
            **recorded,
        })
        if reply:
            self._reply(reply)

    def _assert_waiting_for_authorization(self) -> None:
        """Parked on the one refusal only a named command answers."""
        pinned = self._pinned()
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_UNAUTHORIZED_EXEMPTION)
        self.assertEqual(self.github.label_history, [])

    def _assert_kept_the_record(self) -> None:
        """Nothing the compatibility read was deleted on the way past."""
        pinned = self._pinned()
        self.assertEqual(pinned[KEY_EXEMPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertNotIn(KEY_OVERRIDE_CANDIDATE_SHA, pinned)
