# Migrate dependency, build, and publishing tooling from uv to Poetry

Date: 2026-10-05. Status: proposal; nothing is implemented. Base: `main` at `5ef81121`. Versions checked: Poetry 2.5.1
(2026-09-20), poetry-core 2.5.0, poetry-plugin-export 1.10.1, uv 0.11.16. External facts are linked under
[Sources](#sources).

## Summary

Replace uv as the environment manager, lock tool, and publisher with Poetry 2.5, and replace the hatchling build
backend with poetry-core. Keep the PEP 621 `[project]` table and the PEP 735 `[dependency-groups]` table. Poetry 2.5
reads both, so the manifest stays mostly tool-neutral and the migration stays easy to revert. Seed `poetry.lock` from
the versions `uv.lock` pins on the migration base. The migration then changes tools without changing any installed
version.

The motivation is a review of this repository's uv usage against a published account of moving from uv back to
Poetry. Poetry fixes some of the problems found there directly. Others don't depend on the tool and need their own
fixes; this plan lands those first, so they are kept even if the migration is abandoned. The
[problem map](#problem-map) records which problem falls in which group.

## Trial migration findings

These results come from running Poetry 2.5.1 against a scratch copy of `main`. No repository file was changed.

- **Python range.** Poetry reads `[project]` and `[dependency-groups]`, but a plain `poetry lock` fails.
  `wemake-python-styleguide` declares `Requires-Python <4.0`, and Poetry requires every dependency to be installable
  across the whole `requires-python` range, which here has no ceiling. A lock-only cap fixes this:
  `[tool.poetry.dependencies] python = ">=3.12,<4.0"`. The built wheel still declares `Requires-Python: >=3.12`.
- **Fresh resolution drifts.** A fresh lock resolves the same 68 packages as `uv.lock`, but 35 at newer versions.
  Among them are `ruff` (its resolved version defines the lint rule set), `pyflakes` 3 → 4, `websockets` 16 → 17, and
  `pyarrow` 24 → 25. This skips both the Dependabot cooldowns and review.
- **Seeding works.** Seeding reproduced all 68 `uv.lock` versions exactly: add a temporary group of `name==version`
  pins exported from `uv.lock`, lock, remove the group, and lock again. Without `--regenerate`, `poetry lock` keeps
  versions already in the lock.
- **Root install needs poetry-core.** `poetry install` cannot install the root project while hatchling is the build
  backend. Poetry looks for a package named after the distribution and stops with "No file/folder found for package
  chipping-orchestrator". `poetry build` does honor hatchling; it has accepted any backend since 2.1. Even then,
  `poetry install` always installs the root project with Poetry's own editable builder and ignores `[tool.hatch.*]`
  ([editable builder][poetry-editable]). Keeping hatchling would therefore need a second packaging configuration in
  `[tool.poetry]`, and the tested editable install could drift from the wheel. Switching to poetry-core with
  `packages = [{ include = "orchestrator" }]` gives one packaging configuration for both commands; the console script
  then installs and `--help` succeeds.
- **Group defaults.** Poetry installs every non-optional group by default, PEP 735 groups included. Keeping the
  default install to runtime plus `dev` requires `[tool.poetry.group.docs] optional = true` and the same for
  `dashboard`.
- **Exact vs. additive installs.** `poetry sync` is exact: run without `--with docs`, it removed the 15 packages that
  group had installed. `poetry install` adds and changes packages but removes none.
- **Version bumps leave the lock alone.** `poetry.lock` records no root project version, and its `content-hash`
  ignores `project.version`. After a version bump, `poetry lock` left the file byte-identical and
  `poetry check --lock` passed. Changing groups or optional flags does change the hash. A stale lock makes
  `poetry sync` fail with "pyproject.toml changed significantly since poetry.lock was last generated".
- **Capped `poetry add`.** `poetry add` writes capped constraints, for example `tomli-w (>=1.2.0,<2.0.0)`.
- **Tool version is enforced.** `requires-poetry` in `[tool.poetry]` is checked on every command: "This project
  requires Poetry >=2.6,<3, but you are using Poetry 2.5.1".
- **Environments.** The in-project `.venv` that Poetry creates contains pip.
- **Export is a plugin.** `poetry export` is not bundled. poetry-plugin-export 1.10.1 provides it, with
  `--all-groups` and the `requirements.txt`, `constraints.txt`, and `pylock.toml` formats.
- **Outdated report.** `poetry show --outdated --top-level` lists outdated direct dependencies.
- **Smaller sdist.** The poetry-core sdist holds only `orchestrator/`, `pyproject.toml`, `PKG-INFO`, and `LICENSE`,
  plus the README once it is declared. Today's hatchling sdist holds about 2,300 entries, including `tests/`,
  `plans/`, `.claude/`, and `.agents/`, and any untracked file that isn't gitignored.
- **Implicit classifiers.** Without a `classifiers` list, poetry-core adds Python version classifiers up to 3.15,
  advertising versions CI never runs. An explicit list replaces them.
- **Speed and disk.** Installing every group from a warm cache took 0.8 s with uv and 3.1 s with Poetry. uv hardlinks
  environments from its cache (8,349 shared files); Poetry copies them (none shared). Each worktree's default
  environment then costs about 89 MB of real disk instead of nearly none.

## Problem map

Each item gives the problem, what Poetry changes, and what this plan does. Items 1–15 come from the uv review;
items 16–21 were found while checking the repository and during the trial.

1. **Uncapped `>=` bounds on runtime dependencies** (`PyGithub>=2.1`, `psycopg[binary]>=3.3.4`). Only source
   checkouts get the lockfile; a PyPI install resolves fresh. The `PyGithub` lower bound (2.1) has never been tested,
   since CI runs only the locked 2.10.0. Neither dependency has an upper bound.
   - *Poetry:* new `poetry add` entries get a cap; existing entries don't change. Poetry has no equivalent of uv's
     `--resolution lowest-direct`, so a resolver flag can no longer test lower bounds.
   - *Plan:* raise lower bounds to the locked versions and cap majors: `PyGithub>=2.10,<3`,
     `psycopg[binary]>=3.3.4,<4`. Have Dependabot keep lower bounds equal to the tested versions; the strategy is in
     [open questions](#open-questions). The `dev`, `docs`, and `dashboard` groups never ship, so they keep their
     `>=` bounds; the `ruff` convention is recorded in `pyproject.toml`. Attach a runtime constraints file to each
     GitHub release so operators can reproduce the tested set (see item 7).
2. **README broken on PyPI.** There is no `readme` field yet. About 25 relative links and `./pics/analytics_page.png`
   would 404 on PyPI.
   - *Poetry:* no change. poetry-core has no hook for rewriting the README; leaving hatchling also drops the
     `hatch-fancy-pypi-readme` option.
   - *Plan:* declare `readme = "README.md"` and make README links absolute: repository files under
     `https://github.com/chippingway/chipping-orchestrator/blob/main/`, the image under
     `https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/`. `test_doc_links.py` skips external
     links, so extend it to map those two URL prefixes back to repository paths and check that the paths exist.
     That keeps the dead-link guard for the README. The release checklist also gains a README-rendering check
     (`twine check --strict` from a throwaway environment). `poetry publish` does not validate rendering; the request
     has been open since 2019 ([poetry#769][poetry-769]).
3. **Environments without pip.** With a uv-created `.venv` active, a bare `pip install` reaches some other pip.
   - *Poetry:* fixed for the project environment, which contains pip.
   - *Plan:* PyPI installation docs name one installer per route, each with its own upgrade and rollback commands:
     `pipx install chipping-orchestrator==X`, or `python -m venv` followed by `python -m pip install`. Never bare
     `pip`.
4. **Implicit sync in `uv run`.** In CI it can hide a missing install. In agent worktrees it keeps leftover groups
   installed and rewrites the lock without being asked.
   - *Poetry:* `poetry run` never installs. The flip side is that a stale environment stays stale until someone syncs
     it.
   - *Plan:* CI runs `poetry check --lock` and then `poetry sync`. The develop skill tells agents to run
     `poetry sync` (with `--with dashboard` or `--with docs` when a change needs them) before checks in a worktree.
     `run.sh` syncs after self-update (item 16).
5. **Project version recorded in the lock.**
   - *Poetry:* fixed (verified in the trial).
   - *Plan:* the release procedure drops the "regenerate the lock" step. The test that ties the manifest version to
     `orchestrator.__version__` stays.
6. **`pip.conf` ignored; mirror URLs baked into the lock.**
   - *Poetry:* worse than uv here. It doesn't read `pip.conf` or `PIP_INDEX_URL` either ([poetry#1554][poetry-1554]),
     and unlike uv's `UV_DEFAULT_INDEX` it has no user-level mirror setting. A global override is still an open
     request ([poetry#1632][poetry-1632]); `POETRY_REPOSITORIES_<NAME>_URL` applies only to publishing. A source
     declared as `[[tool.poetry.source]]` is written into `poetry.lock` as `[package.source]` entries. Packages from
     the implicit PyPI source get none; there are none today.
   - *Plan:* never commit a package source. A repository test fails if `pyproject.toml` declares `tool.poetry.source`
     or `poetry.lock` holds a `[package.source]` entry. A maintainer behind a mirror uses the third-party
     [`poetry-plugin-pypi-mirror`][pypi-mirror-plugin], which reads `POETRY_PYPI_MIRROR_URL`. Confirm it leaves the
     lock clean before relying on it (see [open questions](#open-questions)).
7. **Non-standard lock format (PEP 751).**
   - *Poetry:* neutral. `poetry.lock` is non-standard too, but the export plugin writes `pylock.toml`.
   - *Plan:* per release, export `poetry export --only main -f constraints.txt` (and optionally `pylock.toml`) and
     attach it to the GitHub release. That provides the reproducible set from item 1 without requiring Poetry. The
     `pylock.toml` export needs Poetry 2.3 or newer and plugin 1.10 or newer. pip-audit 2.9 can audit that file
     directly with `--locked`, which is an option for the vulnerability scan later.
8. **Tool ownership, and an unpinned tool.** CI installs the latest uv on every run, while actions are pinned by SHA
   and dependencies wait out cooldowns.
   - *Poetry:* maintained by the community `python-poetry` organization, with no company owner listed. Astral, which
     makes uv, announced on 2026-03-19 that it would join OpenAI ([announcement][astral-openai]); closing was subject
     to regulatory approval and is unconfirmed. `requires-poetry` is enforced on every command, and checked before any
     other validation since 2.3.
   - *Plan:* set `requires-poetry = ">=2.5.1,<2.6"`. Nothing below 2.3.3 is acceptable in any case: before 2.3.0,
     editing `[dependency-groups]` did not mark the lock stale, and 2.3.3 fixed lost `include-group` entries. CI
     installs exactly `poetry==2.5.1`; the vulnerability scan also installs `poetry-plugin-export==1.10.1`.
     Dependabot can't bump these pins because they live in `run:` lines, so bumps are deliberate PRs. A repository
     test checks that the CI pin satisfies `requires-poetry`. The plugin is not declared in
     `[tool.poetry.requires-plugins]`: `poetry sync` would then fetch it from the network for every developer, and a
     job that only exports would still need it installed separately.
   - *Plan, supply chain:* commit `solver.min-release-age = 14` in `poetry.toml` (Poetry 2.4+, verified on 2.5.1). It
     keeps a lock made by a maintainer or an agent from picking up releases younger than the shortest Dependabot
     cooldown. Dependabot's own cooldowns still govern its PRs.
9. **uv-downloaded Python builds.**
   - *Poetry:* uses interpreters already present. In CI they come from `actions/setup-python`. Don't use the
     experimental `poetry python install`: it downloads the same python-build-standalone builds that uv uses, hosted
     by Astral.
   - *Plan:* cost: the maintainer's local release smoke tests on 3.13 and 3.14 need real interpreters (pyenv or
     deadsnakes). The maintainer machine has those two only as uv-managed builds today.
10. **Two versions of one package in the lock.**
    - *Poetry:* can also lock several versions of one package under different markers. None today (68 unique
      names).
    - *Plan:* a repository test asserts unique package names in `poetry.lock`, so any split gets reviewed instead of
      slipping in.
11. **Dependabot support.**
    - *Poetry:* there is no `poetry` ecosystem value; Dependabot handles Poetry 2 through `pip`
      ([options reference][dependabot-options]). It treats a project as Poetry-based only when `[tool.poetry]`
      exists, or when `poetry.lock` exists and the backend is poetry-core; the target configuration has both. The
      `pip` ecosystem supports the SemVer-tiered cooldowns. `allow:` is evaluated in shared code, so the `gitpython`
      rule behaves as it does under `uv`.
    - *Known Dependabot issues:*
      - an open crash on `include-group` (unused here);
      - an open fix for Poetry updates that touch dependency groups, which can fail or drift;
      - packages pulled in only by other packages are not refreshed proactively.
      A June 2026 fix made lock regeneration respect cooldowns.
    - *Plan:* switch the `uv` entry to `pip`, keeping the cooldowns and the `allow:` rules, including `gitpython`.
      Labels are covered in [Dependabot labels](#dependabot-labels). The first update cycle after the migration is
      the check for the dependency-group issue (see [Rollout](#rollout)).
12. **Docker layer caching.** `plans/docker-deployment.md` installs "from `uv.lock`".
    - *Poetry:* `poetry install --no-root` also needs `pyproject.toml`, which changes on every version bump, so the
      dependency layer would still rebuild each release.
    - *Plan:* the image installs a hash-checked main-group export and then the wheel, both produced in a builder
      stage, with no Poetry in the runtime image. The export leaves out the root project, so a version-only release
      reuses the dependency layer. Subtask 2 of [`docker-deployment.md`](docker-deployment.md) now says so.
13. **Package name in the lock breaks templates; tox-uv breaks `uv self update`; the `uv check` alias.** Not
    applicable.
14. **Workspaces and Dependabot.** Not applicable today. Poetry has no workspaces at all, so a future split of the
    dashboard into its own package would need a path dependency or a separate repository.
15. **No outdated report.** Fixed: `poetry show --outdated --top-level` (uv's equivalent is `uv tree --outdated`).
16. **`run.sh` never syncs dependencies.** After `git pull`, a merged dependency change restarts on the stale
    `.venv`. Imports then fail and the process restarts every second.
    - *Plan:* when `pyproject.toml` or `poetry.lock` differs between the pre-pull and post-pull `HEAD`, run
      `poetry install --no-interaction`. It is additive, so an operator's `dashboard` group survives. A missing
      `poetry` binary or a failed install logs a warning and launches the existing environment, matching the
      existing pull-failure contract. The operations docs state that the systemd unit's `PATH` must include Poetry's
      directory.
17. **sdist contents.**
    - *Plan:* keep poetry-core's minimal default (package, manifest, license, README). Tests are not shipped.
18. **Error messages assume a source checkout.** The three messages in
    `orchestrator/observability/analytics/sync/database.py`, `.../analytics/query/connections.py`, and
    `orchestrator/observability/dashboard/page_states.py` name uv commands.
    - *Plan:* word them for both install routes: reinstall the package, or `poetry sync` in a checkout.
19. **Implicit classifiers.**
    - *Plan:* declare Python 3.12, 3.13, and 3.14 classifiers in `[project]`. A repository test ties them to the CI
      matrix.
20. **The lock-only Python cap invites a wrong fix.** Someone may "simplify" it by capping `requires-python`, which
    would publish `<4.0` to every installer.
    - *Plan:* a comment beside the cap in `pyproject.toml` explains this, and a repository test asserts that
      `project.requires-python` has no upper bound.
21. **Stray `uv run` in a Poetry checkout.** It would write a fresh `uv.lock` and re-sync the shared `.venv` from its
    own new resolution. Existing crontabs, units, and habits all use it, for example the trajectory prune cron in
    `docs/observability/trajectories.md`.
    - *Plan:* replace every documented `uv run` with `.venv/bin/python` or `poetry run`, list the change in the
      release notes, and add `uv.lock` to `.gitignore` so an accidental lock is never committed.

## Target configuration

`pyproject.toml` after migration (license header and existing comments kept; tool sections for Ruff and pytest
unchanged):

```toml
[project]
name = "chipping-orchestrator"
version = "0.12.0"
description = "GitHub-Issue-driven AI agent workflow."
readme = "README.md"
requires-python = ">=3.12"
license = "Apache-2.0"
license-files = ["LICENSE"]
classifiers = [
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
]
dependencies = ["PyGithub>=2.10,<3", "psycopg[binary]>=3.3.4,<4"]

[project.urls]
# repository, documentation, issues -- as the PyPI release plan specifies

[project.scripts]
chipping-orchestrator = "orchestrator.cli:main"

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"

[tool.poetry]
requires-poetry = ">=2.5.1,<2.6"
packages = [{ include = "orchestrator" }]

# Lock-only Python range: wemake-python-styleguide declares <4.0. This never reaches the published
# Requires-Python, which stays `>=3.12` above; do not move the cap there.
[tool.poetry.dependencies]
python = ">=3.12,<4.0"

[tool.poetry.group.docs]
optional = true

[tool.poetry.group.dashboard]
optional = true

[dependency-groups]
dev = ["pytest>=9.1.1", "pytest-cov>=7.1.0", "ruff>=0.16.3", "wemake-python-styleguide>=1.7.1"]
docs = ["mkdocs>=1.6.1"]
dashboard = ["streamlit>=1.61.1", "plotly>=6.9.0"]
```

`poetry.toml`, committed:

```toml
[virtualenvs]
in-project = true

[solver]
min-release-age = 14
```

The in-project setting keeps the environment at `.venv/`, the path that `run.sh`, `.gitignore`, the docs, and agents
already use. The solver setting is the lock-time cooldown from item 8.

## Changes by area

### Tooling and lock

- Replace `uv.lock` with a seeded `poetry.lock`, built with the procedure in [Seeding the lock](#seeding-the-lock).
- Add `uv.lock` to `.gitignore`. In `tests/support/line_scanning.py`, add `poetry.lock` beside `uv.lock` in the
  line-length exemptions.
- Add repository tests:
  - `poetry.lock` has unique package names and no `[package.source]` entries.
  - `pyproject.toml` declares no `tool.poetry.source`.
  - `requires-python` has no upper bound.
  - The classifiers match the CI matrix.
  - The CI Poetry pin satisfies `requires-poetry`.
  - The README has no relative link targets.

### CI (`.github/workflows/ci.yml`)

Replace `astral-sh/setup-uv` with `actions/setup-python` v7.0.0
(`5fda3b95a4ea91299a34e894583c3862153e4b97`), pinned by full SHA as `test_workflow_action_pins.py` requires. Poetry's
CI guidance is a pinned `pipx install` ([CI recommendations][poetry-ci]). pipx is preinstalled on the Ubuntu 24.04
runner image and on the 26.04 image that `ubuntu-latest` moves to in November 2026. Leave setup-python's
`cache: poetry` off at first: it caches whole environments keyed on `poetry.lock`, and correctness should not depend
on a restored environment. Then:

```yaml
- run: pipx install "poetry==2.5.1"
- run: poetry env use "$(command -v python)"        # the matrix interpreter setup-python put on PATH
- run: poetry check --lock
- run: poetry sync --no-interaction
- run: poetry run ruff check orchestrator tests .github/scripts/docs_site.py
- run: poetry run flake8 orchestrator tests .github/scripts/docs_site.py --select=WPS
- run: poetry run python -m pytest tests --cov=orchestrator --cov-report=term-missing
- run: poetry build
- run: |                                                # installed exactly as a PyPI user would, with pip
    python -m venv "$RUNNER_TEMP/wheel-env"
    "$RUNNER_TEMP/wheel-env/bin/python" -m pip install dist/*.whl
    "$RUNNER_TEMP/wheel-env/bin/chipping-orchestrator" --help
```

Add the same smoke test for the sdist. `poetry build` builds the wheel from the source tree, not from the sdist, so
only installing the sdist catches a file missing from it. Update `tests/repository/test_ci_workflow.py` to match.

### Documentation and vulnerability workflows

- `docs.yml`: run `poetry sync --with docs` and `poetry run mkdocs build --strict`, and change the path filter from
  `uv.lock` to `poetry.lock`. Update `tests/repository/test_docs_site.py` and the `INSTALL_HINT` in
  `docs_site_test_support.py`.
- `vulnerability-scan.yml`: install `poetry==2.5.1` with `pipx inject poetry poetry-plugin-export==1.10.1`. Export
  with `poetry export --all-groups --without-hashes -f requirements.txt`, then strip markers with the existing `sed`.
  Audit with `pipx run "pip-audit>=2.9,<3"` using the existing `--no-deps --disable-pip --strict` flags.

### Dependabot

- Change `package-ecosystem: uv` to `pip`, keeping the cooldowns and `allow:` rules. Update
  `tests/repository/test_dependabot_config.py`.

#### Dependabot labels

Dependabot stamps update PRs with `workflow:python:uv`. It is a service label, not a `WorkflowLabel` member, and
nothing in the tree reads it ([`labels-and-state.md`](../docs/state-machine/labels-and-state.md)). Live PRs still carry
it, so treat a rename as a migration:

- Create `workflow:python:pip` on GitHub before the change merges, and stamp it from the new entry.
- Leave the old label on existing PRs, and record it as retired in `docs/state-machine/labels-and-state.md` and
  `docs/configuration/operations.md`.
- Close any open uv update PRs. The first `pip` cycle replaces them.

### Runtime and launcher

- `run.sh`: add the conditional `poetry install` from item 16.
- The three error messages from item 18.

### Agent instructions and documentation

- `AGENTS.md` (also `CLAUDE.md`), `.agents/skills/develop/SKILL.md`, `.agents/skills/review/SKILL.md`: the command
  block becomes `poetry sync`, `poetry run ruff …`, `poetry run flake8 …`, `poetry run pytest tests`, and
  `poetry run python -m orchestrator --once`. The dependency policy names `poetry.lock` and `poetry lock`. Agents
  must run `poetry sync` in a fresh worktree; `poetry run` won't install anything.
- `README.md`: prerequisites name Poetry; links become absolute (item 2).
- `CONTRIBUTING.md`, `docs/configuration.md`, `docs/configuration/operations.md` (CI, docs-site, and Dependabot
  sections, launcher), `docs/configuration/observability.md`, `docs/observability.md`,
  `docs/observability/analytics-dashboard.md`, `docs/observability/analytics-database.md`,
  `docs/observability/trajectories.md` (cron line), and `docs/security.md` (the CODEOWNERS entry `/uv.lock` becomes
  `/poetry.lock`, plus the CI and lockfile descriptions).
- `.env.example.advanced`: the dashboard launch comments.
- Test messages shown to people: the `_SKIP_REASON` strings in the ten dashboard chart tests,
  `tests/apps/test_analytics_dashboard_render.py`, `tests/cli/test_entrypoints.py`, and the comment in
  `tests/observability/test_optional_dependencies.py`.
- **Left unchanged:** fixtures under `tests/workflow/`, `tests/github/`, and `tests/support/github/` whose sample
  agent evidence contains `uv run pytest` text. Those strings are opaque report content, and no behavior depends on
  the tool named in them.

### Related plans

- [`docker-deployment.md`](docker-deployment.md), updated on this branch:
  - subtask 2 builds the wheel and a hash-checked runtime export in a builder stage, installs Poetry as agent
    tooling, and keeps a uv fallback (item 12);
  - subtask 4 sizes the disk quota for copied per-worktree environments.
- `plans/pypi-release.md` on the `pypi-release` branch, updated to the Poetry procedure below. The procedure waits
  for this migration and lists this plan's tool-independent fixes as release prerequisites. The maintainer guide in
  `CONTRIBUTING.md` on that branch keeps its uv commands until the branch is rebased onto this migration.

## Seeding the lock

Run this on the migration branch before deleting `uv.lock`:

```bash
uv export --locked --all-groups --no-emit-project --no-hashes --no-annotate --format requirements-txt \
  | sed 's/ ;.*//' > /tmp/uv-pins.txt
# Temporarily add a `uv-pins` dependency group listing every line of /tmp/uv-pins.txt.
poetry lock
# Remove the `uv-pins` group, then:
poetry lock
poetry check --lock
```

Verify the result before committing. The `name version` pairs from `poetry.lock` must equal those from `uv.lock`,
apart from the root project; the trial matched 68 of 68. The migration PR changes no installed version. Dependency
moves resume through Dependabot afterwards.

## Release procedure

`plans/pypi-release.md` on the `pypi-release` branch holds the full procedure. The maintainer release guide changes as
follows:

- Version bump: update `pyproject.toml` and `orchestrator/__init__.py`. There is no lock step.
- Build: `poetry build --output "$RELEASE_DIST"` from the clean tagged checkout.
- Smoke tests: for each of 3.12, 3.13, and 3.14, create `python3.X -m venv`, run `python -m pip install` on the wheel
  and then the sdist, and run `chipping-orchestrator --help`, outside the checkout. Add `twine check --strict` on
  both files.
- Upload: read the token at a hidden prompt into `POETRY_PYPI_TOKEN_PYPI` inside a subshell, then run
  `poetry publish --dist-dir "$RELEASE_DIST"`. `poetry publish` cannot take named files. It uploads the latest
  version's `chipping_orchestrator-*.whl` and `.tar.gz` from the directory, using each artifact's own metadata. A
  fresh version-specific directory is therefore what limits the upload to the two checked files. Retry an
  interrupted upload with the same files and without `--skip-existing`. PyPI accepts an identical re-upload and
  rejects a conflicting file with "File already exists"; `--skip-existing` would turn that rejection into a silent
  skip. Then compare the SHA-256 digests on PyPI with the retained files.
- Attach the runtime constraints export (item 7) to the GitHub release.

## Rollout

1. **Tool-independent fixes, on uv.** Land these first; each one stands alone if the migration stops here:
   - dependency bounds (item 1);
   - `run.sh` sync after self-update, written with `uv sync --locked --inexact` for now (item 16);
   - absolute README links and their test (item 2);
   - error messages (item 18).
2. **Migration PR.** Everything in [Changes by area](#changes-by-area) goes in one PR, because CI, tests, docs, and
   agent instructions must agree at every commit. Create the `workflow:python:pip` label before merging.
3. **Operator cut-over.** The lock is seeded identically, so the uv-created `.venv` stays valid when `run.sh`
   self-updates onto the merge; nothing breaks in the meantime. Then:
   - install Poetry (`pipx install poetry==2.5.1`) where the systemd unit's `PATH` can find it;
   - stop the service;
   - run `rm -rf .venv && poetry sync`, adding `--with dashboard` where the dashboard runs;
   - replace `uv run` in crontabs and units;
   - restart.
4. **First Dependabot cycle.** Confirm that `pip` update PRs change `pyproject.toml` and `poetry.lock` together, cover
   the dependency groups, honor the cooldowns, and carry the new labels.
5. **PyPI release.** Proceed with the release plan using the procedure above.

**Rollback:** revert the migration PR, then run `rm -rf .venv && uv sync --locked`. The seeded pins mean the revert
changes no versions either, as long as no dependency PR has merged in between.

## Costs

- **Speed and disk.** Measured in the trial: each sync is about four times slower with a warm cache, and each
  worktree environment holds real copies of its files. This multiplies with the orchestrator's parallel per-issue
  worktrees. It is acceptable at today's 89 MB default environment.
- **Lost uv features.** Lower-bound resolution (`--resolution lowest-direct`), Python downloads, `uv tool` and `uvx`
  convenience, and workspaces.
- **Poetry-specific configuration.** Four entries in an otherwise tool-neutral manifest: the lock-only Python cap,
  the optional-group flags, `packages`, and `requires-poetry`.
- **`poetry add` style.** It writes `name (>=x,<y)`, unlike the existing `name>=x` entries. Both are valid PEP 508;
  normalize by hand when reviewing.

The alternative is to stay on uv and fix its defaults:

- `UV_LOCKED` or `--no-sync` in CI;
- `required-version`;
- the dependency bounds;
- the `run.sh` sync;
- an explicit sdist include list.

That covers items 1, 2, 4, 8, and 16–19 without migrating. Only Poetry provides the remaining gains: a lock without the
project version, pip in the environment, no implicit sync, a minimal default sdist, capped `poetry add`, and
community governance.

## Open questions

- **Dependabot lower bounds:** which `versioning-strategy` for the `pip` ecosystem keeps the runtime lower bounds in
  `[project].dependencies` equal to the locked versions while preserving the `<N` caps (item 1)? Check it on the
  first update cycle.
- **Dependabot groups:** do update PRs for `dev`, `docs`, and `dashboard` packages update `poetry.lock` cleanly while
  the dependency-group fix is still open? Check it on the first cycle; fall back to manual group bumps if not.
- **Mirror plugin:** does a lock made through `poetry-plugin-pypi-mirror` stay free of `[package.source]` entries and
  mirror URLs? Check it before any maintainer depends on it.
- **Dependency graph:** confirm that GitHub's dependency graph and `dependency-review.yml` read `poetry.lock` with
  `[project]` metadata.

## Sources

- [Poetry changelog][poetry-changelog]: 2.2 adds PEP 735 groups, 2.3 adds groups to the lock hash and 2.3.3 fixes
  `include-group`, 2.4 adds `solver.min-release-age`, and 2.5.1 is the current release.
- [Dependency groups][poetry-groups]; [`requires-poetry` and `packages`][poetry-pyproject];
  [alternative build backends][poetry-backends].
- [Editable root install in 2.5.1][poetry-editable]; [lock content hash in 2.5.1][poetry-locker].
- [`poetry publish` uploader in 2.5.1][poetry-uploader]; [README check request][poetry-769].
- [Package sources][poetry-sources]; [pip.conf answer][poetry-1554]; [global mirror request][poetry-1632];
  [mirror plugin][pypi-mirror-plugin].
- [poetry-plugin-export changelog][export-changelog]; [CI recommendations][poetry-ci].
- [Dependabot options reference][dependabot-options]; [Dependabot Python file updater][dependabot-updater].
- [setup-python v7.0.0][setup-python]; [Astral joins OpenAI][astral-openai].

[poetry-changelog]: https://github.com/python-poetry/poetry/blob/main/CHANGELOG.md
[poetry-groups]: https://python-poetry.org/docs/managing-dependencies/#dependency-groups
[poetry-pyproject]: https://python-poetry.org/docs/pyproject/
[poetry-backends]: https://python-poetry.org/docs/libraries/#alternative-build-backends
[poetry-editable]:
  https://github.com/python-poetry/poetry/blob/2.5.1/src/poetry/masonry/builders/editable.py
[poetry-locker]: https://github.com/python-poetry/poetry/blob/2.5.1/src/poetry/packages/locker.py
[poetry-uploader]: https://github.com/python-poetry/poetry/blob/2.5.1/src/poetry/publishing/uploader.py
[poetry-769]: https://github.com/python-poetry/poetry/issues/769
[poetry-sources]: https://python-poetry.org/docs/repositories/#package-sources
[poetry-1554]: https://github.com/python-poetry/poetry/issues/1554
[poetry-1632]: https://github.com/python-poetry/poetry/issues/1632
[pypi-mirror-plugin]: https://pypi.org/project/poetry-plugin-pypi-mirror/
[export-changelog]: https://github.com/python-poetry/poetry-plugin-export/blob/main/CHANGELOG.md
[poetry-ci]: https://python-poetry.org/docs/#ci-recommendations
[dependabot-options]:
  https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference
[dependabot-updater]:
  https://github.com/dependabot/dependabot-core/blob/0db0342964b1627e76be5d5449e7fbbf48b88b70/python/lib/dependabot/python/file_updater.rb
[setup-python]: https://github.com/actions/setup-python/releases/tag/v7.0.0
[astral-openai]: https://astral.sh/blog/openai
