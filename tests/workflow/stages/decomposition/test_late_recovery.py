# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a crashed late tick reads back, and what it must not read back."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_park_state as _late_park_state,
    late_session as _session,
)
from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition.late_run_support import (
    LateCase,
    adjudicate,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CYCLE_ID,
    FIRST_ESTIMATE,
    KEY_PLAN_PATH,
    KEYS,
    LATE_ISSUE_NUMBER,
    LATE_SESSION_ID,
    PLAN_PATH,
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
    QUESTION_ASKED,
    QUESTION_REPLY,
    SECOND_ESTIMATE,
    SINGLE_REPLY,
    SPLIT_REPLY,
    generation_state,
    late_block,
    late_generation,
    seed_plan_pr,
    seeded_late_issue,
)

NEXT_CYCLE_ID = CYCLE_ID + 1

QUESTION_VERDICT = "question"

SINGLE_VERDICT = "single"

HUMAN_REWRITE = "a human rewrote the description"

EDIT_PR_BODY = "edit_pr_body"

REPEATS = 3

# What the failed-hold notice says, so a repeat of it can be counted.
HOLD_FAILED_FRAGMENT = "could not put the adjudication hold"

WORKFLOW_LOG = "orchestrator.workflow"

_TOO_LONG_TO_RECORD = "q" * _session.MAX_RECORDED_BODY

# One reply per field of prose the comment budget covers, each past it on its
# own. A `single` carries an explanation the way a `question` carries what it
# asked, so the same refusal is reachable from either.
_OVERSIZED_OUTCOMES = (
    (
        QUESTION_VERDICT,
        late_block(
            '{"decision": "question", "category": "unsafe_split", '
            f'"question": "{_TOO_LONG_TO_RECORD}"}}'
        ),
    ),
    (
        SINGLE_VERDICT,
        late_block(
            '{"decision": "single", '
            f'"split_blocker": "{_TOO_LONG_TO_RECORD}"}}'
        ),
    ),
)

# The refusal is one sentence for every outcome that overflows, so it has to
# enumerate each field a comment could fail to hold. This is the one a
# `single` adds; a notice that named only the other two would send a human
# looking for a question nobody asked.
_NAMES_THE_EXPLANATION = "an explanation of what stopped a split"


class _CommentSnapshot:
    """What pinned state held each time a comment was posted.

    The persist-before-announce order is only visible from inside the post: a
    result written afterwards would still be there by the time a test looked.
    """

    def __init__(self, github) -> None:
        self.snapshots: list[dict] = []
        self._github = github
        self._comment = github.comment

    def __call__(self, issue, body):
        self.snapshots.append(self._github.pinned_data(LATE_ISSUE_NUMBER))
        return self._comment(issue, body)


class SplitRecoveryTest(LateCase, unittest.TestCase):
    """A split's manifest is what it decided, so the record carries it."""

    def test_a_split_records_its_manifest(self) -> None:
        outcome, spawn = self._adjudicate(
            agent_reply(SPLIT_REPLY, session_id=LATE_SESSION_ID),
        )

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.SPLIT)
        self.assertEqual(self._pinned().get(KEYS.session_id), LATE_SESSION_ID)
        self.assertEqual(self._pinned().get(KEYS.verdict), LateVerdict.SPLIT)
        self.assertEqual(
            [child["title"] for child in self._pinned()[KEYS.children]],
            ["A", "B"],
        )

    def test_a_split_records_each_slice_budget(self) -> None:
        # The child issues are created from this manifest and each states the
        # size its slice was proposed at, so a record without the numbers
        # would leave a crashed tick creating children that say nothing about
        # their own size.
        self._adjudicate(agent_reply(SPLIT_REPLY))

        self.assertEqual(
            [child[ESTIMATE] for child in self._pinned()[KEYS.children]],
            [FIRST_ESTIMATE, SECOND_ESTIMATE],
        )

    def test_a_crashed_split_recovers_its_children(self) -> None:
        # The whole point of recording it: a second run would be paid for
        # again and is free to decide something else entirely.
        self._adjudicate(agent_reply(SPLIT_REPLY))

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.SPLIT)
        self.assertEqual(
            [child["title"] for child in outcome.adjudication.children],
            ["A", "B"],
        )
        self.assertEqual(outcome.adjudication.children[1]["depends_on"], [0])
        self.assertEqual(
            [child[ESTIMATE] for child in outcome.adjudication.children],
            [FIRST_ESTIMATE, SECOND_ESTIMATE],
        )

    def test_a_manifest_without_budgets_answers(self) -> None:
        # A live issue's split was recorded before this domain kept budgets.
        # Reading one as no manifest would send a candidate that has already
        # been adjudicated round again, for a run free to decide differently.
        self._adjudicate(agent_reply(SPLIT_REPLY))
        self.github.seed_state(LATE_ISSUE_NUMBER, **{
            **self._pinned(),
            KEYS.children: [
                {
                    field: declared
                    for field, declared in child.items()
                    if field != ESTIMATE
                }
                for child in self._pinned()[KEYS.children]
            ],
        })

        recovered, unspawned = self._adjudicate()

        unspawned.assert_not_called()
        self.assertEqual(recovered.disposition, _LateDisposition.DECIDED)
        self.assertEqual(
            [child["title"] for child in recovered.adjudication.children],
            ["A", "B"],
        )
        self.assertNotIn(ESTIMATE, recovered.adjudication.children[0])


class AnnouncementRecoveryTest(LateCase, unittest.TestCase):
    """A question is durable before it is posted, and posted if it was not."""

    def test_the_result_is_durable_before_the_comment(self) -> None:
        recorder = _CommentSnapshot(self.github)

        with patch.object(self.github, "comment", recorder):
            self._adjudicate(agent_reply(QUESTION_REPLY))

        self.assertEqual(
            [held.get(KEYS.verdict) for held in recorder.snapshots],
            [LateVerdict.QUESTION],
        )
        self.assertEqual(
            recorder.snapshots[0].get(KEYS.question), QUESTION_ASKED,
        )

    def test_an_unannounced_question_is_announced(self) -> None:
        # The window between the post and the write that records it: the
        # outcome is durable, the park is not, and the next tick owes the
        # issue the question rather than another agent run.
        self._adjudicate(agent_reply(QUESTION_REPLY))
        self.github.seed_state(
            LATE_ISSUE_NUMBER,
            **{**self._pinned(), KEYS.awaiting: False},
        )
        posted = len(self.github.posted_comments)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(len(self.github.posted_comments), posted + 1)
        self.assertIn(QUESTION_ASKED, self.github.posted_comments[-1][1])
        self.assertTrue(self._pinned().get(KEYS.awaiting))

    def test_an_announced_question_is_not_reposted(self) -> None:
        self._adjudicate(agent_reply(QUESTION_REPLY))
        posted = len(self.github.posted_comments)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(len(self.github.posted_comments), posted)


class IncompleteRecordTest(LateCase, unittest.TestCase):
    """A half-written outcome is not an answer, however it got there."""

    def test_a_question_with_no_text_respawns(self) -> None:
        # It would otherwise suppress the next spawn and then announce
        # nothing, leaving the issue decided, silent, and going nowhere.
        self.github.seed_state(
            LATE_ISSUE_NUMBER,
            **{
                **self._pinned(),
                KEYS.run_cycle_id: CYCLE_ID,
                KEYS.run_generation: 1,
                KEYS.source_sha: CANDIDATE_SHA,
                KEYS.verdict: str(LateVerdict.QUESTION),
                KEYS.category: str(LateVerdictCategory.SCOPE_AMBIGUOUS),
            },
        )

        outcome, spawn = self._adjudicate(agent_reply(SINGLE_REPLY))

        spawn.assert_called_once()
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.SINGLE)

    def test_an_outcome_too_large_to_record_parks(self) -> None:
        # Nothing durable would stand behind it, so acting on it would leave
        # the issue decided in a way no later tick could see. Every field of
        # prose the budget covers reaches the same refusal, and the one notice
        # it leaves has to name each of them for the human it stops.
        for verdict, oversized in _OVERSIZED_OUTCOMES:
            with self.subTest(verdict=verdict):
                with self.assertLogs(WORKFLOW_LOG, level="ERROR"):
                    outcome, _ = self._adjudicate(agent_reply(oversized))

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self.assertNotIn(KEYS.verdict, self._pinned())
                notice = self.github.posted_comments[-1][1]
                self.assertIn("half an outcome", notice)
                self.assertIn(_NAMES_THE_EXPLANATION, notice)


class RetriedHoldTest(LateCase, unittest.TestCase):
    """A park the retry answered is retired before the result is processed."""

    def setUp(self) -> None:
        github, issue = seeded_late_issue(
            pr_number=PLAN_PR_NUMBER, **{KEY_PLAN_PATH: PLAN_PATH},
        )
        self.github = github
        self.issue = issue
        self.plan_pr = seed_plan_pr(github)

    def test_a_retried_hold_still_announces(self) -> None:
        # The park the failed hold left would otherwise silence exactly the
        # announcement the successful retry earns: decided, durable, and
        # never said out loud.
        self._fail_the_hold()

        outcome, spawn = adjudicate(
            self.github, self.issue, agent_reply(QUESTION_REPLY),
        )

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertIn(QUESTION_ASKED, self.github.posted_comments[-1][1])
        self.assertEqual(self._pinned().get(KEYS.park_reason), _late_park_state.PARK_QUESTION)

    def test_a_retried_hold_leaves_no_stale_park(self) -> None:
        # The reason a failed hold left is not the one an issue whose verdict
        # landed is waiting on, so the retry replaces it rather than leaving
        # a human to answer a step that has since been reconciled.
        self._fail_the_hold()

        adjudicate(self.github, self.issue, agent_reply(SINGLE_REPLY))

        self.assertEqual(
            self._pinned().get(KEYS.park_reason),
            _late_park_state.PARK_SINGLE_DECISION,
        )

    def test_a_reused_answer_persists_the_retirement(self) -> None:
        # The branch that reuses a recorded answer is the one that would
        # otherwise never write, so a park retired into memory there is a
        # park still standing on the issue -- durably claiming a human is
        # owed something on an issue already decided.
        adjudicate(self.github, self.issue, agent_reply(SPLIT_REPLY))
        self._fail_the_hold()

        reused, unspawned = adjudicate(self.github, self.issue)

        unspawned.assert_not_called()
        self.assertEqual(reused.disposition, _LateDisposition.DECIDED)
        self.assertFalse(self._pinned().get(KEYS.awaiting))
        self.assertIsNone(self._pinned().get(KEYS.park_reason))

    def test_a_stranded_question_survives(self) -> None:
        # The composition: a run whose result persisted and whose comment
        # then failed leaves an announcement owing; a hold that fails in
        # between buries it under a park that has nothing to do with it; and
        # the retry that reconciles the hold has to dig it back out.
        refused = patch.object(
            self.github, "comment", side_effect=RuntimeError,
        )
        with refused, self.assertRaises(RuntimeError):
            self._adjudicate(agent_reply(QUESTION_REPLY))
        self.assertEqual(self._pinned().get(KEYS.verdict), QUESTION_VERDICT)
        self._fail_the_hold()

        recovered, unspawned = adjudicate(self.github, self.issue)

        unspawned.assert_not_called()
        self.assertEqual(recovered.disposition, _LateDisposition.DECIDED)
        self.assertIn(QUESTION_ASKED, self.github.posted_comments[-1][1])
        self.assertEqual(
            self._pinned().get(KEYS.park_reason), _late_park_state.PARK_QUESTION,
        )

    def test_a_repeated_failure_says_it_once(self) -> None:
        # Reconciliation is retried on every eligible tick -- that is what
        # makes it idempotent -- so an unchanged failure would otherwise say
        # the same sentence to the same thread once a tick until a human
        # arrived.
        self.plan_pr.body = HUMAN_REWRITE
        refused = patch.object(
            self.github, EDIT_PR_BODY, side_effect=RuntimeError,
        )

        with refused:
            for attempt in range(REPEATS):
                with self.assertLogs(WORKFLOW_LOG, level="ERROR"):
                    parked, unspawned = self._adjudicate()
                self.assertEqual(parked.disposition, _LateDisposition.PARKED)
                unspawned.assert_not_called()

        self.assertEqual(
            len([
                body for _, body in self.github.posted_comments
                if HOLD_FAILED_FRAGMENT in body
            ]),
            1,
        )
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(
            self._pinned().get(KEYS.park_reason),
            _late_park_state.PARK_HOLD_FAILED,
        )

    def _fail_the_hold(self) -> None:
        """Leave the issue parked the way a refused PR edit does.

        The description is put back to the one the hold preserved first, which
        is what a crash between the persist and the edit leaves: that is the
        body the reconciliation re-applies over, so the edit is reached
        whether or not a hold already stands.
        """
        self.plan_pr.body = PLAN_PR_BODY
        refused = patch.object(
            self.github, EDIT_PR_BODY, side_effect=RuntimeError,
        )
        with refused, self.assertLogs(WORKFLOW_LOG, level="ERROR"):
            adjudicate(self.github, self.issue)
        self.assertTrue(self._pinned().get(KEYS.awaiting))


class CycleIdentityTest(LateCase, unittest.TestCase):
    """A generation counter repeats across cycles; a recorded answer must not."""

    def test_a_new_cycle_re_adjudicates(self) -> None:
        # A restart mints a fresh cycle and puts the generation back to where
        # it started, so counter-plus-commit alone would hand the new attempt
        # the old one's verdict -- and these run fields outlive the clear.
        self._adjudicate(agent_reply(SINGLE_REPLY))
        self.github.seed_state(
            LATE_ISSUE_NUMBER,
            **{
                **self._pinned(),
                **generation_state(late_generation(cycle_id=NEXT_CYCLE_ID)),
            },
        )

        outcome, spawn = self._adjudicate(agent_reply(QUESTION_REPLY))

        spawn.assert_called_once()
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.QUESTION)
        self.assertEqual(self._pinned().get(KEYS.run_cycle_id), NEXT_CYCLE_ID)


if __name__ == "__main__":
    unittest.main()
