# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue writer claim, with a pinned record edited the moment a claim on its issue is granted.

What a reading taken under the claim has to see and nothing earlier can: a
record that moved between an earlier reading -- a poll, a scheduling
classification, nothing at all -- and the grant. Dispatch and the base refresh
each decide on the reading they take once they hold the claim.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from unittest.mock import patch

from orchestrator.scheduler import writer_claims


class _EditedAtGrant:
    """The writer claim, making each issue's edit once, on the first grant on that issue."""

    def __init__(self, edits: dict[int, Callable[[], object]]) -> None:
        self._edits = dict(edits)
        self._granting = writer_claims.issue_writer

    @contextlib.contextmanager
    def __call__(self, repo_id: int, issue_number: int, **claim_options):
        """Take the claim, and make the issue's edit once it is held."""
        with self._granting(repo_id, issue_number, **claim_options) as held:
            edit = self._edits.pop(issue_number, None) if held else None
            if edit is not None:
                edit()
            yield held


@contextlib.contextmanager
def edited_at_grant(edits: dict[int, Callable[[], object]]) -> Iterator[None]:
    """Every writer claim taken in the block, with `edits` made as each issue's is first granted."""
    with patch.object(writer_claims, "issue_writer", _EditedAtGrant(edits)):
        yield
