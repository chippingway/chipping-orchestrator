# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every documentation link resolves, the index and nav group every page the same way,
the contract register keeps the anchors and shape its readers rely on, and the
deployment procedure stays routed from where operators start an upgrade.

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
    contract_register_test_support as _register_support,
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
# The anchors every link into the register is written against. A title is part
# of its anchor, so renaming one breaks those links even though the ID stays; a
# new contract appends its anchor here, and a retired ID is never reused.
_FORMATS_CONTRACT = "c-03-persisted-and-externally-consumed-formats"
_CONTRACT_ANCHORS = (
    "c-01-durable-workflow-state-and-recovery",
    "c-02-workflow-labels-and-transitions",
    _FORMATS_CONTRACT,
    "c-04-authentic-state-and-trusted-input",
    "c-05-writer-claims-and-artifact-maintenance",
    "c-06-guarded-writes-and-recoverable-effects",
    "c-07-publication-authority-and-exact-revisions",
    "c-08-agent-reply-protocols",
    "c-09-reports-review-subjects-and-verification",
    "c-10-pauses-and-parks",
    "c-11-credentials-and-execution-boundaries",
    "c-12-observation-and-the-audit-recovery-exception",
    "c-13-module-ownership-and-public-surfaces",
    "c-14-pinned-session-commands",
    "c-15-lifetime-agent-run-budget",
)
# The pages that tell an agent or contributor how to change the code, each of
# which defers to the register on persisted and external formats.
_INSTRUCTION_PAGES = (
    "AGENTS.md",
    _link_support.CONTRIBUTING_PAGE,
    ".agents/skills/develop/SKILL.md",
    ".agents/skills/decompose/SKILL.md",
)
# The no-migration deployment procedure, one link per hop an operator follows to
# it: the README and the index reach the configuration landing page, which with
# the developer guide reaches the operations page, which defers to C-03 for the
# policy rather than restating it. The README's link is the absolute one.
_DEPLOYMENT_ANCHOR = "deploying-without-migration"
_CONFIGURATION_PAGE = "docs/configuration.md"
_OPERATIONS_PAGE = "docs/configuration/operations.md"
_DEPLOYMENT_LINKS = (
    ("README.md", _CONFIGURATION_PAGE, _DEPLOYMENT_ANCHOR),
    (_link_support.INDEX_PAGE, _CONFIGURATION_PAGE, _DEPLOYMENT_ANCHOR),
    (_CONFIGURATION_PAGE, _OPERATIONS_PAGE, _DEPLOYMENT_ANCHOR),
    ("docs/development.md", _OPERATIONS_PAGE, _DEPLOYMENT_ANCHOR),
    (_OPERATIONS_PAGE, _register_support.CONTRACTS_PAGE, _FORMATS_CONTRACT),
)
# The procedure and the upgrade, rollback, and restart sections it bounds. Links
# written against them from outside this repository have nothing else to keep
# them true.
_RESTART_ANCHOR = "what-survives-a-restart"
_BOUNDED_ANCHORS = (
    (_OPERATIONS_PAGE, _DEPLOYMENT_ANCHOR),
    (_OPERATIONS_PAGE, "upgrade-a-package"),
    (_OPERATIONS_PAGE, "return-to-the-previous-package-version"),
    (_OPERATIONS_PAGE, "rolling-back-to-an-older-orchestrator"),
    (_OPERATIONS_PAGE, _RESTART_ANCHOR),
    (_CONFIGURATION_PAGE, _DEPLOYMENT_ANCHOR),
    (_CONFIGURATION_PAGE, _RESTART_ANCHOR),
)
_REGISTER_SAMPLE = """| ID | Rule |
| --- | --- |
| [C-01] | Keep one rule. |
| [C-02] | Keep another. |

## C-01: First contract

**Rule: Keep one rule.**

**Why:** One reason.

**Limits:** None.

**Specs:** [spec](spec.md).

**Checks:** [test](test.py).

## C-02: Second contract

**Rule: Keep another.**

**Why:** Another reason.

**Limits:** Some.

A second paragraph of limits.

**Specs:** [other spec](other.md).

**Checks:** [other test](other.py).

## Maintaining the contracts

[C-01]: #c-01-first-contract
[C-02]: #c-02-second-contract
"""
_SECOND_ROW = "| [C-02] | Keep another. |\n"
_LISTING_DRIFT = "checklist and sections list different IDs"
_FIRST_PARTS_DRIFT = "C-01: parts are missing or out of order"
# One edit to the sample per case, with the problems the check must report.
_REGISTER_CASES = (
    ("agreeing register", ("", ""), ()),
    ("reworded row", ("| [C-02] | Keep another.", "| [C-02] | Keep more."), (
        "C-02: checklist row differs from its Rule",
    )),
    ("reworded rule", ("**Rule: Keep one", "**Rule: Keep the"), ("C-01: checklist row differs from its Rule",)),
    ("missing row", (_SECOND_ROW, ""), (_LISTING_DRIFT, "C-02: checklist row differs from its Rule")),
    ("repeated row", (_SECOND_ROW, _SECOND_ROW * 2), (_LISTING_DRIFT,)),
    ("missing part", ("**Why:** One reason.\n\n", ""), (_FIRST_PARTS_DRIFT,)),
    ("swapped parts", (
        "**Specs:** [spec](spec.md).\n\n**Checks:** [test](test.py).",
        "**Checks:** [test](test.py).\n\n**Specs:** [spec](spec.md).",
    ), (_FIRST_PARTS_DRIFT,)),
    ("extra part", ("A second paragraph", "**Note:** A second paragraph"), (
        "C-02: parts are missing or out of order",
    )),
    ("renamed title", ("## C-01: First contract", "## C-01: First rule"), (
        "C-01: reference link misses #c-01-first-rule",
    )),
)
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
        """The entry points, the contribution guide, and the skills route, so they are scanned."""
        pages = _link_support.tracked_markdown()
        for name in (*_link_support.ENTRY_POINTS, *_INSTRUCTION_PAGES):
            with self.subTest(page=name):
                self.assertIn(name, pages)

    def test_agents_required_reading_links_contracts(self) -> None:
        """The required-reading section links the contract register."""
        guide = (_link_support.REPO_ROOT / "AGENTS.md").read_text(encoding=_ENCODING)
        required = guide.partition("## Required reading for every task\n")[2].split("\n## ", 1)[0]
        self.assertRegex(required, r"\[[^\]]+\]\(docs/contracts\.md\)")

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


class ContractRegisterTest(unittest.TestCase):
    """The register keeps its anchors, its checklist, and its section shape."""

    def test_contract_anchors_stay_stable(self) -> None:
        sections = _register_support.contract_sections(_register_text())
        self.assertEqual(tuple(anchor for _, anchor, _ in sections), _CONTRACT_ANCHORS)

    def test_checklist_references_and_sections_agree(self) -> None:
        self.assertEqual(_register_support.register_problems(_register_text()), [])

    def test_register_drift_is_reported(self) -> None:
        for name, (old, new), expected in _REGISTER_CASES:
            with self.subTest(case=name):
                self.assertIn(old, _REGISTER_SAMPLE)
                self.assertEqual(
                    _register_support.register_problems(_REGISTER_SAMPLE.replace(old, new, 1)),
                    list(expected),
                )

    def test_instruction_pages_link_formats_contract(self) -> None:
        """Each instruction page links C-03, the one place the format policy is stated."""
        for name in _INSTRUCTION_PAGES:
            with self.subTest(page=name):
                self.assertIn(
                    (_register_support.CONTRACTS_PAGE, _FORMATS_CONTRACT),
                    _link_support.document_links(name, _link_support.REPO_ROOT / name),
                )


def _register_text() -> str:
    return (_link_support.REPO_ROOT / _register_support.CONTRACTS_PAGE).read_text(encoding=_ENCODING)


class DeploymentRouteTest(unittest.TestCase):
    """The no-migration deployment procedure is routed to, and the sections it bounds keep their anchors."""

    def test_each_hop_links_the_next(self) -> None:
        for name, document, anchor in _DEPLOYMENT_LINKS:
            with self.subTest(page=name, target=document):
                self.assertIn(
                    (document, anchor),
                    _link_support.document_links(name, _link_support.REPO_ROOT / name),
                )

    def test_bounded_sections_keep_their_anchors(self) -> None:
        for page, anchor in _BOUNDED_ANCHORS:
            with self.subTest(page=page, anchor=anchor):
                self.assertIn(anchor, _link_support.page_anchors(_link_support.REPO_ROOT / page))


class HeadingAnchorSlugTest(unittest.TestCase):
    """The slug matches GitHub's, including the two cases that bite here."""

    def test_slug_matches_github(self) -> None:
        for heading, expected in _link_support.HEADING_ANCHOR_CASES:
            with self.subTest(heading=heading):
                self.assertEqual(_link_support.heading_anchor(heading), expected)


if __name__ == "__main__":
    unittest.main()
