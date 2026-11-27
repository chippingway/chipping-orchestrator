# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer reply its CLI echoes onto stderr, as the snapshot and the workflow's warnings read it.

An attachment line on stderr is the developer's own text, never the CLI's
evidence: a successful Claude return whose echoed description quotes a
Claude diagnostic is recorded, and its report published, as any other. And
the warning a silent park logs shows its stderr as the park comment quotes
it, the line taken out, with the analytics sink off as well as on.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.observability.analytics.observations import attachments as _attachments
from tests.workflow.fixtures import _agent
from tests.workflow.report_values import _FINISHED_REPORT
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

# A description quoting the diagnostic Claude overflows a resumed transcript with.
_QUOTING = "Handle the Claude diagnostic 'Prompt is too long' during a resume."
_QUOTED_SNAPSHOT = f"ANALYTICS: task-snapshot v1 {json.dumps({'description': _QUOTING})}"
_QUOTED_REPLY = f"{_QUOTED_SNAPSHOT}\n{_FINISHED_REPORT}"

# What the CLI writes before echoing a reply onto stderr.
_ECHO = "CLI echoed its reply:"


class EchoedReplyTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """First implementations whose CLI echoes the developer's reply onto stderr."""

    def test_a_quoted_diagnostic_is_no_refusal(self) -> None:
        # Claude's own result says the turn succeeded.
        github, issue = self.seeded()
        stdout = json.dumps({"type": "result", "is_error": False, "result": _QUOTED_REPLY})
        returned = _agent(last_message=_QUOTED_REPLY, stdout=stdout, stderr=f"{_ECHO}\n{_QUOTED_SNAPSHOT}")
        with patch.object(config, "DEV_AGENT", "claude"):
            self.dispatch(github, issue, returned, **self.committing)
        self.published(github)
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)["description"]["text"], _QUOTING)

    def test_no_warning_carries_the_line(self) -> None:
        # The sink is off, so nothing is collected; the park's warning still
        # quotes the stderr, the echoed line taken out of it.
        github, issue = self.seeded()
        returned = _agent(last_message=_support.SNAPSHOT, stderr=f"{_ECHO}\n{_support.SNAPSHOT}")
        with self.assertLogs("orchestrator.workflow", level="WARNING") as logged:
            self.dispatch(github, issue, returned, analytics_log_path=None, has_new_commits=False)
            parked = [line for line in logged.output if _ECHO in line]
        self.assertEqual(github.pinned_data(_held.ISSUE)["park_reason"], "agent_silent")
        self.assertEqual(self.observations(), [])
        self.assertEqual(len(parked), 1, parked)
        self.assertNotIn(_support.DESCRIPTION, parked[0])
        self.assertIn(_attachments.TAKEN_OUT, parked[0])


if __name__ == "__main__":
    unittest.main()
