# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed inputs and basic mock builders for workflow test runs."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from orchestrator.agents import AgentResult
from orchestrator.git.publication import models as _publication_models
from orchestrator.git.verification.status import _WorktreeStatus
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


class _HeadReadings:
    """What the checkout's own head reads as, this reading.

    A tuple seeds a head that MOVES between readings -- one probe takes it
    before a run and another after -- and its last entry answers every reading
    past it, so a caller that asks once more than a test counted reads the
    head the test left the checkout on rather than running out of answers.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._readings = list(context.head_shas)
        self._reads = 0

    def __call__(self, worktree):
        reading = min(self._reads, len(self._readings) - 1)
        self._reads += 1
        return self._readings[reading]


class _TreeReadings:
    """What `git status` reports about the worktree, this reading.

    A tuple seeds a tree that CHANGES between readings -- clean when the
    disposition proves it and carrying something by the time the publication
    proves it again -- and its last entry answers every reading past it, so a
    caller that asks once more than a test counted reads the tree the test
    left the checkout in rather than running out of answers.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._readings = list(context.tree_states) or [
            _WorktreeStatus(
                readable=context.tree_readable,
                paths=tuple(context.dirty_files),
            ),
        ]
        self._reads = 0

    def __call__(self, worktree):
        reading = min(self._reads, len(self._readings) - 1)
        self._reads += 1
        return self._readings[reading]


class _ForkPoints:
    """The commit one revision's contribution is read over, this reading.

    A mapping answers per revision, which is what a rebase needs: the head it
    replayed and the head it produced fork from different commits, and that
    difference is the whole of what the two ends of one rewrite record say.
    Anything else answers every revision alike, so a case about a fork point
    nothing could read seeds "" once rather than per commit.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._seeded = context.fork_points

    def __call__(self, spec, worktree, revision: str):
        if isinstance(self._seeded, Mapping):
            return self._seeded.get(revision, "")
        return self._seeded


class _AnchorAnswers:
    """What the handoff's move of a branch onto a PR head reports.

    The SHA the branch ended up on, since that is what the baseline the spawn
    path reads back is then measured by. `True` is the ordinary answer -- it
    landed on the head that was asked for -- a string is a test naming a
    different tip (the base, where a plan branch the remote no longer has sends
    it), and `None` is the move that established nothing, which holds the
    handoff.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context

    def __call__(self, spec, issue_number, *, branch: str, head_sha: str):
        landed = self._context.anchor_pr_head
        if landed is True:
            # No head named is the caller asking for the base outright, which
            # is where a finished pull request's branch ends up.
            return head_sha or BASE_TIP_SHA
        return landed or None


class _RemoteTipAnswers:
    """Answer the remote-tip read by which branch it is asked about.

    One seam, two questions: the base a round pins its diff against, and the
    per-issue branch a publication is about to move. A single value would
    answer both with the same SHA, so no test could seed one without seeding
    the other -- and the publication gate reads the second to decide whether
    the branch is still one it may overwrite.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context

    def __call__(self, spec, worktree, branch: str):
        if branch == spec.base_branch:
            return self._context.remote_base_tip
        return self._context.remote_branch_tip


def _default_infer_subject_prefix(spec, worktree, issue):
    labels = {
        (getattr(label, "name", "") or "").lower()
        for label in (getattr(issue, "labels", None) or [])
    }
    return "fix" if {"bug", "fix"} & labels else "feat"


def _published_branch(push) -> MagicMock:
    """The push seam, recording its calls whichever seed drives it.

    A callable becomes the side effect rather than the mock, so a scenario
    that moves the pull request under its own push still answers `call_count`
    and `call_args` the way every other seam here does.
    """
    if callable(push):
        return MagicMock(side_effect=push)
    return MagicMock(return_value=bool(push))


def _squashed(seed) -> MagicMock:
    """The squash seam, recording its calls whichever seed drives it.

    A callable becomes the side effect rather than the answer, which is what a
    case about a HELD candidate needs: the gate parks in memory and leaves the
    flags for its caller to persist, so the double has to mutate the state the
    same way before it reports the hold. A record is taken as itself, and a
    tuple is the historical `(success, sha, count, error)` shape every other
    case here was written in, widened to the same record.
    """
    if callable(seed):
        return MagicMock(side_effect=seed)
    return MagicMock(return_value=_squash_outcome(seed))


def _squash_outcome(seed) -> _publication_models._SquashOutcome:
    """One squash outcome, from either spelling of the seed."""
    if isinstance(seed, _publication_models._SquashOutcome):
        return seed
    success, sha, count, error = seed
    return _publication_models._SquashOutcome(
        success=success, sha=sha, count=count, error=error,
    )


def _fetched(seed) -> MagicMock:
    """The fetch seam, answering once or a reading at a time.

    A sequence is a tick whose two fetches differ -- the pull request's branch
    lands and the base does not -- which is the only way the second refusal is
    reached at all.
    """
    if isinstance(seed, (list, tuple)):
        return MagicMock(side_effect=list(seed))
    return MagicMock(return_value=seed)


def _as_mock(value_or_sequence):
    if callable(value_or_sequence):
        return value_or_sequence
    mock = MagicMock()
    if isinstance(value_or_sequence, (list, tuple)):
        mock.side_effect = list(value_or_sequence)
    else:
        mock.return_value = value_or_sequence
    return mock
