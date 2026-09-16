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

Delivery builders live in `workflow/engine/prompts.py`, question/discussion, PR-follow-up, and human-reply resume
builders in `workflow/engine/conversation_prompts.py`, and the decomposition builder in
`workflow/engine/decomposition_prompts.py`. Their use of the awareness block is:

- **Embedded** in `_build_implement_prompt`, `_build_documentation_prompt`, `_build_review_prompt`,
  `_build_decompose_prompt`, `_build_question_prompt`, `_build_discussion_prompt`, and
  `_build_fresh_respawn_preamble`. The fresh-respawn preamble matters because a transcript-less respawn (proactive
  `DEV_SESSION_MAX_RESUMES` rotation, the consecutive-silent-park fallback, poisoned-session recovery, or an operator
  `/orchestrator continue` command that drops a session-failure park's poisoned dev session before replaying the
  preserved PR-feedback batch) never saw the original spawn's block, so the re-grounding text must re-feed it
  alongside the issue body and conversation.
- **Omitted** from the bare resume / followup builders (`_build_fix_prompt`, `_build_conflict_resolution_prompt`,
  `_build_pr_comment_followup`, `_build_human_reply_followup`, `_build_question_followup_prompt`,
  `_build_discussion_followup_prompt`): those text
  payloads resume a live session that already received the block at spawn time, so repeating it would only burn
  tokens.

The default single-repo deployment (or any host with `EXPOSE_TRACKED_REPOS=off`) gets an empty string here — **zero
added prompt tokens and zero behavior change**. See
[`../configuration.md#agent-roles`](../configuration.md#agent-roles) for the env var.

## The developer report contract in developer prompts

Every prompt a developer can finish work on teaches one report contract, `_DEVELOPER_REPORT_NOTE` in
`workflow/engine/prompt_notes.py`. Its marker spellings come from `workflow/engine/report_outcome_models.py`, the
vocabulary `workflow/engine/report_outcomes.py` reads, so what a developer is told to write and what the reader accepts
cannot drift apart.

The contract settles who owns the report. The developer writes it: the complete, current report for the issue — what
the branch changes and why, how it was verified, and anything a reviewer should know — written whole every time,
because it supersedes every earlier one. Publishing it on the pull request is routine orchestrator work, so the
developer neither posts nor edits it and never asks a human whether or how to publish it. A report that needs no
repository change is delivered with no commit at all: an empty commit, or any change made only to carry a report, is
never asked for. Finished work ends on exactly one of two outcomes, outside any code fence and with nothing after it:

- **Report ready for publication** — the complete report between a `REPORT: READY` line and a `REPORT: END` line.
- **Report already on the pull request** — a single `REPORT: VERIFIED <location> <revision>` line, for a complete,
  current report the developer read on the issue's pull request during the run, such as one a human posted or edited.
  `<location>` is `https://github.com/<owner>/<repo>/pull/<number>` for the description, or that URL followed by
  `#issuecomment-<id>` for a comment on it, and `<revision>` is `sha256:` followed by the 64 lowercase hex digits of
  that text as GitHub returns it.

No other line may open on `REPORT:`, and an outcome never shares a message with an `ACK:` line, which stays the one
finished reply without a report on the prompts that offer it. A question, a disagreement, or work that could not
finish ends on the question with neither outcome.

Where the contract is carried:

- **Whole** in the initial `_build_implement_prompt`, the automated-review `_build_fix_prompt`, the requirements-drift
  `_build_user_content_change_prompt`, the PR-feedback `_build_pr_comment_followup`, the human-reply resume
  `_build_human_reply_followup` (`_resume_developer_on_human_reply`), the late revision's `_revision_prompt`
  (`decomposition/late_revision.py`), which resumes the developer against a human's guidance on an oversized
  candidate, and `_DEVELOPER_CONTINUE_RETRY_PROMPT`, the retry a bare `/orchestrator continue` on a session-failure
  park resumes the developer on (`implementing/continue_command.py`, `validating/awaiting.py`). The resumes carry it
  whole because the transcript they continue may predate the contract or hold another stage's prompt. The fix and
  PR-feedback prompts have an item that asks only for report content answered in the report, with no commit for it;
  the PR-feedback prompt sends a developer whose comments say a human published or updated the report to read it
  there and, when it is complete and current, end on `REPORT: VERIFIED`; and the drift, late-revision, and
  PR-feedback prompts keep `ACK:` for a reply after which neither the branch nor the report has to change.
- **Deferred** in `_build_fresh_respawn_preamble`, which carries `_RESPAWN_REPORT_NOTE` instead: the report covers the
  whole branch, the previous session's commits included, ownership and publication are restated, and the outcome is
  the one the task below the preamble describes — that preamble also precedes tasks that close on markers of their
  own.
- **Absent** from the documentation, review, and conflict-resolution prompts, which close on markers of their own, and
  from the conflict stage's own reply resume and bare-continue retry, which stays on the plain
  `_CONTINUE_RETRY_PROMPT`.

`report_outcomes._report_outcome_of_run` reads an outcome only out of a run that completed: a run never invoked,
interrupted, timed out, refused by its provider, or exited nonzero is refused before its message is read. On a
completed run's message, `_parse_report_outcome` answers `NO_MARKER` for a reply that never used the contract — a
question, a disagreement, an `ACK:`, no-change prose — and `MALFORMED` for one that reached for it and missed: an
unclosed or empty block, text after the outcome, a location or revision out of shape, a stray or second marker line,
an `ACK:` beside it, or a marker line that may render as code. That last reading is made without a Markdown parser, so
a doubt reads as code: a marker line four columns in or behind a tab, or on a line a code fence may enclose, whether
that fence opened at the top level or in a list item (`workflow/engine/report_fences.py`). A `REPORT: VERIFIED`
location and revision are parsed for shape only; completing on one is owed a fresh read of that location whose text
still hashes to the revision.

No stage handler calls `report_outcomes`, records a report transaction, or publishes a report through the
developer-report comment owners (`github/developer_reports.py`, `github/pull_request_reports.py`, and
`workflow/engine/comments.py`'s `_publish_developer_report`). A developer run is still routed by its commits, its
`ACK:` line, and the question parks the [delivery stages][delivery-stages] describe: nothing publishes the report an
outcome carries, and a no-commit reply that ends on a report outcome is read the way its stage reads any other
no-commit reply without `ACK:`.

The durable half of that publication is defined and dormant beside the vocabulary. The additive
`developer_report_pending` / `developer_report_current` / `developer_report_handoff` group
([`../state-machine/labels-and-state.md#pinned-state`](../state-machine/labels-and-state.md#pinned-state)) is what
would carry one outstanding publication across a process that dies mid-way — the complete report text included,
since a transaction recovered from a text nobody kept would have to ask an agent to write it again, and a second
run is not the same report. Its owners read those records fail-closed and refuse to write one a later tick could
not read back; no stage produces one and no dispatcher consumes one, so nothing records, reads, or settles a
transaction yet.

What a settlement would have to PROVE first is dormant beside those records. `workflow/engine/report_evidence.py`
takes one reading of the world per outstanding transaction — over the checkout, remote, and pull-request owners
under it — and answers with one of four verdicts rather than a boolean
(`workflow/engine/report_evidence_models.py`). PROVED alone licenses a publication, and it is the only verdict that
carries anything: the pull request it was proved against travels on it, so a publication is made in the world it was
read in rather than in a second one a re-fetch would see. HOLD is a reading nobody could take — a pull request
GitHub would not serve, a `git status` that failed — and stops the tick so the next one asks again. DEFER is
everything structural: an absent or dirty checkout, a branch ahead of or behind its remote, a head that moved, a
commit no publication receipt names yet, requirements somebody edited. Each of those is cleared by a route *behind*
the evidence — the publication gate that pushes, the drift resume that answers the edit, the dirty-worktree park —
so holding one would strand the issue in front of its own remedy. ENDED is a pull request that has merged or
closed, which needs no report at all.

PROVED requires all of it on the tick that would settle: the recorded pull request open, in this repository, on the
recorded branch, and *standing on* the recorded commit rather than merely carrying it; a readable, clean checkout on
that same commit; a freshly fetched remote branch in sync on it; a code-publication receipt
(`implementing_published_sha` with `implementing_published_pr`) naming both that commit and that pull request; and
issue requirements still hashing to the revision the run was handed. The pull request is read by the NUMBER the
record froze rather than searched for by commit, since several pull requests can stand on one branch carrying one
commit and a search would answer with whichever it reached first. It is also read *ahead* of the local world, which
is an ordering rule rather than a cost preference: a merge auto-deletes its branch, so a fetch or checkout that
failed first would hide the ending behind a hold and keep the issue in front of the terminal that drains it.
Nothing calls either entry point yet.

[question-handler]: ../state-machine/conversation-stages.md#_handle_question-label-question
[discussion-handler]: ../state-machine/conversation-stages.md#_handle_discussion-label-discussion
[delivery-stages]: ../state-machine/delivery-stages.md
