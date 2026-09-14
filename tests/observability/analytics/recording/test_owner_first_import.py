# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a producer that names only the recorders pays for, and still writes."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.observability.observability_test_support import _run_import_probe

_REPO_SHORT = "o/r"


_STAGE_IMPLEMENTING = "implementing"


_STAGE_ENTER = "stage_enter"


_PROBE_ISSUE = 11


_STRANDED_ISSUE = 12


_EVENT_VALUE = "pr_opened"


# The order a producer actually creates: it names the recorders at its own
# import and nothing else. What this pins is the shape of that import -- the
# process configuration behind the sink knob is not paid for until a record is
# actually written -- and that a record still lands afterwards.
_OWNER_FIRST_PROBE = """
import sys

import os
os.environ["ORCHESTRATOR_SKIP_DOTENV"] = "1"
os.environ["ANALYTICS_LOG_PATH"] = {path!r}

from orchestrator.observability.analytics.recording import events as owner

failures = []
if "orchestrator.config" in sys.modules:
    failures.append("importing the recorders planted the process configuration")

import orchestrator.skills.catalog as producer

if producer._recording_events is not owner:
    failures.append("the producer no longer holds the defining module")

# A patch aimed at the canonical owner has to reach the call the producer
# makes, which is the whole point of it holding that object.
intercepted = []
record_catalog = owner.record_repo_skill_catalog
owner.record_repo_skill_catalog = lambda **fields: intercepted.append(fields)
producer._recording_events.record_repo_skill_catalog(
    repo={repo!r}, base_branch="main", remote_name="origin", skills_available=[],
)
if len(intercepted) != 1:
    failures.append("a patch on the canonical owner missed the producer")
owner.record_repo_skill_catalog = record_catalog

# Unpatched, the producer's own reference writes through the sink the knob
# names -- which is what resolving the settings holder inside the call buys.
producer._recording_events.record_stage_enter(
    repo={repo!r}, issue={issue!r}, stage={stage!r},
)
if failures:
    sys.exit("; ".join(failures))
"""


# The sharper case: a caller that named the append itself rather than the
# package. It still has to serialize against the prune, which is what the
# probe below drives -- both take the lock the shared sink owner minted.
_STRANDED_APPEND_PROBE = """
import os
import sys
import threading

os.environ["ORCHESTRATOR_SKIP_DOTENV"] = "1"
os.environ["ANALYTICS_LOG_PATH"] = {path!r}

from orchestrator.observability.analytics.recording.events import (
    append_record,
    build_record,
)

record = build_record(repo={repo!r}, issue={issue!r}, event={event!r})
append_record(record)

from orchestrator.observability.analytics import retention

prune_lock = retention.ANALYTICS_FILE_LOCK


def _append_again():
    append_record(record)
    appended.set()


# A `threading.Lock` is not reentrant, so holding the lock the prune takes is
# enough to tell whether this append takes the same object. Left on a lock of
# its own it would sail straight through and write into the file a prune is
# rewriting underneath it.
appended = threading.Event()
worker = threading.Thread(target=_append_again, daemon=True)
prune_lock.acquire()
worker.start()
raced = appended.wait(0.25)
prune_lock.release()
worker.join(10)
if raced:
    sys.exit("a directly held append_record does not take the prune's lock")
if not appended.is_set():
    sys.exit("the append never finished once the prune lock was released")
"""


class OwnerFirstImportTest(unittest.TestCase):
    """A producer that names only the recorders keeps a working, patchable
    owner -- and an append taken off it keeps the sink lock the prune takes.
    """

    def test_recorders_import_clean_and_still_write(self) -> None:
        with tempfile.TemporaryDirectory() as sink_dir:
            sink = Path(sink_dir) / "a.jsonl"
            completed = _run_import_probe(_OWNER_FIRST_PROBE.format(
                path=str(sink),
                repo=_REPO_SHORT,
                issue=_PROBE_ISSUE,
                stage=_STAGE_IMPLEMENTING,
            ))
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            records = [
                json.loads(line)
                for line in sink.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], _STAGE_ENTER)
        self.assertEqual(records[0]["issue"], _PROBE_ISSUE)

    def test_stranded_append_takes_the_prune_lock(self) -> None:
        with tempfile.TemporaryDirectory() as sink_dir:
            sink = Path(sink_dir) / "a.jsonl"
            completed = _run_import_probe(_STRANDED_APPEND_PROBE.format(
                path=str(sink),
                repo=_REPO_SHORT,
                issue=_STRANDED_ISSUE,
                event=_EVENT_VALUE,
            ))
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            records = [
                json.loads(line)
                for line in sink.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        # Both appends land: serializing against the prune delays the second
        # one, it does not drop it.
        self.assertEqual(len(records), 2)
        self.assertEqual({record["issue"] for record in records}, {_STRANDED_ISSUE})


if __name__ == "__main__":
    unittest.main()
