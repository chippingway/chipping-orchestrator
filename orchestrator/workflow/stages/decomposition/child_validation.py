# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Split-child text and dependency validation before graph traversal.

A dependency must be a real integer naming another child in this manifest.
Invalid text or dependency shape is reported before the graph is walked.

Every child states its list -- `[]` for none -- whoever wrote it: the prompt
asks a fresh reply for one, and a recorded manifest is held to the same rule,
since the record is that reply kept. A missing or null one is refused naming
the child and the field: read as "no prerequisites" it would create and
release a child its own body says must wait.
"""
from __future__ import annotations

_DEPENDS_ON = "depends_on"


def _is_nonempty_text(text_value: object) -> bool:
    return isinstance(text_value, str) and bool(text_value)


def _manifest_child_text_error(
    child: object, child_index: int,
) -> str | None:
    """Validate one child object and its required text fields."""
    if not isinstance(child, dict):
        return f"child {child_index} is not an object"
    if not _is_nonempty_text(child.get("title")):
        return f"child {child_index} missing title or body"
    if not _is_nonempty_text(child.get("body")):
        return f"child {child_index} missing title or body"
    return None


def _manifest_child_dependencies(
    child: dict, child_index: int,
) -> tuple[list | None, str | None]:
    """Return one child's stated dependency list, or why it is not one."""
    if _DEPENDS_ON not in child:
        return None, f"child {child_index} missing {_DEPENDS_ON}"
    dependencies = child[_DEPENDS_ON]
    if dependencies is None:
        return None, f"child {child_index} {_DEPENDS_ON} is null"
    if not isinstance(dependencies, list):
        return None, f"child {child_index} {_DEPENDS_ON} must be a list"
    return dependencies, None


def _is_valid_dependency(
    dependency_index: object,
    *,
    child_index: int,
    child_count: int,
) -> bool:
    """Validate type, bounds, and the no-self-edge invariant."""
    if isinstance(dependency_index, bool):
        return False
    if not isinstance(dependency_index, int):
        return False
    if dependency_index < 0 or dependency_index >= child_count:
        return False
    return dependency_index != child_index


def _manifest_child_error(
    child: object, child_index: int, child_count: int,
) -> str | None:
    """Return the first structural error for one split child."""
    text_error = _manifest_child_text_error(child, child_index)
    if text_error is not None:
        return text_error
    dependencies, dependency_error = _manifest_child_dependencies(child, child_index)
    if dependency_error is not None:
        return dependency_error
    for dependency_index in dependencies or []:
        if not _is_valid_dependency(
            dependency_index,
            child_index=child_index,
            child_count=child_count,
        ):
            return (
                f"child {child_index} has invalid dependency "
                f"{dependency_index!r}"
            )
    return None
