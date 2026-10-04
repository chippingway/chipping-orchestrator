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
_INDEX_SECTION = re.compile(r"^## Every page[ \t]*\n(.*?)(?=^#{1,2}[ \t]|\Z)", re.MULTILINE | re.DOTALL)
_INDEX_ITEM = re.compile(r"^(?P<indent>[ \t]*)-[ \t]+(?P<title>.*?)(?:[ \t]+—[ \t]+|$)")
_INDEX_LINK = re.compile(r"\]\(([^)\s]+\.md)(?:#[^)\s]*)?\)")
_NAV_ITEM = re.compile(r"^(?P<indent>[ \t]+)-[ \t]+(?P<entry>.+)$", re.MULTILINE)
_ENCODING = "utf-8"
_INDENT = "indent"
_Group = tuple[int, str]
_GroupedPage = tuple[tuple[str, ...], str]


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


def index_grouped_pages(index: Path) -> list[_GroupedPage]:
    """Every local page in `Every page`, against its group ancestry, in list order."""
    section = _INDEX_SECTION.search(index.read_text(encoding=_ENCODING))
    groups: list[_Group] = []
    pages: list[_GroupedPage] = []
    for line in (section.group(1) if section else "").splitlines():
        group = _INDEX_ITEM.match(line)
        if group:
            groups = _parent_groups(groups, group[_INDENT])
            groups.append((
                len(group[_INDENT]),
                group["title"].strip("* "),
            ))
        pages.extend(_index_targets(line, groups))
    return pages


def nav_grouped_pages(config: Path) -> list[_GroupedPage]:
    """Every local nav page except Home, against its section ancestry, in nav order.

    A top-level page is its own section, such as Releases. Leaf titles inside
    a section may differ from the index's link text, so only the ancestry and
    target participate in the comparison.
    """
    groups: list[_Group] = []
    pages: list[_GroupedPage] = []
    for entry in _NAV_ITEM.finditer(
        "".join(_NAV_SECTION.findall(config.read_text(encoding=_ENCODING))),
    ):
        groups = _parent_groups(groups, entry[_INDENT])
        title, target = _nav_parts(entry["entry"])
        if not target or not groups:
            groups.append((len(entry[_INDENT]), title))
        if target.endswith(".md") and target != "README.md" and not target.startswith(_EXTERNAL_SCHEMES):
            pages.append(_grouped_target(groups, target))
    return pages


def _parent_groups(groups: list[_Group], indentation: str) -> list[_Group]:
    return [group for group in groups if group[0] < len(indentation)]


def _grouped_target(groups: list[_Group], target: str) -> _GroupedPage:
    ancestry = tuple(title for _, title in groups)
    return ancestry, posixpath.normpath(posixpath.join(_DOCS_PREFIX, target))


def _index_targets(line: str, groups: list[_Group]) -> list[_GroupedPage]:
    return [
        _grouped_target(groups, target)
        for target in _INDEX_LINK.findall(line)
        if not target.startswith(_EXTERNAL_SCHEMES)
    ]


def _nav_parts(entry: str) -> tuple[str, str]:
    plain = entry.split(" #", 1)[0].strip()
    if plain.startswith(_EXTERNAL_SCHEMES):
        return "", plain
    title, separator, target = plain.partition(":")
    return (
        title.strip().strip("'\""),
        (target if separator else title).strip().strip("'\""),
    )
