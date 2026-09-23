# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a body-edit resume freezes for the helper that finishes it.

`_ValidatingDriftRun` carries the five things the finishing helper cannot read
back for itself. `worktree` is the checkout the resume actually ran in, which
need not be the one the route located before the spawn. `agent_result` is the
run the outcome is read from. `before_sha` is the HEAD taken ahead of the
agent, the only thing that tells a commit this run produced from one an
earlier tick stranded on the branch. `paused` says a live pause stopped the
resume before it persisted the session id, which is what makes the caller
return without posting, pushing, or spending a round. `delivery` is the record
of what that resume's prompt quoted of the issue thread -- re-read afterwards
it would be a different thread, since an agent is out for minutes and a human
may write in them -- and it carries the requirements revision that read
fingerprints to: the settlement records it as the baseline and the report the
session wrote is stamped with the same value, so no reader is left holding a
report against requirements its own prompt already contained.

The boundary against `models.py` is who reads the record. That owner answers
for the records several owners in this stage hand each other, so every
importer of it pays for all of them. This one is built and read inside the
body-edit route alone, so it stays beside that route and brings the dataclass,
path, and agent-result imports it needs along with it -- which leaves the
route's own owner importing its collaborators and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine.prompt_delivery import PromptDeliverySnapshot


@dataclass(frozen=True)
class _ValidatingDriftRun:
    worktree: Path
    agent_result: AgentResult
    before_sha: str
    paused: bool
    delivery: PromptDeliverySnapshot
