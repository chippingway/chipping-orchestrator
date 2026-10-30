# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics dashboard owners.

Destination for the Streamlit page rendered over the operator's Postgres
target: the filter state a run of it carries, the read plans it issues, the
KPI, chart, table, and drilldown components, and the theme tokens they share.
``palette``, ``tokens``, ``layout``, ``css``, and ``formatting`` are those
tokens, split by what a value is, and ``theme`` is the one object they are
handed down as: the panels below take a theme as a parameter rather than
importing one, so a page composes that object once and every card is tinted,
set, and shortened from the same reading.
The state a run carries is the first to arrive -- ``windows`` for the date
span and the presets that name one, ``filters`` for the offset, issue, stage,
and cache key it is narrowed and displayed by, and ``read_mode`` for the knob
its reads are issued under and the message an unconfigured database is refused
with. ``date_controls`` and ``date_filter`` are where an operator picks that
span: the five slots the filter bar is laid out across together with the label
and the inline presets drawn among them, and the bar itself -- the window
a preset opens the pickers on, the inclusive days those pickers hand back, and
the half-open window plus the placeholder for the filter line they leave with.
``page_controls`` is the band that bar sits in and the load the choices made
there open: the sidebar a run is narrowed in, the offset its timestamps are
displayed against -- seeded here on the first render and read back off the
session on every one after, since the card that offers it sits at the foot of
the page -- the normalization those raw selections go through, the controls the
whole band is read back as, and the staged plan every panel below is drawn
from. Keeping the narrowing and the staging together is what makes them one
description, since the filters one resolves are what the other's keys are
hashed from.
``read_plan`` is what that state is spent on: the two waves a load is
staged into, the cached task each entry is bound as, and the pair of keys --
this window and the one before it -- they are issued under. ``fanout`` runs
one of those waves the way the knob said, on the calling thread or across a
pool capped at the count beside it, and ``dispatch`` drives both of them in
turn: one spinner over the pair, the chrome rendered between them, a banner and
a stop when a read cannot reach the database, and one timing line when the load
comes back. ``page_pipeline`` is that chrome and the load it opens: the banner
and filter line written back into the slots the controls left, the banners a
window is worth interrupting a page for, the four-tile strip every section
below is read against, and the staged load all three are drawn inside -- whose
first pass is also where a load can end, since a window reporting no event at
all leaves through the empty-window notice and hands nothing back, which is
what the dispatch above short-circuits the second wave on. Each
of those readers goes through ``scoped_reads`` for the connection it runs on,
``filter_binding`` for the filters its cache key is read back as, and --
before any of them, because it is what a window can be picked at all from --
``static_metadata`` for the extent and filter vocabulary a page opens on. The
readers themselves arrive with the panels they are drawn for: ``rollups`` for
the seven a headline or lifecycle section is built from, ``breakdowns`` for
the six a comparison section is, and ``skills`` for the three a skill section
is. Above all of them, ``insights`` holds the two observations a window is
worth interrupting a page for and the ratio each is raised at, and ``kpis``
the four numbers that window is summarized by beneath them. ``kpi_series`` and
``kpi_strip`` are how those numbers reach the page: the per-day spend, token,
and resolved lines a sparkline is drawn from, and the four display entries a
window's own aggregate, the one before it, and three of its first-wave reads
are assembled into. ``cost_text`` and ``spend_text`` are the words their money
is qualified by: the first how one cost reads on either page -- its amount, the
basis it is stated on, and why it falls short of complete spend -- and the
second what only a cohort of runs, a window's or an issue's, can say on top of
that: that it held no run, how many runs left its amount short, and what a move
between two windows is read with. ``breakdown_text`` is what a grouped
breakdown's bar fits of that wording -- the figure drawn past it, the basis and
shortfall under its label -- with the note a panel of such bars closes on and
the one saying a token-share split is an allocation rather than a measured
cache charge. ``sparkline_points`` and ``sparkline_html`` are how one of
those lines reaches a tile: where each day sits in a box too narrow for an axis
-- scaled to the window's own range, floored where a window has none, and left
undrawn where it reported nothing at all -- and the polyline and closed fill
that projection is written as. ``summary_html`` is the band that strip sits in:
the banner naming what the database holds and the window's qualified spend, the
line restating what a run's filters narrowed it to, the pill one tile's move
against the window before it is annotated with, and the four tiles assembled
around them.
``card_html`` is the markup the banners and the
run-health
tiles among those numbers reach the browser as, together with the header every
panel below them is titled by, the muted notes one closes on, and the hidden
mark ``css`` selects a card's container by, and ``tables`` is the markup beside it: the compact table the
four hand-rolled panels are listed in, with the stylesheet each scopes to its
own class, the header and body they are assembled from, and the bar width,
short repository name, and missing count a cell reports. ``issue_table`` is the
first of those four panels: the six columns a window's costliest issues are
ranked into, the rules their in-row bars and status pills are painted by, and
the row each issue is reduced to and rendered as, its cost worded by basis and
shortfall and its bar drawn open where that cost is short of complete spend.
``skill_trigger_table`` is the second: the six columns a cohort's skill use is
reported in, the busiest rate in the table its bar is drawn as a share of, and
the label a cohort the sink named no role or backend for is read under.
The last two are the ones an operator can reorder, so each arrives split by
what a click moves. ``skill_adoption`` is the third: ``skill_adoption_columns``
for the ten columns per-session adoption is read across and the two query
parameters a heading writes, ``skill_adoption_sort`` for the parse those
parameters are read back through and the orders they select,
``skill_adoption_headers`` for the header row each heading is drawn as a sort
control in, ``skill_adoption_rows`` for what one `(repo, role, backend, skill,
level)` cell says -- including which of the two quiet cells reports an
undefined rate and which a real zero -- and ``skill_adoption`` itself for the
sorted panel, the notice a window with no session evidence renders instead,
and the message a caller drawing one slice of a window's cells names in that
notice's place.
``skill_matrix`` is the fourth, split the same five ways:
``skill_matrix_columns`` for the eight columns it is read across and its own
pair of query parameters, ``skill_matrix_sort`` for the parse and orders,
``skill_matrix_headers`` for the header row, ``skill_matrix_rows`` for what one
cell triggered, and ``skill_matrix`` itself for the sorted panel and the notice
a window with no catalog-backed cell renders instead.
``skill_panel`` and ``skill_trigger_panel`` are the two cards three of those
four are reported on. The first is the one the page draws: the aggregate rates
and the matrix open it in one collapsed expander, adoption follows in a
collapsed section per source level -- project, user, harness, and a fourth for
a cell no record classified -- one notice answers a window with no `agent_exit`
row for the whole card, and the caption under those sections qualifies a window
nobody adopted anything in rather than recommending a switch a present row
already proves is on -- which is also what the fold above is handed, to tell a
genuine no-trigger from tracking nobody turned on. The second is the card the
section led with before that one and is kept for a caller that names it: its
own notice, its unconditional prompt to enable tracking, and its own fold-out
matrix.
``recent_runs`` is the listing under those four panels rather than a fifth in
that table: the rows behind the readings above it, projected into the columns
one run is scanned by -- its stored cost worded by basis, with an estimate's
rate dates -- and the offset the sidebar picked, drawn in the collapsed
expander the page ends on, and the notice a window with no `agent_exit` row
renders in place of an empty frame.
``drilldown`` is the last narrowing under that listing: one issue's events in
the order they happened, read outside the cached wrappers because it is scoped
by an issue on top of the window those keys carry, together with the columns
one event is traced in, the notice a number typed before a repository is
answered with, and the two an empty window and a failed read leave instead.
``page_states`` is what is drawn where none of those panels can be: the startup
state a database nobody has ingested into is answered with, which zeroes the
banner's counts and stops the script where it stands; the notice a filtered
window matching no row gets, which emits the load line the skipped second wave
would have carried and hands the page on to that trace; and the footer
restating the span and the run count everything above it was measured over,
closed on the day before the window's end since the reads beneath it are issued
under ``ts < end``.
``usage_panel`` is the card above all of them, the first one under the strip:
the header it is titled by, the two-value toggle deciding whether a day's
tokens are stacked by what they were spent on or by who spent them, the
session-state key that mode survives a rerun in, and the per-day per-backend
totals the second stack is drawn from, summed so a `(day, backend)` cell read
back twice is one band rather than the last of two, with that read's own runs
of unknown token total per day beside them.
Two panels are markup of their own rather than a figure: ``backend_card``
for what a run on one backend is worth and the card the three readings behind
it are laid out on, and ``coverage_card`` for the share of a window's spend the
parser could price, drawn as one bar and the legend under it.
``stage_cost_panel`` and ``issue_cost_panel`` are the first two of the three
sections that spend is compared across, each a pair of columns split 7:5. The first draws the
lifecycle bars -- where the money went by stage beside where it went by review
cycle -- pinned to one height taken off whichever axis carried more buckets, so
two figures read across a gutter cannot stand at different bar thicknesses. The
second draws the window's costliest issues beside the backends that ran them,
and closes that column with the coverage bar qualifying the money the cards
above it report; its two columns answer an empty window differently, since a
window can carry runs the parser could not price while a window with no
`agent_exit` row had nothing to run at all.
``reliability_panel`` closes that run of sections with the third pair, split
the same way: where the window's money went by repository, beside whether the
runs it went to held up. The narrow column is a strip of run-health tiles over
the days the issues those runs resolved landed on, and that day figure is
handed the window's last included day rather than its end, since the reads
below are issued under `ts < end` and a bound taken off `end` itself would draw
a trailing day none of them covered.
``activity_panel`` is the card under all three, and the only one that keeps the
clock rather than reducing the window to a reading: the weekday-by-hour grid
its tokens landed on, headed by the zone those hours are read in and carrying
the one selectbox that picks it. That control sits in the card because it
changes what the figure means rather than which rows reach it, and it is keyed
into the session under the name the page reads the offset back off at the top
of the next rerun -- the read buckets the cells, so the label is true only
while the widget and that read name one key.
``chart_sections`` and ``page_sections`` are the order all of those panels are
reached in once the second wave answers. The first holds the five cards a
window's figures are drawn on, stacked as the page argues them: whether a day's
cost tracked the work behind it, where that cost went, which issues and
backends it went to, whether the runs it went to held up, and -- last, because
it is the only card that keeps the clock rather than reducing the window to a
reading -- when they ran. The second holds the four beneath those cards: what
the runs were working with, the rows every reading above was reduced from, the
trace an operator opens one of those rows into, and the line the page signs off
on. It also holds the single call the whole second wave is drawn by, so the
order across both halves stays readable from one place.
``page_models`` is what a render carries between all of those: the seven frozen
shapes threaded from the controls at the top of the page to the last panel on
it -- the caller's own Streamlit, pandas, and theme handles, the
selections every read is narrowed by together with the issue scope and window
span read off them, the controls and page they open on, what one load answers
with, and the rows, totals, and counts the paired repository-spend and
run-health section is drawn from.
``render_config`` is the one thing every figure below is handed
beside itself: the hover toolbar switched off once for the whole page rather
than at each call site.
What those reads
are then drawn as arrives under ``charts``, where ``primitives`` holds what
every figure family is built out of -- the placeholder a window holding no
rows is answered with, the labels a bar is annotated by, and the height and
legend a horizontal-bar panel is laid out with -- ``cost_layout`` the frame
the horizontal cost families are drawn in and the request one series of bars
is described by, ``cost_horizontal``, ``cost_repo``, ``cost_stage``,
``cost_review``, ``heatmap``, and ``throughput`` hold six families above the
two, the generic spend ranking, the per-repository one drawn through it, the
per-stage split of that spend into what the cache paid for, the per-review-round
split of it across the two roles a round is worked by, the 7x24 weekday-by-hour
grid, and the per-day resolved-issue strip, and
``usage_bands``, ``usage_series``, ``usage_axis``, ``usage_traces``, and
``usage`` hold the usage family: the four bands a day of usage is counted into
and the roll-up that counts them, the days that roll-up spans and the height
each stack over them reaches, the maxima those heights are rounded up to and
the layout the token and cost scales are assembled in, the bands and cost line
a window is drawn as, and the hero figure they are assembled into.

Callers import the owner they need, so this initializer binds nothing.
Streamlit and Plotly live in the optional ``dashboard`` dependency group, so
no owner here names them at module scope: one that assembles a figure imports
Plotly inside that call, one that draws a panel is handed the page it draws
onto as a parameter, and one that only shapes data or markup for another owner
names neither. An ordinary import must keep working
in the default install, which has neither, and the data an owner shapes stays
testable without them.
"""
