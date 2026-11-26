# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One developer invocation's reply, recorded onto an analytics sink of the test's own."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.agents.models import AgentInvocation
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.observations import recorder, records

REPO = "owner/repo"

ISSUE = 42

COMMENT = 9001

ORDINAL = 3

NONCE = "0123456789abcdef"

INVOCATION = AgentInvocation(
    repo=REPO,
    issue=ISSUE,
    comment=COMMENT,
    cycle=0,
    ordinal=ORDINAL,
    nonce=NONCE,
)

REVISION = "abababababababababababababababababababababababababababababababab"

STAGE = "implementing"

RUN = records.ObservedRun(INVOCATION, STAGE, "implementation", REVISION, report_requirements=REVISION)

TASK_REF = f"{REPO}#{ISSUE}@{REVISION}"

DESCRIPTION = "Add a foo flag to the CLI so users can turn foo on."

OUTCOME = "REPORT: READY\nAdds the foo flag.\nREPORT: END\n"

# What a reply's report outcome reads as, as the framing here answers it.
READY = "ready"
NO_MARKER = "no_marker"

# The fields a record carries, spelled once.
EVENT = "event"
SOURCE_FIELD = "source"
DESCRIPTION_FIELD = "description"
EXCERPT_FIELD = "excerpt"
CATEGORY = "category"
COUNTS = "counts"
TEXT = "text"
CHARS = "chars"
TRUNCATED = "truncated"

# The invocation as every record names its source.
SOURCE = MappingProxyType({
    "repo": REPO, "issue": ISSUE, "comment": COMMENT, "cycle": 0, "ordinal": ORDINAL, "nonce": NONCE,
})

_OUTCOME_LINE = re.compile(r"^[ \t]*REPORT:", re.MULTILINE)


def snapshot_line(description: str = DESCRIPTION) -> str:
    """The attachment line carrying `description`."""
    payload = json.dumps({DESCRIPTION_FIELD: description})
    return f"ANALYTICS: task-snapshot v1 {payload}"


def reply(preamble: str, outcome: str = OUTCOME) -> str:
    """A reply: `preamble`, then its outcome."""
    return f"{preamble}\n\n{outcome}"


def framing(message: str) -> recorder.Framing:
    """A reply framed as the report reader frames it: its first marker line, else its end, read as a report or none."""
    marker = _OUTCOME_LINE.search(message)
    if marker is None:
        return recorder.Framing(len(message), NO_MARKER)
    return recorder.Framing(marker.start(), READY)


class SinkCase(unittest.TestCase):
    """A test whose analytics sink is a file of its own."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "analytics.jsonl"
        sink_on = patch.object(analytics_settings, "ANALYTICS_LOG_PATH", self.path)
        sink_on.start()
        self.addCleanup(sink_on.stop)

    def record(self, message: str, run: records.ObservedRun = RUN) -> list[dict]:
        """Record `message` as `run`'s reply; every record the sink holds afterwards."""
        recorder.record_task_snapshot(run, recorder.ObservedReply(message, framing))
        return self.written()

    def written(self) -> list[dict]:
        """Every record on the sink, parsed."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]
