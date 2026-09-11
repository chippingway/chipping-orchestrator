# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stylesheet the analytics page injects to render its own chrome.

One string, written out once at the top of the page through
`st.markdown(unsafe_allow_html=True)`, so the topbar, filter bar, KPI strip,
card grid, and insight banners carry the standalone mock's typography and
spacing. Streamlit's own widgets -- the date inputs, the segmented radio
groups, the bordered containers -- are reached through their `data-testid`
containers, which is what lets the page dress the controls Streamlit draws
instead of re-implementing them.

Every token is interpolated from the palette and geometry owners rather than
restated, so the CSS variables the chrome reads and the values the Plotly
figures are built from cannot drift apart. Producing the string costs neither
Streamlit nor Plotly, so an importer that never renders still loads cleanly.
"""
from __future__ import annotations

from orchestrator.observability.dashboard import palette as _palette
from orchestrator.observability.dashboard.tokens import (
    CARD_PADDING,
    CONTENT_MAX_WIDTH,
    FONT_FAMILY,
    GRID_GAP,
    MONO_FONT_FAMILY,
    RADIUS,
)

PAGE_CSS = f"""
<style>
  :root {{
    --orch-bg: {_palette.BACKGROUND};
    --orch-card: {_palette.CARD_BG};
    --orch-ink: {_palette.INK};
    --orch-muted: {_palette.MUTED_TEXT};
    --orch-muted-soft: {_palette.MUTED_TEXT_SOFT};
    --orch-border: {_palette.BORDER};
    --orch-grid: {_palette.GRID};
    --orch-chip: {_palette.SURFACE};
    --orch-accent: {_palette.ACCENT};
    --orch-success: {_palette.SUCCESS};
    --orch-warn: {_palette.WARNING};
    --orch-danger: {_palette.DANGER};
    --orch-input: {_palette.TOKEN_TYPE_COLORS['Input']};
    --orch-output: {_palette.TOKEN_TYPE_COLORS['Output']};
    --orch-cache: {_palette.TOKEN_TYPE_COLORS['Cache']};
    --orch-radius: {RADIUS};
    --orch-pad: {CARD_PADDING};
    --orch-gap: {GRID_GAP};
  }}
  /* Page chrome -------------------------------------------------- */
  div[data-testid="stAppViewContainer"] {{
    background: var(--orch-bg);
    color: var(--orch-ink);
    font-family: {FONT_FAMILY};
  }}
  /* Streamlit's fixed top toolbar renders OPAQUE with the page
     background and clips the top ~60px of the topbar card. The element
     is a `<header>`, so the historical `div[data-testid="stHeader"]`
     rule never matched and the background never went transparent.
     Target it tag-agnostically, make it click-through (so it stops
     intercepting the topbar beneath it) while keeping its own controls
     clickable, and drop the Deploy button + overflow menu -- chrome a
     local analytics dashboard does not use -- so nothing floats over
     the upper block. The sidebar expand/collapse control stays. */
  [data-testid="stHeader"] {{
    background: transparent; pointer-events: none;
  }}
  [data-testid="stHeader"] * {{ pointer-events: auto; }}
  [data-testid="stAppDeployButton"],
  [data-testid="stMainMenu"] {{ display: none; }}
  /* Main content column. Scoped by the stable `.block-container`
     class (the sidebar uses a different wrapper) rather than a
     `data-testid="stMain"` ancestor -- that testid is absent in some
     Streamlit releases, which silently dropped the max-width AND the
     white-card rules below, leaving every card on the gray page. */
  div[data-testid="stAppViewContainer"] .block-container,
  section.main > div.block-container,
  div.block-container {{
    background: transparent;
    padding-top: 0; padding-bottom: 48px;
    max-width: {CONTENT_MAX_WIDTH};
  }}
  /* Topbar ------------------------------------------------------ */
  /* Sticky to top:0 within the block-container. Stays inside the
     content column (no `100vw` full-bleed) -- a viewport-width bar
     overflows by the vertical scrollbar's width on any page tall
     enough to scroll, which produces a horizontal scrollbar and a
     sliver of background past the bar's right edge. The mock's bar
     is visually fine bounded to the 1480px content column. */
  .orch-topbar {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 24px; flex-wrap: wrap;
    background: var(--orch-card);
    border-bottom: 1px solid var(--orch-border);
    position: sticky; top: 0; z-index: 20;
    margin: 0 0 var(--orch-gap); width: 100%;
    padding: 18px clamp(16px, 4vw, 40px);
    box-sizing: border-box;
    font-family: {FONT_FAMILY};
  }}
  .orch-brand {{ display: flex; align-items: center; gap: 14px; }}
  .orch-brand-mark {{
    width: 34px; height: 34px; border-radius: 9px;
    background: var(--orch-accent);
    display: inline-flex; align-items: center; justify-content: center;
    color: #fff; font-weight: 700; font-size: 16px;
    letter-spacing: 0.04em; flex: none;
  }}
  .orch-brand h1 {{
    margin: 0; font-size: 18px; font-weight: 600;
    color: var(--orch-ink); letter-spacing: -0.01em;
  }}
  .orch-brand .orch-sub {{
    margin: 2px 0 0; color: var(--orch-muted-soft);
    font-size: 12px; font-family: {MONO_FONT_FAMILY};
  }}
  .orch-spend {{
    display: flex; flex-direction: column; align-items: flex-end;
    gap: 2px;
  }}
  .orch-spend .label {{
    color: var(--orch-muted-soft); font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.06em;
  }}
  .orch-spend .value {{
    color: var(--orch-ink); font-size: 22px; font-weight: 600;
    letter-spacing: -0.01em;
    font-family: {MONO_FONT_FAMILY};
  }}
  /* Filter bar ("Date range" card): the white fill / border / radius
     now come from the shared `.orch-cardmark` card rule below -- the
     dashboard renders a hidden `.orch-cardmark` as this container's
     first child so it is painted like every other card. The previous
     filter-bar-specific layout tweaks keyed off the removed
     `stVerticalBlockBorderWrapper` testid and had silently become
     no-ops; the bar lays out cleanly without them on Streamlit 1.58. */
  .orch-filterbar-anchor {{ display: none; }}
  /* The hidden `.orch-cardmark` is a standalone first child here (not
     folded into a header like the chart cards), so it adds one extra
     flex child to the filter bar's vertical block. Zero that block's
     gap so the date controls keep their 20px top inset instead of
     inheriting the vertical-block gap above them. */
  div[data-testid="stVerticalBlock"]:has(
    > div[data-testid="stElementContainer"] .orch-cardmark
  ):has(.orch-filterbar-anchor) {{
    gap: 0;
  }}
  /* On the single-line filter bar the label and the range meta are
     bottom-aligned with the date inputs and preset switch. Those Streamlit
     widgets carry ~25px of internal bottom margin, so we give the plain
     text the same bottom margin to land its baseline on the date-field /
     radio baseline instead of ~15px below it. `white-space: nowrap` keeps
     the meta on one line. */
  .orch-filter-label {{
    display: block; margin-bottom: 25px;
    color: var(--orch-muted-soft); font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.06em;
  }}
  .orch-filter-meta {{
    display: block; text-align: right; margin-bottom: 22px;
    white-space: nowrap;
    color: var(--orch-muted-soft);
    font-size: 11px;
    font-family: {MONO_FONT_FAMILY};
  }}
  /* Frame the From/To date fields. Streamlit already wraps each date
     input in a baseweb box with an 8px radius, but paints its 1px border
     white on the white card -- so the field reads as borderless floating
     text. Recolor that border to the card border tone (and highlight it
     in the accent on focus) so each date placeholder sits in a visible
     frame. The From/To pickers are the only date inputs on the page, so
     the testid selector targets exactly them. */
  div[data-testid="stDateInput"] div[data-baseweb="input"] {{
    border-color: var(--orch-border);
  }}
  div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {{
    border-color: var(--orch-accent);
  }}
  /* Content gutter: re-add the horizontal padding the block-
     container used to provide so the cards do not sit flush
     against the page edge. */
  div[data-testid="stAppViewContainer"] .block-container,
  section.main > div.block-container,
  div.block-container {{
    padding-left: clamp(16px, 3vw, 28px);
    padding-right: clamp(16px, 3vw, 28px);
  }}
  /* KPI strip ---------------------------------------------------- */
  .orch-kpis {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: var(--orch-gap); margin: 0 0 var(--orch-gap);
  }}
  .orch-kpi {{
    background: var(--orch-card); border: 1px solid var(--orch-border);
    border-radius: var(--orch-radius); padding: var(--orch-pad);
    display: flex; flex-direction: column;
    font-family: {FONT_FAMILY};
  }}
  .orch-kpi .kpi-top {{
    display: flex; align-items: center; justify-content: space-between;
  }}
  .orch-kpi .kpi-label {{
    color: var(--orch-muted); font-size: 12.5px; font-weight: 500;
  }}
  .orch-kpi .kpi-value {{
    color: var(--orch-ink); font-size: 30px; font-weight: 600;
    letter-spacing: -0.02em; margin: 8px 0 4px;
    font-variant-numeric: tabular-nums;
    font-family: {MONO_FONT_FAMILY}; line-height: 1.1;
  }}
  .orch-kpi .kpi-foot {{
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 10px; min-height: 30px;
    color: var(--orch-muted-soft); font-size: 11.5px;
    font-family: {MONO_FONT_FAMILY};
  }}
  .orch-delta {{
    font-size: 12px; font-weight: 600;
    padding: 2px 7px; border-radius: 6px; white-space: nowrap;
    font-family: {MONO_FONT_FAMILY};
  }}
  .orch-delta.up {{ background: rgba(217,83,74,.10);
    color: var(--orch-danger); }}
  .orch-delta.down {{ background: rgba(47,158,107,.12);
    color: var(--orch-success); }}
  /* Insights banner: two-column grid (matches the mock) collapsing
     to one column under 1080px. */
  .orch-insights {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: var(--orch-gap); margin: 0 0 var(--orch-gap);
  }}
  .orch-insight {{
    display: flex; gap: 12px; align-items: flex-start;
    background: var(--orch-card); border: 1px solid var(--orch-border);
    border-radius: 12px; padding: 14px 16px;
    color: var(--orch-ink); font-size: 13.5px; line-height: 1.5;
    font-family: {FONT_FAMILY};
  }}
  .orch-insight .icon {{
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--orch-ink); color: var(--orch-card);
    display: grid; place-items: center;
    font-weight: 700; font-size: 13px; flex: none; margin-top: 1px;
  }}
  .orch-insight.warning,
  .orch-insight.error {{
    background: rgba(217,83,74,.06);
    border-color: rgba(217,83,74,.22);
  }}
  .orch-insight.warning .icon,
  .orch-insight.error .icon {{
    background: var(--orch-danger); color: #fff;
  }}
  .orch-insight strong {{ font-weight: 600; margin-right: 4px; }}
  @media (max-width: 1080px) {{
    .orch-insights {{ grid-template-columns: 1fr; }}
    .orch-kpis {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  /* Card surround for charts ------------------------------------
     Streamlit 1.58 renders `st.container(border=True)` as a
     `div[data-testid="stVerticalBlock"]` carrying an unstable emotion
     class; the `stVerticalBlockBorderWrapper` testid the old rule keyed
     off no longer exists, so that rule matched nothing and every card
     sat transparent on the gray page -- the plot inside was white but
     the padding around it showed the page through. The dashboard now
     renders a hidden `.orch-cardmark` as each card's first element and
     we match the bordered container via
     `:has(> stElementContainer .orch-cardmark)`. The direct-child
     combinator pins the match to the bordered level only (a bare
     `:has(.orch-cardmark)` would also match every ancestor block) and
     keys off a class we own rather than a version-specific testid, so
     it survives Streamlit upgrades. `print-color-adjust: exact` keeps
     the white fill in the PDF/print export instead of being stripped. */
  div[data-testid="stVerticalBlock"]:has(
    > div[data-testid="stElementContainer"] .orch-cardmark
  ) {{
    background: var(--orch-card) !important;
    border: 1px solid var(--orch-border) !important;
    border-radius: var(--orch-radius) !important;
    padding: var(--orch-pad) !important;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
    font-family: {FONT_FAMILY};
  }}
  .orch-cardmark {{ display: none; }}
  /* Equal-height cards across a `st.columns` row: stretch each column
     to the tallest in the row, then let every wrapper down to the
     bordered card fill that height so the paired panels line up
     bottom-to-bottom (workflow-stage vs review-round, expensive-issues
     vs backend-efficiency, repo-cost vs reliability). Scoped to rows
     that actually carry cards (`:has(.orch-cardmark)`) so the filter
     bar's own inner columns are left untouched. The wrappers are flex
     columns so the `flex: 1 1 auto` chain carries the stretched height
     down through Streamlit 1.58's `stLayoutWrapper` / `stVerticalBlock`
     nesting to the card. */
  div[data-testid="stHorizontalBlock"]:has(.orch-cardmark) {{
    align-items: stretch;
  }}
  div[data-testid="stHorizontalBlock"]:has(.orch-cardmark)
    > div[data-testid="stColumn"] {{
    display: flex; flex-direction: column;
  }}
  div[data-testid="stHorizontalBlock"]:has(.orch-cardmark)
    > div[data-testid="stColumn"] div[data-testid="stLayoutWrapper"],
  div[data-testid="stHorizontalBlock"]:has(.orch-cardmark)
    > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {{
    flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
  }}
  div[data-testid="stHorizontalBlock"]:has(.orch-cardmark)
    div[data-testid="stVerticalBlock"]:has(
      > div[data-testid="stElementContainer"] .orch-cardmark
    ) {{
    flex: 1 1 auto;
  }}
  .orch-card-title {{
    color: var(--orch-ink); font-size: 15px; font-weight: 600;
    margin: 0; letter-spacing: -0.01em;
  }}
  .orch-card-sub {{
    color: var(--orch-muted-soft); font-size: 12px;
    margin: 3px 0 14px;
  }}
  /* Reliability tiles ------------------------------------------- */
  .orch-rel-tiles {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px;
    margin-bottom: 14px;
  }}
  .orch-rel-tile {{
    border: 1px solid var(--orch-border);
    border-radius: 10px; padding: 12px; text-align: center;
    background: transparent;
  }}
  .orch-rel-tile.good {{
    background: rgba(47,158,107,.07);
    border-color: rgba(47,158,107,.20);
  }}
  .orch-rel-tile.warn {{
    background: rgba(224,145,58,.10);
    border-color: rgba(224,145,58,.22);
  }}
  .orch-rel-tile.bad {{
    background: rgba(217,83,74,.10);
    border-color: rgba(217,83,74,.24);
  }}
  .orch-rel-value {{
    color: var(--orch-ink); font-size: 22px; font-weight: 600;
    letter-spacing: -0.01em;
    font-family: {MONO_FONT_FAMILY};
  }}
  .orch-rel-label {{
    color: var(--orch-muted); font-size: 11px;
    margin-top: 2px;
  }}
  /* Coverage bar ------------------------------------------------ */
  .orch-cov-title {{
    color: var(--orch-muted); font-size: 12px; font-weight: 500;
    margin: 14px 0 8px; padding-top: 14px;
    border-top: 1px solid var(--orch-border);
  }}
  .orch-cov-bar {{
    display: flex; height: 12px; border-radius: 6px;
    overflow: hidden; background: var(--orch-grid);
  }}
  .orch-cov-bar > span {{ display: block; height: 100%; }}
  .orch-cov-legend {{
    display: flex; flex-wrap: wrap; gap: 14px; margin-top: 9px;
    color: var(--orch-muted); font-size: 11.5px;
  }}
  .orch-cov-legend .dot {{
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 6px; vertical-align: middle;
  }}
  /* Footer ------------------------------------------------------ */
  .orch-foot {{
    margin-top: 22px; font-size: 11.5px;
    color: var(--orch-muted-soft); text-align: center;
    font-family: {MONO_FONT_FAMILY};
  }}
  /* Streamlit segmented control --------------------------------
     The dashboard drives two `st.radio(..., horizontal=True,
     label_visibility="collapsed")` controls (date-range preset,
     hero stack toggle). An earlier draft just hid the radio dot,
     which left the active option indistinguishable from the
     inactive ones -- bare text floating with no chrome. Style the
     radiogroup as a real segmented pill so the selected option
     paints a white pill with a soft shadow against the chip
     background, matching the standalone mock. The `:has(input:checked)`
     selector lights up the active label; modern Chromium / Safari /
     Firefox all support it. */
  div[data-testid="stRadio"] > div[role="radiogroup"] {{
    display: inline-flex; gap: 2px; padding: 3px;
    background: var(--orch-chip); border-radius: 9px;
  }}
  div[data-testid="stRadio"] label[data-baseweb="radio"] {{
    margin: 0; padding: 5px 12px; border-radius: 7px; cursor: pointer;
    font-size: 13px; color: var(--orch-muted);
    background: transparent;
    transition: background-color .12s, color .12s, box-shadow .12s;
  }}
  div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {{
    display: none;
  }}
  div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {{
    background: var(--orch-card); color: var(--orch-ink);
    box-shadow: 0 1px 3px rgba(0,0,0,.10);
  }}
</style>
"""
