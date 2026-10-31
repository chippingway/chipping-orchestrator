# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one dev resume asks for, frozen before the run is built.

Every stage that resumes a dev session hands the resume over as one
`_DevResumeRequest`: the issue and the pinned state it runs over, the text the
developer is handed, and the options that shape the run. They are named fields
rather than a keyword blob, so a mistyped option fails where the request is
built instead of quietly resuming without, say, the live-pause guard its caller
asked for. The request also answers which stage every record the run emits is
attributed to.

It lives apart from the frozen handoff records because nothing here has to
survive a boundary the spawn cannot see across. The split rationale a fresh
spawn is re-grounded with is no field of it: the request reads it off the pinned
state it carries, and the run is built with that reading
(`execution._DevResumeContext`), so every caller's fresh spawn quotes the
issue's own record and none can hand it another.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.engine import decomposition_prompts as _decomposition_prompts
from orchestrator.workflow.engine.run_charge_state import OwedLaunch
from orchestrator.workflow.stages.implementing import completion_roads as _roads, state as _state


@dataclass(frozen=True)
class _DevResumeRequest:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    followup_text: str
    stage: str | None = None
    # Whether `followup_text` already lists the tracked repositories, as a
    # documentation prompt does, so a fresh spawn's preamble does not list
    # them a second time.
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
    # The launch the resume is, where it is owed exactly once -- a handed
    # change request's developer: the lifetime run count it is owed at and
    # what else it stands on, which the run circuit holds it to on the
    # readings it charges and starts it from (`run_charge_state.OwedLaunch`).
    # None for every other resume.
    owed: OwedLaunch | None = None
    # The road a report-producing caller froze before the launch -- what its
    # run is handed and where it runs -- so the coordinator captures an
    # eligible return on it (`completion_roads`): an implementing road's, or a
    # reviewer's change request's (`validating/fix_road`, `fixing/resume_road`).
    # None for every other resume, which captures nothing.
    completion: _roads.CompletionRoad | None = None

    @property
    def resolved_stage(self) -> str:
        """Name the stage every record this run emits is attributed to.

        An explicit override wins: the caller that passes one names the stage
        the run belongs to -- the one it relabeled the issue to just before
        resuming, or, recovering a launch a handed request owes, the one the
        issue is on already -- so the attribution does not rest on which
        ``Issue`` object reached the resume: one a relabel did not go through
        reports the stage the run just left. Otherwise the label the issue
        carries names it -- by its bare tag, which is what the audit,
        analytics, and trajectory records have always keyed on.
        """
        return (
            self.stage
            or _workflow_state.stage_name(self.gh.workflow_label(self.issue))
            or _state._IMPLEMENTING_STAGE
        )

    @property
    def split_rationale(self) -> str | None:
        """The split rationale a fresh spawn is re-grounded with: the issue's own record's.

        Read off `state` (`decomposition_prompts._handed_split_rationale`)
        rather than taken from any caller, so no call can hand a replacement
        session residual scope the record does not hold. None is a record
        holding none.
        """
        return _decomposition_prompts._handed_split_rationale(self.state)
