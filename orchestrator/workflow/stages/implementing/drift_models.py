# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a mid-implementation edit's resume freezes for the disposition that finishes it.

`_ImplementingDriftRun` carries what the disposition cannot read back for
itself. `worktree` is the checkout the resume actually ran in. `agent_result`
is the run the outcome is read from. `before_sha` is the HEAD taken ahead of
the agent, the only thing that tells a commit this run produced from one an
earlier tick stranded on the branch, and `committed` is that comparison taken
once the run is back. `paused` says a live pause stopped the resume before it
persisted the session id. `delivery` is the record of what that resume's
prompt quoted of the issue thread: it travels with the run rather than being
re-read after it, since the thread moves while an agent is out.

The boundary against `models.py` is who reads the record. That owner answers
for the records several owners in this stage hand each other, so every
importer of it pays for all of them. This one is built and read inside the
edit route alone, so it stays beside that route and brings the dataclass,
path, and agent-result imports it needs along with it -- which leaves the
route's own owner importing its collaborators and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import messages as _messages, report_redelivery as _report_redelivery
from orchestrator.workflow.engine.prompt_delivery import PromptDeliverySnapshot


@dataclass(frozen=True)
class _ImplementingDriftRun:
    worktree: Path
    agent_result: AgentResult
    before_sha: str | None
    paused: bool
    committed: bool
    # The record of what this resume's prompt actually quoted, which is what
    # the disposition settles. It travels with the run rather than being
    # re-read after it: the thread moves while an agent is out, and a mark
    # taken off what it ends on crosses replies nobody delivered.
    delivery: PromptDeliverySnapshot

    @classmethod
    def finished(
        cls,
        before_sha: str | None,
        resumed: tuple[Path, AgentResult, bool],
        delivery: PromptDeliverySnapshot,
    ) -> _ImplementingDriftRun:
        """One finished resume, told from the head it started on."""
        worktree, agent_result, paused = resumed
        after_sha = _verification_probes._head_sha(worktree)
        return cls(
            worktree=worktree,
            agent_result=agent_result,
            before_sha=before_sha,
            paused=paused,
            committed=bool(after_sha) and after_sha != before_sha,
            delivery=delivery,
        )

    def publishes(
        self,
        spec: _config_models.RepoSpec,
        state: PinnedState,
    ) -> bool:
        if self.agent_result.unfinished_steps:
            return False
        return self.committed or _report_redelivery.redelivers_an_owed_report(
            spec, state, self.agent_result, self.worktree,
        )

    def ack_reason(self) -> str | None:
        if self.agent_result.unfinished_steps:
            return None
        return _messages._drift_ack_reason(
            self.agent_result.last_message or "",
        )
