# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the spent spawn budget an initial decomposition stands on.

The park is seeded rather than earned by running a budget out, because what
these tests are about is the tick that MEETS one: a park is what every later
tick and every restart reads back, and seeding it is how an issue says "I
arrived already stopped".
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.config import settings as config
from orchestrator.workflow.engine import retry_budget as _retry_budget
from orchestrator.workflow.stages.decomposition.models import (
    _DecomposerSession,
)
from orchestrator.workflow.stages.decomposition.session import (
    _read_decomposer_session,
)
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    BACKEND_CLAUDE,
    LABEL_DECOMPOSING,
    _agent,
    _iso_hours_ago,
    _manifest,
)
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _DecomposingWorkflowMixin,
)

ISSUE_NUMBER = 1533

CAP = 3

# Older than the 24h window, so a tick that read the clock instead of the park
# would let this issue spawn again.
ELAPSED_HOURS = 25

WATERMARK = 900

NOTICE_COMMENT_ID = 940

COMMAND_COMMENT_ID = 950

STAGE_DECOMPOSING = "decomposing"

PARK_RETRY_CAP = "retry_cap"

RETRY_CAP_EVENT = "retry_cap"

PHASE_DELIVERED = "delivered"

PHASE_RECONCILED = "reconciled"

PHASE_STANDING = "standing"

PHASE_CONTINUED = "continued"

TRUSTED_AUTHOR = "alice"

OUTSIDER = "mallory"

BOT_LOGIN = "orchestrator"

CONTINUE_COMMAND = "/orchestrator continue"

GUIDANCE = "split it by module"

ISSUE_BODY = "add the thing"

EDITED_BODY = "add the other thing"

RUN_AGENT = "run_agent"

PAUSED_LABEL = "paused"

KEY_AWAITING_HUMAN = "awaiting_human"

KEY_PARK_REASON = "park_reason"

KEY_RETRY_COUNT = "retry_count"

KEY_RETRY_CAP_NOTICE = "retry_cap_notice"

KEY_RETRY_CAP_STAGE = "retry_cap_stage"

KEY_CONTINUED = _retry_budget.RETRY_CAP_CONTINUED

KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

KEY_RETRY_WINDOW_START = "retry_window_start"

KEY_DECOMPOSER_AGENT = "decomposer_agent"

KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"

CAP_SENTENCE = "hit retry cap"

DRIFT_SENTENCE = "issue content changed"

# The sentence a park took, kept verbatim on the issue so the thread can be
# searched for exactly it.
NOTICE = (
    f"hit retry cap ({CAP}/day) for {STAGE_DECOMPOSING}; manual intervention "
    "needed. Window opened at 2026-09-01T00:00:00+00:00."
)

SINGLE_MANIFEST = _manifest('{"decision": "single", "rationale": "fits"}')

DECOMPOSER_QUESTION = "which of the two databases should this use?"

# The conversation that ran out of budget: pinned before the park, and what a
# resume would replay if a fresh attempt left it standing.
OLD_SESSION = "dec-sess"

# A baseline written against a body that has since been edited, so a tick
# meets a real drift rather than its own first encounter with the issue.
STALE_HASH = "written-against-the-old-body"

# What the issue carries beside the park: a manifest and the children it
# already opened on GitHub, the locked decomposer session and the spec that
# pins its backend, the recorded pull request, and a late cycle that has
# finished. None of it is the park's, and none of it may move while it stands.
CARRIED_STATE = MappingProxyType({
    "children": [201, 202],
    "dep_graph": {"202": [201]},
    "expected_children_count": 2,
    "umbrella": True,
    KEY_DECOMPOSER_AGENT: BACKEND_CLAUDE,
    KEY_DECOMPOSER_SESSION_ID: OLD_SESSION,
    "pr_number": 77,
    "late_retired_cycle_id": 7,
    "user_content_hash": STALE_HASH,
})


def trusted(body: str, comment_id: int = COMMAND_COMMENT_ID) -> FakeComment:
    return FakeComment(id=comment_id, body=body, user=FakeUser(TRUSTED_AUTHOR))


def outsider(body: str, comment_id: int = COMMAND_COMMENT_ID) -> FakeComment:
    return FakeComment(id=comment_id, body=body, user=FakeUser(OUTSIDER))


def our_notice(comment_id: int = NOTICE_COMMENT_ID) -> FakeComment:
    """The park's own sentence on the thread, under this orchestrator's name.

    What a tick that posted and then failed to write leaves behind.
    """
    return FakeComment(
        id=comment_id,
        body=f"{config.HITL_MENTIONS} {NOTICE}",
        user=FakeUser(BOT_LOGIN),
    )


class FirstReadFails:
    """A thread read that is refused once and succeeds after.

    The transient shape the notice replay reports as unreadable, and the one
    a second read inside the same tick would answer differently.
    """

    def __init__(self, github) -> None:
        self._read = github.comments_after
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("502")
        return self._read(*args, **kwargs)


class PausedDuringRun:
    """An operator applying `paused` while the bought attempt is running.

    Counts its own calls, since a seed the runner takes as the spawn itself
    is not the mock the other cases assert against.
    """

    def __init__(self, issue) -> None:
        self._issue = issue
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        self._issue.labels.append(FakeLabel(PAUSED_LABEL))
        return _agent(last_message=SINGLE_MANIFEST)


class _RetryCapParkCase(_DecomposingWorkflowMixin):
    """A `decomposing` issue whose spawn budget ran out and nobody answered.

    `standing` is the record it was seeded with, kept so a tick that was
    supposed to change nothing can be held to exactly that.
    """

    def _park(self, *comments, commanded: bool = False, **fields) -> None:
        """Seed the park, and the thread as the tick under test finds it.

        `commanded` puts the operator's own answer on that thread -- the one
        comment that is not scenery but the thing the park is waiting for --
        under the last id a seeded comment carries, so a notice posted during
        the tick lands above it exactly as one would on a live issue.
        """
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            ISSUE_NUMBER, label=LABEL_DECOMPOSING, body=ISSUE_BODY,
        )
        self.issue.comments.extend(comments)
        if commanded:
            self.issue.comments.append(trusted(CONTINUE_COMMAND))
        self.github.add_issue(self.issue)
        self.standing = {
            KEY_AWAITING_HUMAN: True,
            KEY_PARK_REASON: PARK_RETRY_CAP,
            KEY_RETRY_CAP_STAGE: STAGE_DECOMPOSING,
            KEY_RETRY_COUNT: CAP,
            KEY_RETRY_WINDOW_START: _iso_hours_ago(1),
            KEY_LAST_ACTION_COMMENT_ID: WATERMARK,
            **fields,
        }
        self.github.seed_state(ISSUE_NUMBER, **self.standing)

    def _tick(self, agent_result=None):
        return self._run_decomposing(
            self.github, self.issue, run_agent=agent_result or _agent(),
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(ISSUE_NUMBER)

    def _said(self) -> list:
        return [body for _, body in self.github.posted_comments]

    def _phases(self) -> tuple:
        return tuple(
            record["phase"]
            for record in self.github.recorded_events
            if record["event"] == RETRY_CAP_EVENT
        )

    def _locked_session(self) -> _DecomposerSession:
        """What the next resume would be handed off this issue's record."""
        return _DecomposerSession(*_read_decomposer_session(
            self.github.read_pinned_state(self.issue),
        ))

    def _assert_held(self, mocks) -> None:
        """Nothing ran, nothing was said, and nothing durable moved."""
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self._said(), [])
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(self.github.write_state_calls, 0)
        self.assertEqual(self._pinned(), self.standing)
