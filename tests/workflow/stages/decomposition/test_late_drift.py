# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a candidate whose requirements moved is held on, and what frees it."""
from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_content_support import LateContentCase
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
)

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"


class ContentBaselineTest(LateContentCase):
    """The first tick of an adjudication records what it was frozen on."""

    def test_the_baseline_is_taken_and_run_carries_on(self) -> None:
        self._seed(baseline=False, comments=(_support.guidance_comment(),))

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_called_once()
        pinned = self._pinned()
        self.assertTrue(pinned[_support.KEY_TITLE_BODY_HASH])
        self.assertTrue(pinned[_support.KEY_COMMENT_HASH])
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], _support.guidance_comment().id)


class TitleBodyDriftTest(LateContentCase):
    """An edit under a frozen candidate parks without discarding it."""

    def test_drift_parks_and_spawns_nothing(self) -> None:
        self._seed_with_plan_pr()
        self.issue.title = _support.EDITED_TITLE

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.awaiting])
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)

    def test_the_evidence_a_later_tick_needs_survives(self) -> None:
        # The park is a claim about the requirements, not about the evidence:
        # the frozen commit, the late session, the recorded generation, and
        # the preserved plan-PR body all have to still be there.
        self._seed_with_plan_pr(**{KEYS.session_id: _support.LATE_SESSION})
        self.issue.title = _support.EDITED_TITLE

        self._run()

        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)
        self.assertEqual(pinned[KEYS.session_id], _support.LATE_SESSION)
        self.assertEqual(pinned[KEYS.plan_pr_number], PLAN_PR_NUMBER)
        self.assertEqual(pinned[KEYS.plan_pr_body], PLAN_PR_BODY)

    def test_drift_outranks_an_answer_beside_it(self) -> None:
        # The answer was written about the scope as it stood before the edit,
        # so it is neither applied nor consumed -- it is still unread when the
        # human comes back to decide what the edit meant.
        self._seed_with_plan_pr()
        self.issue.title = _support.EDITED_TITLE
        self.issue.comments.append(_support.guidance_comment())

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertIsNone(self._pinned().get(_support.KEY_COMMENT_WATERMARK))

    def test_a_park_is_a_response_boundary(self) -> None:
        # Not a one-tick delay. An answer written before the human was told
        # anything is not a reply to what they were then told, so it must not
        # resolve the park on the next poll either -- and the boundary holds a
        # reply out rather than closing the door, so the same human saying it
        # again once they have read the notice IS an answer.
        self._seed_with_plan_pr()
        self.issue.title = _support.EDITED_TITLE
        self.issue.comments.append(_support.guidance_comment())
        self._run()

        stale, held = self._run()
        _support.reply(self.issue, _support.BARE_CONTINUE)
        answered, resumed = self._run()

        self.assertEqual(stale.disposition, _LateDisposition.PARKED)
        held.assert_not_called()
        self.assertEqual(answered.disposition, _LateDisposition.DECIDED)
        resumed.assert_called_once()
        self.assertFalse(self._pinned()[KEYS.awaiting])

    def test_nothing_a_park_recognizes_resolves_it(self) -> None:
        # Reconciliation runs on every eligible tick, so an unchanged park has
        # to cost neither a repeated comment nor a pinned write. An outsider's
        # reply is not a reply at all: with an allowlist configured it reaches
        # neither the guidance, nor the watermark, nor a digest.
        for label, replies in (
            ("no reply", ()),
            (
                "an outsider's continue",
                (_support.human_comment(_support.SECOND_ID, _support.BARE_CONTINUE, login=_support.OUTSIDER),),
            ),
        ):
            with self.subTest(reply=label):
                self._seed(**_support.DRIFT_PARKED)
                self.issue.title = _support.EDITED_TITLE
                self.issue.comments.extend(replies)
                writes = self.github.write_state_calls

                with patch.object(config, ALLOWED_AUTHORS, (_support.HUMAN,)):
                    outcome, spawn = self._run()

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                spawn.assert_not_called()
                self.assertEqual(self._bodies(), [])
                self.assertEqual(self.github.write_state_calls, writes)
                self.assertEqual(
                    self._pinned()[KEYS.park_reason], _support.PARK_CONTENT_DRIFT,
                )


    def test_an_edit_taken_back_clears_the_park(self) -> None:
        # `awaiting_human` is exactly what suppresses the announcement a
        # question verdict earns, so a reverted edit that left the park
        # standing would silence a question recorded and never said.
        self._seed(**_support.DRIFT_PARKED)

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_called_once()
        pinned = self._pinned()
        self.assertFalse(pinned[KEYS.awaiting])
        self.assertIsNone(pinned[KEYS.park_reason])
        self.assertEqual(len(self._bodies()), 1)


class CertifiedCandidateTest(LateContentCase):
    """A bare continue on a drift park vouches for the frozen commit."""

    def test_a_continue_rebaselines_and_resumes(self) -> None:
        self._seed(**_support.DRIFT_PARKED)
        self.issue.title = _support.EDITED_TITLE
        certificate = _support.reply(self.issue, _support.BARE_CONTINUE)

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_called_once()
        pinned = self._pinned()
        self.assertFalse(pinned[KEYS.awaiting])
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], certificate.id)
        self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)

    def test_a_certified_candidate_stops_drifting(self) -> None:
        # The certificate is what the re-baseline records, so the same edit
        # cannot park the same candidate twice.
        self._seed(**_support.DRIFT_PARKED)
        self.issue.title = _support.EDITED_TITLE
        _support.reply(self.issue, _support.BARE_CONTINUE)
        self._run()

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_not_called()
