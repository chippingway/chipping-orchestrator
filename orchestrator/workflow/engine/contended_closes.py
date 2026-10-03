# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep a close read while another poller holds the issue, scoped to the cycle it ends.

A contender writes nothing, so the latch is the whole of what it keeps, and
one read of the record decides what that latch is about. A close the record
says ends nothing is not kept, and a read that fails keeps the close unscoped.
"""
from __future__ import annotations

import importlib
import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import observations as _observations, stage_targets as _stage_targets
from orchestrator.workflow.late_split import state as _late_state

log = logging.getLogger("orchestrator.workflow")


def _kept_contended_close(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> None:
    """Keep a close this poll read on an issue whose writer claim it was refused.

    Latched in this process and nowhere else: the receipt that would make it
    durable is a post, and a post is the holder's to make. What a reading
    dropped here would cost is the close itself, once a human reopens the
    issue -- the stage handler its label names would resume a cycle the close
    ended.

    Scoped to the cycle the record names now, while the issue still reads
    closed, because the holder may settle that cycle before this process holds
    the issue again, and an operator may then authorize a fresh one. A latch
    that remembered only the issue would end that fresh cycle too, for a close
    that happened before it existed. Reading is not writing, so the one pinned
    read this costs is the contender's to take; it decides nothing about the
    issue, only what this process holds.

    The record's answer is taken as an ordinary poll takes it: a close that
    ends no cycle -- none on the record, or one already marked over -- is not
    held, and drops any older latch on the issue with it, since the record
    itself now carries whatever that latch was for. A read that fails keeps
    the close unscoped, which ends whatever cycle the next pass under the
    claim finds, because a reading lost costs more than one applied late.
    """
    issue_number = int(issue.number)
    try:
        generation = _late_state.read_late_generation(gh.read_pinned_state(issue))
    except Exception:
        log.exception(
            "repo=%s issue=#%d observed closed while its writer claim was "
            "refused, and its record could not be read; holding the "
            "observation unscoped for the next pass that holds the claim",
            spec.slug, issue_number,
        )
        _observations.observe_close(spec.slug, issue_number)
        return
    late_close_reading = importlib.import_module(_stage_targets._LATE_CLOSE_READING_OWNER)
    cycle = late_close_reading._ending_cycle(spec, issue_number, generation)
    if cycle is None:
        _observations.settle_close(spec.slug, issue_number)
        return
    _observations.observe_close(spec.slug, issue_number)
    _observations.scope_close(spec.slug, issue_number, cycle)
    log.info(
        "repo=%s issue=#%d observed closed, but its writer claim was refused; "
        "holding the observation of cycle %d and sweeping it on the next "
        "polling pass",
        spec.slug, issue_number, cycle,
    )
