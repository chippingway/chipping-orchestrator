# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed inputs and basic mock builders for workflow test runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from orchestrator.agents.models import AgentResult
from tests.support.fakes import DEFAULT_PR_HEAD_SHA
from tests.workflow.repo_values import (
    _FAKE_WT,
    BASE_TIP_SHA,
    CONTRIBUTION_DIGEST,
    FORK_POINT_SHA,
    HEAD_AFTER_RUN,
    HEAD_BEFORE_RUN,
)


@dataclass(frozen=True)
class _AgentResultSeed:
    session_id: str = "sess-1"
    last_message: str = ""
    timed_out: bool = False
    interrupted: bool = False
    stderr: str = ""
    exit_code: int | None = None


@dataclass(frozen=True)
class _WorkflowRunContext:
    run_agent: Any
    has_new_commits: Any = False
    dirty_files: tuple = ()
    tree_readable: bool = True
    # What successive readings of the tree report. Empty is the ordinary
    # world -- one answer built from `dirty_files`/`tree_readable`, given to
    # every reading -- and a tuple seeds a tree that CHANGES between them,
    # which is the race the publication boundaries refuse.
    tree_states: tuple = ()
    committed_paths: tuple = ()
    head_contains_path: bool = True
    # Whether the push lands, or the push itself where a scenario has to move
    # the pull request under it -- a tick that pushes twice leases the second
    # against the head the first left.
    push_branch: Any = True
    anchor_pr_head: Any = True
    # The checkout's own head, before the run and after it. The default is
    # the ordinary world -- a head that reads, and a run that moved it -- so a
    # test about publishing says nothing about it, and a test about a head
    # that did not move, or a probe that failed, seeds exactly that.
    head_shas: tuple = (HEAD_BEFORE_RUN, HEAD_AFTER_RUN)
    # Whether the checkout's HEAD is the per-issue branch. True by default,
    # since that is what a round runs on; a test about a commit made detached
    # says otherwise, and the plan publication refuses on it.
    head_on_branch: bool = True
    branch_tip_sha: str = ""
    remote_base_tip: str | None = BASE_TIP_SHA
    remote_branch_tip: str | None = ""
    # What `<remote>/<branch>` is at once a stage has FETCHED it, which is the
    # head an ahead/behind proof was taken against and what the push that
    # proof licenses is pinned to. The default is the head the fake pull
    # request stands on, because in production the two are one fact: the
    # fetch is what makes the ref agree with the remote.
    fetched_branch_tip: str = DEFAULT_PR_HEAD_SHA
    # Whether that reading HAPPENED. A ref nothing could resolve and a count
    # git refused answer zero and zero, which is what an in-sync branch
    # answers -- so a case about a probe that established nothing says so
    # here rather than seeding counts nobody could have taken.
    branch_divergence_readable: bool = True
    commit_contains: Any = True
    unpushed_branch: str | None = None
    first_commit_subject: str = ""
    fallback_prefix: str | None = None
    # What the squash-and-publish hands back. A tuple is the historical
    # spelling every case here was written in -- `(success, sha, count,
    # error)` -- and it is widened to the record the owner now returns, so a
    # case about a HELD candidate names the field instead.
    squash_result: Any = (True, None, 0, None)
    branch_ahead_behind: tuple = (0, 0)
    rebase_in_progress: bool = False
    verify_result: Any = None
    authed_fetch_result: Any = None
    analytics_log_path: Any = None
    trajectory_log_path: Any = None
    # The checkout a round is handed, which is what every reading of the
    # committed work is taken in. A path nothing on this host holds is the
    # ordinary world, since a hermetic run never reaches git; a case whose
    # answer comes from real objects names the repository it built instead.
    issue_worktree: Any = _FAKE_WT
    # What the size gate reads about the candidate a publication is about to
    # push. The default world is the ordinary one -- a commit this host holds,
    # a base the remote named, and a diff well under any ceiling -- so a test
    # about publishing says nothing about size, and a test about the gate
    # seeds exactly the reading it is about. `added_lines` doubles as the
    # refusal: a `MeasurementFailure` here is the count that never happened.
    candidate_commit: Any = None
    # What a revision OTHER than HEAD proves to -- the recorded candidate a
    # retry asks for by id. None answers with the id that was asked for, which
    # is the ordinary world: the object the record names is still here.
    recorded_commit: Any = None
    frozen_base: Any = None
    # Whether the recorded base object is readable here, fetching once. False
    # is a host the pair was not frozen on, where the retry has to park rather
    # than ask the remote for whatever the branch has moved to.
    base_object_present: bool = True
    # A count is the ordinary seed, and a callable is the reading ITSELF --
    # what an acceptance case hands in so the gate acts on a number git
    # produced over a real checkout rather than on one a test chose.
    added_lines: Any = 0
    # What the contribution between the frozen pair fingerprints to -- the
    # digest, or a `FingerprintFailure` for a reading that never happened and
    # therefore has no id at all.
    contribution_digest: Any = CONTRIBUTION_DIGEST
    # Where each revision's branch forked from the base. One value answers
    # every revision alike, which is the world of a tick that replayed
    # nothing; a mapping seeds the two ends a rebase tells apart, and "" is
    # the reading that did not happen.
    fork_points: Any = FORK_POINT_SHA


def _agent(**agent_fields) -> AgentResult:
    seed = _AgentResultSeed(**agent_fields)
    exit_code = seed.exit_code
    if exit_code is None:
        exit_code = -1 if seed.timed_out else 0
    return AgentResult(
        session_id=seed.session_id,
        last_message=seed.last_message,
        exit_code=exit_code,
        timed_out=seed.timed_out,
        stdout="",
        stderr=seed.stderr,
        interrupted=seed.interrupted,
    )


def _default_infer_subject_prefix(spec, worktree, issue):
    labels = {
        (getattr(label, "name", "") or "").lower()
        for label in (getattr(issue, "labels", None) or [])
    }
    return "fix" if {"bug", "fix"} & labels else "feat"


def _as_mock(value_or_sequence):
    if callable(value_or_sequence):
        return value_or_sequence
    mock = MagicMock()
    if isinstance(value_or_sequence, (list, tuple)):
        mock.side_effect = list(value_or_sequence)
    else:
        mock.return_value = value_or_sequence
    return mock
