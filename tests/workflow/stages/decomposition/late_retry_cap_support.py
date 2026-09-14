# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent spawn budget a late adjudication stands on, and the thread of it.

The park is seeded rather than earned by running a budget out, because what
these cases are about is the tick that MEETS one: a park is what every later
tick and every restart reads back off the pinned comment, and seeding it is
how an issue says "I arrived already stopped". The one case that earns it
instead is the exhaustion itself, which is about the write and the sentence
that take it.

The issue under it is the late-mode one every neighbouring module uses, so a
generation, a frozen pair, a held pull request, and a recorded run all mean
here exactly what they mean there -- and what a held tick promises to leave
alone is asserted against the record it really arrived with.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import retry_budget as _retry_budget
from tests.support.fakes import (
    FakeComment,
    FakeLabel,
    FakeUser,
)
from tests.workflow.fixtures import _iso_hours_ago
from tests.workflow.stages.decomposition.late_content_replies import HUMAN, PARK_NOTICE_ID
from tests.workflow.stages.decomposition.late_content_support import OUTSIDER, LateContentCase, RefusedComment
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import (
    KEY_PLAN_PATH,
    KEYS,
    PLAN_PATH,
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
    SHA_LENGTH,
    SPLIT_REPLY,
    seed_plan_pr,
)

# The bound the cases that really run the budget out are held to, so what a
# refusal reports is read against a cap of their own rather than against
# whatever the environment configures.
CAP = 3

MAX_RETRIES = "MAX_RETRIES_PER_DAY"

# Older than the 24h window, so a tick reading the clock instead of the park
# would let this issue spawn again.
ELAPSED_HOURS = 25

BOT_LOGIN = "orchestrator"

CONTINUE_COMMAND = "/orchestrator continue"

GUIDANCE = "split it by module"

STAGE_DECOMPOSING = "decomposing"

PARK_RETRY_CAP = _retry_budget.PARK_RETRY_CAP

RETRY_CAP_EVENT = "retry_cap"

PHASE_DELIVERED = "delivered"

PHASE_RECONCILED = "reconciled"

PHASE_STANDING = "standing"

PHASE_CONTINUED = "continued"

# What the gate's own sentence always opens with, whatever cap and window it
# was made against.
CAP_SENTENCE = "hit retry cap"

# The sentence a seeded park recorded, kept verbatim on the issue so the
# thread can be searched for exactly it.
NOTICE = (
    f"hit retry cap ({CAP}/day) for {STAGE_DECOMPOSING}; manual intervention "
    "needed. Window opened at 2026-09-01T00:00:00+00:00."
)

# The two comment ids a case seeds above the park's own watermark: what a
# crashed tick's notice took, and the human's answer written under it.
DELIVERED_NOTICE_ID = PARK_NOTICE_ID + 1

ANSWER_ID = PARK_NOTICE_ID + 2

KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

KEY_RETRY_CAP_STAGE = _retry_budget.RETRY_CAP_STAGE

# The shared owner's own notice field. A park this mode took never writes it;
# one the shared parking form took under this label does, and the late hold
# has to read it as an obligation of exactly the same standing.
KEY_RETRY_CAP_NOTICE = _retry_budget.RETRY_CAP_NOTICE

KEY_CONTINUED = _retry_budget.RETRY_CAP_CONTINUED

# A reply with no fenced block at all: the one completed run that parks for a
# reason a later attempt supersedes, which is how a case reaches the gate a
# second time without a recorded answer standing in front of it.
UNUSABLE_REPLY = "I read the diff and it seems fine to me."

PARK_UNPARSED = "late_manifest_invalid"

# What says this issue's candidate stands under a plan pull request the hold
# is allowed to mark: the recorded number, and the plan path that proves that
# pull request is a design rather than an implementation.
HELD_PLAN_PR = MappingProxyType({
    "pr_number": PLAN_PR_NUMBER,
    KEY_PLAN_PATH: PLAN_PATH,
})

LOCKED_SPEC = "claude --effort high"

LATE_SESSION = "late-sess"

# What the issue carries beside a standing park: the pull request its
# candidate stands under and the hold's own record of it, and the locked late
# run with the session it opened. None of it is the park's, and none of it may
# move while the park stands.
CARRIED_STATE = MappingProxyType({
    **HELD_PLAN_PR,
    KEYS.plan_pr_number: PLAN_PR_NUMBER,
    KEYS.plan_pr_head: "e" * SHA_LENGTH,
    KEYS.plan_pr_body: PLAN_PR_BODY,
    KEYS.agent: LOCKED_SPEC,
    KEYS.role: "decomposer",
    KEYS.session_id: LATE_SESSION,
})

# What the issue reads as while the park stands: stopped for the shared
# budget's own reason, with the stage that ran out named beside it.
PARKED_STATE = MappingProxyType({
    KEYS.awaiting: True,
    KEYS.park_reason: PARK_RETRY_CAP,
    KEY_RETRY_CAP_STAGE: STAGE_DECOMPOSING,
})

# What it reads as once a command has bought an attempt and a run has spent
# it: no park, the grant emptied rather than dropped, and one spawn charged to
# the window the continuation opened rather than added to the spent one.
GRANT_SPENT = MappingProxyType({
    KEYS.awaiting: False,
    KEYS.park_reason: None,
    KEY_CONTINUED: 0,
    KEYS.retry_count: 1,
})


def owed_notice() -> dict:
    """The obligation a park whose comment never landed leaves behind."""
    return {"reason": PARK_RETRY_CAP, "message": NOTICE}


def trusted(body: str, comment_id: int = ANSWER_ID) -> FakeComment:
    """One comment by an account this workflow takes commands from."""
    return FakeComment(id=comment_id, body=body, user=FakeUser(HUMAN))


def outsider(body: str, comment_id: int = ANSWER_ID) -> FakeComment:
    """The same words from an account nobody authorized."""
    return FakeComment(id=comment_id, body=body, user=FakeUser(OUTSIDER))


def posted_notice(
    *, login: str = BOT_LOGIN, comment_id: int = DELIVERED_NOTICE_ID,
) -> FakeComment:
    """The park's own sentence sitting on the thread, under a given name.

    Ours is what a tick that posted and then failed to write leaves behind.
    Anybody else's is the same words under a different login, which is the
    whole point: the sentence carries no marker, so the thread cannot tell
    the two apart on content and the author is the only thing that can.
    """
    return FakeComment(
        id=comment_id, body=f"@handle {NOTICE}", user=FakeUser(login),
    )


class PausedDuringRun:
    """An operator applying `paused` while the bought attempt is running."""

    def __init__(self, issue, label: str = "paused") -> None:
        self._issue = issue
        self._label = label

    def __call__(self, *_args, **_kwargs):
        self._issue.labels.append(FakeLabel(self._label))
        return agent_reply(SPLIT_REPLY)


class UnreadableThread:
    """A thread read GitHub refuses for as long as it is held.

    The park's own worst case: a tick that can neither prove its sentence was
    said nor read the answer that would lift it.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("502")


class LateRetryCapCase(LateContentCase):
    """A late adjudication whose spawn budget ran out and nobody answered.

    The cap is put in force for the whole case rather than around one call,
    so what a refusal reports is read against a bound of its own rather than
    against whatever the environment configures -- and so a case that seeds a
    park is describing an issue the same bound really would have stopped.

    `standing` is the record the issue was seeded with, kept so a tick that
    was supposed to change nothing can be held to exactly that.
    """

    def _park(self, *comments, commanded: bool = False, **fields) -> None:
        """Seed the park, and the thread as the tick under test finds it.

        `commanded` puts the operator's own answer on that thread -- the one
        comment that is not scenery but the thing the park is waiting for.
        """
        self._spend_the_budget(**{
            KEYS.awaiting: True,
            KEYS.park_reason: PARK_RETRY_CAP,
            KEY_RETRY_CAP_STAGE: STAGE_DECOMPOSING,
            KEY_LAST_ACTION_COMMENT_ID: PARK_NOTICE_ID,
            **fields,
        })
        self.issue.comments.extend(comments)
        if commanded:
            self.issue.comments.append(trusted(CONTINUE_COMMAND))
        self.standing = self._pinned()

    def _spend_the_budget(self, **fields) -> None:
        """Seed a live adjudication with nothing left to spend on it."""
        capped = patch.object(config, MAX_RETRIES, CAP)
        capped.start()
        self.addCleanup(capped.stop)
        self._seed(**{
            KEYS.retry_count: CAP,
            KEYS.retry_window: _iso_hours_ago(1),
            **fields,
        })
        self.plan_pr = seed_plan_pr(self.github)

    def _park_on_a_refused_notice(self) -> None:
        """Run the tick whose park lands and whose comment does not.

        The order the park is taken in, broken in the middle: the flag, the
        stage, and the sentence are all durable by the time GitHub refuses
        the comment, so the tick dies with the obligation outstanding.
        """
        self._spend_the_budget()
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._tick()

    def _tick(self, reply=SPLIT_REPLY, **run_fields):
        """One adjudication over this issue, reported as the spawn it made."""
        return self._run(reply, **run_fields)[1]

    def _phases(self) -> tuple:
        """The retry-cap steps this tick recorded, in order."""
        return tuple(
            record["phase"]
            for record in self.github.recorded_events
            if record["event"] == RETRY_CAP_EVENT
        )

    def _assert_reads_as(self, expected) -> None:
        """Hold the pinned comment to one record of what it now says."""
        recorded = self._pinned()
        self.assertEqual(
            {key: recorded.get(key) for key in expected}, dict(expected),
        )

    def _assert_held(self, spawn) -> None:
        """Nothing ran, nothing was said, and nothing durable moved."""
        spawn.assert_not_called()
        self.assertEqual(self._bodies(), [])
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(self.github.write_state_calls, 0)
        self.assertEqual(self._pinned(), self.standing)
