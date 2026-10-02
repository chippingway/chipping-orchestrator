# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Check site navigation without the optional documentation dependencies."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

_DOCS_PREFIX = "docs/"
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:")
_NAV_SECTION = re.compile(r"^nav:[ \t]*(?:#[^\r\n]*)?\n(.*?)(?=^[^\s#]|\Z)", re.MULTILINE | re.DOTALL)
_NAV_MARKDOWN = re.compile(
    r"^[ \t]+-[ \t]+(?:.+:[ \t]+)?['\"]?([^'\"\r\n]+\.md)['\"]?[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
_ENCODING = "utf-8"


def unnavigated_pages(pages: dict[str, Path], config: Path) -> list[str]:
    """Report docs pages omitted from the site's block-style `nav` list.

    Required CI runs without MkDocs or a YAML library, so it reads Markdown
    leaves from the top-level nav section of the repository's config.
    """
    section = _NAV_SECTION.search(config.read_text(encoding=_ENCODING))
    navigation = section.group(1) if section else ""
    linked = {
        posixpath.normpath(posixpath.join(_DOCS_PREFIX, target))
        for target in _NAV_MARKDOWN.findall(navigation)
        if not target.startswith(_EXTERNAL_SCHEMES)
    }
    return sorted(
        name for name in pages
        if name.startswith(_DOCS_PREFIX) and name not in linked
    )
