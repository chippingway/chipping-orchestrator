# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing developer's conversation was grounded on, kept on this host for the snapshots of its retries.

A task snapshot names the requirements the conversation that wrote it was
handed. A road that hands the developer requirements -- the first
implementation, and a human reply whose batch it delivers -- hands its own,
which that road settles as the baseline the issue records
(`user_content_hash`). An `/orchestrator continue` retry hands none: a
resumed conversation reads its own transcript, while a fresh one is
re-grounded on the read of the issue its preamble quoted -- an edit beside
the command included -- and the baseline, which stamps the retry's report,
stays where it was, the edit owed to the drift road. So a retry that resumes
a conversation is the one attempt whose requirements nothing on the issue
says once the conversation was last handed something other than the
baseline.

This host keeps that beside the issue's writer claim
(`writer_claims.claim_path`), as `repo-<id>-issue-<n>.task-snapshot-grounding`:
`{"session_id", "requirements", "baseline"}` -- the conversation, what it was
last handed, and the baseline the issue recorded then. Every attempt on a
road that asks for a snapshot that reached the agent keeps it current where
the conversation is known, the id it returned or the one it resumed: written
where what it was handed is not the baseline, and taken away where it is. A
conversation that returned no id and resumed none changes nothing, so the
record of whichever conversation stays pinned stands, and neither does a
launch refused before it started or a turn its provider refused, which handed
the conversation nothing. A retry resuming that same conversation is
bound to what the record says while the baseline is the one it was written
beside; another conversation, or a baseline a road has since settled, leaves
it saying nothing, and the attempt is bound to what its road hands it.

It is analytics alone: read and written only while the analytics sink is on,
only by a snapshot, and only under the issue's writer claim. The pinned
comment never carries it, so no settlement, park, or capture measures or
reads it. A record that will not read is nothing, and one the host will not
take is warned of and lost: a later retry's snapshot is then bound to the
baseline. Another host sees none of it.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orchestrator.github.pinned_state import PinnedState
from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import prompt_delivery as _prompt_delivery

log = logging.getLogger("orchestrator.workflow")

GROUNDING_SUFFIX = ".task-snapshot-grounding"

_SESSION = "session_id"

_REQUIREMENTS = "requirements"

_BASELINE = "baseline"


@dataclass(frozen=True)
class Grounding:
    """One issue's grounding record on this host, beside the baseline the issue records now."""

    path: Path
    baseline: str | None

    @classmethod
    def of(cls, repo_id: int, issue_number: int, state: PinnedState) -> Grounding:
        """The record of the issue `repo_id` and `issue_number` name, read beside `state`'s baseline."""
        claim = _writer_claims.claim_path(repo_id, issue_number)
        baseline = state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
        return cls(claim.with_suffix(GROUNDING_SUFFIX), baseline if isinstance(baseline, str) else None)

    def handed(self, resumed: str | None, fresh_requirements: str | None, road_requirements: str) -> str:
        """The requirements an attempt's conversation was handed.

        `fresh_requirements` is what a retry's road re-grounds a fresh
        conversation with, None on a road that hands its own
        (`road_requirements`). On a retry, a fresh conversation (`resumed`
        None) is handed those, and a resumed one what this record says it was
        grounded on, the road's own where it says nothing.
        """
        if fresh_requirements is None:
            return road_requirements
        if resumed is None:
            return fresh_requirements
        return self._grounded(resumed) or road_requirements

    def remember(self, session_id: str | None, requirements: str) -> None:
        """Keep what `session_id` was last handed where it is not the baseline; take the record away where it is.

        No conversation changes nothing.
        """
        if not session_id:
            return
        if requirements and requirements != self.baseline:
            spelled = json.dumps({_SESSION: session_id, _REQUIREMENTS: requirements, _BASELINE: self.baseline})
            self._changed(lambda: _written(self.path, spelled))
        else:
            self._changed(lambda: self.path.unlink(missing_ok=True))

    def _grounded(self, resumed: str) -> str | None:
        """What the record says `resumed` was grounded on, where it still speaks for that conversation."""
        try:
            record = json.loads(self.path.read_bytes())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            log.warning("could not read the task snapshot grounding at %s (%s)", self.path, type(error).__name__)
            return None
        if not isinstance(record, dict) or record.get(_SESSION) != resumed:
            return None
        if record.get(_BASELINE) != self.baseline:
            return None
        requirements = record.get(_REQUIREMENTS)
        return requirements if isinstance(requirements, str) and requirements else None

    def _changed(self, change: Callable[[], object]) -> None:
        """Make `change` to the record, warned of and lost where the host will not take it."""
        try:
            change()
        except OSError as error:
            log.warning("could not keep the task snapshot grounding at %s (%s)", self.path, type(error).__name__)


def _written(path: Path, spelled: str) -> None:
    """`spelled` over the record at `path`, in place, the namespace made where it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spelled, encoding="utf-8")
