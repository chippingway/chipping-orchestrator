# Repository guide for AI agents

This file is the entry point for AI coding agents (Codex, Claude, etc.) working on this repository. `CLAUDE.md` is a
symlink to this file, so both conventions resolve to the same content.

It is loaded into every agent session — keep it short. It routes to the authoritative documents; detail belongs
there, not here. Update this file only when repository-wide agent instructions, safety rules, or documentation
routing change — never to track a moved handler, helper, module, or test.

## What this project is

`chipping-orchestrator` is a GitHub-Issue-driven workflow that watches issues on configured repos, drives them through a
label-based state machine, and spawns local CLI agents (`codex`, `claude`) in per-issue git worktrees to implement
them and open PRs. State lives entirely in GitHub (one workflow label + one pinned JSON comment per issue), so the
orchestrator process is stateless.

## Where the details live

[`docs/README.md`](docs/README.md) is the documentation landing page: it maps every page in the set, names the focused
page under each area, and explains which addresses stay stable. Open it when the area below is not obviously the right
one.

- User-facing overview: [`README.md`](README.md)
- Architecture, module ownership, process / agent / push model: [`docs/architecture.md`](docs/architecture.md), with
  the per-package inventory on the pages under [`docs/architecture/`](docs/architecture/)
- Workflow state machine (labels, per-tick flow, pinned state, stage handlers):
  [`docs/state-machine.md`](docs/state-machine.md), with the label, delivery-stage, conversation-stage, and lifecycle
  pages under [`docs/state-machine/`](docs/state-machine/)
- Agent roles, conversation contracts, command specs, session lifecycles: [`docs/workflow.md`](docs/workflow.md), with
  the role, conversation, and spec pages under [`docs/workflow/`](docs/workflow/)
- Configuration / env vars: [`docs/configuration.md`](docs/configuration.md) is the reference, with the observability
  settings and the operator runbooks under [`docs/configuration/`](docs/configuration/); basic knobs in
  [`.env.example`](.env.example), common advanced overrides in [`.env.example.advanced`](.env.example.advanced)
- Observability: [`docs/observability.md`](docs/observability.md) maps every surface, with the event-stream,
  trajectory, database, dashboard, and usage-parser pages under [`docs/observability/`](docs/observability/)
- Security checklist and operator-owned controls: [`docs/security.md`](docs/security.md)
- Development conventions and the pre-push checklist:
  [`.agents/skills/develop/SKILL.md`](.agents/skills/develop/SKILL.md)

## Repository layout

Top level only. Which module owns what is in
[`docs/architecture.md`](docs/architecture.md#top-level-layout) and the focused pages under
`docs/architecture/`, which are the single place that inventory is maintained.

- `orchestrator/` — the Python package. The root carries the version, `cli.py` (the composition point the
  `chipping-orchestrator` console script calls), and `__main__.py` (the `python -m orchestrator` form over it); every
  other module lives under a subpackage named after what it owns: `workflow/` (tick loop, label dispatch, and the
  per-label stage handlers under `workflow/stages/`), `github/`, `git/`, `agents/`, `scheduler/`, `config/`,
  `skills/`, `runtime/` (the polling process), `apps/` (the `streamlit run` targets), and `observability/` (analytics
  sink, dashboards, usage parser).
- `tests/` — pytest suite, mirroring the package layout (`tests/workflow/`, `tests/github/`, `tests/git/`, …).
  In-memory GitHub doubles live in `tests/support/github/`.
- `docs/` — architecture, state-machine, workflow, configuration, observability, and security references.
- `plans/` — human working notes, not specifications (see below).
- `analytics-db/` — operator-owned local analytics database (see below).
- `run.sh` — production launcher that auto-restarts after self-modifying merges.
- `.env.example` / `.env.example.advanced` — basic and advanced configuration templates.

## Development

Read [`.agents/skills/develop/SKILL.md`](.agents/skills/develop/SKILL.md) before changing anything under
`orchestrator/`, `tests/`, or `docs/`. It carries the commands, commit format, license headers, test placement,
comment rules, and dependency policy.

Any agent that sizes or splits an issue, including the late adjudication of an oversized committed change, must first
read [`.agents/skills/decompose/SKILL.md`](.agents/skills/decompose/SKILL.md). It carries what a child's scope has to
include, the residual test every proposed child passes, and how the initial and late stages differ.

The repo targets Python 3.12+ and installs from the lockfile with [`uv`](https://github.com/astral-sh/uv):

```sh
uv sync --locked                              # creates .venv/ and installs runtime + dev deps from uv.lock
uv run pytest tests                           # run the test suite
uv run python -m orchestrator --once          # one polling tick then exit
```

Tests are the primary correctness gate. Add or update tests for any behavioral change.

## Safety and compatibility

- **`analytics-db/data/` is off limits.** It is the operator-owned Docker bind mount holding the local analytics
  Postgres volume — runtime state, not source. **Never traverse, read, modify, permission-repair, delete, or re-run
  any command against it with elevated privileges.** If a tool reports it as unreadable, that is expected: target
  `tests` explicitly (the default `pytest` config already ignores the directory) rather than escalating access.
- **Workflow labels and pinned-state JSON fields are a compatibility contract.** Live issues already carry them, so a
  rename is a migration, not a refactor. The same holds for comment marker text, watermark fields, and event payload
  shapes. When touching the state machine, agent invocation, or stage handlers, read
  [`docs/state-machine.md`](docs/state-machine.md) and [`docs/workflow.md`](docs/workflow.md) first.
- **Secrets.** `GITHUB_TOKEN` is deliberately *not* loaded from `.env`. Tokens live in
  `~/.config/<owner>/<repo>/token` or the process environment. Rationale:
  [`docs/configuration.md`](docs/configuration.md#github-personal-access-token).
- **`plans/` is working notes, not spec.** Files under `plans/` (roadmap, design explorations, proposals) are
  non-authoritative. Implement what the issue asks for, do not cite a `plans/` document in code, comments, or commit
  messages, and leave those files untouched unless the issue explicitly asks you to edit one.

## Out of scope without explicit ask

- New external dependencies, frameworks, or services.
- Reformatting unrelated files or churning whitespace.
- "Future-proofing" abstractions for hypothetical features. Implement what the issue asks for and stop.
