# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing reply's task snapshot leaves the workflow to read, and what it is bound to on a retry.

The workflow reads a reply with its attachment taken out: a reply carrying
nothing else is silent, and no park quotes the line. Every finished reply was
asked for one, so a reply without it -- with no report outcome either -- is a
missing snapshot. The report reader frames the reply inside the recorder's
own boundary, so a framing that fails is a diagnostic and the report it
spares is published as ever.

An `/orchestrator continue` retry beside a body edit hands a resumed
conversation nothing, so its snapshot keeps the baseline that conversation
was last handed; a retry that opens a fresh conversation re-grounds it on the
issue as it now reads, so its snapshot is bound to that edit.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import content_hash as _content_hash, report_outcomes as _outcomes
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_EDITED = "Require the red variant rather than blue."

_SESSION = "original-session"

# The trusted human's bare retry, above the park.
_RETRY_ID = 1100
_RETRY = FakeComment(id=_RETRY_ID, body="/orchestrator continue", user=FakeUser("alice"))

# A session failure an operator retries.
_SILENT = MappingProxyType({
    "awaiting_human": True,
    "park_reason": "agent_silent",
    "last_action_comment_id": 900,
    "dev_agent": "claude",
})


class _ParsesAfterOneFailure:
    """The report reader's message parse, failing the first time it is asked."""

    def __init__(self) -> None:
        self._parse = _outcomes._parse_report_outcome
        self._failures = [RuntimeError("report parse failed")]

    def __call__(self, message: str):
        """Fail once; parse as the reader does ever after."""
        if self._failures:
            raise self._failures.pop()
        return self._parse(message)


def _quoting_it(github) -> list[str]:
    """Every comment posted on the issue that quotes an attachment line."""
    return [body for _issue, body in github.posted_comments if "ANALYTICS:" in body]


class ReplyReadingTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """A first implementation's reply, as the workflow and the recorder read it."""

    def test_an_attachment_alone_reads_as_silence(self) -> None:
        # Parked as the silent failure an empty reply is, with no notice
        # quoting the line -- and the description still recorded.
        for message in ("", _support.SNAPSHOT):
            github, issue = self.seeded()
            silent = {**self.sunk, "has_new_commits": False}
            self.dispatch(github, issue, _support.returning(message), **silent)
            with self.subTest(message=message):
                self.assertEqual(github.pinned_data(_held.ISSUE).get("park_reason"), "agent_silent")
                self.assertEqual(_quoting_it(github), [])
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)["report_outcome"], "no_marker")

    def test_a_reply_without_it_is_missing(self) -> None:
        # Committed work and neither the attachment nor a report outcome.
        github, issue = self.seeded()
        self.dispatch(github, issue, _support.returning("Implemented and committed."), **self.committing)
        self.assertEqual(self.diagnosed(), [("missing", False)])

    def test_a_failed_framing_spares_the_report(self) -> None:
        # The recorder asks the report reader first, inside its boundary.
        github, issue = self.seeded()
        with patch.object(_outcomes, "_parse_report_outcome", _ParsesAfterOneFailure()):
            self.dispatch(github, issue, _support.returning(), **self.committing)
        self.assertEqual(self.diagnosed(), [("parse_failed", False)])
        self.published(github)


class RetrySnapshotTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """An operator's retry beside a body edit, resumed and fresh."""

    def test_a_resumed_retry_keeps_the_baseline(self) -> None:
        github, issue, baseline = self._edited(dev_session_id=_SESSION)
        ran = self.dispatch(github, issue, _support.returning(), **self._committed())
        self.assertNotIn(_EDITED, _support.prompt_of(ran))
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)[_support.REVISION], baseline)

    def test_a_fresh_retry_takes_the_edit(self) -> None:
        github, issue, baseline = self._edited()
        ran = self.dispatch(github, issue, _support.returning(), **self._committed())
        edited = _content_hash._compute_user_content_hash(issue, set())
        self.assertIn(_EDITED, _support.prompt_of(ran))
        self.assertNotEqual(edited, baseline)
        self.assertEqual(self._bound(), (edited, _support.reference(edited)))

    def _edited(self, **record):
        """The session failure parked, its body edited beside a trusted human's retry; the baseline it keeps."""
        github, issue = self.seeded(**_SILENT, **record)
        baseline = github.pinned_data(_held.ISSUE)["user_content_hash"]
        issue.body = f"{issue.body}\n{_EDITED}"
        issue.comments.append(_RETRY)
        return github, issue, baseline

    def _bound(self) -> tuple:
        """The requirements revision and task reference the one snapshot on the sink is bound to."""
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        return (snapshot[_support.REVISION], snapshot[_support.TASK_REF])

    def _committed(self) -> dict:
        """The seams of a retry whose branch carries commits, its analytics sink this test's."""
        return {**self.sunk, "has_new_commits": True}


if __name__ == "__main__":
    unittest.main()
