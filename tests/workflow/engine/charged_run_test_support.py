# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ledger a driven road is seeded on, and what one tick left on it.

The vocabulary both road tables beside this are written in -- the developer
and reviewer one, and the decomposer and conversation one. Every road either
drives is seeded here, on one ledger: an allowance with room under it, so a
case about a second launch is not secretly a case about the ceiling, and a
spend that is already non-zero, so a road that started the count over rather
than charging the one the issue carried is a road the numbers catch.

What a case reads afterwards is the issue's own pinned comment, never the
object the handler was holding. The charge is written onto freshly read
durable state in the middle of a tick and the handler writes again at the end
of one, so the count surviving that second write is half of what any of this
proves.

The two worlds a road is driven in besides its ordinary one live here for the
same reason: a run the shutdown sweep killed and a run an operator paused
mid-flight are what every road has to answer for, and each cost the issue the
same run as one that came back.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import AgentResult
from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import run_ledger as _run_ledger
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import DEFAULT_PR_HEAD_SHA, MEASURED_CANDIDATE_SHA, _agent

RUN_AGENT = "run_agent"

PUSH_BRANCH = "_push_branch"

# The phase a charge stands in once the invocation is what happens next.
STARTED = _run_ledger.RunPhase.STARTED

# Wide enough that a road spawning twice still has room under it, so a case
# about the SECOND charge is not really a case about the ceiling.
ALLOWANCE = 8

# What the issue had already spent before the tick under test.
SPENT_BEFORE = 2

# The head a round opens on -- which is the head its pull request stands on,
# since the branch is in sync with its publication when the round starts --
# and the head the run leaves the checkout at, which is the commit the size
# gate proves that checkout to.
SHA_BEFORE = DEFAULT_PR_HEAD_SHA
SHA_AFTER = MEASURED_CANDIDATE_SHA

DEV_SESSION = "dev-sess"

# What the shutdown sweep leaves behind: no session, nothing said, and a flag
# saying none of it can be trusted.
INTERRUPTED = _agent(session_id=None, last_message="", interrupted=True)

# What Claude prints when `--resume` lands on a transcript it no longer has.
# It is the one failure a resume answers with a second spawn rather than a
# park, so it is also the one road that pays twice in a single tick.
POISONED_STDERR = f"Error: No conversation found with session ID: {DEV_SESSION}"

_HUMAN = "alice"

_REPLY_ID = 1100

# Old enough that the fix debounce is answered by the reply itself rather than
# by however long the case takes to run.
_REPLY_AGE = timedelta(hours=1)


def ledger(**extra) -> dict:
    """The pinned agent-run ledger every road is seeded on."""
    return {
        _run_ledger.AGENT_RUN_ALLOWANCE: ALLOWANCE,
        _run_ledger.AGENT_RUNS_USED: SPENT_BEFORE,
        **extra,
    }


def seed_issue(number: int, *, label: str, comments=(), stage=None, **state):
    """One issue on `label`, its thread, and its pinned state with the ledger.

    `stage` is the world its road ordinarily spawns in and `state` is what a
    case says instead, so a test about a spent cap names only the field its cap
    is counted on and inherits the rest.
    """
    github = FakeGitHubClient()
    issue = make_issue(number, label=label)
    for comment in comments:
        issue.comments.append(comment)
    github.add_issue(issue)
    github.seed_state(number, **ledger(**{**(stage or {}), **state}))
    return github, issue


def human_reply(body: str = "please carry on", comment_id: int = _REPLY_ID):
    """A trusted reply old enough to be past every debounce window."""
    return FakeComment(
        id=comment_id,
        body=body,
        user=FakeUser(_HUMAN),
        created_at=datetime.now(UTC) - _REPLY_AGE,
    )


@dataclass(frozen=True)
class Driven:
    """What one driven road left behind: the issue's state, and its seams."""

    github: FakeGitHubClient
    mocks: dict
    number: int

    @property
    def spawns(self) -> int:
        """How many processes this tick actually invoked."""
        return self.mocks[RUN_AGENT].call_count

    @property
    def spent(self) -> int:
        """What the issue's pinned comment durably says it has spent."""
        return self._pinned(_run_ledger.AGENT_RUNS_USED)

    @property
    def reservation(self):
        """The launch the issue is durably holding a charge for, if any."""
        return self._pinned(_run_ledger.AGENT_RUN_RESERVATION)

    def _pinned(self, key: str):
        return self.github.pinned_data(self.number).get(key)


@dataclass(frozen=True)
class ChargedRoad:
    """One handler road that reaches a process, and the issue it charges.

    `label` is what the stage wears, which is what a mid-run pause has to be
    applied over for the guard to read it off a freshly fetched view.
    `agent_result` is what a run on this road comes back with when nothing has
    gone wrong, so a case about a declined outcome seeds its own instead.
    """

    role: str
    number: int
    label: str
    drive: Callable[..., Driven]
    agent_result: AgentResult = field(default_factory=_agent)


@contextlib.contextmanager
def paused_mid_run(road):
    """An operator applying `paused` while this road's process is out.

    Patched onto the client class rather than one instance because the road
    builds its own, and what the guard reads is a FRESH fetch -- which is the
    whole point: the labels the handler holds were read before the spawn.
    """
    view = make_issue(road.number, label=road.label)
    view.labels.append(FakeLabel(PAUSED_LABEL))
    with patch.object(
        FakeGitHubClient, "get_issue", MagicMock(return_value=view),
    ) as fetched:
        yield fetched
