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
report it spares is published as ever -- with no attachment line in it, even
where the scan for those lines is what failed. That scan or the fence reader
failing on the reply as written, with the sink on or off, a fenced example is
still the report's own text under the same digest -- the report body's own
fences read in place of the reply's -- and a block holding nothing but the
line is still refused.

An `/orchestrator continue` retry beside a body edit hands a resumed
conversation nothing, so its snapshot keeps the baseline that conversation
was last handed; a retry that opens a fresh conversation re-grounds it on the
issue as its fresh prompt quotes it -- an edit landing while a stale session
it replaces ran included -- so its snapshot is bound to that edit, and so is
the snapshot of a later retry resuming that same conversation. Either way the
task reference names the revision the retry's report is stamped with, the
baseline a reviewer handed that report is told.
"""
from __future__ import annotations

import contextlib
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.github import developer_reports as _developer_reports
from orchestrator.observability.analytics.observations import attachments as _attachments
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_fences as _fences,
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

# What fingerprints the requirements a retry's fresh conversation is re-grounded with.
_FINGERPRINT = "orchestrator.workflow.stages.implementing.completion_roads._requirements"

# A further edit, landing while a retry's first run is out.
_MOVED = "Name the flag foo-mode instead."

# One more, landing while the fresh prompt renders.
_LATE = "Also document the flag."

# Where the fresh preamble lists the tracked repositories, after it read the body.
_TRACKED = "orchestrator.workflow.engine.prompt_context._build_tracked_repos_context"

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


# A reader failing every time it is asked.
_UNAVAILABLE = partial(MagicMock, side_effect=ValueError("framing unavailable"))


class _EditedWhilePoisoned:
    """A retry's runs resuming a session its CLI cannot open, the issue edited as that one runs; then the replacement's.

    Keeps every prompt it was handed, in order, and edits the issue once more
    as a fresh prompt renders, after that prompt read the body (`rendering`).
    """

    def __init__(self, issue) -> None:
        self._issue = issue
        self.prompts: list[str] = []

    def __call__(self, _backend, prompt, *_spawn, **_options):
        """Edit the body and fail as a stale session the first time; return the snapshot and report after."""
        self.prompts.append(prompt)
        if len(self.prompts) > 1:
            return _agent(session_id=_REPLACEMENT, last_message=_support.ATTACHED)
        body = self._issue.body
        self._issue.body = f"{body}\n{_MOVED}"
        return _agent(last_message="", stderr=f"No conversation found with session ID: {_SESSION}")

    def rendering(self, *_context, **_options) -> str:
        """Edit the body while the fresh preamble renders, past its read of the body; list no tracked repositories."""
        body = self._issue.body
        self._issue.body = f"{body}\n{_LATE}"
        return ""


# The readers of a reply that may fail on it, by name, and their owners.
_SCAN = "attachment_lines"
_FENCES = "_fenced_line_starts"
_READERS = MappingProxyType({_SCAN: _attachments, _FENCES: _fences})

# A reply with nothing but the attachment, or nothing at all, whether the sink
# is on as it returns, and how its stderr is read: the attachment scan
# answering or failing on every text, and the credential redactor failing on
# every text.
_SCANNING = contextlib.nullcontext
_SCAN_FAILING = partial(patch.object, _attachments, _SCAN, side_effect=ValueError("scan unavailable"))
_REDACTION_FAILING = partial(
    patch, "orchestrator.config.credentials.redact_secrets", side_effect=ValueError("redactor unavailable"),
)
_SILENT_REPLIES = (
    ("", True, _SCANNING),
    (_support.SNAPSHOT, True, _SCANNING),
    (_support.SNAPSHOT, False, _SCANNING),
    (_support.SNAPSHOT, False, _SCAN_FAILING),
    (_support.SNAPSHOT, False, _REDACTION_FAILING),
)

# Where a framing fails, and how: the report reader once, the outcome's start
# and the scan for attachment lines always.
_FRAMING_FAILURES = (
    (_outcomes, "_parse_report_outcome", _ParsesAfterOneFailure),
    (_replies, "_outcome_start", _UNAVAILABLE),
    (_attachments, _SCAN, _UNAVAILABLE),
)

# A READY report carrying the attachment line inside its block, where it is misplaced.
_MISPLACED = f"REPORT: READY\nImplemented the requested flag.\n{_support.SNAPSHOT}\nREPORT: END"


# A report quoting an attachment line as code, which a fence encloses.
_EXAMPLE = 'ANALYTICS: task-snapshot v1 {"description": "Example payload."}'
_QUOTING_REPORT = f"Updated the example in the docs.\n\n```text\n{_EXAMPLE}\n```"

# That report, the snapshot above it.
_FENCED_EXAMPLE = f"{_support.SNAPSHOT}\n\nREPORT: READY\n{_QUOTING_REPORT}\nREPORT: END"

# A READY block holding nothing but the attachment line.
_ALONE = f"REPORT: READY\n{_support.SNAPSHOT}\nREPORT: END"

# A report the line sits inside of, with text past its outcome.
_TRAILED = f"REPORT: READY\nImplemented.\n{_support.SNAPSHOT}\nREPORT: END\nTrailing prose."

# Replies whose report no attachment line may make publishable, and what their snapshot reads as.
_UNPUBLISHABLE = (
    (f"- ```text\n{_support.SNAPSHOT}\n  ```\nREPORT: READY\nImplemented.\nREPORT: END", "missing"),
    (_ALONE, "misplaced"),
)

# Which reader fails on the reply as written, if any, and whether the sink is
# on: every reader answering with the sink on, then the attachment scan and
# the fence reader each failing with the sink on and off.
_SCANS = (
    (None, True),
    (_SCAN, True),
    (_SCAN, False),
    (_FENCES, True),
    (_FENCES, False),
)


class _FailsOn:
    """A reader failing on every text holding the snapshot's line, and reading every other text as it does.

    So it fails on a reply as written and on the report it ends on, and reads
    the reply the workflow reads, the line kept out of it.
    """

    def __init__(self, read) -> None:
        self._read = read

    def __call__(self, text: str, *args, **kwargs):
        """Fail on a text holding the line; read anything else."""
        if _support.SNAPSHOT in text:
            raise ValueError("unreadable reply")
        return self._read(text, *args, **kwargs)


def _scanned(case: ReplyReadingTest, reply: str, failing: str | None, sink: bool):
    """A fresh issue dispatched over `reply`, the reader `failing` names failing on it, its sink on or off."""
    github, issue = case.seeded()
    seams = {**case.committing, _SINK: case.sink if sink else None}
    scanning = contextlib.nullcontext()
    if failing:
        owner = _READERS[failing]
        scanning = patch.object(owner, failing, _FailsOn(getattr(owner, failing)))
    with scanning:
        case.dispatch(github, issue, _support.returning(reply), **seams)
    return github


def _replaced():
    """What the replacement conversation answers each retry with: the snapshot alone."""
    return _agent(session_id=_REPLACEMENT, last_message=_support.SNAPSHOT)


class ReplyReadingTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """A first implementation's reply, as the workflow and the recorder read it."""

    def test_an_attachment_alone_reads_as_silence(self) -> None:
        # Parked as the silent failure an empty reply is, with no notice
        # quoting the line -- not the reply, nor the stderr the CLI echoed it
        # on -- the sink on or off, the attachment scan answering or failing,
        # the redactor failing on every text, and the description
        # recorded only where the sink is on.
        for message, sink, scanning in _SILENT_REPLIES:
            github, issue = self.seeded()
            with scanning():
                self.dispatch(
                    github, issue, _agent(last_message=message, stderr=f"The CLI echoed its reply:\n{message}"),
                    analytics_log_path=self.sink if sink else None, has_new_commits=False,
                )
            with self.subTest(message=message, sink=sink, scanning=scanning):
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
        # the reader failing once, or the outcome's start or the attachment
        # scan failing every time -- and the report is published without the
        # line misplaced inside it, its readers failing or not.
        for owner, name, failing in _FRAMING_FAILURES:
            self.sink.unlink(missing_ok=True)
            github, issue = self.seeded()
            with patch.object(owner, name, failing()):
                self.dispatch(github, issue, _support.returning(_MISPLACED), **self.committing)
            with self.subTest(failing=name):
                self.assertEqual(self.diagnosed(), [("parse_failed", False)])
                self.published(github)
                self.assertEqual(_support.published_attachments(github), [])

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
        # Code the report quotes is the report's own text, published under
        # the same digest whether the scan for attachment lines answers or
        # fails, the sink on or off; the snapshot above it is read where the
        # scan answers.
        for scan in _SCANS:
            github = _scanned(self, _FENCED_EXAMPLE, *scan)
            settled = self.published(github)["developer_report_current"]
            quoting = _support.published_attachments(github)
            with self.subTest(scan=scan):
                self.assertEqual([_EXAMPLE in body for body in quoting], [True])
                self.assertEqual(settled["content"], _developer_reports.content_digest(_QUOTING_REPORT))
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertEqual(snapshot["description"]["text"], _support.DESCRIPTION)

    def test_no_line_makes_a_report_publishable(self) -> None:
        # A fence the line sits in, which taking it out would close above the
        # markers, and a block of nothing else: each refused, and recorded
        # as the verdict the workflow reached -- and the block of nothing
        # else, like a report with text past it, refused still where the
        # scan for attachment lines or the fence reader fails on the reply
        # and its report, the sink on or off, with no notice quoting the line.
        for reply, category in _UNPUBLISHABLE:
            self.sink.unlink(missing_ok=True)
            github = _scanned(self, reply, *_SCANS[0])
            diagnostic = self.only(_support.DIAGNOSTIC_EVENT)
            with self.subTest(category=category):
                self.assertEqual(github.opened_prs, [])
                self.assertEqual(diagnostic[_support.CATEGORY], category)
                self.assertEqual(diagnostic["report_outcome"], "malformed")
        for scan in _SCANS[1:]:
            for reply in (_ALONE, _TRAILED):
                github = _scanned(self, reply, *scan)
                with self.subTest(scan=scan, reply=reply):
                    self.assertEqual((github.opened_prs, _support.posted_attachments(github)), ([], []))

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
        # A resumed conversation is handed nothing, so no fresh fingerprint is
        # taken for it: one that could not be taken costs it nothing, its
        # snapshot recorded under the baseline as ever.
        github, issue, baseline = self._edited(dev_session_id=_SESSION)
        with patch(_FINGERPRINT, side_effect=OSError("fingerprint unavailable")):
            ran = self.dispatch(github, issue, _support.returning(), **self._committed())
        self.assertNotIn(_EDITED, _support.prompt_of(ran))
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)[_support.REVISION], baseline)

    def test_a_fresh_retry_takes_the_edit(self) -> None:
        # A poisoned session's fresh retry, the issue edited again while the
        # stale one ran: bound to the issue as its preamble quoted it, both
        # edits included, not as the retry first read it -- and not as an
        # edit landing while that preamble rendered left it, which the prompt
        # does not quote either; named by the baseline its report is stamped
        # with. The stale run records nothing.
        github, issue, baseline = self._edited(dev_session_id=_SESSION)
        runs = _EditedWhilePoisoned(issue)
        with patch(_TRACKED, side_effect=runs.rendering):
            self.dispatch(github, issue, runs, **self._committed(commits=False))
        self.assertIn(f"{_EDITED}\n{_MOVED}", runs.prompts[-1])
        self.assertNotIn(_LATE, runs.prompts[-1])
        issue.body = issue.body.removesuffix(f"\n{_LATE}")
        edited = _content_hash._compute_user_content_hash(issue, set())
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
        edited = _content_hash._compute_user_content_hash(issue, set())
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
