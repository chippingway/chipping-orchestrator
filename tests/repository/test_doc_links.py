# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every documentation link resolves, and the index and nav group every page the same way.

A cross-document link is the one reference nothing else checks: moving a page
or renaming a heading leaves the link syntactically valid and silently pointing
nowhere, and the reader who follows it gets a 404 or the top of the wrong page.
The headings here embed values that do change -- a handler's label is in its
heading -- and the hierarchy the index maps is split further as an area grows,
so these checks are what turn the next such move into a test failure rather
than a dead link somebody has to notice by hand.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository import (
    doc_link_target_support as _target_support,
    doc_link_test_support as _link_support,
    docs_nav_test_support as _nav_support,
)

_ENCODING = "utf-8"
_CONFIG_NAME = "mkdocs.yml"
# One written link per case, with the paths the check is expected to report.
_PATH_CASES = (
    ("moved page", "[gone](docs/nowhere.md)", ("docs/nowhere.md",)),
    ("anchor on a moved page", "[x](docs/nowhere.md#top)", ("docs/nowhere.md",)),
    ("external link", "[ci](https://example.com/nowhere.md)", ()),
    ("same-page anchor", "[here](#top)", ()),
    ("page that exists", "[docs](docs/README.md)", ()),
    ("absolute repository page", "[docs](https://github.com/chippingway/chipping-orchestrator/blob/main/docs/README.md)",
     ()),
    ("missing absolute page", "[x](https://github.com/chippingway/chipping-orchestrator/blob/main/docs/gone.md)",
     ("docs/gone.md",)),
    ("absolute image", "![x](https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/pics/analytics_page.png)",
     ()),
    ("missing absolute image", "![x](https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/pics/gone.png)",
     ("pics/gone.png",)),
)
_NAV_SAMPLE = """site_name: Sample
validation:
  nav:
    omitted_files: warn
nav: # Site navigation
  - "README.md"
  - Configuration:
      - 'Landing page': 'configuration/README.md' # Area overview
  - Upstream: https://example.com/configuration/new-page.md
extra:
  links:
    - Example: configuration/new-page.md
"""
_INDEX_SAMPLE = """# Documentation
## Where to start
[details](configuration/new-page.md)
## Every page
- **Configuration** — [overview](configuration/README.md),
  [details](configuration/new-page.md), [upstream](https://example.com/upstream.md)
- **How it works**
    - Agents — [overview](workflow.md), [roles](workflow/roles.md)
- **Releases** — [timeline](release-timeline.md)
## Help
[other](elsewhere.md)
"""
_GROUPED_NAV_SAMPLE = """site_name: Sample
nav: # Site navigation
  - 'README.md'
  - Configuration:
      - Upstream: https://example.com/upstream.md
      - 'Landing page': 'configuration/README.md' # Area overview
      - Details: configuration/new-page.md
  - How it works:
      - Agents:
          - Overview: workflow.md
          - Roles: workflow/roles.md
  - Releases: release-timeline.md
extra:
  links:
    - Example: elsewhere.md
"""
_GROUPING_CASES = (
    ("matching groups", _GROUPED_NAV_SAMPLE, True),
    ("different section", _GROUPED_NAV_SAMPLE.replace("  - Configuration:", "  - Operate:"), False),
    ("different subsection", _GROUPED_NAV_SAMPLE.replace("      - Agents:", "      - Workflow:"), False),
    ("page outside its subsection", _GROUPED_NAV_SAMPLE.replace("          - Roles:", "      - Roles:"), False),
    ("different page order", _GROUPED_NAV_SAMPLE.replace(
        "          - Overview: workflow.md\n          - Roles: workflow/roles.md",
        "          - Roles: workflow/roles.md\n          - Overview: workflow.md",
    ), False),
)


class DocumentAnchorTest(unittest.TestCase):
    """The scan reaches every routed page, and no anchor in one dangles."""

    def test_every_anchor_link_resolves(self) -> None:
        self.assertEqual(_link_support.dangling_anchors(_link_support.tracked_markdown()), [])

    def test_discovery_reaches_documents_below_docs(self) -> None:
        """A guide split into a subdirectory is scanned, not skipped.

        A top-level-only scan leaves the nested pages passing by absence,
        which reads exactly like coverage until a link there rots.
        """
        nested = [name for name in _link_support.tracked_markdown() if name.count("/") > 1]
        self.assertTrue(nested, "no document below docs/ was discovered")

    def test_discovery_reaches_the_routing_pages(self) -> None:
        """The agent entry point and the skills route, so they are scanned."""
        pages = _link_support.tracked_markdown()
        for name in (*_link_support.ENTRY_POINTS, ".agents/skills/develop/SKILL.md"):
            with self.subTest(page=name):
                self.assertIn(name, pages)

    def test_reference_definitions_are_scanned(self) -> None:
        """A foot-of-page definition is a link, and resolves like one."""
        with TemporaryDirectory() as directory:
            page = Path(directory) / "page.md"
            page.write_text(
                "[up](../landing.md#top)\n\n[ref]: ../landing.md#other\n",
                encoding=_ENCODING,
            )
            self.assertEqual(
                _link_support.document_links("docs/area/page.md", page),
                [("docs/landing.md", "top"), ("docs/landing.md", "other")],
            )


class DocumentPathTest(unittest.TestCase):
    """No link names a file or directory the repository does not have."""

    def test_every_relative_link_resolves(self) -> None:
        self.assertEqual(_link_support.unresolved_targets(_link_support.tracked_markdown()), [])

    def test_readme_links_are_absolute(self) -> None:
        targets = _target_support.document_targets(_link_support.REPO_ROOT / "README.md")
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue(target.startswith(("https://", "http://", "mailto:")))

    def test_only_a_missing_in_repo_path_is_reported(self) -> None:
        with TemporaryDirectory() as directory:
            page = Path(directory) / "page.md"
            for name, text, expected in _PATH_CASES:
                with self.subTest(case=name):
                    page.write_text(text, encoding=_ENCODING)
                    self.assertEqual(
                        _link_support.unresolved_targets({"page.md": page}),
                        [f"page.md -> {target}" for target in expected],
                    )


class DocumentationIndexTest(unittest.TestCase):
    """The landing page is a map of the whole set, and both roads lead to it."""

    def test_the_index_links_every_page_under_docs(self) -> None:
        self.assertEqual(_link_support.unindexed_pages(_link_support.tracked_markdown()), [])

    def test_nav_lists_every_docs_page(self) -> None:
        self.assertEqual(
            _nav_support.unnavigated_pages(_link_support.tracked_markdown(), _link_support.REPO_ROOT / _CONFIG_NAME),
            [],
            "Add omitted docs pages to nav in mkdocs.yml",
        )

    def test_index_and_nav_share_groups_and_order(self) -> None:
        self.assertEqual(
            _nav_support.index_grouped_pages(_link_support.REPO_ROOT / _link_support.INDEX_PAGE),
            _nav_support.nav_grouped_pages(_link_support.REPO_ROOT / _CONFIG_NAME),
            "Keep Every page in docs/README.md and nav in mkdocs.yml grouped and ordered the same way",
        )

    def test_grouping_sees_section_and_order_drift(self) -> None:
        with TemporaryDirectory() as directory:
            index = Path(directory) / "README.md"
            index.write_text(_INDEX_SAMPLE, encoding=_ENCODING)
            expected = _nav_support.index_grouped_pages(index)
            self.assertEqual(expected, [
                (("Configuration",), "docs/configuration/README.md"),
                (("Configuration",), "docs/configuration/new-page.md"),
                (("How it works", "Agents"), "docs/workflow.md"),
                (("How it works", "Agents"), "docs/workflow/roles.md"),
                (("Releases",), "docs/release-timeline.md"),
            ])
            config = Path(directory) / _CONFIG_NAME
            for case in _GROUPING_CASES:
                with self.subTest(case=case[0]):
                    config.write_text(case[1], encoding=_ENCODING)
                    self.assertEqual(_nav_support.nav_grouped_pages(config) == expected, case[2])

    def test_index_links_do_not_replace_nav(self) -> None:
        with TemporaryDirectory() as directory:
            pages = {
                name: Path(directory) / name
                for name in ("docs/README.md", "docs/configuration/README.md", "docs/configuration/new-page.md")
            }
            for page in pages.values():
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text("# Page\n", encoding=_ENCODING)
            pages[_link_support.INDEX_PAGE].write_text(
                "[area](configuration/README.md)\n[new](configuration/new-page.md)\n",
                encoding=_ENCODING,
            )
            self.assertEqual(_link_support.unindexed_pages(pages), [])
            config = Path(directory) / _CONFIG_NAME
            config.write_text(_NAV_SAMPLE, encoding=_ENCODING)
            self.assertEqual(_nav_support.unnavigated_pages(pages, config), ["docs/configuration/new-page.md"])
            config.write_text(
                _NAV_SAMPLE.replace("  - Configuration:", "  - configuration/new-page.md\n  - Configuration:"),
                encoding=_ENCODING,
            )
            self.assertEqual(_nav_support.unnavigated_pages(pages, config), [])

    def test_the_entry_points_route_to_the_index(self) -> None:
        pages = _link_support.tracked_markdown()
        for name in _link_support.ENTRY_POINTS:
            with self.subTest(page=name):
                linked = {
                    document
                    for document, _ in _link_support.document_links(name, pages[name])
                }
                self.assertIn(_link_support.INDEX_PAGE, linked)


class HeadingAnchorSlugTest(unittest.TestCase):
    """The slug matches GitHub's, including the two cases that bite here."""

    def test_slug_matches_github(self) -> None:
        for heading, expected in _link_support.HEADING_ANCHOR_CASES:
            with self.subTest(heading=heading):
                self.assertEqual(_link_support.heading_anchor(heading), expected)


if __name__ == "__main__":
    unittest.main()
