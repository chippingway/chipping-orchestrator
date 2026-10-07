---
description: >-
  Reference documentation for chipping-orchestrator, which turns GitHub issues into reviewed pull requests with local
  coding agents, indexed by area.
---
# Documentation

This is the reference set for chipping-orchestrator, the layer under the project [README](../README.md). The README is
the operator's end-to-end guide — install, configure, run, and the labels you drive an issue with. The reference
explains why the system is shaped this way, which module owns what, what every setting does, and what each stage
handler reads and writes.

[![Ask ChatGPT][ask-chatgpt-badge]][ask-chatgpt]
[![Ask Claude][ask-claude-badge]][ask-claude]

## Where to start

| If you want to… | Read |
|---|---|
| install with pipx | the [quick start](../README.md#quick-start), then [basic setup](configuration.md#basic-setup) |
| run from source or launch developer analytics tools | the [developer guide](development.md) |
| understand the design before changing it | [`architecture.md`](architecture.md) |
| know what a label means, or when it moves | [`state-machine.md`](state-machine.md) |
| know which agent a stage spawns, under what prompt | [`workflow.md`](workflow.md) |
| find a setting, or apply an edited `.env` | [`configuration.md`](configuration.md) |
| run a second poller beside the first on one host | [running more than one poller][pollers] |
| see what the orchestrator did, and what it cost | [`observability.md`](observability.md) |
| trace release functionality and upgrade requirements | [`release-timeline.md`](release-timeline.md) |
| publish a release | [maintainer notes](../CONTRIBUTING.md#notes-for-maintainers) |
| harden the deployment | [`security.md`](security.md) |
| report a suspected vulnerability | [`../SECURITY.md`](../SECURITY.md) |
| report a bug, propose a change, or contribute a PR | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| change the code | [`../AGENTS.md`](../AGENTS.md), then the [`develop` skill](../.agents/skills/develop/SKILL.md) |
| size or split an issue | the [`decompose` skill](../.agents/skills/decompose/SKILL.md) |
| preview or publish this documentation | [publishing the documentation][publishing] |

## Every page

Grouped the way the site's navigation groups them.

- **Operate** — [settings](configuration.md), [operations](configuration/operations.md),
  [snapshot capability check](configuration/snapshot-capability-check.md), [security](security.md)
- **How it works**
    - Architecture — [overview](architecture.md), [platform modules](architecture/platform-modules.md),
      [workflow modules](architecture/workflow-modules.md),
      [observability modules](architecture/observability-modules.md)
    - State machine — [overview](state-machine.md), [labels and state](state-machine/labels-and-state.md),
      [delivery stages](state-machine/delivery-stages.md), [conversation stages](state-machine/conversation-stages.md),
      [lifecycle](state-machine/lifecycle.md)
    - Agents — [overview](workflow.md), [agent roles](workflow/roles.md), [conversations](workflow/conversations.md),
      [command specs](workflow/command-specs.md)
- **Observability** — [overview](observability.md), [settings](configuration/observability.md),
  [event streams](observability/event-streams.md), [trajectories](observability/trajectories.md),
  [analytics database](observability/analytics-database.md),
  [analytics dashboard](observability/analytics-dashboard.md), [usage parser](observability/usage.md)
- **Releases** — [release timeline](release-timeline.md)
- **Developers** — [source checkouts and tools](development.md)

[pollers]: configuration/operations.md#running-more-than-one-poller
[publishing]: configuration/operations.md#publishing-the-documentation

[ask-chatgpt-badge]:
  https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/.github/docs-theme/img/ask-chatgpt.svg
[ask-chatgpt]:
  https://chatgpt.com/?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C+I+want+to+ask+questions+about+it.&hints=search
[ask-claude-badge]:
  https://raw.githubusercontent.com/chippingway/chipping-orchestrator/main/.github/docs-theme/img/ask-claude.svg
[ask-claude]:
  https://claude.ai/new?q=Read+https%3A%2F%2Fchippingway.github.io%2Fchipping-orchestrator%2C+I+want+to+ask+questions+about+it.
