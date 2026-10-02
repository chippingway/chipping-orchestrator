# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Published pages retain usable links, and deployment concurrency keeps the latest revision.

Pages serves one site, so main runs share a group: GitHub replaces a pending
run with the newest one while an active deployment finishes. Pull requests
use their own refs and cancel superseded builds without displacing a deploy.
The workflow runs on GitHub, so its concurrency policy is checked as the text
GitHub receives.
"""
from __future__ import annotations

import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository import docs_site_test_support as _site_support
from tests.repository.doc_link_test_support import HEADING_ANCHOR_CASES

_ENCODING = "utf-8"
_SOURCE_URL = "https://github.com/chippingway/chipping-orchestrator/blob/main/README.md#quick-start"
_CONCURRENCY_BLOCK = """concurrency:
  group: >-
    ${{ github.workflow }}-${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' &&
    'pages' || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
"""
_SAMPLE = """# Sample

[source](../README.md#quick-start) and [reference][source].
[local](next.md#local-page).

`[example](../README.md)`

```markdown
[example](../README.md)
```

[source]: ../README.md#quick-start
"""
_HEADING_SAMPLE = "\n\n".join(f"## {heading}" for heading, _ in HEADING_ANCHOR_CASES)


class DocumentationConcurrencyTest(unittest.TestCase):
    def test_only_deploys_share_pages_concurrency(self) -> None:
        workflow = _site_support.REPO_ROOT / ".github" / "workflows" / "docs.yml"
        self.assertIn(_CONCURRENCY_BLOCK, workflow.read_text(encoding=_ENCODING))


@unittest.skipUnless(find_spec("mkdocs"), "install the docs group with uv sync --locked --group docs")
class DocumentationWebsiteTest(unittest.TestCase):
    def test_unique_heading_anchors_match_github(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, _HEADING_SAMPLE), root / _site_support.SITE_DIRECTORY,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            anchors = _site_support.SitePage(root / _site_support.SITE_DIRECTORY / "index.html").anchors
            self.assertLessEqual({expected for _, expected in HEADING_ANCHOR_CASES}, anchors)

    def test_published_links_and_search(self) -> None:
        with TemporaryDirectory() as directory:
            site = Path(directory).resolve() / _site_support.SITE_DIRECTORY
            built = _site_support.build_site(_site_support.REPO_ROOT / "mkdocs.yml", site)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(_site_support.unresolved_site_links(site), [])
            indexed, expected = _site_support.search_page_sets(site)
            self.assertEqual(indexed, expected)
            self.assertIn(_site_support.SITE_URL, (site / "sitemap.xml").read_text(encoding=_ENCODING))

    def test_source_links_preserve_code(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, _SAMPLE), root / _site_support.SITE_DIRECTORY,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            homepage = root / _site_support.SITE_DIRECTORY / "index.html"
            links = _site_support.SitePage(homepage).links
            self.assertEqual(links.count(_SOURCE_URL), 2)
            self.assertIn("next/#local-page", links)
            self.assertEqual(homepage.read_text(encoding=_ENCODING).count("[example](../README.md)"), 2)
            links = _site_support.SitePage(
                root / _site_support.SITE_DIRECTORY / "nested" / "page" / "index.html",
            ).links
            self.assertIn(_SOURCE_URL, links)
            self.assertIn("../../next/#local-page", links)

    def test_broken_repository_link_fails_build(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, "# Sample\n\n[missing](../missing.py)\n"),
                root / _site_support.SITE_DIRECTORY,
            )
            self.assertNotEqual(built.returncode, 0, built.stderr)
            self.assertIn("Repository link does not resolve", built.stderr)


if __name__ == "__main__":
    unittest.main()
