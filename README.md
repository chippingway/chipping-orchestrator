# chipping-orchestrator

[![CI][ci-badge]][ci-link]
[![OpenSSF Scorecard][scorecard-badge]][scorecard-link]
[![OpenSSF Best Practices][best-practices-badge]][best-practices-link]

`chipping-orchestrator` turns GitHub issues into reviewed pull requests with local coding-agent CLIs (`codex`,
`claude`, or `agy`). It plans the work, implements it in an isolated git worktree, reviews the result, and asks a
human to make the final merge decision.

Workflow state lives on the issue itself, so progress stays visible on GitHub and survives process restarts without a
separate queue or workflow database.

## How it works

An issue normally follows this path:

```text
workflow:decomposing → workflow:ready → workflow:implementing
  → workflow:validating → workflow:documenting → in_review
  → done or rejected
```

The decomposer can split large work into child issues. The implementer commits in a dedicated worktree, the reviewer
requests fixes until the change is ready, and the orchestrator opens or updates the pull request. Oversized changes,
conflicts, retries, and human decisions take explicit side paths; pull requests are never merged automatically.

See the [state-machine overview](docs/state-machine.md) for labels and transitions, and the
[workflow guide](docs/workflow.md) for agent roles and session behavior.

## Requirements

- Linux, Git, Python 3.12 or newer, and [`uv`](https://docs.astral.sh/uv/getting-started/installation/). CI tests
  Python 3.12, 3.13, and 3.14; newer versions are not tested.
- An authenticated CLI for every configured role. Defaults are
  [`claude`](https://docs.anthropic.com/en/docs/claude-code) for decomposition and implementation, and
  [`codex`](https://github.com/openai/codex) for review. Any role can instead use
  [Antigravity (`agy`)](https://antigravity.google/docs/cli/headless/).
- A GitHub repository and a fine-grained personal access token with read/write access to Contents, Issues, and Pull
  requests, plus read-only access to Metadata.

Agents run with their approval and sandbox checks disabled, so the host account is the security boundary. Read the
[security checklist](docs/security.md) before using the orchestrator on a public or untrusted repository.

## Quick start

Clone and install from the lockfile:

```sh
git clone https://github.com/chippingway/orchestrator.git chipping-orchestrator
cd chipping-orchestrator
uv sync --locked
cp .env.example .env
```

Edit `.env` and set at least:

- `HITL_HANDLE` — GitHub users to notify when human input is needed.
- `REPO` — the `owner/name` to manage.
- `TARGET_REPO_ROOT` — that repository's local clone when it is not this checkout.
- `ALLOWED_ISSUE_AUTHORS` — trusted users on a public repository.
- `DEV_AGENT`, `REVIEW_AGENT`, and `DECOMPOSE_AGENT` — only when changing the default agent routing.

Store the GitHub token outside the checkout at `~/.config/<owner>/<repo>/token`, or export `GITHUB_TOKEN` in the
launch environment. Tokens in `.env` are deliberately ignored. Ensure each configured agent is logged in, then run:

```sh
./run.sh
```

On first start, the orchestrator creates its labels and begins polling open issues. File a small issue to exercise the
workflow; a completed change stops at `in_review` for a human to merge.

The [configuration reference](docs/configuration.md) covers credentials, agent routing, every setting, and advanced
examples. The [operations guide](docs/configuration/operations.md) covers other run modes and systemd deployment.

## Asking the orchestrator a question

Apply the `question` label to an open issue for a read-only answer. The configured `DECOMPOSE_AGENT` replies on the
issue, keeps the same session for follow-up questions, and stops when the issue is closed.

See the [question-stage contract](docs/workflow/conversations.md#question-stage) and
[handler behavior](docs/state-machine/conversation-stages.md#_handle_question-label-question).

## Discussing an issue's architecture

Apply the `discussion` label to work through design choices before implementation. The decomposer presents options,
continues the conversation from your replies, and writes only `plans/issue-<number>.md` after you confirm the design.
The orchestrator then opens a plan pull request for a human to merge, reject, or route into implementation.

See the [discussion-stage contract](docs/workflow/conversations.md#discussion-stage) and
[handler behavior](docs/state-machine/conversation-stages.md#_handle_discussion-label-discussion).

## Holding and unsticking an issue

Use the control named by the orchestrator's park comment:

| Control | Purpose |
|---|---|
| `backlog` | Prevent pickup until the label is removed. |
| `paused` | Freeze an in-flight issue without discarding its state; remove the label to resume. |
| `/orchestrator continue` | Retry a recoverable stalled run or renew a spent daily retry budget when requested. |
| `/orchestrator authorize-oversized <commit>` | Allow the exact oversized commit named by the park to publish. |
| `/orchestrator add-review-rounds N` | Grant more reviewer rounds after the configured cap is reached. |
| `/orchestrator add-agent-runs N` | Raise the lifetime agent-run allowance for that issue. |

Commands are accepted only in the contexts and formats described by the park comment; ordinary guidance and control
commands are intentionally not interchangeable. See the [control-label reference](docs/configuration.md#control-labels)
and [delivery-stage behavior](docs/state-machine/delivery-stages.md) for trust checks, limits, recovery, and exact
effects.

## Observability

`logs/orchestrator.log` records process and issue activity, while `logs/analytics.jsonl` records transitions, timing,
agent outcomes, usage, and cost estimates. Optional surfaces add an audit log, a Postgres-backed analytics dashboard,
and a file-backed trajectory viewer without becoming part of workflow state.

![Analytics page](./pics/analytics_page.png)

See the [observability overview](docs/observability.md) for every surface and the
[dashboard quickstart](docs/configuration.md#analytics-dashboard-quickstart) for setup commands.

## Managing multiple repositories

Set `REPOS` to manage several repositories from one process. Worktrees and branches are namespaced by repository, and
per-repository plus global concurrency limits keep issues from colliding or overwhelming the host.

See the [`REPOS` syntax](docs/configuration.md#multi-repo-repos-syntax) and
[parallel-processing settings](docs/configuration.md#parallel-processing).

## Reference documentation

The [documentation index](docs/README.md) maps the complete reference set:

| Topic | Covers |
|---|---|
| [Architecture](docs/architecture.md) | Process model, agent model, push model, and module ownership |
| [State machine](docs/state-machine.md) | Labels, state, stage handlers, and lifecycle |
| [Workflow](docs/workflow.md) | Agent roles, conversation contracts, and command specs |
| [Configuration](docs/configuration.md) | Environment variables, defaults, and operator runbooks |
| [Observability](docs/observability.md) | Logs, analytics, dashboards, trajectories, usage, and cost |
| [Security](docs/security.md) | Deployment checklist and operator-owned controls |

Report suspected vulnerabilities through the private process in [SECURITY.md](SECURITY.md), never through a public
issue.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.

[ci-badge]: https://github.com/chippingway/orchestrator/actions/workflows/ci.yml/badge.svg
[ci-link]: https://github.com/chippingway/orchestrator/actions/workflows/ci.yml
[scorecard-badge]: https://api.scorecard.dev/projects/github.com/chippingway/orchestrator/badge
[scorecard-link]: https://scorecard.dev/viewer/?uri=github.com/chippingway/orchestrator
[best-practices-badge]: https://www.bestpractices.dev/projects/14235/badge
[best-practices-link]: https://www.bestpractices.dev/projects/14235
