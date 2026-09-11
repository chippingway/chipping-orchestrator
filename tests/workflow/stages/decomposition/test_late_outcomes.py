# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one finished late run is read as, and what a verdict earns."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import (
    MAX_LINEAGE_DEPTH,
    LateVerdict,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.support.fakes import FakeLabel
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_run_support import (
    LateCase,
    agent_reply,
)

PAUSED_LABEL = "paused"

SPLIT_CHILDREN = 2

# Two unusable replies, malformed in different ways. They park for the same
# reason and say different things, which is what a retried run's park has to
# be able to tell apart.
FIRST_UNPARSED = "no fenced block at all, just prose."

SECOND_UNPARSED = f"```{_support.LATE_FENCE}\nnot json\n```"

PARK_UNPARSED = "late_manifest_invalid"


class _PausedDuringRun:
    """An operator applying `paused` while the agent is still running."""

    def __init__(self, issue, agent_result) -> None:
        self._issue = issue
        self._agent_result = agent_result

    def __call__(self, *_args, **_kwargs):
        self._issue.labels.append(FakeLabel(PAUSED_LABEL))
        return self._agent_result


class RetriedRunParkTest(LateCase, unittest.TestCase):
    """A park the run before it already took is not always the same park."""

    def test_a_second_unusable_reply_is_announced(self) -> None:
        # The first park is retired as superseded, the retry spawns, and the
        # reply is unusable in a NEW way. Quieting that because the reason
        # matched would tell the human nothing about what actually came back.
        self._adjudicate(agent_reply(FIRST_UNPARSED))

        outcome, spawn = self._adjudicate(agent_reply(SECOND_UNPARSED))

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_called_once()
        self.assertEqual(self._pinned()[_support.KEYS.park_reason], PARK_UNPARSED)
        self.assertEqual(len(self.github.posted_comments), 2)


class DeclinedRunTest(LateCase, unittest.TestCase):
    """The outcomes a finished spawn is not allowed to be read as."""

    def test_a_mid_run_pause_writes_no_result(self) -> None:
        # A declined run costs the issue's daily budget nothing, exactly as a
        # declined run in every other stage does: the pre-spawn write carries
        # the late identity and leaves the counters as it found them.
        paused = _PausedDuringRun(self.issue, agent_reply(_support.SINGLE_REPLY))

        outcome, _ = self._adjudicate(paused)

        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self.assertNotIn(_support.KEYS.verdict, self._pinned())
        self.assertNotIn(_support.KEYS.session_id, self._pinned())
        self.assertNotIn(_support.KEYS.retry_count, self._pinned())

    def test_a_declined_run_keeps_a_granted_attempt(self) -> None:
        # The attempt a human bought is spent by the same gate the counters
        # are, and refunded by the same pre-spawn write: a run a mid-run pause
        # declines leaves the continuation to be taken again rather than
        # charging somebody's one word for an answer nobody got.
        self.issue = _support.seed_late_issue(
            self.github, _support.late_generation(), retry_cap_continued=1,
        )
        paused = _PausedDuringRun(self.issue, agent_reply(_support.SINGLE_REPLY))

        outcome, _ = self._adjudicate(paused)

        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self.assertEqual(self._pinned().get(_support.KEYS.retry_grant), 1)

    def test_an_interrupted_run_is_not_read(self) -> None:
        outcome, _ = self._adjudicate(
            agent_reply(_support.SINGLE_REPLY, interrupted=True),
        )

        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self.assertNotIn(_support.KEYS.verdict, self._pinned())
        # A shutdown sweep landing here over and over must not exhaust the
        # cap without ever producing an answer.
        self.assertNotIn(_support.KEYS.retry_count, self._pinned())
        # The spawn record is deliberately durable: it is what the retry
        # measures itself against.
        self.assertEqual(self._pinned().get(_support.KEYS.source_sha), _support.CANDIDATE_SHA)

    def test_a_timeout_parks_and_keeps_its_session(self) -> None:
        # A timed-out run still opened a session a later resume has to land
        # on, and it did spend the retry slot the park now records.
        outcome, _ = self._adjudicate(
            agent_reply("", session_id=_support.LATE_SESSION_ID, timed_out=True),
        )

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertIn("timed out", self.github.posted_comments[-1][1])
        self.assertNotIn(_support.KEYS.verdict, self._pinned())
        self.assertEqual(self._pinned().get(_support.KEYS.session_id), _support.LATE_SESSION_ID)
        self.assertEqual(outcome.run.session_id, _support.LATE_SESSION_ID)
        self.assertEqual(self._pinned().get(_support.KEYS.retry_count), 1)

    def test_a_reply_with_no_block_parks(self) -> None:
        outcome, _ = self._adjudicate(agent_reply(_support.NO_BLOCK_REPLY))

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertIn(_support.LATE_FENCE, self.github.posted_comments[-1][1])
        self.assertNotIn(_support.KEYS.verdict, self._pinned())


class DecidedOutcomeTest(LateCase, unittest.TestCase):
    """What a verdict records, and what it deliberately does not do."""

    def test_a_finished_run_records_its_result(self) -> None:
        outcome, spawn = self._adjudicate(
            agent_reply(_support.SINGLE_REPLY, session_id=_support.LATE_SESSION_ID),
        )

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(outcome.adjudication.verdict, LateVerdict.SINGLE)
        self.assertEqual(self._pinned().get(_support.KEYS.session_id), _support.LATE_SESSION_ID)
        self.assertEqual(self._pinned().get(_support.KEYS.verdict), LateVerdict.SINGLE)
        self.assertEqual(
            self._pinned().get(_support.KEYS.split_blocker), _support.SPLIT_BLOCKER,
        )
        # What is reported is read back off pinned state, so a caller asking
        # the run for its session gets the one a later resume would land on.
        self.assertEqual(outcome.run.session_id, _support.LATE_SESSION_ID)
        self.assertEqual(outcome.run.verdict, LateVerdict.SINGLE)

    def test_a_question_parks_with_what_it_asks(self) -> None:
        outcome, _ = self._adjudicate(agent_reply(_support.QUESTION_REPLY))

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertIn(_support.QUESTION_ASKED, self.github.posted_comments[-1][1])
        self.assertTrue(self._pinned().get(_support.KEYS.awaiting))
        self.assertEqual(
            self._pinned().get(_support.KEYS.category),
            LateVerdictCategory.SCOPE_AMBIGUOUS,
        )

    def test_a_split_at_the_bound_becomes_a_question(self) -> None:
        # The bound is a safety invariant, so the outcome is the question the
        # workflow now owes a human -- and the next tick asks the human rather
        # than paying for the same forbidden split again.
        self.github.seed_state(
            self.issue.number,
            **_bounded_state(),
        )

        outcome, _ = self._adjudicate(agent_reply(_support.SPLIT_REPLY))

        self.assertEqual(outcome.adjudication.verdict, LateVerdict.QUESTION)
        self.assertEqual(
            self._pinned().get(_support.KEYS.category),
            LateVerdictCategory.LINEAGE_BOUND,
        )
        self.assertEqual(self._pinned().get(_support.KEYS.verdict), LateVerdict.QUESTION)

    def test_the_verdict_carries_its_measurement(self) -> None:
        self._adjudicate(agent_reply(_support.SINGLE_REPLY))

        recorded = self._events_named(_support.EVENT_LATE_VERDICT)
        self.assertEqual(len(recorded), 1)
        decided = recorded[0]
        self.assertEqual(decided.get("verdict"), LateVerdict.SINGLE)
        self.assertEqual(
            decided.get("category"),
            LateVerdictCategory.GENERATED_ARTIFACTS,
        )
        self.assertEqual(decided.get("additions"), _support.ADDITIONS)
        self.assertEqual(decided.get("threshold"), _support.THRESHOLD)
        self.assertEqual(decided.get("source_sha"), _support.CANDIDATE_SHA)

    def test_a_later_generation_re_adjudicates(self) -> None:
        # A recorded answer names the generation it answered, so the next
        # frozen candidate is a new question rather than a settled one.
        self._adjudicate(agent_reply(_support.SINGLE_REPLY))
        self.github.seed_state(
            self.issue.number,
            **_nextgeneration_state(self._pinned()),
        )

        outcome, spawn = self._adjudicate(agent_reply(_support.QUESTION_REPLY))

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(
            self._pinned().get(_support.KEYS.run_generation), _support.NEXT_GENERATION,
        )


def _bounded_state() -> dict:
    """The seeded pinned state of a generation at the lineage bound."""
    return _support.generation_state(_support.late_generation(lineage_depth=MAX_LINEAGE_DEPTH))


def _nextgeneration_state(recorded: dict) -> dict:
    """The same issue's state once a second candidate has been frozen."""
    return {
        **recorded,
        **_support.generation_state(_support.late_generation(generation=_support.NEXT_GENERATION)),
    }


if __name__ == "__main__":
    unittest.main()
