# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park an unreadable owner leaves, and how it gets itself out of one.

Nobody can answer "GitHub could not be asked", so the park a failed owner read
files is the one this mode has to clear itself. What brings a tick back to the
read is the pending check the generation records -- durable, and ahead of every
gate that would otherwise route past it -- and what it owes the thread once it
heals is one sentence retiring the mention it filed.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser
from tests.workflow.stages.decomposition import late_settlement_support as _support
from tests.workflow.stages.decomposition.late_run_support import adjudicate
from tests.workflow.stages.decomposition.late_settlement_support import GuardedLateCase
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    QUESTION_ASKED,
    UNDERSIZED_ADDITIONS,
    late_generation,
    seed_late_issue,
)

CATEGORY_SCOPE = "scope_ambiguous"

WRITE_PINNED_STATE = "write_pinned_state"

# The claim the guard makes before it reads. Everything after it on a
# healing tick is the retirement, which is what the kill below aims at.
WRITES_BEFORE_CLEAR = 1

# What the thread carries after the park, and after the follow-up retiring it.
SAID_ONCE = 1
SAID_AND_RETIRED = 2


class _LostClearWrite:
    """The write that CLEARS the park dies, once, after the follow-up posted.

    The healing tick writes twice: the claim that goes out before the read,
    and the clear that goes out after the sentence retiring the park. Only the
    second one is the boundary this ordering exists for -- fail the first and
    nothing has been said yet, so a retry that repeated the follow-up would
    not be caught at all.
    """

    def __init__(self, github, letting_through: int) -> None:
        self._write = github.write_pinned_state
        self._remaining = letting_through
        self._lost = False

    def __call__(self, issue, state):
        if self._remaining > 0:
            self._remaining -= 1
            return self._write(issue, state)
        if self._lost:
            return self._write(issue, state)
        self._lost = True
        raise RuntimeError("the process died here")


class _LostNoticeWrite:
    """The write recording a POSTED park notice as said dies, once.

    Aimed by content rather than by count, because what it has to hit is one
    specific pairing rather than the nth write of a tick: the park is standing
    and its obligation is gone, which is the state only the write that follows
    a comment GitHub took can be in. Everything before it lands, so the notice
    really is on the thread when the process stops.
    """

    def __init__(self, github) -> None:
        self._write = github.write_pinned_state
        self._lost = False

    def __call__(self, issue, state):
        settled = (
            state.get(KEYS.park_reason) == _support.PARK_OWNER_UNREADABLE
            and KEYS.park_notice not in state.data
        )
        if self._lost or not settled:
            return self._write(issue, state)
        self._lost = True
        raise RuntimeError("the process died here")


class TransientOwnerParkTest(GuardedLateCase, unittest.TestCase):
    """The park retries itself, quietly, and says one thing when it heals."""

    def test_the_retry_re_reads_without_respawning(self) -> None:
        # What failed was one GitHub read. The agent has already answered, so
        # the retry reconciles the read and reuses the record rather than
        # paying for a second adjudication that is free to decide otherwise.
        self._decide_unread()

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(len(outcome.guarded_split.children), _support.SPLIT_CHILDREN)
        self.assertFalse(self._pinned().get(KEYS.awaiting))

    def test_a_stuck_retry_repeats_no_notice(self) -> None:
        # Reconciliation runs on every eligible tick, so an unchanged park
        # must cost no second mention of the same wall.
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                parked = self._decide_unread()

                self.assertEqual(parked.disposition, _LateDisposition.PARKED)
                self.assertEqual(
                    self._pinned().get(KEYS.park_reason),
                    _support.PARK_OWNER_UNREADABLE,
                )

        self.assertEqual(len(self.github.posted_comments), 1)

    def test_a_healed_park_says_so_once(self) -> None:
        self._decide_unread()

        self._adjudicate()
        self._adjudicate()

        followups = self._followups()
        self.assertEqual(len(followups), 1)
        self.assertIn(_support.RECOVERED_PREFIX, followups[0])
        self.assertIn(_support.NO_ACTION_LINE, followups[0])
        # The point is to retire the alarming last word, not to notify again.
        self.assertNotIn("@", followups[0])

    def test_a_lost_clear_repeats_no_follow_up(self) -> None:
        # The exact crash boundary the ordering exists for: the follow-up IS
        # posted and the write that would clear the park never lands. The next
        # tick still owes the read, still finds the park standing, and finds
        # its own sentence already on the thread.
        self._seed_owing(_support.RECORDED_SPLIT)
        lost = patch.object(
            self.github,
            WRITE_PINNED_STATE,
            _LostClearWrite(self.github, letting_through=WRITES_BEFORE_CLEAR),
        )

        with lost, self.assertRaises(RuntimeError):
            self._adjudicate()

        # The sentence survived the write that did not.
        self.assertEqual(len(self._followups()), 1)
        self.assertTrue(self._pinned().get(KEYS.owner_check_pending))
        self.assertEqual(
            self._pinned().get(KEYS.park_reason), _support.PARK_OWNER_UNREADABLE,
        )

        outcome, _spawn = self._adjudicate()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(len(self._followups()), 1)
        self.assertNotIn(KEYS.owner_check_pending, self._pinned())

    def test_a_posted_follow_up_is_not_repeated(self) -> None:
        # The post and the write that clears the park cannot be one operation,
        # so the thread past the park's own mention is the only record of it
        # that survives a process dying between them.
        github, issue = _issue_parked_on_an_unreadable_owner()
        issue.comments.append(_posted_followup())

        adjudicate(github, issue)

        self.assertEqual(_followups_on(github), [])

    def test_a_lost_notice_write_still_recovers(self) -> None:
        # The other side of the same boundary: the park's OWN notice posts and
        # the write recording it as said never lands. Read back as still owed,
        # the healed tick would take it as proof that nobody was told and
        # clear the park without the follow-up it promises -- so the thread is
        # what settles it, and the sentence already there is not said twice.
        lost = patch.object(
            self.github, WRITE_PINNED_STATE, _LostNoticeWrite(self.github),
        )

        with (
            _support.unreadable_owner(self.github),
            lost,
            self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR),
            self.assertRaises(RuntimeError),
        ):
            self._decide()

        # The park was announced; the record of it having been announced was
        # what the write took down.
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertIn(KEYS.park_notice, self._pinned())

        outcome, _spawn = self._adjudicate()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(len(self._followups()), 1)
        self.assertEqual(len(self.github.posted_comments), SAID_AND_RETIRED)
        pinned = self._pinned()
        self.assertNotIn(KEYS.park_notice, pinned)
        self.assertFalse(pinned.get(KEYS.awaiting))

    def _followups(self) -> list:
        return _followups_on(self.github)


class PendingCheckRetryTest(GuardedLateCase, unittest.TestCase):
    """A read the generation still owes is taken before anything else."""

    def test_a_small_revision_still_re_reads(self) -> None:
        # A revision that came back under the ceiling is not adjudicable, so
        # nothing downstream of the size gate would ever reach the read again.
        self._seed_owing(additions=UNDERSIZED_ADDITIONS)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.NOT_LATE)
        pinned = self._pinned()
        self.assertNotIn(KEYS.owner_check_pending, pinned)
        self.assertFalse(pinned.get(KEYS.awaiting))
        self.assertEqual(len(self._followups()), 1)

    def test_it_precedes_the_spawn(self) -> None:
        # An oversized generation would otherwise pay for a second decomposer
        # before finding out whether anybody still wants the issue.
        self._seed_owing()

        outcome, spawn = self._decide_unread_run()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertTrue(self._pinned().get(KEYS.owner_check_pending))

    def test_a_closure_during_the_retry_cancels(self) -> None:
        self._seed_owing()
        self.issue.closed = True

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertNotIn(KEYS.owner_check_pending, pinned)

    def _decide_unread_run(self):
        with _support.unreadable_owner(self.github), self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR):
            return self._adjudicate()

    def _followups(self) -> list:
        return _followups_on(self.github)


def _followups_on(github) -> list:
    """The recovery follow-ups this mode has posted on the thread."""
    return [
        body for _number, body in github.posted_comments
        if _support.RECOVERY_FOLLOWUP_MARKER in body
    ]


def _posted_followup() -> FakeComment:
    """The follow-up a tick posted before the write recording it landed."""
    return FakeComment(
        id=_support.PARK_NOTICE_ID + 1,
        body=f"{_support.RECOVERED_PREFIX} whatever\n\n{_support.RECOVERY_FOLLOWUP_MARKER}",
        user=FakeUser("pichaautobot", "Bot"),
    )


def _issue_parked_on_an_unreadable_owner():
    """An issue a previous tick left parked on a read it could not take."""
    github = FakeGitHubClient()
    issue = seed_late_issue(
        github,
        late_generation(),
        **{
            KEYS.verdict: str(LateVerdict.QUESTION),
            KEYS.category: CATEGORY_SCOPE,
            KEYS.question: QUESTION_ASKED,
            KEYS.run_cycle_id: late_generation().cycle_id,
            KEYS.run_generation: late_generation().generation,
            KEYS.source_sha: CANDIDATE_SHA,
            KEYS.awaiting: True,
            KEYS.park_reason: _support.PARK_OWNER_UNREADABLE,
            _support.KEY_LAST_ACTION_COMMENT_ID: _support.PARK_NOTICE_ID,
        },
    )
    return github, issue



if __name__ == "__main__":
    unittest.main()
