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
return without posting, pushing, or spending a round. `requirements_revision`
is the hash the drift check took of the content the resume was handed, which
the report the session wrote is stamped with.

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


@dataclass(frozen=True)
class _ValidatingDriftRun:
    worktree: Path
    agent_result: AgentResult
    before_sha: str
    paused: bool
    requirements_revision: str
