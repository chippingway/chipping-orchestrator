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

Children an ordinary split created are released on the lineage its record
proved, which may have changed since, so that decision is asked again in
front of every walk -- and every child the walk would release is held, before
the first is relabelled, to what a recovery holds it to (see
`entitlement_lapsed`). Either refusal releases none and parks the parent once.
The split's own same-tick release is this walk too, over the same fresh scan
and behind the same parks; a late split's own children are released on that
split's licence instead.

Held children are logged rather than parked, because the tree is still making
progress: their siblings run concurrently and are what will eventually release
them. The line names the exact unfinished dependencies so an operator reading a
tick log can tell a waiting parent from a stuck one without opening GitHub, and
it is emitted only when something is actually held so a healthy parent stays
quiet.

A child another poller on this host is writing is held the same way, and for
the same reason: nothing is wrong with it. Every child a walk would release is
taken under its own writer claim (`child_claims`) before the first is vouched
for, since vouching reads the child's record and the release writes its label,
and each is read again under it, since the scan the walk chose them from was
read before any claim was taken. One refused claim, or one child no longer
open and `blocked` by then, releases none of them, as one lapse does --
without the park, because the next walk scans again.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    child_claims as _child_claims,
    late_child_content as _late_child_content,
    late_publication as _late_publication,
    models as _models,
    parents as _parents,
    replacement_lineage as _replacement_lineage,
    split_seeds as _split_seeds,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_UNSEEDED_CHILD = (
    "child #{child} would be released without exactly what its split owes it -- its `parent_number` does not "
    "name this issue, its late ancestry is missing or no longer whole, or it carries a snapshot pointer this "
    "split no longer keeps for it (the ref no longer held, or `late_consumers` no longer recording the child). "
    "Released like that, its handler, size gate, or reuse instructions would act on a record nothing vouches "
    "for, so no further child is started while that stands. Repair the child's seed or record it as a consumer "
    "again, or close it."
)


@dataclass
class _ChildActivation:
    gh: GitHubClient
    owner: Issue
    slug: str
    state: PinnedState
    scan: _models._ChildScan
    held: list[_state._HeldChild]
    lineage: _replacement_lineage.ReplacementLineage | None = None
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
        refusal = None if lineage is None else lineage.refusal
        return cls(gh, owner, spec.slug, state, scan, [], lineage, refusal)

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

    def entitlement_lapsed(self, child: Issue, number: int) -> bool:
        """Whether this child is no longer one its split's lineage vouches for, as it stands now.

        Read as it stands now, since any of it may have changed since the
        split wrote it, and held to exactly what a recovery holds it to
        (`ReplacementLineage.repair`): anything that recovery would refuse or
        have to write -- a missing link or seed, a pointer the ledger no
        longer keeps, a lost slot -- and a receipt other than the one stamped
        for its slot (`split_seeds.stamp_lapse`) is a child that may not start.
        A child of an ordinary split is held the same way, so every release
        costs one read of its pinned comment. A lapse latches, and says why.
        """
        if self.stopped:
            return True
        if self.lineage is None:
            return False
        texts = (getattr(child, "title", None), getattr(child, "body", None))
        child_state = self.gh.read_pinned_state(child)
        seed = self.lineage.repair(
            self.state, self.owner.number, number, child_state, _late_child_content._named_snapshots(*texts),
        )
        refusal = seed.refusal or _split_seeds.stamp_lapse(
            self.gh, self.owner, self.state, child, self.lineage.ancestry,
        )
        linked = _state._links_to(child_state.get(_state._PARENT_NUMBER), self.owner.number)
        if linked and refusal is None and seed == _replacement_lineage.SeedRepair():
            return False
        log.error(
            "repo=%s issue=#%s may release no child: #%s is not as its split's lineage owes it",
            self.slug, self.owner.number, number,
        )
        self.refusal = refusal or _UNSEEDED_CHILD.format(child=number)
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

    def consider(self, idx: int, child_number) -> int | None:
        """The child at this index where its dependencies are done, or None; one still waiting is held."""
        number = int(child_number)
        if not self.scan.waiting(number):
            return None
        pending = _pending_dependencies(self.state, self.scan, idx)
        if pending:
            self.held.append((number, pending))
            return None
        return number

    def release(self, releasable: list[int]) -> None:
        """Relabel each child `ready`, once every one of them is vouched for.

        Every child this walk would release is held to its split's lineage
        before the first is relabelled, because the refusal parks the parent
        and a park is meant to leave the split unstarted: a walk that
        released as it checked would start the children in front of the one
        that lapsed. Each relabel is still licensed on its own, immediately in
        front of it -- see `may_release`.

        Every one of them is taken under its own writer claim before that,
        and held until the walk ends: the lineage is read off the child's own
        record and the relabel is a write to it, and a child another poller
        on this host is writing is one this walk can neither vouch for nor
        start. Each is then read again under its claim, and vouched for and
        relabelled off that reading: the scan this walk chose them from was
        read before any claim was taken, and in between that poller may have
        relabelled, finished, or closed one of them -- a window the claim
        closes only for a reading taken behind it. So a refused claim, a read
        that fails, or a child no longer open and `blocked` releases none of
        them, as a lapse does, and parks nothing, since none is one -- the
        next walk scans again.
        """
        with _child_claims.held_children(self.gh, self.owner.number, releasable) as claimed:
            current = _parents._read_child_labels(self.gh, self.owner, releasable) if claimed else None
            if current is None or not all(map(current.waiting, releasable)):
                self.held.extend((number, []) for number in releasable)
                return
            if any(self.entitlement_lapsed(current.issues[number], number) for number in releasable):
                self.held.extend((number, []) for number in releasable)
                return
            for number in releasable:
                if self.may_release():
                    self.gh.set_workflow_label(current.issues[number], WorkflowLabel.READY)
                    self.relabeled = True
                else:
                    self.held.append((number, []))


def _pending_dependencies(state: PinnedState, scan: _models._ChildScan, idx: int) -> list[int]:
    dep_graph = state.get("dep_graph") or {}
    dependencies = dep_graph.get(str(idx), [])
    dep_numbers = [
        int(scan.children[int(dep_idx)])
        for dep_idx in dependencies
        if int(dep_idx) < len(scan.children)
    ]
    return [
        number for number in dep_numbers
        if scan.labels.get(number) != _state._DONE
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
    place and stops the walk the same way. Every child it would release is
    claimed, read again, and held to its split's lineage first, and a lapse
    in any one releases none of them.
    """
    activation = _ChildActivation.start(gh, spec, issue, state, scan)
    if activation.refusal is None:
        found = map(activation.consider, range(len(scan.children)), scan.children)
        activation.release([releasable for releasable in found if releasable is not None])
    # Parked once: a parent already awaiting a human is held, not re-parked.
    if activation.refusal is not None and not state.get(_state._AWAITING_HUMAN):
        _replacement_lineage.park_unproved(gh, issue, state, activation.refusal)
    elif activation.relabeled:
        gh.write_pinned_state(issue, state)
    return activation.held


def _activate_created_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    children: list[int],
) -> None:
    """Run this walk over children a split created this tick, the first release of them.

    Over the fresh scan a later poll takes and behind the same parks, since a
    human may have rejected or closed a child while its siblings were still
    being created -- so the split's release is held to exactly what a later
    poll's is.
    """
    scan = _parents._usable_child_scan(gh, spec, issue, state, children)
    if scan is not None:
        _activate_ready_children(gh, spec, issue, state, scan)


def _release_lineage(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, scan: _models._ChildScan,
) -> _replacement_lineage.ReplacementLineage | None:
    """The decision an ordinary split's children here are released on, asked afresh, or None.

    Asked again off the parent's record, for no request, because a dependent
    child starts polls after the record that licensed it may have changed; a
    refusal parks the parent with the notice its creation would have. A late
    split's own register answers None: what licenses releasing those children
    is that split's own, asked by `licence_lapsed`.
    """
    register = _late_state.read_late_generation(state).split_children
    if tuple(int(number) for number in scan.children) == register:
        return None
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
