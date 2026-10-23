# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An auto-rebase checkpoint over a reading refused admission confirms nothing, however the comment reads since.

The road decides on the reading the tick last confirmed. Where that reading
was a record refused admission, a comment repaired in place behind it is still
no reading the road confirmed: it neither makes a step no write can take back
nor lands its checkpoint, and the tick's state is kept out of every whole-state
write.
"""

from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType

from orchestrator.git.base_sync import checkpoints
from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION, PinnedState
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue

_ISSUE = 61

# A record refused admission, and the record a human repairs it to under the
# same comment.
_REFUSED = MappingProxyType({SCHEMA_VERSION_KEY: 2})
_REPAIRED = MappingProxyType({SCHEMA_VERSION_KEY: SUPPORTED_SCHEMA_VERSION})

# The road's two questions of the comment: whether it still owns the attempt
# ahead of a step no write takes back, and whether a step's checkpoint landed.
_ROADS = MappingProxyType({
    "owning the attempt": partial(checkpoints._still_owns_the_attempt, step="pushing"),
    "landing its checkpoint": partial(checkpoints._lands_the_checkpoint, step="clearing its attempt"),
})


def _repaired_after_refusal() -> tuple[FakeGitHubClient, FakeIssue, PinnedState]:
    """The client, the issue, and the state a tick read while the record was refused, repaired in place since."""
    github = FakeGitHubClient()
    issue = make_issue(_ISSUE)
    github.add_issue(issue)
    github.seed_state(issue, raw=True, **_REFUSED)
    state = github.read_pinned_state(issue)
    github._pinned[_ISSUE] = PinnedState(comment_id=state.comment_id, state_data=dict(_REPAIRED))
    return github, issue, state


class RefusedReadingCheckpointTest(unittest.TestCase):
    """Neither question is answered yes over a reading refused admission."""

    def test_a_repaired_comment_confirms_nothing(self) -> None:
        for road, asks in _ROADS.items():
            with self.subTest(road=road):
                github, issue, state = _repaired_after_refusal()

                self.assertFalse(asks(github, issue, state))

                self.assertEqual(github.pinned_data(_ISSUE), dict(_REPAIRED))
                self.assertEqual((github.write_state_calls, state.withheld), (0, True))


if __name__ == "__main__":
    unittest.main()
