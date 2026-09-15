# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a repository skill is defined, and how its frontmatter reads.

A harness decides whether to pull a skill from its `name` and `description`
frontmatter alone, so the metadata tests read exactly those fields and leave
the instructions below them free to change.
"""
from __future__ import annotations

from itertools import takewhile
from pathlib import Path

from orchestrator.skills import discovery

REPO_ROOT = Path(__file__).resolve().parents[2]

_FRONTMATTER_FENCE = "---"
_YAML_BLOCK_MARKERS = frozenset((">", ">-", ">+", "|", "|-", "|+"))


def skill_paths(name: str) -> tuple[Path, ...]:
    """The definition of `name` under each root the skill scanners read.

    The roots come from the discovery owner in its precedence order, so the
    `.agents` path comes first. The harness may load either one, so a trigger
    anchor has to hold on both.
    """
    return tuple(
        REPO_ROOT / root / name / discovery._SKILL_FILE
        for root in discovery._SKILL_ROOTS
    )


def _is_indented_or_blank(line: str) -> bool:
    return not line or line[0].isspace()


def _field_line(lines: list[str], key: str) -> tuple[int, str] | None:
    prefix = f"{key}:"
    return next(
        (
            (index, line.removeprefix(prefix).strip())
            for index, line in enumerate(lines[1:], 1)
            if line.startswith(prefix)
        ),
        None,
    )


def frontmatter_field(text: str, key: str) -> str:
    """Fold one top-level field out of a SKILL.md frontmatter.

    Reads an inline value as written, and the `description: >-` folded form
    the skill files use as the indented block below the key, rejoined on
    single spaces and stopped at the next top-level key or the closing `---`.
    A key the frontmatter does not carry reads empty.
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == _FRONTMATTER_FENCE, "missing frontmatter open"
    frontmatter = [
        lines[0],
        *takewhile(lambda line: line.strip() != _FRONTMATTER_FENCE, lines[1:]),
    ]
    field = _field_line(frontmatter, key)
    if field is None:
        return ""
    index, inline = field
    if inline and inline not in _YAML_BLOCK_MARKERS:
        return inline
    return " ".join(
        line.strip()
        for line in takewhile(_is_indented_or_blank, frontmatter[index + 1:])
        if line.strip()
    )
