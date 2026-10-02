# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prepare ordinary split plans, create their children, and publish the parent summary.

The lineage the children inherit is decided before anything is written, and a
lineage that cannot be proved parks the split with no child created. A child
owed the snapshot its parent's own split holds is created with instructions
for reading it after its slice, since the body is what its implementer is
shown -- and a slice whose own text names any other snapshot ref parks the
split too, because nothing keeps that ref for the child it would tell to reuse
it. Every child carries a hidden receipt naming its parent, this split's
attempt, and its slice -- see `split_receipts` -- so the create a crash
returns into can be found again. The parent then records the expected child
count, the attempt, and the whole dependency graph before creation. Only
children without dependencies are activated after the summary and parent
label land, and through the same walk a later dependency poll runs, so the
first release is held to exactly what any later one is.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    child_creation as _child_creation,
    late_child_content as _late_child_content,
    replacement_lineage as _replacement_lineage,
    split_receipts as _split_receipts,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The parts of a declared slice its child's implementer reads.
_DECLARED = ("title", "body")

_UNSUPPORTED_REUSE = (
    "the decomposer's slice {index} ({title!r}) names a snapshot its child would not be kept: `{ref}`. A "
    "child's implementer reads its body, and the one snapshot kept for a child is the one this split records it "
    "as a consumer of -- which its own instructions, appended below the slice, already name. So no child is "
    "created while a slice points at any other. Ask the decomposer to leave snapshot refs out of its slices."
)


def _prepare_split_plan(
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    state.set("expected_children_count", len(plan.children_manifest))
    state.set(_state._UMBRELLA, plan.is_umbrella)
    state.set(_state._SPLIT_ATTEMPT, plan.attempt)
    dependencies = plan.declared_dependencies()
    if dependencies:
        state.set("dep_graph", dependencies)
    gh.write_pinned_state(issue, state)


def _planned(
    issue_number: int, lineage: _replacement_lineage.ReplacementLineage, parsed: dict,
) -> _SplitPlan:
    """The plan for this manifest, each child stamped with its receipt and told where any snapshot it is owed is.

    Both after the slice the manifest declared, which is what a human reads
    first. The receipt is minted for this split alone. The instructions go
    last, exactly as a late split's own children are told, because the pinned
    pointer is what the child's guard reads and the body is what its
    implementer reads -- one without the other is a snapshot nobody uses, or
    instructions nothing protects. A child owed no snapshot is told none.
    """
    attempt = _split_receipts.mint_attempt()
    children = _split_receipts.stamped(parsed[_state._CHILDREN], issue_number, attempt, lineage.instructions)
    plan = _SplitPlan.start(children, bool(parsed.get(_state._UMBRELLA)), lineage)
    return replace(plan, attempt=attempt)


def _unsupported_reuse(lineage: _replacement_lineage.ReplacementLineage, parsed: dict) -> str | None:
    """The park notice for the first slice naming a snapshot its child would not be kept, or None.

    Asked of the slice as the decomposer declared it, before the instructions
    this split appends, and of every ref its title and body name however they
    name it -- the same reading a recovery holds a recorded child's text to.
    Kept is the one ref the child is pointed at, by the names the lineage
    says it may be told: this repository's mirror of it included, and another
    repository's mirror of the same numbers not. A child owed no pointer is
    kept none, and that includes every child of an issue no late split
    charged. A ref a descendant was itself cut from is exactly that: protected
    for the descendant by its parent's ledger, and for none of the children it
    goes on to create.
    """
    for index, child in enumerate(parsed[_state._CHILDREN]):
        foreign = _late_child_content._named_snapshots(*map(child.get, _DECLARED)) - lineage.told
        if foreign:
            return _UNSUPPORTED_REUSE.format(index=index, title=child["title"], ref=min(foreign))
    return None


def _create_child_issues(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, parsed: dict,
) -> _SplitPlan | None:
    """Crash-safe child issue creation loop for a `split` manifest.

    Returns the populated split plan on success, or None when the lineage
    could not be proved or a create/seed step failed and the parent was
    parked (caller must return).

    Crash-safe sequence:
      0. Decide the late lineage the children inherit, off the record this
         tick already holds. One that cannot be proved parks here, before
         any marker is written -- so nothing is created, and the resume a
         reply buys asks the decomposer again rather than recovering a
         split that never started. A slice naming a snapshot its child
         would not be kept parks the same way.
      1. Persist `expected_children_count` (with the umbrella flag, the
         split attempt, and the whole dependency graph) BEFORE creating any
         child. The half-finished recovery uses these to tell a partial loop
         apart from a completed one, to find a child created and never
         recorded by the receipt that names this attempt and its slice, and
         to finalize to the right label after a mid-loop SIGKILL.
      2. For each child: create the GitHub issue, then IMMEDIATELY record
         its number in parent state -- on the snapshot's consumer ledger
         too, where the child is owed a pointer -- before any further
         non-idempotent work. A SIGKILL between these two steps is
         unavoidable; persisting first means the worst case is an orphan
         child with nothing seeded and nothing pointing it at a snapshot,
         which the recovery finds by its receipt -- not a duplicate child
         created by a decomposer respawn.
      3. Seed child pinned state: the parent link, and the lineage decided
         in step 0. Failure here parks but parent state already records
         the child, so no respawn happens.
    """
    lineage = _replacement_lineage.read_replacement_lineage(state, issue, spec)
    refusal = lineage.refusal or _unsupported_reuse(lineage, parsed)
    if refusal is not None:
        _replacement_lineage.park_unproved(gh, issue, state, refusal)
        return None
    plan = _planned(issue.number, lineage, parsed)
    _prepare_split_plan(gh, issue, state, plan)
    for idx, _child in enumerate(plan.children_manifest):
        if not _child_creation._create_planned_child(gh, issue, state, plan, idx):
            return None
    return plan


def _split_summary(plan: _SplitPlan) -> tuple[str, WorkflowLabel]:
    summary = "\n".join(
        f"- #{number}: {child['title']}" for number, child in plan.created
    )
    if plan.is_umbrella:
        announcement = (
            f":bookmark_tabs: decomposer split this into {len(plan.created)} "
            f"child issue(s); marking parent as `{WorkflowLabel.UMBRELLA}` "
            "(no implementation of its own; will auto-resolve once every "
            f"child resolves):\n\n{summary}"
        )
        return announcement, WorkflowLabel.UMBRELLA
    announcement = (
        f":bookmark_tabs: decomposer split this into {len(plan.created)} "
        f"child issue(s):\n\n{summary}"
    )
    return announcement, WorkflowLabel.BLOCKED


def _activate_initial_split_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    plan: _SplitPlan,
) -> None:
    """Release the children with no dependency, through the walk the parent's polls run.

    That walk, over the children this tick just created and still wear their
    birth label, so the first release is held to exactly what a later one
    is: the lineage decision asked again off the parent's record, and each
    child as it reads now -- its link, its seed, its pointer, its text --
    since anything may have moved between the seed and here. Best-effort: a
    failure leaves the children `blocked`, and the parent's next dependency
    poll walks them again, treating a child with no recorded deps as
    deps-satisfied.
    """
    children = [number for number, _ in plan.created]
    try:
        _activation._activate_created_children(gh, spec, issue, state, children)
    except Exception:
        log.exception(
            "issue=#%s could not release its new children; the parent's dependency walk will retry on its next poll",
            issue.number,
        )


def _finalize_split(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    """Post the split summary, flip the parent label, and activate children.

    children/dep_graph/decomposed_at are already durable from the
    writes in `_create_child_issues`. Flip the parent label to
    `blocked` (or `umbrella` when the parent has no implementation work of
    its own), then activate no-dep children. Activation only runs AFTER the
    final parent-state write, so a crash here cannot leave a runnable
    orphan child against a `decomposing`-labeled parent; and it is the
    dependency walk's own, so a child is released here only as that walk
    would release it.
    """
    summary_intro, final_label = _split_summary(plan)
    _comments._post_issue_comment(gh, issue, state, summary_intro)
    gh.set_workflow_label(issue, final_label)
    gh.write_pinned_state(issue, state)
    _activate_initial_split_children(gh, spec, issue, state, plan)
