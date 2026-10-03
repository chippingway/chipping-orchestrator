# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval whose squash publishes another head, and the dispatcher ticks behind it.

The world is the live reviewer round (`evidence_round_test_support`), ticked
whole -- the evidence reconciliation, then the validating handler, or the
handler the issue's label routes to on a dispatcher tick -- with the
squash seam standing in for a rewrite that publishes: it records its collapse
the way the real one does before it rewrites, and stands the pull request on
the head it pushed. Every commit reads as one tree unless a case stands
another tree in for the squashed head, and a later tick fetches the branch
standing wherever the pull request stands then, as the remote does. What the
pull request's artifacts say, and which verification records the pinned
comment carries, are read back here too.
"""
from __future__ import annotations

from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.models import _SquashOutcome
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    stage_targets as _stage_targets,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
    verification_transaction as _transaction,
)
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import _agent
from tests.workflow.repo_values import _TEST_SPEC, EXISTING_CHECKOUT
from tests.workflow.stages.validating import (
    evidence_round_test_support as _round,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

HEAD = _round.HEAD

# The commit the squash publishes in the approved head's place, and the base
# and count its collapse record names.
SQUASHED = "5c3a91b7" * 5

COLLAPSED_BASE = "cc33dd44" * 5

COLLAPSED = 3

# A tree no evidence was gathered on, and the pinned record of the approval's claim.
OTHER_TREE = "7e5a1c00" * 5

APPROVED_EVIDENCE = "review_approved_evidence"

SQUASH_NOTICE = f":package: squashed {COLLAPSED} commits to 1"

class LandsTheSquash:
    """A squash that rewrites the approved head into `head`, `count` commits collapsed, and publishes it.

    Where `then` is given it is another road's work behind the push, on the case.
    """

    def __init__(self, case, *, head: str = SQUASHED, count: int = COLLAPSED, then=None) -> None:
        self._case = case
        self._head = head
        self._count = count
        self._then = then

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        _collapses.record_pending_collapse(gate.state, head=HEAD, base_sha=COLLAPSED_BASE, count=self._count)
        self._case.pull_request.head.sha = self._head
        if self._then is not None:
            self._then(self._case)
        return _SquashOutcome(success=True, sha=self._head, count=self._count)


class RefusesTheNotice:
    """A pull-request thread that refuses the first squash notice posted to it and takes every other post.

    The one post a handoff stops on: the count it is worded from lives on the
    collapse record, which is kept for the recovery to announce.
    """

    def __init__(self, github) -> None:
        self._posts = github.pr_comment
        self._refused = False

    def __call__(self, pr_number: int, body: str):
        if SQUASH_NOTICE in body and not self._refused:
            self._refused = True
            raise RuntimeError("comment refused")
        return self._posts(pr_number, body)


def dispatcher_tick(github, spec, issue) -> None:
    """One dispatcher tick on `issue`: the evidence reconciliation, then its label's handler where that lets on."""
    label = github.workflow_label(issue)
    if not _transaction._reconciles_pending_evidence(
        github, spec, issue, label, github.read_pinned_state(issue),
    ):
        _stage_targets._call_handler(github, spec, issue, _stage_targets._STAGE_HANDLER_TARGETS[label])


def dispatches(case, github, issue, head: str, **run_options) -> dict:
    """One dispatcher tick on `issue` in `case`'s hermetic world, its checkout here and its branch fetched on `head`.

    An agent run answers as `_agent()` does unless `run_options` says otherwise.
    """
    run_options.setdefault("run_agent", _agent())
    return case._run(
        partial(dispatcher_tick, github, _TEST_SPEC, issue),
        issue_checkout=EXISTING_CHECKOUT,
        fetched_branch_tip=head,
        **run_options,
    )


def reviews_the_squashed_head(case) -> None:
    """Another road's later round over the squashed head: a report of it settled, and a reviewer handed it and returned.

    What the approval was never given: a review subject about that head,
    naming a report the approved one is not, recorded as handed and as
    returned.
    """
    _published_reports.republishes_the_report(case.github, case.issue, "A report of the squashed head.")
    state = case.github.read_pinned_state(case.issue)
    state.set(_review_subjects.RETURNED_SUBJECT, case.handed(state).subject.recorded())
    case.github.write_pinned_state(case.issue, state)


class RefusesTheRelabelOnce:
    """A GitHub that refuses the first relabel and takes every one after it."""

    def __init__(self, github) -> None:
        self._relabels = github.set_workflow_label
        self._refused = False

    def __call__(self, issue, label):
        if not self._refused:
            self._refused = True
            raise RuntimeError("label update rejected")
        return self._relabels(issue, label)


class SquashedRoundWorld(_round.LiveRoundWorld):
    """An issue whose reviewer is about to approve, and whose approval's squash publishes another head."""

    def approves(self, squash=None, **run_options) -> dict:
        """The tick in which a reviewer approves with a passing run and the squash publishes."""
        run_options.setdefault("squash_result", squash or LandsTheSquash(self))
        return self.tick(_round.reviewer(_world.declared_run()), **run_options)

    def later(self, *agents, **run_options) -> dict:
        """A later tick, its branch fetched standing where the pull request stands."""
        run_options.setdefault("fetched_branch_tip", self.pull_request.head.sha)
        return self.tick(*agents, **run_options)

    def moves_the_context(self) -> None:
        """An operator changing `VERIFY_TIMEOUT` for the rest of the case, which moves the verification context."""
        self.enterContext(patch.object(config, "VERIFY_TIMEOUT", config.VERIFY_TIMEOUT + 1))

    def drops_the_record(self, record: str = _review_subjects.RETURNED_SUBJECT, *, popped: bool = False) -> None:
        """A record gone from the pinned comment as a hand edit leaves it: written null, or removed where `popped`.

        The returned review subject unless `record` says which.
        """
        state = self.github.read_pinned_state(self.issue)
        state.set(record, None)
        if popped:
            state.data.pop(record)
        self.github.write_pinned_state(self.issue, state)

    def standing(self) -> tuple:
        """Where the issue stands: its labels, its evidence records, the squash handoff, and each artifact.

        Each artifact as its witness, tested commit, target head, and review
        subject, oldest first; the handoff as the commit it names, "" for none.
        """
        state = PinnedState(state_data=self.pinned())
        artifacts = tuple(
            (found.source, found.tested_sha, found.target_head, found.review_subject)
            for found in _read.artifacts(self)
        )
        handoff = _late_handoffs.read_settled_handoff(state) or ""
        return self.labels(), self._records(state), handoff, artifacts

    def claims(self) -> bool:
        """Whether the approval's claim names the evidence the comment carries: the record owed, or else the current."""
        state = PinnedState(state_data=self.pinned())
        named = _record_state.read_pending_evidence(state) or _settlement.read_current_evidence(state)
        claim = state.get(APPROVED_EVIDENCE) or {}
        return named is not None and claim.get("receipt") == named.receipt

    def _records(self, state: PinnedState) -> tuple:
        """The pending and the current evidence's tested commit and target head, and each history entry's retirement."""
        pending = _record_state.read_pending_evidence(state)
        current = _settlement.read_current_evidence(state)
        return (
            None if pending is None else (pending.binding.tested_sha, pending.binding.target.target_head),
            None if current is None else (current.binding.tested_sha, current.binding.target.target_head),
            tuple(entry.retired.value for entry in _settlement.read_evidence_history(state) or ()),
        )
