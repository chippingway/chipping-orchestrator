---
name: develop
description: >-
  Project conventions and recurring gotchas for implementer agents working on
  chipping-orchestrator. Use before committing any change in orchestrator/,
  tests/, or docs/.
---

# Developer skill — chipping-orchestrator

## Environment and commands

The repo targets Python 3.12+ and installs from the lockfile with [`uv`](https://github.com/astral-sh/uv):

```sh
uv sync --locked                              # creates .venv/ and installs runtime + dev deps from uv.lock
uv run ruff check orchestrator tests          # run Ruff
uv run flake8 orchestrator tests --select=WPS # run wemake-python-styleguide
uv run pytest tests                           # run the test suite
uv run python -m orchestrator --once          # one polling tick then exit
uv run python -m orchestrator --log-level DEBUG
```

## License headers

Every source file (`*.py`, `*.sh`, `pyproject.toml`) starts with:

```
# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
```

## Commits

- Conventional Commits: `<type>: <subject>` with one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
- Subject line only — no body, no `Co-Authored-By` trailer, no extended description. One `-m` flag.
- Imperative mood, short and specific. Match the style in `git log --oneline -20`.

## Pre-push checklist

Before committing, run each of these and fix what they report:

- `.venv/bin/python -m ruff check orchestrator tests` — the lint contract is **Ruff's own default rule set plus
  `E501`**. `[tool.ruff.lint]` in `pyproject.toml` declares no `select`, so the run enforces whatever the `ruff`
  resolved in `uv.lock` ships as its defaults; do not add one back, and do not answer a new diagnostic by narrowing
  the selection. Re-resolving that lock can bring rules with it — fix what they report, in the same commit as the
  bump. There is no tree-wide waiver either: the only suppressions are the exact-path entries under
  `[tool.ruff.lint.per-file-ignores]` and inline `# noqa: <CODE> - <reason>` directives, each naming the rule it
  covers and why, and `tests/repository/test_noqa_directives.py` fails on a bare `# noqa` or a file-wide
  `# ruff: noqa`. Recurring CI breakers:
  - **F401** (unused import): if the name is meant to be a re-export from a package facade that binds its
    surface with imports (`orchestrator/agents/`, `github/`, `scheduler/`, `observability/usage/`), alias it with
    `... as <name>` so ruff treats it as an explicit re-export instead of dead code. A name the initializer
    lists in `__all__` — how `orchestrator/workflow/` publishes its label and guard surface — is already exempt.
    Outside an initializer that alias also trips **PLC0414**, so the module has to be one of the exact paths
    waived under `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`; alias only a name the module never reads
    itself, and add the path in the same commit. `tests/repository/test_reexport_aliases.py` fails on anything else.
  - **F541** (f-string without placeholders): use a plain string.
  - **F841** (unused local).
  - **E402** (module-level import not at top of file).
  - **BLE001** (blind `except Exception`): only a handler that must catch blind gets a `# noqa: BLE001 - <reason>`
    naming what the catch protects; anything narrower catches the exception it means.
  - The defaults also carry the modernization and simplification families — **UP**, **B**, **SIM**, **C4**, **RET**,
    **RUF** — so a diagnostic from one of those is a rewrite, not a waiver.
- `uv run ruff check orchestrator tests --select=I001 --fix` — `I001` is in the run above, so this is just the fixer
  for it; `tests/repository/test_import_sorting.py` fails on a block left unsorted too. Never split one module's names
  across several `from ... import` statements to duck **WPS235** — the sorter merges every statement reading from the
  same module back into one.
- `uv run flake8 orchestrator tests --select=WPS` — all WPS naming, complexity, consistency, bug-prevention,
  refactoring, and OOP rules must pass.
- `git diff --check origin/main...HEAD` — catches trailing whitespace and stray blank lines at EOF.
- `.venv/bin/python -m pytest` — full suite must pass. Do not assume any "known" failure is
  acceptable; if a test fails on your branch, first reproduce it on `origin/main` at the same SHA
  you branched from, and only then call it out in the PR as a baseline failure with the reproduction
  steps. Otherwise fix it.

## Workflow owners and stage modules

Most package initializers are markers. The deliberate public APIs retain their explicit `__all__` surfaces and
exact-path WPS410/WPS412 exclusions. `orchestrator.workflow` publishes the two label vocabularies, the transition
guard, its predicate and exception, and the lazy per-repo `tick` entry point. Labels live on `workflow/state.py`,
label parsing on `workflow/label_reading.py`, the graph on `workflow/transitions.py`, and write guards on
`workflow/transition_guard.py`.

- The workflow initializer imports no engine or stage. Its `tick` shim resolves `workflow/engine/tick.py` inside
  the call, so the GitHub and git layers can import labels and guards without an initialization cycle.
  `tests/workflow/test_imports.py` checks that direction, and `tests/repository/test_package_exports.py` holds the
  declared public surfaces and marker initializers.
- Settings reloads and patches target `orchestrator.config`, the same module object all callers retain.
  `config.RepoSpec` is the public alias of `config.models.RepoSpec`; callers that need only the type may import its
  defining owner. Token resolution is defined on `config.credentials`.
- Stage modules import the owner they borrow from at module scope —
  `from orchestrator.git.worktrees import paths as _worktree_paths`,
  `from orchestrator.workflow.engine import guards as _guards` — and call through that alias. Never
  reintroduce a call-time hop through the package initializer.
- Tests patch the owner. `tests/workflow/git_owners.py` records which git module defines each seam
  (`GIT_SEAM_OWNERS`, `seam_patch`) and `tests/workflow/patch_context.py` installs every hermetic mock
  on that table plus the agent runner, raising rather than falling back when a name has no owner.
- Stage-private helpers stay in the stage package that owns them. Shared helpers are read from their defining
  owner; copying or re-exporting one creates a second patch target that can drift from the running call.
- Each owner declares its own `log = logging.getLogger("orchestrator.workflow")` with the channel spelled
  literally (`workflow/transition_guard.py` owns `orchestrator.state_machine`). Operator filters select on those names,
  so never derive one from `__name__`; `tests/workflow/test_imports.py` walks the package and checks it.
- Preserve the public contract verbatim across a refactor: workflow labels, pinned-state JSON keys,
  comment marker text, watermark fields, event-emission shape. Live issues already carry these — a
  "harmless rename" is a migration, not a refactor.

## Tests

- When you move a helper to a new module, move the test's patch target to that owner with it. There is no
  second site to patch instead: the module the call site names is the only one a mock intercepts.
- Tests mirror the runtime layout: a module under `orchestrator/<package>/` is covered by `tests/<package>/`, and
  stage-handler tests live beside their owners under `tests/workflow/stages/<stage>/`. Put a new test in the module
  that already covers the behavior's owner; add a new module only when none does, and name it after the behavior it
  protects rather than after the symbol it calls.
- Each stage package's tests are already split into focused modules — routing, the outcomes one tick can reach, the
  parks, drift, live pause — with the fixtures they share in a `*_test_support.py` beside them. Follow the split
  that is there instead of growing one omnibus module, and put a stage's shared fixtures in
  its own support module rather than in a sibling stage's.
- Each tests package carries its package-level guards (clean-process import, import-cycle / layering direction,
  and public surface) in its own `test_imports.py`.
- Helpers that belong to no single stage get their own focused module under `tests/workflow/`, and
  `tests/workflow/fixtures.py` re-exports the ones a test spanning several of those leaves needs.
  Nothing lands at the `tests/` root: a helper shared across domains goes under `tests/support/`, and
  a test covering the repository's own files or the root package goes under `tests/repository/`.
- Prefer extending the in-memory fakes in `tests/support/github/` (reached through the
  `tests/support/fakes.py` bridge) over mocking PyGithub directly. New behavior should land with tests in
  the matching stage file.
- Before finalizing tests, do a redundancy pass:
  - List each added/modified test and the distinct behavior it protects.
  - Merge tests that differ only by input shape or branch case into `pytest.mark.parametrize` cases
    or a small named loop, unless separate setup materially improves clarity.
  - Prefer one focused helper/unit test that covers sibling branches over multiple tests with repeated setup.
  - Keep end-to-end tests only when they exercise an integration boundary that helper tests cannot cover.
  - Ensure assertions observe the behavior being fixed. For resource-usage bugs (over-fetching,
    redundant API calls, retained state), add a direct assertion at the helper/producer level when
    final-result checks could pass for the wrong reason.
  - Remove incidental low-level assertions when existing tests already cover that behavior.

## Comments

Write every comment against the current state of the code, as if it had always been this way:

- Prefer stating why the code below exists — the invariant it protects, the non-local consumer it
  serves, the failure it prevents — over describing what it does. If a comment paraphrases an
  already-readable line (`# cap the page size at what we still need` above `min(remaining, page_size)`)
  or the assert below it, delete it or replace it with the reason.
- Exception: a plain-language summary of genuinely dense code (tricky offset math, a multi-step
  comprehension or iterator chain, subtle ordering constraints) is fine even though it "restates" the
  code. The test is whether the comment is faster to understand than the code below it, not whether
  it repeats it.
- No diff-relative wording: "previously", "the old X", "instead of a `set`", "no longer", "now sized
  to". Those sentences address the reviewer and go stale the moment the PR merges — put the
  before/after story in the commit message or PR description instead.
- Same rule for test docstrings: describe the behavior the test pins down, not the bug or implementation it replaced.

## Documentation drift

When you move a handler, helper, or constant, grep for the symbol across these files and update them in the same commit:

- `docs/architecture.md` and the focused pages under `docs/architecture/` — the module-by-module inventory
  lives here and nowhere else, with one exception:
  `docs/architecture/observability-modules.md` maps `observability/` and `apps/` at the package boundary, so a
  move inside those two trees updates the owner's own module docstring rather than a map entry
- `docs/state-machine.md` and the focused pages under `docs/state-machine/`
- `docs/workflow.md` and the focused pages under `docs/workflow/`
- the module docstrings at the top of the owners the symbol moved between

`AGENTS.md` (and its `CLAUDE.md` symlink) is deliberately not on that list. It carries no module, owner, or test
inventory, so a routine symbol or module move must leave it alone. Update it only when repository-wide agent
instructions, safety rules, or documentation routing change.

Be precise about what a package does and does not publish — overstated claims like "every helper is re-exported"
get flagged.

## `plans/` is working notes, not spec

Files under `plans/` (roadmap, design explorations, proposal write-ups) are human working notes, not
authoritative implementation requirements. Implement what the **issue** asks for; do not treat a
`plans/` document — or a numbered "Proposal N" inside one — as a spec to satisfy, and do not cite one
in code, comments, docstrings, or commit messages (that reference outlives the note and goes stale the
moment it is revised or deleted). Leave files under `plans/` untouched unless the current issue
explicitly asks you to edit or remove one.

## Dependencies

`pyproject.toml` pins `PyGithub` and `psycopg[binary]` as runtime deps; `pytest`, `pytest-cov`, `ruff`, and
`wemake-python-styleguide` live in the `dev` group; the analytics dashboard's `streamlit` and `plotly` live in the
separate `dashboard` group so the default `uv sync --locked` stays minimal. `uv.lock` is the source of truth for exact
versions and is committed — regenerate it (`uv lock`) whenever `pyproject.toml` changes. Anything else needs
justification.

## Out of scope without explicit ask

- Adding dependencies that the current issue did not request.
- Reformatting unrelated files or churning whitespace.
- "Future-proofing" abstractions for hypothetical features. Implement what the issue asks for and stop.
