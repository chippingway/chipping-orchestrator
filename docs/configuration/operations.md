# Operations

How the orchestrator is installed, upgraded, checked, launched, supervised, and reconfigured: package installation
and rollback, deploying a build without migration, continuous integration, documentation publishing, run modes, the
systemd user service, and when an edited `.env` takes effect. The environment-variable reference is in
[`../configuration.md`](../configuration.md), which also routes to the observability settings beside this page.

## Package installation, upgrades, and rollback

Install the published PyPI package with [pipx][pipx-installation] 1.16.0 or newer. This minimum supports `pipx pin`
and `pipx unpin`, reuse of saved `--pip-args` during upgrades, and forced installs into existing uv environments
([changelog][pipx-changelog]). Check `pipx --version` and upgrade older pipx before following this guide.
Python 3.12, 3.13, and 3.14 are tested.
Poetry and a clone of the orchestrator repository are only needed for [development](../development.md).
The [maintainer guide](../../CONTRIBUTING.md#notes-for-maintainers) describes release publication.

### Install and configure

```sh
pipx install chipping-orchestrator
pipx ensurepath
```

Open a new terminal after `pipx ensurepath` if the command is not yet on `PATH`. If pipx's default interpreter is
older than Python 3.12, select an installed supported one with
`pipx install --python python3.12 chipping-orchestrator`. pipx keeps the package's dependencies in an isolated
environment and exposes the installed `chipping-orchestrator` command. See the [pipx command reference][pipx-cli]
for installer options.

The forced install examples below use `--python python3.12`; substitute the interpreter used by your installation.
Pass it on every forced install: with the uv backend, `pipx install --force` can reset an existing environment to
pipx's default Python when `--python` is omitted.
Ignore pipx's `--python is ignored when --force is passed` warning for uv-backed environments and keep `--python`.
On pip-backed environments, a forced install never changes the interpreter, even with `--python`; use
[`pipx reinstall --python`](#change-the-python-interpreter) to change it on either backend.

Check the installed version with `pipx runpip chipping-orchestrator show chipping-orchestrator`, then save that
version's templates below and configure the live settings. Keep configuration and logs outside the pipx environment.

<a id="download-the-chosen-releases-files"></a>

#### Save the installed version's templates

The basic template `.env.example` and the advanced template `.env.example.advanced` ship inside the package, under
`orchestrator/service/`, so every installation carries the pair written for its own version and nothing has to be
downloaded or cloned. An upgrade or rollback replaces them along with the package, so save a copy outside the pipx
environment for the configuration comparisons below.

Replace `X.Y.Z` with the installed version, including any prerelease suffix. Run these blocks in the same shell.
The saving block reads both templates from the installed package without loading any configuration, so it works
before `.env` exists, and it stops without writing anything when the installed version is not `X.Y.Z`. Its `-I` keeps
the launch directory off the import path, so a source checkout there cannot stand in for the installed package:

```sh
ORCHESTRATOR_VERSION='X.Y.Z'
ORCHESTRATOR_RELEASE_DIR="$HOME/.local/share/chipping-orchestrator/releases/v${ORCHESTRATOR_VERSION:?}"
ORCHESTRATOR_PYTHON="$(pipx environment --value PIPX_HOME)/venvs/chipping-orchestrator/bin/python"
(
  set -eu
  umask 077
  "${ORCHESTRATOR_PYTHON:?}" -I -c '
import sys
from pathlib import Path

from orchestrator import __version__
from orchestrator.service.templates import TEMPLATES, template_text

version, directory = sys.argv[1:]
if __version__ != version:
    sys.exit(f"the installed version is {__version__}, not {version}")
Path(directory).mkdir(parents=True, exist_ok=True)
for name in TEMPLATES:
    Path(directory, name).write_text(template_text(name), encoding="utf-8")
' "${ORCHESTRATOR_VERSION:?}" "${ORCHESTRATOR_RELEASE_DIR:?}"
)
```

Stop if the block fails. Retain these version-matched files for upgrade comparisons and rollback; their directory
does not select targets or become a launch directory.

Versions up to v0.13.0 do not carry their templates in the package; the saving block fails on them because they have
no `orchestrator.service` module. For one of those, such as the previous version of an upgrade from v0.13.0 or the
recorded version of a [dedicated-venv migration](#moving-from-a-dedicated-venv), download both from the root of its
release tag into the same directory instead:

```sh
(
  set -eu
  umask 077
  mkdir -p "${ORCHESTRATOR_RELEASE_DIR:?}"
  for ORCHESTRATOR_TEMPLATE in .env.example .env.example.advanced; do
    curl --fail --location --output "${ORCHESTRATOR_RELEASE_DIR:?}/$ORCHESTRATOR_TEMPLATE" \
      "https://raw.githubusercontent.com/chippingway/chipping-orchestrator/v${ORCHESTRATOR_VERSION:?}/${ORCHESTRATOR_TEMPLATE}"
  done
)
```

#### Configure live settings

For **first setup only**, `~/.config/chipping-orchestrator/.env` and the token files are written one of two ways.
At a terminal, `chipping-orchestrator init` [onboards](#onboarding-with-init): it asks for each setting, writes them
once the last answer confirms them, and goes on to install the service. Without prompts, write `.env` with
`configure`, naming the top of a local clone of the repository to manage and the GitHub logins whose issues and
comments the orchestrator may act on:

```sh
chipping-orchestrator configure --clone "$HOME/src/acme-api" --authors alice
```

`configure` asks nothing, so a script can run it as well as an operator; onboarding writes `.env` through the same
code, so the same answers write the same file. It writes the basic template the installed
version carries, with `REPOS`, `ALLOWED_ISSUE_AUTHORS`, `HITL_HANDLE`, `DEV_AGENT`, `REVIEW_AGENT`, and
`DECOMPOSE_AGENT` set on the template's own lines and every comment kept, and appends `LOG_DIR` naming the absolute
path of `~/.local/state/chipping-orchestrator/logs`. It creates the configuration directory with mode 0700, as it does
`~/.config` where that is missing, whatever the umask, and writes the file whole, with mode 0600. Only `--clone` and
`--authors` are required; each other option replaces a default:

- `--repo OWNER/NAME` — the repository the clone's GitHub remote names. That remote is `origin` when it points at
  GitHub, otherwise the only remote that does, and the `REPOS` entry then records the remote by name.
- `--base-branch BRANCH` — that remote's default branch as the clone recorded it, otherwise the branch checked out.
  Nothing is fetched. A branch given has to be a name git allows for one.
- `--notify LOGINS` — the `--authors` logins, for `HITL_HANDLE`.
- `--dev-agent`, `--review-agent`, and `--decompose-agent` — `claude`, `codex`, and `claude`. Each has to be
  `claude`, `codex`, or `agy`, with an executable of that name on the `PATH` `configure` runs with.

`--authors` has no default because it decides whose issues and comments the orchestrator trusts. `configure` checks
every answer before it reads the clone for the rest of the entry, and all of it before it writes anything
([setup checks](../configuration.md#setup-checks-and-clone-defaults)). It exits 1 with one message on stderr, having
written nothing, when an answer is refused or the `REPOS` entry cannot carry it, the message naming the option; when
`.env` already exists, since it never overwrites one; and when it runs from a source checkout of the orchestrator,
which reads its own `.env` ([development](../development.md)).
It writes no token into `.env` and loads no configuration, so it runs on a host that has none yet.

`.env` does not expand `$HOME` or `~`, which is why `LOG_DIR` is written as an absolute path. To change it, edit that
line rather than add another assignment: the first occurrence in `.env` wins.
`orchestrator.log` and the default `analytics.jsonl` then live under `~/.local/state/chipping-orchestrator/logs`.
Without this override, `LOG_DIR` defaults to `<REPO_ROOT>/logs`, inside the installed environment's `site-packages`.
Recreating or uninstalling that environment can delete those logs. For an existing installation using the default,
stop the poller, copy its logs to the external directory, and set an absolute `LOG_DIR` before replacing the
environment. Preserve explicit `ANALYTICS_LOG_PATH` and `TRAJECTORY_LOG_PATH` overrides outside the environment too.

Edit `~/.config/chipping-orchestrator/.env` to change any of these, following
[basic setup](../configuration.md#basic-setup). To manage another repository, add its entry with `add-repo`, which
reads it off the clone the way `configure` does and edits the `REPOS` line in place, keeping every other line
([adding a repository](../configuration.md#adding-a-repository-with-add-repo)):

```sh
chipping-orchestrator add-repo --clone "$HOME/src/acme-web"
```

Copy only wanted operational overrides from the saved `.env.example.advanced` into that same file. Keep GitHub
tokens in per-repository token files or the launch environment
([credentials](../configuration.md#github-personal-access-token)); `.env` does not load them. The launch directory's
`.env` is never read by an installed package.

Store each `REPOS` repository's token with `set-token`, at its hidden prompt or from a file a script redirects in:

```sh
chipping-orchestrator set-token acme/api
chipping-orchestrator set-token acme/web < "$HOME/acme-web-token.txt"
```

Each run proves the token with one read-only GitHub call for that repository and only then writes
`~/.config/<owner>/<name>/token`, mode 0600 in a 0700 directory, replacing any token there; a token GitHub refuses
leaves the old one in place. It reads no configuration, so it works before `.env` is written, and it never edits
`.env`. Running it again is how a token is rotated ([set-token](../configuration.md#storing-a-token-with-set-token)).
With the settings and tokens in place, [check the setup](#check-compatibility-and-start) before the first start, then
[install the user service](#installing-with-init) with `init` and [start it](#operating) with `start` to keep the
poller running.

### Select an existing environment

`pipx list` shows the installed package and its exposed command. Use `pipx runpip chipping-orchestrator` for package
inspection and dependency checks; it selects the package's isolated environment without activating it.
`command -v chipping-orchestrator` shows the absolute launcher path to use, followed by `run`, in a hand-written
service unit; the unit [`init` installs](#installing-with-init) runs the environment's own interpreter instead.

### Check compatibility and start

Review the installed release's [notes][package-releases] for Python and agent CLI requirements, settings changes,
and workflow-state compatibility. Check the package version, dependency consistency, CLI, and setup before starting a
poller:

```sh
(
  set -eu
  pipx runpip chipping-orchestrator show chipping-orchestrator
  pipx runpip chipping-orchestrator check
  chipping-orchestrator --help
  chipping-orchestrator check
)
```

`pipx runpip chipping-orchestrator check` is pip's dependency check. `chipping-orchestrator check` checks the setup
in the environment the systemd user service runs with ([checking a setup](../configuration.md#checking-a-setup)):
`HOME`, `USER`, and the absolute entries of `PATH`, taken from the shell it runs in, and nothing else from it. Its
settings come from `~/.config/chipping-orchestrator/.env` and its tokens from the token files, as the service's do, so
an exported `GITHUB_TOKEN`, `REPOS`, `ALLOWED_ISSUE_AUTHORS`, agent binary override, or `ORCHESTRATOR_SKIP_DOTENV`
cannot make it pass where the service would fail. Run it as the service user, from a shell whose `PATH` holds the
directories the service is given.

It resolves the settings and target checkouts as a start does, refuses an empty author allowlist, finds a token for
every `REPOS` entry, and finds every agent binary the three roles run on that `PATH`, honoring `CLAUDE_BIN`,
`CODEX_BIN`, and `AGY_BIN` from `.env` and refusing a relative path among them, all in a fresh interpreter started as
the service's process starts. Then it proves each token reads its repository with one read-only GitHub call per entry;
`chipping-orchestrator check --local` leaves those calls out. It exits 0 with one line on stdout, or 1 with one line on
stderr per problem, and never polls an issue, writes a label or workflow state, or starts an agent. It does not prove
the token's write permissions, agent authentication, or compatibility with live issue state. `--help` checks the CLI
only; `run --once` performs a real polling tick and can start agents. Stop on a failed check and repair the settings
before starting or resuming polling.

Releases up to v0.13.0 have no `check` command. On one of them, as after [migrating](#moving-from-a-dedicated-venv)
with that version or [returning](#return-to-the-previous-package-version) to it, leave that line out and check the
settings as that release's own guide describes.

Start in the foreground:

```sh
chipping-orchestrator run
```

Startup diagnostics identify invalid settings, missing `REPOS`, invalid target checkouts, or an empty
`ALLOWED_ISSUE_AUTHORS`. Repair the live `.env` or overriding process/service environment before restarting.
Unknown or removed settings may be ignored, so diagnostics do not replace release-note and template comparisons.
For persistent supervision, use the [systemd user service](#running-under-systemd-user-service).

### Moving from a dedicated venv

For the v0.13.0 installation route at `~/.local/share/chipping-orchestrator/venv`, record the installed version with
`~/.local/share/chipping-orchestrator/venv/bin/python -m pip show chipping-orchestrator`. Keep that exact version and
its tested runtime dependency pins during migration; upgrade separately using the
[upgrade checklist](#upgrade-a-package).
Before stopping, read the recorded release's [notes][package-releases], set `ORCHESTRATOR_VERSION` to that version,
and download its `constraints.txt` using the [pinned procedure](#pin-a-release-and-runtime-dependencies).
[Save its templates](#save-the-installed-versions-templates) from the dedicated venv, with `ORCHESTRATOR_PYTHON` set to
`"$HOME/.local/share/chipping-orchestrator/venv/bin/python"`; a version up to v0.13.0 takes the release-tag download
described there instead. Retain a configuration backup and the service unit as described under
[upgrades](#upgrade-a-package).

Choose a [safe stopping point](#safe-restart-guidance), run `systemctl --user stop orchestrator.service` (or Ctrl+C
the foreground poller), and wait for shutdown. Deactivate the dedicated venv if it is active, then run the constrained
`pipx install` command from that procedure with the recorded version and its constraints, followed by
`pipx ensurepath`. The procedure explicitly selects a supported Python interpreter. Open a new terminal if needed
so the pipx command is on `PATH`.

Keep `~/.config/chipping-orchestrator/.env` and its absolute `LOG_DIR`, along with any explicit analytics or trajectory
paths outside the environment. Skip the first-setup `configure`. Compare the saved templates with the existing
settings and run the [compatibility checks](#check-compatibility-and-start). Confirm the installed version matches
the recorded version before restarting.
v0.13.0 has no `init`, so this migration keeps the hand-written `orchestrator.service` it runs under: replace that
unit's `ExecStart` with the absolute pipx launcher path shown by `command -v chipping-orchestrator`. v0.13.0 polls from
that bare command; add `run` only when an upgrade moves past it, as the [upgrade warning](#upgrade-a-package)
describes. Run `systemctl --user daemon-reload` and `systemctl --user start orchestrator.service`, then check startup
output and polling logs.

Keep the dedicated venv until the new installation passes these checks. If migration fails, stop the new poller,
restore the saved unit and compatible configuration, reload systemd, and restart the dedicated-venv service, honoring
the release's [rollback restrictions](#return-to-the-previous-package-version). Remove the old venv only after a
successful migration; subsequent upgrades and rollback use the pipx procedures below.

### Upgrade a package

**v0.14.0 changes the polling command.** Upgrading from v0.13.0 or earlier requires starting the poller as
`chipping-orchestrator run`. The bare command prints the help listing every command and exits 0, and a polling flag
given before any command is a usage error naming its `run` form, for example `chipping-orchestrator run --once`.
Before starting the upgraded package, append `run` to every launch line, script, and timer that runs the bare command,
and move any polling flag after it.

A hand-written unit whose `ExecStart` is the bare command would exit 0 on every start, and `Restart=always` would
relaunch it every `RestartSec` without it ever polling. Append `run` to its `ExecStart` and run
`systemctl --user daemon-reload` before starting it, or
[replace it with the unit `init` installs](#moving-from-the-hand-written-unit). A
[rollback](#return-to-the-previous-package-version) to v0.13.0 or earlier needs the bare form back, since those
releases refuse `run`, and has no `init`.

Package changes are operator-initiated. Use `pipx upgrade-all --skip chipping-orchestrator` for routine updates of
other apps so they do not change the package under a running poller. Before upgrading:

1. Read the [release notes][package-releases] for the version you intend to install and record that version. Check
   compatibility with the current Python, agents, targets, and live workflow state. Where that version cannot read the
   workflow state the installed one wrote, follow [Deploying without migration](#deploying-without-migration), which
   uses the backup and install steps below: no upgrade converts that state, and the work it cannot read does not
   resume. Record the current `Version` from `pipx runpip chipping-orchestrator show chipping-orchestrator` and retain
   its templates; if they are missing, [save them](#save-the-installed-versions-templates) now, while that version is
   still the one installed.
2. Choose a [safe stopping point](#safe-restart-guidance), preferably with no live agent child. Stop the service
   with `chipping-orchestrator stop` (`systemctl --user stop orchestrator.service` on a host still running the
   hand-written unit of v0.13.0 or earlier), or Ctrl+C the foreground command, and wait for shutdown. Stop every
   poller using this pipx environment before changing it.
3. Back up settings and retain the previous release selection:

   ```sh
   ORCHESTRATOR_PREVIOUS_VERSION='A.B.C'
   ORCHESTRATOR_PREVIOUS_RELEASE_DIR="$HOME/.local/share/chipping-orchestrator/releases/v${ORCHESTRATOR_PREVIOUS_VERSION:?}"
   ORCHESTRATOR_BACKUP_DIR="$HOME/.local/share/chipping-orchestrator/backups/$(date -u +%Y%m%dT%H%M%SZ)"
   (
     set -eu
     umask 077
     mkdir -p "${ORCHESTRATOR_BACKUP_DIR:?}"
     cp -a "$HOME/.config/chipping-orchestrator" "${ORCHESTRATOR_BACKUP_DIR:?}/configuration"
     printf '%s\n' "${ORCHESTRATOR_PREVIOUS_VERSION:?}" > "${ORCHESTRATOR_BACKUP_DIR:?}/version.txt"
   )
   ```

   Replace `A.B.C` with the recorded version. Also retain custom service units, referenced environment files, and
   process/service overrides with their existing access restrictions. Keep credentials, clones, worktrees, and
   external log paths in place.
4. For an unconstrained, unpinned installation, upgrade to the latest available release:

   ```sh
   pipx upgrade chipping-orchestrator
   pipx runpip chipping-orchestrator show chipping-orchestrator
   ```

   An enabled [release-age cooldown](../security.md#checklist-mapping) is saved and reused by upgrades and forced
   installs unless `PIPX_COOLDOWN` or explicit `--cooldown` overrides it; `pipx reinstall` always uses the saved
   window and ignores `PIPX_COOLDOWN`. If it hides a fresh release you have reviewed, add `--cooldown 0` (or a shorter
   window) to the upgrade or recovery install, for example
   `pipx install --force --python python3.12 --cooldown 0 "chipping-orchestrator==X.Y.Z"`.
   pipx saves the chosen window, including zero, for later upgrades and forced installs; restore your usual window
   explicitly on the next package change if needed.

   For a constrained installation, repeat the [pinned procedure](#pin-a-release-and-runtime-dependencies) with the
   new version and its own constraints. `pipx upgrade` reuses the `--pip-args` saved at installation, including the
   previous release's constraint path. To return to unconstrained, unpinned releases, use the forced reinstall
   command in that section. After a rollback without constraints, run `pipx unpin chipping-orchestrator` before
   the upgrade above, with the poller stopped.

   Stop if installation fails or the displayed `Version` differs from the version reviewed in step 1. For an
   unconstrained installation, recover that reviewed version explicitly (replace `X.Y.Z` with it):

   ```sh
   pipx install --force --python python3.12 "chipping-orchestrator==X.Y.Z"
   pipx runpip chipping-orchestrator show chipping-orchestrator
   ```

   Leave the poller stopped until the intended version is installed and passes checks.
5. On every upgrade, [save the templates](#save-the-installed-versions-templates) the intended version installed and
   [compare configuration](#compare-configuration-across-versions) before resuming.
6. Repeat [compatibility checks](#check-compatibility-and-start), then start `chipping-orchestrator run` again or run
   `chipping-orchestrator start`, which [checks the settings locally](#operating) once more, starts the service, and
   reports it active or prints the last lines of its journal. A host still on the hand-written unit
   [replaces it](#moving-from-the-hand-written-unit) before that start. Run `chipping-orchestrator init` before it
   when the interpreter path or the agents' directories changed, which rewrites and reloads the unit; editing `.env`
   alone needs no reload. Check startup output and logs for connections and polling.

If a release requires a different Python interpreter, follow
[Change the Python interpreter](#change-the-python-interpreter) before installing it.

### Change the Python interpreter

Provision a supported interpreter and stop every poller using the environment. Record the installed `Version` with
`pipx runpip chipping-orchestrator show chipping-orchestrator`.
For a pinned installation, unpin before reinstalling and restore the pin after a successful reinstall:

```sh
pipx unpin chipping-orchestrator
pipx reinstall --python python3.13 chipping-orchestrator
pipx pin chipping-orchestrator
pipx runpip chipping-orchestrator show chipping-orchestrator
```

Substitute the chosen interpreter; skip the unpin and pin commands for an unpinned installation. Reinstall reuses
the saved package requirement and installation options, including constraints and the cooldown window. It ignores
`PIPX_COOLDOWN` and has no `--cooldown` option.

A saved `==X.Y.Z` keeps that version, while a bare package name can install the newest available release.
`pipx upgrade` and `pipx upgrade-all` replace a saved version requirement with the bare package name, so a later
interpreter-only reinstall can also upgrade the orchestrator. The constrained procedure avoids those upgrade
commands and retains `==X.Y.Z`.

Confirm the displayed `Version` matches the intended release; for an interpreter-only change, it must match the
recorded version. If it differs, use the explicit version install in [Upgrade a package](#upgrade-a-package) or the
[pinned procedure](#pin-a-release-and-runtime-dependencies) with the chosen interpreter to install the intended
release. Keep the poller stopped if any command fails. Retain the external settings and logs, then repeat
compatibility checks before restarting.

### Compare configuration across versions

Release notes identify added, renamed, or removed settings, changed defaults, stricter validation, and any migration
or rollback restrictions. Compare the retained templates and the live settings in the same shell as the upgrade:

```sh
diff -u "${ORCHESTRATOR_PREVIOUS_RELEASE_DIR:?}/.env.example" "${ORCHESTRATOR_RELEASE_DIR:?}/.env.example"
diff -u "${ORCHESTRATOR_PREVIOUS_RELEASE_DIR:?}/.env.example.advanced" "${ORCHESTRATOR_RELEASE_DIR:?}/.env.example.advanced"
diff -u "${ORCHESTRATOR_RELEASE_DIR:?}/.env.example" "$HOME/.config/chipping-orchestrator/.env"
```

`diff` exits 1 when files differ; review those differences. Merge required changes into the existing `.env` rather
than replacing it. Keep local target paths, author lists, agent specs, budgets, and other deliberate overrides.
For a changed default, decide whether to adopt it or explicitly retain the previous value. Check selected advanced
settings and service overrides too; commented examples are not active settings.

Keep the backup and record edits. Older versions can ignore new settings or reject values accepted by a newer one,
so review startup diagnostics after every repair and after rollback.

### Return to the previous package version

Read both releases' rollback notes: restoring `.env` does not undo workflow state written on GitHub. Returning an
older binary to workflow state a newer one wrote is not a supported procedure for this release
([C-03](../contracts.md#c-03-persisted-and-externally-consumed-formats)): nothing converts that state back, and the
older version is not promised to read it. A return carries no such risk only while the newer version has not polled,
as after a failed installation or check; otherwise treat it as a
[deployment without migration](#deploying-without-migration) that keeps from the older version every issue the newer
one wrote. Before returning to a version that cannot handle late split state, complete the
[workflow drain](#rolling-back-to-an-older-orchestrator) with the newer package running and `DECOMPOSE=off`.
Honor other release-specific restrictions, then stop the process and supervisor and wait for shutdown.
Returning to v0.13.0 or earlier also takes away the service `init` installed, since those releases have no `init`
and refuse the `run` its unit launches: while the newer package is still installed, run
`chipping-orchestrator remove`, which [stops, disables, and deletes](#removing) that unit and keeps everything else.

Select the retained backup explicitly, replacing `YYYYMMDDTHHMMSSZ` with its timestamp:

```sh
ORCHESTRATOR_BACKUP_DIR="$HOME/.local/share/chipping-orchestrator/backups/YYYYMMDDTHHMMSSZ"
ORCHESTRATOR_PREVIOUS_VERSION="$(cat "${ORCHESTRATOR_BACKUP_DIR:?}/version.txt")"
```

Stop if the backup or version record is missing. For a constrained installation, repeat the
[pinned procedure](#pin-a-release-and-runtime-dependencies) with the recorded previous version and that version's
own constraints. For an unconstrained installation, reinstall the recorded version:

```sh
pipx install --force --python python3.12 "chipping-orchestrator==${ORCHESTRATOR_PREVIOUS_VERSION:?}"
```

Stop if installation fails.
After a successful rollback, run `pipx pin chipping-orchestrator` to prevent `pipx upgrade` and `pipx upgrade-all`
from replacing the chosen version ([pipx pinning][pipx-pinning]). Unpin only for a planned upgrade or
[interpreter change](#change-the-python-interpreter) while the poller is stopped.

Restore or translate configuration only where the older version requires it. Preserve the current `.env` before
restoring the backup; if `.env.pre-rollback` already exists, use another filename throughout:

```sh
(
  set -eu
  umask 077
  test ! -e "$HOME/.config/chipping-orchestrator/.env.pre-rollback"
  cp -p "$HOME/.config/chipping-orchestrator/.env" "$HOME/.config/chipping-orchestrator/.env.pre-rollback"
  cp -p "${ORCHESTRATOR_BACKUP_DIR:?}/configuration/.env" "$HOME/.config/chipping-orchestrator/.env"
)
```

Compare the restored settings with the saved current file:

```sh
diff -u "$HOME/.config/chipping-orchestrator/.env" "$HOME/.config/chipping-orchestrator/.env.pre-rollback"
```

`diff` exits 1 when files differ. Reconcile edits made since the backup with the older version's supported settings,
keeping compatible target paths, author lists, log paths, and other deliberate overrides. Review process/service
overrides too.

Returning to v0.13.0 or earlier also returns the poller to the bare command, since those releases refuse `run`, and
to a hand-written unit, since they have no `init`. Where the service `init` installed is still there because the
older package was installed before `remove` ran, run
`systemctl --user disable --now chipping-orchestrator.service` and delete
`~/.config/systemd/user/chipping-orchestrator.service`, whose `ExecStart` runs `run`. Then remove `run` from launch
lines and from the hand-written unit's `ExecStart`, or restore the unit retained before the upgrade (on a host that
never had one, write it as that release's guide describes), and run `systemctl --user daemon-reload`.

Repeat [compatibility checks](#check-compatibility-and-start), confirm the restored version, then restart and inspect
startup output and logs. Keep external logs and credentials at their existing paths throughout.

### Pin a release and runtime dependencies

For reproducible installs, upgrades, or rollback, choose a release whose matching [GitHub release][package-releases]
includes `constraints.txt`. Set `ORCHESTRATOR_VERSION` to that exact version, with the same release directory the
[saving block](#save-the-installed-versions-templates) uses, and download its runtime constraints there:

```sh
ORCHESTRATOR_VERSION='X.Y.Z'
ORCHESTRATOR_RELEASE_DIR="$HOME/.local/share/chipping-orchestrator/releases/v${ORCHESTRATOR_VERSION:?}"
(
  set -eu
  umask 077
  mkdir -p "${ORCHESTRATOR_RELEASE_DIR:?}"
  curl --fail --location --output "${ORCHESTRATOR_RELEASE_DIR:?}/constraints.txt" \
    "https://github.com/chippingway/chipping-orchestrator/releases/download/v${ORCHESTRATOR_VERSION:?}/constraints.txt"
)
```

Stop if the download fails. Select an installed Python supported by the chosen release; for an existing environment,
pass its interpreter on every forced install (`python3.12` below). To use a different interpreter, first follow
[Change the Python interpreter](#change-the-python-interpreter), then use the chosen interpreter in the forced
install below.

For a fresh release you have reviewed, add `--cooldown 0` (or a shorter window) to the command below if an enabled
[release-age cooldown](../security.md#checklist-mapping) would exclude it or any constrained dependency. Explicit
`--cooldown` overrides both `PIPX_COOLDOWN` and the saved value, and pipx saves the chosen window, including zero,
for later upgrades and forced installs. Restore your usual window explicitly on the next package change if needed.

Use an absolute `ORCHESTRATOR_RELEASE_DIR` path without whitespace: the uv backend splits constraint paths on
whitespace even when quoted. If `$HOME` contains spaces, set `ORCHESTRATOR_RELEASE_DIR` to a directory whose absolute
path has no whitespace, download the constraints there, and save the templates there after installing; retain it for
later reinstalls.

With the poller stopped, install the chosen version using those constraints:

```sh
pipx install --force --python python3.12 \
  --pip-args="--constraint ${ORCHESTRATOR_RELEASE_DIR:?}/constraints.txt" \
  "chipping-orchestrator==${ORCHESTRATOR_VERSION:?}"
```

`pipx install --force` requests a forced reinstall and keeps an existing environment's recorded installer backend.
The `--pip-args` constraint is applied by pip or uv, whichever that
environment uses. [Pip constraints][pip-constraints]
restrict runtime dependency versions; the explicit package requirement selects the orchestrator version.
Keep `--upgrade` out of `--pip-args`: pipx supplies it during upgrades, and uv rejects duplicate flags.
Use each release's own constraints, compare settings, and repeat compatibility checks before starting.

After a successful installation, [save its templates](#save-the-installed-versions-templates) into the same release
directory, then run `pipx pin chipping-orchestrator` to exclude the environment from routine upgrades. pipx saves the
installation's `--pip-args`; unpinning alone leaves the constraint path in place. Upgrade a constrained installation
by repeating this procedure for the new version with its own templates and constraints.

To return to the latest release without saved constraints, stop every poller using the environment and run:

```sh
pipx install --force --python python3.12 chipping-orchestrator
```

The forced install replaces the saved pip arguments and clears the pin, permitting subsequent upgrades.
Compare configuration and repeat compatibility checks before restarting.

[package-releases]: https://github.com/chippingway/chipping-orchestrator/releases
[pipx-installation]: https://pipx.pypa.io/stable/how-to/install-pipx.html
[pipx-cli]: https://pipx.pypa.io/stable/reference/cli.html
[pipx-changelog]: https://pipx.pypa.io/stable/changelog.html
[pipx-pinning]: https://pipx.pypa.io/stable/how-to/pin-packages.html
[pip-constraints]: https://pip.pypa.io/en/stable/user_guide/#constraints-files

## Deploying without migration

This procedure deploys a build that cannot read the work the running pollers own: a package version or source commit
that no longer reads a format some issue, record, or artifact of theirs still carries.
[C-03](../contracts.md#c-03-persisted-and-externally-consumed-formats) sets the policy for this release, so there is no
migration to run, no final 0.x release to install first, and no automatic resumption of the work the selected build
cannot read. Finishing some of that work under a build that reads it, before these steps, is optional.

Breaking changes do not wait for a release tag. They reach `main` as they merge, so a source checkout that follows it
can receive one before any release carries it, and a tag deploys nothing by itself: a package changes only when an
operator installs another version. Judge the selected build by its own release notes or commits, whatever its version.

Three procedures are not supported for this release: converting earlier-format JSONL records or Postgres analytics
data to current formats, continuing an agent session recorded in an earlier format, and returning an older binary to
workflow state a newer one wrote. [Upgrade a package](#upgrade-a-package),
[Return to the previous package version](#return-to-the-previous-package-version),
[Rolling back to an older orchestrator](#rolling-back-to-an-older-orchestrator), and
[What survives a restart](#what-survives-a-restart) all stay inside that boundary.

### Take an inventory

Record the following before stopping anything, on every host that runs a poller against the same repositories. One
host is the [supported topology](#running-more-than-one-poller), so finding a second is a finding in itself.

- **Pollers and agents.** `pgrep -af 'orchestrator|run\.sh|codex|claude|agy'` lists them. A poller runs the
  `chipping-orchestrator` command or `python -m orchestrator`, a source wrapper runs `run.sh`, and an agent is a
  `codex`, `claude`, or `agy` process whose working directory (`readlink /proc/<pid>/cwd`) lies under `WORKTREES_DIR`.
  Count each `run --once` and `run --cleanup-terminal-artifacts` launch among them.
- **Installations and checkouts.** For a package: `pipx list`, the `Version` that
  `pipx runpip chipping-orchestrator show chipping-orchestrator` shows, and `chipping-orchestrator status`, which
  names the `.env` and the unit in use; a v0.13.0 [dedicated venv](#moving-from-a-dedicated-venv) is one more
  installation. For a source checkout: `git rev-parse HEAD` and `git branch --show-current` run in it, and the
  `ORCHESTRATOR_BASE_BRANCH` its `.env` or launch environment sets (default `main`).
- **Supervision and updates.** `systemctl --user list-unit-files 'chipping-orchestrator*' 'orchestrator*'` finds the
  service `init` installs and the hand-written unit of v0.13.0 or earlier. Look as well for a development unit
  running a checkout's `run.sh`, whose name is the developer's choice, and read `systemctl --user list-timers --all`,
  `crontab -l`, and any job that runs `pipx upgrade`, `pipx upgrade-all`, `pipx reinstall`, or a `git pull` in a
  checkout. Note which units are enabled: an enabled unit starts whenever the user manager does, at boot with linger.
  A source wrapper is an update mechanism of its own, since
  [`run.sh`](../development.md#development-restart-wrapper) pulls before it launches.
- **The selected build.** The exact package version, or the full commit SHA of the source revision, and what its
  [release notes][package-releases] or commits say it no longer reads.
- **Repositories and `WORKTREES_DIR`.** The `REPOS` each poller resolves -- from `~/.config/chipping-orchestrator/.env`
  for a package, from the checkout's own `.env` for a source checkout, and from any process or drop-in override, which
  `systemctl --user cat chipping-orchestrator.service` shows -- and the `WORKTREES_DIR` each one resolves, explicit or
  [defaulted](../configuration.md#workspace-and-agent-identity) beside the first entry. Note which entries share one
  `target_root`: those can only be [excluded](#exclude-or-retire-unsupported-work) together.
- **Owned work, per repository.** Issues carrying a workflow label in any spelling, open or closed; issues carrying a
  pinned state comment; and every open issue an `ALLOWED_ISSUE_AUTHORS` login filed that carries neither, which the
  selected build would take up as new work. List apart the old issues with no pinned comment, including those whose
  only stage-like label is an obsolete bare one such as `ready` or `fixing`
  ([obsolete bare labels](../state-machine.md#obsolete-bare-labels)): to a build that reads canonical labels only,
  such an issue carries no workflow label and no pinned comment, which is exactly what fresh pickup looks for. Then
  the pull requests on `orchestrator/` branches, the branches and refs under `orchestrator/` in the clone and on the
  remote, the worktrees, and the host's recovery records: the claim files and quota retirement
  records in `WORKTREES_DIR/.issue-writer-claims/` ([host records](#running-more-than-one-poller)), and
  `EVENT_LOG_PATH` with every rotated copy beside it
  ([audit log](../observability/event-streams.md#audit-event-log-event_log_path)).

With the GitHub CLI, `gh`, logged in to an account that reads the repository, and the shell's `WORKTREES_DIR` set to
the resolved directory, these list a repository's share; repeat them for every `REPOS` entry:

```sh
ORCHESTRATOR_REPO='acme/api'
ORCHESTRATOR_CLONE="$HOME/src/acme-api"
ORCHESTRATOR_REMOTE='origin'
(
  set -eu
  gh api --paginate "repos/${ORCHESTRATOR_REPO:?}/issues?state=all&per_page=100" \
    --jq '.[] | select(.pull_request | not) | [.number, .state, .user.login, ([.labels[].name] | join(","))] | @tsv'
  gh api --paginate "repos/${ORCHESTRATOR_REPO:?}/issues/comments?per_page=100" \
    --jq '.[] | select((.body // "") | contains("<!--orchestrator-state")) | [.issue_url, .id, .user.login] | @tsv'
  gh api --paginate "repos/${ORCHESTRATOR_REPO:?}/pulls?state=all&per_page=100" \
    --jq '.[] | select(.head.ref | startswith("orchestrator/")) | [.number, .state, .head.label] | @tsv'
)
git -C "${ORCHESTRATOR_CLONE:?}" for-each-ref refs/heads/orchestrator/ refs/orchestrator/
git -C "${ORCHESTRATOR_CLONE:?}" ls-remote "${ORCHESTRATOR_REMOTE:?}" 'refs/heads/orchestrator/*' 'refs/orchestrator/*'
git -C "${ORCHESTRATOR_CLONE:?}" worktree list --porcelain
ls -la "${WORKTREES_DIR:?}" "${WORKTREES_DIR:?}/.issue-writer-claims"
grep -L -x '{}' "${WORKTREES_DIR:?}"/.issue-writer-claims/*.quota-retirement
```

The three listings page through the whole repository: every issue, open or closed, with its author and labels; every
issue comment that carries the pinned-state marker, with the issue it is on; and every pull request on an
`orchestrator/` branch. Stop if the subshell fails, since a page it did not fetch leaves the inventory incomplete, and
work missing from the inventory is work nothing below keeps away from the selected build. A pinned comment counts as
state only when the orchestrator's own account wrote it
([authentication](../security.md#pinned-state-authentication)), so compare the login each line prints with that
account. A build that admits only version-1 records reads that state only where its JSON object carries an integer
`schema_version` of `1` ([pinned state](../state-machine/labels-and-state.md#pinned-state)): a pinned comment without
one, which is every one a build predating that field wrote, is refused and left as it stands, and its issue is work the
selected build cannot read. The last command names every quota retirement record that does not read `{}`: an arming or
an owed retirement that holds its issue's developer launches until someone settles it.

### Stop and hold every poller

Stop every poller in the inventory, with its agents, before replacing any code it runs, and hold whatever would start
or update one again until the [deliberate start](#install-check-and-start-deliberately). Choose a
[safe stopping point](#safe-restart-guidance) where you can, preferably with no live agent child.

For a package:

1. Hold package updates. `pipx pin chipping-orchestrator` keeps `pipx upgrade` and `pipx upgrade-all` from replacing
   the installed version ([pipx pinning][pipx-pinning]); disable any scheduled job that installs, reinstalls, or
   upgrades the package as well.
2. Stop the service and hold it:

   ```sh
   chipping-orchestrator stop
   systemctl --user disable chipping-orchestrator.service
   ```

   `stop` leaves the service enabled, so the user manager would start it again the next time it starts, as at boot;
   `disable` holds it until supervision is restored. `init` enables the service whenever it runs, so leave it to the
   deliberate start, or disable the service again after running it. A host still on the hand-written unit of v0.13.0
   or earlier runs `systemctl --user disable --now orchestrator.service` instead.
3. Stop the rest: Ctrl+C each foreground `chipping-orchestrator run` and wait for it to exit, and hold each timer or
   crontab line that launches `run` in any form, with `systemctl --user disable --now <name>.timer` or by commenting
   the line out in `crontab -e`.

For a source checkout:

1. Stop and hold the wrapper's supervisor first, so nothing relaunches it: `systemctl --user disable --now <unit>` for
   a [development unit](../development.md#development-restart-wrapper), whose stop sends the wrapper the `SIGTERM` it
   exits on without relaunching, and comment out each crontab line that runs `run.sh` or `python -m orchestrator`.
2. Ctrl+C a foreground `./run.sh` once and wait for it to exit; a second Ctrl+C ends it at once, without the graceful
   shutdown.
3. Leave `run.sh` stopped until the selected revision is [held](#install-check-and-start-deliberately): on its base
   branch it pulls `origin/<ORCHESTRATOR_BASE_BRANCH>` when it starts and again before every relaunch after an exit
   that is not a signal stop, so any start of it there takes whatever that branch carries by then.

Then check that everything is down:

```sh
pgrep -af 'orchestrator|run\.sh|codex|claude|agy'
chipping-orchestrator status
systemctl --user is-enabled chipping-orchestrator.service
```

No poller, wrapper, or agent working under `WORKTREES_DIR` may remain in the list. `status` exits 3 for a service that
is not running, and `is-enabled` prints `disabled`; ask the same of a development unit or hand-written unit by name. A
graceful stop ends its agents with it ([what survives a restart](#what-survives-a-restart)). An agent left running by a
poller killed outright is still working in its worktree: wait for it to exit, or stop it knowing that this can leave a
dirty worktree and, for `agy`, an armed quota record. Go no further while any of them runs.

### Exclude or retire unsupported work

Sort the inventoried work into what the selected build reads and what it cannot. Current work it reads resumes from
its label, pinned comment, worktree, and host records once it starts. Everything else has to be kept from it, and
which paths reach an issue decides what keeps it away:

- **Pickup.** The first tick greets as new work every open issue an `ALLOWED_ISSUE_AUTHORS` login filed that carries
  no workflow label and no pinned comment. An old issue with no pinned comment and only an obsolete bare label is one
  of them: a build that reads [canonical labels only](../state-machine.md#obsolete-bare-labels) finds no workflow
  label on it, so the issue appears unlabeled and enters ordinary pickup, which starts it from scratch. The bare label
  is not authoritative state, and no implicit migration reads or rewrites it: label setup creates only the canonical
  labels a repository lacks and leaves every other definition, and the issues carrying it, as they are. A build's
  [refusal](#install-check-and-start-deliberately) of unsupported pinned state cannot hold such an issue either, since
  it has no pinned comment to refuse and an issue without one is fresh work, so this exclusion is what keeps it away.
  To a build that still routes the bare spelling, the same issue instead reaches the stage handler the label names
  with no record behind it. Apply `backlog` to each of those that is not new work.
- **Dispatch and refresh.** An open issue whose workflow label routes it reaches the stage handler that label names,
  and the base refresh before each tick can rebase its worktree. A build that admits only version-1 records
  [refuses dispatch](../state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick) of an issue whose
  pinned comment it cannot admit, writing nothing for it, and its
  [refresh](../state-machine/labels-and-state.md#base-refresh) leaves that issue's checkout, branches, and pull request
  as they stand, saying so in a local warning each tick; only the base fetch every worktree shares still runs. An
  issue with no pinned comment is not refused this way. `paused`, or `backlog`, holds both, at dispatch, scheduling,
  and the refresh, which then reads no comment and says nothing ([control labels](../configuration.md#control-labels)).
  Hold a decomposed family as a whole: a parent's handler writes its children too, under each child's own claim. Its
  seeds, recovery repairs, releases, merge finalizes of a closed child, and notices that a reclaimed snapshot is gone
  write nothing to a child whose pinned comment it cannot admit, and no snapshot a consumer like that was cut from is
  deleted while it stays unadmitted.
- **Closed-issue recovery and cleanup.** The closed-issue sweep finalizes a closed issue still on a stage label, and
  `paused` holds that as it holds dispatch. It asks for canonical label names only, so neither it nor the closed-owner
  sweep below reaches a closed issue carrying only an obsolete bare label
  ([pollable issues](../state-machine/labels-and-state.md#pollable-issues-and-finalization)). A closed issue on
  `workflow:decomposing`, `workflow:umbrella`, `workflow:ready`, or `workflow:blocked` goes to the
  [closed-owner sweep](../state-machine/delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own) instead,
  which ends the cycle, closes the pull request it held, reclaims what its ledger owes the remote, and writes
  `rejected`; a control label defers those steps but not the cancellation it records in the pinned comment. Over an
  owner whose pinned comment the selected build refuses, that sweep and the close receipt a poll would post write
  nothing, and its pull request, branch, and snapshot ref stay where they are; a close the poll read on it is held in
  memory, costing a refused pass every tick until the comment is dealt with or the poller restarts. The
  [maintenance pass](#reclaiming-a-finished-issues-artifacts) reclaims the current-layout worktree and branch of a
  closed issue on one terminal label whatever its control labels or obsolete bare labels say, though only what its
  gates prove nothing else needs, and keeps those of a closed issue carrying only an obsolete bare label, which has no
  workflow label to own them by, and those of one whose pinned comment the selected build refuses, saying so in a
  local warning each pass. No path reclaims a flat `orchestrator/issue-<n>` branch or `WORKTREES_DIR/issue-<n>`
  checkout an earlier layout left, and terminal, question, and late-split teardowns delete a recorded branch only
  where it is the issue's current-layout name, remove a checkout only where it is proven a worktree of the clone on
  that branch at its own path (never through a symlink), and touch neither where another configured repository
  derives the same names. Closing an issue retires it into these paths, not out of them: retire that way only work
  whose records the selected build reads, and keep the rest out with its repository.
- **Work on an earlier branch layout.** The selected build works an issue's branch only where its pinned record names
  the repository's current-layout `orchestrator/<owner>__<name>/issue-<n>`, or names neither a branch nor a pull
  request. A record naming a pull request with no `branch` beside it, which an earlier build read as the flat
  `orchestrator/issue-<n>`, and a record pinning a flat or any other name are refused at every road that would create,
  reuse, or restore a checkout, launch an agent, or push, with a local warning each tick and nothing written, and the
  base refresh routes nothing over them. A checkout at an issue's current path standing on the flat branch, another
  repository's, or a detached HEAD no unfinished rebase of the issue's branch accounts for is refused by every road
  that would resume, reuse, rebase, recover, or publish from it, whatever commits it carries
  ([branch refusal](../state-machine/labels-and-state.md#branch-refusal)). No later tick resumes such an issue: finish
  it under a build that still reads it, or close it, whose teardown deletes only the current-layout branch.
- **Community pull requests.** The per-tick community sweep writes to open pull requests from authors outside
  `ALLOWED_ISSUE_AUTHORS` — save, to a build that skips an issue's own, those the token's own account opened and
  any standing on a branch of the repository under `orchestrator/` — and no control label holds it. To a build whose
  [sweep](../state-machine/labels-and-state.md#workflow-labels) takes only `workflow:community_contribution` as the
  mark of an earlier HITL ping, one carrying only the pre-namespace `community_contribution` is unmarked: its first
  sweep @-mentions `HITL_HANDLE` on it again and adds the namespaced label beside the bare one, which stays. Accept
  that one ping per such pull request, or leave the repository out.
- **Requirements baselines.** A build that compares the drift baseline in the current fingerprint alone reads a
  recorded `user_content_hash` or `observed_user_content_hash` it does not reproduce as a requirements edit, whichever
  build wrote it -- one an earlier build recorded counting a bare `/orchestrator continue` among the requirements
  included, on an issue whose thread carries one. Nothing rewrites that value, so the issue's next
  [drift check](../state-machine/delivery-stages.md#user-content-drift-detection) takes the route its stage takes for
  a human's edit: back to `workflow:decomposing` before implementation, orphaning an umbrella's tracked children; a
  developer resume once implementation has started; the `documenting` unwind; or, in a late adjudication, a
  content-drift park that waits for a human. An issue on `workflow:blocked` meets it on its release to
  `workflow:ready`, and `paused` or `backlog` only defers it. Accept that one route per such issue, or leave its
  repository out.
- **Review feedback delivery.** A build that counts as delivered only the stretch of the issue thread a developer
  prompt quoted (`delivered_after_comment_id` through `delivered_through_comment_id`) reads an issue an earlier build
  picked up as having been handed nothing: that build recorded delivery on the reply boundary
  `last_action_comment_id`, which no feedback reader takes as delivery now, and nothing writes the stretch back. The
  approval's seed walk, and the initialization of an in_review watermark left unset, therefore stop at the first human
  comment on the thread, and the issue-thread replies an earlier developer resume already answered reach `in_review`
  as unread feedback and route it to `workflow:fixing`, where they are delivered and settled once. A fix round an
  earlier build parked with only its `pending_fix_*_max_id` bookmarks, and no recorded id lists, replays nothing: a
  bare `/orchestrator continue` on it is refused, so answer it with the feedback written out instead. Accept that
  extra fix round per such issue, or leave its repository out.
- **A whole repository.** A repository the selected build is not configured for is never polled, swept, or
  refreshed, and the maintenance pass leaves alone every artifact whose name marks it as that repository's. Flat
  `orchestrator/issue-<n>` branches and `WORKTREES_DIR/issue-<n>` checkouts are no entry's, whichever entries are
  configured. The exception is a pair of entries whose slugs the sanitizer cannot tell apart, so that they derive one
  branch name or checkout directory ([shared clones](#what-it-looks-for)): with both configured the pass refuses those
  artifacts as ambiguous; with one left out, the other claims them and judges them against its own issue of that
  number. So leave out every entry that collides with the excluded repository that way, and keep them all out until
  those artifacts have been disposed of by hand. Set `WORKTREES_DIR` explicitly first: left unset, it follows the
  first `REPOS` entry, and dropping that entry
  would move it away from the retained work and its records. Keep at least one compatible entry, too, or keep polling
  stopped: an installed package refuses to start with `REPOS` empty, but a source checkout then falls back to its
  developer settings, `REPO` at `TARGET_REPO_ROOT`
  ([developer fallback](../configuration.md#developer-fallback-and-target-checks)), which can name the very repository
  left out. Within those conditions, leaving a repository out is the one exclusion every path honors.

Never make old work look current or new to get the selected build started: do not delete or edit a pinned comment,
stamp earlier JSON as a supported format, reset lifetime run charges
([C-15](../contracts.md#c-15-lifetime-agent-run-budget)), or delete a branch, worktree, or host record nobody has
proved unneeded. A record the selected build cannot read is left for a human to decide on.

### Preserve records for manual disposition

Everything the inventory lists stays in place for manual disposition, decided artifact by artifact and never as a step
toward starting the selected build:

- Export every inventoried issue with its comments, the pinned comment included, off the host, as the
  [backup drill](../security.md#backup-and-restore-drills) does, so what each issue records now survives whatever is
  written to it later.
- Back up `WORKTREES_DIR/.issue-writer-claims/` while the pollers are stopped, and keep `WORKTREES_DIR` at the same path
  with its worktrees: retained work recovers from them and from the claim and quota retirement records
  ([C-01](../contracts.md#c-01-durable-workflow-state-and-recovery)), and an unsettled quota record keeps holding its
  issue's developer launches until someone settles it ([owed quota retirement](#running-more-than-one-poller)).
- Keep the target clones and every branch and ref under `orchestrator/`, locally and on the remote. No automatic path
  deletes a flat `orchestrator/issue-<n>` branch or `WORKTREES_DIR/issue-<n>` checkout an earlier layout left, so
  those stay until you dispose of them.
- Keep `EVENT_LOG_PATH` naming the same file, with every rotated copy beside it readable: a base-rewrite finish still to
  retry reads them so it files its `base_rebased` only once
  ([C-12](../contracts.md#c-12-observation-and-the-audit-recovery-exception)).
- Back up the settings, as step 3 of [Upgrade a package](#upgrade-a-package) does for a package or by copying a source
  checkout's `.env`, and keep custom units, drop-ins, and the logs.
- Leave operator-owned analytics storage alone: the analytics and trajectory JSONL files, and the analytics database
  with its `analytics-db/data/` volume. Nothing in them is converted, and the dashboard and the trajectory viewer read
  an earlier record only as the current producers would have written it: a field it never carried stays unknown, so a
  skill load recorded with no offered set joins no adoption denominator, an unclassified catalog name pads no cell,
  and a run that recorded no review round reports under `unknown`.

### Install, check, and start deliberately

With every poller still stopped and held, install the selected build, give it the configuration and launch syntax it
documents, check it, and start it by hand.

For a package:

1. Install the selected version with the explicit-version forced install in step 4 of
   [Upgrade a package](#upgrade-a-package), or with the [pinned procedure](#pin-a-release-and-runtime-dependencies) and
   that version's constraints. Confirm the `Version` pipx shows, then run `pipx pin chipping-orchestrator` again, since
   a forced install clears the pin.
2. [Save its templates](#save-the-installed-versions-templates) and
   [compare configuration](#compare-configuration-across-versions), merging what the version requires into `.env`.
   Give every launch line, script, timer, and unit its launch syntax, such as `run` after the command
   ([upgrade warning](#upgrade-a-package)).
3. Run the [compatibility checks](#check-compatibility-and-start). Run `chipping-orchestrator init` only where the
   interpreter path or the agents' directories changed, or the unit was removed, remembering that it enables the
   service.

For a source checkout:

1. Hold the selected revision. A checkout on its base branch is fast-forwarded by `run.sh` before every launch, and the
   [self-restart guard](../architecture.md#process-model) ends the poller, before any polling pass, whenever
   `origin/<ORCHESTRATOR_BASE_BRANCH>` has moved past the running commit with changes under `orchestrator/`. Another
   branch skips the pull but not the guard: once that remote branch moves on, the poller exits before its first pass on
   every launch, and the wrapper relaunches it every second without it ever polling. The guard reads
   `origin/<ORCHESTRATOR_BASE_BRANCH>` from the checkout's own refs once its fetch is done, so a remote-tracking ref a
   deleted remote branch left behind, which `git fetch` does not prune by default, still counts. So check the revision
   out on a local branch whose name matches no ref on `origin` and none of the checkout's `origin/` refs, and name that
   branch as `ORCHESTRATOR_BASE_BRANCH`:

   ```sh
   ORCHESTRATOR_CHECKOUT="$HOME/src/chipping-orchestrator"
   ORCHESTRATOR_COMMIT='<full commit SHA>'
   git -C "${ORCHESTRATOR_CHECKOUT:?}" fetch origin
   git -C "${ORCHESTRATOR_CHECKOUT:?}" ls-remote --exit-code origin held-deployment 'held-deployment/HEAD'
   git -C "${ORCHESTRATOR_CHECKOUT:?}" rev-parse --verify --quiet origin/held-deployment
   git -C "${ORCHESTRATOR_CHECKOUT:?}" switch --create held-deployment "${ORCHESTRATOR_COMMIT:?}"
   ```

   Switch only once both checks come back empty. `ls-remote` has to exit 2, finding no ref on `origin` the wrapper's
   `git pull origin held-deployment` could resolve the name to: a branch, a tag, or any other ref ending in it. And
   `rev-parse` has to exit 1, finding nothing the guard's `origin/held-deployment` would resolve to in the checkout.
   Where either finds the name, pick another rather than deleting the ref it found, and pick one nobody will push to
   `origin` as a branch or a tag: the wrapper's pull asks `origin` for that name on every launch and the guard's fetch
   before every polling pass, and a branch the fetch finds writes the tracking ref the guard then reads. Set
   `ORCHESTRATOR_BASE_BRANCH=held-deployment` in the checkout's `.env`, editing an existing line rather than adding a
   second one, since the wrapper and the poller each read the first; a value in the environment the wrapper starts
   with, such as a unit's `Environment=`, wins over the file, so change it there too. The wrapper's pull of that branch
   then fails on every launch, warning `self-update failed -- running existing code`, and the guard finds nothing to
   restart for. Returning the checkout to its base branch takes whatever `origin` carries there at the next launch,
   which is another deployment.
2. Bring the environment and settings to the revision as the [developer guide](../development.md#source-checkout-setup)
   describes: `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync` while nothing uses the checkout's `.venv/`, keeping the
   checkout's `.env` and comparing it with the revision's `orchestrator/service/.env.example` and
   `.env.example.advanced`.
3. Run the developer guide's local startup-settings check under
   [direct launch commands](../development.md#direct-launch-commands).

Either way, the selected build's `REPOS` names only the repositories it may touch, and at least one, beside an
explicit `WORKTREES_DIR`; where no compatible repository is left, polling stays stopped. Before the first start, print
the targets and the `WORKTREES_DIR` the build resolves, with `ORCHESTRATOR_PYTHON` set to the package environment's
interpreter as for [saving its templates](#save-the-installed-versions-templates), or to
`"$ORCHESTRATOR_CHECKOUT/.venv/bin/python"` for a source checkout:

```sh
env -i HOME="$HOME" USER="$USER" PATH="$PATH" "${ORCHESTRATOR_PYTHON:?}" -I -c '
from orchestrator import config

for spec in config.default_repo_specs():
    print(spec.slug, spec.target_root)
print("WORKTREES_DIR", config.WORKTREES_DIR)
'
```

It reads the settings file the build reads and takes nothing from the shell but the three variables it names, so add
any `REPOS` or `WORKTREES_DIR` a unit, drop-in, or launch environment sets, which wins over the file. It exits 1 with
the reason where a setting is invalid or, for a package, no target is selected. Keep polling stopped if it names a
repository left out, or a developer-fallback target nobody chose.

The setup checks prove settings, targets, tokens, and agents, not that the selected build reads the live workflow
state, so the first start is where the two meet. `run --once` is no dry run either: it performs one real polling tick,
label setup, pickup, and agent launches included ([run modes](#run-modes)).

Start deliberately and watch the first ticks in the journal and `LOG_DIR/orchestrator.log`: run
`chipping-orchestrator start` for the service, `chipping-orchestrator run` or `run --once` in the foreground, and
`./run.sh` or the developer guide's [launch commands](../development.md#direct-launch-commands) for a source checkout.
A diagnostic in which the selected build refuses an issue, a record, or an artifact as unsupported or unreadable is a
refusal that needs manual disposition: hold the issue with `paused` if nothing holds it yet, keep everything it names,
and decide by hand. No migration will run for it, and no later tick will repair it.

Restore supervision once the started build behaves, stopping a foreground start first so the supervised process does
not poll beside it. For the service, run `systemctl --user enable chipping-orchestrator.service`, which `init` also
does, so the user manager starts it again at boot; re-enable the timers and crontab lines held above with the selected
build's launch syntax, and keep the pipx pin until the next deliberate upgrade. For a source checkout,
`systemctl --user enable --now <unit>` restores a development unit, which launches `run.sh` on the held revision. Held
work rejoins only once a human has disposed of what it carried, by removing `backlog` or `paused`, or by adding its
repository, and every entry sharing its clone, back to `REPOS`.

## Continuous integration

[`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs Ruff, WPS, pytest with an informational
coverage report, `poetry build`, and separate wheel and sdist smoke installs on every push to `main` and every pull
request. It installs Poetry 2.5.1 with `pipx`, checks the committed [`../../poetry.lock`](../../poetry.lock) with
`poetry check --lock`, then installs runtime and development dependencies with `poetry sync --no-interaction`.
`poetry run` executes the checks without changing the environment. The coverage report sets no minimum threshold.

The job runs the whole set on Python 3.12, 3.13, and 3.14. These are the versions CI verifies within the range
[`../../pyproject.toml`](../../pyproject.toml) admits: `requires-python = ">=3.12"` names a floor and no ceiling, so a
newer interpreter installs without CI coverage. The explicit classifiers name only the three tested versions. All
matrix jobs install the same pins from the same lockfile. `actions/setup-python` provides each matrix interpreter,
which `poetry env use "$(command -v python)"` selects explicitly. `fail-fast: false` keeps the remaining jobs running
when one fails. Branch protection must require `ci (3.12)`, `ci (3.13)`, and `ci (3.14)`
([`../security.md#required-checks`](../security.md#required-checks)).

The packaging steps prove the distribution independently of the editable checkout. `poetry build` uses poetry-core
and builds both artifacts from the tree; installing the sdist separately catches files missing from the archive even
when the wheel works. Each smoke step creates its own `python -m venv`, installs the artifact with that environment's
`python -m pip install`, changes directory outside the checkout, runs `chipping-orchestrator --help`, and reads both
`.env` templates back out of the installed package. The flat package is declared under `[tool.poetry].packages`, and
the two templates beside it under `[tool.poetry].include`, by name, so neither artifact depends on a glob or an
ignore rule to carry them. These environments contain only the distribution and its declared runtime dependencies,
resolved fresh from PyPI, so an undeclared dependency supplied by the project lock cannot hide a packaging error.
The smoke steps configure nothing, and need nothing configured: the command line is read before any owner that
resolves the settings is imported, so `--help` answers even where a `REPOS` value would abort a real launch, and the
template owner imports no configuration at all.
[`../../tests/repository/test_distribution_contents.py`](../../tests/repository/test_distribution_contents.py)
builds both artifacts with `poetry build` into temporary storage and checks that each carries the two templates with
the text the checkout holds.

The job declares `timeout-minutes: 20`, generous next to the few minutes a green run takes and far under the six-hour
default GitHub would otherwise cancel it at; the reasoning that ceiling serves is the same one the scans below are
bounded by. The workflow also declares a `concurrency` group of
`${{ github.workflow }}-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}` with
`cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. A pull request runs in a lane per ref, and a second
push cancels the run its own earlier push started rather than leaving two runs racing for a runner and reporting
checks against a commit nobody is reviewing. Every other run — a push to `main` above all — is keyed on its own run
id, so it shares a group with nothing. That, rather than the flag, is what makes those runs uncancellable:
`cancel-in-progress: false` protects a run that has started, but GitHub keeps at most one pending run per group and
cancels the one each newcomer replaces, so under a shared group a third push would evict a queued `main` run while the
first still held the runner. A CI run on `main` is the record of what that commit does, and no later push may erase it,
waiting or started.
[`../../tests/repository/test_ci_workflow.py`](../../tests/repository/test_ci_workflow.py) holds that concurrency
block, the interpreter matrix and its floor against `requires-python`, the packaging steps, and this page's versions
against the matrix that proves them.

Ruff rules live in [`../../pyproject.toml`](../../pyproject.toml) under `[tool.ruff.lint]`; WPS is selected inline so
Flake8 does not duplicate Ruff's checks; dev tools are declared in `[dependency-groups]`. The only on-disk Flake8
config is [`../../.flake8`](../../.flake8). WPS uses its default rules and complexity limits. Exact-path
`WPS410` / `WPS412` exclusions preserve the deliberate package APIs; no structural rule is waived.

Most initializers are markers. The declared publishers retain explicit `__all__` surfaces for distribution
metadata, configuration, agent and GitHub operations, scheduling, workflow entry, usage parsing, and analytics
recording. `tests/repository/test_package_exports.py` checks those surfaces and requires every other initializer
to bind nothing. These API exclusions remain exact-path unless a maintainer deliberately redesigns the API.

Resolved process values live in `orchestrator.config`. Importing or reloading that package invokes the
`environment` resolver and binds fresh values, while callers retain the same module object for attribute reads
and patches. Repository types live in `config.models`, and token resolution in `config.credentials`.

Refactors separate responsibilities and move callers, mocks, and ownership documentation together. Every resulting
module must satisfy the default limits; a refactor cannot add an exclusion, an inline suppression, or a raised
complexity limit. `flake8 orchestrator tests --select=WPS` must pass without diagnostics. The isolated run,
`flake8 --isolated --select=WPS orchestrator tests`, must report only the deliberate initializer violations;
every remaining file/rule exclusion must correspond to one of those diagnostics.

The rule set is Ruff's own. `[tool.ruff.lint]` in [`../../pyproject.toml`](../../pyproject.toml) declares no `select`,
so what `ruff check orchestrator tests` enforces is whatever the `ruff` resolved in
[`../../poetry.lock`](../../poetry.lock) ships as its defaults, plus the single `E501` opted into
through `extend-select`. That pair is the whole contract.
`[dependency-groups]` names a floor (`ruff>=`) rather than a version, and `poetry sync` installs the lockfile's
resolution, so what settles the rule set is the lock and what moves it is a regenerated one — which is what the weekly
`workflow:dependencies` PR carries when it bumps the tool. A `select` of this repo's own would be a copy of those
defaults taken on the day it was written, and a copy buys only the drift it cannot follow: every rule the tool adds
afterwards stays off, unreported, and unanswered. Nothing is waived tree-wide under the contract either. The only
suppressions are the exact-path per-file entries below and the inline `# noqa: <CODE> - <reason>` directives naming
the rule each covers and why, so a rule a new `ruff` adds reports here on the first run after the bump.

Ruff and the line-length test enforce a repository-wide 120-column target set once as `line-length` under
`[tool.ruff]` in [`../../pyproject.toml`](../../pyproject.toml). Ruff applies it to Python via the opted-in `E501`
rule; the first-party
[`../../tests/repository/test_line_length.py`](../../tests/repository/test_line_length.py) reads the same value and
applies it to tracked Markdown/text files, exempting fenced code blocks, single unbreakable tokens (e.g. long URLs),
binary assets, the lockfile, and the verbatim `LICENSE`.

`[tool.ruff.lint.per-file-ignores]` in that same file carries one waiver, `PLC0414`, over six exact paths. The rule
reports `import X as X`, which is the spelling `F401` is answered with here: a name aliased to itself is a re-export
both Ruff and a reader can see, and the import that drops the alias reads as dead. Only one of the six is nothing but
a facade: `orchestrator/observability/dashboard/theme.py` implements nothing and reads the five style owners back
under one name, which is the theme object a dashboard page hands every panel. The other five seed and drive a stage's
scenarios and carry the re-export beside that work — the types, the mid-run effects, and the publication heads a
sibling test module reads a case back through, bound there and read only there. A waiver covers the whole file rather
than the import that earned it, so what holds the rest of the file to the rule is the check below rather than the
entry. `PLC0414` is in the default set, so those entries are read by `ruff check orchestrator tests` itself rather
than by an audit beside it; a package initializer needs no entry, because Ruff never reports the rule there. Each key
is an exact path rather than a glob, and
[`../../tests/repository/test_reexport_aliases.py`](../../tests/repository/test_reexport_aliases.py) holds the list
against the tree: a self-alias in a module the list does not name, one on a name its own module already reads, or a
key that globs fails there.

`BLE001` is answered a line at a time instead. The rule reports a blanket `except Exception` / `except BaseException`,
and it is in the default set beside `PLC0414`, so those answers are what `ruff check orchestrator tests` reads and a
handler missing one fails CI. No per-file entry would fit: what earns a waiver is one handler rather than the file
around it, so each carries an inline `# noqa: BLE001 - <reason>` naming what its blanket catch protects, and every
other handler beside it stays held to the rule. Three families earn one. The GitHub-API calls — the best-effort PR
notices, the issue and pull-request reads, and the child-issue create under `orchestrator/git/base_sync/` and
`orchestrator/workflow/` — catch blind because PyGithub raises its own `GithubException` and the transport errors
underneath it alike, and a narrower handler would turn a connection reset into a stranded run. The fail-open guards
under `orchestrator/observability/analytics/` and in `orchestrator/workflow/late_split/telemetry.py` catch blind so a
parser bug or an unwritable sink costs the record and never the tick that produced it. And two test helpers keep
whatever escapes a worker thread so the main thread can assert on it. Ruff exempts a blind handler that reports
through a logger it can resolve back to `logging` itself, which is why a guard logging through an imported `log`
carries a directive where the identical one beside its own `getLogger` call does not.

`lint.external` in [`../../pyproject.toml`](../../pyproject.toml) is what keeps a directive from reading as dead when
it answers a rule the run does not enable. `RUF100` — itself in the default set — reports a `# noqa` naming such a
rule and offers to delete it. The blind-handler directives above need no entry, because `BLE001` is in the default set
and the run reads them itself. `N802` is the one code outside it, and listing it is what leaves the single directive
naming it in place with the rule that would strip it still on.

That one entry is a narrow claim rather than a clean bill. `N802` answers for the one directive there is — on the
`DataFrame` method of the test double standing in for the `pd` handle a dashboard page is handed — and for nothing
wider. `ruff check orchestrator tests --select=N802` reports two deliberate names the convention does not reach, a
test spelling codex's `-C` flag and a shouted stub that raises where a call is expected, so the tree is not held to
that rule the way the default run holds it to `BLE001`.

[`../../tests/repository/test_noqa_directives.py`](../../tests/repository/test_noqa_directives.py) holds three
readings, two of them the halves of that declaration. It runs Ruff itself over the two trees under the configured
selectors plus `RUF100` — which rules a selector enables is Ruff's answer and not one a prefix test could reproduce,
since `F` covers `F401` and not `FLY002` — so a directive naming a rule that is neither selected nor listed fails
there rather than surviving until someone strips it. The other half is the one Ruff has no reading of: a listed code
no directive carries suppresses nothing, and is read off the tree instead. The third sits under both and is what the
contract above needs beyond them: it tokenizes every module and fails on a comment that opens a suppression and names
no rule for it, line-level `# noqa` or file-wide `# ruff: noqa` alike. Ruff honours either spelling and reports
neither, so a blanket waiver is the one suppression the two halves would let through.

Import order is Ruff's answer too, under `[tool.ruff.lint.isort]` in [`../../pyproject.toml`](../../pyproject.toml),
and `I001` is in the default set with the two rules above, so the run CI makes is what holds that order. One setting
is declared there. `combine-as-imports` keeps every member a module is read for on the single statement that names it:
Ruff's default hands an aliased member a statement of its own, and the modules here read most of their neighbours
under an alias — a stage module and its tests name several of a package's owners in one `import ... as ...` — so the
default would spell one read as a statement per alias and push whole files past the twelve-import ceiling `WPS201`
holds them to. [`../../tests/repository/test_import_sorting.py`](../../tests/repository/test_import_sorting.py) runs
the rule on its own beside that, so an unsorted block is reported next to the tests a change was written for and not
only by the lint step beside them.

`WPS235` uses its default ceiling of eight names per `from ... import` statement. Sorted imports merge all
reads of one module into one statement, so splitting an oversized read across several statements cannot satisfy
that limit. Read values through their actual owner, keep explicit type and fixture imports where needed, and
separate responsibilities when a coordinator needs too many sibling owners. Callers import defining owners directly.
Neither `WPS201` nor `WPS235` is relaxed to accommodate a refactor, and no
facade, dynamic dependency lookup, or replacement exemption substitutes for a direct owner.

The CI workflow declares `permissions: contents: read` so the run's `GITHUB_TOKEN` is read-only and cannot publish
artifacts, push tags, or comment on PRs. The job uses no repository secrets, so PRs from forks run safely under the same
scope.

[`../../.github/workflows/codeql.yml`](../../.github/workflows/codeql.yml) runs CodeQL's default queries against the
Python source on every push to `main`, every pull request targeting `main`, and a weekly schedule. Its one-language
matrix fixes the language at `python` and uses `build-mode: none`, so the scan analyzes source without installing or
executing the project. The workflow keeps `contents: read` as its top-level token scope; the analysis job restates it
and adds only `security-events: write`, which the CodeQL action needs to upload its results. It reads no secrets.

[`../../.github/workflows/scorecard.yml`](../../.github/workflows/scorecard.yml) runs OpenSSF Scorecard — the
supply-chain grader behind the README badge — on a weekly `schedule`, on every push to `main`, and on
`workflow_dispatch`, which is how a maintainer can prove a change to it works without waiting a week. It sets
`publish_results: true`, so a run on `main` publishes the score the badge and the public
[viewer](https://scorecard.dev/viewer/?uri=github.com/chippingway/chipping-orchestrator) read, and hands the SARIF it
produces to `github/codeql-action/upload-sarif`, which files each finding as a code-scanning alert on this repo. It
declares the same top-level `contents: read` and reads no secrets; the job adds exactly the two grants those two
publications need — `id-token: write` for the OIDC token the publication is authenticated by, and
`security-events: write` for the SARIF upload — and restates `contents: read`, because a job-level `permissions:` block
replaces the top-level one rather than adding to it. Nothing gates on the grade: a low score is a set of alerts to
triage rather than a failing run, and the workflow is outside the required checks a merge waits on
([`../security.md#required-checks`](../security.md#required-checks)).

Every `uses:` in every workflow names a full 40-character commit SHA with the release it belongs to in a trailing
comment (`uses: owner/action@<sha> # v1.2.3`), so a retagged release cannot change what a run executes.
[`../../tests/repository/test_workflow_action_pins.py`](../../tests/repository/test_workflow_action_pins.py) holds that
shape for every workflow, but nothing checks the comment against the SHA it labels, so a hand edit has to move both
together; Dependabot's `github-actions` updates rewrite the pair.

Each security scan bounds its own job the same way: 30 for the CodeQL analysis, 20 for Scorecard and the
vulnerability scan, 15 for the dependency review. A job that hangs otherwise runs until GitHub's six-hour default
cancels it. The dependency review is a required check and CodeQL's findings are enforced by a ruleset
([`../security.md#required-checks`](../security.md#required-checks)), so a hung job
holds a merge for those six hours instead of failing in the minutes the scan takes. Scorecard, the vulnerability scan,
and CodeQL's scheduled pass have nobody watching, so a hung one holds a runner while reading as a scan that has yet to
report rather than as one that failed. The documentation build and deploy jobs each allow 10 minutes: the build is
a required check, so a hung one would hold a merge, and a hung deployment from `main` holds the `pages` concurrency
group, so later deployments wait.
[`../../tests/repository/test_workflow_job_timeouts.py`](../../tests/repository/test_workflow_job_timeouts.py) holds a
declared timeout, shorter than that default, on every job in all six workflows, and holds the list it walks against
the workflow directory, so a seventh workflow arrives with a timeout rather than outside every check.

[`../../.github/dependabot.yml`](../../.github/dependabot.yml) opens weekly update PRs for `github-actions` and `pip`
(Python `pyproject.toml` + `poetry.lock`). For routine version updates, `github-actions` uses the ecosystem-wide
cooldown GitHub supports and holds every release for 30 days. The `pip` entry holds a major release, and anything SemVer
does not classify, for 30 days; it holds a minor or a patch for 14 days. Cooldowns do not delay security updates. The
`pip` entry limits update PRs to direct dependencies with `dependency-type: direct` in its `allow:` block.
Each entry also declares the service labels GitHub stamps on the PRs it opens:
`workflow:dependencies` on every update PR, so the whole dependency queue is one label filter, plus
`workflow:github_actions` or `workflow:python:pip` naming which ecosystem moved. Those three share the `workflow:`
prefix with the labels the orchestrator writes but are not workflow states — nothing in the tree reads them, so a PR
carrying one is not an issue in a stage. `github-actions` and `pip` above name the ecosystems Dependabot updates, not
labels. The `pip` entry uses `versioning-strategy: increase` so dependency updates raise runtime lower bounds to the
locked versions tested by CI.
[`../../tests/repository/test_dependabot_config.py`](../../tests/repository/test_dependabot_config.py) holds the
cooldown policies, the direct-dependency scope, the versioning strategy, and the labels against the config.

Create all three custom labels in GitHub's **Issues → Labels** before Dependabot runs. The orchestrator does not
create these service labels, and [Dependabot ignores custom labels that do not exist][dependabot-labels].

`workflow:python:uv` is retired and remains on historical PRs. When reviewing `pip` updates, verify that they change
the manifest and lock together, cover `dev`, `docs`, and `dashboard`, raise runtime lower bounds to the locked
versions, preserve one entry per package and the major caps, honor cooldowns, and carry the service labels above.
Use manual group bumps if Dependabot cannot update a group cleanly.
[`../../.github/workflows/dependency-review.yml`](../../.github/workflows/dependency-review.yml) runs
`actions/dependency-review-action` on every PR and fails the check when a PR introduces a vulnerable or non-compliant
dependency.

[`../../.github/workflows/vulnerability-scan.yml`](../../.github/workflows/vulnerability-scan.yml) is the standing
scan beside that diff gate: a weekly `schedule` plus `workflow_dispatch`, the second so an edit to it is verifiable
from the Actions tab instead of a week away. It exports the pins from [`../../poetry.lock`](../../poetry.lock) with
`poetry export --all-groups --without-hashes -f requirements.txt`, then audits them with `pip-audit` and fails the job
when a published advisory names one of them. The job installs `poetry-plugin-export` at the workflow's exact pin into
the Poetry tool environment with `pipx inject`; exporting does not require installing the project. Why the export and
audit are shaped that way:

- **`--all-groups`** covers the `dashboard` and `docs` groups as well as the runtime and `dev` ones, so the audit is
  the whole lockfile rather than the subset a default `poetry sync` installs.
- **Environment markers are stripped** from the export before the audit. A pin kept for another platform
  (`colorama` under Windows, `tzdata`) is a version this repository still ships, and an audit reading markers would
  skip it as inapplicable to the Linux runner — silently, and while reporting success.
- **The scanner is CI-only.** `pipx run` runs `pip-audit` from a throwaway environment, so it audits the pins without
  becoming one: it appears in neither [`../../pyproject.toml`](../../pyproject.toml) nor the lockfile, and the
  version range there is what keeps a new major from changing the CLI under the job.
- **`--no-deps --disable-pip` and `--strict`.** The exported versions are already the complete pinned set, and the
  two collection flags are what have `pip-audit` read them as written. `--no-deps` on its own still hands the file to
  pip's resolver and audits whatever that resolves to — a fresh resolution, which is the step the lockfile exists to
  settle. `--strict` closes the one hole left in that reading: a pin PyPI has no record of is otherwise skipped and
  reported under a green run, while a line carrying no exact version fails the job with or without it. Neither flag
  is a claim about the advisory data — a service that errors out fails the run on its own, and a pin no advisory
  names is simply a clean result.

The job declares the same `permissions: contents: read` and uses no secrets. It is not a required check and cannot
be one — it never runs on a pull request — so a red run is triaged from the Actions tab. Turning one of its findings
into a bump PR is Dependabot's job, which is why enabling Dependabot security updates is on the operator list in
[`../security.md#dependabot-security-updates`](../security.md#dependabot-security-updates). The audit reads the whole
lockfile while those updates reach only what the `allow:` rules above name, so a finding against a transitive pin
those rules do not name is cleared by widening them or by hand rather than by waiting for a PR.
For manual security fixes younger than 14 days, follow the
[manual security-fix procedure](../security.md#dependabot-security-updates).

### Dependency tooling

Poetry is developer tooling for source checkouts; package users install with pipx. It keeps checkout environments
in `.venv/`, and the default sync installs runtime plus `dev` dependencies.
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with docs` and
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard` select optional groups; use `--with docs,dashboard`
for both. Sync removes unselected groups. `poetry run` executes commands without syncing. The wrapper's install policy,
timeouts, and sync requirements are documented under
[Launcher dependency refresh](../development.md#launcher-dependency-refresh).

Poetry uses an inherited `VIRTUAL_ENV` or non-base `CONDA_PREFIX` even with `virtualenvs.in-project = true`.
Prefix every manual Poetry command with `env -u VIRTUAL_ENV -u CONDA_PREFIX` so it selects this checkout's `.venv/`.
Agent and verify subprocesses remove `VIRTUAL_ENV` and its `bin` directory from `PATH` for all managed repositories;
Conda markers and their `PATH` entries stay together so Conda-based targets keep a consistent activation. Commands for
a Poetry target launched from Conda must explicitly deactivate it or use the manual override above. Without that
override, `poetry sync` can remove unrelated packages from the operator's active Conda environment; the subprocess
filter does not protect it. The launcher clears both markers for its dependency install, while its Python process
inherits the caller's Conda activation.

The manifest accepts Poetry `>=2.4,<3`; CI and developer setup pin `2.5.1`. Poetry 2.4 is the minimum for the
[release-age setting][poetry-release-age] in [`../../poetry.toml`](../../poetry.toml), which holds new releases for
14 days during resolution. Use `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry lock` for dependency or group changes and
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry check --lock`
to detect a stale lock. A project version bump does not change the lock. Never commit package sources or mirror URLs.
If a mirror is required, validate a maintainer-local mirror plugin's output before using it; the committed lock must
stay free of `[package.source]` entries.
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry show --outdated --top-level` reports outdated direct dependencies.

Keep runtime dependencies' lower bounds and major-version caps in the manifest, and keep each locked version
within its declared range. Repository checks accept lock-only updates within those ranges. Raise runtime lower
bounds with manual updates; for a lock-only security update, raise the affected lower bound to exclude vulnerable
releases. Use the [manual security-fix procedure](../security.md#dependabot-security-updates) for security fixes
younger than 14 days.

[dependabot-labels]:
  https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#labels
[poetry-release-age]: https://python-poetry.org/docs/configuration/#solvermin-release-age

## Publishing the documentation

The documentation is a static MkDocs site hosted by GitHub Pages at
<https://chippingway.github.io/chipping-orchestrator/>. GitHub supplies the address and HTTPS; a custom domain is
optional. The Markdown under `docs/` is the source for both the website and GitHub's directory view, with
[`../README.md`](../README.md) serving as the site's homepage.

### Local preview and build

Install the optional `docs` dependency group from the lockfile, then start the local preview:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with docs
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run mkdocs serve
```

Open `http://127.0.0.1:8000/` to browse the preview. To check the deployable HTML, build it once and point the
checks at that output, as the **Documentation** workflow does:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run mkdocs build --strict
env -u VIRTUAL_ENV -u CONDA_PREFIX DOCS_SITE_DIR=site poetry run pytest tests/repository/test_docs_site.py \
  tests/repository/test_docs_output.py tests/repository/test_docs_navigation.py
```

The build writes to the ignored `site/` directory. `DOCS_SITE_DIR` makes `tests/repository/test_docs_output.py` check
the generated links, heading anchors, search index, sitemap, [page descriptions](#page-descriptions), and homepage AI
buttons of that output instead of building a copy of its own. A directory it names that holds no built site fails the
check rather than being rebuilt or skipped. Without the variable, the same `pytest` command builds a fresh strict copy
into a temporary directory. Links in the Markdown sources are checked by `tests/repository/test_doc_links.py`, which
needs no documentation builder and runs with the rest of the suite in [Continuous integration](#continuous-integration).
The `docs` group is separate from runtime and development dependencies, so the default `poetry sync` does not install
the documentation builder.

[`../../mkdocs.yml`](../../mkdocs.yml) defines the navigation, site URL, search-enabled theme, the template directory
the theme's `custom_dir` layers over it ([Site navigation](#site-navigation), [Page descriptions](#page-descriptions)),
and validation rules. Every page must appear in navigation; missing pages, links, and heading anchors fail the strict
build. The hook in [`../../.github/scripts/docs_site.py`](../../.github/scripts/docs_site.py) preserves GitHub-style
heading anchors for unique headings and turns links to repository files outside `docs/` into GitHub links while
building. Repeated headings use Python-Markdown suffixes such as `_1` instead of GitHub's `-1`. Relative links between
documentation pages keep pointing within the site. Link examples in code blocks are left intact, and the source files
retain the relative paths the repository's documentation checks validate.

### Site navigation

`nav:` in [`../../mkdocs.yml`](../../mkdocs.yml) groups the pages by what a reader came to do:
**Contracts**, **Operate** (quick start, settings, operations, snapshot capability check, security),
**How it works** (architecture, the state machine, and the agents), **Observability**, **Releases**, and **Developers**,
beside the homepage the site name links to. [`../README.md`](../README.md) lists every page under the same grouping for
readers browsing on GitHub. A page's URL follows its path under `docs/`, not its place in `nav:`, so moving a page
between groups changes no address. The templates in [`../../.github/docs-theme/`](../../.github/docs-theme/) render that
list over the bundled `mkdocs` theme:

- The top bar names each top-level entry once, as a plain link rather than a dropdown. A section links to its first
  page, which makes that page the section's landing page, so an area's overview goes first. The current section is
  underlined, as are top-bar section links on hover and keyboard focus. Every top-bar link and the theme toggle show a
  white outline on keyboard focus. Search, buttons to ask ChatGPT or Claude about the project, a link to the repository,
  and the light / dark / auto theme menu sit on the right. The AI buttons open a new tab with a prompt pointing to the
  documentation homepage from `site_url`. The documentation homepage offers each AI button once, only in the top bar;
  `tests/repository/test_docs_output.py` checks this in the built site. Below a viewport width of 1200px, the top bar
  collapses into a menu so both AI buttons fit.
- The sidebar lists the pages of the current page's top-level section above that page's own headings. A subsection
  there is a link to its first page, and opens onto its own pages only while it holds the current one.
- Previous and next links sit under the page, where the theme's `n` and `p` keyboard shortcuts find them.

`tests/repository/test_docs_navigation.py` builds a sample site through the templates to check the navigation rules.
Styling is not tested. The test needs the `docs` group but not `DOCS_SITE_DIR`, and the **Documentation** workflow
runs it beside the two checks above.

### Page descriptions

A page summarizes itself for search results and link previews with `description` front matter, a YAML block that opens
the Markdown file, before its title:

```markdown
---
description: How the orchestrator is checked, launched, supervised, and reconfigured.
---
# Operations
```

Write the description as one or two sentences of plain text, about 160 characters at most so a search result can show
it whole. Markdown in it is not rendered, and HTML is shown as text. Quote the value when it contains a colon followed
by a space or a space followed by `#`, or starts with a YAML indicator such as `'`, `"`, `&`, `*`, `[`, or `{`, so it
parses as one string. Front matter is held to the same 120-column line target as the rest of the page
([Continuous integration](#continuous-integration)), so a description longer than one line allows is written as a
`>-` folded block indented under the key, as every described page under `docs/` does; its lines join on single spaces
and need no quoting.

The template [`../../.github/docs-theme/main.html`](../../.github/docs-theme/main.html) overrides the bundled `mkdocs`
theme's `site_meta` block, and writes the value into the page's single `<meta name="description">` tag, HTML-escaped. On
the homepage the page's own description takes precedence over `site_description` in
[`../../mkdocs.yml`](../../mkdocs.yml), which remains the homepage's fallback; any other page without front matter emits
no description. The rest of that block is the theme's own, so every page keeps the canonical URL and the rest of the
head metadata the bundled theme gives it; a page without front matter has the bundled head plus the two verification
tags described in [GitHub Pages setup](#github-pages-setup) and the custom theme stylesheet, with the same search entry
as under that theme.
`tests/repository/test_docs_site.py` builds sample sites through the template to hold each of those rules, and checks
that `mkdocs.yml` names the template directory. GitHub's file view shows front matter as a table above the page.

`tests/repository/test_docs_output.py` holds the repository's own pages to those rules in the built site: the homepage
and each landing page it lists emit exactly the description their front matter gives, and no two of those descriptions
match. It reads the front matter without a YAML parser, so a page it lists writes its description as a plain or `>-`
folded value rather than a quoted one.

### GitHub Pages setup

In `chippingway/chipping-orchestrator`, configure these settings once:

1. Open **Settings → Pages**, and select **GitHub Actions** under **Build and deployment → Source**.
2. Create or open **Settings → Environments → github-pages**, and restrict deployment branches to `main`.
3. In the repository's **About** panel, open its settings and set **Website** to
   `https://chippingway.github.io/chipping-orchestrator/`.

The `extrahead` block in [`../../.github/docs-theme/main.html`](../../.github/docs-theme/main.html) adds the Google
Search Console `google-site-verification` and Bing Webmaster Tools `msvalidate.01` meta tags to every page, including
the 404 page; update their verification values when moving the site or changing the verification owner.

[`../../.github/workflows/docs.yml`](../../.github/workflows/docs.yml) builds and checks every pull request and the
pushes to `main` that change a documentation source, using the committed lockfile. The `pull_request` trigger carries
no path filter, so a pull request touching no documentation still reports the `build` check that branch protection
requires ([`../security.md#required-checks`](../security.md#required-checks)). Pull requests only build and validate.
A push to `main` runs the workflow when it changes a path its `push` filter lists — the published pages, the MkDocs
configuration and build hook, `.github/docs-theme/` for the site template, the workflow, the documentation tests, and
the dependency manifests — then uploads the generated site and deploys through the `github-pages` environment. The
deployment job alone has `pages: write` and `id-token: write` permissions; no personal access token is needed. The
**Documentation** workflow can also be run manually from **Actions**, selecting `main` to publish or another branch to
validate its build.

Documentation runs publishing `main` share a `pages` concurrency group: a newer run replaces a queued run so the
latest documentation wins, while `cancel-in-progress: false` lets an active deployment finish. CI gives every `main`
run its own group to preserve each merged commit's test record ([Continuous integration](#continuous-integration)).
Pull-request documentation runs share a group per ref and cancel in progress when superseded.

Each run builds the site once and checks that `site/` output before any upload, so the pages a `main` run publishes are
the pages its checks read. Only the generated `site/` artifact is uploaded. Python source links, agent instructions, and
configuration examples lead back to the repository; the site does not publish the checkout or notes under `plans/`.

## Run modes

### Launch commands

Use the command installed by pipx:

- `chipping-orchestrator run` — continuous polling.
- `chipping-orchestrator run --once` — one real polling tick, including label setup and possible agent launches.
- `chipping-orchestrator run --cleanup-terminal-artifacts` — reclaim the worktrees and branches of finished issues, then
  exit. Polls no issue, ensures no labels, and writes **no workflow state** — no label, no pinned state, no comment.
  It does delete refs, which is what it is for: the orchestrator-owned branches it proved reclaimable go from the
  local clone *and* from the remote, after the fail-closed gates cleared each one. It connects read-only clients and
  asks each repository only about the issues and pull requests its artifacts name.

  Safe to run on the same host as the polling process because it refuses to run *beside* it: every polling run holds
  a shared `flock` claim on `WORKTREES_DIR/.artifact-maintenance.lock` for its whole life, this mode needs that claim
  exclusively, and a refusal defers the whole pass and exits 0 (a deferral is what the mode was asked for, not a
  failure a timer unit should report). Two of these runs exclude each other the same way, and the daemon's own
  recurring pass takes the same claim — from inside its own scheduler barrier, so it only gives its presence up
  once it has stopped admitting and drained, and takes it back before admitting again. A second daemon on the host
  therefore cannot be submitting work while either of them deletes. A polling process that starts while a pass is
  running waits for it (no deadline, because polling through a teardown is never safe — though only for a lock
  something is holding: one that does not work at all is reported instead, and the pass simply does not act); a
  pass gives the host back
  at a candidate boundary once it has held it for 120s, with whatever it did not reach owed to the next pass.
  Point a nightly service
  timer at it for hosts whose orchestrator is not always up; a host running the daemon continuously already gets a
  pass between polling passes — every `TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS`, or inside
  `TERMINAL_ARTIFACT_CLEANUP_WINDOW` where one is set ([When it runs](#when-it-runs)) — and the timer will simply
  defer.
- `chipping-orchestrator run --log-level DEBUG` — verbose logs.

The polling flags belong to `run`: given before any command, as in `chipping-orchestrator --once`, they are a usage
error (exit status 2) naming the `run` form that means them. The bare `chipping-orchestrator` prints the help listing
every command and exits 0, as `--help` does, and `chipping-orchestrator --version` prints the installed version. All
three answer before any configuration is read, so they work on a host with no `.env` or an invalid one.

Source-checkout module launches and the restart wrapper are for developers; see the
[developer guide](../development.md#direct-launch-commands).

On first start the orchestrator creates the workflow labels and the `backlog` / `paused` /
`workflow:community_contribution` control labels on the repo, then begins polling open issues every `POLL_INTERVAL`
seconds. It creates only the labels a repo lacks: on a repo it drove before the labels were namespaced, each
namespaced label is created beside its pre-namespace one, which stays defined and stays on every issue carrying it as
a repository label that routes nothing ([obsolete bare labels](../state-machine.md#obsolete-bare-labels)).

### Poetry migration for operators

Poetry applies to developer source checkouts. The
[source-tooling migration](../development.md#poetry-migration-for-source-checkouts) covers checkout environments,
verification commands, and development service units. Published-package users install and upgrade with pipx.

### Launcher dependency refresh

Dependency refresh by the source wrapper is developer tooling. Its fingerprints, timeout behavior, and optional
groups are in the [developer guide](../development.md#launcher-dependency-refresh). Stop all processes using a pipx
environment before upgrading or reinstalling the package.

## Running more than one poller

The supported topology is **one host**. More than one polling process may run there against the same repositories —
a second daemon, or a `run --once` beside one — provided every one of them resolves the same `WORKTREES_DIR`, and
the in-process scheduler guards (a duplicate active issue, the caps, the family slot) still apply first inside each.
Left unset, `WORKTREES_DIR` defaults beside the first configured target — the first `REPOS` entry, or
`TARGET_REPO_ROOT` without `REPOS` ([default](../configuration.md#workspace-and-agent-identity)) — so pollers whose
lists start with different repositories resolve different roots unless every one of them sets it explicitly.

The shared issue claims coordinate workflow work. Set the same `WORKTREES_DIR` in every poller's process or service
environment. Installed pollers under one account read the same `~/.config/chipping-orchestrator/.env`; use process
or service overrides for different `REPOS` lists and a distinct absolute `LOG_DIR` for each poller, including
each `run --once` beside it. Override any explicit `ANALYTICS_LOG_PATH` and `TRAJECTORY_LOG_PATH` with distinct absolute
paths per poller too; the default analytics path follows `LOG_DIR`. Runtime log rotation and analytics retention
rewrites do not coordinate across processes, so sharing these files can lose records even when issue claims are
separate. Stop every process using a shared pipx environment before upgrading it. Developer source wrappers also
need the isolation described under
[Development restart wrapper](../development.md#development-restart-wrapper).

- **One writer per issue.** Each dispatched issue is taken under a host-local writer claim: an exclusive `flock` on a
  file in `WORKTREES_DIR/.issue-writer-claims/`, named `repo-<id>-issue-<n>.lock` for the repository's numeric GitHub
  id — which no rename or transfer changes, unlike the configured slug or the `owner/name` a poller fetched at startup —
  and the issue number. A poller that finds the issue held by another skips it for that tick — no refetch, guard,
  recovery pass, close receipt, or handler, so no label, comment, or pinned write, no agent run, and no usage or
  evaluation record — and takes the issue up on a later tick once the holder is done. The pre-tick base refresh takes
  the same claim for each worktree it syncs, before it reads the issue, and holds it until that worktree's rebase,
  push, park, or crash recovery is done, so a refresh and a dispatch — or two pollers' refreshes — never write one
  issue at once; a refresh that finds the issue held skips that worktree for the tick with no read, rebase, push, or
  write, and syncs the rest. The terminal-artifact maintenance pass takes the same claim for each candidate before it
  reads the issue and holds it through the deletions, and keeps a candidate whose issue is held with nothing read or
  deleted. A close a refused poll read for the issue
  costs a pinned read, an issue read behind it, and a pinned read behind that, and is kept in its own memory and
  nowhere else: a reopen before then cannot take the reading away, and a later tick sweeps it under the claim. It is
  tied to the late cycle the record names only where the issue still reads closed behind that read and the record read
  behind the issue still names that cycle — a record that moved is read again behind another issue read, a few times
  at most, so a close of a cycle the holder restarted between the reads is tied to that cycle — or, where a retirement
  has just taken the cycle off the record, to the cycle the holder noted on the claim it is retiring, a note read as the
  claim is refused, so a holder letting go during those reads costs nothing — so a cycle the holder settled and an
  operator restarted in the meantime is left alone. One the poller cannot tie to a cycle ends one later only if the
  issue is closed again then. A close the record says ends no cycle is not kept. A poller granted the claim reads the
  issue again behind it before routing it, so it never resumes a stage another poller advanced the issue past since its
  poll, and a close its own poll read ends the cycle the record names only where it still reads closed, or where no
  other poller has held the issue since the poll began (see what a claim file holds, below). Different issues, and one
  issue number in two repositories, never contend. Inside one process the claim is exclusive between threads too,
  logged as `reason=held_here`, with one exception: the receipt a poll posts for a close it observed, and the notice
  a parent posts telling a consumer its snapshot is gone, are comments built to land beside that process's own worker,
  so they are let in alongside one. The skip is logged on `orchestrator.scheduler` as
  `writer claim skip repo=<owner/name> repo_id=<id> issue=#<n> reason=held_elsewhere`, where the name is only a label
  and the id is the key.
- **A parent writes a child under the child's claim.** A decomposed parent's handler writes its children too — the walk
  that relabels a `workflow:blocked` child `workflow:ready`, the seeds that give a child its parent link and ancestry,
  the finalize of a child whose pull request merged, and the notice that a reclaimed snapshot is gone — and each of
  those is made under that child's own claim, off what it reads behind it: the release walk and a merged child's
  finalize read each child again once claimed, and a seed adds to whatever record the child carries by then. A child
  another poller holds is left for a later pass, which parks nothing, and one that poller moved since the walk's scan is
  judged as it reads now: the release walk starts none of them, and the finalize counts it as it stands. An ordinary
  split creates the rest and leaves the held child's seed and its own finalize to the next tick's recovery. Only a late
  split's placement of a held child parks the parent, exactly as a seed that could not be written does. A child whose
  pinned record, read behind its claim, admission refuses is answered the same way: the seed, the recovery's repair,
  and the release write nothing to it and say why only in the log, and the split's summary, finalize, and release wait
  until a record admission takes is back on that child, after which the next tick continues on its own. So do a merged
  child's finalize, which leaves such a child neither finalized nor counted, and its snapshot notice, which stays owed.
  A snapshot's delete holds every recorded consumer's claim, alongside this process's own worker, from its last reading
  of them through the delete and its notices, so one held elsewhere or carrying a record admission refuses keeps the
  ref on the remote, and the owner's terminal with it, until a later pass finds every consumer admitted.
- **What the namespace assumes.** Every participating poller can read each repository's numeric id from GitHub, which is
  what makes two configured spellings of one repository, or a poller started before a rename and one started after it,
  meet on one key. They run as a user that can create and open files in that directory, and see it on a local filesystem
  whose `flock` is honored between them — a network filesystem that emulates `flock` per client coordinates nothing.
  They read one monotonic clock, as every process on a host does unless it runs in a time namespace of its own.
  Anything else that can write the directory can hold a claim, so keep it writable by the orchestrator's user alone.
- **Failures withhold.** A claim that cannot be worked — the namespace cannot be created or opened, or `flock` fails
  for any reason other than another holder — skips the issue as a held one is skipped, with a `reason=unusable`
  warning, rather than letting it be written uncoordinated. Repair the directory and the next tick proceeds.
- **What a claim file holds.** The lock, and a few lines from the last hold on it: a token the poller draws at startup,
  which is how a poller tells another's holds from its own; while a hold retires a late cycle, that cycle's id, which a
  refused poller reads; and the moment the hold let go, on the host's monotonic clock. Every acquisition empties the
  file before signing it, a moment after it takes the lock, and a refused poller reads a note only off a file its hold
  signed and has not stamped as released, so no note outlives a hold that stamped its release. A close a poller's poll
  read is tied to the record it holds next only where every other poller's hold it has found had let go before the
  poll began, so a poller restarted over the namespace its predecessor used is not held up by the tokens that
  predecessor stamped. A hold whose process was killed holding it — `SIGKILL`, an OOM kill, the forced exit past
  `SHUTDOWN_GRACE_SECONDS` — stamps nothing and counts as ending when the next holder finds it; its note, if it left
  one, is read until that holder empties the file, since it was the last hold to write the issue until then. The same
  holds for a hold whose release stamp could not be written. Each line is written whole or not at all: one a file-size
  limit or a full disk lets land only in part is taken back and logged as not written, and a line with no end, or a
  file nobody signed, is never read as a release time or a retiring cycle — only as a hold that ended when it is found.
  That includes an empty file, even the one an issue's first claim on the host creates, since another poller can have
  held and emptied it before that claim locked it. So a close a poll reads on an issue no poller on the host has
  claimed since its predecessor was killed holding it, or ever, and that is reopened before the poller claims it, ends
  no cycle by that reading. Pollers must all run a build that signs and stamps its claims: one that does not is a hold
  nobody sees, and a close read beside it can end a cycle that poller restarted.
- **An owed quota retirement.** Beside an issue's claim file, `repo-<id>-issue-<n>.quota-retirement` holds the
  quota retirement the host owes the issue until the pinned comment takes it. Every Antigravity developer launch arms
  it first, under the claim, as `{"armed": "<id>", "launch": "<token>"}` (`null` for a fresh spawn), and is refused,
  uncharged, with a warning where the host will not take that write — a namespace that takes no new entry with no
  record standing, or a record that takes no write. The attempt's return settles it as `{}` where no quota stopped
  it; a quota stop resolves it to `{"session_id": "<id>"}` — the conversation the failure names, or the launched one
  where it names none — which every poller on the host lands ahead of the issue's next resume plan and before each
  developer launch, refusing the launch until it lands. Once landed it is settled as `{}`, written in place and never
  removed, and every launch waits while it cannot be, so a landed record is never landed again over a conversation
  pinned after it. A resolution the record would not take is held in that poller's memory and written again at each
  check, only for as long as the record still shows the arming it resolves, or nothing: once another poller or an
  operator has resolved or settled it, the memory is dropped. Every write is in place, so a namespace that takes no
  new entry still works once the record stands, and none counts until it is flushed to disk with the directory
  entries that reach it — the record's directory and the namespace's — so a host crash keeps the state every launch
  since rested on; a write the disk will not flush fails like any other, and an arming it refused is taken back
  before its launch is refused. A record that names no retirement a poller can land holds every
  developer launch on the issue, logging an error each time, until an operator acts: one that will not read — torn
  by a crash or a full disk, or blocked by something else standing at its name — or an arming nothing resolved, which
  is what a poller killed mid-run, an exception out of the runner, a settle the record refused, or a resolution it
  refused before a restart leave behind. Such an arming says a launch went out and not which conversation, if any, a
  quota stopped: a fresh spawn's id is unknown until it returns. It holds only the launches after it, each refused
  uncharged: a run no quota stopped whose settle the record refused still goes on to its disposition, and its commit
  publishes. The operator writes the retirement it owes as
  `{"session_id": "<id>"}` (`null` where none can be named) or settles it as `{}`; a tick whose resume was planned
  over such a record launches nothing even where it is written again or settled before the launch. Settling the
  record by hand drops the obligation, and the next run may resume the conversation the quota stopped; deleting it
  does too, except that a poller still holding the resolution in memory writes it again.
- **Release.** A claim ends when the dispatch or base-refresh route that took it ends, however it ends, and the kernel
  drops it when a process dies, so a crashed poller leaves nothing held; its descriptor is closed with it and is not
  inherited by an agent the holder spawns. The files stay: never delete the directory or a file in it while any poller
  runs, since a recreated file is a new inode another process can lock beside a holder of the old one. The claim files
  are small, one per issue key ever claimed, and safe to remove once every poller has stopped; a `.quota-retirement`
  record beside one is not, unless it reads `{}` — removing one that is armed or owes a retirement drops that
  obligation, as [An owed quota retirement](#running-more-than-one-poller) describes.
- **Not covered.** Pollers on different hosts, or on one host with different `WORKTREES_DIR` values, are not
  coordinated at all and are not supported against the same repository. And the claim is separate from the artifact
  presence on `WORKTREES_DIR/.artifact-maintenance.lock`: a maintenance pass neither takes nor reads a writer claim, and
  holding one says nothing about the host's artifacts.

## Running under systemd (user service)

For persistent operation, run the installed package as a systemd **user** service, which `chipping-orchestrator init`
installs and enables, and `start`, `stop`, `restart`, `status`, and `remove` [manage](#operating) from then on. A
foreground process does not survive a reboot, a `tty` logout, or the user manager being torn down. `init` refuses to
run from a source checkout; source-checkout service configuration belongs to the
[developer guide](../development.md#development-restart-wrapper).

A detached `screen` / `tmux` session wrapped in a `Type=forking` unit looks similar but is the wrong shape: systemd ends
up supervising `screen`, not the orchestrator; `ExecStop` races the screen session's own lifecycle; logs split; and the
unit silently does nothing at boot unless linger is enabled. Keep `screen` / `tmux` for interactive debugging.

### Installing with `init`

Install the service as the user it runs as, from a shell whose `PATH` finds the agents:

```sh
chipping-orchestrator init
```

On a fresh host at a terminal, `init` first asks for the setup, as [onboarding](#onboarding-with-init) describes. Set
up by script instead, a fresh host takes a `set-token` per repository, `configure` for the first repository,
`add-repo` for each further one, and `init`, none of which prompts, and the files they write are the ones onboarding
writes for the same answers:

```sh
chipping-orchestrator set-token acme/api < "$HOME/acme-api-token.txt"
chipping-orchestrator set-token acme/web < "$HOME/acme-web-token.txt"
chipping-orchestrator configure --clone "$HOME/src/acme-api" --authors alice
chipping-orchestrator add-repo --clone "$HOME/src/acme-web"
chipping-orchestrator init
```

`init` loads no configuration itself. It exits 1, having written nothing, with its reason on stderr when:

- it runs from a source checkout of the orchestrator, with the refusal `configure` gives one;
- `~/.config/systemd/user/orchestrator.service` exists, the hand-written unit releases up to v0.13.0 documented: a
  second service would poll beside it, so [move from it](#moving-from-the-hand-written-unit) first;
- the interpreter running `init`, or an entry of its `PATH`, holds a value the [unit](#unit-file) cannot carry;
- `systemctl --user` reaches no user manager, as under `su` or `sudo`: run `init` in an ssh or desktop login of the
  service user;
- `~/.config/chipping-orchestrator/.env` does not exist and standard input is not a terminal: the message names
  `set-token` and `configure`, which write the tokens and the file;
- onboarding is stopped or declined before its last answer, having written nothing, or a write after it fails;
- [`check`](#check-compatibility-and-start), GitHub calls included, finds a problem, printed as `check` prints it.

Otherwise it writes the unit, runs `systemctl --user daemon-reload` and
`systemctl --user enable chipping-orchestrator.service`, ensures [linger](#enabling), and prints the command that
starts the service. It never starts or restarts the service. A manager that refuses the reload or the enable exits 1
with the unit left written; run `init` again once that is repaired. Each `systemctl` and `loginctl` call is given 30
seconds and counts as failed past them.

Run `init` again whenever what the unit records changes: the interpreter's path, as when the package moves to another
environment, or the directories the agents are found in. It leaves `.env` and the token files exactly as they are and
rewrites only the unit, from the interpreter and `PATH` it runs with now. When the service is running, it says to
restart it, which `chipping-orchestrator restart` does; choose a [safe stopping point](#safe-restart-guidance).

### Onboarding with `init`

Where `~/.config/chipping-orchestrator/.env` does not exist and standard input is a terminal, `init` asks for the
setup before it checks or installs anything. Onboarding is the scripted setup asked for: one question per setting,
each answer held to the check `set-token`, `configure`, or `add-repo` holds it to, and the answers handed to the code
those commands run, in the same process. Run it as the service user from the top of the first clone; each default is
in brackets, and Enter takes it:

```text
$ cd ~/src/acme-api && chipping-orchestrator init
No configuration at /home/alice/.config/chipping-orchestrator/.env. Let's create it.
Nothing is written until the last question; Ctrl+C leaves everything as it is.

[1/6] Local clone of the repository to manage [/home/alice/src/acme-api]:
[2/6] GitHub repository (owner/name) [acme/api]:
[3/6] Branch pull requests target [main]:
[4/6] GitHub token for acme/api (input hidden):
      the token reaches acme/api (owner: alice)
[5/6] GitHub logins whose issues the orchestrator may act on [alice]:
[6/6] GitHub logins to mention when a human is needed [alice]:

Agents: implement=claude (found)  review=codex (found)  decompose=claude (found)
Keep these agents? [Y/n]:
Add another repository? [y/N]:

Write /home/alice/.config/acme/api/token and /home/alice/.config/chipping-orchestrator/.env? [Y/n]:
```

- **Clone** — the current directory where it is the top of a git checkout, and otherwise no default. The answer has to
  be the top of a clone or linked worktree, as for `configure --clone`.
- **Repository and branch** — read off the clone as `configure` reads them: the repository its GitHub remote names,
  and that remote's default branch, else the branch checked out. A repository the clone has no remote for is refused
  at this question, with the message `configure` would give after the last one.
- **Token** — not asked for where `~/.config/<owner>/<name>/token` exists: that file is kept as it is. Otherwise it is
  typed at a hidden prompt, which offers an exported `GITHUB_TOKEN` as its default, named but never shown, and proved
  with the read-only call `set-token` makes. It stays in memory until the last question. GitHub is asked whose token
  it is, too, which is the next question's default.
- **Authors and people to mention** — the token owner's login, then the authors answer. Where GitHub names no owner,
  the authors have no default, since they decide whose issues and comments the orchestrator trusts.
- **Agents** — the roles' defaults, `claude`, `codex`, and `claude`, each shown with whether it is on the `PATH` the
  service will run with: the absolute entries of the shell's, which [the unit](#unit-file) records. Keeping one that
  is not found is refused with the message `configure` gives it; answering `n` asks each role in turn, from
  `claude`, `codex`, and `agy`.
- **Another repository** — each `y` asks the clone, repository, branch, and token questions again, numbered `[1/4]` to
  `[4/4]`. The clone has no default, and a repository already given is refused, compared without regard to case.

A refused answer is printed beneath its question in the words the setup commands print for it, without an option name
in front, and the question is asked again. Nothing is written until the last question, which names every file the
answers write, is answered yes: Ctrl+C or the end of input at any question, a terminal that cannot hide the token, and
`n` to the last question each exit 1 with no `.env`, token, unit, or directory written. After it, onboarding saves
each token it was given as `set-token` does, writes `.env` as `configure` does for the first repository, and adds
each further one as `add-repo` does, then `init` carries on with the full check and the unit. A write that fails there
exits 1, keeping what the lines above it report written; since `.env` is what `init` looks for, a run that stopped
before writing it onboards again, keeping each token already stored.

Without a terminal -- a pipe, a redirect, an `ssh` command without `-t` -- `init` never prompts. Once `.env` exists it
never onboards either: run again, it rewrites only the unit, and [`add-repo`](#install-and-configure) adds a
repository after that.

### Unit file

`init` writes `~/.config/systemd/user/chipping-orchestrator.service` whole, replacing any unit at that path. For alice,
with pipx's default home, it reads:

```ini
# Written by chipping-orchestrator init, which rewrites this file each time it
# runs; keep a local change in a drop-in: systemctl --user edit chipping-orchestrator.service
[Unit]
Description=chipping-orchestrator
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=%h
ExecStart="/home/alice/.local/share/pipx/venvs/chipping-orchestrator/bin/python" -m orchestrator run
Environment="PATH=/home/alice/.local/bin:/usr/local/bin:/usr/bin:/bin"
Restart=on-failure
RestartSec=30
SuccessExitStatus=130 143

[Install]
WantedBy=default.target
```

- `ExecStart` runs the interpreter of the package that ran `init`, so the service cannot pick up another installation
  through `PATH`.
- `Environment=PATH` is the `PATH` `init` ran with, absolute entries only, which is also the `PATH` `check` judges. A
  user service does not inherit the login shell's `PATH`, so this is what finds `claude`, `codex`, `agy`, and `node`;
  absolute `CLAUDE_BIN`, `CODEX_BIN`, and `AGY_BIN` paths in `.env` work too.
- `WorkingDirectory=%h` is the home directory. It selects neither the configuration file,
  `~/.config/chipping-orchestrator/.env`, nor the log directory: set an absolute `LOG_DIR` as
  [package setup](#install-and-configure) does.
- `Type=simple` tracks the foreground process. `SIGTERM` from `systemctl stop` triggers its graceful shutdown, which
  exits with `128 + signum`, and `SuccessExitStatus=130 143` records that exit as a success rather than a failure.
- `Restart=on-failure` relaunches a failed process every 30 seconds (`RestartSec=30`) with no limit
  (`StartLimitIntervalSec=0`), so a GitHub outage at boot cannot leave the unit failed for good. A refused start, from
  invalid settings or targets or an empty `ALLOWED_ISSUE_AUTHORS`, repeats on that cadence too. `start` and `restart`
  [check for those](#operating) before asking systemd anything, so the loop arises where the settings changed with no
  such check after, as when the user manager starts the service at boot: read the diagnostic with
  `journalctl --user-unit chipping-orchestrator.service -f`, run `chipping-orchestrator stop`, and repair the
  configuration.
- Both quoted values have each backslash and double quote escaped and every `%` written `%%`, because systemd unquotes
  both and then expands its `%` specifiers. `init` refuses a value holding a control character, and an interpreter
  path holding a quote, a backslash, or a `$`, which systemd rejects or rewrites in a command.

Keep a local change in a drop-in made with `systemctl --user edit chipping-orchestrator.service`, since `init` rewrites
the unit file whole each time. Package version changes require an explicit pipx upgrade while the service is stopped.

### Enabling

`init` runs `systemctl --user daemon-reload` and `systemctl --user enable chipping-orchestrator.service`, so the
service starts whenever the user manager does, and leaves the first start to you:

```sh
chipping-orchestrator start
```

Linger is **required for boot-time start**: without it the per-user systemd manager only runs while the user has an
active login session. `init` reads `loginctl show-user <user> --property=Linger` for the `USER` it runs with and, unless
that reports `Linger=yes`, runs `loginctl enable-linger <user>`. Where logind refuses, as under a policy leaving linger
to administrators, `init` still installs the service and warns on stderr that it runs only while the user is logged
in, until an administrator runs:

```sh
sudo loginctl enable-linger <user>
```

### Moving from the hand-written unit

Releases up to v0.13.0 documented a hand-written `~/.config/systemd/user/orchestrator.service`, and `init` refuses to
install beside it so two pollers never run at once. At a [safe stopping point](#safe-restart-guidance), stop, disable,
and delete it, then install its replacement and start that:

```sh
systemctl --user stop orchestrator.service
systemctl --user disable orchestrator.service
rm ~/.config/systemd/user/orchestrator.service
systemctl --user daemon-reload
chipping-orchestrator init
chipping-orchestrator start
```

Carry any `Environment=` setting the old unit held over to a drop-in made with
`systemctl --user edit chipping-orchestrator.service`. Variables it read from an `EnvironmentFile=` go there as
`Environment=` lines instead, since `start` and `restart` [refuse](#operating) a drop-in that reads one. A token it
supplied as `GITHUB_TOKEN` belongs in a token file: `check`, and so `init`, read tokens only from those, so store it
with [`set-token`](#install-and-configure) before running `init`. `start` and `restart` would accept a `GITHUB_TOKEN`
a drop-in's `Environment=` sets, as the service does, but the token file is owner-only and is what `check` and `init`
judge. Linger the old unit relied on stays enabled.

### Operating

```sh
chipping-orchestrator start      # check the settings locally, start the service, and confirm it stays active
chipping-orchestrator restart    # the same check, then restart it, as after editing .env or add-repo
chipping-orchestrator stop       # SIGTERM the poller; the service stays enabled
chipping-orchestrator status     # the version, .env, and unit, then systemctl --user status
chipping-orchestrator remove     # stop, disable, and delete the unit, keeping everything else
journalctl --user-unit chipping-orchestrator.service -f     # tail the supervised command's stdout/stderr
```

None of these loads the configuration in its own process, so each answers on a host whose settings would stop a start.
Run them as the service user; each refuses, naming itself, where `systemctl --user` reaches no user manager, as
under `su` or `sudo`.

`start` and `restart` first run the local [check](#check-compatibility-and-start) -- what
`chipping-orchestrator check --local` checks -- in the environment the service would run with: the shell's `HOME` and
`USER`, then what the user manager's configuration hands every service, then every variable the [unit](#unit-file) and
its drop-ins set, each read off the files as systemd assembles them rather than taken from the shell. So the agents are
looked for on the `PATH` the service gets -- the one `init` recorded, or the one a drop-in replaced it with -- and a
setting a drop-in's `Environment=` overrides is checked as overridden. The check also runs in the directory the service
starts in: the home, unless a drop-in's `WorkingDirectory=` names another, so a `REPOS` target given relative to it is
looked for where the service will look. The check makes no GitHub call, so a GitHub outage never keeps the service from
starting; the service rides one out by restarting. While it finds a problem, each is printed, systemd is asked nothing,
and the command exits 1, leaving a running service running.

Tokens are judged as the service will find them too: a token file, or a `GITHUB_TOKEN` an `Environment=` line in the
unit or a drop-in sets, which the service takes before any token file. This is where `start` and `restart` differ from
`check` and `init`, which take nothing from the shell but `HOME`, `USER`, and `PATH` and read no unit, and so read the
token files alone. Keep tokens in the token files [`set-token`](#install-and-configure) writes owner-only, which all
four judge alike.

The drop-ins read are the `*.conf` files in a `chipping-orchestrator.service.d`, `chipping-.service.d`, or
`service.d` directory under each directory systemd reads user units from by default -- `~/.config/systemd/user`,
`~/.config/systemd/user.control`, and `~/.local/share/systemd/user`, and `systemd/user` under `/etc`, `/etc/xdg`,
`/run`, the user's runtime directory, `/usr/local/lib`, `/usr/lib`, `/usr/local/share`, and `/usr/share`. Of two with
the same name the one systemd ranks first wins, and they apply in name order; a hidden file, whose name starts with a
dot, is not read, as systemd reads none. An empty `Environment=` drops every assignment before it.

A user service sets no `HOME` or `USER` of its own: it inherits the user manager's environment as it stands, and the
check holds it too. The manager's own `HOME` and `USER` -- the shell's -- lie at the bottom, then what its
configuration hands every service: `ManagerEnvironment=` and, over it, `DefaultEnvironment=` in the `[Manager]`
section of `~/.config/systemd/user.conf` (or `/etc/systemd/user.conf` where the home has none) and of each
`user.conf.d` drop-in in `~/.config/systemd` and under `/etc`, `/run`, `/usr/local/lib`, and `/usr/lib`, the home's
ranking first, with the specifiers the manager expands there -- `%h`, `%u`, `%U`, `%G`, and `%%` -- read as the home,
the user's name and ID, the group ID, and a `%`; and over those each assignment of the `*.conf` files in
`~/.config/environment.d` and in `environment.d` under `/etc`, `/run`, `/usr/local/lib`, and `/usr/lib`, each value
expanded as the manager's generator expands it against the variables set before it. The unit's own variables lie over
all of it. So an author allowlist or a `REPOS` an `environment.d` file sets is checked as the service will read it,
and so is a `HOME` it sets, under which the service, and the check, read `.env`. What the manager is told at run time
-- by `systemctl --user set-environment` or `import-environment`, as a desktop session may do -- and its own process
environment past the home and the user are known only to the manager, which a launch does not ask before its check
passes, so a setting kept there is not checked; keep settings in `.env`.

Before anything else, and asking systemd nothing, a launch refuses:

- a missing unit, naming `init`;
- `EnvironmentFile=`, `PassEnvironment=`, or `UnsetEnvironment=` in the unit or a drop-in, which take the service's
  environment from a file or from the user manager's own, and `ExecStart=` in a drop-in, after which the service no
  longer runs the package that installed it;
- an `Environment=` value using an escape other than a backslash before a backslash or a quote, or a specifier other
  than `%%`, `%h`, and `%u`, and a `WorkingDirectory=` that is relative, uses such a specifier, or is marked `-`, which
  lets systemd skip a missing directory and leave the service wherever the user manager runs;
- a unit and drop-ins that leave the service no `PATH` of their own, since it would then run with the user manager's, or
  that give it one holding an empty or relative entry: the service starts each agent in an issue's worktree, so a lookup
  through such an entry finds nothing there, or whatever that checkout holds, wherever the check found it;
- an `environment.d` file or `user.conf` it cannot read as systemd does: a quote left open -- even after a name systemd
  ignores, since it reads the value first and the quote runs on over the lines below -- or a line continued past
  its end, a `${` expansion other than `${NAME}`, `${NAME:-TEXT}`, and `${NAME:+TEXT}`, or a `ManagerEnvironment=` or
  `DefaultEnvironment=` value read as an `Environment=` one could not be or using a specifier other than those above,
  such as the host name's `%H`;
- a `ManagerEnvironment=` setting `HOME` or an `XDG_` directory variable, or a `DefaultEnvironment=` setting `HOME` or
  `XDG_CONFIG_HOME`, since either moves where systemd reads its own configuration -- the units and `user.conf`, or
  the `environment.d` files.

Each refusal names the file and the setting or variable in it, and never quotes a value, which may be a token; take that
out, or start the service with `systemctl --user start`, which checks nothing. The unit files are read as systemd's
parser reads them: a byte-order mark opening the first line that has one is dropped only after comments are told, so a
`#` or `;` right after it opens no comment, a line ends at a newline, a carriage return, or the two together in either
order, and only a space, a tab, a newline, or a carriage return counts as a blank; a file holding a NUL character is
refused, and so is one holding a malformed section header -- one never closed, or whose name holds a control
character, a backslash, or a quote -- at which systemd stops reading the file, ignoring every setting after it.

Then the user manager reloads its units, so that what it launches is the definition just checked rather than one it
loaded before the files changed, and starts or restarts the service. A `Type=simple` service counts as started as soon
as its process does, so the command asks at each of the 5 seconds after the job whether it is still active. The whole
watch ends within 7 seconds of the job: each question waits for its second unless a slow answer has already passed it,
and is bounded by the time left, so a manager slow to answer cannot stretch it. The command exits 0 with the service
active throughout, or 1 with what the service is now -- `activating` while systemd waits out `RestartSec` to start it
again, or that a question got no state in the time left -- and the last 20 lines of its journal, as it does when the
manager refuses the job itself.

`stop` has the manager stop the service: the poller receives `SIGTERM` and
[shuts down gracefully](#what-survives-a-restart). The service stays enabled, so the user manager starts it again
the next time it starts, as at boot. `status` prints the package version, `~/.config/chipping-orchestrator/.env`, and
the unit, each followed by `(missing)` where there is no such file, then
`systemctl --user status --no-pager chipping-orchestrator.service`, and exits with that command's status: 3 for a
service that is not running, 4 for no unit at all.

Each job these commands hand the manager -- a start, stop, restart, disable, reload, or reset -- is given 120 seconds,
past the 90 seconds systemd gives a unit to stop, and each question about the service 30; a job still running at its
bound is reported as failed while the manager carries on with it.

systemd's journal captures the supervised command's stdout/stderr (process lifecycle, exit codes, restart messages).
The orchestrator's own structured log lives at `LOG_DIR/orchestrator.log` (rotated, ~10 MiB × 5).
The `configure` step of package setup above records an absolute `LOG_DIR` pointing to
`~/.local/state/chipping-orchestrator/logs`.
`WorkingDirectory` does not select the default log location.
Check the journal first for "did it start / did it die", then `LOG_DIR/orchestrator.log` for per-issue handler detail.

### Removing

`chipping-orchestrator remove` takes the service away and keeps the setup. It stops the service, disables it, deletes
`~/.config/systemd/user/chipping-orchestrator.service`, and runs `systemctl --user daemon-reload`, which unloads the
service. Where the manager still remembers the service as failed, it then runs
`systemctl --user reset-failed chipping-orchestrator.service`; a service stopped cleanly is gone with the reload, and
`reset-failed` refuses a unit the manager no longer has loaded.

It keeps `.env`, the token files, the logs, the worktrees, and linger, and says so, and leaves any drop-in directory
beside the unit as well; delete them, or run `loginctl disable-linger`, only once nothing else needs them. `init`
installs the service over the same setup again. With no unit installed, `remove` does nothing and exits 0.

A step that fails exits 1 with the manager's reason and takes no step after it. A stop or disable that fails keeps the
unit, so `remove` run again takes it up from the start; a reload or reset that fails once the unit is deleted names the
`systemctl --user` command that finishes the removal. Only a state `systemctl --user is-failed` prints answers whether
the service is still remembered as failed -- `inactive` for one the reload unloaded -- so a query the manager refuses,
or one that does not finish, is a failed step too, naming the `is-failed` and `reset-failed` commands that finish.

## Reclaiming what a split leaves on the remote

An issue whose committed implementation is adjudicated as a split leaves two things on the target repository: the
branch its superseded candidate was committed on, and an immutable snapshot ref under
`refs/orchestrator/late-split/issue-<n>/cycle-<c>/gen-<g>` holding the exact commit its children were told to reuse.
Both are recorded on the issue's own pinned obligation ledger, and the orchestrator reclaims them itself — there is
no TTL and no background garbage collection. Three passes do it, and between them every live ledger stays visited:

- the **umbrella's terminal**, which settles what is owed before it closes the parent (see
  [`../state-machine/delivery-stages.md`](../state-machine/delivery-stages.md#_handle_umbrella-label-workflowumbrella));
- the **umbrella's park**, on the way out of the two dispositions that stop the parent for a human — a child
  `rejected`, or one closed without reaching a terminal label. Both closed the child, which is the reading the rule
  takes, so the ledger is settled from the same scan that parked the parent; the park itself is unchanged and no
  terminal is decided. Nothing else revisits an issue parked this way, which is why it happens here;
- the **closed-owner cleanup sweep**, for an issue a human closed mid-cycle while it still carried
  `workflow:decomposing` or `workflow:umbrella` — or `workflow:ready` / `workflow:blocked`, where a decomposition
  outcome that landed after the close can leave an ending nothing else would find (see
  [`../state-machine/delivery-stages.md`](../state-machine/delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own)).

The sweep runs on the existing `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` cadence and adds no per-tick traffic of its own, so
raising that knob (the multi-repo rate-limit advice in
[`../configuration.md`](../configuration.md#github-rate-limits)) also stretches how long an unreclaimed branch or ref
survives, by the same factor. It is cleanup-only: it never spawns an agent, resumes a workflow, activates a child, or
touches one that already exists. It does end the cycle the close interrupted — the cancellation is marked, any pull
request that cycle was holding is closed over one notice, and the issue moves to `rejected` once nothing is owed. That
last write is the only label it makes, and it is also what stops the sweep: an owner still owing the remote keeps its
label and keeps being visited, so a repository whose closed owners stay on `workflow:decomposing` or
`workflow:umbrella` is a repository with something the orchestrator could not reclaim.

Reopening such an owner does not get the workflow going again. The same cleanup runs from the dispatcher instead,
once per dispatch, the issue reaches no stage handler, and the same `rejected` is written once the ledger settles —
each held dispatch logs a warning naming what is still owed. Clearing the refusal is clearing the obligation; starting
a fresh attempt afterwards is removing `rejected`, which is the handshake below.

### Rolling back to an older orchestrator

The late generation an oversized candidate is adjudicated under lives in additive `late_*` fields on the issue's own
pinned comment. An orchestrator that predates them ignores those fields entirely, which is safe for an issue that
never entered the size gate and **not** safe for one currently in it: the older binary would read a
`workflow:decomposing` issue carrying a frozen candidate as one waiting to be decomposed, spawn the initial
decomposer against it, and decide the size question by not asking it. The same holds for an issue whose ledger still
records a snapshot ref or a superseded branch — nothing in the older binary reclaims either.

So a rollback is drained rather than cut over. Set `DECOMPOSE=off` and restart, which stops new candidates entering
the gate while every recorded generation goes on being adjudicated, cancelled, cleaned up, and restarted. Then wait
for **both** halves of the drain, because they end at different times:

- **No open issue carries `late_cycle_id`** in its pinned comment. That is the adjudication half — a cycle still
  deciding, revising, or splitting.
- **No CLOSED issue carries an unsettled `late_resources` ledger**, on any of the four labels the cleanup sweep
  visits. A closed owner is exactly the case the first check cannot see: its cycle was ended by the close, and what
  is left is the sweep reclaiming the superseded branch and the snapshot ref its children were cut from, at the
  `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` cadence rather than every tick. Deploying the older binary over one abandons
  precisely the resources the paragraph above says nothing else reclaims. A ledger is settled when every entry reads
  `reconciled`; a `retained` ref (its consumers are still live) is **not** settled and is the one state that can take
  arbitrarily long, since it waits on issues that are still being worked.

The section above lists the ref namespace and the `git ls-remote` that shows what is still out there, which is the
direct check when a pinned comment is ambiguous. An issue that has to be parked mid-cycle instead is closed, which
ends its cycle irreversibly and settles what it owes the remote — the work stays committed in its worktree and the
section below says how to start it again.

The drain settles the late generation and nothing else a newer orchestrator wrote. Returning an older binary to that
state stays outside the procedures this release supports
([C-03](../contracts.md#c-03-persisted-and-externally-consumed-formats)), and
[Deploying without migration](#deploying-without-migration) is how to keep from it whatever else it cannot read.

### Restarting an issue whose cycle was cancelled

**Reopen the issue, then remove `rejected`.** That is the whole gesture, and both halves are required: the
orchestrator restarts an issue that is open and wearing no workflow label at all, over a pinned comment that records
a cancelled cycle with nothing left owed **and** records that this cycle's `rejected` was actually handed out.
Removing the label is what authorizes it — GitHub grants label writes only to a repository's own people — so the
restart runs whoever filed the issue, `ALLOWED_ISSUE_AUTHORS` included.

Three things follow from that last condition. Removing a *workflow* label from an owner whose cleanup has not
finished does not authorize anything: the ending was never in a state it could write `rejected` from, so it writes it
once the cleanup settles, and the handshake starts from there. Neither does a `rejected` the orchestrator tried and
failed to apply — what is recorded is a label a pass could see on the issue, not an attempt, so a refused write is
simply retried. And an issue whose cancellation is still owing the remote is refused until the cleanup finishes —
including the one obligation no pass can clear for you, a recorded held pull request with no preserved description
beside it, which the held-terminal warning names as `held PR #<n> (no preserved description)`. Repair that record
first; nothing restarts over it.

Cancellations the orchestrator ended itself need nothing from you, closed owners included: the pass that writes
`rejected` records it in the same breath, so the first removal is the one that counts. Cancellations that ended
*before* this record existed are sitting on `rejected` with nothing recorded, and the first tick that sees one there
writes it down — so removing the label works the first time on those too, as long as a tick has seen the issue open
and still labelled. If one of those older issues is **closed**, then reopened and unlabelled inside a single poll
interval, the orchestrator asks GitHub's own label history for that issue before deciding: where the most recent
workflow label **it** applied is `rejected`, the removal counts and the fresh cycle starts one tick later. Only its
own applications count — a `rejected` a collaborator applied and removed by hand is somebody else's label, not a
terminal this orchestrator wrote. A history whose newest one is some other state — which is what an issue that has
already been restarted once looks like, since the restart applied a label of its own — and one the API would not
serve both re-apply the terminal, and removing it again starts the cycle.

Removing a terminal from an issue that never had a late cycle does not start anything either. An issue that already
carries a pinned comment is one the orchestrator has met, and greeting it a second time would write a second pinned
comment that every later read shadows, so an unlabeled issue with a pinned comment is left exactly where it is and
logged once a tick. To drive such an issue again, apply the workflow label you want it to run from by hand — the
same way an outsider's issue is driven past `ALLOWED_ISSUE_AUTHORS`.

What you will see, on the next tick after the label comes off: **one comment** naming the new cycle and where the
issue is going, and **one label** — `workflow:decomposing`, or `workflow:implementing` when `DECOMPOSE=off`. The
issue then runs as a fresh attempt. Everything the cancelled cycle recorded is dropped from the pinned comment: its
agent sessions, its pull request and branch, its child issues and dependency graph, the snapshot it was cut from,
any park, the drift baseline, the retry and review counters, and the timestamps. What is kept is the pinned comment
itself, the ids of the comments the orchestrator has posted on the thread, and the issue's cumulative agent-run,
token, and cost counters — so the receipt a later terminal posts still reports what the whole issue has spent, not
just what the newest attempt did. The record of developer conversations retired as failed (`dev_session_retirement`) is
kept too, so the fresh attempt never pins or resumes one of them, even where a backend hands its id back to the first
spawn. A child an ordinary split created keeps its seed as well — its `parent_number` and its `late_ancestry_*` group,
the snapshot pointer included — because the receipt in its body holds every later dispatch to that seed
([below](#re-decomposing-an-issue-inside-a-late-lineage)); nothing of the cancelled cycle's candidate, exemption, or
authorization comes with it, and neither does the drift baseline its split recorded beside that seed, which goes with
the rest. Child issues the cancelled cycle created on GitHub are **not** touched: they are real
issues carrying real work, and what happens to them stays a human's decision.

If you apply that same target label by hand while a restart is mid-transaction, you will see the orchestrator take
it off and put it straight back. That is deliberate, not a fight over the label: its own application of the target
is what separates the fresh cycle from the previous one's `rejected` in the label history, and GitHub records no
event for a label that is already there. Leave it be — the issue ends up on the label you wanted either way.

If the restart cannot finish — GitHub refuses the comment or the label — the issue keeps the pending marker in its
pinned comment, a `late_failure` carrying `restart_failed` reaches both sinks, and the next tick resumes at the step
that is still owed rather than starting over. `backlog` or `paused` on the issue defers the whole restart until the
control label comes off; the authorization is not lost meanwhile.

**What to look at when something is not going away.** Four signals, and they mean different things:

- A `late_failure` carrying `snapshot_delete_failed` or `branch_cleanup_failed` (see
  [`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks)), together
  with an umbrella that will not close, or a closed owner that keeps its label. The remote **refused** the delete.
  That is a permission or ruleset problem — a protected-ref rule over `refs/orchestrator/*`, or a token that lost
  push scope — and only an operator can clear it. Nothing is retried into success meanwhile; the retry itself is
  every visit, but the *record* of it is not: the sinks carry the move to `failed` once and say nothing on the
  visits that reach the same answer again, so what tells you a refusal is still standing is the terminal that never
  fires and the warning logged on every visit that holds — not a second event.
- A snapshot ref that is simply still there, with no failure recorded, and an umbrella that will not close. It is
  **retained** on purpose: a ref is kept until every recorded direct consumer has ended — which means the consumer's
  issue is *closed*, since reaching `done`, being `rejected`, and a human closing it all close it, and reopening
  leaves the label where it was. Those readings are taken fresh on every visit rather than latched, and every
  obligation that is not `reconciled` holds the owner's terminal, so the umbrella stays open and logs what it is
  waiting for on each due dependency poll. A child that stays open forever keeps its ancestor's ref forever, which is
  the deliberate trade — invalidating a live child's only copy of the work it was told to reuse is worse. Closing (or
  finishing) the child is what lets both go. That includes a child the umbrella no longer tracks: after an edit
  re-decomposed the umbrella, the children its drift notice named as ORPHANED are still the ref's recorded consumers,
  so an orphan left open (or one the orchestrator cannot read) holds the ref and the umbrella after every replacement
  is done. A replacement that re-decomposition pointed at the ref is a recorded consumer as well, so it holds the ref
  exactly as an original does until it is closed — reopened after it resolved included. Close the orphans that no
  longer apply; the ref goes on the next dependency poll that finds the replacements resolved and every recorded
  consumer, original or replacement, closed. Where the re-decomposition kept work for the parent, the same hold
  shows as a parent staying on `workflow:blocked` after every child is `done`, logging what it holds its return to
  implementation on; closing the consumers is what lets it go. On its way out it retires the split's late cycle, so
  its next implementation run starts a cycle of its own rather than looking for the split's superseded candidate.
- An umbrella that will not close with **nothing owed at all** — every obligation `reconciled`, no failure on
  either sink. The issue was split on the far side of publication, and the pull request that split superseded is
  open again (or was merged, or has been pushed to since). Everything the umbrella still had to do was licensed by
  that change being closed, so the parent holds rather than handing itself `done` over a live change carrying
  superseded work: no child is released, the branch is left wherever it is, and the terminal waits. There is nothing
  on the ledger to look at because nothing is owed the remote — the reason is only in the log line, said on every
  tick that holds and naming the pull request. Settling that pull request is what clears it; the label staying put
  is the retry. Do not expect the orchestrator to re-delete a branch you restored — a branch put back by hand is
  yours, and refusing to remove it is the point.
- A `late_cleanup` carrying `outcome: reclaiming`, and an umbrella that will not close over a ref that is already
  **gone**. That state is progress, not failure: the decision is written down before the delete, so an entry left in
  it is one whose delete landed while a child it owes a receipt could not be reached. Every obligation short of
  `reconciled` holds the terminal, so the parent stays open until the next visit finishes the telling — which it
  does by finding the ref absent, which counts as reclaimed, and then saying so to the children that were missed. A
  child that stays unreachable is the one case that repeats, and the log line names it on every visit.

To list what a repository is holding:

```sh
git ls-remote origin 'refs/orchestrator/late-split/*'
```

Deleting one by hand is safe once you are sure no child still needs it, and it does not strand the ledger: an absent
ref counts as a successful reclamation, so the entry reconciles on the next visit at the cost of one read.

Do **not** recreate a ref the orchestrator has already reclaimed. Its value was that it provably carried one exact
commit, and a ref pushed again from whatever is reachable now proves nothing. The orchestrator does not do it either,
and it makes sure nothing resumes against one:

- **As the ref goes, each child cut from it gets one comment** saying so, carrying a hidden marker naming the owner,
  cycle, and generation so it is said once. That is *all* the owner does to a child. It never edits a child's pinned
  comment: that comment is written whole by whoever writes it, and a handler of the child's own that read it first
  and wrote it after would silently undo the edit — so the receipt is an appended comment, which nothing can lose.
  A cycle a human's close **cancelled** leaves even that unsaid: it is responsible for none of those children, so it
  reclaims the ref and touches nothing. The child is not left uncovered — the mirror goes before the remote ref, so
  the guard below reaches the same park a receipt would have earned it, one `ls-remote` later.
- **The child refuses the work itself, at its own dispatch.** Before any handler runs, an issue whose recorded
  ancestry still names a snapshot looks for that receipt on its own thread — marked with the owner, cycle, and
  generation it was born of, and authored by the orchestrator — and refuses if it finds one. That answer is
  authoritative: it says the reclamation *happened*, which no later look at the ref can contradict. A thread the
  tick could not *read* is not a thread with no receipt on it, and stops the dispatch there rather than falling
  through to readings a receipt would have overruled.
- **Where the thread answered and carries none, the ref itself decides**, and its three answers are three different
  outcomes. Gone → park. Still there under **another commit** → park too, under `late_snapshot_repointed`: the name
  survived and what it stood for did not, and nothing here re-points or deletes that ref. Unreachable → the dispatch
  is *held* for the next dispatch, with nothing written, because an outage is evidence of nothing. A park drops the
  dangling pointer, marks the issue `awaiting_human`, and returns before the label's handler is reached — including
  for a reopened `done` / `rejected` child, which is otherwise a dispatch no-op.
- **The steady state costs nothing on the wire.** The ref reading asks this host's own copy first, and a reclamation
  takes that copy down *before* it touches the remote ref — refusing the whole reclamation if it cannot prove the
  copy gone — so a copy still here means nothing has been reclaimed. It is read for the exact commit it carries,
  since it lives in the object store the agents' own worktrees share, and it is trusted only for a pointer this
  binary wrote (children created before that ordering existed pay one `ls-remote` instead).

  A child the split recorded but never managed to seed — an ancestry write that failed after the issue existed —
  carries the split's marker in its **body**, and that marker is corroborated rather than believed: the owner's own
  generation is read fresh and has to name the same cycle and generation and carry this issue among its recorded
  consumers. Vouched, it hands over the ref *and* the commit the owner preserved, and the same three answers follow.
  Unvouched, the guard steps aside — a marker anyone can paste into a body parks nobody. Unreadable, opaque, or
  naming no candidate, the dispatch is held.

  This is also why deleting a snapshot ref by hand is not the same as the orchestrator reclaiming one: no receipt is
  written, so the children are never told — and on the host that already fetched the ref, its own copy is still
  there and is what a child reads first, so that child goes on working from the candidate until the copy goes too.

Continuing after such a park means either implementing the issue as an ordinary change or starting an explicit new
split cycle on the owner, which preserves a candidate of its own.

### Re-decomposing an issue inside a late lineage

A genuine edit to an issue a late split made, or to the umbrella of one, sends it back to the ordinary decomposer.
The children that answer creates stay inside the same lineage: each is seeded one level below its parent under the
same root, and a parent whose own split still holds its snapshot ref points each child at that ref, appends the
reuse instructions to its body, and records it on the ref's consumer ledger in the write that records the child — so
the replacements hold the ref exactly as the originals do (see the signals above). Nothing of the parent's own size
gate is carried over: a child is measured on its own commits, at its own depth. Each child also carries a hidden
receipt naming its parent, the split's attempt, and its slice, which is how a crash between creating a child and
recording it is recovered without opening a second issue for the same slice.

Every refusal on this road parks the issue it lands on: a notice on its thread mentioning `HITL_HANDLE`, saying which
refusal it is, and `awaiting_human: true` on its pinned comment. The pinned `park_reason` is left cleared, as every
ordinary park leaves it; the reason is recorded only on the `park_awaiting_human` record both sinks receive, as
`reason: replacement_lineage_unproved` (see
[`../observability/event-streams.md`](../observability/event-streams.md)), so filter the event stream on that to find
every such park. Where it lands tells you what to repair:

- **On the parent, before any child exists.** Its record cannot prove the lineage, it already sits at the lineage
  depth bound, its own split's snapshot reads as neither held nor released or is held with no base recorded, or a
  slice the decomposer proposed names a snapshot ref its child would not be kept. Nothing was created and no
  split marker was written, so repair the record the notice names, or reply asking the decomposer not to split (or
  to leave snapshot refs out of its slices); the reply resumes the decomposer.
- **On the parent, after children exist.** A crash recovery or a dependency poll found a recorded child it cannot
  vouch for — an unreadable pinned comment, a `parent_number` that is not the parent's number, a late ancestry or
  pointer the split did not write, text naming a snapshot ref it cannot keep, a register naming it twice, or a
  receipt in its body other than the one the split stamped for its slice (another slice's, another split's, or one
  owing a different lineage). No child of that split is started while it stands, and the parent is parked once
  rather than on every poll. Repair or close the child the notice names; for a receipt, put back the one the split
  stamped, since the child's own dispatch holds its seed to it.
- **On a child.** Its pinned seed is not the one its receipt says it was owed: it never landed, or its late ancestry
  was taken off, cut down, or rewritten. It is held under every label but `done` and `rejected` — a hand relabel to
  `workflow:ready`, and the adjudication of an oversized candidate of its own, included — until its seed is whole.
  Where its parent is still recovering the split, that recovery writes the seed and clears `awaiting_human` in the
  same write; otherwise write the parent link and the lineage the receipt names, set `awaiting_human` back to
  `false`, or close the child. A child whose pinned comment will not parse is held without a park or a write, logged
  on every tick, so the comment is left for you to repair. A restart you authorize on such a child keeps its seed
  (see [the restart](#restarting-an-issue-whose-cycle-was-cancelled)), so it is not held afterwards.

A crash recovery that cannot take over the child it finds — one a human closed or relabelled, one whose body ends on
a receipt other than this slice's, one the register already records, or a receipt more than one issue carries —
parks the parent under `decomposition_crash` and names it rather than creating the slice again. A drift reset that
discards a manifest also drops the split's attempt, so a child the discarded split left behind is never adopted into
the next one — but it is written onto `late_consumers` first, so the ref waits for it as an orphan.

While such a split is still short of its own count, the snapshot ref its replacements are pointed at is held whatever
the original split's ledger says: the replacement it created last may be on GitHub and not yet recorded as a
consumer. So is a finished one's ref while a replacement it recorded is missing from `late_consumers`, until it is
recorded there again. Either holds the umbrella's terminal, a `blocked` parent's return to its own work, and the
closed-owner sweep — so an owner closed mid-split keeps `workflow:decomposing` and its ref, visited on every sweep.
Two ways out, each in this order:

- **Recover, then close.** On an open owner, the next `workflow:decomposing` tick adopts the unrecorded replacement,
  records it on the ledger, and finalizes; the ref then waits on it like any consumer. Do not close it first: the
  recovery refuses a closed candidate and parks the owner under `decomposition_crash` instead.
- **Discard by hand** where nothing will recover it — a closed owner, or a recovery parked on a candidate it could not
  adopt: close every issue this orchestrator opened carrying the owner's receipt for that `split_attempt`, then remove
  `split_attempt` from the owner's pinned record. The ledger reads as whole again and the ref goes once every recorded
  consumer has ended; closing the unrecorded replacements first keeps it from going while one still works from it.

## Reclaiming a finished issue's artifacts

An issue this orchestrator finished with leaves two things behind on the host that ran it: the per-issue checkout an
agent worked in, and the `orchestrator/`-namespaced branch the work was published on — in the clone and on the remote.
Nothing in the state machine deletes them. A terminal-artifact **maintenance pass** does, once a day by default, and
this section is what an operator needs to run it, read what it reports, and settle what it would not touch.

**Why maintenance and not a workflow stage.** Every stage handler is about one issue in one repository, and several of
them run at once. What this pass reclaims is not per-issue: it is one host's disk and one clone's ref store, shared by
every configured repository and by every worker on the host. A stage cannot say the host is quiet, because a tick is
what makes it busy — and a handler that deleted a directory would be deleting it beside workers it cannot see. So the
pass runs *between* polling passes, over a host that has been proved quiet, and it is deliberately the one deletion
path here that no issue transition triggers. It writes no workflow state at any point: no label, no pinned state, no
comment, no agent session. An issue that has ended keeps every record of how it ended, and a host tidying its own disk
cannot change what GitHub says happened.

### When it runs

- **On the daily interval, when no window is set.** With `TERMINAL_ARTIFACT_CLEANUP_WINDOW` unset or blank, the
  polling loop fits one pass in at the end of the wait between two polling passes — never inside a tick — at most
  once every `TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS` (default `86400`, one day; see
  [`../configuration.md`](../configuration.md#cadence-and-budgets)). The due gate is in memory on a monotonic
  clock, so an NTP step, a suspend, or a timezone change cannot bring a pass forward or push it out, and nothing is
  persisted: a restart costs at most one extra pass. A turn is spent when it is handed out, so a pass that defers
  waits for the next interval.
- **In a local window, when one is set.** `TERMINAL_ARTIFACT_CLEANUP_WINDOW` takes precedence and the interval is not
  consulted. The same boundary between polling passes attempts a pass at its first opportunity inside the window, read
  off the wall clock in `TERMINAL_ARTIFACT_CLEANUP_TIMEZONE` — the start inclusive, the end exclusive:
  - **The window decides when a pass may start, and is read twice.** Once between polling passes, and again after
    the pass has drained its own workers and taken the host lock, since both of those wait. A window that closed
    during that wait starts nothing. A pass that did start keeps its usual bounds — the 120s host-hold budget below —
    whatever the clock does next.
  - **A started pass spends the window.** It is spent as the last thing before discovery, so a pass that then finds
    no candidate, keeps or fails every candidate, raises, or runs out of budget has had its night. Only a deferral
    before that point — workers that would not drain within 30s, or a host lock another process holds — leaves the
    window owed, and the next attempt comes **no sooner than 15 elapsed minutes** later, timed on the monotonic clock
    so a stepped wall clock cannot make attempts more frequent.
  - **Nothing is caught up.** A window the host stayed busy through, or the process was down for, is missed; the
    next attempt is the next window, never a daytime pass.
  - **A window is named by the local date it opened on.** An overnight `23:00-01:00` is one window on both sides of
    midnight, and an hour a daylight-saving fall-back repeats is that same window again, so neither owes a second
    pass. An hour a spring-forward transition skips never occurs, so a window lying wholly inside it is missed that
    night.
  - **Scheduling state is in memory only.** A restart outside the window waits for the next one; a restart inside it
    may repeat a pass the previous process already made that night, which is safe — the pass reads the host again
    and reports whatever is already gone as done. Nothing guarantees exactly one pass per window across restarts.
- **On demand.** `chipping-orchestrator run --cleanup-terminal-artifacts` runs exactly the same pass once and exits,
  regardless of the interval or the window — the form to point a nightly service timer at on hosts whose orchestrator
  is not always up. See [Run modes](#run-modes) for what that mode connects and why it exits 0 when it defers.
- **Only on a quiet host.** Before it reads anything, the pass closes its own scheduler's admission (`submit` refuses
  with `reason=maintenance`, `track_active` hands back `claimed=False`), waits up to 30s for the work already admitted
  to drain, and acts only if the host went quiet inside that bound. Nothing running is cancelled or hurried. A bound
  that expires, a shutdown that started, or a barrier it could not take **defers the whole pass** — which costs one
  finished issue's disk until the next scheduled attempt and nothing else: the next interval with no window set, or no
  sooner than 15 elapsed minutes later inside a window that is still open. Admission always reopens afterwards,
  whatever the pass did.
- **Only one process at a time.** The barrier answers for this process's own workers; a second orchestrator on the
  same host is outside it. So every pass also holds `WORKTREES_DIR/.artifact-maintenance.lock` exclusively while it
  acts, and every polling run holds that same lock shared for its whole life. A pass refused the lock defers; a poller
  that wants it back waits without a deadline. What bounds that wait is the pass itself: it gives the host back at a
  candidate boundary once it has held it for 120s, with whatever it did not reach owed to the next pass. The whole
  mechanism is in [`../configuration.md#parallel-processing`](../configuration.md#parallel-processing).

Both of those are in-application coordination between orchestrator processes. Neither is an OS boundary: see
[`../security.md#scheduled-artifact-reclamation`](../security.md#scheduled-artifact-reclamation) for what that does and
does not protect against, and for the isolation to use where the boundary has to hold against an arbitrary process.

### What it looks for

One host-wide scan per pass, then one repository at a time. A candidate is one *issue*, however many artifacts it is
holding and wherever they are:

- **Branches, in the exact orchestrator namespace.** The clone's `refs/heads/orchestrator/` listing and one
  `git ls-remote` of the same namespace on the remote. One name per issue is recognized and no other: the
  `orchestrator/<sanitized-slug>/issue-<n>` this orchestrator publishes. Any other name is never a candidate — no tag,
  no pull-request ref, no default branch, no branch of anyone else's, and no flat `orchestrator/issue-<n>` an earlier
  layout left, here or only on the remote, is reachable from this path.
- **Checkouts, under the one root it writes.** `WORKTREES_DIR/<sanitized-slug>/issue-<n>`, the per-repository path. A
  directory has to be a real directory under the exact name, reached through no symlink below `WORKTREES_DIR`, *and* a
  worktree of this repository's own clone. A flat `WORKTREES_DIR/issue-<n>` checkout is never listed, so it is never a
  candidate, whichever clone it is a worktree of; one a symlinked per-repository directory reaches is foreign.
- **Remote-only artifacts.** A branch the remote still carries under the owned namespace with nothing left on this
  host — a re-cloned checkout, a host rebuilt, a local ref somebody deleted by hand. The local and remote halves are
  folded into one candidate per issue, so a branch that exists in both places is one artifact over two hosts rather
  than two artifacts.

The `layout` a candidate is reported under says where it was found: `current` (this host still holds its checkout or
branch) or `remote_only` (nothing local at all, only the remote's copy of the branch).

**Shared clones.** Two configured `REPOS` entries can share one ref store — the case slug namespacing exists for —
whether they name one `target_root`, spell it differently, or name linked worktrees of one repository; entries are
grouped by the git common directory their targets share, and one whose store cannot be read is refused and still counted
a claimant on every clone. Attribution re-derives each spec's own names and refuses anything ambiguous: a name several
entries derive alike, a checkout standing on such a name even in a directory of its own (the ref sanitizer's digest
suffix lets two slugs share a branch name while their checkout directories differ), and every checkout under a directory
two lossily-sanitized slugs both produce, is attributed to **none** of them and left alone. A flat branch or checkout is
attributed to nobody on any host — being the only entry that could own it is not ownership — and a flat checkout
standing on a candidate's branch keeps that branch, because the teardown reads what every tree of the clone is standing
on before it deletes one
([what it deletes](#what-it-deletes-and-in-what-order)). A repository whose ref store, checkout root, or remote listing
could not be read is left out of the pass entirely rather than reported in part, and said out loud on the log: a partial
list of what a repository still holds reads exactly like a complete one.

### What clears a candidate, and what keeps it

Every gate fails closed, and they are asked cheapest first. Nothing is deleted unless all of them pass:

1. **Nothing is running for this issue.** The live scheduler is asked per candidate, underneath the barrier that
   already emptied it. An unreadable answer keeps the candidate.
2. **No other orchestrator writer holds the issue.** The issue's writer claim — the one every dispatch and the base
   refresh take, in `WORKTREES_DIR/.issue-writer-claims/` — is taken before the issue is read and held through every
   gate below and the deletions, so nothing else on this host relabels the issue or rewrites its pinned comment in
   between. A claim another holder has, or one that cannot be taken at all, keeps the candidate with nothing read.
3. **The issue has really ended.** It is closed, it carries exactly one terminal workflow label, and its pinned comment
   is one this build admits — a version-1 record, or none at all. Two workflow labels at once, an issue or a comment
   that could not be read, and a pinned comment admission refuses — unversioned, under a version this build does not
   admit, or holding something that is not a state — each keep the candidate. A refused comment keeps it even on an
   issue closed on `done` or `rejected` whose artifacts every other gate would clear: it reads back as empty as an
   issue that recorded nothing, and taken that way the pull request and branch it names would go unasked.
4. **No pull request still stands on it.** Open pull requests are looked up for the issue's branch, for the branch its
   pinned record names, and for the recorded number, whatever base they target. A human reviewing a branch is standing
   on it even though the issue underneath has ended. Every branch lookup is **owner-qualified** — the query head is
   `<this repository's owner>:<branch>`, never the bare branch name — so a fork that happens to carry a branch of the
   same name is not mistaken for this candidate's pull request, in either direction: a fork's open PR cannot keep an
   artifact this repository owns, and it cannot be read as the ended PR that accounts for a commit. The recorded number
   is read straight off this repository for the same reason.
5. **Every commit an artifact holds survives its deletion.** A branch's tip and the commit a checkout's own HEAD is on
   each have to be contained in the configured base or in a pull request that has ended. The remote is asked what the
   branch is at whatever the base says, because the two answer different questions — a merged tip can sit under a
   branch somebody has since pushed past.
6. **The checkout carries nothing of its own.** It has to be reached at its own path rather than through a symlink and
   be on this issue's own current branch — a checkout at that path on a flat branch or any other, or a flat checkout a
   symlinked path reaches, is foreign and keeps the candidate — prove it holds nothing modified
   or untracked, and prove it hides nothing besides: a path the repository's own `.gitignore` covers — a `.env`, a
   virtualenv, a build directory — keeps the whole candidate, because `git worktree remove` would take all of it and
   git does not count it as dirty.
7. **Nothing has touched the checkout for an hour.** Its own directory (for what is created or removed at the top of
   it) and its index and reflog (for the edit-and-commit that moves neither) are read against a one-hour quiet period.
   That period is a constant, not a knob: what a shorter one buys is the chance to delete a tree somebody is standing
   in.

Ambiguous evidence is not permission. Every probe answers "confirmed", "refuted", or "could not read", and the third
is never collapsed into either: a reading that failed keeps the artifact exactly as a reading that said no does.

### What it deletes, and in what order

Order is not a detail here — it is what a failed pass leaves behind:

1. **The checkout first.** A branch a worktree still has checked out cannot be deleted, so a pass that took the branch
   first would strand the tree and make its branch undeletable. Removal is **never forced**: `git worktree remove`
   refuses a tree written in since the proof, and that refusal is the answer.
2. **Then each branch, on the remote before the clone.** The remote is read first so the three answers stay apart — a
   branch that is not there is a step already done (the ordinary shape of a merged pull request's head), a branch at
   another commit is a push nobody here cleared, a reading that failed is not permission to delete. The delete itself
   is a **leased** push pinned to the proved commit, so a branch somebody pushed to between the proof and the delete
   is refused by the remote rather than removed. The local delete is the pinned `update-ref -d` naming that same
   commit and refusing to dereference, so a branch an agent committed onto survives and a symbolic ref planted under a
   branch name is deleted as itself rather than followed onto the base.
3. **Local last, on purpose.** The local ref is the cheapest thing the next discovery finds, so a failed remote delete
   leaves it standing and the candidate discoverable; taking it first would leave a remote-only artifact that only a
   remote listing would ever surface again.

Immediately before each mutation the artifact's tip is re-read against the commit the classification proved, and a
checkout's identity — its path, its clone, its branch — with it. An artifact that has moved since (an agent committed, a
human pushed, a checkout switched onto another branch) is not a failure — it is a race, and the candidate is kept for
the next pass to start over on.

**There is no retry, and that is deliberate.** The first refusal ends the pass *for that candidate*; the ones behind it
are still evaluated. Nothing is written down — no queue, no ledger, no backoff state — because the discovery that found
the candidate once finds whatever is left of it again. That is what makes a repeated pass cheap: it reads the host as
it is now and reports whatever is already gone as done. A candidate refused by a branch-protection ruleset therefore
reports `failed` once per pass until the rule or the branch changes, and costs one pass each time.

### Reading a cleanup result

Every candidate the pass decided about earns **one** bounded
[`terminal_artifact_cleanup`](../observability/event-streams.md#terminal_artifact_cleanup-records) record on the
analytics sink — repository, issue, `outcome`, `reason`, `layout`, and a `branch` where the reason names one — and one
line per candidate on the `orchestrator.worktree_lifecycle` log channel, followed by the pass's own
`cleaned=/retained=/failed=` tally. The log is where the artifact each reason is about is named; the record is
deliberately narrower and never carries a path, a command, or git's own output. Both surfaces are observation-only:
losing either changes nothing about what was deleted. A sink turned off writes nothing and says nothing, and a sink
the filesystem refuses (read-only mount, full disk, a path that is not one) is reported on the `orchestrator.analytics`
channel by the writer itself rather than on the lifecycle channel — so an operator missing records looks there first.

- **`cleaned`** — done. Every artifact that candidate was found holding is gone from this host and the remote,
  absences included. It will not be reported again.
- **`retained`** — the pass declined to act, and it will decline again every pass until something changes. This is the
  one outcome that can repeat forever, so a candidate retained for the same reason day after day is one to settle by
  hand. Match the `reason` against the
  [reason-code table](../observability/event-streams.md#terminal_artifact_cleanup-records):
  - `active_claim` / `recent_activity` are self-clearing — work was in flight, or the checkout had been touched inside
    the hour. Nothing to do.
  - `writer_claim_refused` is another orchestrator writer holding the issue's writer claim on this host — a dispatch,
    a base refresh, another poller's pass — and clears itself once it lets go. Where the `orchestrator.scheduler`
    log's `writer claim skip` line for that issue says `reason=unusable`, or the lifecycle log says the claim could not
    be keyed, nothing holds it: the claim namespace, or the repository's id, could not be read, and that is the host or
    the token to fix.
  - `tip_moved` is a race that also clears itself: something moved the artifact between the proof and the mutation,
    or a checkout stopped being the issue's own — switched onto another branch, or reached through a new symlink —
    which the next pass keeps as `foreign_checkout` until it is put back or disposed of by hand.
  - `unproven` is the classification's own answer, and the log line beside it names the artifact it kept the candidate
    for. Look at that artifact: an open pull request still on the branch (close or merge it), a checkout carrying
    modified, untracked, or ignored files (take what you want off it — an ignored `.env` or a stray build directory is
    the common one), commits the base and every ended pull request do not account for (push them somewhere that
    outlives the branch, or accept the artifact stays), an issue that is not closed, a workflow label that is not
    exactly one terminal, or a `foreign_checkout`: a tree at the issue's path that is another repository, stands on a
    flat or other branch, or is reached through a symlink, which no pass removes and which is yours to dispose of by
    hand. `state_unsupported` and `state_malformed` are a pinned comment this build refuses — an
    object unversioned or under a version it does not admit, and a body that is no state at all — and a warning on
    `orchestrator.worktree_lifecycle` names the repository, the issue, the comment, and the version found against the
    one supported. The pass reclaims nothing of that issue's for as long as the comment stands, so the record and its
    artifacts are yours to dispose of by hand, as
    [deploying without migration](#preserve-records-for-manual-disposition) describes.
  - The `*_unreadable` reasons are a read that failed rather than a fact about the artifact: an expired token, a
    repository this installation cannot see, a remote that was down, a git command that would not run. They clear
    themselves when the underlying read works, and the log line beside them says which artifact could not be read.
  - `branch_checked_out` means some worktree of the clone is still standing on the branch — often an operator's own
    `git worktree add`, or a flat `WORKTREES_DIR/issue-<n>` checkout no pass attributes. Move that tree off the branch
    (or remove it) and the next pass takes it.
- **`failed`** — a step ran and was refused, which is a host or a remote to look at:
  - `worktree_removal_failed` — git would not remove the checkout. It is never forced, so the usual cause is a tree
    written into after the proof, or a permission problem on the directory. Inspect the path on the log line; remove
    it by hand once you are sure nothing wants it.
  - `remote_delete_failed` — the remote refused the leased delete. A ruleset forbidding deletions under
    `refs/heads/orchestrator/*`, a token without the permission, or a branch that moved. This blocks tidying and
    nothing else: no issue is parked or relabelled, and the local ref is deliberately kept so the candidate is found
    again.
  - `local_delete_failed` — the pinned local delete would not run: another process holding the clone's ref store, or a
    ref that moved between the read and the delete.

A candidate the pass never reached has **no** record: nothing was decided about it. The one a stop landed on says
so on the log — `artifacts left alone: this pass may no longer act` — and earns no record either, for the same
reason. That is not a silent failure; see below.

### Recovery after an interrupted pass

A pass can stop part way through for four ordinary reasons: `SIGINT` / `SIGTERM`, the scheduler closing under it, its
120s host-hold budget running out (which is what a polling process waiting for the host is owed), or the process being
killed outright. Whichever it is, **recovery is nothing**:

- Nothing is persisted, so there is no partial state to repair, no lock file to clear (a `flock` dies with the process
  that held it), and no queue to drain. The next pass rediscovers the host as it is.
- A candidate the pass stopped *before* is exactly as it was, and has no result to interpret.
- A candidate whose teardown was under way cannot be half-deleted in a way that matters. A signal is never answered
  mid-teardown: the last reading is taken immediately before the first mutation, and past it the candidate is taken as
  one unit. What a kill can interrupt is therefore a checkout removal and, per branch, a leased remote delete and a
  pinned local one — each idempotent and each already leased to a proved commit. What ran is done, and what did not is
  rediscovered; an artifact already gone is simply reported as done next time.
- The pass that ran can leave a checkout removed with its branch still standing, or a branch gone from the remote and
  still in the clone. Both are discoverable states, and the next pass finishes them.

So an interrupted pass costs the wait for the next scheduled pass — the next interval with no window set, or the next
night's window, since a pass that started has spent its own — and a crashed one costs no more: the process that comes
back is owed a pass at once on the interval, and inside the window may repeat that night's. If a host was killed
mid-pass often enough to matter, the thing to check is not the artifacts but why: the pass gives the host back on its
own at a candidate boundary, and never blocks workflow progress either way.

## Applying `.env` changes

`~/.config/chipping-orchestrator/.env` is read once, when `chipping-orchestrator run` starts. Most edits take effect
on the next process start; there is no signal to reload configuration. Restart the foreground command or systemd
service at a safe stopping point. A repository `add-repo` adds is such an edit, and `add-repo` says to restart when
the service is running. [Developer checkouts](../development.md) use their own root `.env`.

### What survives a restart

Per-issue progress lives in the issue's pinned JSON comment on GitHub and in the per-issue worktree on disk, and an
Antigravity developer launch also keeps a quota retirement record on the host
([An owed quota retirement](#running-more-than-one-poller)). Restarting between ticks loses nothing — the next tick
picks each issue back up from its label and pinned state, and from that record on the same host. That holds for a
restart onto a build that reads the formats the stopped one wrote; starting one that cannot is a
[deployment without migration](#deploying-without-migration), and what it cannot read is not resumed. Three
restart-time hazards are worth knowing:

- **A live `codex` / `claude` child.** Stage handlers spawn agent subprocesses that may run for as long as
  `AGENT_TIMEOUT`. On a SIGTERM/SIGINT stop the loop terminates in-flight agent process groups up front (and, as a hard
  backstop, the shutdown watchdog force-terminates them after `SHUTDOWN_GRACE_SECONDS` and exits), so the process leaves
  within the grace window instead of holding open for up to `AGENT_TIMEOUT` and being SIGKILLed at the systemd stop
  deadline. The interrupted child is still killed mid-session. The runner flags such a run `interrupted` (distinct from
  `timed_out`), and every dev-resume stage handler (`implementing`, `validating`, `fixing`, `documenting`, `in_review`,
  `resolving_conflict`) short-circuits on it — they ignore the partial result and leave durable GitHub state
  untouched, so the next process retries the resume from scratch rather than parking on `awaiting_human` or routing
  through timeout recovery. A dirty worktree may still remain on disk for the next tick to reconcile.
- **A live `agy` child's quota record.** Every Antigravity developer launch arms its issue's quota retirement record
  before it runs, and the run's return settles it — the interrupted return above included. Each change is flushed to
  disk first, so the record outlives a crash of the host as well as of the poller, but it lives only under this
  host's `WORKTREES_DIR`: back it up and restore it with the rest of that namespace
  ([backups](../security.md#backup-and-restore-drills)). A poller that dies before that return reaches the record —
  killed past the shutdown watchdog, by SIGKILL, or with the host — leaves the arming standing, which says nothing
  about whether a quota stopped the run, so every developer launch on that issue waits, logging an error each tick,
  until an operator writes the retirement it owes or settles it as `{}`
  ([An owed quota retirement](#running-more-than-one-poller)).
- **In-flight agent spec is pinned.** When a `codex` / `claude` session starts, the orchestrator writes the full
  `DEV_AGENT` / `DECOMPOSE_AGENT` spec into pinned state and re-parses it (not the current `.env`) on every resume.
  Flipping `DEV_AGENT` or `DECOMPOSE_AGENT` after a session is locked does nothing for that issue until it reaches
  `done` or `rejected`. The question and discussion stages each seed from `DECOMPOSE_AGENT` on their own first spawn
  and pin to `question_agent` / `discussion_agent` for the rest of that conversation. `REVIEW_AGENT` is not pinned —
  the reviewer spawns fresh each round.

### Safe restart guidance

- **Idle / between ticks — safe.** Restart freely; the next tick resumes from GitHub state.
- **Issue mid-stage with no agent child — generally safe.** Workflow state is on GitHub and in the worktree.
- **Live `codex` / `claude` / `agy` child — avoid.** Wait for the agent to exit. Forcing a restart can park the issue,
  leave a dirty worktree behind, or leave an `agy` launch's quota record armed for an operator to settle.

Set the shell's `LOG_DIR` to the running process's log directory:
`~/.local/state/chipping-orchestrator/logs` after package setup above, unless overridden. Use an absolute path;
settings in `.env` are not automatically shell variables. Then inspect processes and logs:

```sh
pgrep -af 'chipping-orchestrator|codex|claude|agy'
tail -f "${LOG_DIR:?}/orchestrator.log"
journalctl --user-unit chipping-orchestrator.service -f   # systemd users
```

### Per launch style

**Foreground terminal.**

1. Edit `~/.config/chipping-orchestrator/.env`.
2. Wait for a safe stopping point without an agent child; inspect processes with `pgrep -af 'codex|claude|agy'`.
3. Ctrl+C the command and wait for shutdown.
4. Start `chipping-orchestrator run` again.

**systemd user service.**

1. Edit `~/.config/chipping-orchestrator/.env`.
2. Run `chipping-orchestrator check` as the service user and repair what it reports
   ([compatibility check](#check-compatibility-and-start)).
3. Run [`chipping-orchestrator init`](#installing-with-init) again only if the interpreter path or the directories the
   agents are found in changed; it rewrites and reloads the unit. A reload reads unit definitions, not `.env`.
4. When safe, run `chipping-orchestrator restart`. It repeats the local check and leaves the running service as it is
   if that finds a problem, then [reports the service active](#operating) or prints its last journal lines.
5. Tail logs with `journalctl --user-unit chipping-orchestrator.service -f`.

Change an `Environment=` value with `systemctl --user edit chipping-orchestrator.service`, which reloads the unit once
the editor exits, before restarting; `init` rewrites the unit file itself, so a value edited there is lost on its next
run. `start` and `restart` check the service with the values a drop-in's `Environment=` sets, a `GITHUB_TOKEN` among
them, and refuse one that reads an `EnvironmentFile=` ([operating](#operating)). `check` and `init` read tokens from the
token files alone, so store each with `set-token`, which all four judge alike.

Each `chipping-orchestrator run --once` invocation starts a new process and reads current settings. Restarts keep the
installed package version; [package upgrades](#upgrade-a-package) are explicit operator actions. Development
wrapper restarts are described in the [developer guide](../development.md#development-restart-wrapper).

### Setting-by-setting expectations

When each setting's change takes effect:

- `TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS` — next Python start, like the settings below, and the restart also
  starts a fresh due gate: the cadence is held in memory, so with no window set the run that comes back is owed a
  pass at once rather than at the end of an interval it cannot remember. A repeated pass costs one discovery and
  reports whatever is already gone as done.
- `TERMINAL_ARTIFACT_CLEANUP_WINDOW`, `TERMINAL_ARTIFACT_CLEANUP_TIMEZONE` — next Python start, where both are
  validated again: a malformed window, or a blank or unresolvable timezone beside a set one, stops that start. The
  restart also forgets which window was spent: a run that comes back outside the window waits for the next one, and
  one that comes back inside it may repeat that night's pass.
- `POLL_INTERVAL`, `AGENT_TIMEOUT`, `REVIEW_TIMEOUT`, `SHUTDOWN_GRACE_SECONDS`, `MAX_REVIEW_ROUNDS`,
  `MAX_CONFLICT_ROUNDS`, `MAX_RETRIES_PER_DAY`, `MAX_ADDED_LINES`, `DEV_SESSION_MAX_RESUMES`,
  `MAX_AGENT_RUNS_PER_ISSUE`, `IN_REVIEW_DEBOUNCE_SECONDS`, `DECOMPOSE`, `SQUASH_ON_APPROVAL`,
  `PR_REF_IN_SUBJECT`, `EXPOSE_TRACKED_REPOS`, `VERIFY_COMMANDS`, `VERIFY_TIMEOUT`, `LOG_DIR`, `EVENT_LOG_PATH`,
  `ANALYTICS_LOG_PATH`, `ANALYTICS_RETENTION_DAYS`, `TRACK_SKILL_TRIGGERS`, `TRAJECTORY_LOG_PATH`,
  `TRAJECTORY_RETENTION_DAYS`, `REPO` / `REPOS` / `TARGET_REPO_ROOT` / `BASE_BRANCH` / `REMOTE_NAME`, `HITL_HANDLE`,
  `ALLOWED_ISSUE_AUTHORS` — next Python start
- `WORKTREES_DIR` — next Python start. Left unset, it follows the first `REPOS` entry, or `TARGET_REPO_ROOT` without
  `REPOS`, so an edit that changes either moves it too: set it explicitly before such an edit on a host with issues in
  flight ([default](../configuration.md#workspace-and-agent-identity))
- `ANALYTICS_DB_URL` — next analytics sync invocation and dashboard launch
  ([operator sync commands](../observability/analytics-database.md#operator-workflow),
  [developer dashboard commands](../development.md#analytics-sync-and-dashboard)).
  The value is parsed once when the analytics settings holder is first imported, so a browser reload is not enough —
  relaunch Streamlit. The polling loop does not read this setting.
- `DASHBOARD_PARALLEL_READS` — next developer analytics dashboard launch.
  The value is parsed once per process, on the first render's import of the read-mode owner.
- `MAX_PARALLEL_ISSUES_PER_REPO`, `MAX_PARALLEL_ISSUES_GLOBAL` — next Python start. Per-`REPOS` `parallel_limit`
  overrides take precedence over `MAX_PARALLEL_ISSUES_PER_REPO`.
- `WORKFLOW_TRANSITION_GUARD` — next Python start (parsed at config import).
- `DEV_AGENT`, `DECOMPOSE_AGENT` — next Python start, **except** for issues whose pinned state already names a
  `dev_agent` / `decomposer_agent` / `question_agent` / `discussion_agent` — those keep the pinned spec until the
  issue reaches `done` or `rejected`
- `REVIEW_AGENT` — next reviewer spawn after the next Python start (not pinned per issue)
- `GITHUB_TOKEN` — not loaded from `.env`. Update the process environment or rewrite the token file before the next
  start: the one `ORCHESTRATOR_TOKEN_FILE` names, or else each configured repository's own
  `~/.config/<owner>/<repo>/token`, which `chipping-orchestrator set-token <owner>/<repo>` replaces once the new token
  reaches the repository
- `ORCHESTRATOR_BASE_BRANCH` — developer source wrappers capture this before the restart loop, so editing it requires
  restarting the wrapper itself ([developer guide](../development.md#development-restart-wrapper)). The Python
  process picks it up on the same next start. An installed package never uses it: the
  [self-restart guard](../architecture.md#process-model) runs only in a source checkout.
