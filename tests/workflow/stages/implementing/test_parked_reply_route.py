# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reply to a park is the frozen batch's to deliver, not the drift road's.

A trusted reply moves the requirements fingerprint, and the drift check runs
ahead of the resume -- so over the baseline a real park carries, a reply would
take the drift road: a separate read quoting the whole thread, pasted markers
and control commands included, and a watermark stamped at the tip before the
run. Measured by what the park had already read, only a real edit is drift,
and the settlement records the requirements through the reply it delivered,
so the next poll does not answer that reply again.

Every tick here runs the whole handler over a park seeded with that baseline.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import messages as _messages
from orchestrator.workflow.stages.implementing import (
    resume_batch as _resume_batch,
    state as _state,
)
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_payloads as _consent_payloads,
    resume_batch_test_support as _support,
)

_RUN_AGENT = "run_agent"
_PROMPT_ARGUMENT = 1
_ASKS = "which of the two did you mean?"
_DRIFT_NOTICE = "issue body changed"
_EDITED_BODY = "the requirements, rewritten while the issue was parked"

# The opening line of the prompt an explicit retry issues.
_RETRIED = "Resuming after a session/usage limit"

# The locked session a resume continues.
_SESSION = MappingProxyType({
    _state._DEV_AGENT: "claude", _state._DEV_SESSION_ID: "dev-sess",
})

# The replies a question park is answered with, and the one of them that must
# reach no developer: a pasted marker, and a run-grant command already answered.
_REPLIES = (
    ("guidance beside a pasted marker", (_support.GUIDANCE, _support.FORGED), _support.FORGED),
    ("guidance under an answered grant", (
        _consent_payloads.ANSWERED_GRANT, _support.GUIDANCE,
    ), _consent_payloads.ANSWERED_GRANT),
)


class _ClassifiedAsOneLands:
    """The continue classifier, with a bare command written as it classifies.

    A class rather than a closure because the classifier this repository
    patches is a value with a name, and the command has to land after the one
    read the tick answers from and before anything it hands on runs.
    """

    def __init__(self, case) -> None:
        self._case = case
        self._classify = _messages._continue_command_action
        self.landed = 0

    def __call__(self, replies, park_reason) -> str:
        self.landed = self._case._they_say(_consent_payloads.CONTINUE)
        return self._classify(replies, park_reason)


class ParkedReplyRouteTest(_support._ParkedThread, unittest.TestCase):
    """The whole implementing tick over a park and the replies to it."""

    def test_a_reply_reaches_the_resume(self) -> None:
        # Delivered by the batch -- filtered as a prompt is -- and settled
        # with the requirements it answers, so the poll after it is quiet.
        for described, thread, withheld in _REPLIES:
            with self.subTest(thread=described):
                self.setUp()
                self._assert_delivered(thread, withheld)

    def test_an_edit_to_the_body_is_still_drift(self) -> None:
        # What the park had not read moved, so the drift road answers the tick
        # and quotes the edited requirements.
        self._seed(**_SESSION)
        self._they_say(_support.GUIDANCE)
        self.issue.body = _EDITED_BODY

        prompt = self._prompt_of(self._tick())

        self.assertIn(_EDITED_BODY, prompt)
        self.assertTrue(_drift_said(self.github))

    def test_one_read_answers_the_whole_tick(self) -> None:
        # Mixed guidance passes the classifier through to the resume, and a
        # bare continue written as it classifies is in no part of this tick:
        # the developer is handed what was classified, the mark stops below
        # the late command, and the next poll retries on it as the command it
        # is rather than as prose.
        self._seed(**_SESSION, **{_state._PARK_REASON: _state._AGENT_TIMEOUT})
        self._they_say(_consent_payloads.CONTINUE)
        guided = self._they_say(_support.GUIDANCE)
        landing = _ClassifiedAsOneLands(self)

        with (
            patch.object(_messages, "_continue_command_action", side_effect=landing),
            patch.object(_resume_batch, "_freeze", wraps=_resume_batch._freeze) as frozen,
        ):
            prompt = self._prompt_of(self._tick(_agent(timed_out=True)))
            frozen.assert_called_once()

        self.assertIn(_support.GUIDANCE, prompt)
        self.assertEqual(self._pinned_watermark(), guided)
        self.assertLess(guided, landing.landed)
        self.assertIn(_RETRIED, self._prompt_of(self._tick()))

    def _assert_delivered(self, thread: tuple, withheld: str) -> None:
        self._seed(**_SESSION)
        replied = {said: self._they_say(said) for said in thread}

        prompt = self._prompt_of(self._tick())
        quiet = self._tick()

        self.assertIn(f"@{_support.TRUSTED_AUTHOR}: {_support.GUIDANCE}", prompt)
        self.assertNotIn(withheld, prompt)
        self.assertFalse(_drift_said(self.github))
        self.assertGreaterEqual(self._pinned_watermark(), replied[_support.GUIDANCE])
        quiet[_RUN_AGENT].assert_not_called()

    def _tick(self, answers=None):
        """One whole implementing tick, the agent answering with `answers`."""
        return self._run_implementing(
            self.github,
            self.issue,
            run_agent=answers or _agent(last_message=_ASKS),
            has_new_commits=False,
        )

    def _prompt_of(self, polled) -> str:
        polled[_RUN_AGENT].assert_called_once()
        return polled[_RUN_AGENT].call_args.args[_PROMPT_ARGUMENT]

    def _pinned_watermark(self):
        return self.github.pinned_data(_support.ISSUE_NUMBER)[_state._LAST_ACTION_COMMENT_ID]


class AuthorizationReplyRouteTest(_consent_case._ParkedCase, unittest.TestCase):
    """Guidance written over the command an authorization park waits on."""

    def test_the_command_reaches_no_prompt(self) -> None:
        # The guidance replaced the command, so the developer answers it --
        # handed the guidance alone, by the resume rather than the drift road.
        self._seed(**_consent_payloads.measured_pair(), **_SESSION)
        self._reply(_consent_payloads.AUTHORIZE)
        self._reply(_consent_payloads.GUIDANCE)

        polled = self._run_tick(
            run_agent=_agent(last_message=_ASKS), has_new_commits=False,
        )

        polled[_RUN_AGENT].assert_called_once()
        prompt = polled[_RUN_AGENT].call_args.args[_PROMPT_ARGUMENT]
        self.assertIn(_consent_payloads.GUIDANCE, prompt)
        self.assertNotIn(_consent_payloads.AUTHORIZE, prompt)
        self.assertFalse(_drift_said(self.github))


def _drift_said(github) -> bool:
    """Whether the drift road announced itself on this thread."""
    return any(_DRIFT_NOTICE in body for _, body in github.posted_comments)


if __name__ == "__main__":
    unittest.main()
