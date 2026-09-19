# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one historical resume call supplied, checked before the run is built.

The dev resume entry point still accepts the positional-and-keyword call its
several callers were written against, so its arguments arrive as an
`inspect`-bound blob rather than as named parameters. These two records are
what turns that blob back into something typed. `_DevResumeRequest` freezes
exactly what one call supplied and answers which stage every record the run
emits is attributed to; `_DevResumeOptions` rejects an unknown keyword that
named parameters would have refused on their own, so a mistyped `pause_guard=`
raises the `TypeError` it deserves instead of being swallowed and quietly
resuming without a live-pause guard.

They validate rather than carry, which is why they live apart from the frozen
handoff records: nothing here has to survive a boundary the spawn cannot see
across, and both are finished before the first attempt runs.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.stages.implementing import state as _state


@dataclass(frozen=True)
class _DevResumeRequest:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    resume_args: tuple
    option_fields: dict
    stage: str | None

    @property
    def resolved_stage(self) -> str:
        """Name the stage every record this run emits is attributed to.

        An explicit override wins: the caller that passes one relabeled the
        issue just before resuming and names the stage it moved to, so the
        attribution does not rest on which ``Issue`` object reached the
        resume -- one the relabel did not go through reports the stage the
        run just left. Otherwise the label the issue carries names it -- by
        its bare tag, which is what the audit, analytics, and trajectory
        records have always keyed on.
        """
        return (
            self.stage
            or _workflow_state.stage_name(self.gh.workflow_label(self.issue))
            or _state._IMPLEMENTING_STAGE
        )


@dataclass(frozen=True)
class _DevResumeOptions:
    followup_has_tracked_repos: bool = False
    pause_guard: bool = False
    # The conversation a FRESH spawn is re-grounded with, where the caller
    # froze one. A retired session turns a resume into a spawn with no
    # transcript, so its prompt quotes the thread -- and read at spawn time
    # that is a second reading minutes newer than the batch the caller will
    # settle, which delivers a comment nothing records. None is every caller
    # holding no frozen read, where the prompt builder takes its own; an
    # empty string is a frozen conversation with nothing in it, and is quoted
    # as that.
    thread_text: str | None = None

    @classmethod
    def from_fields(cls, fields: dict) -> _DevResumeOptions:
        unknown = set(fields) - {
            "followup_has_tracked_repos", "pause_guard", "thread_text",
        }
        if unknown:
            raise TypeError(f"unexpected resume option(s): {sorted(unknown)!r}")
        return cls(**fields)
