# chipping-orchestrator

**Autonomous GitHub issue → reviewed PR pipeline for Claude Code, Codex CLI, and Antigravity CLI.**

[![CI][ci-badge]][ci-link]
[![OpenSSF Scorecard][scorecard-badge]][scorecard-link]
[![OpenSSF Best Practices][best-practices-badge]][best-practices-link]

`chipping-orchestrator` turns GitHub issues into reviewed pull requests with local coding-agent CLIs (`codex`,
`claude`, or `agy`). It plans the work, implements it in an isolated git worktree, reviews the result, and asks a
human to make the final merge decision.

Workflow state lives on the issue itself, so progress stays visible on GitHub and survives process restarts without a
separate queue or workflow database.

[![Ask ChatGPT][ask-chatgpt-badge]][ask-chatgpt]
[![Ask Claude][ask-claude-badge]][ask-claude]

## When to use it

- **Use it when:** you work solo or on a small team, have an authenticated `codex`, `claude`, or `agy` CLI, and want
  issue-to-PR autonomy without running a separate planner, queue, or workflow database. You decide what to merge.
- **Don't use it when:** you need a hosted service or automatic merges, cannot let agents run with the host account as
  their security boundary, or need issue trackers other than GitHub.

## How it works

An issue normally follows this path:

```text
workflow:decomposing → workflow:ready → workflow:implementing
  → workflow:validating → workflow:documenting → in_review
  → done or rejected
```

The decomposer can split large work into child issues. The implementer commits in a dedicated worktree, the reviewer
requests fixes until the change is ready, and the orchestrator opens or updates the pull request. The reviewer declares
the verification its verdict relies on, which the orchestrator publishes on the pull request before acting on it; an
approval without passing evidence covering every configured `VERIFY_COMMANDS` command waits for a human. A final docs
pass that commits documentation changes sends the pull request back to `workflow:validating`, where the developer
reports on the new head and a fresh reviewer verifies it before another docs pass. One that changes nothing hands the
pull request on only while the approval's verification evidence still proves current behind it; evidence that no
longer does is invalidated, and the pull request goes back for a fresh review. In `in_review` a human is told the pull
request is ready only over current passing evidence proved again at that moment. Oversized changes, conflicts,
retries, and human decisions take explicit side paths; pull requests are never merged automatically.

See the [state-machine overview][states] for labels and transitions, and the
[workflow guide][workflow] for agent roles and session behavior.

## Requirements

- Linux, Git, and Python 3.12 or newer. CI tests Python 3.12, 3.13, and 3.14; newer versions are not tested.
- [pipx](https://pipx.pypa.io/stable/how-to/install-pipx.html) 1.16.0 or newer with a Python 3.12 or newer interpreter.
- An authenticated CLI for every configured role. Defaults are
  [`claude`](https://docs.anthropic.com/en/docs/claude-code) for decomposition and implementation, and
  [`codex`](https://github.com/openai/codex) for review. Any role can instead use
  [Antigravity (`agy`)](https://antigravity.google/docs/cli/headless/).
- A GitHub repository and a fine-grained personal access token with read/write access to Contents, Issues, and Pull
  requests, plus read-only access to Metadata.

Agents run with their approval and sandbox checks disabled, so the host account is the security boundary. Read the
[security checklist][security] before using the orchestrator on a public or untrusted repository.

## Quick start

Install the published package from PyPI:

```sh
pipx install chipping-orchestrator
pipx ensurepath
```

Open a new terminal after `pipx ensurepath` if the command is not yet on `PATH`. If pipx selects an older Python,
use `pipx install --python python3.12 chipping-orchestrator` with an installed supported interpreter.

The quick start resolves runtime dependencies from PyPI without `poetry.lock`, tested constraints, or a 14-day hold;
use the [pinned installation procedure][pinned-installation] for the release's tested dependency versions.

Log in each agent CLI the roles use, then, from the top of a local clone of the repository to manage and in a shell
whose `PATH` finds those CLIs, set the orchestrator up as a systemd user service, start it, and look at it:

```sh
chipping-orchestrator init
chipping-orchestrator start
chipping-orchestrator status
```

With no configuration yet, `init` first asks for it at the terminal, one question per setting, each default in
brackets for Enter to take:

- the local clone, the current directory by default, and the repository and branch pull requests target, read off the
  clone's GitHub remote;
- the repository's GitHub token, typed at a hidden prompt that offers an exported `GITHUB_TOKEN`, and checked with one
  read-only GitHub call; a token already stored for the repository is kept without asking;
- the GitHub logins whose issues and comments the orchestrator acts on, the token owner's by default, and those to
  mention when a human is needed, the same by default;
- the agent each role runs, shown with whether it is on `PATH`, and any further repository.

A refused answer is asked again with the reason. Nothing is written until the last question confirms the files it
names, so Ctrl+C leaves the host as it was. Then `init` saves each token to `~/.config/<owner>/<name>/token`, writes
`~/.config/chipping-orchestrator/.env`, [checks the setup][checking] the way the service will read it, GitHub calls
included, and installs and enables `~/.config/systemd/user/chipping-orchestrator.service` for this installation's
interpreter and the shell's `PATH`, with linger where logind allows it, without starting the service. The
orchestrator's own repository does not need to be cloned.

`start` checks the settings locally once more, without asking GitHub, then starts the service and confirms it stays
active, printing its last journal lines if it does not. `status` prints the installed version, the `.env` and the
unit, then `systemctl --user status`: run it after a start, a reboot, or an edit to see whether the poller is running,
and follow its output with `journalctl --user-unit chipping-orchestrator.service -f`. `stop`, `restart`, and `remove`
manage it from there, `remove` deleting the unit and keeping the setup. Run `init` again when the agents move to other
directories: with `.env` in place it asks nothing and rewrites only the unit. The [user service guide][user-service]
covers the unit, linger, each command, and replacing a hand-written `orchestrator.service`.

The same setup runs without prompts, as a script or a host without a terminal needs: there, `init` refuses a missing
`.env` and names these commands.

```sh
chipping-orchestrator set-token acme/api < "$HOME/acme-api-token.txt"
chipping-orchestrator configure --clone /home/alice/src/acme-api --authors alice
chipping-orchestrator init
```

`set-token` reads the token from standard input, at a hidden prompt on a terminal, checks it reaches the repository,
and writes its token file owner-only; `configure` writes `.env` for the repository a local clone names, trusting the
GitHub logins given as authors, and the [package setup instructions][installation] cover its other options. Tokens in
`.env` are deliberately ignored, and the token is never a command-line argument.

Either way, `.env` sets these; edit it to change any of them, then `chipping-orchestrator restart`:

- `REPOS` — the repository to manage, written `owner/name|target_root|base_branch`: its GitHub `owner/name`, the
  absolute path to an existing local clone of it, and the branch its pull requests target. For example:

  ```dotenv
  REPOS=acme/api|/home/alice/src/acme-api|main
  ```

  The template explains the two optional trailing fields; [several repositories][multiple-repos] are
  more entries in the same setting, which onboarding's further repositories and `add-repo` add.
- `HITL_HANDLE` — GitHub users to notify when human input is needed: the people to mention, else the authors.
- `ALLOWED_ISSUE_AUTHORS` — required: the GitHub logins whose issues and comments the orchestrator acts on; it refuses
  to start while this names nobody.
- `DEV_AGENT`, `REVIEW_AGENT`, and `DECOMPOSE_AGENT` — the agent each role runs: `claude`, `codex`, and `claude`
  unless onboarding or `--dev-agent`, `--review-agent`, or `--decompose-agent` says otherwise.
- `LOG_DIR` — an absolute directory outside the pipx environment, so logs survive package upgrades.

Nothing from `.env.example.advanced` is needed: it holds optional operational settings and, in a section of their own,
the developer settings for working on the orchestrator itself.

To run the poller in the foreground instead of as a service, check the setup and run it:

```sh
chipping-orchestrator check
chipping-orchestrator run
```

A foreground `run` also accepts one `GITHUB_TOKEN` exported in its launch environment in place of the token files, for
every repository. `check` ignores that export, since a service is not started from that shell, and reports each
repository without a token file as a problem, so store the tokens with `set-token` for any setup a service will run.

On first start, the orchestrator creates its labels and begins polling open issues. Each issue gets its own worktree
under `wt-orchestrator`, beside the first repository's clone. File a small issue to exercise the workflow; a completed
change stops at `in_review` for a human to merge.

The [configuration reference][configuration] covers credentials, agent routing, every setting, and advanced
examples. The [operations guide][operations] covers run modes, upgrades and rollback, running more than one poller
on one host, and systemd deployment. For unconstrained, unpinned installs, use `pipx upgrade chipping-orchestrator`
after stopping the poller and reviewing release notes. Constrained installs upgrade by repeating the pinned
procedure in the operations guide with the new release's constraints. Package upgrades are operator-initiated.
Upgrading to v0.14.0 from v0.13.0 or earlier moves the poller to `chipping-orchestrator run`: the bare command prints
help and exits. Read the [v0.14.0 release and upgrade notes][release-0.14.0] and the
[package upgrade procedure][installation] before upgrading a host whose scripts or systemd unit run it.
A release or source revision that cannot read the work the running poller owns is
[deployed without migration][deploying]: stop and hold every poller, keep what the new build cannot read away from it
and in place for a human to decide on, then install, check, and start it deliberately. Nothing converts earlier
workflow state, and breaking changes reach `main` as they merge, not first at a release tag.

## Asking the orchestrator a question

Apply the `question` label to an open issue for a read-only answer. The configured `DECOMPOSE_AGENT` replies on the
issue, keeps the same session for follow-up questions, and stops when the issue is closed.

See the [question-stage contract][question-contract] and
[handler behavior][question-handler].

## Discussing an issue's architecture

Apply the `discussion` label to work through design choices before implementation. The decomposer presents options,
continues the conversation from your replies, and writes only `plans/issue-<number>.md` after you confirm the design.
The orchestrator then opens a plan pull request for a human to merge, reject, or route into implementation.

See the [discussion-stage contract][discussion-contract] and
[handler behavior][discussion-handler].

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
commands are intentionally not interchangeable. See the [control-label reference][controls]
and [delivery-stage behavior][delivery] for trust checks, limits, recovery, and exact
effects.

## Observability

`orchestrator.log` records process and issue activity, while `analytics.jsonl` records transitions, timing, agent
outcomes, usage, and cost estimates. Both live under `LOG_DIR`, set to `~/.local/state/chipping-orchestrator/logs`
by [package setup][installation]. An explicit `ANALYTICS_LOG_PATH` can place analytics elsewhere. Optional surfaces
add an audit log, a Postgres-backed analytics dashboard, and a file-backed trajectory viewer without becoming part
of workflow state. The dashboards are source-checkout developer tools; their dependencies and launch commands are
in the [developer guide][development].

![Analytics page with spend and token usage over time categorized by different dimensions][analytics-image]

See the [observability overview][observability] for every surface.

## Managing multiple repositories

One process manages several repositories. To add one to an installed setup, store its token, add its entry, and
restart the service so it reads the new entry:

```sh
chipping-orchestrator set-token acme/web
chipping-orchestrator add-repo --clone /home/alice/src/acme-web
chipping-orchestrator restart
```

`add-repo` reads the repository, the remote that points at it, and the branch pull requests target off the clone, the
way `configure` does, and adds the entry to the end of the `REPOS` line in `~/.config/chipping-orchestrator/.env`,
keeping every other line as it was. `--repo`, `--base-branch`, and `--remote` replace what it reads, and
`--parallel N` lets N of the repository's issues run at once. It refuses a missing `.env` and a repository `REPOS`
already lists, and says to `restart` when the service is running, since a service reads `REPOS` only as it starts.
`restart` checks the setup locally first, a token for the new entry included, and leaves the service running as it
was if that check finds a problem. [Adding a repository][adding-repo] covers every option and refusal.

`REPOS` itself carries one entry per repository, separated by `;` since `.env` holds each value on a single line, and
can still be edited by hand. Edit the first `REPOS` line rather than adding another: `.env` keeps the first value it
reads for a setting.

```dotenv
REPOS=acme/api|/home/alice/src/acme-api|main;acme/web|/home/alice/src/acme-web|master|upstream|2
```

Every entry names its own local clone and reads its own token file, `~/.config/<owner>/<name>/token`, which
`chipping-orchestrator set-token <owner>/<name>` writes, unless one exported `GITHUB_TOKEN` covers them all for a
foreground run. The optional fourth and fifth fields set the git remote that points at the repository (`origin` by
default) and how many of its issues run at once; they are positional, so setting the limit means writing the remote too.
Worktrees and branches are namespaced by repository, and per-repository plus global concurrency limits keep issues from
colliding or overwhelming the host.

See the [`REPOS` syntax][repos] and
[parallel-processing settings][parallel].

## Reference documentation

Browse the [documentation website](https://chippingway.github.io/chipping-orchestrator/) or the
[documentation index][documentation] for the complete reference set:

| Topic | Covers |
|---|---|
| [Architecture][architecture] | Process model, agent model, push model, and module ownership |
| [State machine][states] | Labels, state, stage handlers, and lifecycle |
| [Agents][workflow] | Agent roles, conversation contracts, and command specs |
| [Configuration][configuration] | Environment variables, defaults, and operator runbooks |
| [Observability][observability] | Logs, analytics, dashboards, trajectories, usage, and cost |
| [Security][security] | Deployment checklist and operator-owned controls |
| [Release timeline][releases] | Published milestones, release notes, and upgrade guidance |

Report suspected vulnerabilities through the private process in [SECURITY.md][reporting], never through a public
issue.

## Contributing

See [CONTRIBUTING.md][contributing] for writing issues, setting up a development checkout, running checks, and
submitting pull requests. Source-checkout installation, direct Python launches, and the development wrapper are
documented in the [developer guide][development].

## License

Licensed under the Apache License, Version 2.0. See [LICENSE][license] for the full text.

[ci-badge]: https://github.com/chippingway/chipping-orchestrator/actions/workflows/ci.yml/badge.svg
[ci-link]: https://github.com/chippingway/chipping-orchestrator/actions/workflows/ci.yml
[scorecard-badge]: https://api.scorecard.dev/projects/github.com/chippingway/chipping-orchestrator/badge
[scorecard-link]: https://scorecard.dev/viewer/?uri=github.com/chippingway/chipping-orchestrator
[best-practices-badge]: https://www.bestpractices.dev/projects/14235/badge
[best-practices-link]: https://www.bestpractices.dev/projects/14235

[ask-chatgpt-badge]:
  https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/.github/docs-theme/img/ask-chatgpt.svg
[ask-chatgpt]:
  https://chatgpt.com/?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C+I+want+to+ask+questions+about+it.&hints=search
[ask-claude-badge]:
  https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/.github/docs-theme/img/ask-claude.svg
[ask-claude]:
  https://claude.ai/new?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C+I+want+to+ask+questions+about+it.

[states]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/state-machine.md
[workflow]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/workflow.md
[security]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/security.md
[configuration]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md
[installation]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#package-installation-upgrades-and-rollback
[deploying]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#deploying-without-migration
[pinned-installation]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration/operations.md#pin-a-release-and-runtime-dependencies
[operations]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#run-modes
[question-contract]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/workflow/conversations.md#question-stage
[question-handler]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/state-machine/conversation-stages.md#_handle_question-label-question
[discussion-contract]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/workflow/conversations.md#discussion-stage
[discussion-handler]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/state-machine/conversation-stages.md#_handle_discussion-label-discussion
[controls]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#control-labels
[delivery]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/state-machine/delivery-stages.md
[observability]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/observability.md
[development]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/development.md
[repos]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#repos-syntax
[adding-repo]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#adding-a-repository-with-add-repo
[checking]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#checking-a-setup
[user-service]:
 https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#running-under-systemd-user-service
[multiple-repos]:
  https://github.com/chippingway/chipping-orchestrator/blob/main/README.md#managing-multiple-repositories
[parallel]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/configuration.md#parallel-processing
[documentation]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/README.md
[architecture]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/architecture.md
[releases]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/release-timeline.md
[release-0.14.0]: https://github.com/chippingway/chipping-orchestrator/blob/main/docs/release-timeline.md#v0140
[reporting]: https://github.com/chippingway/chipping-orchestrator/blob/main/SECURITY.md
[contributing]: https://github.com/chippingway/chipping-orchestrator/blob/main/CONTRIBUTING.md
[license]: https://github.com/chippingway/chipping-orchestrator/blob/main/LICENSE
[analytics-image]: https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/pics/analytics_page.png
