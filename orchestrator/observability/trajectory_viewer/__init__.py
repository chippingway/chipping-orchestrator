# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory viewer owners.

Home of the second Streamlit page -- the file-backed viewer that reads the
trajectory JSONL directly, usage and cost included, and needs no Postgres: the
pure filter and summary read model, the run views built from it, and the HTML a
page is rendered from.

The record side arrives first. ``constants`` owns what one line is recognized,
bracketed, and dismissed by; ``coercion`` owns the narrowing every untyped
field passes through, so a hand-edited or damaged record costs a smaller row
rather than a failed read. ``models`` owns the frozen pieces a record is read
back as -- the step, the timeline entry, and the two usage summaries -- with
the constructor signatures they are published under. ``runs`` is the record
itself, and it defines no view of its own: ``usage_views`` answers for a run's
tallies and its money, and ``timeline_views`` for the one ordered sequence it
renders as, the labels it is picked by, and the tells that mark it a fixture.
``parsing`` is what turns a decoded line into one of those records -- the event
it is accepted for, the position it is stamped with, and the narrowing every
field goes through.

The read over them arrives with it. ``reading`` is the whole of one pass over
the file: the blank, malformed, and foreign lines skipped rather than raised
over, the newest-first order the records come back in, and the missing file
answered silently where any other read error is warned about first.
``log_paths`` answers *which* file that is -- read off the settings holder a
caller hands in, so two reader worlds stay apart -- and what an operator gets
instead when the opt-in sink was never switched on.

What a page then narrows that read to arrives last, and none of it opens a
file. ``filter_models`` holds the shapes one request is spelled, narrowed, and
answered in; ``filter_values`` a single value -- the distinct ones a dropdown
is offered, the empty selection that constrains nothing, and the text a needle
is compared against; ``filtering`` which runs one request keeps, in the order
the read already handed them over; and ``summaries`` the headline counts the
survivors are totalled into. The three that answer over runs name the record at
import even though none of them builds one: what they are annotated in is a
published surface, and a name bound only for a type checker is a
``get_type_hints`` that raises for the caller reading it back.

What that read is then drawn as begins to arrive after it, and none of it
imports Streamlit either. ``css`` is the stylesheet this page adds on top of
the chrome both pages share, written against the same geometry owner the
analytics page is set in; ``summary_html`` the banner and the five tiles a
whole read is summarized in, built off the summary rather than the runs;
``run_html`` the three renderings one run is identified by -- the metadata
grid, the overview row, and the picker label; ``usage_html`` what a run cost,
tallied once for the whole run and once per assistant turn, with the note
saying why the authoritative figure and the estimates beneath it need not sum;
and ``timeline_html`` the header one entry is read by and the decision of which
entry a usage strip belongs above. What a caller passes into any of them is
escaped before it reaches the markup, because a page writes these with
``unsafe_allow_html=True`` and every value in them is record text this viewer
does not own.

What draws that markup arrives last, and it does not import Streamlit either:
each of these five takes the module in as an argument, the way a run and a
settings holder are handed in, so drawing a page costs nothing at import.
``page_models`` holds the two frozen shapes one run of the page is carried
by -- the file as it was read, and what the controls then answered.
``page_setup`` is what a run settles before anything is drawn: the two
stylesheets in the order their cascade depends on, the opt-in refusal an
unconfigured sink is stopped with, and the one pass over the file the whole
page is built from. ``controls`` draws the sidebar and reads it back as one
request, folding every "no clause" spelling together so an operator who
narrowed nothing is not answered with an empty table. ``picker`` is the two
surfaces that get from that request's survivors down to one run -- the capped
overview table, which says what it capped, and the uncapped cascade that keeps
every match reachable -- and ``run_render`` is the card the picked run is read
in full through, ordered so the notices that qualify a timeline are read before
it.

Callers import the owner they need, so this initializer binds nothing, and no
owner here imports Streamlit -- the page that does keeps that import inside
``main()``, for the same reason ``dashboard`` does and one more: everything
under this package is pure, and its value is that it stays importable, and
testable, in an install carrying no viewer dependencies at all.
"""
