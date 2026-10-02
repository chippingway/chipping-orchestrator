# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The built site keeps its links, anchors, search index, and sitemap whole.

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

from tests.repository import docs_site_test_support as _site_support

_ENCODING = "utf-8"
_DOCS = _site_support.REPO_ROOT / "docs"
_HOMEPAGE = "# Sample\n\n[local](next.md#local-page)\n"
# Each fault edits one file of a clean sample build -- the page, the text it
# replaces, and its replacement -- against the problem the check must report.
_FAULTS = MappingProxyType({
    "index.html -> gone/#local-page: missing file": ("index.html", '"next/#local-page"', '"gone/#local-page"'),
    "index.html -> next/#local-page: missing anchor": ("next/index.html", 'id="local-page"', 'id="moved"'),
    "search index lacks /next/": ("search/search_index.json", '"location":"next/', '"location":"gone/'),
    f"sitemap.xml omits {_site_support.SITE_URL}": ("sitemap.xml", _site_support.SITE_URL, "https://example.com/"),
})


def _site_problems(site: Path, docs: Path) -> list[str]:
    """Dead links and anchors, pages search misses or invents, and a sitemap that does not name the site."""
    problems = _site_support.unresolved_site_links(site)
    indexed, expected = _site_support.search_page_sets(site, docs)
    problems.extend(f"search index lacks /{page}" for page in sorted(expected - indexed))
    problems.extend(f"search index lists unknown /{page}" for page in sorted(indexed - expected))
    if _site_support.SITE_URL not in (site / "sitemap.xml").read_text(encoding=_ENCODING):
        problems.append(f"sitemap.xml omits {_site_support.SITE_URL}")
    return problems


def _faulted_copy(clean: Path, page: str, original: str, replacement: str) -> Path:
    """A copy of the clean build with one fault, so the fault exists in that copy alone."""
    site = Path(mkdtemp(dir=clean.parent)) / _site_support.SITE_DIRECTORY
    shutil.copytree(clean, site)
    edited = (site / page).read_text(encoding=_ENCODING).replace(original, replacement)
    (site / page).write_text(edited, encoding=_ENCODING)
    return site


class PublishedSiteTest(unittest.TestCase):
    def test_published_links_and_search(self) -> None:
        site = self._published_site()
        if site is None:
            self.skipTest(_site_support.INSTALL_HINT)
        self.assertEqual(_site_problems(site, _DOCS), [])

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
