# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, whose returned verdict is disposed of rather than only prepared.

A returned run goes to `review_disposition.disposes_of_the_verdict`, and a
later tick is the dispatcher's evidence reconciliation and then
`review_disposition.finishes_the_verdict`, over the run the verdict was
returned in, which a later tick's caller rebuilds (`run`). What those ticks
leave is read back here -- the verdict waiting, the park, the feedback posted,
the last notice -- beside how a tick runs whose developer answers a change
request and pushes (`fixing`), and the replies no pinned comment can record
over the notes that fill it (`UNRECORDED`, `fills`). The doubles a tick posts
or writes through are the owners' own: `review_handoff_test_support` for the
feedback post and the run circuit, `review_park_test_support` for a park's
notice and room.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import completion_verdicts as _completion_verdicts
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_disposition as _disposition,
    review_parks as _parks,
)
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import (
    review_handoff_test_support as _handoff,
    review_park_test_support as _parked,
    review_verdict_test_support as _world,
)
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

# The replay anchor a change request's handoff records, and the member of the
# verdict's record saying at which run count it was handed.
ANCHOR = _handoff.ANCHOR

HANDED = "handed"

# A change request's feedback longer than most of what the pinned comment
# holds, and a failed run's output the transaction quotes again: the filler
# leaves room for the round's own records and not for the verdict, or for the
# verdict and not its transaction.
_LONG = "12 passed, 1 failed " * 1000

# Each verdict that cannot be persisted, the operator notes filling the comment
# ahead of it, and why it went unrecorded: no room for the verdict, no room for
# its transaction beside it, or feedback in words UTF-8 cannot carry -- which a
# reviewer's JSON decodes a lone surrogate into -- however much room there is.
UNRECORDED = (
    (
        "no room for the verdict",
        f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED",
        MAX_PINNED_BODY - len(_LONG),
        _parks.NO_ROOM,
    ),
    (
        "no room for its evidence",
        _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=_LONG),
        MAX_PINNED_BODY - len(_LONG) * 3 // 2,
        _parks.NO_ROOM,
    ),
    ("feedback UTF-8 cannot carry", "1. Handle \ud800 too.\n\nVERDICT: CHANGES_REQUESTED", 0, _parks.UNREADABLE),
)


# How an approval's tick runs: its checkout standing on the head the reviewer
# was handed.
ON_THE_HEAD = MappingProxyType({"head_shas": (_world.HEAD,)})


def fixing() -> dict:
    """How a tick runs in which the one developer a change request owes answers it and pushes."""
    return {
        _world.RUN_AGENT: [_handoff.developer()],
        "dirty_files": (),
        "push_branch": True,
        "head_shas": FIX_HEAD_SHAS,
    }


def fills(case, filled: int) -> None:
    """Put `filled` characters of operator notes on `case`'s pinned comment."""
    state = case.github.read_pinned_state(case.issue)
    state.set("operator_notes", "x" * filled)
    case.github.write_pinned_state(case.issue, state)


def last_notice(case) -> str:
    """The last comment posted on `case`'s issue thread, or "" where there is none."""
    posted = case.github.posted_comments
    return posted[-1][1] if posted else ""


class DisposedVerdictWorld(_world.ReviewVerdictWorld):
    """The same issue, whose returned verdict is disposed of rather than only prepared."""

    def setUp(self) -> None:
        super().setUp()
        # The run the verdict waiting on the comment was returned in.
        self.run: _models._ReviewerRun | None = None

    def finishes(self, *, meanwhile=None, **run_options) -> dict:
        """One later tick: the evidence reconciliation, then the waiting verdict finished where it is ready.

        `meanwhile` is another road's work once the tick has read the comment
        it acts over.
        """
        run_options.setdefault(_world.RUN_AGENT, [])
        return self._run(lambda: self._finishes(meanwhile), **run_options)

    def waiting(self) -> str | None:
        """Which verdict the pinned comment has waiting, or None."""
        return (self.pinned().get(_world.RETURNED_VERDICT) or {}).get("verdict")

    def parked(self) -> tuple:
        """The park the pinned comment records and whether it waits, the verdict waiting, and every park reported."""
        pinned = self.pinned()
        flags = (pinned.get("park_reason"), bool(pinned.get("awaiting_human")))
        reasons = [event["reason"] for event in _parked.reported(self)]
        return (flags, self.waiting(), reasons)

    def feedback_posts(self) -> list[str]:
        """Every reviewer-feedback comment on the pull request, oldest first."""
        return [said.body for said in self.pull_request.issue_comments if _handoff.FEEDBACK_NOTICE in said.body]

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
        """The verdict the comment carries, finished over the run it was returned in, past the reconciliation."""
        if _world.reconciles(self):
            return
        state = self.github.read_pinned_state(self.issue)
        if meanwhile is not None:
            meanwhile(self)
        _disposition.finishes_the_verdict(self.github, _TEST_SPEC, self.issue, state, self.run)
