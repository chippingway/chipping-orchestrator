# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, whose returned verdict is filed under a park.

No road files a park of a reviewed subject yet, so a case calls each entry
the way its caller is to (`FILES`): the parks a verdict takes instead of being
acted on, right behind that verdict's preparation, and an approval's failed
verify gate or squash over the approval it prepared. A later tick files the
park of a verdict a tick left waiting over the run it was returned from. What
another road does behind a park's notice is spelled here too: the issue
pointed at another pull request, or a later round's verdict put in place of
the one waiting.
"""
from __future__ import annotations

from functools import partial
from types import MappingProxyType

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import completion_verdicts as _completion_verdicts
from orchestrator.workflow.stages.validating import (
    handoff as _handoff,
    models as _models,
    review_disposition as _disposition,
    review_parks as _parks,
    review_verdicts as _verdicts,
)
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import review_verdict_test_support as _world
from tests.workflow.value_helpers import _open_pr_for

UNVERIFIED = "reviewer_unverified"

UNRECORDED = "reviewer_unrecorded"

VERIFY_FAILED = "verify_failed"

SQUASH_FAILED = "squash_failed"

APPROVED = "approved"

REQUESTED = "changes_requested"

PR_NUMBER = "pr_number"

PARK_EVENT = "park_awaiting_human"

# The notes a case fills the pinned comment with.
NOTES = "operator_notes"

# What each park's notice says about itself.
UNVERIFIED_NOTICE = "approved without the verification evidence"

UNRECORDED_NOTICE = "could not be recorded"

VERIFY_NOTICE = "local verification failed"

SQUASH_NOTICE = "squash-on-approval failed"

NOTICES = (UNVERIFIED_NOTICE, UNRECORDED_NOTICE, VERIFY_NOTICE, SQUASH_NOTICE)

# Why an approval earned no evidence, as a caller refusing it words it.
REFUSAL = "nothing it declared earned verification evidence"

# Each park's entry, called as its caller is to call it over the state in
# hand and the run the verdict came back from: an approval's refusal, the
# verdict a preparation could not persist, an approval's failed verify gate
# measured against the comment as the gate's reading left it, and an
# approval's failed squash holding the verdict it finishes and the subject it
# was of.
FILES = MappingProxyType({
    UNVERIFIED: lambda case, state, run: _parks.parks_unverified(
        case.github, case.issue, state, run, REFUSAL,
    ),
    UNRECORDED: lambda case, state, run: _parks.parks_unrecorded(
        case.github, case.issue, state, run, case.prepared.unrecorded,
    ),
    VERIFY_FAILED: lambda case, state, run: _parks.parks_over_the_subject(
        case.github, case.issue, state, run.measured_over(state.data), (VERIFY_FAILED, VERIFY_NOTICE, None),
    ),
    SQUASH_FAILED: lambda case, state, run: _parks.parks_the_failed_squash(
        case.github,
        case.issue,
        state,
        f"{SQUASH_NOTICE} (force-push rejected); the approved commits stand",
        _handoff._Held(
            _verdicts.read_returned_verdict(state),
            dict(state.data),
            run.subject.recorded(),
        ),
    ),
})

# Every park: the reply that earns it, a phrase of its notice, and the verdict
# it leaves waiting where no park lands over it -- none for a verdict nothing
# persisted.
PARKS = (
    (UNVERIFIED, "LGTM\n\nVERDICT: APPROVED", UNVERIFIED_NOTICE, APPROVED),
    (UNRECORDED, "1. Handle \ud800 too.\n\nVERDICT: CHANGES_REQUESTED", UNRECORDED_NOTICE, None),
    (VERIFY_FAILED, _world.declared_run(), VERIFY_NOTICE, APPROVED),
    (SQUASH_FAILED, _world.declared_run(), SQUASH_NOTICE, APPROVED),
)


def saying(phrase: str):
    """Whether a post's body says `phrase`, for a request another road lands behind."""
    return lambda body: phrase in body


def repoints(case) -> None:
    """Another road pointing `case`'s issue at another pull request than the one its reviewer reviewed."""
    _open_pr_for(case.github, issue_number=_world.ISSUE, pr_number=_world.PR + 1)
    state = case.github.read_pinned_state(case.issue)
    state.set(PR_NUMBER, _world.PR + 1)
    case.github.write_pinned_state(case.issue, state)


def replaces_the_verdict(case) -> None:
    """Another road putting a later round's change request in place of `case`'s waiting verdict."""
    state = case.github.read_pinned_state(case.issue)
    later = dict(state.get(_world.RETURNED_VERDICT), verdict=REQUESTED, feedback="Later.")
    state.set(_world.RETURNED_VERDICT, dict(later, round=1, evidence=None))
    case.github.write_pinned_state(case.issue, state)


class ParkWorld(_world.ReviewVerdictWorld):
    """The issue whose returned verdict is filed under a park by its entry (`entry`) right behind its preparation."""

    def parks(self, park: str, message: str, behind: tuple | None = None) -> None:
        """One tick in which a reviewer returned `message`, its verdict prepared and then filed under `park`.

        `behind` is another road's work -- a phrase of the issue comment it
        lands behind, and the road -- where one does. The run is kept as
        `run`, for a later tick that rebuilds it.
        """
        self.entry = FILES[park]
        if behind is None:
            self.returns(message)
        else:
            phrase, road = behind
            _world.AnotherRoadBehind(self, "comment", saying(phrase), road).returning(message)
        self.run = self.decision.run

    def parks_waiting(self, entry) -> None:
        """One later tick filing, by `entry`, the verdict the comment has waiting, over the run it came back from."""
        state = self.github.read_pinned_state(self.issue)
        self._run(partial(entry, self, state, self.run), run_agent=[])

    def parked(self) -> tuple:
        """The park the pinned comment records and whether it waits, the verdict waiting, and every park reported."""
        pinned = self.pinned()
        waiting = pinned.get(_world.RETURNED_VERDICT) or {}
        reported = [
            event.get("reason")
            for event in self.github.recorded_events
            if event["event"] == PARK_EVENT
        ]
        parks = (pinned.get("park_reason"), bool(pinned.get("awaiting_human")))
        return (parks, waiting.get("verdict"), reported)

    def last_notice(self) -> str:
        """The last comment posted on the issue thread, or "" where there is none."""
        return self.github.posted_comments[-1][1] if self.github.posted_comments else ""

    def fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set(NOTES, "x" * filled)
        self.github.write_pinned_state(self.issue, state)

    def fills_to(self, spare: int) -> None:
        """Fill the pinned comment with operator notes to `spare` characters short of its ceiling."""
        self.fills(0)
        written = len(pinned_state_body(self.pinned()))
        self.fills(MAX_PINNED_BODY - written - spare)

    def _prepares(self, message: str) -> None:
        """The returned round as the world's own is prepared, then filed by `entry` over the state it left in hand.

        How much of the comment what that run staged, and could not persist,
        takes is kept as `staged`.
        """
        state = self.github.read_pinned_state(self.issue)
        run = _world.returned_run(self, state, message)
        # The launch's lifetime charge, which the live round's run circuit takes.
        charged = state.get(_world.AGENT_RUNS_USED) or 0
        state.set(_world.AGENT_RUNS_USED, charged + 1)
        self.decision = _models._ReviewerDecision(run, *_completion_verdicts._parse_review_verdict(message))
        self.prepared = _disposition.prepares_the_verdict(self.github, _TEST_SPEC, self.issue, state, self.decision)
        in_hand = len(pinned_state_body(state.data))
        self.staged = in_hand - len(pinned_state_body(self.pinned()))
        self.entry(self, state, run)
