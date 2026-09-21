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

## The commit-subject contract in commit-producing prompts

Every prompt whose agent may author a commit subject carries one subject contract, `_COMMIT_STYLE_NOTE` in
`workflow/engine/prompt_notes.py`. It enumerates no prefix vocabulary of its own, because the orchestrator drives
arbitrary configured repos and a closed list would teach the wrong style everywhere but the one it was written for:
the agent reads `git log --oneline -20` and mirrors whatever subject/prefix convention that repository's own recent
history uses, as a single short imperative line with no body, no trailer, and one `-m`.

What the note carves out of that history is the reference suffix. Under `PR_REF_IN_SUBJECT` — the default — every
commit the orchestrator publishes onto a pull request ends in ` (#N)` naming that pull request
([`../configuration.md`](../configuration.md#cadence-and-budgets)); with the switch off nothing is suffixed at all, and
the history stays whatever the developers wrote. So on a repo this orchestrator has already published to with the
default on, "mirror recent history" reads as an instruction to write a numeric suffix — and the only number the agent
has is the issue it is implementing, which would land a subject naming the issue and the pull request both. So the
note says what those suffixes are: publication metadata rather than style. The agent writes the descriptive subject
alone, adds no numeric suffix of its own, never copies the tracked issue's number into one, and leaves the pull
request reference to the orchestrator that appends it when configured to. Issue linkage is the pull request body's to
carry, not the subject's. The note is unconditional, because the prompt is built with no reading of that switch and a
repo whose history carries references from an earlier setting reads the same either way.

The note is not the only guard, and the code enforces the same rule at each of the three places an agent-written
subject is read back out. PR-title selection (`git/publication/titles.py`) takes the tracked issue's own trailing
reference off whichever line it reuses — the branch's first commit subject, or the issue title — so a commit written
before this contract, one a human wrote by hand, and an issue title with the number typed onto the end each still
yield a title without it. Nothing is appended in its place: a title is picked before the pull request has a number.
The two publishers decide the whole of it instead, because each has a pull request to name: the approval squash
reads that same first commit subject for the commit it collapses or rewrites to, and the documenting pass reads the
`docs:` commit's own. On both, the tracked issue's reference goes and the pull request's is kept exactly once, so a
subject a developer ended in the issue's number — and the `<subject> (#issue) (#PR)` a developer commit and an
earlier publication each wrote half of — land alike as `<subject> (#PR)`. A reference to any other number is
somebody else's link and survives on every road.

Where the contract is carried:

- **Whole** in the initial `_build_implement_prompt`, the automated-review `_build_fix_prompt`, the final pass's
  `_build_documentation_prompt`, the requirements-drift `_build_user_content_change_prompt`, the PR-feedback
  `_build_pr_comment_followup`, both discussion builders (`_build_discussion_prompt` and
  `_build_discussion_followup_prompt` — whichever round the confirmation lands on commits the plan file, and that
  subject becomes the plan pull request's title), and the late revision's `_revision_prompt`
  (`decomposition/late_revision.py`).
- **Whole** in the bare developer resume payloads too — `_build_human_reply_followup` and
  `_DEVELOPER_CONTINUE_RETRY_PROMPT` — which ask for commits while resuming a transcript that may predate the contract
  or hold another stage's prompt. They carry it for one more reason than the report contract they restate beside it: a
  developer resume can rotate into a **fresh** session (`DEV_SESSION_MAX_RESUMES`, the consecutive-silent-park
  fallback, or poisoned-session recovery), and the only text ahead of the payload there is
  `_build_fresh_respawn_preamble`, which teaches no subject contract of its own. Without it a brand-new agent would be
  told to commit with nothing said about what its subject may carry.
- **Absent** from `_build_conflict_resolution_prompt` and from the conflict stage's own bare continue, which stays on
  the plain `_CONTINUE_RETRY_PROMPT`: that agent finishes an in-progress rebase with `git rebase --continue` and
  authors no subject at all.

`tests/workflow/engine/test_prompts.py` sweeps the prompts listed above for both halves of the note, so removing one
from a prompt already in the sweep fails the suite. A newly written commit-producing prompt has to be added to that
sweep by hand — nothing enumerates the builders automatically.

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
  `_build_human_reply_followup` (`_resume_developer_on_human_reply`, over the replies
  `implementing/resume_batch.py` froze and recorded as delivered), the late revision's `_revision_prompt`
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
  own. Its conversation block is the caller's FROZEN, classified thread read wherever the caller holds one — the
  awaiting-human resumes and the explicit `/orchestrator continue` retries (less the commands they consume) take it
  from `implementing/resume_batch.py` — so the preamble and the record of what the prompt delivered come off one
  reading and one filter. A caller with no frozen read gets the read `_build_dev_spawn_prompt` takes for itself.
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

The **initial implementation delivery** is the road that acts on an outcome: `workflow/engine/report_delivery.py`
reads one out of the run the disposition is publishing and records it before the size gate and the push, and
`report_binding.py` binds it to the pull request the code reaches and publishes it there
([`_handle_implementing`](../state-machine/delivery-stages.md#_handle_implementing-label-workflowimplementing)).
There a no-commit reply ending on a report outcome publishes the commits already on the branch where the issue still
owes a report it could not deliver, and is read as any other no-commit reply everywhere else.

The **requirements-drift resume on an open pull request** acts on one too, on `workflow:validating` and `in_review`
([user-content drift](../state-machine/delivery-stages.md#user-content-drift-detection)). A commit the resume made
has its report recorded before the size gate, under the requirements revision the drift check handed the resume, and
bound and settled once the push lands and the stage's own bookkeeping is written; one with no usable report parks
rather than being pushed, and stays unpublished until a reply brings the report. A no-commit reply ending on a report
outcome is published onto the head the pull request already carries — over a tree proved clean, or parked on the
tree with nothing recorded — and routed as an `ACK:` is, and the reviewer waits until the report is confirmed on the
pull request. `ACK:` and a question keep their own roads.

The **reviewer-requested fix round** acts on one on the same pull request, under the `workflow:fixing` label it runs
under: the initial `CHANGES_REQUESTED` run and the parked resume behind it both read their result through
`workflow/stages/validating/fix_reports.py`
([`_handle_validating`](../state-machine/delivery-stages.md#_handle_validating-label-workflowvalidating)'s
`changes_requested` arc and
[`_handle_fixing`](../state-machine/delivery-stages.md#_handle_fixing-label-workflowfixing)).
A commit has its report recorded before the size gate and bound once the push lands; one with no usable report parks
rather than being pushed. A no-commit reply ending on a report outcome is the handover a reviewer item naming report
content earns: published onto the head the branch and the code-publication receipt are PROVED to agree on — every
reading affirmative, since a reading that did not happen may be a branch carrying a commit the pull request has not
got — and routed as a pushed fix is, back on `workflow:validating` for a fresh review of the report and requirements
being handed on. What that handover costs is the SETTLEMENT's to write: the round and the automated-fix bookmarks
ride the record and are closed by the write that confirms the report, so a refused post or a crash leaves the round
unspent and the round to be finished again. A commit an earlier round
left unpublished still passes the gate on its way there, since its own report was that round's to record. The ordinary
non-actionable `ACK:` and a question keep their own roads, and on the human-feedback route the `ACK:` still returns
the pull request to `in_review` — but only a reply that never used the report contract at all is that: one that
reached for the markers and missed, an `ACK:` line beside a report block included, is a broken contract and parks.

Every other developer road is still routed by its commits, its `ACK:` line, and the question parks the
[delivery stages][delivery-stages] describe, and a no-commit reply that ends on a report outcome is read there the way
its stage reads any other no-commit reply without `ACK:`.
The awaiting-human resumes settle the input they delivered straight into pinned state: the report transaction a
run may record carries no consumed watermarks to freeze it onto. The settlement records delivery and nothing more, so
the question the run came back with is still the disposition's to answer.

The **PR-feedback fix round** on `workflow:fixing` records the same thing through the same producer
(`workflow/engine/prompt_delivery.py`): a pushed fix, an `ACK:`, a timeout, a dirty-tree park, and a question park all
delivered the prompt, so all of them record what it carried, while a run the circuit never invoked, one a shutdown
killed, and one an operator paused mid-run record nothing. Each surface of that batch settles the reader that owns it,
so the issue-thread half moves `last_action_comment_id` and the pull-request halves do not, and an accepted
`/orchestrator continue` settles the batch it replayed joined with the fresh rescan — including the bare command the
prompt deliberately never hands the developer, on the surface that command was typed into.

That round can also end on a report outcome, since its prompt teaches the contract like every other developer prompt
and asks by name for an item wanting report content only to be answered in the report with no commit for it. Such a
round settles nothing on the tick: the publication it owes is not this tick's to promise, and feedback recorded as
answered for a report no reviewer has is the one reading that fork exists to refuse.

Delivery is still not completion: an `ACK:` may settle a round whose comments named no actionable change, and it does
not answer the automated `CHANGES_REQUESTED` review that asked for a concrete one — that route has no ACK fast path
and parks for a human with its `pending_fix_*` replay anchor intact.

Publication is recoverable because the records outlive the process. The additive `developer_report_delivery` /
`developer_report_pending` / `developer_report_current` / `developer_report_handoff` group
([`../state-machine/labels-and-state.md#pinned-state`](../state-machine/labels-and-state.md#pinned-state)) is what
carries one report from the run that wrote it across a process that dies mid-way — the complete report text included,
since a transaction recovered from a text nobody kept would have to ask an agent to write it again, and a second run is
not the same report. The publication that records one also tries to complete it on the tick it pushes; where that
did not happen, [the developer-report transaction][report-transaction] finishes a `developer_report_pending`
transaction ahead of every handler. Both publish through the developer-report comment owners
(`github/developer_reports.py`, `github/pull_request_reports.py`, and `workflow/engine/comments.py`'s
`_publish_developer_report`). The reconciliation never reads an agent's message: what it acts on is the record a stage
wrote, and on an issue carrying none it costs one pinned read that has already happened. No reconciliation acts on a
`developer_report_delivery`: binding one to a publication is a stage's step — the implementing publication's, and on
an open pull request the review stages' own, which is also what binds a delivery a later push carried — exchanging
the delivery for its transaction in one write before anything is posted, and taken again on every tick that
republishes the same commit onto the same pull request until it lands.

[question-handler]: ../state-machine/conversation-stages.md#_handle_question-label-question
[discussion-handler]: ../state-machine/conversation-stages.md#_handle_discussion-label-discussion
[delivery-stages]: ../state-machine/delivery-stages.md
[report-transaction]: ../state-machine/delivery-stages.md#the-developer-report-transaction-every-dispatch
