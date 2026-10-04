# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The site's navigation: sections in the top bar, the current section in the sidebar, and a pager under the page.

The top bar names each top-level nav entry once on content pages and the 404
page, as a plain link: a section links to its first page, past an external link
listed ahead of it, and the homepage is left to the site name. No dropdown stands
in for a section, and the bar carries the repository link but no previous, next,
or per-page edit link.
The sidebar lists the current page's top-level section, opens only the
subsection holding the page, and marks the page with `aria-current`, which the
theme's scrollspy leaves alone. Its card scrolls on its own, no taller than the
window under the top bar, so a long contents list keeps its end in reach, and
breaks a long heading rather than scrolling sideways to it.
Previous and next sit under the page, inside a `.navbar`, where the theme's
keyboard shortcuts look for them.

A sample site is built once through the repository's templates with a nav
shaped like the real one, so the check needs the `docs` group but no built
site, and each part of the navigation is read from that one build.
"""
from __future__ import annotations

import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository import docs_site_test_support as _site_support

_ENCODING = "utf-8"
_Attributes = dict[str, str | None]
# Two attributes of one link, such as its target and its `aria-current`.
_Pair = tuple[str | None, str | None]
_REPOSITORY = "https://github.com/chippingway/chipping-orchestrator"
_UPSTREAM = "https://example.com/upstream"
_NAV = f"""nav:
  - Home: README.md
  - Area:
      - Upstream: {_UPSTREAM}
      - First group:
          - Next: next.md
      - Second group:
          - Nested: nested/page.md
  - Last: last.md
"""
_SITE = "Site"
_AREA = "Area"
_PAGES = "Pages"
_HOMEPAGE = "index.html"
_NOT_FOUND = "404.html"
_NEXT = "next/index.html"
_NESTED = "nested/page/index.html"
_LAST = "last/index.html"
_HERE = "./"
_CURRENT_PAGE = "page"
_TO_NESTED = "../nested/page/"
_SIDEBAR_CARD = "toc-collapse"
_SIDEBAR_CARD_STYLE = frozenset((
    "max-height: calc(100vh - 3.5rem - 40px)",
    "overflow-y: auto",
    "overflow-wrap: anywhere",
))


def _links(page: _site_support.SitePage, label: str) -> list[_Pair]:
    """Each link inside the `<nav>` labelled `label`, as its target and its `aria-current`."""
    landmark = page.landmarks.get(label, [])
    return [(link.get("href"), link.get("aria-current")) for link in landmark]


def _related(links: list[_Attributes]) -> list[_Pair]:
    """Each of `links` that names a `rel`, as that relation and its target."""
    related = [link for link in links if link.get("rel")]
    return [(link.get("rel"), link.get("href")) for link in related]


def _style(page: _site_support.SitePage, element_id: str) -> set[str]:
    """The declarations in the `style` attribute of the element whose id is `element_id`."""
    by_id = {attributes.get("id"): attributes for _, attributes in page.tags}
    style = by_id[element_id].get("style") or ""
    declarations = (declaration.strip() for declaration in style.split(";"))
    return set(filter(None, declarations))


def _anchors(page: _site_support.SitePage) -> list[_Attributes]:
    return [attributes for tag, attributes in page.tags if tag == "a"]


@unittest.skipUnless(find_spec("mkdocs"), _site_support.INSTALL_HINT)
class SiteNavigationTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(TemporaryDirectory())).resolve()
        config = _site_support.write_sample_repository(root, "# Sample\n")
        config.write_text(config.read_text(encoding=_ENCODING) + _NAV, encoding=_ENCODING)
        (root / "docs" / "last.md").write_text("# Last page\n", encoding=_ENCODING)
        self.site = root / _site_support.SITE_DIRECTORY
        built = _site_support.build_site(config, self.site)
        self.assertEqual(built.returncode, 0, built.stderr)

    def test_navigation_follows_the_nav(self) -> None:
        """The top bar, the sidebar, and the pager of one build, each checked under its own subtest."""
        checks = (
            self._top_bar_links_each_section_once,
            self._sidebar_opens_the_current_subsection,
            self._sidebar_scrolls_inside_the_window,
            self._previous_and_next_sit_under_the_page,
        )
        for check in checks:
            with self.subTest(check=check.__name__):
                check()

    def _top_bar_links_each_section_once(self) -> None:
        """A section link marks its landing page as current, and the section as current on its other pages."""
        expected = {
            _HOMEPAGE: [("next/", None), ("last/", None)],
            _NOT_FOUND: [("/chipping-orchestrator/next/", None), ("/chipping-orchestrator/last/", None)],
            _NEXT: [(_HERE, _CURRENT_PAGE), ("../last/", None)],
            _NESTED: [("../../next/", "true"), ("../../last/", None)],
            _LAST: [("../next/", None), (_HERE, _CURRENT_PAGE)],
        }
        for name, links in expected.items():
            page = self._page(name)
            with self.subTest(page=name):
                self.assertEqual(_links(page, _SITE), links)
                self.assertNotIn("dropdown", [link.get("data-bs-toggle") for link in _anchors(page)])
                self.assertIn(_REPOSITORY, page.links)
                self.assertFalse([link for link in page.links if link.startswith(f"{_REPOSITORY}/edit/")])

    def _sidebar_opens_the_current_subsection(self) -> None:
        """The current section is listed with only the subsection holding the page open, and the page marked."""
        expected = {
            _NEXT: [(_UPSTREAM, None), (_HERE, None), (_HERE, _CURRENT_PAGE), (_TO_NESTED, None)],
            _NESTED: [(_UPSTREAM, None), ("../../next/", None), (_HERE, None), (_HERE, _CURRENT_PAGE)],
        }
        for name, links in expected.items():
            with self.subTest(page=name):
                self.assertEqual(_links(self._page(name), _AREA), links)
        landmarks = set(self._page(_LAST).landmarks)
        self.assertEqual(landmarks, {_SITE, _PAGES}, "a top-level page belongs to no section")

    def _sidebar_scrolls_inside_the_window(self) -> None:
        """The sidebar card scrolls down inside the window under the top bar, and wraps rather than scrolls across."""
        self.assertEqual(_style(self._page(_NESTED), _SIDEBAR_CARD), _SIDEBAR_CARD_STYLE)

    def _previous_and_next_sit_under_the_page(self) -> None:
        """The only previous and next links are the pager's, in nav order, past the external link."""
        expected = {
            _HOMEPAGE: [("next", "next/")],
            _NEXT: [("prev", ".."), ("next", _TO_NESTED)],
            _NESTED: [("prev", "../../next/"), ("next", "../../last/")],
            _LAST: [("prev", _TO_NESTED)],
        }
        for name, related in expected.items():
            page = self._page(name)
            with self.subTest(page=name):
                self.assertEqual(_related(page.landmarks[_PAGES]), related)
                self.assertEqual(_related(_anchors(page)), related)

    def _page(self, name: str) -> _site_support.SitePage:
        return _site_support.SitePage(self.site / name)


if __name__ == "__main__":
    unittest.main()
