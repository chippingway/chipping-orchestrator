# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An implementing developer's reply carrying a task snapshot, and an analytics sink of the test's own.

The sink is this test's file, the trajectory sink and the database off, so
whatever an observation reaches it stands on nothing else.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.observability.analytics import settings as _analytics_settings
from tests.workflow.fixtures import _TEST_SPEC, _agent
from tests.workflow.report_values import _FINISHED_REPORT
from tests.workflow.stages.implementing import held_capture_test_support as _held

DESCRIPTION = "Add a foo flag to the CLI so users can turn foo on."

SNAPSHOT = f"ANALYTICS: task-snapshot v1 {json.dumps({'description': DESCRIPTION})}"

# A finished run's message carrying the snapshot above its report.
ATTACHED = f"Implemented.\n\n{SNAPSHOT}\n\n{_FINISHED_REPORT}"

SNAPSHOT_EVENT = "task_snapshot"

DIAGNOSTIC_EVENT = "observation_diagnostic"

# The fields of a record a case reads.
SOURCE = "source"
REVISION = "requirements_revision"
TASK_REF = "task_ref"
ROUTE = "route"
CATEGORY = "category"

_OBSERVATIONS = frozenset((SNAPSHOT_EVENT, DIAGNOSTIC_EVENT))

_KNOBS = (("TRAJECTORY_LOG_PATH", None), ("ANALYTICS_DB_URL", None))


def returning(message: str = ATTACHED) -> MagicMock:
    """A runner whose one run finishes on `message`."""
    return MagicMock(return_value=_agent(last_message=message))


def prompt_of(ran: dict) -> str:
    """The prompt a dispatch's one run was handed."""
    called = ran[_held.RUN_AGENT].call_args
    return called.args[1]


def reference(revision: str) -> str:
    """The task reference a snapshot bound to `revision` is named by."""
    return f"{_TEST_SPEC.slug}#{_held.ISSUE}@{revision}"


def posted_attachments(github) -> list[str]:
    """Every comment posted on the issue that holds an attachment line."""
    return [body for _issue, body in github.posted_comments if "ANALYTICS:" in body]


def published_attachments(github) -> list[str]:
    """Every comment the opened pull request carries that holds an attachment line."""
    comments = github.get_pr(_held.OPENED_PR).issue_comments
    return [posted.body for posted in comments if "ANALYTICS:" in posted.body]


def charged(snapshot: dict) -> tuple:
    """The charge ordinal a snapshot names its source by, and the road it came down."""
    return (snapshot[SOURCE]["ordinal"], snapshot[ROUTE])


class SinkOfItsOwn(unittest.TestCase):
    """A test whose analytics sink is a file of its own."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.sink = Path(directory.name) / "analytics.jsonl"
        for knob, setting in (("ANALYTICS_LOG_PATH", self.sink), *_KNOBS):
            patched = patch.object(_analytics_settings, knob, setting)
            patched.start()
            self.addCleanup(patched.stop)
        # A dispatch's seams pointing its analytics sink here, and those of a
        # fresh run that commits: no earlier work, then the run's.
        self.sunk = {"analytics_log_path": self.sink}
        self.committing = {**self.sunk, "has_new_commits": [False, True]}

    def events(self, event: str | None = None) -> list[dict]:
        """Every record of kind `event` on the sink; every record where `event` is None."""
        if not self.sink.exists():
            return []
        lines = self.sink.read_text(encoding="utf-8").splitlines()
        recorded = [json.loads(line) for line in lines]
        return [record for record in recorded if event in {None, record["event"]}]

    def observations(self) -> list[dict]:
        """Every snapshot and diagnostic on the sink, in the order written."""
        return [record for record in self.events() if record["event"] in _OBSERVATIONS]

    def only(self, event: str) -> dict:
        """The one record of kind `event` on the sink."""
        found = self.events(event)
        self.assertEqual(len(found), 1, found)
        return found[0]

    def diagnosed(self) -> list[tuple]:
        """Each diagnostic on the sink: its category, and whether it carries an excerpt."""
        diagnostics = self.events(DIAGNOSTIC_EVENT)
        return [(diagnostic[CATEGORY], "excerpt" in diagnostic) for diagnostic in diagnostics]
