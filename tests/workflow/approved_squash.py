# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval whose squash publishes another head, and the dispatcher ticks that carry the issue past it.

The world is the review round's (`review_world`), with the squash seam
standing in for a rewrite that publishes: it records its collapse the way the
real one does before it rewrites, and stands the pull request on the head it
pushed. Every commit reads as one tree unless a case stands another tree in for
the squashed head, and a later tick fetches the branch standing wherever the
pull request stands then, as the remote does.

No stage owns it. `validating` drives its approval and the carry behind it
through its own round (`stages/validating/squash_evidence_test_support.py`),
and a stage the approval hands the issue on to drives the same journey through
whole dispatcher ticks (`ApprovedSquashWorld`), each the evidence
reconciliation and then the handler its label routes to. What the pinned
comment's verification records and the pull request's artifacts say afterwards
is read back here too (`SquashedApproval.standing`).
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
from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state
from tests.workflow import review_world as _world
from tests.workflow.fixtures import _agent
from tests.workflow.repo_values import _TEST_SPEC, EXISTING_CHECKOUT

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

    It leaves what the real push does: the collapse recorded, the pull
    request standing on `head`, and this issue's receipt of that push from
    the approved head onto the pull request. Where `then` is given it is
    another road's work behind the push, on the case.
    """

    def __init__(self, case, *, head: str = SQUASHED, count: int = COLLAPSED, then=None) -> None:
        self._case = case
        self._head = head
        self._count = count
        self._then = then

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        _collapses.record_pending_collapse(gate.state, head=_world.HEAD, base_sha=COLLAPSED_BASE, count=self._count)
        _late_publication_state._record_publication(gate.state, self._head, _world.HEAD, _world.PR)
        self._case.pull_request.head.sha = self._head
        if self._then is not None:
            self._then(self._case)
        return _SquashOutcome(success=True, sha=self._head, count=self._count)


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


class SquashedApproval:
    """An issue whose reviewer is about to approve, and whose approval's squash publishes another head.

    Mixed into a world that ticks the issue (`tick`) and reads it back
    (`review_world.ReviewWorld`): which handler a tick reaches is the world's.
    """

    def approves(self, squash=None, **run_options) -> dict:
        """The tick in which a reviewer approves with a passing run and the squash publishes."""
        run_options.setdefault("squash_result", squash or LandsTheSquash(self))
        return self.tick(_world.reviewer(_world.declared_run()), **run_options)

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
        found = tuple(
            (artifact.source, artifact.tested_sha, artifact.target_head, artifact.review_subject)
            for artifact in _world.artifacts(self)
        )
        handoff = _late_handoffs.read_settled_handoff(state) or ""
        return self.labels(), self._records(state), handoff, found

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


class ApprovedSquashWorld(SquashedApproval, _world.ReviewWorld):
    """The approval's squash, ticked whole by the dispatcher: each tick reaches the handler its label routes to."""

    def tick(self, *agents, **run_options) -> dict:
        """One dispatcher tick on the issue, whose agent runs answer `agents` in order."""
        run_options.setdefault(_world.RUN_AGENT, list(agents))
        run_options.setdefault("head_shas", (_world.HEAD,))
        return self._run(partial(dispatcher_tick, self.github, _TEST_SPEC, self.issue), **run_options)
