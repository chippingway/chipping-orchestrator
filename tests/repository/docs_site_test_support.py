# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Build the docs and check the links a visitor follows in the generated HTML.

`SITE_VARIABLE` names a site that is already built -- the one the Documentation
workflow uploads -- so the check reads that output instead of building its own.
"""
from __future__ import annotations

import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_URL = "https://chippingway.github.io/chipping-orchestrator/"
SITE_DIRECTORY = "site"
SITE_VARIABLE = "DOCS_SITE_DIR"
INSTALL_HINT = "install the docs group with uv sync --locked --group docs"
_SITE_ADDRESS = urlsplit(SITE_URL)
_ENCODING = "utf-8"
_BUILD_TIMEOUT_SECONDS = 30
_LINK_ATTRIBUTES = MappingProxyType({"a": "href", "link": "href", "img": "src", "script": "src"})
_DOCS_ROOT = REPO_ROOT / "docs"
_NESTED_SAMPLE = """# Nested page

[source](../../README.md#quick-start).
[local](../next.md#local-page).
"""


class SitePage(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()
        self.feed(path.read_text(encoding=_ENCODING))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        anchor = attributes.get("id") or attributes.get("name")
        if anchor:
            self.anchors.add(anchor)
        attribute = _LINK_ATTRIBUTES.get(tag, "")
        href = attributes.get(attribute)
        if href:
            self.links.append(href)


def build_site(config: Path, site: Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "mkdocs", "build", "--strict"]
    command.extend(["--config-file", str(config), "--site-dir", str(site)])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_SECONDS,
        check=False,
    )


def unresolved_site_links(site: Path) -> list[str]:
    pages = {path: SitePage(path) for path in site.rglob("*.html")}
    return [
        problem
        for path, page in pages.items()
        for href in page.links
        if (problem := _link_problem(site, path, href, pages))
    ]


def _link_problem(site: Path, source: Path, href: str, pages: dict[Path, SitePage]) -> str:
    parsed = urlsplit(href)
    target = _local_target(site, source, href)
    if target is None:
        return ""
    if not target.is_relative_to(site):
        return f"{source.relative_to(site)} -> {href}: outside the site"
    if target.is_dir():
        target /= "index.html"
    if not target.is_file():
        return f"{source.relative_to(site)} -> {href}: missing file"
    anchor = unquote(parsed.fragment)
    if anchor and target in pages and anchor not in pages[target].anchors:
        return f"{source.relative_to(site)} -> {href}: missing anchor"
    return ""


def _local_target(site: Path, source: Path, href: str) -> Path | None:
    parsed = urlsplit(href)
    if parsed.netloc and parsed.netloc != _SITE_ADDRESS.netloc:
        return None
    if parsed.scheme and not parsed.netloc:
        return None
    path = unquote(parsed.path)
    if path.startswith("/"):
        return (site / path.removeprefix(_SITE_ADDRESS.path)).resolve()
    if not path:
        return source
    return (source.parent / path).resolve()


def write_sample_repository(root: Path, markdown: str) -> Path:
    docs = root / "docs"
    docs.mkdir()
    (root / "README.md").write_text("# Quick start\n", encoding=_ENCODING)
    (docs / "README.md").write_text(markdown, encoding=_ENCODING)
    (docs / "next.md").write_text("# Local page\n", encoding=_ENCODING)
    (docs / "nested").mkdir()
    (docs / "nested" / "page.md").write_text(_NESTED_SAMPLE, encoding=_ENCODING)
    config = root / "mkdocs.yml"
    hook = REPO_ROOT / ".github" / "scripts" / "docs_site.py"
    config.write_text(
        "site_name: Sample\n"
        f"site_url: {SITE_URL}\n"
        "repo_url: https://github.com/chippingway/chipping-orchestrator\n"
        f"hooks:\n  - '{hook}'\n"
        "validation:\n  links:\n    anchors: warn\n",
        encoding=_ENCODING,
    )
    return config


def search_page_sets(site: Path, docs: Path = _DOCS_ROOT) -> tuple[set[str], set[str]]:
    index = json.loads((site / "search" / "search_index.json").read_text(encoding=_ENCODING))
    indexed = {urlsplit(entry["location"]).path for entry in index["docs"]}
    expected = {""}
    for source in docs.rglob("*.md"):
        relative = source.relative_to(docs).with_suffix("")
        if source.name == "README.md":
            relative = relative.parent
        if relative != Path("."):
            expected.add(f"{relative.as_posix()}/")
    return indexed, expected
