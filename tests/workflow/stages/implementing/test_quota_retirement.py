# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An AGY account quota retiring the developer conversation it stopped, tick by tick.

Synthetic Antigravity quota stops are driven through implementing ticks and
read back off the pinned comment: the conversation is retired whichever road
launched it and whatever the run left behind, the next permitted run is a
fresh conversation under the pinned command, and the retirement itself
launches, retries, and charges nothing. A retirement the comment would not
take is `test_quota_retirement_refusal`'s.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from tests.support import agy_stream as stream
from tests.workflow.agent_failure_values import agy_quota_stop
from tests.workflow.stages.implementing import (
    quota_retirement_test_support as quota,
    retry_test_support as support,
)

_RUN_AGENT = quota.RUN_AGENT
_AGENT_SILENT = quota.AGENT_SILENT
_QUOTA = quota.QUOTA
_UNNAMED_QUOTA = quota.UNNAMED_QUOTA
_PINNED_SESSION = quota.PINNED_SESSION
_FRESH_SESSION = quota.FRESH_SESSION
_REPORTED = quota.REPORTED
_FRESH_LAUNCH = quota.FRESH_LAUNCH
_PUBLISHES = quota.PUBLISHES
_SPAWN_PUBLISHES = quota.SPAWN_PUBLISHES
_PARK = quota.PARK
_PARKED = quota.PARKED
_VALIDATING = quota.VALIDATING
_COMMAND = quota.COMMAND
_PIN = quota.PIN
_RECORD = quota.RECORD
_RESUMES = quota.RESUMES
_STREAK = quota.STREAK
_AWAITING = quota.AWAITING
_PARKED_AS = quota.PARKED_AS
_RUNS = quota.RUNS
_RETRIES = quota.RETRIES
_retired = quota.retired
_launch = quota.launch
_reply = quota.reply


class QuotaRetirementLifecycleTest(quota.QuotaTicks, unittest.TestCase):
    """A conversation an account quota stopped is retired before any later developer launch."""

    def test_fresh_spawn_quota_recovers_fresh(self) -> None:
        # The step left running beside the quota buys no continuation: the one
        # attempt parks as the session limit with its conversation retired,
        # until a continue after the reset buys a fresh conversation over the
        # same checkout under the pinned command -- which, returning an id of
        # its own, ends the recovery and publishes.
        github, issue = self._issue()

        self._tick(github, issue, _QUOTA, has_new_commits=False)[_RUN_AGENT].assert_called_once()

        self.assertEqual(
            [event["reason"] for event in github.recorded_events if event["event"] == "park_awaiting_human"],
            [quota.QUOTA_REASON],
        )
        self.assertEqual(
            self._pinned(github, _COMMAND, _PIN, _RECORD, _RESUMES, _STREAK, _AWAITING, _PARKED_AS, _RUNS, _RETRIES),
            {
                _COMMAND: stream.SPEC, _PIN: None, _RECORD: _retired(), _RESUMES: 0, _STREAK: 1,
                _AWAITING: True, _PARKED_AS: _AGENT_SILENT, _RUNS: 1, _RETRIES: 1,
            },
            "one run charged, its conversation retired, and the issue parked for a human",
        )

        _reply(github, issue, support.CONTINUE_COMMAND)
        recovered = self._tick(github, issue, _REPORTED, **_PUBLISHES)[_RUN_AGENT]

        self.assertEqual(_launch(recovered), _FRESH_LAUNCH)
        self.assertIn(support.IMPLEMENT_PROMPT_FRAGMENT, recovered.call_args.args[1], "re-grounded on the issue")
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _RUNS),
            {_PIN: _FRESH_SESSION, _RECORD: _retired(pending=False), _RUNS: 2},
        )
        self.assertEqual(github.label_history, [_VALIDATING])

    def test_resumed_quota_retires_its_launch(self) -> None:
        # A continue resumes the pinned conversation and the quota stops it
        # again with no conversation named, so the one the attempt resumed is
        # retired; neither budget a resume answers to is charged for it. The
        # next continue's fresh run hands that id back and publishes, and the
        # publication pins nothing.
        github, issue = self._issue(**_PARKED)
        _reply(github, issue, support.CONTINUE_COMMAND)

        resumed = self._tick(github, issue, _UNNAMED_QUOTA, has_new_commits=False)[_RUN_AGENT]

        self.assertEqual(_launch(resumed)[0], _PINNED_SESSION)
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _RESUMES, _STREAK, _AWAITING, _PARKED_AS, _RUNS, _RETRIES),
            {
                _PIN: None, _RECORD: _retired(), _RESUMES: 0, _STREAK: 1,
                _AWAITING: True, _PARKED_AS: _AGENT_SILENT, _RUNS: 1, _RETRIES: _PARKED[_RETRIES],
            },
            "the counters start over for the fresh conversation, and the park counts this stop on them",
        )

        _reply(github, issue, support.CONTINUE_COMMAND)
        recovered = self._tick(github, issue, quota.HANDED_BACK, **_PUBLISHES)[_RUN_AGENT]

        self.assertEqual(_launch(recovered), _FRESH_LAUNCH)
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _AWAITING),
            {_PIN: None, _RECORD: _retired(), _AWAITING: False},
            "the retired id is never pinned again, and the fresh conversation stays owed",
        )
        self.assertEqual(github.label_history, [_VALIDATING])

    def test_committed_quota_stays_retired(self) -> None:
        # The quota stopped a run that had already committed over a clean
        # tree: the commit publishes through the report gate's incomplete-run
        # waiver and the issue moves on to review, a write that zeroes every
        # counter a rotation reads. The next developer launch any stage makes
        # is still a fresh conversation.
        github, issue = self._issue()

        self._tick(github, issue, agy_quota_stop(), **_SPAWN_PUBLISHES)

        self.assertEqual(github.label_history, [_VALIDATING])
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _STREAK),
            {_PIN: None, _RECORD: _retired(), _STREAK: 0},
        )
        run_agent = MagicMock(return_value=_REPORTED)
        self._run_resume(github, issue, fake_run=run_agent, threshold=0)
        self.assertEqual(_launch(run_agent), _FRESH_LAUNCH)

    def test_paused_quota_lands_only_the_retirement(self) -> None:
        # A human's guidance resumes the pinned conversation, the quota stops
        # it, and an operator pauses the issue while it ran. The tick writes
        # none of its disposition -- no notice, the reply unconsumed, the park
        # standing -- but the retirement it owes is on the comment, so the
        # reply the unpaused tick resumes on goes to a fresh conversation.
        github, issue = self._issue(**_PARKED)
        _reply(github, issue, support.GUIDANCE_REPLY)

        with self._paused(github):
            self._tick(github, issue, _QUOTA, has_new_commits=False)

        self.assertEqual(github.posted_comments, [])
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _RESUMES, _STREAK, *_PARK),
            {_PIN: None, _RECORD: _retired(), _RESUMES: 0, _STREAK: 0, **_PARK},
            "the park, its reason and the reply's watermark stand; only the retirement moved",
        )
        resumed = self._tick(github, issue, _REPORTED, **_PUBLISHES)[_RUN_AGENT]
        self.assertEqual(_launch(resumed), _FRESH_LAUNCH)


if __name__ == "__main__":
    unittest.main()
