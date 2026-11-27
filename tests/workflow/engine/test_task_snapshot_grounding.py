# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing conversation was handed, as a task snapshot of it is bound to.

A road that hands the developer requirements hands its own, whatever this
host keeps. On a retry, a fresh conversation is handed what the road
re-grounds it with, and a resumed one holds what the host's record says it
was grounded on -- while that record still speaks for it: the same
conversation, under the same baseline. Another conversation, a baseline a
road has since settled, or a record no reading parses says nothing, and the
road's own answers. The record is kept where the conversation was last
handed something other than the baseline and taken away where it was handed
the baseline; an unknown conversation leaves it as it stands, and a record
the host will not take is warned of and lost.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import task_snapshot_grounding as _grounding

_BASELINE = "baseline-revision"
_EDITED = "edited-revision"
_ROAD = "road-revision"
_SESSION = "replacement-session"
_OTHER = "another-session"
_REPO_ID = 7
_ISSUE = 42


def _kept(baseline: str | None = _BASELINE) -> _grounding.Grounding:
    """The issue's record on this host, read beside `baseline`."""
    state = PinnedState(comment_id=1, state_data={"user_content_hash": baseline})
    return _grounding.Grounding.of(_REPO_ID, _ISSUE, state)


def _grounded(session: str = _SESSION, baseline: str = _BASELINE) -> dict:
    """The record of `session` grounded on the edit under `baseline`."""
    return {"session_id": session, "requirements": _EDITED, "baseline": baseline}


# Records that speak for the resumed conversation, and those that do not.
_SILENT_RECORDS = (
    ("another conversation", json.dumps(_grounded(_OTHER))),
    ("a settled baseline", json.dumps(_grounded(baseline=_ROAD))),
    ("a damaged record", '{"session_id": '),
    ("a record without requirements", json.dumps({"session_id": _SESSION, "baseline": _BASELINE})),
)

# On an issue recording no baseline: records of any shape but the whole one,
# which a missing `baseline` would otherwise pass for.
_UNSHAPED_RECORDS = (
    ("a record without a baseline", json.dumps({"session_id": _SESSION, "requirements": _EDITED})),
    ("a record with a member too many", json.dumps({**_grounded(baseline=None), "extra": True})),
)


class _HostRecord(unittest.TestCase):
    """A test reading and writing the issue's record on this host."""

    def setUp(self) -> None:
        self.kept = _kept()
        self.path = self.kept.path

    def recorded(self, spelled: str) -> None:
        """The record spelling `spelled` on the host."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(spelled, encoding="utf-8")


class HandedTest(_HostRecord):
    """What each attempt's conversation was handed."""

    def test_the_record_sits_beside_the_claim(self) -> None:
        claim = writer_claims.claim_path(_REPO_ID, _ISSUE)
        self.assertEqual(self.path, claim.with_suffix(_grounding.GROUNDING_SUFFIX))

    def test_a_road_with_requirements_hands_its_own(self) -> None:
        self.recorded(json.dumps(_grounded()))
        self.assertEqual(self.kept.handed(None, None, _ROAD), _ROAD)
        self.assertEqual(self.kept.handed(_SESSION, None, _ROAD), _ROAD)

    def test_a_retry_keeps_the_grounding(self) -> None:
        # A fresh conversation is handed the re-grounding; a resumed one what it was grounded on.
        self.recorded(json.dumps(_grounded()))
        self.assertEqual(self.kept.handed(None, _OTHER, _ROAD), _OTHER)
        self.assertEqual(self.kept.handed(_SESSION, _OTHER, _ROAD), _EDITED)

    def test_a_stale_record_says_nothing(self) -> None:
        self.assertEqual(self.kept.handed(_SESSION, _EDITED, _ROAD), _ROAD)
        for name, spelled in _SILENT_RECORDS:
            with self.subTest(record=name):
                self.recorded(spelled)
                self.assertEqual(self.kept.handed(_SESSION, _EDITED, _ROAD), _ROAD)

    def test_only_a_whole_record_speaks(self) -> None:
        # On an issue recording no baseline, the whole record -- its baseline
        # null -- speaks for the conversation, and no other shape does.
        unset = _kept(baseline=None)
        self.recorded(json.dumps(_grounded(baseline=None)))
        self.assertEqual(unset.handed(_SESSION, _OTHER, _ROAD), _EDITED)
        for name, spelled in _UNSHAPED_RECORDS:
            with self.subTest(record=name):
                self.recorded(spelled)
                self.assertEqual(unset.handed(_SESSION, _OTHER, _ROAD), _ROAD)


class RememberTest(_HostRecord):
    """The record kept beside an attempt's return."""

    def test_only_what_differs_is_kept(self) -> None:
        self.kept.remember(_SESSION, _EDITED)
        record = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(record, _grounded())
        self.kept.remember(_OTHER, _BASELINE)
        self.assertFalse(self.path.exists())

    def test_an_unknown_conversation_leaves_it(self) -> None:
        self.kept.remember(_SESSION, _EDITED)
        self.kept.remember(None, _BASELINE)
        self.assertEqual(self.kept.handed(_SESSION, _OTHER, _ROAD), _EDITED)

    def test_a_refused_write_is_warned_of(self) -> None:
        refused = patch.object(_grounding, "_written", side_effect=OSError("read-only"))
        with refused, self.assertLogs("orchestrator.workflow", level="WARNING") as logged:
            self.kept.remember(_SESSION, _EDITED)
            self.assertEqual(len(logged.output), 1)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
