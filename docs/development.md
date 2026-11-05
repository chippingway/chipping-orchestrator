---
description: >-
  Developer-only source checkout setup, direct launch commands, the restart wrapper, optional analytics tools, and the
  parser fuzz targets.
---
# Developer guide

Source checkouts and direct poller launches are for developing chipping-orchestrator. To install and operate a
published release, use the [pipx quick start](../README.md#quick-start) and [configuration reference](configuration.md).
The [contribution guide](../CONTRIBUTING.md) covers branches, checks, pull requests, and maintainer releases; the
[develop skill](../.agents/skills/develop/SKILL.md) carries the detailed coding conventions.

## Source checkout setup

Use Linux, Git, Python 3.12 or newer, and Poetry 2.5.1:

```sh
pipx install "poetry==2.5.1"
git clone https://github.com/chippingway/chipping-orchestrator.git
cd chipping-orchestrator
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync
cp orchestrator/service/.env.example .env
```

Both templates are package data under `orchestrator/service/`: `.env.example` is the basic one and
`.env.example.advanced` holds the optional overrides and the developer settings. Those two files are the only copies,
and the built distributions ship them, so edit them there. Keep an existing `.env` when updating a checkout. Edit the
checkout's `.env` following [basic setup](configuration.md#basic-setup): set `REPOS`, `ALLOWED_ISSUE_AUTHORS`,
`HITL_HANDLE`, and any agent overrides.
Live runs act on real GitHub issues and can start agents, so use a dedicated test repository. Tokens belong in
`~/.config/<owner>/<repo>/token` or the launch environment, as described in the
[credential reference](configuration.md#github-personal-access-token). A source checkout reads the same token file as
an installed package, so [`set-token`](configuration.md#storing-a-token-with-set-token) runs from one too:
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m orchestrator set-token <owner>/<repo>`.

A verified source checkout reads only its own root `.env`; the installed command reads
`~/.config/chipping-orchestrator/.env`. Process environment overrides win in both cases. With `REPOS` unset or blank,
only a verified source checkout can use the
[developer fallback settings](configuration.md#developer-fallback-and-target-checks) to manage the orchestrator's
own repository or a fork. The default source-checkout log directory is `<checkout>/logs`.

Whether the package runs from a source checkout is read at the root of the package that is running: an ordinary
clone, a linked worktree, or an editable install of either is one, and an installed package stays installed even when
launched from inside a checkout. Setup that writes the installed `~/.config/chipping-orchestrator/.env`, such as
`chipping-orchestrator configure` or `add-repo`, therefore refuses to run from a source checkout, which would never
read that file.
Its message names the checkout's own `.env`, this guide, and the checkout's `run.sh`: set the `.env` up as above and
launch with the [restart wrapper](#development-restart-wrapper). The checks and clone defaults that setup applies are
under [setup checks](configuration.md#setup-checks-and-clone-defaults).

Run Poetry sync in each fresh worktree before checks. Add `--with docs`, `--with dashboard`, or `--with docs,dashboard`
when the change needs those optional groups, and `--with fuzz` for the [fuzz targets](#fuzzing-the-parsers). Clear
`VIRTUAL_ENV` and `CONDA_PREFIX` for every manual Poetry command; the
[dependency tooling reference](configuration/operations.md#dependency-tooling) explains why.

## Direct launch commands

Run from the checkout with its Poetry environment:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m orchestrator run --once
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m orchestrator run --log-level DEBUG
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m orchestrator run --cleanup-terminal-artifacts
```

`run --once` performs a real polling tick, including label setup and possible agent launches. The cleanup mode reclaims
eligible worktrees and branches without polling issues or writing workflow state; its gates and remote deletions are
under [run modes](configuration.md#run-modes).
The module form and `poetry run chipping-orchestrator` both call `orchestrator/cli.py`; a bare launch of either
prints the help listing every command and exits 0.

For a local startup-settings check without connecting to GitHub:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -c \
  'from orchestrator.runtime.startup import require_issue_authors; require_issue_authors(); print("Configuration OK")'
```

This checks local settings, targets, and the required author allowlist; agent authentication, token permissions, and
live workflow-state compatibility still need checking separately.

## Development restart wrapper

```sh
./run.sh
```

The wrapper launches `python -m orchestrator run` with its own arguments, so `./run.sh --log-level DEBUG` passes the
flag to `run`. It continuously polls and relaunches after every exit except a signal stop. Before each launch it
attempts `git pull --ff-only origin "$ORCHESTRATOR_BASE_BRANCH"` (default `main`) and refreshes dependencies. A non-base
checkout skips the pull; a failed fast-forward warns and launches the existing working tree. A self-modifying merge
can therefore restart the checkout on new code. See the [process model](architecture.md#process-model) for the full
skip-and-warn contract. Installed packages change version only through an explicit pipx upgrade or reinstall.

A non-base branch does not hold a checkout at a selected revision on its own: the Python loop's self-restart guard
still ends the poller before each polling pass once `origin/<ORCHESTRATOR_BASE_BRANCH>` has moved past the running
commit with changes under `orchestrator/`, and the wrapper then relaunches it every second without it ever polling.
To deploy a revision that cannot read the work the checkout's poller owns, follow
[deploying without migration](configuration/operations.md#deploying-without-migration), which stops and holds the
wrapper and its supervisor, keeps that work away from the new revision, and names as `ORCHESTRATOR_BASE_BRANCH` a
local branch whose name matches no ref on `origin`, branch or tag, and none of the checkout's own `origin/` tracking
refs -- the wrapper's pull resolves a tag of that name as readily as a branch, and the guard reads a stale tracking ref
as readily as a live one -- so the pull leaves the checkout where it is and the guard never asks to restart.

Run one wrapper per checkout: dependency refreshes can replace packages while other Python processes use the same
`.venv/`. Additional wrappers need separate checkouts and `.venv/` environments, with the same explicit
`WORKTREES_DIR` when coordinating on one host; see
[running more than one poller](configuration/operations.md#running-more-than-one-poller). Invalid settings or targets
cause repeated startup errors because the wrapper retries failed starts after one second.

Ctrl+C or `SIGTERM` stops the wrapper and its orchestrator process (`128 + signum`, without a restart). A second
Ctrl+C terminates immediately. Edit the checkout's `.env`, wait until no agent child is running, stop the wrapper,
and run it again to apply settings. `ORCHESTRATOR_BASE_BRANCH` is read before the wrapper's loop and requires
restarting the wrapper itself.

A self-update never reloads the wrapper either: bash keeps the loop of the `run.sh` it started with. A wrapper
started from a checkout whose `run.sh` still launches the bare `python -m orchestrator` keeps doing so after it pulls
the `run` form, and every launch then prints help and exits 0, which that wrapper relaunches each second without
polling. Stop such a wrapper and start it again once the pull has landed.

For a systemd-supervised development checkout, write a unit like the one `init` installs for a
[user service](configuration.md#running-under-systemd-user-service), since `init` refuses a source checkout: set
`WorkingDirectory=/path/to/chipping-orchestrator`, `ExecStart=/path/to/chipping-orchestrator/run.sh`, and include
the directory containing Poetry on the unit's `PATH`. `SIGTERM` from `systemctl stop` propagates through the wrapper,
which exits without relaunching; source updates are handled by the wrapper. Manage that unit with `systemctl --user`:
the service commands act on the unit `init` installs, and `start` and `restart` check an installed package's setup.

### Launcher dependency refresh

Before each Python launch, `run.sh refresh_dependencies` compares the current `pyproject.toml` and `poetry.lock` git
blob IDs with the successful install stamp in `.venv/.poetry-dependencies`. A missing or mismatched stamp runs
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry install --no-interaction`. Only a successful install records the IDs.
New environments and rollbacks are checked even when the pull brings no changes.

The timeout sends SIGTERM to Poetry after 300 seconds, then SIGKILL 10 seconds later if needed.
`timeout --foreground` keeps the installer in the wrapper's process group so signals stop both together, but its
timeout signals do not cover Poetry's child processes. After a timeout, stop the wrapper and any surviving build
processes before repairing or syncing the environment. Stop other processes using the checkout's `.venv/` before a
manual install or sync too.

The additive install preserves installed optional groups and packages removed from the lock. Packages exclusive to
an optional group keep their installed versions until a sync selects that group. To upgrade those packages and
remove obsolete ones, sync with every desired group selected, for example
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`. A failed refresh or unwritable stamp warns,
launches the available environment, and retries on each restart until it succeeds.

### Poetry migration for source checkouts

Install Poetry 2.5.1 and put it on the development service's `PATH`. Stop the service, remove the checkout's `.venv/`,
and recreate it with `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync`, selecting any required optional groups.
Replace `uv run` in checkout crontabs and units with Poetry commands or absolute `.venv/` executable paths, then
restart the wrapper so its shell functions come from the updated `run.sh`.

For verification of this repository, update `VERIFY_COMMANDS` too. Fresh issue worktrees need a sync before checks:

```dotenv
VERIFY_COMMANDS=env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --no-interaction && env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m pytest -q;env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run ruff check orchestrator tests
```

Add optional groups to the sync when checks need them. Venv-based targets need absolute executable paths or explicit
activation in their verification commands. Create `workflow:python:pip` before Dependabot's next run, keeping
`workflow:python:uv` on historical PRs; a fresh repository also needs `workflow:dependencies` and
`workflow:github_actions`.

To roll back the source-tooling migration, revert it, stop the service, remove `.venv/`, recreate it with
`uv sync --locked`, restore the crontab, unit, and verification commands, then restart. This does not change the
package-user pipx workflow.

## Analytics tools

Analytics sync and trajectory pruning run directly from the installed pipx environment without a source checkout;
the [sync operator workflow](observability/analytics-database.md#operator-workflow) and
[trajectory operator workflow](observability/trajectories.md#trajectory-operator-workflow) carry commands and
scheduling. The two Streamlit pages need the optional `dashboard` dependencies, which pipx does not install.
Use a separate checkout environment for the pages; follow the [observability reference](observability.md) for
their data contracts. Do not access or change `analytics-db/data/`; it is operator-owned runtime data.

Keep this checkout dedicated to tools: do not run a poller here, including `run --once` or `run.sh`. The `.env`
settings below point at the packaged poller's log files; a poller in this checkout would write to them too, and
`TRAJECTORY_LOG_PATH` also enables trajectory writing.
In the tools checkout's `.env`, leave `REPOS` blank or configure an existing clone, since the tools validate
repository targets at startup.

### Analytics sync and dashboard

Ask the operator to provision the [analytics database](observability.md#analytics-database-analytics-db). Point the
tools at the packaged poller's existing JSONL file and the database with absolute paths in the checkout's `.env`:

```dotenv
ANALYTICS_LOG_PATH=/home/<user>/.local/state/chipping-orchestrator/logs/analytics.jsonl
ANALYTICS_DB_URL=postgresql://orchestrator:orchestrator@127.0.0.1:5432/orchestrator_analytics
```

For local-only Postgres, storing the database password in the checkout's `.env` as part of `ANALYTICS_DB_URL` is
acceptable: that credential is scoped to the analytics database and never grants write access to GitHub.

Replay the file into Postgres using the installed package's
[sync command](observability/analytics-database.md#operator-workflow), or use this checkout's module command when
developing the sync. Install the optional dashboard group and launch the page:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m orchestrator.observability.analytics.sync.cli
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run streamlit run orchestrator/apps/analytics_dashboard.py
```

For a one-off replay, add `--log-path /path/to/rotated.jsonl --db-url postgresql://other/db` to the sync command.
Inserts dedupe by `content_hash`, so replay is idempotent. Streamlit prints a `http://localhost:8501` URL.
Rerun the sync to pick up new records; relaunch the page after changing `ANALYTICS_DB_URL` or
`DASHBOARD_PARALLEL_READS`, since those values are read once per process. Neither tool affects workflow state.

Unattended replay uses the installed environment as described in the
[operator workflow](observability/analytics-database.md#operator-workflow). Do not sync or replace the dashboard
environment while a page or development replay is running.

### Trajectory viewer

Set `TRAJECTORY_LOG_PATH` in the checkout's `.env` to the absolute JSONL file written by the poller, or a mirrored
copy, then launch:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run streamlit run orchestrator/apps/trajectory_dashboard.py
```

The viewer reads the file directly, without Postgres or analytics sync. The
[trajectory reference](observability/trajectories.md#trajectory-operator-workflow) explains mirroring and retention.

Trajectory retention is not automatic in the polling loop. Run the packaged prune helper using the
[trajectory operator workflow](observability/trajectories.md#trajectory-operator-workflow), while the poller is stopped
or guaranteed not to append trajectories.

## Fuzzing the parsers

Two [Atheris](https://github.com/google/atheris) targets under `fuzz/` fuzz the readers that untrusted text reaches
first. `pinned_admission_fuzzer` hands `PinnedAdmission.admit` in `orchestrator/github/pinned_state.py` one comment
body at a time, and `manifest_fuzzer` hands `_parse_manifest` one decomposer reply: its owner,
`orchestrator/workflow/stages/decomposition/manifest.py`, with `validation.py` and `child_validation.py` behind it.
Each entry script instruments every `orchestrator` module it imports and runs the real owner; the target logic beside
it, `fuzz/pinned_admission.py` and `fuzz/manifest_reply.py`, imports without Atheris, so the default suite replays the
seeds through it too.

A target holds its reader's answer to the reader's contract rather than to a copy of the reader:

- **Admission** ([C-03](contracts.md#c-03-persisted-and-externally-consumed-formats),
  [C-04](contracts.md#c-04-authentic-state-and-trusted-input)). Another author, a comment with no author, and a reader
  with no trusted account authenticate nothing. An authenticated comment is the whole-comment marker, and it is
  admitted only as a JSON object carrying the integer `schema_version` 1; a missing, boolean, float, string, or other
  version is refused, and an undecodable payload is refused as malformed. Every admitted record, and a record quoting
  the input as a key, a list member, and a value, are written back through `pinned_state_body` in both renderings and
  read back as themselves, whatever markers and terminators they carry.
- **Manifests** ([C-08](contracts.md#c-08-agent-reply-protocols)). A reply is a manifest, a refusal with a reason, or
  no block at all, and never raises. An accepted manifest closes the reply on its one fence; an accepted split holds to
  the contract `fuzz/split_contract.py` states apart from the validators, its graph walked another way than theirs.
  Written back, an accepted manifest reads back the same; quoted twice, followed by prose, or with each child's
  `depends_on` missing, null, not a list, or holding a boolean, a float, a string, a negative, an out-of-range or
  oversized index, a self-edge, or an edge closing a cycle, it is refused. Those graphs follow the edges, one cycle for
  each distinct edge however often a list repeats it, so the target's own work stays in proportion to the reply and a
  timeout is the parser's.

A refusal the reader documents is a normal answer. A raise, a broken rule (`AdmissionBreach`, `ManifestBreach`), a
`SideEffectError`, a run past the per-input timeout, and a run past the memory limit are findings, and nothing in the
targets catches them. Both targets start from `fuzz/isolation.py`. It refuses an interpreter older than 3.12. It
registers `orchestrator.config` without running its initializer: the pinned-state owner's import runs the
`orchestrator.github` initializer, and its client imports that package, whose initializer asks git about every
configured target and reads every token file, `ORCHESTRATOR_SKIP_DOTENV` notwithstanding. Every input is then parsed
under an audit hook that refuses file opens, directory listings, processes, and connections, letting through only a
read of Python source, which a coverage tracer and a traceback ask for. So a target makes no GitHub call and reads no
runtime state, and the same input always gets the same answer.

### Toolchain and installation

| Piece | Version | Pinned in |
| --- | --- | --- |
| Atheris | 3.1.0 | `poetry.lock`, in the optional `fuzz` group |
| Python | CPython 3.12, 3.13, or 3.14 on Linux x86_64 locally; 3.12.15 in the image | Atheris wheels; `Dockerfile` |
| Poetry | 2.5.1, as in every workflow | `Dockerfile` |
| Base image | `gcr.io/oss-fuzz-base/base-builder-python` with clang 22 on Ubuntu 20.04 | `Dockerfile`, by digest |
| PyInstaller | 6.10.0, the base image's own pin | `build.sh` |
| coverage.py | 6.3.2 in coverage builds, which the base runner reads | `build.sh` |

The `Dockerfile` and `build.sh` are the two under `.clusterfuzzlite/`.

Atheris 3.1.0 publishes CPython 3.12, 3.13, and 3.14 wheels for Linux x86_64 and no source, so the `fuzz` group
installs on that combination alone; anywhere else, use the [image](#reproducing-in-the-fuzzing-image). The wheel
carries its own libFuzzer. A default `poetry sync` leaves the group out and removes it again, so neither CI nor a
published distribution ever installs Atheris. Install it and check what resolved:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with fuzz
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -c \
  'import atheris, importlib.metadata as m, sys; print(sys.version, "atheris", m.version("atheris"))'
```

Run the targets from the checkout's root, where `python -m fuzz.<target>` finds the `fuzz` package.

### Seeds, limits, and dictionaries

Each target's seeds are small synthetic files in `fuzz/corpus/<target>/`, one case each and named after it: supported
records and split manifests, truncation, malformed JSON, unexpected JSON types, Unicode, nesting, large numeric
literals, marker, terminator, and fence boundaries, and invalid dependency graphs.
[`../tests/repository/test_fuzz_targets.py`](../tests/repository/test_fuzz_targets.py) replays every one and fails
when the corpus stops reaching an admission status, a version refusal, the over-ceiling rendering, or a manifest
outcome. `.gitattributes` keeps the seeds byte for byte, CRLF ones included, and a seed is a text file held to the
120-character line limit unless a line is one unbroken token or the file carries a NUL byte.

`fuzz/<target>.options` holds the libFuzzer limits the runner applies: inputs up to 65536 bytes (`max_len`), 2048 MiB
of resident memory (`rss_limit_mb`), and 10 seconds an input (`timeout`). Inside those limits nothing is filtered: a
malformed, truncated, or oversized input is parsed whole. `fuzz/<target>.dict` lists the format's tokens. Locally,
pass the limits and the dictionary as flags, as below.

### Replaying seeds and inspecting coverage

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m pytest tests/repository/test_fuzz_targets.py
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m fuzz.pinned_admission_fuzzer \
  fuzz/corpus/pinned_admission_fuzzer -runs=0
```

The pytest module replays the seeds without Atheris and, when the `fuzz` group is installed, runs each entry point
over them too. A replay prints `INFO: Instrumenting <module>` for every module it instrumented, `orchestrator.github`
`.pinned_state` and the three manifest owners among them, and `cov:` with the edges the seeds reach. To see which
lines they reach, run a target under coverage.py, which the `dev` group installs, over the seed directory for exactly
the seeds plus the empty input Atheris always runs first. It then exits through Python, which is what writes the data;
a run handed the seeds as separate files, or `-runs=0`, exits through libFuzzer and writes none:

```sh
seeds=fuzz/corpus/manifest_fuzzer
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m coverage run --branch --data-file=/tmp/manifest.coverage \
  --include='orchestrator/workflow/stages/decomposition/*.py' \
  -m fuzz.manifest_fuzzer "$seeds" -atheris_runs=$(( $(ls "$seeds" | wc -l) + 1 ))
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m coverage report -m --data-file=/tmp/manifest.coverage
```

For the admission target, include `orchestrator/github/pinned_state.py` and use its corpus; the client methods that
walk a thread and write the comment are no part of it. Lines the seeds leave uncovered are what a new seed is for.

### Bounded fuzzing

```sh
mkdir -p /tmp/fuzz-manifest/corpus /tmp/fuzz-manifest/artifacts
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m fuzz.manifest_fuzzer \
  /tmp/fuzz-manifest/corpus fuzz/corpus/manifest_fuzzer -dict=fuzz/manifest_fuzzer.dict \
  -max_len=65536 -rss_limit_mb=2048 -timeout=10 -max_total_time=600 \
  -artifact_prefix=/tmp/fuzz-manifest/artifacts/
```

libFuzzer adds the inputs it finds to the first corpus directory, so the committed one goes second and stays as it
is. `-max_total_time` bounds the run; a finding stops it early and leaves `crash-*`, `timeout-*`, or `oom-*` under
the artifact prefix, outside the checkout. The admission target runs the same way with its own corpus and dictionary.

### Reproducing in the fuzzing image

ClusterFuzzLite builds `.clusterfuzzlite/Dockerfile` with the checkout's root as the context and runs the base image's
`compile`, which runs `.clusterfuzzlite/build.sh`. The root `.dockerignore` makes that context an allowlist: the
`.clusterfuzzlite/`, `fuzz/`, and `orchestrator/` trees and the files Poetry installs from, never a `.env`, a
credential, `.venv/`, caches, logs, worktrees, fuzzer artifacts, or `analytics-db/`, whose `data/` the client never
even lists. [`../tests/repository/test_fuzz_build.py`](../tests/repository/test_fuzz_build.py) builds such a context
with Docker where a daemon answers and checks exactly that. Build, package, check, and run the targets as
ClusterFuzzLite does, with the output directory outside the checkout:

```sh
docker build -t chipping-orchestrator-fuzz -f .clusterfuzzlite/Dockerfile .
mkdir -p /tmp/fuzz-out
docker run --rm -e SANITIZER=address -e FUZZING_ENGINE=libfuzzer -e FUZZING_LANGUAGE=python \
  -e ARCHITECTURE=x86_64 -v /tmp/fuzz-out:/out chipping-orchestrator-fuzz compile
docker run --rm -v /tmp/fuzz-out:/out -e SANITIZER=address -e FUZZING_ENGINE=libfuzzer \
  -e FUZZING_LANGUAGE=python -e ARCHITECTURE=x86_64 gcr.io/oss-fuzz-base/base-runner test_all.py
docker run --rm -v /tmp/fuzz-out:/out -e SANITIZER=address -e FUZZING_ENGINE=libfuzzer \
  -e FUZZING_LANGUAGE=python -e RUN_FUZZER_MODE=interactive gcr.io/oss-fuzz-base/base-runner \
  run_fuzzer manifest_fuzzer -max_total_time=600
```

`compile` leaves each target in the output directory as a PyInstaller binary with its wrapper, beside
`<target>.options`, `<target>.dict`, and `<target>_seed_corpus.zip`; `run_fuzzer` unpacks the seeds and applies the
options. `-runs=0` in place of `-max_total_time` only replays the seeds. `SANITIZER=coverage` builds the coverage
variant, which the base runner's `coverage` command runs over a corpus and whose data it merges; its report step runs
on the runner's own Python 3.11, which cannot parse the 3.12 standard library the targets bundle, so it writes no
report. Read coverage locally, as above, until the runner's Python reaches 3.12.

How the image's pieces relate to the lock:

- **From `poetry.lock`.** `build.sh` checks the lock and runs `poetry sync --only main,fuzz` in the copied checkout,
  so the runtime dependencies and Atheris are the locked versions, hash-checked, and the checked-out revision is the
  installed root package. The `dev` group is not installed.
- **Pinned in the image, outside the lock.** The base image by digest, with clang, the sanitizer runtime the wrapper
  preloads, `llvm-symbolizer`, and the compile scripts; CPython 3.12.15, built from the python.org tarball and refused
  unless its SHA-256 matches; Poetry 2.5.1; PyInstaller 6.10.0, and coverage.py 6.3.2 in coverage builds. Pip
  resolves the dependencies of the last three fresh, and the Ubuntu packages CPython is built against come from the
  base image's archive.
- **Not used.** The base image's own Python 3.11 and Atheris, which are older than this project supports.

To move a pin, change it in the `Dockerfile` or `build.sh`, rebuild, and run the commands above; for CPython, take
the new release's SHA-256 from python.org.

### Minimizing a crash

The packaged binary reruns itself, so minimize in the image:

```sh
cp /tmp/fuzz-manifest/artifacts/crash-<sha1> /tmp/fuzz-out/
docker run --rm -v /tmp/fuzz-out:/out -e SANITIZER=address -e FUZZING_ENGINE=libfuzzer \
  -e FUZZING_LANGUAGE=python gcr.io/oss-fuzz-base/base-runner bash -c \
  'cd /out && ./manifest_fuzzer -minimize_crash=1 -runs=20000 -exact_artifact_path=/out/minimized crash-<sha1>'
```

A local run under `python -m` cannot rerun itself, so reproduce there rather than minimize: hand the target the
artifact alone, which prints the Python traceback or the broken rule.

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m fuzz.manifest_fuzzer /tmp/fuzz-manifest/artifacts/crash-<sha1>
```

### Turning a finding into a regression

1. Reproduce it with the artifact as above, and decide whose it is: a reader answering outside its contract is a
   parser defect, while a target rule the contract does not state is a harness defect.
2. For a parser defect, add a focused test beside the owner, asserting the documented answer for the minimized input
   rather than the absence of a crash: [`../tests/github/test_pinned_state.py`](../tests/github/test_pinned_state.py)
   for admission and serialization, and
   [`../tests/workflow/stages/decomposition/test_manifest.py`](../tests/workflow/stages/decomposition/test_manifest.py)
   for the manifest envelope, decoding, and validators. Watch it fail, then fix the owner. Keep the test small and its
   assertion an answer, never a duration: a timeout or memory finding stays with the targets' limits, and a refusal
   only an interpreter's own bound produces, such as nesting past what its decoder recurses, is asked of a stubbed
   decoder rather than of an input whose fate depends on the interpreter and the stack it runs on.
3. Leave the targets' rules alone unless the contract itself changes, and then change the contract's page and its
   checks with it.
4. Add the input to the target's corpus when it reaches an outcome no seed does, inside `max_len` and readable as
   above, so every later replay keeps it.
