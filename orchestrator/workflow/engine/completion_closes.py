# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The closes a pending capture's recovery reads, for a road whose owner a close of its issue ends.

A late adjudication's developer revision answers a cycle that a close of its
issue ends whatever a later reading shows
(`stages/decomposition/late_owner_reading`): a reopening takes the close off
GitHub, never off the cycle. The readings the recovery's admission takes of
that issue (`completion_admission`, `completion_effect`) answer a close only as
the effect it proves -- a retirement of the capture, or, where the issue reads
open again behind it, a hold -- and a reopening the next dispatch reads would
then hand the capture on for a cycle a close ended.

So where the capture's road names an owner for a close (`CLOSE_OWNERS`), the
recovery decides it over a client that keeps any close a fetch of the issue
reads (`watching`), and a close kept there is handed to that owner in place of
whatever the admission decided (`ended`): the late revision's ends the cycle,
or keeps the close latched for it. A handoff admitted with no close read
carries the same client on to the road's owner, so a close its own fetches
read is kept alike. Every other road decides over the client as it was handed,
and reads a close as its admission always did.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import issues as _issues
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_routes as _routes,
    completion_state as _state,
    stage_targets as _stage_targets,
)

# The owner each road names for a close its recovery read, as the defining
# module and the function taking the client the close was kept by, the spec,
# the issue, and the dispatch's pinned state, and answering whether the tick
# stops -- resolved when called, as every stage owner the engine reaches is.
CLOSE_OWNERS: Mapping[_routes.CompletionRoute, tuple[str, str]] = MappingProxyType({
    _routes.CompletionRoute.LATE_REVISION: (_stage_targets._LATE_REVISION_CLOSE_OWNER, "closed"),
})


class SeesItsCloses:
    """`gh` for one issue's recovery: every call passed through, any fetch of that issue reading closed kept."""

    def __init__(self, gh: GitHubClient, issue_number: int) -> None:
        self._gh = gh
        self._issue_number = issue_number
        self.closed = False

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def get_issue(self, number: int):
        """Fetch issue `number` as the client does, keeping a close that fetch reads of the recovery's own issue."""
        fetched = self._gh.get_issue(number)
        if number == self._issue_number and _issues.issue_is_closed(fetched):
            self.closed = True
        return fetched


def watching(gh: GitHubClient, issue: Issue, state: PinnedState) -> GitHubClient:
    """`gh`, wrapped to keep a close any fetch of `issue` reads where `state`'s capture is on such a road."""
    if _road(state) not in CLOSE_OWNERS:
        return gh
    return SeesItsCloses(gh, issue.number)


def ended(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState) -> bool:
    """Whether a close `gh` kept went to the owner its capture's road names for one, and that owner stops the tick."""
    if not isinstance(gh, SeesItsCloses) or not gh.closed:
        return False
    owner_module, owner_name = CLOSE_OWNERS[_road(state)]
    owner = getattr(importlib.import_module(owner_module), owner_name)
    return bool(owner(gh, spec, issue, state))


def _road(state: PinnedState) -> _routes.CompletionRoute | None:
    """The road the capture `state` carries pending was taken on; None where it carries none anyone can read."""
    capture = _state.read(state)
    return capture.handoff.route if isinstance(capture, _records.CompletionCapture) else None
