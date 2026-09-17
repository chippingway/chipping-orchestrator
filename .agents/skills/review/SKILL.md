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
  - **F401** — unused import on a package initializer. If the import is intended as a re-export, it must
    be aliased `from X import Y as Y` or listed in that initializer's `__all__`. A bare import will not
    survive ruff.
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
- Every source file the PR adds (`*.py`, `*.sh`, `pyproject.toml`) places the `# Copyright 2026 Geser Dugarov` /
  `# SPDX-License-Identifier: Apache-2.0` header pair immediately after any shebang, or at the beginning of the file
  when there is no shebang.

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
- Verify each added regression test fails before the fix and passes afterward.
- Require tests for changed contracts to assert those contracts directly.
- Allow tests that document and protect existing behavior, including coverage added before refactoring.
- For resource-usage fixes (over-fetching, redundant API calls, retained state), reject tests that
  only assert the final result; require at least one assertion at the helper/producer level.
- Prefer fewer tests with clear distinct coverage over many narrowly overlapping regression tests.
- Check placement: tests mirror the runtime layout, so a module under `orchestrator/<package>/` is covered by
  `tests/<package>/` and stage handlers by `tests/workflow/stages/<stage>/`. Flag a new omnibus module added beside
  an existing per-behavior split, a test parked away from the owner it exercises, and a stage reaching into a
  sibling stage's `*_test_support.py` for fixtures.

## Documentation drift

After a PR moves, renames, or deletes a symbol or module — a handler, helper, constant, or whole owner — grep the
PR for stale pointers to that name, inventory entries and docstrings included, and request fixes in:

- `docs/architecture.md` and the focused pages under `docs/architecture/` — the module-by-module inventory
  lives here and nowhere else, except `docs/architecture/observability-modules.md`, which maps
  `observability/` and `apps/` at the package boundary: flag a per-module entry grown back into that page
  rather than asking for one
- `docs/state-machine.md` and the focused pages under `docs/state-machine/`
- `docs/workflow.md` and the focused pages under `docs/workflow/`
- module docstrings at the top of the owners the symbol moved between, was renamed in, or was deleted from, and of
  the package initializers above them that describe where a name answers

`AGENTS.md` (and its `CLAUDE.md` symlink) is deliberately off that list, and the inverse is what to flag: it is
loaded into every agent session and carries no module, owner, or test inventory. Reject a PR that answers a routine
move, rename, or deletion of a symbol or module by editing it, or that grows an inventory back into it. It changes
only when repository-wide agent instructions, safety rules, or documentation routing change.

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
- Reject a developer commit whose subject ends in a numeric reference — ` (#N)` — the tracked issue's own number
  most of all. Publication references belong to the orchestrator, which appends the pull request's own reference when
  it publishes; a developer-written suffix lands a subject naming the issue and the pull request both. Read the
  subjects on the branch, not only the PR title, since approval planning can reuse a developer subject verbatim.

## Out of scope — push back

- Dependencies outside the issue's stated scope.
- Reformatting of files outside the change's blast radius.
- Abstractions or generality added for hypothetical future features. The issue's stated scope is the source of truth.
