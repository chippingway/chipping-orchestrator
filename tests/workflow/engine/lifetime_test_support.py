# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's whole life under a small allowance, driven a tick at a time.

The owners under the lifetime ledger are each covered where they live: what
the ledger reads, what the circuit charges, what the park says, what the
command buys. None of those answers the question an operator actually has --
how many agent processes one issue can start before something stops it -- and
none of them could, because the answer is spread over every stage the issue
walks through and every tick it takes to walk it.

So a journey here is a real issue, seeded on a small allowance, run one tick
at a time until the runs run out. Ordinarily a tick is
`_route_issue_to_handler`, and the dispatcher is the entry on purpose: the
hold that stops a spent issue, the sentence it replays, and the command that
buys it more all live there rather than in any handler, and a case that called
the handlers directly would be driving the workflow with the half that ends it
removed. The other tick a leg can name is the base refresh, which runs ahead
of every dispatch rather than through one -- it starts no agent, and what it
does to the counters the caps below are measured on is the reason a journey
built out of it is worth walking.

Nothing carries the count between ticks but the issue's pinned comment. Each
tick builds its own patch set, its own mocks and its own state objects, so
what a later tick knows about an earlier one is exactly what a restarted
process would know -- which is why the totals below are read off the pinned
comment and the spawns are counted per tick and summed.

A leg stages the state a stage would have been entered with rather than
transitioning into it: the label goes on as a hand-applied one, so
`label_history` stays a record of what the WORKFLOW did this walk, and the
staged fields are the ones a stage needs to have work in front of it. What no
leg stages is the park a spent ledger takes -- that is the thing under test,
and it holds the tick from the moment it is written.

Every OTHER cap is pinned wide for the whole walk. Each of them -- the day's
spawn budget, the review-round cap, the conflict-round cap -- refuses a launch
ahead of the ledger and is bounded by a setting the environment can carry, so
a walk run under whatever numbers the suite happens to start with would be
measuring whichever of them ran out first rather than the lifetime total. The
order between them and the ledger is `test_capped_launches.py`'s subject; here
they are held out of the way.
"""
from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    run_ledger_values as _run_ledger_values,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import (
    lifetime_comments as _lifetime_comments,
    lifetime_models as _lifetime_models,
)
from tests.workflow.fixtures import (
    _issue_branch,
    _open_pr_for,
)

RUN_AGENT = "run_agent"

ISSUE_NUMBER = 1580

PR_NUMBER = 80

BRANCH = _issue_branch(ISSUE_NUMBER)

DEV_SESSION = "dev-sess"

# What every cap beside the ledger is pinned to for the length of a walk, and
# so also the round count a case about one of those caps has to seed to spend
# it. Wide enough that no journey here reaches it.
HELD_CAP = 100

# The settings pinned to it. Each is a ceiling some road checks ahead of the
# spawn, so any of them left at whatever the environment carries could be the
# thing that ends a walk -- which would make these cases measure a different
# cap on a different host.
_CAPS_HELD_WIDE = (
    "MAX_RETRIES_PER_DAY",
    "MAX_REVIEW_ROUNDS",
    "MAX_CONFLICT_ROUNDS",
)

# The counter a base rebase and a recovered conflict both put back to
# nothing, and the one thing a walk about resets has to be watched for.
_REVIEW_ROUND = "review_round"


def seeded(
    journey: _lifetime_models.Journey,
    *,
    allowance: int | None = _lifetime_models.ALLOWANCE,
    used: int | None = 0,
    **fields,
) -> tuple[FakeGitHubClient, Any]:
    """One issue at the start of `journey`, on the ledger a case names.

    `used=None` seeds an issue carrying no count of this ledger's own, which
    is every issue that was already running when the ledger arrived.
    `allowance=None` seeds one carrying no ceiling of its own, which is every
    issue nobody has decided anything special about: the setting governs it.
    """
    github = FakeGitHubClient()
    issue = make_issue(ISSUE_NUMBER, label=journey.legs[0].label)
    github.add_issue(issue)
    ledger = {}
    if allowance is not None:
        ledger[_run_ledger_values.AGENT_RUN_ALLOWANCE] = allowance
    if used is not None:
        ledger[_run_ledger_values.AGENT_RUNS_USED] = used
    github.seed_state(ISSUE_NUMBER, **{
        **ledger,
        **journey.seed,
        **fields,
    })
    if journey.pull_request:
        _open_pr_for(
            github,
            issue_number=ISSUE_NUMBER,
            pr_number=PR_NUMBER,
            **journey.pr_fields,
        )
    return github, issue


def walk(
    case, journey: _lifetime_models.Journey, ticks: int | None = None, *, seeded_on=None,
) -> _lifetime_models.Walk:
    """Run `journey`'s issue one tick at a time, and count what it spawned.

    `seeded_on` continues a walk somebody else started, which is how a case
    about what a granted run buys asks its question: the issue is already out
    of runs, and what is under test is what happens after that.

    Each pass records what it started and the review round it left, which is
    what a journey about resets is read against.
    """
    github, issue = seeded_on or seeded(journey)
    with _caps_held_wide():
        passes = tuple(
            _one_pass(case, github, issue, journey.legs[tick % len(journey.legs)])
            for tick in range(_ticks(journey, ticks))
        )
    return _lifetime_models.Walk(github=github, issue=issue, passes=passes)


@contextlib.contextmanager
def _caps_held_wide():
    """Every cap beside the ledger, pinned wide for the length of a walk."""
    with contextlib.ExitStack() as held:
        for cap in _CAPS_HELD_WIDE:
            held.enter_context(patch.object(config, cap, HELD_CAP))
        yield


def _ticks(journey: _lifetime_models.Journey, asked: int | None) -> int:
    """How long the walk is: what a case asked for, or what the journey needs."""
    if asked is None:
        return journey.ticks
    return asked


def _one_pass(case, github: FakeGitHubClient, issue, leg: _lifetime_models.Leg) -> _lifetime_models.Pass:
    """One pass: what it started, and the review round it left behind."""
    _stage(github, issue, leg)
    return _lifetime_models.Pass(
        spawned=_ticked(case, github, issue, leg),
        review_round=github.pinned_data(issue.number).get(_REVIEW_ROUND),
    )


def _stage(github: FakeGitHubClient, issue, leg: _lifetime_models.Leg) -> None:
    """Put the issue in the state its next stage would be entered in."""
    github.apply_foreign_label(issue, leg.label)
    for body in leg.replies:
        _lifetime_comments.said(issue, body)
    state = github.read_pinned_state(issue)
    for key, staged in leg.staged.items():
        state.set(key, staged)
    github.write_pinned_state(issue, state)


def _ticked(case, github: FakeGitHubClient, issue, leg: _lifetime_models.Leg) -> int:
    """Run one tick of the workflow, and report the processes it started."""
    with contextlib.ExitStack() as stack:
        if leg.around is not None:
            stack.enter_context(leg.around())
        mocks = case._run(
            leg.tick(github, issue),
            run_agent=leg.agent_result,
            **leg.world,
        )
    return mocks[RUN_AGENT].call_count
