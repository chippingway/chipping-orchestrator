# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The bundled theme's output outside the site's custom navigation."""
from __future__ import annotations

import json
import re
from pathlib import Path

from tests.repository import docs_site_test_support as _site_support

_ENCODING = "utf-8"
_HREF = "href"
_Attributes = dict[str, str | None]
_Tag = tuple[str, _Attributes]
_SEARCH_INDEX = "search/search_index.json"
_FOOTER = re.compile(r"<footer\b[^>]*>.*?</footer\b[^>]*>", re.DOTALL | re.IGNORECASE)
_SCRIPTS = re.compile(r"<script\b[^>]*>.*?</script\b[^>]*>", re.DOTALL | re.IGNORECASE)


def ai_button_stylesheet(head: list[_Tag]) -> _Tag:
    """The custom stylesheet beside a page's bundled theme styles, including nested and 404 paths."""
    stylesheet = next(
        attributes[_HREF] or "" for tag, attributes in head
        if tag == "link" and (attributes.get(_HREF) or "").endswith("css/base.css")
    )
    return "link", {"rel": "stylesheet", _HREF: stylesheet.replace("base.css", "ai-assistants.css")}


def rendering(site: Path) -> dict[str, object]:
    """Every page's head, footer and script markup, and modal ids, plus search, keyed by their site path."""
    rendered: dict[str, object] = {}
    for path in site.rglob("*.html"):
        page = _site_support.SitePage(path)
        markup = path.read_text(encoding=_ENCODING)
        rendered[path.relative_to(site).as_posix()] = {
            "head": page.head,
            "footer": _FOOTER.findall(markup),
            "scripts": _SCRIPTS.findall(markup),
            "modals": [
                attributes.get("id")
                for _, attributes in page.tags[len(page.head):]
                if "modal" in (attributes.get("class") or "").split()
            ],
        }
    rendered[_SEARCH_INDEX] = json.loads((site / _SEARCH_INDEX).read_text(encoding=_ENCODING))
    return rendered
