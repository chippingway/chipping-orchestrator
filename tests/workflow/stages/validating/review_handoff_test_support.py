# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support` with a change request waiting, handed straight to `review_handoffs`.

A case leaves the request as the disposition hands one over ready --
persisted over the standing subject, the reviewer's launch charged -- keeps
the decision it was returned as (`HandoffWorld.seeds`), and hands it over in
a tick whose developer answers and pushes (`HandoffWorld.hands_over`): through
that decision in the tick its reviewer returned, or from the pinned comment
alone on a later tick, which holds none -- or in a tick that dies on the
relabel ahead of that developer (`HandoffWorld.hands_over_unlaunched`).
Beside that world: a feedback post GitHub refuses, takes answering no usable
id, or takes and loses the response to, once (`RefusesOnce`), the run
circuit's start refused or its response lost (`RefusesTheStart`), and what another road does
between two of the handoff's requests -- a repoint, a run charged, the
feedback anchor moved.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.workflow.engine import run_ledger as _run_ledger
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_handoffs as _handoffs,
    review_verdicts as _verdicts,
)
from tests.workflow.fixtures import _agent, _reported
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS
from tests.workflow.value_helpers import _open_pr_for

# What the reviewer's feedback post says about itself.
FEEDBACK_NOTICE = "requested changes"

# The replay anchor the handoff records, spelled as the comment spells it.
ANCHOR = "pending_fix_reviewer_comment_id"

RESERVATION = "agent_run_reservation"

# The launch identity another road's developer run is charged under.
ANOTHER_LAUNCH = "another-road-developer"

# How a tick runs in which the one developer a request owes answers and pushes.
_FIXING = (("dirty_files", ()), ("push_branch", True), ("head_shas", FIX_HEAD_SHAS))


def developer():
    """The developer run a handed change request is answered by."""
    return _agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed"))


def repoints(case) -> None:
    """Another road pointing `case`'s issue at another pull request than the one its reviewer reviewed."""
    _open_pr_for(case.github, issue_number=_world.ISSUE, pr_number=_world.PR + 1)
    state = case.github.read_pinned_state(case.issue)
    state.set("pr_number", _world.PR + 1)
    case.github.write_pinned_state(case.issue, state)


def moves_the_anchor(case, *, to: str) -> None:
    """Another write of the reviewer-feedback anchor than the handoff's, `to` naming which.

    `nowhere` is the fixing stage's clear of the round's bookmarks, the anchor
    among them; `elsewhere` points it at another comment on the pull request
    than the feedback the request was handed over with; and `a float` spells
    that very comment's id as a float, which the fixing stage's replay
    refuses.
    """
    state = case.github.read_pinned_state(case.issue)
    posted = state.get(ANCHOR)
    others = [said.id for said in case.pull_request.issue_comments if said.id != posted]
    anchor = None
    if to == "elsewhere":
        anchor = others[0]
    elif to == "a float":
        anchor = float(posted)
    state.set(ANCHOR, anchor)
    case.github.write_pinned_state(case.issue, state)


def charges_a_run(case, *, owed: bool = True, pushes: bool = False) -> None:
    """Another road's run, charged and started as the run circuit does.

    `owed` makes it the launch of the developer the handed request waiting is
    owed, whose start records the count it was handed at; otherwise it is
    some other launch -- a reviewer's -- which records none, and may be
    charged before any request is handed. Where it `pushes`, that run pushes
    as a developer answering the request does, standing the pull request on a
    head nobody reviewed.
    """
    state = case.github.read_pinned_state(case.issue)
    owed_at = state.get(_world.RETURNED_VERDICT)["handed"] if owed else None
    _run_ledger._reserve_run(state, ANOTHER_LAUNCH)
    _run_ledger._start_reserved_run(state, owed_at)
    case.github.write_pinned_state(case.issue, state)
    if pushes:
        _world.pushes(case)


class RefusesOnce:
    """A post that fails once where it says `phrase`, and goes through every other time.

    Refused outright, or -- where it `lands` -- taken with an answer whose id
    is `answers`: none at all, or one that is no positive whole comment id; or,
    where `answers` is an exception, taken with its response lost, which
    raises that. `posts` is the client's own pull-request comment request.
    """

    def __init__(self, posts, phrase: str, *, lands: bool, answers: object = None) -> None:
        self._posts = posts
        self._phrase = phrase
        self._lands = lands
        self._answers = answers
        self._failed = False

    def __call__(self, thread, body):
        if self._failed or self._phrase not in body:
            return self._posts(thread, body)
        self._failed = True
        if not self._lands:
            raise RuntimeError("comment rejected")
        self._posts(thread, body)
        if isinstance(self._answers, Exception):
            raise self._answers
        return SimpleNamespace(id=self._answers)


class RefusesTheStart:
    """A pinned-comment write GitHub refuses where it moves a run charge to started, and takes otherwise.

    The window between the run circuit's two writes: the charge and its
    reservation land, and the start that would let the spawn through does not,
    so no agent is invoked. Where it `lands`, GitHub takes that start and
    loses its response instead, which the circuit answers the same way.
    """

    def __init__(self, writes, *, lands: bool = False) -> None:
        self._writes = writes
        self._lands = lands

    def __call__(self, issue, state):
        if state.get(RESERVATION) != "started":
            return self._writes(issue, state)
        if self._lands:
            self._writes(issue, state)
        raise RuntimeError("GitHub refused the edit, or lost its response")


class HandoffWorld(_world.ReviewVerdictWorld):
    """The same issue, whose change request is handed to its developer rather than only prepared."""

    def seeds(self, *, evidence: bool = False) -> _models._ReviewerDecision:
        """Leave a change request waiting as the disposition hands one over ready; the decision it was returned as.

        Its claim is a settled run of the configured suite where `evidence`
        says so, and nothing otherwise, as a reviewer that found a bug
        without running anything leaves it. The reviewer's launch is charged
        as the round's run circuit charges it.
        """
        settled = _read.settles_evidence(self) if evidence else None
        run = _read.seeds_a_verdict(self, settled, _verdicts.CHANGES_REQUESTED)
        state = self.github.read_pinned_state(self.issue)
        charged = state.get(_world.AGENT_RUNS_USED) or 0
        state.set(_world.AGENT_RUNS_USED, charged + 1)
        self.github.write_pinned_state(self.issue, state)
        return _models._ReviewerDecision(run, _verdicts.CHANGES_REQUESTED, _world.REQUESTED)

    def hands_over(self, decision: _models._ReviewerDecision | None = None, **run_options):
        """One tick handing the waiting request over, over the pinned comment as it reads; the developer runs it made.

        Through `decision`, in the tick its reviewer returned, or -- None --
        from the pinned comment alone, as a later tick does. The developer
        that tick launches answers and pushes.
        """
        run_options.setdefault(_world.RUN_AGENT, [developer()])
        for option, setting in _FIXING:
            run_options.setdefault(option, setting)
        return self._run(lambda: self._hands_over(decision), **run_options)[_world.RUN_AGENT]

    def hands_over_unlaunched(self) -> _models._ReviewerDecision:
        """The tick that hands a fresh request over, whose relabel ahead of the launch GitHub refuses; its decision.

        The tick dies on that refusal, so the request is left written as
        handed beside its posted feedback, and nobody launched.
        """
        decision = self.seeds()
        refused = patch.object(self.github, "set_workflow_label", side_effect=RuntimeError("refused"))
        with refused, self.assertRaises(RuntimeError):
            self.hands_over(decision)
        return decision

    def remembers(self) -> None:
        """Keep the pinned comment as it reads now (`remembered`), for a road behind a request to read back."""
        self.remembered = self.pinned()

    def feedback_posts(self) -> list:
        """Every reviewer-feedback comment on the pull request, oldest first."""
        return [said for said in self.pull_request.issue_comments if FEEDBACK_NOTICE in said.body]

    def waiting(self) -> dict | None:
        """The change request the pinned comment has waiting, as it spells it, or None."""
        return self.pinned().get(_world.RETURNED_VERDICT)

    def _hands_over(self, decision: _models._ReviewerDecision | None) -> None:
        """The request handed over through `decision`, or from the comment alone, as this tick reads the comment."""
        state = self.github.read_pinned_state(self.issue)
        if decision is None:
            _handoffs.hands_the_waiting_request_over(self.github, _TEST_SPEC, self.issue, state)
        else:
            _handoffs.hands_the_request_over(self.github, _TEST_SPEC, self.issue, state, decision)
