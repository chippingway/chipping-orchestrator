# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics query owners.

Destination for the read side of the operator's Postgres target: the typed
filters and connection inputs one request carries, the query families built
from them, and the read models a page renders.

The connection half is here already. ``connections`` owns what a read dials
with -- the lazily imported driver, the two connect factories, and the one
exception every driver failure is wrapped in; ``connection_cache`` owns the
persistent socket a thread reuses across many reads and the two events that
evict it; and ``execution`` owns one SELECT: whose connection it runs on and
whether that connection is closed afterwards.

So is what a read is asked for. ``requests`` owns the keyword vocabulary every
public read is called by and the bind of one such call into the typed parts
``request_models`` declares; ``filters`` owns the selection those parts project
onto and the builder a predicate and its bindings accumulate in together;
``predicates`` owns the `WHERE` clause that selection becomes against each of
the three tables it can be scanned on; and ``conditions`` owns the splice of a
table's own required condition into it, the finished-run condition the reads
narrowing to completed runs splice, plus the probe that decides whether an
event filter leaves a view-backed read any rows at all.

So is what a read answers with, one owner per result family:
``activity_models`` for the cells a volume is bucketed into by when it
happened, ``overview_models`` for what a page frames a whole window with,
``cost_models`` for the axes its spend is broken down along, ``run_models`` for
the run, issue, and traced-event rows plus the accessor behind the trace row's
`result` alias, and ``skill_models`` for the cells a skill's reach is reported
in with the share each derives.

So is one family of reads itself. ``raw_reads`` owns the six answered off the
events table row by row -- the values its filters offer, how far its data
reaches, what each event counted, the newest agent runs, one row per issue, and
one issue's trace -- and each names the projection owner beside it:
``filter_options``, ``event_breakdowns``, ``agent_exits``, ``issue_summaries``,
and ``issue_events`` each own one family's SQL and the rows it is read back as.
Under them, ``query_rows`` names the columns of the widest SELECT lists so a
projection reads them by field rather than by index, and ``raw_values`` narrows
one column to what its result field declares -- a JSONB cell included, decoded
the same whether a driver adapted it or handed back its text -- plus the
cleared multiselect no row can match.

So is the second family. ``rollup_reads`` owns the seven answered off the
day-bucketed rollup instead -- what a window totalled, what the window before it
did, its daily series, and its stage, backend, repository, and throughput
breakdowns -- and again names one projection owner per read.
``summary_queries`` owns the single round-trip totals and both breakdowns come
back from and ``summary_results`` the ranking and defaulting they are read back
with; ``kpi_totals`` the trimmed scalar scan a delta is measured against;
``time_series`` the per-day-and-event cell a chart pivots; ``stage_breakdowns``
and ``backend_efficiency`` the two axes a run's spend and duration are compared
along; ``repo_breakdowns`` each repository's share of the window; and
``throughput_days`` the two terminal stages a day resolved or turned away.

So is the third. ``breakdown_reads`` owns the four whose grouping key that
rollup threw away: a review round, a cost source, and one run's own token split
are per-run facts the day bucket aggregated over, so those three scan the
agent-run view, and an hour of day is what it rounded off, so the heatmap stays
on the events table. ``review_rounds`` owns the bucketing a round is labelled
by and the two roles each bucket is reported per, ``cost_coverage`` the sources
a window's spend could be attributed to, ``backend_tokens`` the per-day stack
each backend contributes, and ``hourly_heatmaps`` the weekday-and-hour cell,
with the offset that cell is bucketed in bound rather than spliced.

So is the fourth. ``skill_reads`` owns the three answered from the `extras`
JSONB blob no table above the events one carries: how often a cohort reaches
for a skill at all, which of a repository's offered skills each cohort
triggered, and how many sessions that could have used one did.
``skill_trigger_rates`` owns the cohort denominator a quiet role still reports
against, ``skill_matrices`` the runs scan the observed cells are counted from
with the padding and the ranking over them, ``skill_provenance`` the catalog
scan that padding is drawn from, the narrower filtering that repository-level
scan takes, and the one offered level an unclassified load is filed at,
``skill_adoption`` the per-session ratio and the window diagnostics that ride
beside it without moving it, and ``skill_sessions`` which row belongs to which
logical session and how far back the evidence for one reaches. Beneath them,
``skill_values`` owns the coercion a JSONB name array is read through, the
cohort a row is filed under, and the ranking a matrix cell is sorted by.

Beneath the rollup and breakdown families, ``cache_shares`` owns the token
share one row's cost is split into cache and no-cache bands by, once per set of
column names the two scan targets spell it with. ``row_cells`` owns the
readings a cell from any of the four passes through before it lands in a result
field -- alongside ``raw_values``, whose NULL-preserving coercions every family
projects through.

Callers import the owner they need, so this initializer binds nothing, and the
connection stays under the owner that opens it -- a read model is a plain
dataclass, and importing one must not reach a database.
"""
