---
description: >-
  The agent role each stage spawns, what its prompt grants and forbids, and how the DEV_AGENT, REVIEW_AGENT, and
  DECOMPOSE_AGENT specs are parsed and pinned.
---
# Agents — roles and command specs

This area documents who runs an issue: which stage invokes which agent role, what that role's prompt grants and
forbids, how the role command specs (`DEV_AGENT` / `REVIEW_AGENT` / `DECOMPOSE_AGENT`) are parsed, and how the spec an
in-flight issue runs under is pinned for the life of its session. Label semantics, transitions, and per-handler
behavior belong to [`state-machine.md`](state-machine.md).

## The pages in this area

- [Agent roles and sessions](workflow/roles.md) defines role permissions, session lifecycles, size-gate adjudication,
  and late-split decisions.
- [Conversations and prompt contracts](workflow/conversations.md) defines question and discussion prompts, repository
  awareness, commit subjects, developer reports, reviewer evidence, and foreground execution.
- [Command specs](workflow/command-specs.md) defines backend selection, CLI arguments, examples, and session pins.

The summaries below retain the section addresses used by existing links.

## Roles at a glance

- **Decomposer** — `DECOMPOSE_AGENT` (default `claude`), used for initial decomposition, late adjudication, question,
  and discussion, each with its own session pin per issue.
- **Implementer / dev** — `DEV_AGENT` (default `claude`), spawned by implementing and resumed by documenting,
  validating, fixing, and conflicts; locked per issue after the first spawn.
- **Reviewer** — `REVIEW_AGENT` (default `codex`), spawned fresh by validating every round, so the current config
  always wins, and handed the developer report the pull request carries, quoted whole in its prompt.

The defaults (`claude` decomposes, `claude` implements, `codex` reviews) require those two CLIs; both need to be
authenticated on the host before the orchestrator starts. Per-role detail:
[`workflow/roles.md`](workflow/roles.md#the-three-roles).

## Question stage — read-only Q&A on the `question` label

The operator-applied `question` label runs the decomposer as a read-only Q&A agent with its own pinned conversation.
Answers go to the issue thread; it creates no pull request. The
[question prompt](workflow/conversations.md#question-stage)
defines the conversation contract, and the [question handler][question-handler] defines parks and cleanup.

## Discussion stage — architecture discussion on the `discussion` label

The operator-applied `discussion` label explores a design through numbered questions. Human confirmation permits a
commit of the plan file alone, which the orchestrator publishes for human review. The
[discussion prompt](workflow/conversations.md#discussion-stage) defines that permission; the
[discussion handler][discussion-handler] owns publication and terminal behavior.

## Tracked-repos awareness in working-agent prompts

With multiple repositories and `EXPOSE_TRACKED_REPOS` enabled, working-agent prompts name the other tracked checkouts
without widening the stage's permissions. The [awareness contract][tracked-repos] defines the block and its consumers;
the [disclosure analysis][disclosure] explains what it reveals.

## Commit-subject contract in commit-producing prompts

Commit-producing prompts ask agents to follow the target repository's recent style with one short imperative subject
and no body or trailer. The orchestrator owns the published pull request suffix. The
[commit-subject contract][commit-subject] defines prompt coverage and conflict-resolution exceptions.

## Developer report contract in developer prompts

Developers finish with a complete report of the final branch state, or verify a report already on the pull request.
The orchestrator records and publishes it before review, binding it to the code and requirements it describes. The
[report contract][report-contract] owns the output syntax and writing scope; the
[report lifecycle](workflow/conversations.md#the-developer-report-lifecycle) connects delivery, recovery, and freshness.

## Reviewer verification contract in reviewer prompts

A reviewer receives the current developer report and verification evidence for its exact subject, then declares the
commands it ran or the evidence revision it reused. Approval needs settled, passing evidence; change requests carry
reproducible findings. The [reviewer contract][reviewer-verification] defines both declarations and finding entries.

## Foreground execution and asynchronous command guidance

Commit-producing prompts require commands to finish within the current agent response. Background jobs end with the
agent process, so asynchronous tools must be waited on before returning. The
[foreground-execution contract][foreground-guidance] defines prompt coverage and supported wait/status behavior.

## Examples

Role values combine a backend with optional CLI arguments. The same grammar applies to all three role variables;
[command-spec examples](workflow/command-specs.md#examples) cover model selection, effort, and quoting.

## In-flight session lock — pinned full spec until the session ends

Each conversation pins its full backend and arguments when it starts, so configuration edits do not change a resumed
session. Developer, decomposer, question, discussion, and late-adjudication pins are independent; reviewers start fresh
with current configuration every round. The [session-lock reference][session-lock] owns the keys and legacy reads;
[session lifecycles](workflow/roles.md#session-lifecycles) covers replacement of retired developer conversations.

[commit-subject]: workflow/conversations.md#the-commit-subject-contract-in-commit-producing-prompts
[tracked-repos]: workflow/conversations.md#tracked-repository-awareness-in-working-agent-prompts
[disclosure]: security.md#cross-repo-awareness-disclosure-expose_tracked_repos
[session-lock]: workflow/command-specs.md#in-flight-session-lock
[question-handler]: state-machine/conversation-stages.md#_handle_question-label-question
[discussion-handler]: state-machine/conversation-stages.md#_handle_discussion-label-discussion
[foreground-guidance]: workflow/conversations.md#foreground-execution-and-asynchronous-command-guidance
[reviewer-verification]: workflow/conversations.md#the-reviewer-verification-contract
[report-contract]: workflow/conversations.md#the-developer-report-contract-in-developer-prompts
