# Conversation stages and prompt contracts

`question` and `discussion` are the two operator-applied workflow labels: nothing routes an issue into either, and
neither has an agent role of its own — both reuse the decomposer's configured backend, because a question is the
decomposer answering without implementing and a discussion is the decomposer reasoning about a design before anything
is decomposed. Each conversation pins its own agent + session keys, so its backend, args, and session id are locked
independently of any other conversation on the same issue (see
[`roles.md#session-lifecycles`](roles.md#session-lifecycles) and
[`command-specs.md#in-flight-session-lock`](command-specs.md#in-flight-session-lock)).

Label transitions, park reasons, the checks a round's branch is read by, publication and crash recovery, and terminal
cleanup are the state machine's — [`_handle_question`][question-handler] and
[`_handle_discussion`][discussion-handler]. What follows is what each prompt
grants and forbids, where the agent is invoked, and how its session is continued.

## Question stage

`_handle_question` runs the configured `DECOMPOSE_AGENT` backend in the issue's per-issue worktree (recreated from
`<remote>/<base>` each spawn) with a read-only prompt that forbids modifying, committing, or pushing files. The
agent's answer (or its own clarifying follow-up question) is posted as a comment pinging `HITL_HANDLE`; no PR is ever
opened and no branch is ever pushed. Subsequent human replies resume the locked session
(`_build_question_followup_prompt`), so a multi-turn Q&A keeps the same backend + args.

Violating that contract — commits, a dirty tree, a run that timed out — ends the round awaiting a human with the
worktree kept for inspection rather than torn down. Closing the issue is the terminal signal. The park reason each
outcome writes, and the guard a relabel to `workflow:implementing` has to pass, are in
[`../state-machine/conversation-stages.md#_handle_question-label-question`][question-handler].

## Discussion stage

`_handle_discussion` runs the decomposer once per round in the issue's per-issue worktree (`issue-N`, on the issue's
own branch) with a prompt that tells it to research the repository itself, explore the design as a tree rather than a
single answer, raise architecture decisions, unconventional alternatives, and worthwhile research rather than
implementation trivia, and close with a NUMBERED list of the questions answerable right now — each with the agent's
own recommended answer — so a human can agree or overrule by number. Nothing is written, and nothing is implemented,
until a human states on the thread that they and the agent understand the design the same way.

Where the two stages part is what a round may leave behind. `question` is read-only for its whole life — a commit or a
dirty tree is a violation — it opens no PR, and it tears its worktree down on every safe exit. A discussion is
read-only only up to the confirmation: after it the agent may commit exactly one file, the orchestrator publishes that
file as a pull request, and the `issue-N` checkout is preserved on every round exit instead, since the conversation
keeps running on it. The verdict the humans leave on that pull request is what ends the issue.

Answering by number resumes the pinned session for another round. Only issue comments past the consumed
`last_action_comment_id` that are neither from an untrusted author nor the orchestrator's own count as an answer, so
an empty or all-untrusted batch is a no-op that writes nothing and leaves the reply for the tick after the allowlist
changes. The resume quotes those replies to the live session (`_build_discussion_followup_prompt`) and asks for the
tree redrawn around what they settled and the frontier recomputed. A round with no `discussion_session_id` to resume
gets the full prompt instead, since it reaches a fresh agent that would otherwise arrive with no design to fold an
answer into; that rebuilt context keeps the orchestrator's own posted analyses even when `ALLOWED_ISSUE_AUTHORS` does
not list the bot's account, so the fresh agent reads the human's answers together with the numbered questions they
answer.

`discussion_agent` is written before the spawn, so the conversation's identity survives a CLI that hands back nothing
and a replayed round stays on the backend that opened it rather than on whatever `DECOMPOSE_AGENT` says now; the run
itself is recorded under `agent_role="decomposer"` with `stage="discussion"`. The `issue-N` worktree is reused rather
than rebuilt across the whole conversation, the clean response is posted as a comment pinging `HITL_HANDLE`, and the
issue then waits for a human — a round on the thread is the humans' turn, and costs one comment read per tick until
somebody answers. No developer or reviewer is ever spawned by this stage.

### The plan file the confirmation earns

Both prompts also carry the one write the confirmation unlocks: `plans/issue-<number>.md`, holding the resolved
decisions, the evidence and research behind them, the alternatives and why they lost, the risks, and the
implementation plan — committed alone, with no push and no PR of the agent's own. The path is spelled by the stage's
own key owner and handed to the prompt builders, so what the agent is told and what the check looks for cannot drift.

Publishing it is the orchestrator's job, not the agent's, and it is not taken on trust: no orchestrator can verify
that a human agreed to anything, so a round that moved HEAD has its branch read and has to prove that what it commits
is the plan file and nothing else before the stage pushes it and opens the pull request. Which probes read that
branch, what each failure parks as, and how a tick that died mid-publication recovers are in
[`../state-machine/conversation-stages.md#_handle_discussion-label-discussion`][discussion-handler].

The plan is an artifact, not a specification anything downstream reads. Nothing in the workflow parses it: the relabel
to `workflow:implementing` spawns the developer with the ordinary `_build_implement_prompt` built from the issue body
and the trusted thread, on the branch the plan PR is open against, and the final-docs pass that follows is told not to
inspect or modify the `plans/` tree at all. So the plan file rides along on the branch and lands with the
implementation as the human-readable record of what was agreed — the issue is still what the developer is briefed from
and judged against.

## Tracked-repository awareness in working-agent prompts

When the orchestrator drives more than one repo (`REPOS`) and `EXPOSE_TRACKED_REPOS` is on (the default), the
reasoning-prompt builders prepend a compact, read-only awareness block naming the *other* repos this process tracks.
It lets an agent implementing an issue in one repo know that a sibling repo is also monitored and where its source is
checked out locally. The block is built once by `_build_tracked_repos_context(current, specs)` in
`workflow/engine/prompt_context.py` from `config.default_repo_specs()` — no GitHub round-trip, no pinned state, no new
config surface.

Shape of the block:

- One line per *other* repo (`- owner/name — source at <target_root> (base <base>)`), excluding the current repo, with
  a closing `Your task is on owner/name.` marker. The list is capped at 20 entries with an `… and N more` overflow
  line so a host driving dozens of repos cannot blow the prompt.
- Only the durable `target_root` checkout is exposed — never the ephemeral per-issue `issue-N` worktrees. No tokens,
  no remote URLs — see [`../security.md`](../security.md#cross-repo-awareness-disclosure-expose_tracked_repos) for the
  full disclosure analysis.
- The framing is deliberately **stage-neutral**: it says only that the sibling checkouts are read-only references and
  explicitly defers the question of whether the agent may write in its *own* working directory to the surrounding
  stage prompt. So the same block is safe in the write-granting prompts (implementer / documentation), in the
  read-only ones (reviewer / decomposer / question), and in the discussion prompts, whose single write a human's
  confirmation unlocks — none of them widens what the surrounding prompt granted.

Delivery builders live in `workflow/engine/prompts.py`, question/discussion and PR-follow-up builders in
`workflow/engine/conversation_prompts.py`, and the decomposition builder in
`workflow/engine/decomposition_prompts.py`. Their use of the awareness block is:

- **Embedded** in `_build_implement_prompt`, `_build_documentation_prompt`, `_build_review_prompt`,
  `_build_decompose_prompt`, `_build_question_prompt`, `_build_discussion_prompt`, and
  `_build_fresh_respawn_preamble`. The fresh-respawn preamble matters because a transcript-less respawn (proactive
  `DEV_SESSION_MAX_RESUMES` rotation, the consecutive-silent-park fallback, poisoned-session recovery, or an operator
  `/orchestrator continue` command that drops a session-failure park's poisoned dev session before replaying the
  preserved PR-feedback batch) never saw the original spawn's block, so the re-grounding text must re-feed it
  alongside the issue body and conversation.
- **Omitted** from the bare resume / followup builders (`_build_fix_prompt`, `_build_conflict_resolution_prompt`,
  `_build_pr_comment_followup`, `_build_question_followup_prompt`, `_build_discussion_followup_prompt`): those text
  payloads resume a live session that already received the block at spawn time, so repeating it would only burn
  tokens.

The default single-repo deployment (or any host with `EXPOSE_TRACKED_REPOS=off`) gets an empty string here — **zero
added prompt tokens and zero behavior change**. See
[`../configuration.md#agent-roles`](../configuration.md#agent-roles) for the env var.

[question-handler]: ../state-machine/conversation-stages.md#_handle_question-label-question
[discussion-handler]: ../state-machine/conversation-stages.md#_handle_discussion-label-discussion
