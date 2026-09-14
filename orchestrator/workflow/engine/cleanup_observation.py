# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retain a cleanup pass's observed close until its ending is proved settled.

An exception preserves the receipt and is re-raised. A completed pass
still keeps the latch when its durable ending remains owed, including
work that no current sweep label would enumerate.
"""
from __future__ import annotations

import contextlib
import importlib

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    observations,
    stage_targets as _stage_targets,
)

_PASS_FAILED = "the pass that took it failed before marking anything"
_ENDING_UNFINISHED = "the ending it ran is owed under no label the sweep asks for"


@contextlib.contextmanager
def _cleanup_observation(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue_number: int,
):
    """Hold one cleanup's observation until the pass has actually run it.

    Every path that runs a cleanup wraps it in this, and they all have to:
    the scheduler's fan-out submit, the in-tick parallel one, and the
    sequential loop that dispatches on its own thread. A pass that raises
    anywhere -- the refetch, the route, the sweep -- marked nothing, so the
    reading it was carrying is still the only one there is, and dropping it
    there would let a reopen before the next tick resume the very cycle the
    close ended.

    A pass that RETURNS is asked what it left, because returning is not
    finishing: a live consumer holds the ref, a remote that refuses a delete
    holds the branch, and the terminal is one more request that can be
    declined. What the answer decides is only whether this reading is the
    LAST route back -- an owner still wearing a swept label is one the sweep
    reaches on its own cadence, and one whose label the cancelled cycle's own
    agent moved is reachable by nothing else at all.
    """
    try:
        yield
    except Exception:
        _dispatch_closure._deferred_cleanup(gh, spec, issue_number, _PASS_FAILED)
        raise
    _kept_cleanup_reading(gh, spec, issue_number)


def _kept_cleanup_reading(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue_number: int,
) -> None:
    """Hold a cleanup's reading where nothing else would come back for it.

    The one question this asks the remote after a pass, and it is asked of the
    ending rather than of the pass: every step of a cleanup is idempotent and
    each is skipped where the record already says what a visit would say, so a
    reading kept over an owner that settled a moment later costs one more pass
    and a reading dropped over one that did not costs the close itself.

    The observation is re-latched before the question rather than after the
    answer, because the answer is a request and a request can fail. What that
    ordering leaves at worst is a latch over an owner with nothing left to
    end, which the next tick's own cleanup pass settles.
    """
    observations.observe_close(spec.slug, issue_number)
    late_close_reading = importlib.import_module(_stage_targets._LATE_CLOSE_READING_OWNER)
    if late_close_reading._cleanup_settled(gh, spec, issue_number):
        observations.settle_close(spec.slug, issue_number)
        return
    _dispatch_closure._said_deferred(spec, issue_number, _ENDING_UNFINISHED)
