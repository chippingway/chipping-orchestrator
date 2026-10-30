# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a card, its notes, a banner, and a tile look like by the time a browser reads them.

Every case here reads the rendered string the way the stylesheet does: a class
name is what paints a severity or a tone, an icon is what a severity says
without a word for it, and an escaped value is what keeps a repo name or an
issue title off the page as markup rather than as text. The three surfaces are
read the same way because they are one contract -- the class names spelled here
are the ones `css.py` writes rules for.

The two halves a caller may leave out are read from both sides. A card given no
subtitle must not draw an empty line under its title, and a tile handed a value
that already reads as text must not be pushed through the caller's number
formatter, because the same strip is drawn beside counts and percentages.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import card_html
from orchestrator.observability.dashboard.insights import InsightBanner

_WARNING = "warning"

# A title and a message carrying markup, so what a browser is asked to
# interpret is read off the same strings the class names are.
_UNSAFE_TITLE = "Cost <b>by</b> repo"

_ESCAPED_TITLE = "Cost &lt;b&gt;by&lt;/b&gt; repo"

_MESSAGE = "Agent failure rate >= 10% in this window."

_ESCAPED_MESSAGE = "Agent failure rate &gt;= 10% in this window."

_SUBTITLE = "Spend across managed repos"

_SUBTITLE_CLASS = "orch-card-sub"

# The glyph each severity paints with, and the neutral one a severity nothing
# is mapped for falls back to rather than a banner with an empty box on it.
_SEVERITY_ICONS = (
    ("error", "✕"),
    (_WARNING, "!"),
    ("info", "›"),
    ("success", "✓"),
    ("catastrophe", "›"),
)

_AGENT_RUNS = 250

_TIMEOUTS = 17

# One tile per shape the strip is handed: a count the caller's formatter
# renders, a percentage already in its final text, and a label carrying markup.
_TILES = (
    (_AGENT_RUNS, "Agent runs", ""),
    ("0%", "Success rate", "bad"),
    (_TIMEOUTS, "la<b>el", "warn"),
)


def _banner(severity: str) -> InsightBanner:
    """One banner of `severity`, carrying the message every case reads."""
    return InsightBanner(severity=severity, message=_MESSAGE)


class CardHeaderTest(unittest.TestCase):
    """A card is always marked and titled, its subtitle is drawn only when it
    was given one, and the text of both reaches the page escaped.
    """

    def test_the_subtitle_is_drawn_only_when_given(self) -> None:
        with_subtitle = card_html.card_header_html(_UNSAFE_TITLE, _SUBTITLE)
        titled_only = card_html.card_header_html(_UNSAFE_TITLE)
        for rendered in (with_subtitle, titled_only):
            with self.subTest(rendered=rendered):
                self.assertIn('<span class="orch-cardmark">', rendered)
                self.assertIn(_ESCAPED_TITLE, rendered)
                self.assertNotIn(_UNSAFE_TITLE, rendered)
        self.assertIn(
            f'<p class="{_SUBTITLE_CLASS}">{_SUBTITLE}</p>', with_subtitle,
        )
        self.assertNotIn(_SUBTITLE_CLASS, titled_only)


class CardNoteTest(unittest.TestCase):
    """The muted lines a card closes on are each a paragraph the stylesheet
    paints, escaped, and a note with nothing to say draws no empty line.
    """

    def test_each_given_note_is_one_escaped_line(self) -> None:
        rendered = card_html.card_note_html(_MESSAGE, "", _UNSAFE_TITLE)
        self.assertEqual(
            rendered,
            f'<p class="orch-card-note">{_ESCAPED_MESSAGE}</p><p class="orch-card-note">{_ESCAPED_TITLE}</p>',
        )
        self.assertEqual(card_html.card_note_html(""), "")


class InsightsHtmlTest(unittest.TestCase):
    """A banner says its severity through the class it is painted by and the
    icon beside it, and the message is the whole of the line it carries.
    """

    def test_each_severity_paints_its_own_icon(self) -> None:
        for severity, icon in _SEVERITY_ICONS:
            with self.subTest(severity=severity):
                rendered = card_html.insights_html([_banner(severity)])
                self.assertIn(
                    f'<div class="orch-insight {severity}">', rendered,
                )
                self.assertIn(f'<span class="icon">{icon}</span>', rendered)

    def test_the_message_is_the_whole_line(self) -> None:
        # The severity is already carried by the class and the icon, so the
        # text beside them is what the operator was told and nothing else.
        rendered = card_html.insights_html([_banner(_WARNING)])
        self.assertIn(f"<span>{_ESCAPED_MESSAGE}</span>", rendered)
        self.assertNotIn(_MESSAGE, rendered)

    def test_an_empty_stack_still_opens_the_block(self) -> None:
        # The caller branches on whether it has banners at all, so an empty
        # sequence is a container with nothing in it rather than a broken tag.
        self.assertEqual(
            card_html.insights_html([]), '<div class="orch-insights"></div>',
        )


class ReliabilityTilesHtmlTest(unittest.TestCase):
    """The strip draws one tile per `(value, label, tone)` triple: a number
    through the formatter the caller injected, a value already reading as text
    verbatim, the label escaped, and the tone as the class it is painted by.
    """

    def test_only_a_numeric_value_is_formatted(self) -> None:
        rendered = card_html.reliability_tiles_html(
            _TILES, fmt_num=lambda count: f"~{count}",
        )
        self.assertIn(f">~{_AGENT_RUNS}<", rendered)
        self.assertIn(f">~{_TIMEOUTS}<", rendered)
        self.assertIn(">0%<", rendered)

    def test_each_tile_carries_its_label_and_tone(self) -> None:
        rendered = card_html.reliability_tiles_html(_TILES, fmt_num=str)
        self.assertIn('<div class="orch-rel-tiles">', rendered)
        self.assertIn(">Agent runs<", rendered)
        self.assertIn("orch-rel-tile bad", rendered)
        self.assertIn("la&lt;b&gt;el", rendered)
        self.assertNotIn("la<b>el", rendered)


if __name__ == "__main__":
    unittest.main()
