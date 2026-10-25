# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What lands on a late split's child while its drift baseline is decided, and what the seed left behind.

A late child's baseline is decided where the walk creates it, and what can
land on the child after that -- a human's edit to its title or body, or a
comment -- is the subject of every case that uses this module. Each landing
says whether the drift check reads it as a requirements edit. The rest is the
seed write or the record read that never comes back, a configuration a
resumed walk renders the same manifest under differently, and the
announcement a split owes its parent exactly once.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from tests.support.fakes import FakeGitHubClient, FakeIssue
from tests.workflow.stages.decomposition import (
    child_baseline_support as _baseline_support,
    late_transaction_support as _transaction_support,
)
from tests.workflow.stages.decomposition.late_test_support import LATE_ISSUE_NUMBER

KEY_BASELINE = _baseline_support.KEY_BASELINE

# The one author the drift check trusts here, and the one these cases comment
# as -- so what the hash filters is a bot or orchestrator output.
_HUMAN = "alice"


@dataclass(frozen=True)
class Edited:
    """A human's edit to one field of an issue, appending to what it says."""

    field: str
    appended: str

    def __call__(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Append to the field."""
        setattr(issue, self.field, f"{getattr(issue, self.field)}{self.appended}")


@dataclass(frozen=True)
class Landing:
    """Something landing on a child, beside whether the drift check reads it as a requirements edit.

    `land` is None for a child nothing lands on.
    """

    land: Callable[[FakeGitHubClient, FakeIssue], None] | None
    edits: bool = False

    def on(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Land it on the issue."""
        if self.land is not None:
            self.land(gh, issue)


BODY_EDIT = Edited("body", "\n\nand cover the edge cases too")

# What can land on a child once its baseline is decided: an edit to its title
# or its body, or a human's comment, is a requirements edit; a bot's comment
# and one carrying the orchestrator's marker are neither.
LANDINGS = MappingProxyType({
    "its title edited": Landing(Edited("title", ", and its docs"), edits=True),
    "its body edited": Landing(BODY_EDIT, edits=True),
    "a human's comment": Landing(_baseline_support.Commented(_HUMAN), edits=True),
    "a bot's comment": Landing(_baseline_support.Commented(_HUMAN, kind="Bot")),
    "a generated comment": Landing(
        _baseline_support.Commented(_HUMAN, body=f"noted {ORCHESTRATOR_COMMENT_MARKER}"),
    ),
})

# The same, beside a child nothing lands on at all.
LANDINGS_OR_NONE = MappingProxyType({"nothing": Landing(None), **LANDINGS})

# What a poller that dispatched a child ahead of its seed may have left on it:
# the park a `blocked` issue nothing attributes takes, beside a baseline of its
# own.
RECORDED_BASELINE = "a baseline recorded before the seed"
REACHED_FIRST = MappingProxyType({
    "schema_version": 1,
    "awaiting_human": True,
    "park_reason": "blocked_no_children",
    KEY_BASELINE: RECORDED_BASELINE,
})


def seeded(gh: FakeGitHubClient, number: int) -> tuple[str | None, bool | None]:
    """The baseline a child's record carries, and whether its drift check reads what landed since as drift.

    None for both where the record carries no baseline, which the check is
    not asked about. The check is asked under an allowlist naming the human
    these cases comment as.
    """
    baseline = gh.pinned_data(number).get(KEY_BASELINE)
    if baseline is None:
        return None, None
    with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_HUMAN,)):
        return baseline, _baseline_support.drifted(gh, number)


def lost_seed(gh: FakeGitHubClient, *, lands: bool):
    """The first child seed write never coming back: dying before it lands, or landing with its answer lost."""
    return patch.object(
        gh, "write_pinned_state", _baseline_support.LostSeed(gh, LATE_ISSUE_NUMBER, lands=lands),
    )


def unreadable(gh: FakeGitHubClient, number: int):
    """GitHub not answering the read of one issue's pinned record."""
    return patch.object(gh, "read_pinned_state", _baseline_support.UnreadableRecord(gh, number))


def announcements(gh: FakeGitHubClient) -> int:
    """How many times the parent was told what its split became."""
    return sum(_transaction_support.FORWARD_LINK_MARKER in body for _, body in gh.posted_comments)


def renamed_remote(remote: str):
    """Every later split transaction run under a configuration naming the remote `remote`."""
    renamed = replace(_transaction_support._TEST_SPEC, remote_name=remote)
    return patch.object(_transaction_support, "_TEST_SPEC", renamed)
