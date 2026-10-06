# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, whose returned verdict is parked rather than acted on.

A case files a park directly, the way the disposition service does
(`disposed_verdict_test_support` goes through that service instead). An
approval parks under `reviewer_unverified` from a verdict an earlier tick
persisted (`awaits`), over the comment as the tick reads it. A change request
parks under `reviewer_unrecorded` over the run's own records staged unwritten
-- the launch, its charge, and the return -- since the verdict itself never
went down, measured against the comment its subject was resolved over.

Beside that world: another road's work behind a park's notice, which is
`review_verdict_test_support.AnotherRoadBehind` over the client's issue-thread
post, the moves that road can make that no other case makes -- a repoint, a
verdict put in the place of the one parked -- a notice GitHub takes without
answering its id (`LeavesNoId`), operator notes filling the pinned comment
-- or the room a change request's handoff needs in it (`fills_to`) -- and what
each park that landed reported (`reported`).
"""
from __future__ import annotations

from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.stages.validating import (
    review_parks as _parks,
    review_records as _review_records,
    review_verdicts as _verdicts,
)
from tests.workflow.stages.validating import review_verdict_test_support as _world
from tests.workflow.value_helpers import _open_pr_for

UNVERIFIED = "reviewer_unverified"

UNRECORDED = "reviewer_unrecorded"

# What each park's notice says about itself.
NOTICES = MappingProxyType({
    UNVERIFIED: "approved without the verification evidence",
    UNRECORDED: "could not be recorded",
})

# Why the approval parked under `reviewer_unverified` earned no evidence.
REFUSAL = "it named no verification run"

# Why each park refuses its verdict, unless a case says otherwise.
_WHY = MappingProxyType({UNVERIFIED: REFUSAL, UNRECORDED: _parks.NO_ROOM})

PARK_EVENT = "park_awaiting_human"

ISSUE_COMMENT = "comment"

LAST_ACTION = "last_action_comment_id"

# What each park's reviewer returned: an approval, and a change request.
_RETURNED = MappingProxyType({
    UNVERIFIED: "LGTM\n\nVERDICT: APPROVED",
    UNRECORDED: f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED",
})


# What a park's event carries that says nothing about the park: when, and where.
_EVENT_FRAME = frozenset(("ts", "repo", "issue", "event"))


def saying(phrase: str):
    """Whether a post's body says `phrase`, for a request another road lands behind."""
    return lambda body: phrase in body


def fills_to(case, spare: int, *, handing: bool = False) -> None:
    """Fill `case`'s pinned comment with operator notes to `spare` characters short of its ceiling.

    Where `handing`, the comment is measured with the change request it has
    waiting at its widest handoff, beside its developer's charge
    (`ReturnedVerdict.at_its_handoff`), so `spare` is what that handoff leaves.
    """
    state = case.github.read_pinned_state(case.issue)
    state.set("operator_notes", "")
    measured = state
    if handing:
        measured = _verdicts.read_returned_verdict(state).at_its_handoff(state)
    notes = MAX_PINNED_BODY - len(pinned_state_body(measured.data)) - spare
    state.set("operator_notes", "x" * notes)
    case.github.write_pinned_state(case.issue, state)


def repoints(case) -> None:
    """Another road pointing `case`'s issue at another pull request than the one its reviewer reviewed."""
    _open_pr_for(case.github, issue_number=_world.ISSUE, pr_number=_world.PR + 1)
    state = case.github.read_pinned_state(case.issue)
    state.set("pr_number", _world.PR + 1)
    case.github.write_pinned_state(case.issue, state)


def replaces_the_verdict(case, record: dict | None = None) -> None:
    """Another road putting `record` waiting where the verdict is written.

    By default a later round's change request, of the subject `case`'s run
    was handed.
    """
    state = case.github.read_pinned_state(case.issue)
    if record is None:
        subject = case.run.subject.recorded()
        record = _verdicts.ReturnedVerdict(1, _verdicts.CHANGES_REQUESTED, subject, _world.REQUESTED).recorded()
    state.set(_verdicts.RETURNED_VERDICT, record)
    case.github.write_pinned_state(case.issue, state)


def reported(case) -> list[dict]:
    """What each park that landed on `case`'s issue reported, beside its reason."""
    return [
        {field: said for field, said in event.items() if field not in _EVENT_FRAME}
        for event in case.github.recorded_events
        if event["event"] == PARK_EVENT
    ]


class LeavesNoId:
    """An issue-thread post that goes through, and answers no comment where it says `phrase`, once."""

    def __init__(self, posts, phrase: str) -> None:
        self._posts = posts
        self._phrase = phrase
        self._left = 1

    def __call__(self, thread, body):
        said = self._posts(thread, body)
        if self._left and self._phrase in body:
            self._left = 0
            return None
        return said


class ParkedVerdictWorld(_world.ReviewVerdictWorld):
    """The same issue, whose returned verdict parks instead of being acted on.

    The thread is read through the pinned comment, as the pickup leaves it, so
    a park's notice has a watermark to carry over itself.
    """

    def setUp(self) -> None:
        super().setUp()
        state = self.github.read_pinned_state(self.issue)
        state.set(LAST_ACTION, state.comment_id)
        self.github.write_pinned_state(self.issue, state)
        # The run the last park was filed over.
        self.run = None

    def awaits(self, reason: str) -> None:
        """Leave what `reason`'s park refuses where its tick finds it.

        An approval of the standing subject waiting, with its run's records, as
        the tick that persisted it wrote them; a verdict nothing could record
        is on the comment nowhere.
        """
        if reason != UNVERIFIED:
            return
        state = self.github.read_pinned_state(self.issue)
        run = _world.returned_run(self, state, _RETURNED[UNVERIFIED])
        _review_records._records_the_return(state, run.agent_result.usage, run.agent_result.session_id, run.subject)
        returned = _verdicts.ReturnedVerdict(run.round_n, _verdicts.APPROVED, run.subject.recorded())
        state.set(_verdicts.RETURNED_VERDICT, returned.recorded())
        self.github.write_pinned_state(self.issue, state)

    def parks(self, reason: str, meanwhile=None, *, why: str = "") -> None:
        """One tick filing the park `reason` names; `meanwhile` is another road's work once the tick has read.

        `why` is the refusal the park answers: `REFUSAL` for an approval and
        `NO_ROOM` for a verdict nothing could record, unless a case names one.
        """
        refused = why or _WHY[reason]
        self._run(partial(self._parks, reason, meanwhile, refused), run_agent=[])

    def behind_the_notice(self, reason: str, road) -> None:
        """The tick filing `reason`'s park, with `road` done by another road once its notice is posted."""
        behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, saying(NOTICES[reason]), road)
        with patch.object(self.github, ISSUE_COMMENT, behind):
            self.parks(reason)

    def unidentified(self, reason: str, road=None) -> None:
        """The tick filing `reason`'s park, over a notice GitHub takes without answering its id.

        `road` is another road's work once that notice is posted, where given.
        """
        posts = self.github.comment
        if road is not None:
            posts = _world.AnotherRoadBehind(self, ISSUE_COMMENT, saying(NOTICES[reason]), road)
        with patch.object(self.github, ISSUE_COMMENT, LeavesNoId(posts, NOTICES[reason])):
            self.parks(reason)

    def parked(self) -> tuple:
        """The park the pinned comment records and whether it waits, the verdict waiting, and every park reported."""
        pinned = self.pinned()
        waiting = pinned.get(_verdicts.RETURNED_VERDICT) or {}
        flags = (pinned.get("park_reason"), bool(pinned.get("awaiting_human")))
        reasons = [event["reason"] for event in reported(self)]
        return (flags, waiting.get("verdict"), reasons)

    def _parks(self, reason: str, meanwhile, why: str) -> None:
        """The park, filed as the disposition service will file it."""
        state = self.github.read_pinned_state(self.issue)
        self.run = _world.returned_run(self, state, _RETURNED[reason])
        if reason == UNRECORDED:
            # The launch's lifetime charge, and what the returned run leaves.
            charged = state.get(_world.AGENT_RUNS_USED) or 0
            state.set(_world.AGENT_RUNS_USED, charged + 1)
            returned = self.run.agent_result
            _review_records._records_the_return(state, returned.usage, returned.session_id, self.run.subject)
        if meanwhile is not None:
            meanwhile(self)
        if reason == UNVERIFIED:
            _parks.parks_unverified(self.github, self.issue, state, self.run, why)
        else:
            _parks.parks_unrecorded(self.github, self.issue, state, self.run, why)
