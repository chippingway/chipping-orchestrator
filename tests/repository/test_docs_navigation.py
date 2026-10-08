# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The site's navigation: sections in the top bar, the current section in the sidebar, and a pager under the page.

The top bar names each top-level nav entry once on content pages and the 404
page, as a plain link: a section links to its first page, past an external link
listed ahead of it, and the homepage is left to the site name. No dropdown stands
in for a section. The bar carries the repository link and ChatGPT and Claude
buttons whose documentation prompts open a new tab with `noopener`, but no
previous, next, or per-page edit link.
Both README pages carry the same prompts, and the template follows `site_url`
when the documentation is hosted elsewhere.
The sidebar lists the current page's top-level section, opens only the
subsection holding the page, and marks the page with `aria-current`, which the
theme's scrollspy leaves alone. Its card scrolls on its own, no taller than the
window under the top bar, so a long contents list keeps its end in reach, and
breaks a long heading rather than scrolling sideways to it.
Its heading links follow the page's headings in order, through the configured
navigation depth, outside the section's navigation landmark.
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
from urllib.parse import parse_qs, urlsplit

from tests.repository import doc_link_target_support as _target_support, docs_site_test_support as _site_support

_ENCODING = "utf-8"
_HREF = "href"
_Attributes = dict[str, str | None]
# Two attributes of one link, such as its target and its `aria-current`.
_Pair = tuple[str | None, str | None]
_REPOSITORY = "https://github.com/chippingway/chipping-orchestrator"
_AI_PROMPT_URLS = (
    (
        "https://chatgpt.com/?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C"
        "+I+want+to+ask+questions+about+it.&hints=search"
    ),
    (
        "https://claude.ai/new?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C"
        "+I+want+to+ask+questions+about+it."
    ),
)
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
_REL_PREVIOUS = "prev"
_REL_NEXT = "next"
_TO_NESTED = "../nested/page/"
_SIDEBAR_CARD = "toc-collapse"
_SIDEBAR_HEADING_TAGS = frozenset(("h1", "h2", "h3"))
_HEADING_SAMPLE = """# Local page

## Details

### Example

#### Deeper heading

## Summary
"""
_SIDEBAR_CARD_STYLE = frozenset((
    "max-height: calc(100vh - 3.5rem - 40px)",
    "overflow-y: auto",
    "overflow-wrap: anywhere",
))


def _links(page: _site_support.SitePage, label: str) -> list[_Pair]:
    """Each link inside the `<nav>` labelled `label`, as its target and its `aria-current`."""
    landmark = page.landmarks.get(label, [])
    return [(link.get(_HREF), link.get("aria-current")) for link in landmark]


def _related(links: list[_Attributes]) -> list[_Pair]:
    """Each of `links` that names a pager relation, as that relation and its target."""
    related = [link for link in links if link.get("rel") in {_REL_PREVIOUS, _REL_NEXT}]
    return [(link.get("rel"), link.get(_HREF)) for link in related]


def _style(page: _site_support.SitePage, element_id: str) -> set[str]:
    """The declarations in the `style` attribute of the element whose id is `element_id`."""
    by_id = {attributes.get("id"): attributes for _, attributes in page.tags}
    style = by_id[element_id].get("style") or ""
    declarations = (declaration.strip() for declaration in style.split(";"))
    return set(filter(None, declarations))


def _anchors(page: _site_support.SitePage) -> list[_Attributes]:
    """Each anchor on the page, with its link attributes."""
    return [attributes for tag, attributes in page.tags if tag == "a"]


def _ai_prompt_links(page: _site_support.SitePage) -> list[_Attributes]:
    """Each AI prompt button, with its link attributes."""
    return [
        link for link in _anchors(page)
        if "ai-chat-button" in (link.get("class") or "").split()
    ]


class DocumentationPromptTest(unittest.TestCase):
    def test_readmes_share_the_documentation_prompts(self) -> None:
        """Both README pages offer the same ChatGPT and Claude prompts as the top bar."""
        for name in ("README.md", "docs/README.md"):
            with self.subTest(page=name):
                targets = _target_support.document_targets(_site_support.REPO_ROOT / name)
                self.assertLessEqual(set(_AI_PROMPT_URLS), set(targets))

    @unittest.skipUnless(find_spec("mkdocs"), _site_support.INSTALL_HINT)
    def test_buttons_use_the_configured_site_url(self) -> None:
        """Both buttons point to the configured documentation homepage without a trailing slash."""
        root = Path(self.enterContext(TemporaryDirectory())).resolve()
        config = _site_support.write_sample_repository(root, "# Sample\n")
        config.write_text(
            config.read_text(encoding=_ENCODING).replace(
                f"site_url: {_site_support.SITE_URL}", "site_url: https://example.com/manual/",
            ),
            encoding=_ENCODING,
        )
        site = root / _site_support.SITE_DIRECTORY
        built = _site_support.build_site(config, site)
        self.assertEqual(built.returncode, 0, built.stderr)
        prompt = "Read https://example.com/manual, I want to ask questions about it."
        self.assertEqual(
            [
                parse_qs(urlsplit(link.get(_HREF) or "").query)
                for link in _ai_prompt_links(_site_support.SitePage(site / _HOMEPAGE))
            ],
            [{"q": [prompt], "hints": ["search"]}, {"q": [prompt]}],
        )


@unittest.skipUnless(find_spec("mkdocs"), _site_support.INSTALL_HINT)
class SiteNavigationTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(TemporaryDirectory())).resolve()
        config = _site_support.write_sample_repository(root, "# Sample\n")
        configured = config.read_text(encoding=_ENCODING).replace(
            "  name: mkdocs\n", "  name: mkdocs\n  navigation_depth: 3\n",
        )
        config.write_text(configured + _NAV, encoding=_ENCODING)
        (root / "docs" / "next.md").write_text(_HEADING_SAMPLE, encoding=_ENCODING)
        (root / "docs" / "last.md").write_text("# Last page\n", encoding=_ENCODING)
        self.site = root / _site_support.SITE_DIRECTORY
        built = _site_support.build_site(config, self.site)
        self.assertEqual(built.returncode, 0, built.stderr)

    def test_navigation_follows_the_nav(self) -> None:
        """The top bar, the sidebar, and the pager of one build, each checked under its own subtest."""
        checks = (
            self._top_bar_links_each_section_once,
            self._sidebar_opens_the_current_subsection,
            self._sidebar_lists_headings_within_the_window,
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
                self.assertLessEqual(set(_AI_PROMPT_URLS), set(page.links))
                for prompt in _ai_prompt_links(page):
                    self.assertEqual(prompt.get("target"), "_blank")
                    self.assertIn("noopener", (prompt.get("rel") or "").split())
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

    def _sidebar_lists_headings_within_the_window(self) -> None:
        """The card lists headings in page order through level three, scrolls within the window, and wraps text."""
        for name in (_HOMEPAGE, _NEXT, _NESTED, _LAST):
            page = self._page(name)
            expected = [
                f"#{attributes['id']}"
                for tag, attributes in page.tags
                if tag in _SIDEBAR_HEADING_TAGS
            ]
            with self.subTest(page=name):
                self.assertTrue(expected, "sample pages exercise heading navigation")
                self.assertEqual([link.get(_HREF) for link in page.sidebar_headings], expected)
        self.assertEqual(_style(self._page(_NESTED), _SIDEBAR_CARD), _SIDEBAR_CARD_STYLE)

    def _previous_and_next_sit_under_the_page(self) -> None:
        """The only previous and next links are the pager's, in nav order, past the external link."""
        expected = {
            _HOMEPAGE: [(_REL_NEXT, "next/")],
            _NEXT: [(_REL_PREVIOUS, ".."), (_REL_NEXT, _TO_NESTED)],
            _NESTED: [(_REL_PREVIOUS, "../../next/"), (_REL_NEXT, "../../last/")],
            _LAST: [(_REL_PREVIOUS, _TO_NESTED)],
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
