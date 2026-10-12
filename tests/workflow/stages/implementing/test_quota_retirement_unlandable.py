# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A quota retirement record that names no retirement a poller can land, and the developer launches it holds.

One that will not read has lost the conversation it named, and an arming
nothing resolved never knew it, so neither is ever landed: every developer
launch on the issue waits until an operator writes it again or settles it, and
a tick whose resume was planned over one launches nothing whatever the record
says by its launch. The attempt that left one behind is not held by it.
"""
from __future__ import annotations

import importlib
import json
import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator.workflow.stages.implementing import (
    quota_record as _quota_record,
    session as _session,
)
from tests.workflow.stages.implementing import (
    quota_retirement_test_support as quota,
    retry_test_support as support,
)

_QUOTA = quota.QUOTA
_PINNED_SESSION = quota.PINNED_SESSION
_FRESH_LAUNCH = quota.FRESH_LAUNCH
_PARK = quota.PARK
_PARKED = quota.PARKED
_PIN = quota.PIN
_RECORD = quota.RECORD
_RUNS = quota.RUNS
_launch = quota.launch
_retired = quota.retired
# The resume plan an operator's hand is let in behind.
_plan = _session._resolve_dev_session_for_resume


def _planned_then(record, written, *plan_args):
    """The resume plan, with the record at `record` written as `written` -- removed, for None -- once it is made."""
    plan = _plan(*plan_args)
    if written is None:
        record.unlink()
    else:
        record.write_text(json.dumps(written), encoding="utf-8")
    return plan


def _reported_unsettled(record):
    """A run that reports and commits while the record at `record` comes to take no write."""
    return quota.stops_after(record.chmod, quota.READ_ONLY, stop=quota.REPORTED)


class QuotaRetirementUnlandableRecordTest(quota.QuotaTicks, unittest.TestCase):
    """A record naming no retirement is never landed, and no developer launch
    it may stand in front of is made until an operator writes or settles it.
    """

    @quota.honors_modes
    def test_unsettled_arming_holds_later_launches(self) -> None:
        # A first spawn reports and leaves a commit, but the record it was
        # armed with has come to take no write, so its return cannot settle
        # it. No quota stopped the run, so its own tick goes on: the commit
        # publishes and the returned conversation is pinned. The arming left
        # standing names no retirement anyone can land, so the next developer
        # launch -- a resume of that conversation -- is refused, neither made
        # nor charged, until an operator settles the record.
        github, issue = self._issue()
        record = _quota_record._located(github, issue)
        self._spawned(github, issue, _reported_unsettled(record))
        record.chmod(quota.WRITABLE)

        self.assertEqual(
            (github.label_history, self._pinned(github, _PIN, _RUNS)),
            ([quota.VALIDATING], {_PIN: quota.FRESH_SESSION, _RUNS: 1}),
            "the run that left the arming standing still publishes",
        )
        run_agent = MagicMock(return_value=quota.REPORTED)
        refused = self._run_resume(github, issue, fake_run=run_agent, threshold=0)[1]
        self.assertEqual(
            (run_agent.called, refused.invoked, self._pinned(github, _RUNS)),
            (False, False, {_RUNS: 1}),
            "the next launch is refused uncharged",
        )

        record.write_text(json.dumps({}), encoding="utf-8")
        self._run_resume(github, issue, fake_run=run_agent, threshold=0)
        self.assertEqual(
            (_launch(run_agent)[0], self._pinned(github, _RUNS)),
            (quota.FRESH_SESSION, {_RUNS: 2}),
            "an operator's settlement lets the resume run, charged once",
        )

    def test_unreadable_record_holds_every_launch(self) -> None:
        # A fresh spawn's quota stop is never pinned, and its edit goes
        # unanswered, so the host's record alone names the conversation. That
        # record then reads as nothing a poller can trust -- text that is no
        # record, or bytes that are not even UTF-8 -- and the poller restarts.
        # With the name lost, nothing launches; once an operator writes the
        # record again, the retirement lands, and the fresh run that hands the
        # failed id back and publishes leaves it unpinned.
        for unreadable in (b"not a record", bytes([0xFF])):
            with self.subTest(unreadable=unreadable):
                github, issue = self._issue()
                record = _quota_record._located(github, issue)
                github.pinned_failures.refused.add(quota.ISSUE)
                self._tick(github, issue, _QUOTA, has_new_commits=False)
                record.write_bytes(unreadable)
                importlib.reload(_quota_record)
                github.pinned_failures.refused.clear()

                self.assertFalse(self._spawned(github, issue).called, "nothing launches while the name is lost")
                record.write_text(json.dumps({"session_id": _PINNED_SESSION}), encoding="utf-8")
                spawned = self._spawned(github, issue)

                self.assertEqual(
                    (
                        _launch(spawned),
                        self._pinned(github, _PIN, _RECORD),
                        github.label_history,
                        _quota_record._OwedRetirement.recorded(github, issue),
                    ),
                    (_FRESH_LAUNCH, {_PIN: None, _RECORD: _retired()}, [quota.VALIDATING], None),
                    "the repaired retirement lands and is owed no more, the handed-back id stays unpinned, "
                    "and the commit publishes",
                )

    def test_unreadable_record_holds_the_reply(self) -> None:
        # The same lost name on a parked issue: the reply's resume plan lands
        # nothing from a record that will not read, nothing the comment pins
        # stands in for the conversation it named, and the reply waits under
        # the park with nothing written.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        record = _quota_record._located(github, issue)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_bytes(b"not a record")

        held = self._replied(github, issue, quota.HANDED_BACK)

        self.assertEqual(
            (
                held.called,
                github.posted_comments,
                self._pinned(github, _PIN, _RECORD, *_PARK),
                record.exists(),
            ),
            (False, [], {_PIN: _PINNED_SESSION, _RECORD: None, **_PARK}, True),
        )

    def test_record_rewritten_after_plan_holds_tick(self) -> None:
        # The reply's resume is planned over a record that will not read, so
        # over the pinned conversation that record may name, and an operator
        # then writes it again naming that conversation -- or removes it --
        # before the launch. That tick launches nothing either way and posts
        # nothing; the tick after it plans over what the record then says, a
        # fresh conversation where it retires the pinned one.
        for written, relaunched in (({"session_id": _PINNED_SESSION}, None), (None, _PINNED_SESSION)):
            with self.subTest(written=written):
                github, issue = self._issue(**_PARKED)
                quota.reply(github, issue, support.GUIDANCE_REPLY)
                record = _quota_record._located(github, issue)
                record.parent.mkdir(parents=True, exist_ok=True)
                record.write_bytes(b"not a record")
                with patch.object(_session, "_resolve_dev_session_for_resume", partial(_planned_then, record, written)):
                    self.assertFalse(self._replied(github, issue).called, "the tick planned over it launches nothing")
                self.assertEqual(github.posted_comments, [], "and posts nothing")

                self.assertEqual(_launch(self._replied(github, issue))[0], relaunched)


if __name__ == "__main__":
    unittest.main()
