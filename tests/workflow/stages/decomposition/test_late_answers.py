# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What reopens a categorized question, and what is refused instead."""
from __future__ import annotations

from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_content_support import LateContentCase
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    OTHER_SHA,
    SINGLE_REPLY,
    late_block,
)

NEEDS_GUIDANCE = "needs your actual guidance"

# What the adjudicator asks on the round AFTER its first question was answered.
SECOND_QUESTION = "and which of the two owns the migration?"

SECOND_QUESTION_REPLY = late_block(
    '{"decision": "question", "category": "scope_ambiguous",'
    f' "question": "{SECOND_QUESTION}"}}'
)


class RecordedQuestionTest(LateContentCase):
    """Only a real answer reopens a question the adjudicator recorded."""

    def test_a_real_answer_drops_the_record(self) -> None:
        self._seed(**_support.ASKED_STATE)
        _support.reply(self.issue)

        outcome, spawn = self._run(SINGLE_REPLY)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_called_once()
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.verdict], str(LateVerdict.SINGLE))
        # The question this answered is gone: what the issue waits on now is
        # the decision the fresh verdict earned, not the one it replaced.
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_SINGLE_DECISION)

    def test_the_answer_reaches_the_agent_that_asked(self) -> None:
        # A question is a conversation, and the pin exists so the answer can
        # continue it: a fresh run would have to be told what it had asked
        # before it could be told the answer.
        self._seed(**_support.ASKED_STATE)
        _support.reply(self.issue)

        _outcome, spawn = self._run()

        self.assertEqual(
            spawn.call_args.kwargs["resume_session_id"], _support.LATE_SESSION,
        )

    def test_a_stale_session_is_not_resumed(self) -> None:
        # A session opened against a commit that has since been replaced holds
        # a conversation about work nobody is adjudicating.
        self._seed(**{
            **_support.ASKED_STATE, KEYS.source_sha: OTHER_SHA,
        })
        _support.reply(self.issue)

        _outcome, spawn = self._run()

        # The tracked runner forwards the kwarg only when there is a session
        # to resume, so a fresh conversation is its absence.
        self.assertNotIn("resume_session_id", spawn.call_args.kwargs)

    def test_a_second_question_is_announced_too(self) -> None:
        # Q1 answered, and the resumed adjudicator asks Q2. A park quieted
        # because its REASON matches the one just answered would leave that
        # second question recorded, durable, and never said out loud.
        self._seed(**_support.ASKED_STATE)
        _support.reply(self.issue)

        outcome, _spawn = self._run(SECOND_QUESTION_REPLY)

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.question], SECOND_QUESTION)
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_QUESTION)
        self.assertTrue(
            any(SECOND_QUESTION in body for body in self._bodies()),
        )

    def test_a_bare_continue_is_refused_once(self) -> None:
        # "Proceed" is not an answer to "which half of this is in scope", and
        # letting it through would record a `single` nobody decided. The
        # command is consumed, so the refusal is not re-posted every tick.
        self._seed(**_support.ASKED_STATE)
        _support.reply(self.issue, _support.BARE_CONTINUE)

        outcome, spawn = self._run()
        self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.verdict], str(LateVerdict.QUESTION))
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_QUESTION)
        self.assertEqual(
            len([body for body in self._bodies() if NEEDS_GUIDANCE in body]),
            1,
        )

    def test_a_certificate_re_earns_the_verdict(self) -> None:
        # A bare continue on a DRIFT park vouches for the commit, not for an
        # answer taken against requirements that have since moved -- acting on
        # one would be the drift rule refused a step later.
        self._seed(**_support.ASKED_STATE)
        self.issue.title = _support.EDITED_TITLE
        self._run()
        _support.reply(self.issue, _support.BARE_CONTINUE)

        outcome, spawn = self._run(SINGLE_REPLY)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_called_once()
        self.assertEqual(
            self._pinned()[KEYS.verdict], str(LateVerdict.SINGLE),
        )

    def test_baselined_conversation_is_not_an_answer(self) -> None:
        # A baseline covers what the issue already said, so a comment the
        # adjudication was frozen beside cannot reopen the question it asked
        # -- the recorded outcome is reused instead of re-earned.
        self._seed(comments=(_support.guidance_comment(),), **_support.ASKED_STATE)

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(outcome.run.verdict, LateVerdict.QUESTION)
        spawn.assert_not_called()
