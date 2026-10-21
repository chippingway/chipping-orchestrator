---
description: >-
  Developer-only source checkout setup, direct launch commands, the restart wrapper, and optional analytics tools.
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
when the change needs those optional groups. Clear `VIRTUAL_ENV` and `CONDA_PREFIX` for every manual Poetry command;
the [dependency tooling reference](configuration/operations.md#dependency-tooling) explains why.

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
