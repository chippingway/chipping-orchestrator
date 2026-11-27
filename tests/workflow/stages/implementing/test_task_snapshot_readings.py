# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing reply's task snapshot leaves the workflow to read, and what it is bound to on a retry.

The workflow reads a reply with its attachment lines kept out, the analytics
sink on or off: a reply carrying nothing else is silent, no park quotes the
line, and one written inside the report block leaves the published report and
its digest as they would be without it. A line a fence encloses is code the report quotes, and
is published with it; and no line makes a report publishable -- neither one
a fence encloses above the markers nor one that is all a block holds -- each
recorded as the verdict the workflow reached. Every finished reply was asked
for one, so a reply without it -- with no report outcome either -- is a
missing snapshot. The reply is framed inside the recorder's own boundary, so a
framing that fails, once or every time it is asked, is a diagnostic and the
report it spares is published as ever.

An `/orchestrator continue` retry beside a body edit hands a resumed
conversation nothing, so its snapshot keeps the baseline that conversation
was last handed; a retry that opens a fresh conversation re-grounds it on the
issue as it now reads, so its snapshot is bound to that edit -- and so is the
snapshot of a later retry resuming that same conversation. Either way the
task reference names the revision the retry's report is stamped with, the
baseline a reviewer handed that report is told.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.github import developer_reports as _developer_reports
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_outcomes as _outcomes,
    task_snapshot_replies as _replies,
)
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_EDITED = "Require the red variant rather than blue."

_SESSION = "original-session"

# The trusted human's bare retry, above the park.
_RETRY_ID = 1100
_RETRY = FakeComment(id=_RETRY_ID, body="/orchestrator continue", user=FakeUser("alice"))

# The conversation a fresh retry opens, and the second retry that resumes it.
_REPLACEMENT = "replacement-session"
_SECOND_RETRY_ID = 2000
_SECOND_RETRY = FakeComment(id=_SECOND_RETRY_ID, body="/orchestrator continue", user=FakeUser("alice"))

_NEW_COMMITS = "has_new_commits"

# The dispatch seam naming the analytics sink, None where it is off.
_SINK = "analytics_log_path"

# A reply with nothing but the attachment, or nothing at all, and whether the sink is on as it returns.
_SILENT_REPLIES = (("", True), (_support.SNAPSHOT, True), (_support.SNAPSHOT, False))

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


def _unavailable() -> MagicMock:
    """The outcome's start, failing every time it is asked."""
    return MagicMock(side_effect=ValueError("framing unavailable"))


# Where a framing fails, and how: the report reader once, the outcome's start always.
_FRAMING_FAILURES = (
    (_outcomes, "_parse_report_outcome", _ParsesAfterOneFailure),
    (_replies, "_outcome_start", _unavailable),
)


# A report quoting an attachment line as code, which a fence encloses.
_EXAMPLE = 'ANALYTICS: task-snapshot v1 {"description": "Example payload."}'
_QUOTING_REPORT = f"Updated the example in the docs.\n\n```text\n{_EXAMPLE}\n```"

# That report, the snapshot above it.
_FENCED_EXAMPLE = f"{_support.SNAPSHOT}\n\nREPORT: READY\n{_QUOTING_REPORT}\nREPORT: END"

# Replies whose report no attachment line may make publishable, and what their snapshot reads as.
_UNPUBLISHABLE = (
    (f"- ```text\n{_support.SNAPSHOT}\n  ```\nREPORT: READY\nImplemented.\nREPORT: END", "missing"),
    (f"REPORT: READY\n{_support.SNAPSHOT}\nREPORT: END", "misplaced"),
)


def _fingerprint(issue) -> str:
    """The requirements fingerprint the issue reads as now."""
    return _content_hash._compute_user_content_hash(issue, set())


def _replaced():
    """What the replacement conversation answers each retry with: the snapshot alone."""
    return _agent(session_id=_REPLACEMENT, last_message=_support.SNAPSHOT)


class ReplyReadingTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """A first implementation's reply, as the workflow and the recorder read it."""

    def test_an_attachment_alone_reads_as_silence(self) -> None:
        # Parked as the silent failure an empty reply is, with no notice
        # quoting the line, the sink on or off -- and the description
        # recorded only where it is on.
        for message, sink in _SILENT_REPLIES:
            github, issue = self.seeded()
            silent = {_SINK: self.sink if sink else None, _NEW_COMMITS: False}
            self.dispatch(github, issue, _support.returning(message), **silent)
            with self.subTest(message=message, sink=sink):
                self.assertEqual(github.pinned_data(_held.ISSUE).get("park_reason"), "agent_silent")
                self.assertEqual(_support.posted_attachments(github), [])
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)["report_outcome"], "no_marker")

    def test_a_reply_without_it_is_missing(self) -> None:
        # Committed work and neither the attachment nor a report outcome.
        github, issue = self.seeded()
        self.dispatch(github, issue, _support.returning("Implemented and committed."), **self.committing)
        self.assertEqual(self.diagnosed(), [("missing", False)])

    def test_a_failed_framing_spares_the_report(self) -> None:
        # The recorder asks the report reader first, inside its boundary --
        # the reader failing once, or the outcome's start failing every time.
        for owner, name, failing in _FRAMING_FAILURES:
            self.sink.unlink(missing_ok=True)
            github, issue = self.seeded()
            with patch.object(owner, name, failing()):
                self.dispatch(github, issue, _support.returning(), **self.committing)
            with self.subTest(failing=name):
                self.assertEqual(self.diagnosed(), [("parse_failed", False)])
                self.published(github)

    def test_a_line_inside_the_report_stays_out_of_it(self) -> None:
        # Published as the same report, under the same digest, as the reply
        # without the line, the sink on or off -- and recorded as misplaced
        # only where it is on.
        inside = f"{_support.SNAPSHOT}\n"
        digests = {
            self._published_digest(""),
            self._published_digest(inside),
            self._published_digest(inside, **{_SINK: None}),
        }
        self.assertEqual(len(digests), 1)
        self.assertEqual(self.diagnosed(), [("missing", False), ("misplaced", True)])

    def test_a_fenced_example_is_published(self) -> None:
        # Code the report quotes is the report's own text, the snapshot above it read.
        github, issue = self.seeded()
        self.dispatch(github, issue, _support.returning(_FENCED_EXAMPLE), **self.committing)
        settled = self.published(github)["developer_report_current"]
        quoting = _support.published_attachments(github)
        self.assertEqual(len(quoting), 1)
        self.assertIn(_EXAMPLE, quoting[0])
        self.assertEqual(settled["content"], _developer_reports.content_digest(_QUOTING_REPORT))
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertEqual(snapshot["description"]["text"], _support.DESCRIPTION)

    def test_no_line_makes_a_report_publishable(self) -> None:
        # A fence the line sits in, which taking it out would close above the
        # markers, and a block of nothing else: each refused, and recorded
        # as the verdict the workflow reached.
        for reply, category in _UNPUBLISHABLE:
            self.sink.unlink(missing_ok=True)
            github, issue = self.seeded()
            self.dispatch(github, issue, _support.returning(reply), **self.committing)
            diagnostic = self.only(_support.DIAGNOSTIC_EVENT)
            with self.subTest(category=category):
                self.assertEqual(github.opened_prs, [])
                self.assertEqual(diagnostic[_support.CATEGORY], category)
                self.assertEqual(diagnostic["report_outcome"], "malformed")

    def _published_digest(self, inside: str, **seams) -> str:
        """The digest of the report a fresh issue publishes for a READY block carrying `inside`; none quotes a line."""
        github, issue = self.seeded()
        reply = f"REPORT: READY\nImplemented the requested flag.\n{inside}REPORT: END"
        seams = {**self.committing, **seams}
        self.dispatch(github, issue, _support.returning(reply), **seams)
        settled = self.published(github)["developer_report_current"]
        self.assertEqual(_support.published_attachments(github), [])
        return settled["content"]


class RetrySnapshotTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """An operator's retry beside a body edit, resumed and fresh."""

    def test_a_resumed_retry_keeps_the_baseline(self) -> None:
        github, issue, baseline = self._edited(dev_session_id=_SESSION)
        committed = self._committed()
        ran = self.dispatch(github, issue, _support.returning(), **committed)
        self.assertNotIn(_EDITED, _support.prompt_of(ran))
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)[_support.REVISION], baseline)

    def test_a_fresh_retry_takes_the_edit(self) -> None:
        # Bound to the edit its preamble quoted; named by the baseline its
        # report is stamped with.
        github, issue, baseline = self._edited()
        ran = self.dispatch(github, issue, _support.returning(), **self._committed())
        self.assertIn(_EDITED, _support.prompt_of(ran))
        edited = _fingerprint(issue)
        self.assertNotEqual(edited, baseline)
        self.assertEqual(self._bound(), (edited, _support.reference(baseline)))

    def test_its_continuation_keeps_the_edit(self) -> None:
        # The replacement session the fresh retry opened, resumed by the next
        # retry, is handed nothing new: still bound to the edit it was grounded on.
        github, issue, _baseline = self._edited()
        runner = MagicMock(side_effect=[_replaced(), _replaced()])
        self.dispatch(github, issue, runner, **self._committed(commits=False))
        issue.comments.append(_SECOND_RETRY)
        self.dispatch(github, issue, runner, **self._committed(commits=False))
        self.assertEqual(runner.call_args.kwargs["options"].resume_session_id, _REPLACEMENT)
        edited = _fingerprint(issue)
        self.assertEqual(self._revisions(), [edited, edited])

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

    def _committed(self, *, commits: bool = True) -> dict:
        """The seams of a retry whose branch carries commits, or none with `commits` False; its sink this test's."""
        return {**self.sunk, _NEW_COMMITS: commits}

    def _revisions(self) -> list[str]:
        """The requirements revision of every snapshot on the sink, in order."""
        return [snapshot[_support.REVISION] for snapshot in self.events(_support.SNAPSHOT_EVENT)]


if __name__ == "__main__":
    unittest.main()
