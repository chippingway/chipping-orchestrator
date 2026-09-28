# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, whose returned verdict is disposed of rather than only prepared.

A returned run goes to `review_disposition.disposes_of_the_verdict`, and a
later tick is the dispatcher's evidence reconciliation and then
`review_disposition.finishes_the_verdict`, over the run the verdict was
returned from, which a later tick's handler rebuilds (`run`). Beside that
world: what each post a verdict's tick can make says about itself, the
developer a handed change request is answered by, and a post GitHub refuses,
or takes without answering its id, once (`RefusesOnce`).
"""
from __future__ import annotations

from orchestrator.workflow.engine import completion_verdicts as _completion_verdicts
from orchestrator.workflow.stages.validating import models as _models, review_disposition as _disposition
from tests.workflow.fixtures import _agent, _reported
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import review_verdict_test_support as _world

# What each post a verdict's tick can make says about itself: the reviewer's
# feedback, the approval comment, the notice a squash of two commits posts,
# and the notices of the parks an unverified approval and a failed squash take.
FEEDBACK_NOTICE = "requested changes"

APPROVAL_NOTICE = "review approved"

SQUASH_NOTICE = "squashed 2 commits"

UNVERIFIED_NOTICE = "approved without the verification evidence"

SQUASH_FAILED_NOTICE = "squash-on-approval failed"

NOTICES = (FEEDBACK_NOTICE, APPROVAL_NOTICE, SQUASH_NOTICE, UNVERIFIED_NOTICE, SQUASH_FAILED_NOTICE)

# The pinned ledger of the comments the orchestrator posted, which every
# prompt keeps an orchestrator comment by.
LEDGER = "orchestrator_comment_ids"

PARK_EVENT = "park_awaiting_human"


def developer():
    """The developer run a handed change request is answered by."""
    return _agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed"))


def saying(phrase: str):
    """Whether a post's body says `phrase`, for a request another road lands behind."""
    return lambda body: phrase in body


def feedback_posts(case) -> list[str]:
    """Every reviewer-feedback comment posted on `case`'s pull request."""
    return [body for _, body in case.github.posted_pr_comments if FEEDBACK_NOTICE in body]


def fills(case, filled: int) -> None:
    """Put `filled` characters of operator notes on `case`'s pinned comment."""
    state = case.github.read_pinned_state(case.issue)
    state.set("operator_notes", "x" * filled)
    case.github.write_pinned_state(case.issue, state)


class RefusesOnce:
    """A post that fails once where it says `phrase`, and goes through every other time.

    Refused outright, or -- where it `lands` -- taken with an answer that
    names no comment, so nothing reads its id back. `posts` is the client's
    own request, a pull-request or an issue comment.
    """

    def __init__(self, posts, phrase: str, *, lands: bool = False) -> None:
        self._posts = posts
        self._phrase = phrase
        self._lands = lands
        self._failed = False

    def __call__(self, thread, body):
        if self._failed or self._phrase not in body:
            return self._posts(thread, body)
        self._failed = True
        if not self._lands:
            raise RuntimeError("comment rejected")
        self._posts(thread, body)
        return None


class DisposedVerdictWorld(_world.ReviewVerdictWorld):
    """The same issue, whose returned verdict is disposed of rather than only prepared."""

    def setUp(self) -> None:
        super().setUp()
        # The run the verdict waiting on the comment was returned from.
        self.run: _models._ReviewerRun | None = None

    def finishes(self, *agents, meanwhile=None, **run_options) -> dict:
        """One later tick: the evidence reconciliation, then the waiting verdict finished where it does not hold.

        `agents` are the runs it launches, and `meanwhile` is another road's
        work once the tick has read the comment it acts over.
        """
        run_options.setdefault(_world.RUN_AGENT, list(agents))
        return self._run(lambda: self._finishes(meanwhile), **run_options)

    def waiting(self) -> str | None:
        """Which verdict the pinned comment has waiting, or None."""
        waiting = self.pinned().get(_world.RETURNED_VERDICT) or {}
        return waiting.get("verdict")

    def parked(self) -> tuple:
        """The park the pinned comment records and whether it waits, the verdict waiting, and every park reported."""
        pinned = self.pinned()
        reported = [
            event.get("reason")
            for event in self.github.recorded_events
            if event["event"] == PARK_EVENT
        ]
        parks = (pinned.get("park_reason"), bool(pinned.get("awaiting_human")))
        return (parks, self.waiting(), reported)

    def last_notice(self) -> str:
        """The last comment posted on the issue thread, or "" where there is none."""
        return self.github.posted_comments[-1][1] if self.github.posted_comments else ""

    def _prepares(self, message: str) -> None:
        """The returned round, as the live one records it, handed to the disposition."""
        state = self.github.read_pinned_state(self.issue)
        self.run = _world.returned_run(self, state, message)
        # The launch's lifetime charge, which the live round's run circuit takes.
        charged = state.get(_world.AGENT_RUNS_USED) or 0
        state.set(_world.AGENT_RUNS_USED, charged + 1)
        verdict, body = _completion_verdicts._parse_review_verdict(message)
        decision = _models._ReviewerDecision(self.run, verdict, body)
        _disposition.disposes_of_the_verdict(self.github, _TEST_SPEC, self.issue, state, decision)

    def _finishes(self, meanwhile) -> None:
        """The verdict the comment carries, finished over the run it was returned from, past the reconciliation."""
        if _world.reconciles(self):
            return
        state = self.github.read_pinned_state(self.issue)
        if meanwhile is not None:
            meanwhile(self)
        _disposition.finishes_the_verdict(self.github, _TEST_SPEC, self.issue, state, self.run)
