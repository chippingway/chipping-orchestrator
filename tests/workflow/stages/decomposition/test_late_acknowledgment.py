# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an unchanged commit needs before it counts as a developer's answer."""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition.late_content_replies import reply
from tests.workflow.stages.decomposition.late_content_support import (
    BARE_CONTINUE,
    KEY_GENERATION,
    PARK_REVISION_UNANSWERED,
    REVISED_SHA,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    ACKNOWLEDGED,
    DEV_QUESTION,
    DEV_SILENT,
    NON_ANSWERS,
    UNCHANGED,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    GENERATION_NUMBER,
    KEYS,
    NEXT_GENERATION,
)

# What the resumed developer asks on the round after its first question was
# answered -- a different sentence under the same park reason.
SECOND_QUESTION = "and should the old column stay for one release?"


class AcknowledgedCommitTest(RevisionCase):
    """The marker is the only thing an unchanged commit gets through on."""

    def test_a_marked_reply_is_measured_again(self) -> None:
        # A developer that read the guidance and answered with the marker has
        # acknowledged it -- the same commit is a real answer, and the
        # generation advances so the verdict recorded before the edit is no
        # longer read as this candidate's.
        self._seed_drifted()

        outcome, _spawn = self._revise(
            seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_GENERATION], NEXT_GENERATION)

    def test_a_commit_nobody_vouched_for_parks(self) -> None:
        # Silence, a question, and prose that merely sounds like agreement all
        # leave HEAD where it was, and reading any of them as "the work already
        # covers it" would adjudicate a candidate nobody vouched for.
        for label, said in NON_ANSWERS:
            with self.subTest(reply=label):
                self._seed_drifted()

                outcome, _spawn = self._revise(
                    reply=said, seed=UNCHANGED, measurement=ACKNOWLEDGED,
                )

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                pinned = self._pinned()
                self.assertEqual(
                    pinned[KEYS.park_reason], PARK_REVISION_UNANSWERED,
                )
                self.assertEqual(pinned[KEY_GENERATION], GENERATION_NUMBER)

    def test_an_unchanged_timeout_is_not_an_answer(self) -> None:
        self._seed_drifted()

        outcome, _spawn = self._revise(
            reply=agent_reply(DEV_SILENT, timed_out=True),
            seed=UNCHANGED,
            measurement=ACKNOWLEDGED,
        )

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned()[KEYS.park_reason], PARK_REVISION_UNANSWERED,
        )

    def test_the_park_quotes_what_it_did_say(self) -> None:
        # The commonest reason to be here is a question, and a question the
        # park swallowed is one the human never gets to answer.
        self._seed_drifted()

        self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        self.assertTrue(
            any(DEV_QUESTION in body for body in self._bodies()),
        )

    def test_the_park_it_leaves_holds_the_candidate(self) -> None:
        # A park the next tick falls straight through would be no park at all:
        # it would adjudicate the very commit nobody vouched for.
        self._seed_drifted()
        self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        outcome, spawn = self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertEqual(
            self._pinned()[KEY_GENERATION], GENERATION_NUMBER,
        )

    def test_a_human_continue_accepts_the_commit(self) -> None:
        # The park told them to reply `/orchestrator continue` to take the
        # commit as it stands, so that continue is the acknowledgment the run
        # did not give -- and it costs no second developer run.
        self._seed_drifted()
        self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )
        reply(self.issue, BARE_CONTINUE)

        outcome, spawn = self._revise(
            seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_not_called()
        pinned = self._pinned()
        self.assertEqual(pinned[KEY_GENERATION], NEXT_GENERATION)
        self.assertFalse(pinned[KEYS.awaiting])

    def test_a_new_commit_needs_no_marker(self) -> None:
        # The marker only decides an UNCHANGED commit: work that moved HEAD
        # speaks for itself and is measured whatever the reply said.
        self._seed_drifted()

        outcome, _spawn = self._revise(reply=DEV_QUESTION)

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertEqual(self._pinned()[KEYS.candidate_sha], REVISED_SHA)


class UnansweredParkTest(RevisionCase):
    """The park an unvouched-for commit leaves, across more than one round."""

    def test_a_second_question_is_announced_too(self) -> None:
        # The human answered the developer's first question and the resumed
        # developer asked another. A park quieted because its REASON matches
        # the one just answered would swallow that second question whole.
        self._seed_drifted()
        self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )
        reply(self.issue)

        asked, resumed = self._revise(
            reply=SECOND_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )

        self.assertEqual(asked.disposition, _LateDisposition.PARKED)
        resumed.assert_called_once()
        self.assertTrue(
            any(SECOND_QUESTION in body for body in self._bodies()),
        )
