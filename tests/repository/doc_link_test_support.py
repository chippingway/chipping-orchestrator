# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The scan behind the documentation link checks.

Three questions are asked of one set of pages -- every relative path names
something the repository has, every `#anchor` names a heading that exists, and
every page under `docs/` is reachable from the index -- so the walk answering
them sits beside the checks rather than inside one of them.

Notes under `plans/` are deliberately outside the set. They are human working
material, not part of the reference hierarchy, and they name paths the code has
since moved away from; scanning them would fail the suite over a file nobody is
asked to keep current.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.repository import doc_link_target_support as _targets

REPO_ROOT = Path(__file__).resolve().parents[2]
# The documentation landing page, and the two pages that route readers into it.
INDEX_PAGE = "docs/README.md"
ENTRY_POINTS = ("README.md", "AGENTS.md")

# Shared cases keep the link checker and site hook aligned on GitHub's punctuation rules.
HEADING_ANCHOR_CASES = (
    ("`_handle_validating` (label `workflow:validating`)",
     "_handle_validating-label-workflowvalidating"),
    ("In-flight session lock — pinned spec",
     "in-flight-session-lock--pinned-spec"),
)

# `.claude/` and `CLAUDE.md` are symlinks onto `.agents/` and `AGENTS.md`, so
# the scan reads one side of each pair and covers both.
_PAGE_ROOTS = ("docs", ".agents/skills")
_DOCS_PREFIX = "docs/"
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_PUNCTUATION = re.compile(r"[^\w\s-]")
_ENCODING = "utf-8"


def heading_anchor(heading: str) -> str:
    """Slug a heading the way GitHub does: drop punctuation, space -> hyphen.

    Punctuation is removed in place rather than replaced, so the `:` in a
    namespaced label closes up while the spaces around an em dash each still
    become their own hyphen.
    """
    return _PUNCTUATION.sub("", heading.strip().lower()).replace(" ", "-")


def tracked_markdown() -> dict[str, Path]:
    """Every scanned page, keyed by the repo-relative path a link names it by.

    `docs/` nests, so the key has to carry the directory: two pages named
    `observability.md` sit one level apart, and a bare filename would resolve
    a link into whichever of them the dictionary happened to keep. The skill
    files join the docs because they route the same way, and the two entry
    points because they are where a reader picks an area to begin with.
    """
    pages = {
        path.relative_to(REPO_ROOT).as_posix(): path
        for root in _PAGE_ROOTS
        for path in (REPO_ROOT / root).rglob("*.md")
    }
    pages.update({name: REPO_ROOT / name for name in ENTRY_POINTS})
    return pages


def document_links(name: str, path: Path) -> list[tuple[str, str]]:
    """Every `(document, anchor)` one page links to, anchor `''` when absent.

    A relative target is resolved against the directory of the page that wrote
    it, so the `../` a nested page reaches a sibling directory with names the
    same key the flat page beside it writes directly. A same-page `#anchor`
    link carries no target at all and stays on its own page. Both link forms
    count, since a reference definition at the foot of a page is how the
    longest anchors here are written.
    """
    resolved = (_targets.resolved_target(name, target) for target in _targets.document_targets(path))
    return [link for link in resolved if link is not None]


def dangling_anchors(pages: dict[str, Path]) -> list[str]:
    """Report every `...#anchor` link whose target heading is missing.

    Links out to another repository are skipped: only a document this repo
    tracks has headings this check can resolve the anchor against.
    """
    anchors = {
        name: {
            heading_anchor(heading)
            for heading in _MARKDOWN_HEADING.findall(
                path.read_text(encoding=_ENCODING),
            )
        }
        for name, path in pages.items()
    }
    return [
        f"{name} -> {document}#{anchor}"
        for name, path in pages.items()
        for document, anchor in document_links(name, path)
        if anchor and document in anchors and anchor not in anchors[document]
    ]


def unresolved_targets(pages: dict[str, Path]) -> list[str]:
    """Report every link whose path names something the repo does not have.

    This is the half an anchor check cannot see: a moved or renamed page
    leaves the link syntactically valid, and the anchor behind it resolves
    against nothing, so the reader gets a 404 rather than a wrong heading. A
    directory target counts as resolved -- GitHub renders one -- and a link
    back to the page it was written on is skipped as vacuous.
    """
    return [
        f"{name} -> {document}"
        for name, path in pages.items()
        for document, _ in document_links(name, path)
        if document != name and not (REPO_ROOT / document).exists()
    ]


def unindexed_pages(pages: dict[str, Path]) -> list[str]:
    """Report every page under `docs/` the landing page does not link to.

    The index is what makes the hierarchy navigable, so a page it never names
    is one a reader only reaches by knowing the filename already.
    """
    linked = {
        document
        for document, _ in document_links(INDEX_PAGE, pages[INDEX_PAGE])
    }
    return sorted(
        name
        for name in pages
        if name.startswith(_DOCS_PREFIX)
        and name != INDEX_PAGE
        and name not in linked
    )
