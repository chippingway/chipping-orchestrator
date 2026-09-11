# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent-budget park a late tick meets with its sentence still unsaid.

Two owners can have taken a `retry_cap` park under `workflow:decomposing`, and
they record what it owes the thread on different fields. The late adjudication
writes `late_park_notice` and says it from inside its own tick; the shared
parking form writes `retry_cap_notice`, and the only thing that says that one
is the replay at stage entry -- which stands down, saying nothing, for exactly
one reason: a thread it could not read.

The late hold runs the very next step. So the tick is driven through the stage
handler rather than through the coordinator, because the whole subject is what
the second step does about the first step's silence: a second read taken there
is as likely to succeed as the first was to fail, and a park read as explained
would buy an adjudication with a command written before the human was ever
asked anything.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.fixtures import _agent, _iso_hours_ago
from tests.workflow.stages.decomposition import late_retry_cap_support as _support
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _DecomposingWorkflowMixin,
)
from tests.workflow.stages.decomposition.late_content_support import (
    PARK_NOTICE_ID,
    late_issue,
)
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    LATE_ISSUE_NUMBER,
)
from tests.workflow.stages.decomposition.retry_cap_support import (
    FirstReadFails,
)

RUN_AGENT = "run_agent"


class StrandedSharedNoticeTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """A park recorded on the shared field, on a thread nobody could read."""

    def setUp(self) -> None:
        seeded = late_issue(**{
            KEYS.awaiting: True,
            KEYS.park_reason: _support.PARK_RETRY_CAP,
            _support.KEY_RETRY_CAP_STAGE: _support.STAGE_DECOMPOSING,
            _support.KEY_RETRY_CAP_NOTICE: _support.NOTICE,
            KEYS.retry_count: _support.CAP,
            KEYS.retry_window: _iso_hours_ago(1),
            _support.KEY_LAST_ACTION_COMMENT_ID: PARK_NOTICE_ID,
        })
        self.github = seeded[0]
        self.issue = seeded[1]
        # The words a human wrote before anybody told them the issue had
        # stopped: a real command, and no answer at all to a question that has
        # never been put.
        self.issue.comments.append(_support.trusted(_support.CONTINUE_COMMAND))
        self.standing = self.github.pinned_data(LATE_ISSUE_NUMBER)

    def test_the_late_hold_reads_the_shared_field_too(self) -> None:
        flaky = FirstReadFails(self.github)

        with patch.object(self.github, "comments_after", flaky):
            mocks = self._run_decomposing(
                self.github, self.issue, run_agent=_agent(),
            )

        # One read, the replay's own. A second would have succeeded, found the
        # command, and bought an adjudication off it.
        self.assertEqual(flaky.calls, 1)
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self.github.posted_comments, [])
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(
            self.github.pinned_data(LATE_ISSUE_NUMBER), self.standing,
        )
        # The refusal is still countable, so an operator sees a park that goes
        # on holding rather than an adjudication that went quiet.
        self.assertEqual(
            [
                record["phase"] for record in self.github.recorded_events
                if record["event"] == _support.RETRY_CAP_EVENT
            ],
            [_support.PHASE_STANDING],
        )

    def test_the_replay_says_it_once_the_thread_reads(self) -> None:
        # The other half of the same contract: the hold is a deferral, not a
        # silence. The tick after the read recovers says the sentence, and the
        # delivery consumes the command written before it -- which is why the
        # tick above was not allowed to act on it.
        mocks = self._run_decomposing(
            self.github, self.issue, run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        said = [body for _, body in self.github.posted_comments]
        self.assertEqual(len(said), 1)
        self.assertIn(_support.NOTICE, said[0])
        pinned = self.github.pinned_data(LATE_ISSUE_NUMBER)
        self.assertEqual(pinned.get(KEYS.park_reason), _support.PARK_RETRY_CAP)
        self.assertNotIn(_support.KEY_RETRY_CAP_NOTICE, pinned)
        self.assertNotIn(KEYS.retry_grant, pinned)


if __name__ == "__main__":
    unittest.main()
