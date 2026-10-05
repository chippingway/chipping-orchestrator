# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Markdown targets mapped back to the repository paths they name."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

_MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
_MARKDOWN_REFERENCE = re.compile(r"^\[[^\]]+\]:\s*(\S+)\s*$", re.MULTILINE)
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:")
_REPOSITORY_URLS = (
    "https://github.com/chippingway/chipping-orchestrator/blob/main/",
    "https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/",
)


def document_targets(path: Path) -> tuple[str, ...]:
    """Every written target, including external URLs and reference definitions."""
    text = path.read_text(encoding="utf-8")
    return (*_MARKDOWN_LINK.findall(text), *_MARKDOWN_REFERENCE.findall(text))


def resolved_target(name: str, target: str) -> tuple[str, str] | None:
    """Split a link, mapping hosted repository files to checkout paths."""
    location, _, anchor = target.partition("#")
    for prefix in _REPOSITORY_URLS:
        if location.startswith(prefix):
            return posixpath.normpath(location.removeprefix(prefix)), anchor
    if location.startswith(_EXTERNAL_SCHEMES):
        return None
    if not location:
        return name, anchor
    directory = posixpath.dirname(name)
    return posixpath.normpath(posixpath.join(directory, location)), anchor
