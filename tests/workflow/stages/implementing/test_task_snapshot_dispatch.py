# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A first implementation's task snapshot, dispatched as a poll does.

The spawn is asked for a snapshot and its genuine return is recorded under
its own invocation, bound to the requirements its prompt was built from --
whatever the issue says by the time the run is back -- and named by the
reference a reviewer of its settled report names. The observation is
analytics alone: it reaches the sink with the usage parse failing and the
trajectory sink and the database off, an invalid report outcome stays
invalid beside it, a recording that fails costs the run nothing, and the
recovery that finishes a captured report, running no developer, records
nothing new.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.config import credentials as _credentials
from orchestrator.workflow.engine import content_hash as _content_hash, prompt_notes as _notes
from tests.workflow.fixtures import _agent, accounted
from tests.workflow.report_values import _FINISHED_REPORT
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_PARSER = "orchestrator.observability.usage.metrics.parse_agent_usage"

_EDIT = "Require the red variant rather than blue."

# What a reply leaves past its outcome, beside the snapshot itself.
_TRAILING_PROSE = "One more thing."


def _fingerprint(issue) -> str:
    return _content_hash._compute_user_content_hash(issue, set())


class _EditsMidRun:
    """The run, and a human's edit to the body landing while it is out."""

    def __init__(self, issue) -> None:
        self._issue = issue

    def __call__(self, *_spawn, **_options):
        """Edit the body, then return the snapshot and the report."""
        body = self._issue.body
        self._issue.body = f"{body}\n{_EDIT}"
        return _agent(last_message=_support.ATTACHED)


class _FailsOnTheDescription:
    """The credential redactor, failing on the one text that carries the developer's description."""

    def __init__(self, redact) -> None:
        self._redact = redact

    def __call__(self, text: str) -> str:
        """Redact `text`, unless it is the description's."""
        if _support.DESCRIPTION in text:
            raise RuntimeError("redactor unavailable")
        return self._redact(text)


class DispatchedSnapshotTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """Whole dispatches of a first implementation whose developer describes its task."""

    def test_the_first_implementation_is_recorded(self) -> None:
        # The snapshot names the run's own charge, the road, and the
        # description it returned.
        github, issue = self.seeded()
        self.dispatch(github, issue, _support.returning(), **self.committing)
        ordinal, nonce = _support.receipt(self.published(github))
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertEqual(_support.charged(snapshot), (ordinal, "implementation"))
        self.assertEqual(snapshot[_support.SOURCE]["nonce"], nonce)
        self.assertEqual(snapshot["stage"], "implementing")
        self.assertEqual(snapshot["description"]["text"], _support.DESCRIPTION)

    def test_a_reviewer_can_name_it(self) -> None:
        # The prompt closes on the request; the report the pull request
        # carries holds no attachment, and is stamped with the revision the
        # snapshot's reference names.
        github, issue = self.seeded()
        ran = self.dispatch(github, issue, _support.returning(), **self.committing)
        settled = self.published(github)["developer_report_current"]
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertTrue(_support.prompt_of(ran).endswith(_notes._TASK_SNAPSHOT_NOTE))
        self.assertEqual(snapshot[_support.TASK_REF], _support.reference(settled["requirements"]))
        self.assertEqual(_support.published_attachments(github), [])

    def test_a_mid_run_edit_is_never_bound(self) -> None:
        github, issue = self.seeded()
        handed = _fingerprint(issue)
        edits = MagicMock(side_effect=_EditsMidRun(issue))
        self.dispatch(github, issue, edits, **self.sunk)
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertNotEqual(_fingerprint(issue), handed)
        self.assertEqual(snapshot[_support.REVISION], handed)
        self.assertEqual(snapshot[_support.TASK_REF], _support.reference(handed))

    def test_it_needs_no_usage_parse(self) -> None:
        # No usage parse, so no `agent_exit`; the trajectory sink and the
        # database are off; the observation stands on none of them.
        github, issue = self.seeded()
        with patch(_PARSER, side_effect=ValueError("unreadable stream")):
            self.dispatch(github, issue, _support.returning(), **self.sunk)
        self.assertEqual(len(self.events(_support.SNAPSHOT_EVENT)), 1)
        self.assertEqual(self.events("agent_exit"), [])

    def test_an_invalid_outcome_is_not_rescued(self) -> None:
        # The attachment after the outcome leaves the report malformed --
        # exactly as any other line there does -- and is recorded as
        # misplaced rather than read.
        misplaced = _malformed_outcome(self, _support.SNAPSHOT)
        self.assertEqual(misplaced, _malformed_outcome(self, _TRAILING_PROSE))
        self.assertEqual(misplaced[:2], (0, []))
        self.assertEqual(self.diagnosed(), [("misplaced", True), ("missing", False)])
        self.assertEqual(self.events(_support.SNAPSHOT_EVENT), [])

    def test_a_failed_recording_costs_the_run_nothing(self) -> None:
        # The redactor fails on the description alone: the run is still accounted
        # once, captured, and published, with no retry, and the observation
        # is its diagnostic.
        github, issue = self.seeded()
        failing = _FailsOnTheDescription(_credentials.redact_secrets)
        with patch.object(_credentials, "redact_secrets", failing):
            ran = self.dispatch(github, issue, _support.returning(), **self.committing)
        record = self.published(github)
        ran[_held.RUN_AGENT].assert_called_once()
        self.assertEqual(accounted(record), (1, 1))
        self.assertEqual(record[_held.CAPTURED]["stage"], _held.HANDED_OFF)
        self.assertEqual(self.events(_support.SNAPSHOT_EVENT), [])
        self.assertEqual(self.diagnosed(), [("redaction_failed", False)])

    def test_a_recovered_capture_records_nothing_new(self) -> None:
        # The held return is observed as it comes back; the recovery that
        # finishes its captured report runs no developer and adds nothing.
        github, issue = self.seeded()
        finished = _agent(last_message=_support.ATTACHED)
        self.held_mid_run(github, issue, finished, has_new_commits=[False], **self.sunk)
        observed = self.observations()
        self.unpaused(github, issue, **self.sunk)
        self.published(github)
        self.assertEqual([record["event"] for record in observed], [_support.SNAPSHOT_EVENT])
        self.assertEqual(self.observations(), observed)


def _malformed_outcome(case: DispatchedSnapshotTest, trailer: str) -> tuple:
    """A fresh issue's dispatch over a reply with `trailer` past its outcome: what the workflow did."""
    github, issue = case.seeded()
    message = f"Implemented.\n\n{_FINISHED_REPORT}\n{trailer}"
    case.dispatch(github, issue, _support.returning(message), **case.sunk)
    record = github.pinned_data(_held.ISSUE)
    parked = record.get("park_reason")
    return (len(github.opened_prs), github.label_history, parked, _held.capture_of(record))


if __name__ == "__main__":
    unittest.main()
