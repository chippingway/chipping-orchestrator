# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A first implementation's task snapshot, dispatched as a poll does.

The spawn is asked for a snapshot and its genuine return is recorded under
its own invocation, bound to the requirements its prompt was built from --
whatever the issue says by the time the run is back -- and named by the
reference a reviewer of its settled report names. The observation is
analytics alone: it reaches the sink with the usage parse failing and the
trajectory sink and the database off, an invalid report outcome stays
invalid beside it and no notice quotes the line, a recording that fails --
or a sink whose settings will not read -- costs the run nothing, and the
recovery that finishes a captured report, running no developer, records
nothing new.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from orchestrator.agents import codex_events as _codex_events
from orchestrator.config import credentials as _credentials
from orchestrator.observability.analytics.observations import recorder as _recorder
from orchestrator.workflow.engine import content_hash as _content_hash, prompt_notes as _notes
from tests.workflow.fixtures import _TEST_SPEC, _agent, accounted
from tests.workflow.report_values import _FINISHED_REPORT
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_PARSER = "orchestrator.observability.usage.metrics.parse_agent_usage"

_EDIT = "Require the red variant rather than blue."

# What a reply leaves past its outcome, beside the snapshot itself.
_TRAILING_PROSE = "One more thing."

# What the reviewer of a report is told its task reference is.
_TOLD = "Task snapshot reference for this report: `{reference}`."

# What GitHub names the repository by once it is renamed after a report settled.
_RENAMED = "chippingway/renamed-orchestrator"


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


# Where a recording fails, and the observation it leaves: the redactor on the
# description, and the reading of whether the CLI refused the turn.
_RECORDING_FAILURES = (
    (
        (_credentials, "redact_secrets", _FailsOnTheDescription(_credentials.redact_secrets)),
        [("redaction_failed", False)],
    ),
    ((_codex_events, "codex_turn_failure", MagicMock(side_effect=ValueError("classification unavailable"))), []),
)


class DispatchedSnapshotTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """Whole dispatches of a first implementation whose developer describes its task.

    The repository is configured cased otherwise than GitHub spells it, which
    GitHub answers all the same: the identity a snapshot and its reviewer name
    is the one the settled report records it was published under, as
    configured.
    """

    configured = replace(_TEST_SPEC, slug=_TEST_SPEC.slug.upper())

    def test_the_first_implementation_is_recorded(self) -> None:
        # The prompt closes on the request; the snapshot names the run's own
        # charge, the road, and the description it returned, under the
        # reference the settled report's repository and stamp spell, which
        # the reviewer that report is handed is told however the
        # configuration cases the repository and whatever GitHub renames it
        # to since; the pull request carries no attachment.
        github, issue = self.seeded()
        ran = self.dispatch(github, issue, _support.returning(), **self.committing)
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertTrue(_support.prompt_of(ran).endswith(_notes._TASK_SNAPSHOT_NOTE))
        self.assertEqual(_named(snapshot), _named_by(self.published(github)))
        self.assertEqual(snapshot["description"]["text"], _support.DESCRIPTION)
        self.assertEqual(_support.published_attachments(github), [])
        told = _TOLD.format(reference=snapshot[_support.TASK_REF])
        self.assertIn(told, _reviewed(self, github, issue))

    def test_a_mid_run_edit_is_never_bound(self) -> None:
        github, issue = self.seeded()
        handed = _content_hash._compute_user_content_hash(issue, set())
        self.dispatch(github, issue, _EditsMidRun(issue), **self.sunk)
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertNotEqual(_content_hash._compute_user_content_hash(issue, set()), handed)
        named = (snapshot[_support.REVISION], snapshot[_support.TASK_REF])
        self.assertEqual(named, (handed, _support.reference(handed, self.configured.slug)))

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
        # exactly as any other line there does, though no notice quotes it
        # -- and is recorded as misplaced rather than read.
        misplaced = _malformed_outcome(self, _support.SNAPSHOT)
        self.assertEqual(misplaced, _malformed_outcome(self, _TRAILING_PROSE))
        self.assertEqual(misplaced[:2], (0, []))
        self.assertEqual(self.diagnosed(), [("misplaced", True), ("missing", False)])
        self.assertEqual(self.events(_support.SNAPSHOT_EVENT), [])

    def test_an_unreadable_sink_costs_the_run_nothing(self) -> None:
        # The sink's settings will not read: one warning, and the report is
        # published as ever.
        github, issue = self.seeded()
        settings = SimpleNamespace(live_settings=MagicMock(side_effect=OSError("settings unavailable")))
        with patch.object(_recorder, "analytics_config", settings):
            self.dispatch(github, issue, _support.returning(), **self.committing)
        self.assertEqual(len(github.opened_prs), 1)
        self.assertEqual(self.observations(), [])

    def test_a_failed_recording_costs_the_run_nothing(self) -> None:
        # The redactor failing on the description alone, or the reading of
        # whether the CLI refused the turn failing: either way the run is
        # still charged and accounted once -- no retry -- captured, and
        # published, and the observation is the redactor's diagnostic or
        # nothing at all.
        for failing, diagnosed in _RECORDING_FAILURES:
            self.sink.unlink(missing_ok=True)
            github, issue = self.seeded()
            with patch.object(*failing):
                self.dispatch(github, issue, _support.returning(), **self.committing)
            record = self.published(github)
            with self.subTest(failing=failing[1]):
                self.assertEqual(accounted(record), (1, 1))
                self.assertEqual(record[_held.CAPTURED]["stage"], _held.HANDED_OFF)
                self.assertEqual(self.events(_support.SNAPSHOT_EVENT), [])
                self.assertEqual(self.diagnosed(), diagnosed)

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


def _named(snapshot: dict) -> tuple:
    """What a snapshot names: its charge ordinal and road, its nonce and stage, and its task reference."""
    nonce = snapshot[_support.SOURCE]["nonce"]
    named = (nonce, snapshot["stage"], snapshot[_support.TASK_REF])
    return (*_support.charged(snapshot), *named)


def _named_by(record: dict) -> tuple:
    """What the snapshot of the first implementation `record` settled names: its own charge, road, stage, and report.

    The report is named by the repository it records it was published under
    and the revision it is stamped with.
    """
    ordinal, nonce = record["issue_usage_receipts"]["recent"][0]
    report = record["developer_report_current"]
    reference = f"{report['repo']}#{_held.ISSUE}@{report['requirements']}"
    return (ordinal, "implementation", nonce, "implementing", reference)


def _reviewed(case: DispatchedSnapshotTest, github, issue) -> str:
    """The prompt the next tick hands the reviewer of the report `github` published, GitHub having renamed it since."""
    # The fake pull request stays where it opened; a real one stands on the
    # commit the push carried, which is the one the report is about.
    github.get_pr(_held.OPENED_PR).head.sha = _held.SOURCE
    renamed = patch.object(type(github), "repo_slug", new_callable=PropertyMock, return_value=_RENAMED)
    with renamed:
        ran = case.dispatch(github, issue, _support.returning(""), **case.sunk)
    return _support.prompt_of(ran)


def _malformed_outcome(case: DispatchedSnapshotTest, trailer: str) -> tuple:
    """A fresh issue's dispatch over a reply with `trailer` past its outcome: what the workflow did and posted."""
    github, issue = case.seeded()
    message = f"Implemented.\n\n{_FINISHED_REPORT}\n{trailer}"
    case.dispatch(github, issue, _support.returning(message), **case.sunk)
    record = github.pinned_data(_held.ISSUE)
    parked = (record.get("park_reason"), _held.capture_of(record))
    return (len(github.opened_prs), github.label_history, parked, _support.posted_attachments(github))


if __name__ == "__main__":
    unittest.main()
