# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing conversation was handed, as a task snapshot of it is bound to.

A road that hands the developer requirements hands its own, whatever this
host keeps. On a retry, a fresh conversation is handed what the road
re-grounds it with, and a resumed one holds what the host's record says it
was grounded on -- while that record still speaks for it: the same
conversation, under the same baseline. Another conversation, a baseline a
road has since settled, or a record no reading parses says nothing, and the
road's own answers; a record the host will not let be read fails the
snapshot that asked. The record is kept where the conversation was last
handed something other than the baseline and taken away where it was handed
the baseline; an unknown conversation leaves it as it stands, and a change
the host will not take fails the snapshot that asked, the record a refused
write would have replaced taken away with it.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _regrounding() -> str:
    """What a retry's road re-grounds a fresh conversation with."""
    return _OTHER


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

# A whole record but for its requirements written twice, which a decoder would settle as the last.
_TWICE = (
    f'{{"session_id": "{_SESSION}", "requirements": "{_OTHER}", '
    f'"requirements": "{_EDITED}", "baseline": null}}'
)

# On an issue recording no baseline: records of any shape but the whole one,
# which a missing `baseline` would otherwise pass for.
_UNSHAPED_RECORDS = (
    ("a record without a baseline", json.dumps({"session_id": _SESSION, "requirements": _EDITED})),
    ("a record with a member too many", json.dumps({**_grounded(baseline=None), "extra": True})),
    ("a record with a member written twice", _TWICE),
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

    def test_it_sits_beside_the_settled_baseline(self) -> None:
        # Beside the baseline a road's settlement writes, the issue's own
        # where it writes none.
        state = PinnedState(comment_id=1, state_data={"user_content_hash": _BASELINE})
        settles = (("last_action_comment_id", 900), ("user_content_hash", _ROAD))
        settled = _grounding.Grounding.of(_REPO_ID, _ISSUE, state, settles)
        self.assertEqual((settled.baseline, self.kept.baseline), (_ROAD, _BASELINE))

    def test_a_road_with_requirements_hands_its_own(self) -> None:
        self.recorded(json.dumps(_grounded()))
        self.assertEqual(self.kept.handed(None, None, _ROAD), _ROAD)
        self.assertEqual(self.kept.handed(_SESSION, None, _ROAD), _ROAD)

    def test_a_retry_keeps_the_grounding(self) -> None:
        # A fresh conversation is handed the re-grounding, fingerprinted for it
        # alone; a resumed one what it was grounded on, nothing fingerprinted.
        self.recorded(json.dumps(_grounded()))
        regrounding = MagicMock(return_value=_OTHER)
        self.assertEqual(self.kept.handed(_SESSION, regrounding, _ROAD), _EDITED)
        regrounding.assert_not_called()
        self.assertEqual(self.kept.handed(None, regrounding, _ROAD), _OTHER)

    def test_a_stale_record_says_nothing(self) -> None:
        self.assertEqual(self.kept.handed(_SESSION, _regrounding, _ROAD), _ROAD)
        for name, spelled in _SILENT_RECORDS:
            with self.subTest(record=name):
                self.recorded(spelled)
                self.assertEqual(self.kept.handed(_SESSION, _regrounding, _ROAD), _ROAD)

    def test_only_a_whole_record_speaks(self) -> None:
        # On an issue recording no baseline, the whole record -- its baseline
        # null -- speaks for the conversation, and no other shape does.
        unset = _kept(baseline=None)
        self.recorded(json.dumps(_grounded(baseline=None)))
        self.assertEqual(unset.handed(_SESSION, _regrounding, _ROAD), _EDITED)
        for name, spelled in _UNSHAPED_RECORDS:
            with self.subTest(record=name):
                self.recorded(spelled)
                self.assertEqual(unset.handed(_SESSION, _regrounding, _ROAD), _ROAD)


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
        self.assertEqual(self.kept.handed(_SESSION, _regrounding, _ROAD), _EDITED)

    def test_a_refused_write_fails_its_snapshot(self) -> None:
        # Raised to the snapshot that asked, which records nothing over it;
        # the record the write would have replaced is taken away with it, so
        # a superseded grounding never speaks for the conversation: a retry
        # resuming it falls back to the road's own.
        self.kept.remember(_SESSION, _OTHER)
        refused = patch.object(Path, "write_text", side_effect=PermissionError("read-only"))
        with refused, self.assertRaises(PermissionError):
            self.kept.remember(_SESSION, _EDITED)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.kept.handed(_SESSION, _regrounding, _ROAD), _ROAD)

    def test_an_unreadable_record_fails_its_snapshot(self) -> None:
        # A record the host will not let be read might speak for the
        # conversation, so it binds no snapshot to the road's own.
        self.recorded(json.dumps(_grounded()))
        unreadable = patch.object(Path, "read_bytes", side_effect=PermissionError("unreadable"))
        with unreadable, self.assertRaises(PermissionError):
            self.kept.handed(_SESSION, _regrounding, _ROAD)


if __name__ == "__main__":
    unittest.main()
