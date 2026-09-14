# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Split-manifest envelope bounds, child validation, and dependency cycles.

The envelope requires a bounded nonempty child list and a boolean umbrella
flag when present. Every child validates before cycle detection indexes the
graph, so malformed references remain refusals instead of traversal errors.
"""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition import child_validation as _child_validation

_MAX_CHILDREN = 10


def _split_manifest_children(
    manifest: dict,
) -> tuple[list | None, str | None]:
    """Return the bounded, non-empty children list for a split decision."""
    children = manifest.get("children")
    if not isinstance(children, list) or not children:
        return None, "split decision requires non-empty children list"
    if len(children) > _MAX_CHILDREN:
        return None, f"too many children ({len(children)} > {_MAX_CHILDREN})"
    return children, None


def _manifest_umbrella_error(manifest: dict) -> str | None:
    """Validate the optional umbrella flag without truthy coercion."""
    umbrella = manifest.get("umbrella")
    if umbrella is not None and not isinstance(umbrella, bool):
        return "umbrella must be a boolean"
    return None


def _dep_cycle_visit(
    child_index: int, children: list[dict], color: list[int],
) -> bool:
    """DFS one node of the children dep graph; True on a back-edge to a node
    still on the stack.

    `color` is mutated in place (0=unvisited, 1=on-stack, 2=finished) and
    shared across the whole walk, so a node finished on one root is never
    re-descended from another.
    """
    color[child_index] = 1
    for dependency_index in (children[child_index].get("depends_on") or []):
        if color[dependency_index] == 1:
            return True
        if color[dependency_index] == 0 and _dep_cycle_visit(
            dependency_index, children, color,
        ):
            return True
    color[child_index] = 2
    return False


def _has_dep_cycle(children: list[dict]) -> bool:
    """DFS for back-edges in the children dep graph (white/gray/black)."""
    color = [0 for _ in children]  # 0=unvisited, 1=on-stack, 2=finished
    return any(
        color[child_index] == 0
        and _dep_cycle_visit(child_index, children, color)
        for child_index in range(len(children))
    )


def _manifest_children_error(children: list) -> str | None:
    """Validate every child and then the dependency graph as a whole."""
    for child_index, child in enumerate(children):
        child_error = _child_validation._manifest_child_error(
            child, child_index, len(children),
        )
        if child_error is not None:
            return child_error
    if _has_dep_cycle(children):
        return "dependency graph has a cycle"
    return None


def _split_manifest_error(manifest: dict) -> str | None:
    """Return the first split-only manifest validation error."""
    children, children_error = _split_manifest_children(manifest)
    if children_error is not None:
        return children_error
    umbrella_error = _manifest_umbrella_error(manifest)
    if umbrella_error is not None:
        return umbrella_error
    return _manifest_children_error(children or [])
