# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Parse navigation landmarks, top bar links, and sidebar headings from built docs HTML."""
from __future__ import annotations

from html.parser import HTMLParser

_Attributes = dict[str, str | None]
_ANCHOR_TAG = "a"


class NavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        # Each `<nav>` by its `aria-label`, against the attributes of every link inside it.
        self.landmarks: dict[str, list[_Attributes]] = {}
        self.top_bar_links: list[_Attributes] = []
        self.sidebar_headings: list[_Attributes] = []
        self._open_landmarks: list[str] = []
        self._top_bar_depth = 0
        self._sidebar_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_starttag(tag, dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self._open_landmarks:
            self._open_landmarks.pop()
        elif tag == "div":
            if self._top_bar_depth:
                self._top_bar_depth -= 1
            if self._sidebar_depth:
                self._sidebar_depth -= 1

    def _record_starttag(self, tag: str, attributes: _Attributes) -> None:
        self._record_landmark(tag, attributes)
        self._record_top_bar(tag, attributes)
        self._record_sidebar(tag, attributes)

    def _record_landmark(self, tag: str, attributes: _Attributes) -> None:
        if tag == "nav":
            label = attributes.get("aria-label") or ""
            self._open_landmarks.append(label)
            self.landmarks.setdefault(label, [])
        elif tag == _ANCHOR_TAG and self._open_landmarks:
            self.landmarks[self._open_landmarks[-1]].append(attributes)

    def _record_top_bar(self, tag: str, attributes: _Attributes) -> None:
        classes = (attributes.get("class") or "").split()
        if tag == "div" and (self._top_bar_depth or {"navbar", "fixed-top"}.issubset(classes)):
            self._top_bar_depth += 1
        elif tag == _ANCHOR_TAG and self._top_bar_depth:
            self.top_bar_links.append(attributes)

    def _record_sidebar(self, tag: str, attributes: _Attributes) -> None:
        """Heading links inside the sidebar card, outside the section's navigation landmark."""
        if tag == "div":
            if self._sidebar_depth or attributes.get("id") == "toc-collapse":
                self._sidebar_depth += 1
        elif tag == _ANCHOR_TAG and self._sidebar_depth and not self._open_landmarks:
            self.sidebar_headings.append(attributes)
