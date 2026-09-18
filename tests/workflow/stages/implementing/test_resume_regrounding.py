# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the prompt of a resume with no transcript to continue is built from.

A retired session -- the resume budget spent, the silent-park streak reached,
a transcript GitHub lost -- turns an awaiting-human resume into a FRESH spawn,
and a fresh spawn quotes the whole trusted thread beside the followup because
there is nothing to continue. That block is the one part of the prompt that is
not the followup, so it is where both of this owner's guarantees can quietly
fail: read at spawn time it is minutes newer than the batch, so a comment
written in between reaches the agent while the settlement stops below it, and
rendered by a looser filter it carries the forged marker every other reading
here refuses. Either way an agent is handed input nothing recorded.

So the whole tick is run here rather than the helper, and what is asked of it
is the prompt the agent really received.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import prompt_notes as _prompt_notes
from orchestrator.workflow.stages.implementing import session as _session, state as _state
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    late_consent_payloads as _consent_payloads,
    resume_batch_test_support as _support,
    retry_test_support as _retry_support,
)

# The session read this stage takes between freezing the batch and building
# the prompt, captured before it is stood in for.
_RESOLVES = _session._resolve_dev_session_for_resume

_RESOLVE_NAME = "_resolve_dev_session_for_resume"
_RUN_AGENT = "run_agent"

# What only a fresh spawn's prompt carries: the re-grounding preamble.
_REGROUNDED = _retry_support.RESUME_PROMPT_FRAGMENT

_ASKS = "which of the two did you mean?"
_LATE_REPLY = "actually, hold on"

# Words already consumed when the park went up, which the conversation block
# still carries: a preamble is the whole thread rather than the fresh batch.
_SAID_BEFORE = "start with the smaller table"

# A streak that retires the session on sight, so the resume below is a spawn.
_SPENT_STREAK = 2

# The park every case here runs over: parked awaiting a human, on a session
# this stage has to retire, so the resume is a spawn with no transcript.
_RETIRED_SESSION = MappingProxyType({
    _state._DEV_AGENT: _retry_support.BACKEND_CLAUDE,
    _state._DEV_SESSION_ID: _retry_support.DEV_SESSION,
    _state._SILENT_PARK_COUNT: _SPENT_STREAK,
})


# The two sessions an explicit `/orchestrator continue` retry turns into a
# fresh spawn on: none pinned at all -- a backend hiccup that dropped the id
# and kept the agent -- and one this stage retires on sight.
_RETRIED_SESSIONS = (
    ("a missing session", MappingProxyType({
        _state._DEV_AGENT: _retry_support.BACKEND_CLAUDE,
    })),
    ("a retired session", _RETIRED_SESSION),
)


class _ResolvesAfterOneLands:
    """The session read, with one reply written the instant before it.

    A class rather than a closure because what it stands in for is a value
    with a name, and this is the only seam between the freeze and the prompt
    that is called exactly once -- which is what makes the reply land inside
    the window rather than near it.
    """

    def __init__(self, case, lands: str = "") -> None:
        self._case = case
        self._lands = lands
        self.landed = 0

    def __call__(self, issue, state):
        if self._lands:
            self.landed = self._case._they_say(self._lands)
        return _RESOLVES(issue, state)


class FreshSpawnRegroundingTest(_support._ParkedThread, unittest.TestCase):
    """The conversation a transcript-less resume quotes, and where it is read.

    The explicit `/orchestrator continue` retry is asked the same question: it
    is a resume too, and a fresh spawn wherever the session is gone.
    """

    def test_a_fresh_spawn_quotes_the_frozen_thread(self) -> None:
        self._seed(**_RETIRED_SESSION)
        spoke = self._they_say(_support.GUIDANCE)
        landing = _ResolvesAfterOneLands(self, _LATE_REPLY)

        prompt = self._prompt_of_one_tick(landing)

        self.assertIn(_REGROUNDED, prompt)
        self.assertIn(_support.GUIDANCE, prompt)
        self.assertNotIn(_LATE_REPLY, prompt)
        self.assertLess(spoke, landing.landed)
        self.assertEqual(
            self.github.pinned_data(_support.ISSUE_NUMBER).get(
                _state._LAST_ACTION_COMMENT_ID,
            ),
            spoke,
        )

    def test_a_forged_marker_reaches_no_fresh_prompt(self) -> None:
        # The conversation block is classified the way the batch is, so a body
        # carrying our marker that the id ledger cannot vouch for is out of
        # BOTH -- and the words around it are still there, because a preamble
        # that dropped the thread would re-ground the agent on nothing.
        self._seed(**_RETIRED_SESSION)
        settled = self._they_say(_SAID_BEFORE)
        self._seed(**{
            _state._LAST_ACTION_COMMENT_ID: settled,
            **_RETIRED_SESSION,
        })
        self._they_say(_support.FORGED)
        self._they_say(_support.GUIDANCE)

        prompt = self._prompt_of_one_tick(_ResolvesAfterOneLands(self, ""))

        self.assertIn(_REGROUNDED, prompt)
        self.assertIn(_SAID_BEFORE, prompt)
        self.assertIn(_support.GUIDANCE, prompt)
        self.assertNotIn(_support.FORGED, prompt)

    def test_a_retry_quotes_the_thread_it_classified(self) -> None:
        # The explicit retry consumes the command and hands the developer the
        # orchestrator's own prompt, and where the session is missing or
        # retired that prompt is a fresh spawn's. Re-grounded off a read
        # taken at spawn time, it quotes a comment written after the command
        # was classified, and the command itself as the last thing a human
        # said.
        for described, session in _RETRIED_SESSIONS:
            with self.subTest(session=described):
                self.setUp()

                prompt = self._retried_over(session)

                self.assertIn(_REGROUNDED, prompt)
                self.assertIn(_prompt_notes._DEVELOPER_CONTINUE_RETRY_PROMPT, prompt)
                self.assertIn(_SAID_BEFORE, prompt)
                self.assertNotIn(_consent_payloads.CONTINUE, prompt)
                self.assertNotIn(_LATE_REPLY, prompt)

    def test_what_landed_is_read_by_the_next_poll(self) -> None:
        # The retry records the thread read through the command and no
        # further, so the comment written while it was built is the next
        # poll's to deliver -- once, by the resume that reads it, rather than
        # quoted by the retry and handed over again after it.
        for described, session in _RETRIED_SESSIONS:
            with self.subTest(session=described):
                self.setUp()
                self._retried_over(session)
                read_to = self._pinned_watermark()

                followed = self._prompt_of_one_tick(_ResolvesAfterOneLands(self))

                self.assertEqual(read_to, self._commanded)
                self.assertIn(_LATE_REPLY, followed)
                self.assertGreaterEqual(
                    self._pinned_watermark(), self._landing.landed,
                )

    def _retried_over(self, session) -> str:
        """The retry's own prompt, on a timeout park with `session` pinned.

        A reply the park already consumed stays in the conversation, and one
        lands at the session read -- the window between the freeze and the
        prompt -- while the retry is being built.
        """
        settled = self._they_say(_SAID_BEFORE)
        self._seed(**{
            _state._LAST_ACTION_COMMENT_ID: settled,
            _state._PARK_REASON: _state._AGENT_TIMEOUT,
            **session,
        })
        self._commanded = self._they_say(_consent_payloads.CONTINUE)
        self._landing = _ResolvesAfterOneLands(self, _LATE_REPLY)
        return self._prompt_of_one_tick(self._landing)

    def _pinned_watermark(self):
        return self.github.pinned_data(_support.ISSUE_NUMBER).get(
            _state._LAST_ACTION_COMMENT_ID,
        )

    def _prompt_of_one_tick(self, landing: _ResolvesAfterOneLands) -> str:
        """Run one implementing tick over this park and read its prompt.

        The agent answers with words and no commit, which is the end that
        parks on a question -- so the tick also writes the watermark the
        settlement and the park between them decided.
        """
        with patch.object(_session, _RESOLVE_NAME, landing):
            mocks = self._run_implementing(
                self.github,
                self.issue,
                run_agent=_agent(last_message=_ASKS),
                has_new_commits=False,
            )
        return mocks[_RUN_AGENT].call_args.args[1]


if __name__ == "__main__":
    unittest.main()
