# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dep-graph walk that decides which children may start next.

A `blocked` child becomes `ready` the moment every dependency the manifest
recorded for it is `done`. A child with no recorded dependencies satisfies that
vacuously, which is deliberate: it is also the retry for a no-dep child whose
same-tick activation flip failed at split time, so nothing has to remember that
the flip was missed.

A child GitHub reports as closed is passed over, whatever label it wears.
Closing an issue does not change its label, so a child a human ended while it
was still `blocked` sits there looking startable forever -- and a walk that
started it would relabel a closed issue `ready`, overriding the close and
handing the umbrella a child that will never report. It is skipped rather than
held, because nothing is going to release it.

A parent whose children a late split handed over is asked one more thing, at
exactly the same place and for exactly the same reason: those children start
on the strength of the pull request their work was superseded on still being
closed, and that can stop being true between one relabel and the next. A walk
that asked once -- or that let its caller ask, one scan of the children
earlier -- would release its second child on evidence taken before its first.
So it is asked off this parent's own record, immediately in front of every
relabel, and a refusal latches: a licence that has lapsed does not come back
inside one walk. A parent that never entered the size gate carries no such
record and answers without a request.

That ask is itself a request, so the latch is taken on both sides of it: once
in front, where it costs nothing to refuse early, and once behind, where a
close a poll observed during the lookup would otherwise reach nothing before
the relabel lands.

Children an ordinary split created are released on the lineage and snapshot
that split proved before creating them, and a dependent one is released polls
later, off a record that may have changed since. So that decision is asked
again, off the parent's record and for no request, in front of every walk
over them -- and in front of each release, the pointer the child itself
carries is held to it: a pointer at a ref the parent's split no longer holds,
or one its consumer ledger no longer records the child against, is a child
told to reuse work nothing keeps for it. Either refusal releases none of the
rest and parks the parent once. A late split's own children are released on
that split's licence instead.

Held children are logged rather than parked, because the tree is still making
progress: their siblings run concurrently and are what will eventually release
them. The line names the exact unfinished dependencies so an operator reading a
tick log can tell a waiting parent from a stuck one without opening GitHub, and
it is emitted only when something is actually held so a healthy parent stays
quiet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import lineage as _lineage, state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_publication as _late_publication,
    models as _models,
    replacement_lineage as _replacement_lineage,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_UNPROTECTED_CHILD = (
    "child #{child} would be released carrying a snapshot pointer this issue's split does not keep for it -- the "
    "ref is no longer held, `late_consumers` no longer records the child, or its pinned comment will not parse so "
    "the pointer cannot be checked. Released, it would be told to reuse work nothing keeps while it runs, so no "
    "further child is started while that stands. Record the child as a consumer again, clear its pointer, or "
    "close it."
)


@dataclass
class _ChildActivation:
    gh: GitHubClient
    owner: Issue
    slug: str
    state: PinnedState
    scan: _models._ChildScan
    held: list[_state._HeldChild]
    lineage: _replacement_lineage.ReplacementLineage = field(default_factory=_replacement_lineage.ReplacementLineage)
    refusal: str | None = None
    relabeled: bool = False
    stopped: bool = False

    @classmethod
    def start(
        cls,
        gh: GitHubClient,
        spec: _config_models.RepoSpec,
        owner: Issue,
        state: PinnedState,
        scan: _models._ChildScan,
    ) -> _ChildActivation:
        lineage = _release_lineage(spec, owner, state, scan)
        return cls(gh, owner, spec.slug, state, scan, [], lineage, lineage.refusal)

    def parent_is_gone(self) -> bool:
        """Whether a poll saw the parent closed since this walk began.

        Asked before EVERY relabel rather than once for the walk, because a
        relabel is a request and the poll runs beside it: a close latched
        after the first child was released must not release the second. It
        costs nothing to ask, and what it protects is an agent started
        against a slice of work somebody has ended.

        Nothing is written here. The parent's own record is not this walk's to
        move -- the handler that called it owns the mark -- and stopping is
        the whole of what a shared dep-graph walk may decide.
        """
        if self.stopped:
            return True
        if not _observations.close_observed(self.slug, self.owner.number):
            return False
        log.warning(
            "repo=%s issue=#%s was observed closed while its children were "
            "being released; releasing none of the rest",
            self.slug, self.owner.number,
        )
        self.stopped = True
        return True

    def licence_lapsed(self) -> bool:
        """Whether a split's own children may still be released, right now.

        Asked before EVERY relabel on the rule the close is asked on: what
        licenses a release here is a fact about a pull request somewhere else,
        and that moves between two requests. Asked off this parent's own
        record rather than handed in, so a caller cannot answer it a scan of
        the children too early -- and so a parent that never entered the gate
        answers without a request at all.

        Latched with the close, because the two mean the same thing to this
        walk -- release none of the rest -- and because re-asking past the
        first refusal spends a request to be told what it already knows.
        """
        if self.stopped:
            return True
        lapsed = _late_publication._release_undone(
            self.gh, self.owner, self.state,
        )
        if not lapsed:
            return False
        log.error(
            "repo=%s issue=#%s may release no child: %s",
            self.slug, self.owner.number, lapsed,
        )
        self.stopped = True
        return True

    def protection_lapsed(self, child: Issue, number: int) -> bool:
        """Whether the pointer this child carries is one its parent's split no longer keeps for it.

        Asked of the child's own pinned comment in front of its release,
        because that pointer is what its guard and its instructions act on,
        and the parent's record decides whether anything still keeps it: a
        pointer is kept only while the split holds the ref and its consumer
        ledger records this child -- the rule the pointer was written under.
        A child carrying no pointer is owed nothing here, and a parent whose
        lineage points no child at a snapshot spends no request. A comment
        that will not parse cannot say which it is, and is held with the
        rest. A lapse latches, and says why for the parent to park on.
        """
        if self.stopped:
            return True
        if self.lineage.ancestry is None:
            return False
        child_state = self.gh.read_pinned_state(child)
        carried = _lineage.read_late_ancestry(child_state)
        kept = self.lineage.child_ancestry(self.state, number)
        # No pointer at all, or exactly the one the ledger still protects.
        owed = {("", ""), (kept.snapshot_ref, kept.snapshot_sha)}
        if child_state.parsed and (carried.snapshot_ref, carried.snapshot_sha) in owed:
            return False
        log.error(
            "repo=%s issue=#%s may release no child: #%s carries a pointer nothing keeps for it",
            self.slug, self.owner.number, number,
        )
        self.refusal = _UNPROTECTED_CHILD.format(child=number)
        self.stopped = True
        return True

    def may_release(self) -> bool:
        """Whether this walk may still relabel the child in front of it.

        The latch first, because it is already in this process and costs
        nothing; then the publication, which is a request; then the latch
        AGAIN, because that request is exactly the kind of window a poll
        observes a close inside. Asking it only in front would license a
        release on a reading the lookup behind it had already outlived --
        the same mistake this walk exists to stop one layer up.

        The last ask is the one with nothing between it and the write, which
        is the whole rule: every barrier here belongs immediately in front of
        the effect it licenses, and the cheapest one can afford to be the
        barrier twice.
        """
        if self.parent_is_gone() or self.licence_lapsed():
            return False
        return not self.parent_is_gone()

    def consider(self, idx: int, child_number) -> None:
        number = int(child_number)
        child = self.scan.issues.get(number)
        if self.scan.labels.get(number) != WorkflowLabel.BLOCKED:
            return
        if child is None or issue_is_closed(child):
            return
        pending = self._pending_dependencies(idx)
        if pending:
            self.held.append((number, pending))
            return
        if self.protection_lapsed(child, number) or not self.may_release():
            self.held.append((number, []))
            return
        self.gh.set_workflow_label(child, WorkflowLabel.READY)
        self.relabeled = True

    def _pending_dependencies(self, idx: int) -> list[int]:
        dep_graph = self.state.get("dep_graph") or {}
        dependencies = dep_graph.get(str(idx), [])
        dep_numbers = [
            int(self.scan.children[int(dep_idx)])
            for dep_idx in dependencies
            if int(dep_idx) < len(self.scan.children)
        ]
        return [
            number for number in dep_numbers
            if self.scan.labels.get(number) != _state._DONE
        ]


def _activate_ready_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _models._ChildScan,
) -> list:
    """Dep-graph activation walk shared by `_handle_blocked` / `_handle_umbrella`.

    Any `blocked` child whose recorded dependencies are all `done` gets
    relabeled `ready`. A child with no recorded deps also flips (vacuous
    all-done over an empty list) -- this recovers any no-dep child that the
    decomposer's same-tick activation step left as `blocked` (network blip,
    label-flip failure, etc.). A child that is closed, or that this scan holds
    no issue for, is passed over: the first has ended and the second cannot be
    written to. Writes pinned state when at least one child was relabeled. Returns the still-held children as
    `[(child_number, pending_dep_numbers)]` for visibility logging.

    A parent a poll observed closed stops the walk where it stands, asked
    again before every relabel: this walk is the one step of a late split
    that puts an agent on somebody's repository, and a close latched after
    the first child was released may not release the second. A pull request a
    split superseded these children out from under is asked about in the same
    place and stops the walk the same way.
    """
    activation = _ChildActivation.start(gh, spec, issue, state, scan)
    if activation.refusal is None:
        for idx, child_number in enumerate(scan.children):
            activation.consider(idx, child_number)
    # Parked once: a parent already awaiting a human is held, not re-parked.
    if activation.refusal is not None and not state.get(_state._AWAITING_HUMAN):
        _replacement_lineage.park_unproved(gh, issue, state, activation.refusal)
    elif activation.relabeled:
        gh.write_pinned_state(issue, state)
    return activation.held


def _release_lineage(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, scan: _models._ChildScan,
) -> _replacement_lineage.ReplacementLineage:
    """The decision an ordinary split's children here are released on, asked afresh.

    The lineage and snapshot an ordinary split proved before creating them are
    what licenses starting them, and a dependent child starts polls later,
    off a record that may have changed since: a snapshot entry that no longer
    reads as held or released, a base gone, an ancestry damaged. So the same
    decision is asked again, off the parent's record and without a request,
    in front of every walk; its refusal releases none of them and parks the
    parent with the notice its creation would have parked on.

    A late split's own children -- exactly the ones its register records --
    answer the ordinary lineage: they were never created under this
    decision, and what licenses releasing them is that split's own, asked by
    `licence_lapsed`.
    """
    register = _late_state.read_late_generation(state).split_children
    if tuple(int(number) for number in scan.children) == register:
        return _replacement_lineage.ReplacementLineage()
    return _replacement_lineage.read_replacement_lineage(state, issue, spec)


def _held_dependency_line(child_number: object, pending: list) -> str:
    """Format one held child and the unfinished dependencies gating it."""
    return f"#{child_number} waits on {_state._issue_ref_list(pending)}"


def _log_held_children(
    issue: Issue, parent_kind: str, children: list, child_labels: dict,
    held: list,
) -> None:
    """Surface which children are still held under a parent and the exact
    unfinished dependencies gating each, so an operator can see at a glance
    why a decomposed parent is not advancing.

    Children whose deps are satisfied are intentionally NOT held -- they run
    concurrently while the parent waits, which is what drives the tree to
    completion. Logged only when something is held to keep a healthy parent
    from spamming the tick log. `parent_kind` is `"blocked"` or `_UMBRELLA`.
    """
    if not held:
        return
    done_count = sum(
        1 for lbl in child_labels.values() if lbl == _state._DONE
    )
    summary = "; ".join(
        _held_dependency_line(cn, pending) for cn, pending in held
    )
    log.info(
        "issue=#%s %s parent: %d/%d children done, %d held: %s",
        issue.number, parent_kind, done_count, len(children), len(held),
        summary,
    )
