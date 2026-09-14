# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reply this mode acted on is marked read for every stage, not just this one.

Two readers walk the same issue thread. The late fingerprints stop a comment
coming back as fresh guidance HERE; the shared `last_action_comment_id` stops
the later validating -> in_review handoff finding it as fresh PR feedback and
routing the pull request to `fixing` over an answer already spent. Every route
that reads a reply has to move both, so they are tested together rather than
one at a time beside the semantics each route is really about.
"""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition.late_content_replies import reply
from tests.workflow.stages.decomposition.late_content_support import (
    ASKED_STATE,
    BARE_CONTINUE,
    DRIFT_PARKED,
    EDITED_TITLE,
    KEY_COMMENT_WATERMARK,
    KEY_LAST_ACTION_COMMENT_ID,
    REVISION_PARKED,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_PIN,
    RevisionCase,
)


class ConsumedReplyTest(RevisionCase):
    """Each route that spends a reply leaves both watermarks past it."""

    def test_an_answered_question_is_marked_read(self) -> None:
        self._seed(**ASKED_STATE)
        answer = reply(self.issue)

        self._run()

        self._assert_read_through(answer.id)

    def test_a_refused_continue_is_marked_read(self) -> None:
        # Refused, but still spent: the command was consumed and answered with
        # a notice, so it must not reach the in-review scan as feedback.
        self._seed(**ASKED_STATE)
        nudge = reply(self.issue, BARE_CONTINUE)

        self._run()

        self._assert_read_through(nudge.id)

    def test_a_certificate_is_marked_read(self) -> None:
        self._seed(**DRIFT_PARKED)
        self.issue.title = EDITED_TITLE
        certificate = reply(self.issue, BARE_CONTINUE)

        self._run()

        self._assert_read_through(certificate.id)

    def test_a_stalled_continue_is_marked_read(self) -> None:
        # No agent ran, but the continue was still acted on: it re-read the
        # checkout and re-measured the commit.
        self._seed(**REVISION_PARKED, **DEV_PIN)
        nudge = reply(self.issue, BARE_CONTINUE)

        self._revise()

        self._assert_read_through(nudge.id)

    def test_a_mixed_batch_is_marked_read_whole(self) -> None:
        # Guidance and a bare continue in one batch: the developer is resumed
        # on the guidance, and BOTH are marked read -- the continue arrived in
        # the same reply and must not be left behind for the in-review scan.
        self._seed_drifted(guided=False)
        reply(self.issue)
        nudge = reply(self.issue, BARE_CONTINUE)

        revised, resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        resumed.assert_called_once()
        self._assert_read_through(nudge.id)

    def _assert_read_through(self, consumed: int) -> None:
        """Both watermarks cover the reply, and neither was left behind."""
        pinned = self._pinned()
        self.assertEqual(pinned[KEY_COMMENT_WATERMARK], consumed)
        self.assertGreaterEqual(pinned[KEY_LAST_ACTION_COMMENT_ID], consumed)
