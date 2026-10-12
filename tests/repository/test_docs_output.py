# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The built site keeps its links, anchors, search index, and sitemap whole.

The homepage and every reference area's landing page each emit the one
description their front matter gives, and no two of those descriptions match,
so a search result or link preview tells the pages apart.
The documentation homepage offers each AI button once, only in the top bar.

The Documentation workflow builds the repository site once and uploads that
output, so the check has to read the same output rather than a copy of its own:
`DOCS_SITE_DIR` names the built directory, and the check reads it in place.
Without the variable the check builds a fresh strict copy into a temporary
directory, which is the local path and the one that needs the docs group.

A requested directory is never replaced. One that holds no built site fails
the check -- it does not build another, and it does not skip for want of the
builder -- so a workflow pointing at the wrong place cannot pass on pages it
never read, and an empty directory cannot pass by having no links to break.
"""
from __future__ import annotations

import os
import shutil
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from types import MappingProxyType
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from tests.repository import docs_site_test_support as _site_support
from tests.repository.skill_metadata_test_support import frontmatter_field

_ENCODING = "utf-8"
_DOCS = _site_support.REPO_ROOT / "docs"
_HOMEPAGE_PATH = "index.html"
_CHAT_BADGES = MappingProxyType({"chatgpt.com": "ask-chatgpt.svg", "claude.ai": "ask-claude.svg"})
_AI_PROMPT_HREFS = tuple(
    f'href="{url}"'.replace("&", "&amp;") for url in _site_support.AI_PROMPT_URLS
)
_HOMEPAGE = """# Sample

[local](next.md#local-page)
[ChatGPT](https://chatgpt.com/)
[Claude](https://claude.ai/)
[ChatGPT greeting](https://chatgpt.com/?q=Hello)
"""
# Each fault edits one file of a clean sample build -- the page and its text
# replacements -- against the problem the check must report.
_FAULTS = MappingProxyType({
    "index.html -> gone/#local-page: missing file": (_HOMEPAGE_PATH, ('"next/#local-page"', '"gone/#local-page"')),
    "index.html -> next/#local-page: missing anchor": ("next/index.html", ('id="local-page"', 'id="moved"')),
    "search index lacks /next/": ("search/search_index.json", ('"location":"next/', '"location":"gone/')),
    f"sitemap.xml omits {_site_support.SITE_URL}": ("sitemap.xml", (_site_support.SITE_URL, "https://example.com/")),
    "index.html offers the chatgpt.com prompt 2 times": (
        _HOMEPAGE_PATH, ('href="https://chatgpt.com/"', _AI_PROMPT_HREFS[0]),
    ),
    "index.html offers the chatgpt.com prompt outside the top bar": (
        _HOMEPAGE_PATH,
        (_AI_PROMPT_HREFS[0], ""),
        ('href="https://chatgpt.com/"', _AI_PROMPT_HREFS[0]),
    ),
    "index.html offers the claude.ai prompt 0 times": (
        _HOMEPAGE_PATH, (_AI_PROMPT_HREFS[1], ""),
    ),
    "index.html offers the chatgpt.com badge 2 times": (
        _HOMEPAGE_PATH,
        (
            '<a href="https://chatgpt.com/">ChatGPT</a>',
            '<a href="https://chatgpt.com/?q=Hello"><img src="img/ask-chatgpt.svg" alt="Ask ChatGPT" /></a>',
        ),
    ),
    "index.html offers the claude.ai badge 0 times": (
        _HOMEPAGE_PATH, ('src="img/ask-claude.svg"', ""),
    ),
})
# Each described source under `docs/`, against the page the site builds from it.
_DESCRIBED_PAGES = MappingProxyType({
    "README.md": _HOMEPAGE_PATH,
    "architecture.md": "architecture/index.html",
    "state-machine.md": "state-machine/index.html",
    "workflow.md": "workflow/index.html",
    "configuration.md": "configuration/index.html",
    "observability.md": "observability/index.html",
    "security.md": "security/index.html",
})


def _site_problems(site: Path, docs: Path) -> list[str]:
    """Dead links, search omissions, sitemap mistakes, and missing, repeated, or misplaced homepage AI buttons."""
    problems = _site_support.unresolved_site_links(site)
    indexed, expected = _site_support.search_page_sets(site, docs)
    problems.extend(f"search index lacks /{page}" for page in sorted(expected - indexed))
    problems.extend(f"search index lists unknown /{page}" for page in sorted(indexed - expected))
    if _site_support.SITE_URL not in (site / "sitemap.xml").read_text(encoding=_ENCODING):
        problems.append(f"sitemap.xml omits {_site_support.SITE_URL}")
    problems.extend(_homepage_chat_problems(site))
    return problems


def _described(docs: Path) -> dict[str, str]:
    """Each described page against the `description` its source's front matter gives -- empty where it gives none."""
    return {
        page: frontmatter_field((docs / source).read_text(encoding=_ENCODING), "description")
        for source, page in _DESCRIBED_PAGES.items()
    }


def _chat_prompt_host(link: dict[str, str | None]) -> str:
    parsed = urlsplit(link.get("href") or "")
    prompt = parse_qs(parsed.query).get("q")
    return parsed.netloc if prompt == [_site_support.AI_PROMPT] else ""


def _homepage_chat_problems(site: Path) -> list[str]:
    """Each documentation prompt and badge appears once, with the prompt inside the fixed top bar."""
    homepage = _site_support.SitePage(site / _HOMEPAGE_PATH)
    chat_hosts = [_chat_prompt_host(link) for tag, link in homepage.tags if tag == "a"]
    top_bar_hosts = [_chat_prompt_host(link) for link in homepage.top_bar_links]
    return (
        _chat_badge_problems(homepage)
        + [
            f"index.html offers the {host} prompt {chat_hosts.count(host)} times"
            for host in _CHAT_BADGES if chat_hosts.count(host) != 1
        ]
        + [
            f"index.html offers the {host} prompt outside the top bar"
            for host in _CHAT_BADGES if chat_hosts.count(host) > top_bar_hosts.count(host)
        ]
    )


def _chat_badge_problems(homepage: _site_support.SitePage) -> list[str]:
    """Badge images identify duplicate buttons even when their prompts differ; prose links remain uncounted."""
    badges = [
        Path(urlsplit(attributes.get("src") or "").path).name
        for tag, attributes in homepage.tags if tag == "img"
    ]
    return [
        f"index.html offers the {host} badge {badges.count(badge)} times"
        for host, badge in _CHAT_BADGES.items() if badges.count(badge) != 1
    ]


def _faulted_copy(clean: Path, page: str, *replacements: tuple[str, str]) -> Path:
    """A copy of the clean build with one fault, so the fault exists in that copy alone."""
    site = Path(mkdtemp(dir=clean.parent)) / _site_support.SITE_DIRECTORY
    shutil.copytree(clean, site)
    edited = (site / page).read_text(encoding=_ENCODING)
    for original, replacement in replacements:
        if original not in edited:
            raise ValueError(f"{page} has no {original!r}")
        edited = edited.replace(original, replacement)
    (site / page).write_text(edited, encoding=_ENCODING)
    return site


class PublishedSiteTest(unittest.TestCase):
    def test_links_search_descriptions_and_ai_buttons(self) -> None:
        """Links, search, descriptions, and homepage AI buttons are checked against the same built site."""
        site = self._published_site()
        if site is None:
            self.skipTest(_site_support.INSTALL_HINT)
        self.assertEqual(_site_problems(site, _DOCS), [])
        described = _described(_DOCS)
        distinct = set(described.values())
        self.assertNotIn("", distinct, "every described source gives a description")
        self.assertEqual(len(distinct), len(described), "each page describes its own subject")
        for page, description in described.items():
            with self.subTest(page=page):
                self.assertEqual(_site_support.SitePage(site / page).descriptions, [description])

    def test_an_unbuilt_request_fails(self) -> None:
        """It fails without the builder too, so neither a skip nor a fresh build can stand in for the request."""
        directory = Path(self.enterContext(TemporaryDirectory()))
        requests = {"an empty value": "", "a missing directory": directory / "site", "an empty directory": directory}
        for description, requested in requests.items():
            with (
                self.subTest(request=description),
                patch.dict(os.environ, {_site_support.SITE_VARIABLE: str(requested)}),
                patch(f"{__name__}.find_spec", return_value=None),
                self.assertRaisesRegex(AssertionError, "holds no built site"),
            ):
                self._published_site()

    @unittest.skipUnless(find_spec("mkdocs"), _site_support.INSTALL_HINT)
    def test_requested_output_is_validated_in_place(self) -> None:
        """The check reads the requested directory as it stands, so a fault left in that output is reported."""
        clean = Path(self.enterContext(TemporaryDirectory())).resolve() / _site_support.SITE_DIRECTORY
        built = _site_support.build_site(_site_support.write_sample_repository(clean.parent, _HOMEPAGE), clean)
        self.assertEqual(built.returncode, 0, built.stderr)
        docs = clean.parent / "docs"
        self.assertEqual(self._requested_problems(clean, docs), [])
        for problem, fault in _FAULTS.items():
            with self.subTest(problem=problem):
                self.assertIn(problem, self._requested_problems(_faulted_copy(clean, *fault), docs))

    def _published_site(self) -> Path | None:
        """The output `DOCS_SITE_DIR` names, else a fresh strict build -- or None with neither to read."""
        requested = os.environ.get(_site_support.SITE_VARIABLE)
        if requested is not None:
            site = Path(requested).resolve()
            if not requested or not (site / "index.html").is_file():
                self.fail(f"{_site_support.SITE_VARIABLE}={requested!r} holds no built site")
            return site
        if not find_spec("mkdocs"):
            return None
        site = Path(self.enterContext(TemporaryDirectory())).resolve() / _site_support.SITE_DIRECTORY
        built = _site_support.build_site(_site_support.REPO_ROOT / "mkdocs.yml", site)
        self.assertEqual(built.returncode, 0, built.stderr)
        return site

    def _requested_problems(self, site: Path, docs: Path) -> list[str]:
        with patch.dict(os.environ, {_site_support.SITE_VARIABLE: str(site)}):
            published = self._published_site()
        self.assertEqual(published, site)
        return _site_problems(published, docs)


if __name__ == "__main__":
    unittest.main()
