# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One closed `implementing` owner, and the submits offered for it.

Shared by the two modules that ask about the same window from either end:
what a REFUSED submit was carrying, and what the record says while a worker
is retiring the cycle a close would end. Both drive the dispatcher's own
partition and submit rather than calling the deferral directly, since half of
what either is about is which reading that path establishes.
"""
from __future__ import annotations

from types import SimpleNamespace

from orchestrator.workflow.engine import dispatch, observations
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_IMPLEMENTING

SPEC = SimpleNamespace(slug="acme/widget")

OWNER_NUMBER = 41

CYCLE_ID = 5

CANDIDATE_SHA = "c0ffee0000000000000000000000000000000041"

WORKFLOW_LOG = "orchestrator.workflow"

KEY_CANCELLED = "late_cancelled"

# What the fake answers with when the request behind a read fails outright.
OUTAGE = ConnectionError("github unreachable")

# The client read every probe and every guard in these modules goes through.
PINNED_READ = "read_pinned_state"


class RefusingOnce:
    """Refuse the guard's own pinned read, and answer every read after it."""

    def __init__(self, github: FakeGitHubClient) -> None:
        self._reading = github.read_pinned_state
        self._refused = False

    def __call__(self, issue):
        """Answer one read, having refused the first one asked for."""
        if self._refused:
            return self._reading(issue)
        self._refused = True
        raise OUTAGE


class Retiring:
    """A record the worker holding the issue retires as the probe reads it."""

    def __init__(self, github: FakeGitHubClient) -> None:
        self._github = github
        self._reading = github.read_pinned_state

    def __call__(self, issue):
        """Drop the cycle, then answer with the record that is left."""
        _late_state.clear_late_generation(self._reading(issue))
        self._github.seed_state(int(issue.number), pr_number=7)
        return self._reading(issue)


class Scheduler:
    """One of the two answers a submit comes back with, as a double.

    `admits` is the whole of what a case chooses: a refusal is an issue a
    worker already runs, and an admission is an idle slot. The callable is
    kept either way, because what an admitted task does with the reading it
    was handed is half of what these cases are about -- and so is what it
    does when nothing ever calls it.

    What the latch said as each submit was decided is kept beside it: the
    window this module is about opens at the enumeration and closes at the
    submit, and a worker holding the issue reads the latch throughout.
    """

    def __init__(self, *, admits: bool) -> None:
        self._admits = admits
        self.task = None
        # What the latch said as this submit was being decided, which is what
        # a worker already holding the issue would have read at that moment.
        self.latched: list[bool] = []

    def submit(self, slug, issue_number, callable_, **_answering) -> bool:
        """Answer the way this double was asked to, holding the callable."""
        self.task = callable_
        self.latched.append(observations.close_observed(slug, issue_number))
        return self._admits


def offered(github: FakeGitHubClient, scheduler) -> None:
    """Offer this tick's fan-out issues to one scheduler double."""
    dispatch._submit_scheduler_fanout_issues(
        github,
        SPEC,
        scheduler,
        dispatch._partition_pollable_issues(github, SPEC),
        1,
    )


def closed_owner(*, live: bool) -> FakeGitHubClient:
    """A closed `implementing` issue, with or without a cycle to end."""
    github = FakeGitHubClient()
    github.add_issue(make_issue(
        OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=True,
    ))
    if not live:
        github.seed_state(OWNER_NUMBER, pr_number=7)
        return github
    state = github.read_pinned_state(github.get_issue(OWNER_NUMBER))
    _late_state.write_late_generation(state, LateGeneration(
        cycle_id=CYCLE_ID,
        generation=1,
        root_issue=OWNER_NUMBER,
        current_issue=OWNER_NUMBER,
        candidate_sha=CANDIDATE_SHA,
        phase=LatePhase.ADJUDICATING,
    ))
    github.seed_state(OWNER_NUMBER, **state.data)
    return github
