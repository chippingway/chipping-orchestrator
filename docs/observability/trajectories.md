# Agent trajectories

The opt-in, default-off third JSONL sink (`TRAJECTORY_LOG_PATH`) that records what an agent run actually *did* — the
ordered timeline of tool calls, results, and text turns, plus the final output — together with the operator workflow
that mirrors and prunes the file and the dedicated Streamlit viewer that reads it. It is deliberately kept apart from
the numeric [event streams](event-streams.md): the free-text bodies never enter the analytics rollup, the Postgres
sync, or the analytics dashboard.

Read the privacy contract under the [trajectory sink](#trajectory-sink-trajectory_log_path) before enabling it:
redaction masks secret-shaped values, not repository content, so an enabled trajectory file carries the same
sensitivity as the repositories the orchestrator works on. Where the write, prune, and viewer paths sit in the
package tree is in
[`architecture/observability-modules.md`](../architecture/observability-modules.md), at the package boundary; the
knobs are in [`configuration/observability.md`](../configuration/observability.md).

## Trajectory sink (`TRAJECTORY_LOG_PATH`)

A sibling, opt-in JSONL sink for agent *reasoning trajectories* — the ordered timeline of tool calls / results
interleaved with the assistant / user text turns, plus the final output a run produced — written by
`orchestrator/observability/analytics/trajectories/`, its two knobs (`TRAJECTORY_LOG_PATH` /
`TRAJECTORY_RETENTION_DAYS`) parsed alongside the analytics ones by `observability/analytics/environment.py`. It is
kept deliberately **separate** from the analytics sink so the large free-text trajectory bodies never enter the
numeric usage rollup, its Postgres aggregation, or the dashboard.

**Producer: `record_agent_exit`.** After the baseline `agent_exit` analytics record (and the opt-in skill parse) are
produced, `record_agent_exit` calls `trajectories.persistence.maybe_record_trajectory`, which — only when
`TRAJECTORY_LOG_PATH` is enabled —
parses the run's trajectory from the same stdout (`observability/usage/trajectory.py`'s `parse_agent_trajectory`),
redacts and truncates it, and appends one `event="agent_trajectory"` record. `_run_agent_tracked` (in
`workflow/engine/usage.py`) forwards its
orchestrator-built `prompt` so it can land as the redacted `user_input`; `record_agent_exit` also threads through the
`UsageMetrics` it already parsed for the baseline record so the trajectory can carry a denormalized `run_usage` summary
without a re-parse. The whole block rides its **own** inner fail-open `try/except`: a parser, redactor, or sink
failure logs (`log.exception`) and is swallowed, so it can never drop the baseline `agent_exit` usage / cost record or
the `skill_triggered` audit events, all of which were already produced before it runs. With the sink off (the default)
the block is a no-op before any parse work — the prompt is never read into a record and the `agent_exit` shape is
byte-for-byte unchanged. `runtime.ticks.run_tick` does not yet call `prune_trajectory_records`, so trajectory
retention stays operator-driven for now.

**Record shape.** One `agent_trajectory` record per tracked run carries the standard envelope (`ts`, `repo`, `issue`,
`event`, `stage`) plus correlation context (`agent_role`, `backend`, `session_id`, `review_round`, `retry_count`) and
the redacted trajectory: `user_input` (the orchestrator prompt), `system_prompt`, `tools` (the offered-tools set — read
from claude's or agy's stream, and for codex backfilled with `skills.discovery.discover_codex_tools()` as a baseline
since its stream carries no offered-tools frame), `skills_triggered` / `skills_available` (names-only — for codex the
`skills_available` set is backfilled from the out-of-band
`skills.discovery.discover_local_skill_sources(cwd)` filesystem scan, since its stream carries no offered-skills
catalog; the source level that scan also reports rides the `agent_exit` record, not this one), a `run_usage` summary,
a claude-only per-turn `turns` array, a codex-only `source_items` accounting with its `source_item_counts` summary and
`source_items_truncated` flag, an ordered `steps` array (each `{kind, name, tool_id, content}` plus a `turn`
index on the billed steps, where
`kind` is `tool_call` / `tool_result` / `assistant_message` / `user_message` / `unsupported_item` and `content` is the
redacted tool input, tool result, or text turn — `name` / `tool_id` are `null` on the message turns, and an
`unsupported_item` is the metadata-only placeholder a codex item type the parser does not normalize leaves behind,
naming the item type in `name`, its id in `tool_id`, and its reported status in `content` — `null` for an item type
that reports none), and the final `output`. `run_usage`
is the denormalized `UsageMetrics` (`models`, `input_tokens`, `output_tokens`, `cached_tokens`, `cache_read_tokens`,
`cache_write_tokens`, `turns` count, `cost_usd`, `cost_source`) minus `backend` (already on the record) — the run
headline, and the codex surface too, since codex has no per-turn detail. Each `turns[]` entry is one claude assistant
turn (`turn` index, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, and an
always-*estimated* `cost_usd` / `cost_source`); each billed `steps[]` entry (`assistant_message` / `tool_call`) carries
the same `turn` index tying it to its turn, while a `tool_result` / `user_message` step is a turn *input* and omits
`turn`. `build_record` drops every empty / `None` field, so an absent prompt, an empty system prompt, a no-trigger skill
set, codex's empty per-turn array, or a claude run's absent item accounting simply leaves its key off.

**Per-item accounting (`source_items`).** Beside the steps, a codex record carries the parser's [per-item
accounting](usage.md): one `{item_id, item_type, disposition}` row per item the exec stream identified, in first-seen
order. Exactly one of four dispositions is assigned per identified id, which is what makes the rows an accounting
rather than a sample: `stored` (the item's own steps are in `steps`), `unsupported` (nothing normalized its type, so
the `unsupported_item` placeholder step is what names it), `excluded` (the parser holds the item out whole — codex's
`reasoning` today, whose hidden text is exactly what the exclusion exists to keep out, so the row carries its id and
type and nothing else), and `empty` (its frames carried no payload to store — an `agent_message` with no text, a call
whose fields never arrived, or a frame too malformed to name a type at all, whose `item_type` is then the empty
string). It is what an `item_N` coverage audit reads — an id that reached no step is a classification the record names
rather than a silence — and it carries provider-assigned ids and item type names rather than agent-sourced content, so
like `tools` and a step's `name` it is written unredacted; everything an item actually *said* is in the step it
contributed and is redacted there. `source_item_counts` is the always-kept summary beside it: `identified`, then one
count per disposition (zeros included, so the shape is fixed). `identified` counts the ids the stream carried, so a
frame that arrived without one is outside the accounting altogether — nothing correlates it under a name, and its
steps still ride `steps`. `source_items_truncated: true` is written when the budget left room for only a prefix of the
rows — or for none of them, in which case the `source_items` key is absent while the counts and the flag still say how
many items the stream identified. A claude run identifies no codex items, so all three keys are simply absent from its
record.

**Join keys.** The envelope and correlation context double as join keys back to the numeric sinks. `session_id` (the
live `result.session_id`) is the per-run key onto the
[`agent_exit`](event-streams.md#agent_exit-records) analytics record and the
`agent_exit` audit event from the same run — both carry that same result id. The shared context `(repo, issue, stage,
agent_role, backend, review_round, retry_count)` lines up field-for-field with the analytics `agent_exit` record (the
audit events carry the same context under their own names, with backend as `agent`). The paired `agent_spawn` audit
event is **not** keyed by this `session_id`: its `session_id` is the *resume* session id, which is omitted entirely on a
fresh spawn and points at the prior session on a resume — so correlate the trajectory to the spawn through that shared
context, not `session_id`. Either way the heavy free-text trajectory body can be correlated back to the usage / cost /
token row for the same run without ever being stored alongside it — the whole point of keeping it in a separate file.

**Redaction and truncation caps.** Every free-text field — `user_input`, `system_prompt`, each step's `content`, and
`output` — is passed through `config.credentials.redact_secrets` (the same secret-shaped-env-value masker used on
agent stderr) **before** truncation, so a secret straddling an elided boundary cannot survive as two halves. Each field
is then head/tail truncated to its first `TRAJECTORY_FIELD_HEAD` (`2000`) and last `TRAJECTORY_FIELD_TAIL` (`2000`)
characters — declared by `trajectories/models.py`, which is where a caller shrinks one, and snapshotted once per
record — with an `...[N chars elided]...` marker in between; the head keeps the
request/intent, the tail the
result/answer. The whole record is additionally bounded: each step is charged its full **serialized** size — the JSON
metadata (`kind` / `name` / `tool_id` / `turn`) plus its truncated content, not just `len(content)`, so even thousands
of empty- or metadata-only steps still consume the budget — and the per-turn `turns` array and the `source_items`
accounting are charged **and truncated** against the same budget (turns first, then the accounting, then the steps),
so a pathological claude run of thousands of
turns with no tool calls cannot write the whole array in full and blow the budget. Once the running total crosses
`TRAJECTORY_RECORD_BUDGET` (`200_000`) bytes the remaining turns — then accounting rows, then steps — are dropped and a
`truncated: true`
flag is set; only the two small fixed summaries are always kept whole (`run_usage` and `source_item_counts`), so one
pathological run (thousands of turns
or tool calls) cannot write an unbounded line. The draw-down order is what keeps the accounting readable on exactly the
runs that overran: the ids an `item_N` audit needs outlive the steps they account for, and when the budget reaches the
rows themselves `source_items_truncated` says the surviving ids are a prefix rather than the whole set. Non-string step
content (claude tool inputs are dicts; `tool_result`
content a list) is redacted **leaf-by-leaf before** JSON serialization (`sanitize.redact_tree`) — serializing first
would escape a multiline secret's newlines into `\n`, leaving the literal `str.replace` in `redact_secrets` unable to
match the raw env value, so the secret would leak into the serialized content.

**Privacy contract — redaction is not anonymization.** The redactor masks only *secret-shaped* values: env vars whose
name is in the secret-key set or ends in a secret suffix, plus the resolved `GITHUB_TOKEN`, each verbatim occurrence
replaced with `***`. It deliberately does **not** strip issue or repository content. The prompt (`user_input`), the
`system_prompt`, every step's `content` in `steps` (tool inputs / results and the assistant / user text turns), and the
final `output` can — and routinely will — carry issue titles and bodies, quoted source from the worktree, file
paths, diffs, the MCP tool arguments a codex run issued together with whatever those servers answered, the
web-search queries it ran, the plan a codex run wrote for itself and the paths each of its patches touched, and the
agent's own text turns, all in cleartext after redaction. Two payloads a stream carries stay out of the record: a
codex `reasoning` item never enters it — the accounting names that id and its type and nothing else, never the hidden
text — and a web search records the query and the `action` it resolved to but no result body, because the stream
carries none and nothing reconstructs one. An enabled trajectory file therefore
carries the same sensitivity as the repositories the orchestrator works on; scope its filesystem permissions (and any
retention) accordingly. This is why the sink is off by default and why it never leaves the local filesystem (next
paragraphs).

**Opt-in, default off.** Unlike `ANALYTICS_LOG_PATH` (which defaults to `<LOG_DIR>/analytics.jsonl`),
`TRAJECTORY_LOG_PATH` defaults *off*: unset, empty, or `off` / `disabled` / `none` (case-insensitive) all disable it;
any other value is the explicit opt-in path. `TRAJECTORY_RETENTION_DAYS` defaults to `90` and mirrors
`ANALYTICS_RETENTION_DAYS` (non-positive keeps trajectories indefinitely).

**Append / prune discipline, dedicated lock.** `append_trajectory_record` reopens the file in append mode per record
after `mkdir(parents=True, exist_ok=True)`, downgrading `OSError` to a `log.warning`; `prune_trajectory_records(*,
now=None)` removes records older than `TRAJECTORY_RETENTION_DAYS` through a temp-file + `os.replace` rewrite, preserves
malformed / unparseable lines verbatim, and no-ops when the sink is disabled, retention is non-positive, or the file is
absent. Both reuse the shared append (`analytics/sink.py`) and prune (`retention_scan.py` / `retention_rewrite.py`)
cores but hold a **dedicated**
`threading.Lock`, so the trajectory file serializes its own append-vs-prune race without ever blocking against — or
touching — `ANALYTICS_LOG_PATH`, the analytics Postgres sync, or the dashboard. That lock is minted on
`analytics/sink.py`, beside the analytics sink's and for the same reason: an append and the prune that rewrites the
file under it are safe only while both hold one object, and a caller is free to hold an `append_trajectory_record` it
took off the owner rather than call through a package. A lock minted beside the append would leave that reference
serializing against nothing while the prune took another, which is precisely the append-during-prune race the lock
exists to close.

**No built-in rotation.** As with the audit and analytics sinks, each append reopens the file after `mkdir`; there is no
size cap, long-lived descriptor, or compression. `prune_trajectory_records` is **not yet wired into the polling loop**,
so beyond the by-age prune (which only an in-process caller drives today) retention and rotation are entirely
operator-managed — pair `TRAJECTORY_LOG_PATH` with `logrotate` (or equivalent). Because every append re-resolves the
path, create/rename or `copytruncate` rotation is safe between writes.

**Local filesystem only.** A trajectory record is never written to `ANALYTICS_LOG_PATH`, never replayed into Postgres by
the sync (which only reads `ANALYTICS_LOG_PATH`), and never surfaced in the **analytics** dashboard
(`orchestrator/apps/analytics_dashboard.py`), which renders only the Postgres rollup. The sink is one JSONL file on
local disk; the
only reader is the dedicated trajectory viewer below, which reads that file straight off disk.

**Observation-only, like every surface here.** The polling tick never reads the trajectory file back and no dispatch
decision keys off it; workflow state lives entirely in the pinned `<!--orchestrator-state ...-->` JSON comment and the
workflow label. The file is therefore safe to truncate, rotate, or delete at any time without affecting workflow state
or correctness.

### Trajectory operator workflow

There is no trajectory equivalent of `python -m orchestrator.observability.analytics.sync.cli`: trajectories are
deliberately file-backed only, and the analytics Postgres schema does not ingest their free-text bodies. To browse
trajectories on another host, mirror `TRAJECTORY_LOG_PATH` as a file and run the dedicated viewer on that host with
`TRAJECTORY_LOG_PATH` pointing at the mirrored JSONL. Scope the remote path like source code or issue content:
redaction masks secret-shaped values, not repository text or the agent's own text turns.

For an unattended deployment, mirror the file with SSH-based tooling such as `rsync`. Use a dedicated receiver account
whose key can only write into the trajectory directory. On an Ubuntu receiver, use a neutral shared directory such as
`/srv/orchestrator` instead of landing the file in the receiver user's home. That keeps `/home/forsync` out of the
dashboard read path and lets the Streamlit user read through a shared group:

```sh
# On the remote VPS.
sudo adduser --system --group --shell /bin/bash --home /home/forsync forsync
sudo groupadd -f orchestrator
sudo usermod -aG orchestrator forsync
sudo usermod -aG orchestrator <dashboard-user>
sudo mkdir -p /srv/orchestrator
sudo chown forsync:orchestrator /srv/orchestrator
sudo chmod 2750 /srv/orchestrator
sudo install -d -m 700 -o forsync -g forsync /home/forsync/.ssh

# Confirm rrsync is available; on current Ubuntu it is shipped by rsync.
command -v rrsync
```

Generate a dedicated cron key on the source host:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/forsync_ed25519 -C "trajectory-sync" -N ""
```

Then install the public key on the remote account as one `authorized_keys` line. Pick the network restriction that
matches the deployment:

- **Private overlay / Tailscale available.** Use the exact source host tailnet IP in `from=` when possible;
  `100.64.0.0/10` is the broader Tailscale CGNAT range. A tailnet ACL that allows only the source device to reach SSH on
  the VPS is stronger, with `from=` as defense-in-depth.
- **Public SSH / no Tailscale.** Use the source host's stable public egress IP or CIDR in `from=` instead. If the source
  IP is not stable, omit `from=` and restrict port 22 at the VPS firewall / cloud security group to the narrowest source
  range you can. Keep the forced `rrsync` command and `restrict` either way.

```text
command="/usr/bin/rrsync -wo -no-del /srv/orchestrator",restrict,from="<source-ip-or-cidr>" ssh-ed25519 AAAA... trajectory-sync
```

Lock the SSH account down further with `/etc/ssh/sshd_config.d/forsync.conf`:

```sshconfig
Match User forsync
    AuthenticationMethods publickey
    PasswordAuthentication no
    PermitTTY no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
```

Validate and reload SSH:

```sh
sudo sshd -t
sudo systemctl reload ssh
```

A small source-side wrapper is easier to test than a heavily-quoted crontab line, lets cron fail fast when SSH would
otherwise prompt, and uses the same lock name as trajectory maintenance jobs so sync and prune never overlap each other.
With the `rrsync` root above, `DEST=forsync@<host>:trajectories.jsonl` lands at `/srv/orchestrator/trajectories.jsonl`
on the receiver. `rrsync` rejects absolute destination paths; keep the destination relative to its configured root:

```sh
#!/usr/bin/env bash
set -euo pipefail

SRC=/path/to/chipping-orchestrator/logs/trajectories.jsonl
DEST=forsync@<host>:trajectories.jsonl
LOCK=/tmp/chipping-orchestrator-trajectory.lock
KEY=/home/<local-user>/.ssh/forsync_ed25519

SSH_CMD="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"

echo "=== $(date -Is) trajectory sync start ==="
if /usr/bin/flock -n -E 75 "$LOCK" \
  /usr/bin/rsync -az --timeout=120 --chmod=F640 \
    -e "$SSH_CMD" \
    "$SRC" "$DEST"; then
  echo "=== $(date -Is) trajectory sync done ==="
else
  rc=$?
  if [ "$rc" -eq 75 ]; then
    echo "=== $(date -Is) trajectory sync skipped: lock held ==="
    exit 0
  fi
  exit "$rc"
fi
```

Install it as executable before adding the cron entry:

```sh
chmod +x /path/to/chipping-orchestrator/bin/sync-trajectories.sh
```

```cron
10 * * * * /path/to/chipping-orchestrator/bin/sync-trajectories.sh >> /path/to/chipping-orchestrator/logs/trajectory-sync.cron.log 2>&1
```

- `rsync` is a file mirror, not an append-only archive. When local retention later rewrites or shrinks the JSONL, a
  later mirror run will make the remote file match.
- The default `rsync` destination update path already writes a temporary file and renames it into place for this
  single-file mirror; avoid `--inplace`.
- Do not use `--append` or `--append-verify` for this mirror: retention pruning can shrink or rewrite the source file,
  and append-mode transfer would leave stale remote tail data or give remote readers partial in-place writes.
- `StrictHostKeyChecking=accept-new` is convenient on a trusted private network because the first cron-run pins the host
  key and later key changes still fail. The stricter alternative is to pre-seed once with `ssh-keyscan -H <host> >>
  ~/.ssh/known_hosts` and drop that option.
- `--chmod=F640` makes the mirrored file readable by the receiver owner and the shared `orchestrator` group. The setgid
  bit on `/srv/orchestrator` (`2750`) keeps replaced files in that group, so the dashboard user can read them after a
  fresh login / restarted service picks up its new group membership.
- If you migrate from an older `/home/forsync/...` landing path, move the existing file once (`sudo mv
  /home/forsync/chipping-orchestrator/trajectories.jsonl /srv/orchestrator/`) and then apply `sudo chgrp orchestrator
  /srv/orchestrator/trajectories.jsonl && sudo chmod 640 /srv/orchestrator/trajectories.jsonl`.
- Verify dashboard readability before launching Streamlit: `id` for the dashboard user must show `orchestrator`, and
  `sudo -u <dashboard-user> head /srv/orchestrator/trajectories.jsonl` should print JSONL.
- If the remote host should keep a longer archive than the local machine, mirror to dated snapshots instead of one fixed
  destination path.
- Treat the remote SSH key as sensitive. For a write-only receiver, constrain it in `authorized_keys` with a forced
  `rrsync` command, no PTY / forwarding, and either a `from=` source restriction or network-level SSH allowlist.
- Rotate `trajectory-sync.cron.log`, or send the wrapper output to the journal with `logger`, so the cron log does not
  grow forever.

The mirror cron does not lock the source file against the running orchestrator. A record that is fully appended before
`rsync` reads the file is copied; a record appended during or after the transfer may be absent until the next mirror
run. If `rsync` ever catches a final line mid-write, the remote file may briefly end with a malformed JSON line after
the destination rename; the trajectory reader skips malformed lines, and the next mirror run repairs the fixed
destination because this command mirrors the whole file rather than using `--append`.

Decide whether the remote file is a **mirror** or an **archive** before enabling retention. A fixed destination path is
a mirror: after local retention prunes old records, the next sync shrinks the remote file too. That is correct for a
remote viewer that should show only the retained window, but wrong if the remote host is meant to preserve history
before the local file is pruned. For an archive, use a different strategy, such as dated snapshots, a never-pruned local
archive file, or a custom high-water-mark shipper.

Because `prune_trajectory_records()` is not called by the polling loop, drive trajectory retention explicitly when you
want `TRAJECTORY_RETENTION_DAYS` to affect the file. The value may live in `.env` like the other non-secret knobs; it is
parsed when the prune process first reads a knob off `observability/analytics/settings.py`, which the entry point
below resolves inside the call. The cron entry relies on `.env` for both
`TRAJECTORY_LOG_PATH` and `TRAJECTORY_RETENTION_DAYS`, runs the prune helper, and logs how many records were removed:

```cron
25 0 * * * cd /path/to/chipping-orchestrator && /usr/bin/flock -n -E 75 /tmp/chipping-orchestrator-trajectory.lock /home/<user>/.local/bin/uv run python -c 'from orchestrator.observability.analytics import retention; print(f"trajectory prune removed {retention.prune_trajectory_records()} record(s)")' >> /path/to/chipping-orchestrator/logs/trajectory-prune.cron.log 2>&1
```

To make the same cron entry use a one-off retention window instead of `.env`, prefix the command with `env
TRAJECTORY_LOG_PATH=/path/to/chipping-orchestrator/logs/trajectories.jsonl TRAJECTORY_RETENTION_DAYS=30`.

Only run this prune command while the orchestrator is stopped or otherwise guaranteed not to append trajectories. The
shared `/tmp/chipping-orchestrator-trajectory.lock` serializes operator cron jobs with each other, but not with the live
orchestrator process: the lock the append and the prune share (minted on
`observability/analytics/sink.py`) is a process-local `threading.Lock`, not an interprocess file lock. An
external prune process can race with the live polling process and lose a record appended to
the old inode between the prune read and `os.replace`. Schedule pruning after at least one mirror run if the remote
fixed-path mirror should receive records before they age out locally. The prune rewrites only the trajectory JSONL
through the same temp-file + `os.replace` path described above; it never touches GitHub workflow state,
`ANALYTICS_LOG_PATH`, Postgres, or the analytics dashboard.

### Trajectory viewer (`orchestrator/apps/trajectory_dashboard.py`)

A deliberately **separate** Streamlit page from the analytics dashboard, launched the same way (`uv run streamlit run
orchestrator/apps/trajectory_dashboard.py`, opt-in `dashboard` group). The two pages stay apart on purpose: the
analytics dashboard reads the numeric usage / cost rollup from Postgres, while the viewer reads the JSONL trajectory
file **directly** — the trajectory bodies are never in Postgres — so an operator can browse trajectories with nothing
but the file on disk (no database, no sync).

**Read model (`orchestrator/observability/trajectory_viewer/`).** A pure, import-light, Streamlit-free reader (the
file-backed analogue of `observability/analytics/query/`). Its owners take the analytics settings holder as an
argument rather than resolving one themselves — the page hands down the one it resolves at call time, so a patch on
that holder intercepts every read the page makes. Together they read `TRAJECTORY_LOG_PATH`, parse each
`agent_trajectory`
record into a frozen `TrajectoryRun` (with a normalised `TrajectoryStepView` per step), and expose `read_trajectories`
(newest first by `ts`, file order as the tie-break), `filter_options`, `filter_runs` (repo / backend / agent-role /
stage / issue / free-text-search, every filter conjunctive and an empty multi-value meaning "no constraint", plus an
opt-in `exclude_fixtures`), and `summarize`. Each run exposes a normalised, vintage-agnostic `timeline` — the leading
`user_input` prompt, then the ordered `steps[]`, then the final `output`, as one ordered `TimelineEntry` sequence — so
an old steps-only record (only `tool_call` / `tool_result` steps) and a new record whose steps interleave
`assistant_message` / `user_message` text turns render the same way; `tool_calls` still counts only `tool_call` steps,
so neither the text turns nor an `unsupported_item` placeholder inflates the tally, and a codex plan or patch counts
once — as the single call its frames fold into — rather than once per frame. A step kind the timeline has no
badge for — `unsupported_item` today — falls back to rendering its own kind as the badge text, which is why a new
kind needs no viewer change. `is_fixture` flags the synthetic test-suite records an inherited file may
carry (the sentinel prompt `ignored`, a `sess-*` session id, or a `Skill`-only run), which
`filter_runs(exclude_fixtures=True)` drops. Each run also exposes the record's usage: a `run_usage` (`RunUsageView`) run
summary and a claude-only per-turn `turns` tuple (`TurnUsageView`), with convenience accessors `model` (first of
`run_usage.models`), `cost_usd` / `cost_source` (the authoritative run figure), `total_tokens`, and an O(1)
`usage_for_turn(idx)` lookup so a `TimelineEntry` (which now carries the producing step's `turn` index) can find its
turn's usage while walking the timeline; `summarize` adds `total_cost_usd`, the summed run cost over runs that recorded
one. A pre-usage record parses with `run_usage=None`, `turns=()`, and every `step.turn=None`, so it renders exactly as
before. The codex per-item accounting (`source_items` with its `source_item_counts` and `source_items_truncated`) is
deliberately **not** projected onto `TrajectoryRun`: the viewer renders what a run *did*, while an id-by-id `item_N`
coverage audit is a question for the JSONL file itself, so those three keys ride past the read model untouched. The
`truncated` warning the run card draws speaks of dropped steps for the same reason — the accounting is drawn from the
budget before the steps, so a record that lost accounting rows lost its steps first. The same resilience contract the
rest of the codebase honours holds: a missing / disabled path, a malformed
line, a non-`agent_trajectory` record, or a renamed field yields a smaller result, never an exception. A file that is
there but cannot be read — anything raising an `OSError` other than `FileNotFoundError`, an unreadable file or a
directory in the knob's place — takes the same empty result with a warning first, through the
`orchestrator.trajectory_reader` logger. That name is spelled out literally in
`observability/trajectory_viewer/reading.py` rather than derived from the module path, so an operator's log filter
keeps selecting on it however far the module holding it moves. The records are
already redacted and truncated by the sink, so the viewer is a read-only window onto an already-sanitised file — it
adds no redaction of its own and must be scoped (filesystem permissions, who can reach the Streamlit port) with the same
care as the trajectory file itself.

**Page (`orchestrator/apps/trajectory_dashboard.py`).** Reuses the analytics dashboard's theme (CSS variables, fonts,
`fmt_*` formatters) so the two pages read as one family — the owners under `observability/trajectory_viewer/` name
`dashboard/tokens.py`, `dashboard/css.py`, and `dashboard/formatting.py` directly — and reuses `dashboard/filters.py`'s
`parse_issue_number` for the
issue filter, so `#123` and `123` mean the same thing on both pages. Streamlit is
imported lazily inside `main()`, alongside every owner the page composes, and the repo-root `sys.path` shim comes
from `orchestrator/apps/bootstrap.py` (`ensure_repo_root_on_path`). Importing that module (or the
polling tick) therefore never needs the `dashboard` group — `tests/apps/` guards the lazy-import and the
script-launch `sys.path` shape on the viewer's launch path. The layout is intentionally minimal-but-useful: a
sidebar of filters (plus a *Hide synthetic fixtures*
toggle that drives the reader's `exclude_fixtures`, off by default), a topbar + five-tile KPI strip (runs / issues /
repos / tool calls / total cost, the last summed from `summarize`'s `total_cost_usd`), a foldable *Recorded runs*
overview table (capped at the 200 most recent; collapse the expander to focus on a single run), three cascading run
pickers (repo → issue → the run's `detail_label` cohort — stage/role · backend · round · timestamp) that
together still reach every match, and a per-run detail card that lists the offered tools and triggered / available
skills — the triggered-skills row always renders, marked `none` when no skill fired so a run that used no skill is
distinguishable from an omitted row, while the offered-tools and available-skills rows are dropped when empty — a
run-level usage / cost row (model(s), token buckets, turn count, and the authoritative run cost tagged with
its `cost_source` — the codex surface too), then walks the run's normalised `timeline` as one ordered sequence — the
redacted prompt, then the interleaved assistant / user text turns, tool calls / results, and any
`unsupported_item` placeholder (each rendered by its `kind`), then the final output (rendered as markdown; every
other entry is shown verbatim in a code block). For a claude
run, a compact per-turn usage strip (model · in / out tokens · cache-read / cache-write · estimated cost, with a
*cache hit* chip when the turn read from cache) is drawn at each assistant-turn boundary in the timeline; the copy
states that per-turn figures are claude-only estimates that need not sum to the authoritative run total, and that
entries without a strip (tool results, user turns) are turn inputs billed on the next turn. A pre-usage record carries
no usage, so the row and strips are absent and it renders exactly as before. The fixtures `is_fixture` flags are tagged
in the overview table and the run-level picker (the `[fixture]` prefix rides the run option; and the detail card carries
a notice) so the operator can tell the inherited test-suite records from real runs even with the toggle off. When the
sink is off it renders the opt-in banner and stops; an empty file or an empty filter set renders an explanatory notice
rather than a blank page. That app file is the only launch path the viewer has. The page
owners beneath it take Streamlit in as an argument rather than importing it, so none of them puts the `dashboard`
group behind an import, and the one that reads the trajectory knob reads it off the analytics settings holder the app
hands down — a caller's world is bound for the page the same way it is for the read.
