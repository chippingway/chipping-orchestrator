# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The compact table the page's hand-rolled panels are drawn as."""
from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import tables

# Two panels drawn by the same helper, named here so a case can check that
# neither one's rules reach the other's markup.
_ISSUES_CLASS = "orch-issues"

_SKILLS_CLASS = "orch-skills"

_EXTRA_RULE = "  .orch-issues td.strong { font-weight: 600; }"

# Stand-ins for the stylesheet and header a caller hands the assembly, so the
# order they are written in is readable off the rendered string.
_CSS_MARKER = "<style>css</style>"

_HEAD_MARKER = "<thead>head</thead>"

_ROWS = ("<tr>one</tr>", "<tr>two</tr>")

# A header label carrying markup, and what a cell renders it as.
_UNSAFE_LABEL = "cost<&>"

_ESCAPED_LABEL = "cost&lt;&amp;&gt;"

# One bar at the width of the widest, one at half of it, and the widths each
# is drawn at.
_WIDEST_BAR = 10.0

_HALF_BAR = 5.0

_FULL_WIDTH = 100.0

_HALF_WIDTH = 50.0

_NO_BAR = float(0)


class TableMarkupTest(unittest.TestCase):
    """Four panels are inline HTML rather than `st.dataframe`, so what they
    share has to be one stylesheet and one assembly: a panel restating either
    is the one that stops matching the others.
    """

    def test_rules_are_scoped_to_the_class(self) -> None:
        issues_css = tables.table_css(_ISSUES_CLASS)
        skills_css = tables.table_css(_SKILLS_CLASS)
        self.assertNotIn(_SKILLS_CLASS, issues_css)
        self.assertNotIn(_ISSUES_CLASS, skills_css)
        for rule in ("thead th", "tbody td", "td.r"):
            with self.subTest(rule=rule):
                self.assertIn(f".{_ISSUES_CLASS} {rule}", issues_css)

    def test_extra_rules_land_inside_the_style(self) -> None:
        # A panel's own rules are written in the tag the shared ones are, so a
        # page cannot render one styled by half of what it asked for.
        css = tables.table_css(_ISSUES_CLASS, extra_rules=_EXTRA_RULE)
        self.assertIn(_EXTRA_RULE, css)
        self.assertLess(css.index(_EXTRA_RULE), css.index("</style>"))

    def test_header_right_aligns_what_asked(self) -> None:
        self.assertEqual(
            tables.table_head_html((("Issue", False), ("Cost", True))),
            '<thead><tr><th>Issue</th><th class="r">Cost</th></tr></thead>',
        )

    def test_header_escapes_a_label(self) -> None:
        head = tables.table_head_html(((_UNSAFE_LABEL, False),))
        self.assertIn(_ESCAPED_LABEL, head)
        self.assertNotIn(_UNSAFE_LABEL, head)

    def test_table_is_assembled_in_order(self) -> None:
        # The rules precede the markup they style, and the rows land inside
        # the body rather than beside the header.
        self.assertEqual(
            tables.table_html(
                table_class=_ISSUES_CLASS,
                css=_CSS_MARKER,
                head=_HEAD_MARKER,
                rows=_ROWS,
            ),
            "{}<table class=\"{}\">{}<tbody>{}</tbody></table>".format(
                _CSS_MARKER, _ISSUES_CLASS, _HEAD_MARKER, "".join(_ROWS),
            ),
        )


class CellReadingsTest(unittest.TestCase):
    """What a cell reports before it is escaped into the markup above."""

    def test_bar_is_a_share_of_the_widest(self) -> None:
        cases = (
            (_WIDEST_BAR, _WIDEST_BAR, _FULL_WIDTH),
            (_HALF_BAR, _WIDEST_BAR, _HALF_WIDTH),
            # A window whose rows all read zero has no widest bar to be a
            # share of, so every row draws an empty one rather than dividing.
            (_HALF_BAR, _NO_BAR, _NO_BAR),
        )
        for magnitude, maximum, width in cases:
            with self.subTest(magnitude=magnitude, maximum=maximum):
                self.assertEqual(
                    tables.relative_width_pct(magnitude, maximum), width,
                )

    def test_repo_name_drops_the_owner(self) -> None:
        cases = (("acme/orchestrator", "orchestrator"), ("bare", "bare"))
        for repo, labelled in cases:
            with self.subTest(repo=repo):
                self.assertEqual(tables.short_repo_name(repo), labelled)

    def test_a_missing_count_reads_as_zero(self) -> None:
        # A read answers a row that never reached review with a null rather
        # than a zero, and the column it lands in is right-aligned numerals.
        self.assertEqual(tables.int_or_zero(None), 0)
        self.assertEqual(tables.int_or_zero("4"), 4)


if __name__ == "__main__":
    unittest.main()
