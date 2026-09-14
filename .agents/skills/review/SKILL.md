---
name: review
description: >-
  Review checklist for reviewer agents on chipping-orchestrator PRs. Use when
  evaluating a developer-produced branch before approval or change-requests.
---

# Reviewer skill — chipping-orchestrator

## CI / lint

Reject (or request fixes) if any of these are red:

- `ruff check orchestrator tests`. Common offenders to look for explicitly:
  - **F401** — remove unused bindings and import definitions from their owners. Package initializers are
    markers and carry no imports or `__all__`. Existing test support re-exports use `... as <name>` only
    for a name the module never reads itself; their exact paths are declared under `PLC0414` in
    `[tool.ruff.lint.per-file-ignores]`. `tests/repository/test_reexport_aliases.py` holds that set.
  - **F541** — f-strings without placeholders, typically in newly-added test files.
  - **F841** — unused local in tests.
  - **E402** — import after non-import code.
- `uv run flake8 orchestrator tests --select=WPS`. All WPS naming, complexity, consistency, bug-prevention,
  refactoring, and OOP findings are rejection criteria.
- `git diff --check origin/main...HEAD` — trailing whitespace and blank lines at EOF. Check it even
  if everything else looks clean.
- Full `pytest` run is referenced in the PR description and passes end-to-end. Reject "known failure"
  hand-waves; if the PR claims a baseline failure, the description must include a reproduction on
  `origin/main` at the branch point. Otherwise the developer must fix it.
- Every source file the PR adds (`*.py`, `*.sh`, `pyproject.toml`) opens with the `# Copyright 2026 Geser Dugarov` /
  `# SPDX-License-Identifier: Apache-2.0` header pair.

## Behavior preservation

For any refactor:

- Workflow labels, pinned-state JSON keys, comment marker text, watermark fields, and event-emission
  shape must match `main` exactly. Issues already in flight depend on these — a rename is a migration,
  not a refactor.
- Spot-check that moved code still routes through the same auth / fetch / push / retry helpers. A
  refactor is not allowed to silently change side effects.
- Squash-on-approval, the in_review HITL ready-ping gates (mergeable + approved + no standing
  CHANGES_REQUESTED), retry budgets, and stale-session detection are easy to break by accident during
  a move; verify their call paths survive intact.

## Workflow owners and stage modules

Every package initializer is a marker, so callers name defining modules directly. Labels live on
`workflow/state.py`, label parsing on `workflow/label_reading.py`, the graph on `workflow/transitions.py`, and
write guards on `workflow/transition_guard.py`. The per-repo tick lives on `workflow/engine/tick.py` and resolved
process settings on `config/settings.py`. Confirm:

- Initializers bind no engine, stage, model, service, or settings owner. The GitHub and git layers can import
  the label, reading, graph, and guard owners without loading the engine into their own initialization.
  `tests/workflow/test_imports.py` checks that direction, and `tests/repository/test_package_exports.py` checks
  every initializer's source and namespace.
- Settings reloads and patches target `orchestrator.config.settings`, the same module object all callers retain.
  Repository types come from `config.models`, and token resolution from `config.credentials`.
- Stage modules import the owner they borrow from at module scope and call through that alias; flag any
  reintroduced call-time hop through the package initializer.
- Test patches target the module the call site names. Flag a test that patches anything else — including
  the workflow package — since a mock left there intercepts nothing.
- Stage-private helpers stay in the stage package that owns them. Shared helpers are read from their defining
  owner; copying or re-exporting one creates a second patch target that can drift from the running call.
- Workflow owners declare `log = logging.getLogger("orchestrator.workflow")` with the channel spelled literally;
  `workflow/transition_guard.py` owns `orchestrator.state_machine`. Operator filters select on those names,
  and `tests/workflow/test_imports.py` checks them.

## Test economy and assertion quality

- Identify newly added tests that duplicate existing tests or each other; request merging into
  `pytest.mark.parametrize` cases or a small named loop when the only difference is fixture values or
  branch selection.
- Verify each added test fails against the old behavior or directly protects a changed contract.
- For resource-usage fixes (over-fetching, redundant API calls, retained state), reject tests that
  only assert the final result; require at least one assertion at the helper/producer level.
- Prefer fewer tests with clear distinct coverage over many narrowly overlapping regression tests.
- Check placement: tests mirror the runtime layout, so a module under `orchestrator/<package>/` is covered by
  `tests/<package>/` and stage handlers by `tests/workflow/stages/<stage>/`. Flag a new omnibus module added beside
  an existing per-behavior split, a test parked away from the owner it exercises, and a stage reaching into a
  sibling stage's `*_test_support.py` for fixtures.

## Documentation drift

After any handler or helper move, grep the PR for stale pointers and request fixes in:

- `docs/architecture.md` and the focused pages under `docs/architecture/` — the module-by-module inventory
  lives here and nowhere else, except `docs/architecture/observability-modules.md`, which maps
  `observability/` and `apps/` at the package boundary: flag a per-module entry grown back into that page
  rather than asking for one
- `docs/state-machine.md` and the focused pages under `docs/state-machine/`
- `docs/workflow.md` and the focused pages under `docs/workflow/`
- module docstrings at the top of the owners the symbol moved between, and of the package initializers
  above them that describe where a name answers

`AGENTS.md` (and its `CLAUDE.md` symlink) is deliberately off that list, and the inverse is what to flag: it is
loaded into every agent session and carries no module, owner, or test inventory. Reject a PR that answers a routine
symbol or module move by editing it, or that grows an inventory back into it. It changes only when repository-wide
agent instructions, safety rules, or documentation routing change.

Treat blanket statements about what a package publishes — "every helper is re-exported", "the hub answers for
these names" — with suspicion; verify literally against the code, since an attribute that no longer exists raises
`AttributeError` rather than reading as stale prose.

## Comment hygiene

- Flag diff-relative comments — "previously", "the old retry cap", "instead of a dict", "now uses" —
  in code and test docstrings alike. A comment must read correctly to someone who never saw the
  change; the before/after story belongs in the commit message or PR description.
- Flag comments that paraphrase an already-readable line or the assert below them instead of stating
  a why (invariant, non-local consumer, prevented failure). Ask for the reason or for deletion. Do
  not flag plain-language summaries above genuinely dense code (tricky offset math, multi-step
  comprehension chains) — a comment that is faster to understand than the code it heads earns its
  place.

## `plans/` references

- `plans/` holds human working notes, not spec. Flag any code, comment, docstring, or test that cites
  a `plans/` document — or a numbered "Proposal N" from one — as authoritative; the change must stand
  on its own once that note is revised or deleted. Ask for the reference to be reworded to describe the
  behavior directly.
- A developer should not edit or remove files under `plans/` unless the issue explicitly asked. Flag
  unrequested `plans/` changes.

## Commit hygiene

- Conventional Commits: `<type>: <subject>` only. Reject any commit with a body, a `Co-Authored-By`
  trailer, or a non-imperative subject. Type must be one of `feat`, `fix`, `chore`, `docs`,
  `refactor`, `test`.

## Out of scope — push back

- Dependencies outside the issue's stated scope.
- Reformatting of files outside the change's blast radius.
- Abstractions or generality added for hypothetical future features. The issue's stated scope is the source of truth.
