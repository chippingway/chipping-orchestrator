# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An `/orchestrator continue` retry beside a body edit, which the conversation it resumes is never handed.

A retry hands its developer the retry prompt and nothing else: the resumed
conversation reads its own transcript, and an edit that landed beside the
command stays owed to the drift resume. So the retry's road freezes the
baseline the issue records, as the requirements its report answers. On its
own tick the report goes to the delivery stamped with that baseline, and
the binding leaves it owed for the drift resume rather than publishing it as
the edit's answer; held, its capture freezes the same baseline, and the
recovery retires it as past the requirements the issue now has. Neither
road ever stamps a report with an edit its developer did not see.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent, _reported
from tests.workflow.stages.implementing import held_capture_test_support as _held

_SESSION = "original-session"
_COMMAND_ID = 1100

# A session failure an operator retries, parked over a pinned conversation.
_SILENT = MappingProxyType({
    "awaiting_human": True,
    "park_reason": "agent_silent",
    "last_action_comment_id": 900,
    "dev_agent": "claude",
    _held.SESSION_PIN: _SESSION,
})

# The edit a human made to the body beside the command.
_EDITED = "Require the red variant rather than blue."

# Every record a developer report is stamped with its requirements in, the
# settled one first.
_SETTLED = "developer_report_current"
_REPORT_RECORDS = (_SETTLED, "developer_report_pending", "developer_report_delivered")


def _retried() -> FakeComment:
    """A trusted human's bare retry, above the park."""
    return FakeComment(id=_COMMAND_ID, body="/orchestrator continue", user=FakeUser("alice"))


def _stamped(record: dict) -> set:
    """The requirements every developer report `record` holds is stamped with."""
    return {
        report["requirements"] for report in map(record.get, _REPORT_RECORDS)
        if isinstance(report, dict)
    }


class RetryBesideAnEditTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A retry beside a body edit answers the baseline its conversation was handed, never the edit it did not see."""

    def test_its_own_tick_keeps_the_baseline(self) -> None:
        # Unpaused, the retry's report goes to the delivery stamped with the
        # baseline, and the binding leaves it owed for the drift resume rather
        # than publishing it as an answer to the edit.
        github, issue, baseline = self._edited()
        ran = self.dispatch(github, issue, self._finished(), has_new_commits=True)
        record = github.pinned_data(_held.ISSUE)
        self.assertNotIn(_EDITED, ran[_held.RUN_AGENT].call_args.args[1])
        self.assertEqual(
            (_stamped(record), record.get(_SETTLED)),
            ({baseline}, None),
        )

    def test_a_held_return_keeps_the_baseline(self) -> None:
        # Held, the capture freezes that same baseline. Recovered, the edit
        # leaves its report past what the issue now asks for: it is retired
        # with nothing recorded or opened, and the park waits on the retry.
        github, issue, baseline = self._edited()
        held = self.held_mid_run(github, issue, self._finished(), has_new_commits=True)
        self.unpaused(github, issue)
        record = github.pinned_data(_held.ISSUE)
        self.assertEqual(
            (held[_held.CAPTURED]["requirements"], record[_held.CAPTURED]["stage"]),
            (baseline, _held.RETIRED),
        )
        self.assertEqual(
            (_stamped(record), record["awaiting_human"], github.opened_prs),
            (set(), True, []),
        )

    def _edited(self):
        """The park, its body edited beside a trusted human's retry; the baseline the record keeps."""
        github, issue = self.seeded(**_SILENT)
        baseline = github.pinned_data(_held.ISSUE)["user_content_hash"]
        issue.body = f"{issue.body}\n{_EDITED}"
        issue.comments.append(_retried())
        return github, issue, baseline

    def _finished(self):
        """What the retried conversation comes back as: its report."""
        return _agent(session_id=_SESSION, last_message=_reported())


if __name__ == "__main__":
    unittest.main()
