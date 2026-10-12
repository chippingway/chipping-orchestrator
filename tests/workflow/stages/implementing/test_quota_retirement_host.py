# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The host record a quota retirement is owed from, and the developer launches it holds.

Every Antigravity launch is armed with the record first, owing the retirement
of the conversation it runs until its return clears it, so a quota stop's
obligation is on the host before the stop is known and outlives a failed write
and a restart alike. A launch the host will not arm is not made, and a record a
commit has landed owes nothing once it is cleared. A record that names no
retirement a poller can land is `test_quota_retirement_unlandable`'s.
"""
from __future__ import annotations

import importlib
import json
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.stages.implementing import quota_record as _quota_record
from tests.workflow.stages.implementing import (
    quota_retirement_test_support as quota,
    retry_test_support as support,
)

_PINNED_SESSION = quota.PINNED_SESSION
_FRESH_SESSION = quota.FRESH_SESSION
_FRESH_LAUNCH = quota.FRESH_LAUNCH
_PARK = quota.PARK
_PARKED = quota.PARKED
_PIN = quota.PIN
_RECORD = quota.RECORD
_RUNS = quota.RUNS
_launch = quota.launch
_retired = quota.retired
_honors_modes = quota.honors_modes


def _another_poller():
    """A second poller on the host: the same record and comment, and none of this process's memory of either."""
    return patch.multiple(_quota_record, _unwritten={}, _armed={})


def _refusing(record, stop=quota.QUOTA):
    """A run ending in `stop` while the record at `record` comes to take no write."""
    return quota.stops_after(record.chmod, quota.READ_ONLY, stop=stop)


def _freezing(case, record, stop=quota.QUOTA):
    """A run ending in `stop` while the namespace `record` belongs in comes to take no new entry, thawed after it."""
    case.addCleanup(record.parent.chmod, quota.WRITABLE)
    return quota.stops_after(record.parent.chmod, quota.FROZEN, stop=stop)


def _blocked(record) -> None:
    """A directory standing in place of the record at `record`, so nothing can be written there."""
    record.unlink()
    record.mkdir()


def _frozen_namespace(record, repo_id):
    """The namespace `record` belongs in, holding the issue's claim file and no record, made to take no new entry."""
    record.parent.mkdir(parents=True, exist_ok=True)
    record.unlink(missing_ok=True)
    _writer_claims.claim_path(repo_id, quota.ISSUE).touch()
    record.parent.chmod(quota.FROZEN)
    return record.parent


def _frozen_record(record, _repo_id):
    """The record at `record`, owing nothing, made to take no write."""
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({}), encoding="utf-8")
    record.chmod(quota.READ_ONLY)
    return record


class QuotaRetirementHostRecordTest(quota.QuotaTicks, unittest.TestCase):
    """The record beside the issue's writer claim holds every developer launch
    it has to, in this process or one restarted on the same host, and none it
    has already been landed for.
    """

    @_honors_modes
    def test_failed_write_keeps_the_armed_record(self) -> None:
        # The resume of the pinned conversation is armed, and the record comes
        # to take no write while the run is out, so the quota stop cannot
        # resolve it; the edit goes unanswered. Once the record takes writes
        # again a second poller, sharing none of the first's memory, finds an
        # arming nothing resolved and launches nothing. The first poller writes
        # the resolution it held, which a restarted poller lands once the edit
        # is answered, and the reply goes to a fresh conversation.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        record = _quota_record._located(github, issue)
        github.pinned_failures.refused.add(quota.ISSUE)
        self._tick(github, issue, _refusing(record, quota.UNNAMED_QUOTA), has_new_commits=False)
        record.chmod(quota.WRITABLE)

        with _another_poller():
            held = [self._replied(github, issue).called]
        held += [self._replied(github, issue).called]
        importlib.reload(_quota_record)
        github.pinned_failures.refused.clear()
        held += [_launch(self._replied(github, issue))]

        self.assertEqual(
            (held, self._pinned(github, _PIN, _RECORD)),
            ([False, False, _FRESH_LAUNCH], {_PIN: _FRESH_SESSION, _RECORD: _retired(pending=False)}),
        )

    @_honors_modes
    def test_unresolved_arming_outlasts_a_restart(self) -> None:
        # A first spawn is armed naming no conversation, the quota stops it
        # naming its own, and neither the record nor the comment takes that
        # while the run is out. The poller restarts, and the edit is answered:
        # the arming names no conversation the restarted poller could retire,
        # so nothing launches -- not even a spawn whose run would hand the
        # stopped id back and publish it. Once an operator writes the
        # retirement the stop owed, it lands, and that run pins nothing.
        github, issue = self._issue()
        record = _quota_record._located(github, issue)
        github.pinned_failures.refused.add(quota.ISSUE)
        self._tick(github, issue, _refusing(record), has_new_commits=False)
        record.chmod(quota.WRITABLE)
        importlib.reload(_quota_record)
        github.pinned_failures.refused.clear()

        held = self._spawned(github, issue)
        record.write_text(json.dumps({"session_id": _PINNED_SESSION}), encoding="utf-8")
        spawned = self._spawned(github, issue)

        self.assertEqual(
            (held.called, _launch(spawned), self._pinned(github, _PIN, _RECORD)),
            (False, _FRESH_LAUNCH, {_PIN: None, _RECORD: _retired()}),
        )

    @_honors_modes
    def test_settled_record_outlasts_stale_memory(self) -> None:
        # A first spawn beside the pinned conversation is stopped by the quota
        # naming none, and neither the record nor the comment takes the
        # retirement, which the first poller keeps in memory. A second poller
        # holds on the arming nothing resolved until an operator resolves it;
        # then it lands it, settles the record, and publishes a fresh
        # conversation. The first poller's memory does not outlast that
        # settlement: its next resume runs on the fresh conversation, its
        # resume budget counted from that pin.
        github, issue = self._issue(dev_session_id=_PINNED_SESSION)
        record = _quota_record._located(github, issue)
        github.pinned_failures.refused.add(quota.ISSUE)
        self._tick(github, issue, _refusing(record, quota.UNNAMED_QUOTA), has_new_commits=False)
        record.chmod(quota.WRITABLE)
        github.pinned_failures.refused.clear()
        with _another_poller():
            self.assertFalse(self._spawned(github, issue, quota.REPORTED).called, "held until it is resolved")
            record.write_text(json.dumps({"session_id": None}), encoding="utf-8")
            self.assertTrue(self._spawned(github, issue, quota.REPORTED).called, "then landed and recovered")
        resumed = MagicMock(return_value=quota.REPORTED)

        state = self._run_resume(github, issue, fake_run=resumed, threshold=0)[0]

        self.assertEqual(_launch(resumed)[0], _FRESH_SESSION)
        self.assertEqual(
            {key: state.get(key) for key in (_PIN, quota.RESUMES, _RECORD)},
            {_PIN: _FRESH_SESSION, quota.RESUMES: 1, _RECORD: _retired(pending=False)},
        )

    @_honors_modes
    def test_landed_record_never_retires_its_recovery(self) -> None:
        # The namespace comes to take no new entry, nor let one go, while a
        # first spawn beside the pinned conversation is out, and the quota
        # stops it naming none. The retirement lands, and the record that
        # cannot be removed is written over as owing nothing, so nothing lands
        # it again: the continue's fresh conversation is pinned as the
        # recovery, and a later resume runs on it, its resume budget counted
        # from that pin and each of the three runs charged once.
        github, issue = self._issue(dev_session_id=_PINNED_SESSION)
        freezing = _freezing(self, _quota_record._located(github, issue), quota.UNNAMED_QUOTA)
        self._tick(github, issue, freezing, has_new_commits=False)
        quota.reply(github, issue, support.CONTINUE_COMMAND)
        self._tick(github, issue, quota.REPORTED, **quota.PUBLISHES)
        resumed = MagicMock(return_value=quota.REPORTED)

        state = self._run_resume(github, issue, fake_run=resumed, threshold=0)[0]

        self.assertEqual(
            (
                _launch(resumed)[0],
                self._pinned(github, _RUNS),
                {key: state.get(key) for key in (_PIN, quota.RESUMES, _RECORD)},
            ),
            (
                _FRESH_SESSION,
                {_RUNS: 3},
                {_PIN: _FRESH_SESSION, quota.RESUMES: 1, _RECORD: _retired(pending=False)},
            ),
        )

    @_honors_modes
    def test_unwritable_namespace_keeps_the_record(self) -> None:
        # Each tick takes the issue's writer claim on a file that stays
        # writable, but the namespace comes to take no new entry while the run
        # is out, and the edit landing the retirement goes unanswered. The
        # retirement is written over the record that launch was armed with,
        # in place, so the poller restarted after it takes the claim and still
        # launches nothing; once the edit is answered the reply goes to a fresh
        # conversation.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        github.pinned_failures.refused.add(quota.ISSUE)
        freezing = _freezing(self, _quota_record._located(github, issue))
        with _writer_claims.issue_writer(github.repo_id, quota.ISSUE):
            self._tick(github, issue, freezing, has_new_commits=False)
        importlib.reload(_quota_record)

        with _writer_claims.issue_writer(github.repo_id, quota.ISSUE) as claimed:
            self.assertEqual(
                (claimed, self._replied(github, issue).called, github.posted_comments),
                (True, False, []),
                "the restarted poller takes the claim, and launches and posts nothing",
            )

        github.pinned_failures.refused.clear()
        self.assertEqual(
            (_launch(self._replied(github, issue)), self._pinned(github, _PIN, _RECORD)),
            (_FRESH_LAUNCH, {_PIN: _FRESH_SESSION, _RECORD: _retired(pending=False)}),
        )

    @_honors_modes
    def test_host_keeping_no_record_holds_the_launch(self) -> None:
        # The host will not take the record an Antigravity launch is armed
        # with: the namespace holds the issue's claim file but takes no new
        # entry, or the record standing there takes no write. A quota stop
        # that launch met could be kept by this process alone, so the reply
        # waits under its park, uncharged and with nothing written, though the
        # writer claim is taken. Once the host takes the record again, the
        # reply resumes the pinned conversation, which nothing stopped.
        for freeze in (_frozen_namespace, _frozen_record):
            with self.subTest(frozen=freeze.__name__):
                github, issue = self._issue(**_PARKED)
                quota.reply(github, issue, support.GUIDANCE_REPLY)
                frozen = freeze(_quota_record._located(github, issue), github.repo_id)
                with _writer_claims.issue_writer(github.repo_id, quota.ISSUE) as claimed:
                    self.assertEqual(
                        (
                            claimed,
                            self._replied(github, issue).called,
                            github.posted_comments,
                            self._pinned(github, _RUNS, *_PARK),
                        ),
                        (True, False, [], {_RUNS: None, **_PARK}),
                    )

                frozen.chmod(quota.WRITABLE)
                self.assertEqual(_launch(self._replied(github, issue))[0], _PINNED_SESSION)

    def test_unwritten_record_holds_every_launch(self) -> None:
        # Neither the host nor the comment takes the retirement: a directory
        # comes to stand in place of the record while the run is out, and the
        # edit goes unanswered. The poller that owes it keeps it in its own
        # memory, and a second poller on the host, sharing none of that memory,
        # reads the blocked record as one that will not read -- owed all the
        # same -- so neither of them launches anything. Once the host takes the
        # record the first poller writes it there, a restarted poller reads it,
        # and once the edit is answered the reply goes to a fresh conversation.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        blocked = _quota_record._located(github, issue)
        github.pinned_failures.refused.add(quota.ISSUE)
        self._tick(github, issue, quota.stops_after(_blocked, blocked), has_new_commits=False)

        with patch.object(_quota_record, "_unwritten", {}):
            held = [self._replied(github, issue).called]
        held += [self._replied(github, issue).called]
        blocked.rmdir()
        held += [self._replied(github, issue).called]
        importlib.reload(_quota_record)
        github.pinned_failures.refused.clear()
        resumed = self._replied(github, issue)

        self.assertEqual(
            (held, _launch(resumed), self._pinned(github, _PIN, _RECORD)),
            ([False, False, False], _FRESH_LAUNCH, {_PIN: _FRESH_SESSION, _RECORD: _retired(pending=False)}),
            "the second poller, the first, and the first once its record is written all hold; then it lands",
        )


if __name__ == "__main__":
    unittest.main()
