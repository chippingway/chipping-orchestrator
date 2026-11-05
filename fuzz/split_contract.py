# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The split-manifest contract, stated apart from the validators it checks.

What the decompose prompt asks a split for and the parser promises to hold it
to (`workflow/stages/decomposition/manifest.py` and the validators behind it):
one to ten children, an `umbrella` that is a boolean where it is given, and
children that are objects with nonempty `title` and `body` strings and a
stated `depends_on` list of integers naming other children, the graph they
draw free of cycles. The manifest target asks this of every split the parser
accepts, so the graph is walked here by eliminating whatever waits on nothing
left rather than by the depth-first search the parser uses: two walks
agreeing is evidence, one walk asked twice is not.

`broken_children` derives, from children that hold to it, the ones that must
not: each child with its list missing, null, or not a list, an entry that is
a boolean, a float, a string, negative, past the last child, or far past any,
an edge to itself, and an edge back along each distinct one already drawn. A
list may name a prerequisite more than once and still be valid, so an edge is
taken once however often it is listed: what a reply derives is bounded by its
graph, ten children at most, never by the length of a list. Each variant is
the children as they were read with one child replaced, sharing the others
rather than copying them.
"""
from __future__ import annotations

from collections.abc import Iterator

MAX_CHILDREN = 10
DEPENDS_ON = "depends_on"

# Entries a dependency list may not hold, whatever the graph: JSON's `true`
# and `0.0` are not the index 0, a string is not a number, -1 names no child,
# and neither does an integer no machine word holds.
_FOREIGN_ENTRIES = (True, float(0), "0", -1, 18_446_744_073_709_551_616)

# Values a stated list may not be: null, and the falsy scalar and object that
# would read as "no prerequisites" if anything coerced them.
_NOT_LISTS = (None, 0, {})

# Stands in for a list a child leaves unstated, which its variant drops.
_UNSTATED = object()


def is_valid_split(manifest: dict) -> bool:
    """Whether a split manifest holds to the contract."""
    children = manifest.get("children")
    if not isinstance(children, list) or not 1 <= len(children) <= MAX_CHILDREN:
        return False
    umbrella = manifest.get("umbrella")
    if umbrella is not None and not isinstance(umbrella, bool):
        return False
    graph = [
        _dependencies(index, child, len(children))
        for index, child in enumerate(children)
    ]
    return None not in graph and _is_acyclic(graph)


def broken_children(children: list[dict]) -> Iterator[list[dict]]:
    """Every variant of valid `children` the contract refuses, one rule broken in each."""
    for index, child in enumerate(children):
        for listing in _broken_listings(child[DEPENDS_ON], index, len(children)):
            yield _with_dependencies(children, index, listing)
    for index, child in enumerate(children):
        for dependency in dict.fromkeys(child[DEPENDS_ON]):
            yield _with_dependencies(children, dependency, [*children[dependency][DEPENDS_ON], index])


def _dependencies(index: int, child: object, count: int) -> list | None:
    """The child's stated prerequisites where the child holds to the contract, else None."""
    if not isinstance(child, dict):
        return None
    texts = [child.get("title"), child.get("body")]
    if not all(isinstance(text, str) and text for text in texts):
        return None
    listed = child.get(DEPENDS_ON)
    if not isinstance(listed, list):
        return None
    return listed if all(_is_another_child(entry, index, count) for entry in listed) else None


def _is_another_child(entry: object, index: int, count: int) -> bool:
    if isinstance(entry, bool) or not isinstance(entry, int):
        return False
    return 0 <= entry < count and entry != index


def _is_acyclic(graph: list[list[int]]) -> bool:
    """Whether eliminating every child whose prerequisites are all eliminated eliminates them all."""
    prerequisites = [set(listed) for listed in graph]
    eliminated: set[int] = set()
    ready = {0}
    while ready:
        ready = {
            index for index, waiting in enumerate(prerequisites)
            if index not in eliminated and waiting <= eliminated
        }
        eliminated.update(ready)
    return len(eliminated) == len(graph)


def _broken_listings(stated: list, index: int, count: int) -> tuple:
    entries = (*_FOREIGN_ENTRIES, count, index)
    return (_UNSTATED, *_NOT_LISTS, *([*stated, entry] for entry in entries))


def _with_dependencies(children: list[dict], index: int, dependencies: object) -> list[dict]:
    """`children` with one child's list replaced, or dropped for `_UNSTATED`, and every other child shared."""
    replaced = dict(children[index])
    replaced.pop(DEPENDS_ON)
    if dependencies is not _UNSTATED:
        replaced[DEPENDS_ON] = dependencies
    variant = list(children)
    variant[index] = replaced
    return variant
