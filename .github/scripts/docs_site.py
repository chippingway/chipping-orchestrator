# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep repository links and heading anchors usable in the published docs."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree.ElementTree import Element

from markdown import Markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.exceptions import PluginError
from mkdocs.structure.pages import Page


def _github_slugify(heading: str, separator: str) -> str:
    normalized = heading.strip().lower()
    return re.sub(r"[^\w\s-]", "", normalized).replace(" ", separator)


class _RepositoryLinkProcessor(Treeprocessor):
    def __init__(self, md: Markdown, page: Page, config: MkDocsConfig) -> None:
        super().__init__(md)
        self.source = Path(page.file.abs_src_path)
        self.docs_dir = Path(config.docs_dir).resolve()
        self.repo_root = Path(config.config_file_path).resolve().parent
        self.repo_url = config.repo_url.rstrip("/")

    def run(self, root: Element) -> Element:
        for anchor in root.iter("a"):
            href = anchor.get("href")
            if href:
                anchor.set("href", self._source_link(href))
        return root

    def _source_link(self, href: str) -> str:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
            return href
        target = (self.source.parent / unquote(parsed.path)).resolve()
        if target.is_relative_to(self.docs_dir):
            return href
        if not target.is_relative_to(self.repo_root) or not target.exists():
            raise PluginError(f"Repository link does not resolve: {target}")
        relative = quote(target.relative_to(self.repo_root).as_posix(), safe="/")
        kind = "tree" if target.is_dir() else "blob"
        url = urlsplit(f"{self.repo_url}/{kind}/main/{relative}")
        return url._replace(query=parsed.query, fragment=parsed.fragment).geturl()


class _RepositoryLinkExtension(Extension):
    def __init__(self, config: MkDocsConfig) -> None:
        super().__init__()
        self.page: Page | None = None
        self.config = config

    def extendMarkdown(self, md: Markdown) -> None:
        if self.page is None:
            raise PluginError("Repository link extension requires a current page")
        # Inline links are parsed at priority 20; MkDocs validates them at 0.
        md.treeprocessors.register(
            _RepositoryLinkProcessor(md, self.page, self.config),
            "repository_links",
            5,
        )


def on_config(config: MkDocsConfig, **kwargs: object) -> MkDocsConfig:
    config.mdx_configs.setdefault("toc", {})["slugify"] = _github_slugify
    config.markdown_extensions.append(_RepositoryLinkExtension(config))
    return config


def on_page_markdown(markdown: str, *, page: Page, config: MkDocsConfig, **kwargs: object) -> str:
    for extension in config.markdown_extensions:
        if isinstance(extension, _RepositoryLinkExtension):
            extension.page = page
    return markdown
