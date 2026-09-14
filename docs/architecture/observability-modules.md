# Observability modules

This page maps `orchestrator/observability/` — the four surfaces that watch a run without steering it: the analytics
sink and everything downstream of it, the parser that meters one finished agent run, the Streamlit page over the
operator's Postgres target, and the file-backed trajectory viewer beside it — together with the two `streamlit run`
targets under `orchestrator/apps/` that compose the pages. It is split out of
[`../architecture.md#top-level-layout`](../architecture.md#top-level-layout), which keeps the top-level map and the
naming rules that hold for the tree as a whole. The packages these owners observe are in
[`platform-modules.md`](platform-modules.md) and [`workflow-modules.md`](workflow-modules.md).

Each entry below is the responsibility its package holds, and it answers there and on no second site. What each sink
writes, what the database a replay fills holds, and what the two pages report over them are in
[`../observability.md`](../observability.md) and the focused pages under it; the knobs are in
[`../configuration/observability.md`](../configuration/observability.md).

## Enforced boundaries

The first four rules below are held by checks that walk the tree off disk, so an owner added anywhere under it is
covered the day it lands. The last two are held against a declared list instead — the analytics owners' own import
guard for the first, and the owner's own tests for each channel of the second, save the sink's, which is convention.

- **Observation-only.** Nothing here sits on the workflow's decision path, so no module may import the workflow
  engine, a stage, or an application entry point — the CLI and the runtime loop on one side, the two `streamlit run`
  targets under `apps/` on the other. The dependency runs one way and an entry point composes these owners rather
  than the reverse. That is also what makes every surface safe to truncate, rotate, or delete.
- **An initializer binds nothing, with two declared exceptions.** Importing one owner must not charge the importer
  for its siblings: the recording path runs inside every tracked agent run, and a binding would put the query owners
  and the database driver behind that import. `usage/` and `analytics/recording/` pay that cost deliberately, since
  each is reached through its package rather than through an owner, and the check that excuses them is keyed on
  their `__all__`, so a third publisher is a deliberate edit rather than a silent one. What a publisher may charge
  for beyond its own owners is declared per package: recording buys the analytics configuration, the shared sink,
  the usage parsers, and the trajectory writers, and nothing else.
- **No second site.** Nothing under the tree carries an export manifest, a resolver hook, or a `.pyi` stub — a
  re-export is the owner's own object, bound once at import, so a lookup lands on the module that defines the name
  rather than on something answering for it. The same check holds the declared package inventory against what is on
  disk and requires a mirrored tests package for each.
- **Streamlit and Plotly stay function-local.** Both live in the optional `dashboard` dependency group, so every
  module has to import cleanly with the two blocked outright *and* with no attempt on either recorded — a
  module-scope import that swallows its own `ImportError` is still a load in the install that has the package.
  Pandas joins them one level up: no launch path under `apps/` may cost one of the three at import.
- **One knob binder, and one lazy reach past it.** `analytics/environment.py` parses the six sink and database
  knobs — the disable vocabulary with them, so what "off" spells is settled once — and `analytics/settings.py` is
  the sole module that calls those parses and the sole module that binds them, so a knob answers the same way
  wherever it is read. Reading one back is the configuration owner beside them: every adapter resolves a knob off a
  holder inside the call rather than at import, which is what lets a caller settle *which* holder answers — the
  trajectory app hands its page one explicitly, while the analytics page resolves the live one through the
  configuration owner as it reads. That holder is also the only place a knob is read out of `orchestrator.config`,
  for the `LOG_DIR` the default sink lives under, and the parse defers that import to a call so nothing on the
  append path pays for it until a record is written. The one other reach into the configuration layer is not a knob
  at all: the trajectory writer imports the secret redactor inside the write that uses it, so a producer on the
  recording path pays for the credential owner only when the opt-in sink is actually on.
- **Operator log channels are spelled literally** rather than derived from `__name__`, because an operator's level
  and handler selection is keyed on them: `orchestrator.analytics` for a refused sink write,
  `orchestrator.analytics.sync` for a replay, `orchestrator.analytics.connection` for a read-path driver failure,
  `orchestrator._dashboard_read_dispatch` for the one `dashboard.load:` line an operator A/Bs the fan-out with, and
  `orchestrator.trajectory_reader` for a trajectory file the viewer could not read. A module moved between packages
  does not take its channel with it.

## The map

Each line is the responsibility its package holds; which owner inside it decides what is in that module's own
docstring. A package publishes a surface only where the entry says so — everywhere else the initializer is a marker
and callers import an owner directly.

```
orchestrator/
  observability/        the four surfaces that watch a run without steering it, one package each; nothing sits flat
                        beside them
    analytics/          the JSONL sink and everything downstream of it: the parse of the six sink and database
                        knobs, the process-wide holder bound over it and the view an adapter reads one back
                        through, the record envelope and locked line both sinks reach disk through, and the by-age
                        prune that bounds each of them
      recording/        the append side, publishing the six recorders a producer appends through (`__all__`): the
                        envelope and the append beneath them, and the token, cost, skill, and catalog steps a
                        finished agent run is summarized by before one of them writes
      query/            the read side of the Postgres target: the keyword vocabulary a read is called by, the
                        selection it narrows to, what it dials with, and the four families it is answered by — the
                        events table, the day-bucketed rollup above it, the per-run breakdowns whose grouping key
                        that rollup threw away, and the skill facts recorded in an `agent_exit` row's `extras` —
                        each over frozen result models a caller can consume with no driver installed
      sync/             the JSONL → Postgres replay and the `-m` command an operator schedules: what a record must
                        carry and hash to, the dedup and batching one pass is made of, the driver boundary beneath
                        it, and the transaction shape a run guarantees
      trajectories/     the opt-in per-run reasoning sink: the caps a record is measured against, the redaction and
                        head/tail truncation it passes through, and the fail-open write the whole of it rides
    usage/              the provider payload parsers, publishing the parser surface and the result types it returns
                        (`__all__`): token and cost metering, skill evidence, and per-run trajectories, one family
                        per backend over a shared JSONL vocabulary and the first-party rate tables
    dashboard/          the Streamlit analytics page: the visual theme both pages are drawn in, the window and
                        filters one run of it carries, the two waves a load is staged into with the read adapters
                        they are made of, the banners and headline numbers drawn between them, and the panels,
                        tables, and inline markup the rest of the page is
      charts/           the Plotly figures those reads are drawn as: what every family is built out of, the frame
                        the horizontal cost families share, the weekday-by-hour grid and the per-day throughput
                        strip, and the usage hero figure
    trajectory_viewer/  the file-backed trajectory page: the read model over the sink's JSONL, the filters and
                        totals a page narrows it to, the inline HTML it is drawn as, and the controls, picker, and
                        rendering one run of the page is driven by
  apps/                 the two `streamlit run` targets, one per page — the analytics dashboard and the trajectory
                        viewer — over the standard-library `sys.path` shim a script launch needs; the polling loop
                        is launched at `cli.py` instead
```

## How these packages depend on each other

- Inside `analytics/`, the environment parse and the configuration view over the holder it fills are the bottom, and
  the shared sink sits above both write packages: it imports neither `recording/` nor `trajectories/`, so an
  `agent_exit` composing a trajectory write reaches the envelope and the line above both rather than back through the
  recorders that called it, and the direction runs one way — recording names the trajectory writers, never the
  reverse. Each sink's lock is minted on that shared owner once per process, which is what makes an append and the
  prune that rewrites the file under it serialize against each other without either sink blocking on the other's
  file.
- `query/` and `sync/` both keep psycopg behind a call — the read path defers the driver import to its connect
  factory, the replay keeps it inside the two adapters a caller may replace — so the result models, the row layout,
  and the content hash a replay deduplicates on are all usable on a machine with no driver installed.
- `dashboard/` composes downward and nothing reads back up. The controls normalize a run's selections into the
  filters and the pair of cache keys both waves are bound to, and a panel is the card and the figure together: a
  section names its own builder under `charts/` rather than being handed a chart handle. The style owners are read
  back under one name, and a page passes that object down to the sections whose own arithmetic needs a hue or a
  formatter; the sections drawn from a figure or a hand-rolled table take none, since the chart family reads its
  hues off the palette owner directly and the table markup is painted by the stylesheet the page injects. Under
  `charts/`, a family names only the style owners, its own siblings, and the `query/` result model its rows arrive
  as.
- `trajectory_viewer/` runs the same way: the parse sits above the record and the views bound onto it, the file read
  above the parse, and the filter, summary, and markup owners open nothing. Which file a read opens comes off the
  settings holder the page hands down rather than one an owner captured, and nothing here imports Streamlit — the
  owners that draw take it in as an argument.
- The two `streamlit run` targets are the one launch path each page has and own nothing the page decides:
  everything they compose is imported inside the pass that reaches it, Streamlit and pandas included, so importing
  an app costs the `sys.path` shim and nothing else.
