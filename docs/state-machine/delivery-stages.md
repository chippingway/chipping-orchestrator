# Delivery stage handlers

The stages that carry an issue from pickup to a merged PR: pickup and decomposition, the family walks that hold a
parent behind its children, the dev / reviewer / docs loop, and the two labels a PR bounces through. Each section is
one handler — its trigger, the pinned state it reads, its internal flow in the order a tick runs it, and every
transition it may produce — plus the drift hook the drift-sensitive handlers share.

The two operator-applied conversation stages are in [`conversation-stages.md`](conversation-stages.md); the labels,
per-tick flow, and pinned-state keys these handlers are typed by are in
[`labels-and-state.md`](labels-and-state.md); the compact lifecycle reference is in [`lifecycle.md`](lifecycle.md).
Which module owns each handler is in
[`../architecture/workflow-modules.md`](../architecture/workflow-modules.md) and the dispatch that reaches one in
[`../architecture.md#stage-handlers`](../architecture.md#stage-handlers); what each agent role's prompt grants and
forbids is in [`../workflow.md`](../workflow.md).

## `_handle_pickup` (no label → `workflow:decomposing` or `workflow:implementing`)
- **Trigger**: open issue with no workflow label **and no pinned comment**. What this handler does is *greet* an
  issue — the "picking this up" comment, a drift baseline over a thread it assumes nobody has worked, and the
  issue's pinned comment — so an issue that already carries one has been through it, and greeting it again writes a
  second pinned comment that is invisible from the moment it is written (`read_pinned_state` answers with the first
  authenticated one it finds) while the finished workflow in the old one goes on deciding. The dispatcher therefore
  leaves an issue whose workflow label a human removed exactly where they left it, saying so once a tick; the way
  back in is applying a workflow label by hand. The one unlabeled issue with a pinned comment that *is* answered is
  the [restart](labels-and-state.md#late-generation-state), which reaches the same two labels by projecting the
  pinned comment it already has rather than through this path's greeting, fresh state, and author allowlist.
- **Input**: issue title/body/comments; `config.DECOMPOSE` (default on); `config.ALLOWED_ISSUE_AUTHORS` (required —
  startup refuses a list that names nobody).
- **Action**: an issue authored by anyone outside `ALLOWED_ISSUE_AUTHORS` is silently skipped (log only); otherwise
  post a "picking this up" comment, anchor `pickup_comment_id` and `last_action_comment_id` on
  it (the floor the bounded park ending the first agent run walks from), snapshot `user_content_hash`
  over title + body + non-orchestrator comments, then route to `workflow:decomposing` (`DECOMPOSE=on`) or
  `workflow:implementing` (`DECOMPOSE=off`) and run that stage's handler in the same tick, so an unlabeled issue's
  first tick ends inside its second stage.

The allowlist, both routes, and the order they publish the comment, hash, label, and pinned state in all live in
`workflow/engine/pickup.py`; the same-tick handler call is a call-time import of the chosen stage's owner under
`workflow/stages/` — `decomposition/run.py` for one route, `implementing/handler.py` for the other.

## User-content drift detection

The drift-sensitive handlers — `_handle_decomposing`, `_handle_ready`, `_handle_blocked`, `_handle_umbrella`,
`_handle_implementing`, `_handle_validating`, `_handle_documenting`, `_handle_in_review`, `_handle_resolving_conflict`
— run `_detect_user_content_change` somewhere in their flow. The hash covers the issue title, body, and every
human-authored *issue-thread* comment body (PR-conversation comments are not in the hash). The hash and eight
filters below live in `workflow/engine/content_hash.py`; baseline handling and drift routes live in
`workflow/engine/drift.py`, and the frozen prompt every drift resume is answered with — on an open pull
request as much as before one — in `workflow/engine/drift_delivery.py`. Operator-command filters read the
syntax from the owners of those commands.

`_handle_in_review` is the exception in ordering: it runs the four-surface fresh-feedback ID scan FIRST and routes any
unread human comment past those watermarks to `workflow:fixing`, so the drift check that follows reacts only to
changes the ID scan didn't catch (title/body edits, and edits to existing issue-thread comments whose ids are already
below the watermark).

`_handle_implementing` and `_handle_validating` narrow the check on a PARKED tick the same way. Each freezes its one
reply batch before asking, and measures the requirements by what the park had already read — the frozen comments at or
below `last_action_comment_id` — so a reply to the park is the batch's to deliver rather than a drift that resumes the
developer on the whole thread. Only a title/body edit, or an edit to a comment the park had already read, takes the
drift road there, and settling the batch records `user_content_hash` through the reply it delivered.

Every drift road is frozen the same way the batch is, and bounded differently.
`drift_delivery._drift_resume_prompt` reads the
thread ONCE, renders the resume prompt from that read, and carries the `prompt_delivery` record of it through the run —
`_ImplementingDriftRun.delivery`, `_ValidatingDriftRun.delivery`, `_ConflictResumeRun.delivered`, and
`_DriftResume.delivery` — so what the developer was quoted and what the
issue may mark answered are one fact. What differs is the excerpt: a drift resume quotes the WHOLE thread, so it is
capped at 4000 characters like every other whole-thread prompt, while the reply batch quotes only the replies past
the park's watermark and is deliberately uncapped (`resume_batch._UNBOUNDED_EXCERPT`). A cap there would record an
omission the followup never made — it quotes every reply it was handed — and the watermark would then stop below a
comment the developer read.

`in_review` is the one road whose prompt reads a SECOND surface, and
`drift_delivery._pr_drift_resume_prompt` freezes both into the one record. The pull request's unread conversation is
quoted entire below the bounded thread and recorded uncapped for the same reason the reply batch is — every comment
handed over is quoted, so the record may name no omission the prompt did not make. The two halves stay apart in the
record because they answer different cursors and because only one of them is bounded. An outsider's comment is kept
as a refused entry rather than dropped: no reader is ever owed it, so the watermark carry may cross it, and an entry
nothing recorded would have stopped that walk on it forever.

The rules below follow from the frozen record, and they are the general rules for feedback a prompt is settled by
— on either surface it may quote — rather than anything specific to a body edit:

- **The excerpt bound decides the mark.** Where there is one: a comment the drift resume's 4000-character excerpt
  dropped reaches no prompt, so the issue-thread watermark stops below it and it stays deliverable by the scan that
  owns it. The uncapped reply batch drops nothing and so holds nothing back. The requirements revision
  the settlement records still covers the whole read, because that field is the comparison point a later edit is
  measured against and stopping it short of the drop would re-open the same resume, on an identically bounded prompt,
  every poll.
- **A comment that arrives after the freeze is unread.** Nothing between the freeze and the settlement re-reads the
  thread, so a reply written while the agent is out is neither quoted nor crossed — and the revision recorded leaves
  it an edit for the next tick. The bounded walk an announced park takes afterwards stops below it for the same
  reason.
- **Only a run that read the prompt settles it.** The record is settled after the run and only for an outcome that
  counts the input as delivered: a shutdown kill, a live pause, and a launch the run circuit refused consume nothing,
  while a push, an `ACK:`, a timeout, and a question park all do. Delivery is not resolution — the park's reason says
  what is wrong with the answer, not with the input. Each of the three refusals returns before pinned state is
  written (`_ignore_if_never_invoked`, `_ignore_if_interrupted`, and the live-pause flag), so a withheld run leaves
  the watermark, the park flags and the drift baseline exactly as it found them.
- **Only a cursor ONE reading can vouch for is settled.** Every drift road settles `last_action_comment_id`, the
  issue thread's own, for exactly what its prompt quoted there. `pr_last_comment_id` is nobody's settlement to
  write: it spans both IssueComment surfaces, and the one record that covers both — `in_review`'s — reads them a
  moment apart, so a comment landing on the surface read first, after that read, is in neither half while an id
  above it on the other surface is in one. That cursor is derived by the park carry instead, which re-reads both
  surfaces at one moment (see `_handle_in_review` below).
  `pr_last_review_comment_id` and `pr_last_review_summary_id` never move on any drift road, because no drift prompt
  quotes an inline review comment or a review summary — a road that crossed them would hide a reviewer's words from
  the `workflow:fixing` round that exists to deliver them.
- **That settlement is what records the new baseline.** `user_content_hash` moves with the prompt that answered the
  edit, and on the three roads that stage nothing ahead of the run it moves with nothing else: a deferral or a
  refusal park records none of it, and an edit no prompt has carried is still an edit on the next tick. `in_review`
  is the exception, and only for the hash: it stages the refreshed value with the marker saying the issue owes
  `workflow:validating` a move, because the two may never become durable apart (see that handler below). The
  comments are never staged there either — a withheld run leaves every one of them unread.
- **A route that invokes nobody settles nothing.** `_handle_documenting`'s drift unwind changes a label and resets a
  worktree; no agent reads anything, so no watermark moves. It records the requirements revision alone, and that
  record is about the reroute rather than the conversation: it says this stage has already answered the edit with a
  relabel, so the next poll does not announce the same one again. The comments that moved the hash stay unread for
  the reviewer the relabel hands the issue to, and for the fix round behind it.

`_handle_fixing`, `_handle_question`, and `_handle_discussion` deliberately skip the drift check. `_handle_fixing`
refreshes `user_content_hash` itself once it has consumed the PR-side feedback; `_handle_question` and
`_handle_discussion` run their own conversation flows on an operator-applied label nothing routes into, so rerouting
an edited issue to `workflow:decomposing` would take it out of the conversation a human deliberately put it in.

Non-human content is filtered eight ways:

- pinned-state comments by `PINNED_STATE_MARKER`;
- orchestrator-posted comments by `_ORCH_COMMENT_MARKER` (an HTML comment embedded via `_with_orch_marker`, invisible in
  rendered Markdown, survives id-cap eviction);
- legacy orchestrator comments by id from `orchestrator_comment_ids`;
- third-party Bot/App accounts (Dependabot, Renovate, CI bots) via GitHub's `user.type == "Bot"` structural flag;
- a bare `/orchestrator continue` operator command via `_is_bare_orchestrator_continue` — it is an operator control, not
  requirements content, so it must not shift the hash and route the nudge through drift handling instead of the stage's
  intentional session-limit retry (a comment carrying the command *alongside* genuine guidance is not bare, so it still
  shifts the hash);
- a bare `/orchestrator add-agent-runs N` command via `run_grant_request._is_bare_command`, for the same reason and
  one of its own: the dispatcher answers that command and then hands the **same tick** to the stage below, so a hash
  counting it would meet the handler as a body edit nobody made — `validating` would resume the developer on "the human
  edited the issue" instead of running the reviewer round the issue stopped mid-way through. Filtered in **both**
  hashing modes, since the legacy algorithm the flag below reproduces predates the command entirely; guidance beside
  the command is requirements here too, so it is not bare, it shifts the hash, and the drift road carries those words
  to the agent;
- a whole-comment `/orchestrator authorize-oversized <commit>` via
  `messages._authorized_oversized_candidate`, in both modes and for the same reasons: it is an operator control, and
  the tick that reads it hands the **same issue** straight on to the stage the authorized publication continues at,
  so a hash counting it would meet that stage as a body edit nobody made — resuming a developer over the very commit
  an operator just authorized. Only the whole comment is the command, so a paragraph containing the line is
  requirements text, shifts the hash, and reaches the developer as the guidance it is;
- untrusted authors via `github.comments.is_trusted_author` against `ALLOWED_ISSUE_AUTHORS`, so an outsider's
  comment cannot shift the hash and re-trigger drift on a public repo.
  The same trust helpers filter agent-prompt text in `workflow/engine/prompt_context.py`: `_recent_comments_text`
  (documentation / decompose / question — the prompts whose stage settles
  nothing by what they quote), `_delivered_thread` beside it (the implementing fresh spawn, the validating reviewer
  round, and every drift resume, which render the same filtered text and keep the record of which
  comments it was made of), and `drift_delivery._delivered_pr_conversation` for the one prompt that reads the pull
  request's conversation too. Beneath `_recent_comments_text` sits `_thread_text`, which the `discussion`
  stage calls directly over its own thread snapshot — with one documented retention, the orchestrator's own comments
  by recorded `orchestrator_comment_ids`, since that stage's full-context prompt rebuilds a conversation the
  orchestrator is half of (see
  [the trust boundary](../security.md#comment-trust-boundary-allowed_issue_authors)); the awaiting-human resume paths
  that quote new
  replies directly (`filter_trusted` in the implementing, validating, decomposing, documenting, resolving_conflict,
  question, and discussion resumes) plus the auto-rebase-park retry-unpark in `_sync_pr_worktree_to_base`; and the
  four-surface
  PR-feedback scans driving the `in_review` -> `workflow:fixing` route, the fixing dev-resume, and the `/orchestrator
  continue` batch replay (`filter_trusted` in `_scan_fresh_pr_feedback`, the drift-resume PR-conversation block,
  `_rescan_fixing_feedback`, and `_reconstruct_pending_fix_batch`). On every awaiting-human resume — and the
  auto-rebase retry-unpark — the filter runs on the whole `comments_after` batch up front, so it gates the non-empty
  check, the quoted follow-up, the consumed-watermark advance, and — in `workflow:validating` — the `/orchestrator
  add-review-rounds` review-cap command and the reviewer-respawn nudge; an untrusted comment resumes none of those
  sessions and does not advance the watermark (it is re-filtered on each later tick, never marked consumed). On the
  `workflow:implementing` and `workflow:validating` human-reply resumes that batch is frozen ONCE, by
  `implementing/resume_batch.py`, and the park-reason decisions, the quoted follow-up, and the settlement all read it.
  Beside the trust filter it drops the orchestrator's own comments by recorded id and refuses a body carrying
  `<!--orchestrator-comment-->` that the id ledger cannot vouch for — the marker is text anybody may paste, and the
  token's login may be a human's. The pinned state comment is left out by its id, never by the
  `<!--orchestrator-state` marker, so a human reply quoting that marker is a reply. The same read supplies the
  conversation a FRESH spawn is re-grounded with, through the same classification (our own recorded comments stay in
  it), so a retired session's spawn is not handed a comment minutes newer than the batch the settlement records. The
  `/orchestrator continue` that renews a spent spawn budget on a `retry_cap`-parked `workflow:decomposing` or
  `workflow:implementing` issue is read through the same filter (`filter_trusted` in each stage's
  `retry_cap._trusted_replies`), so what buys an agent run there is a trusted account's word and nothing else. The
  `/orchestrator add-agent-runs N` that widens a spent LIFETIME agent-run allowance is filtered in the one place it
  is read — the dispatcher's own hold, `run_grant._lifts_the_park` — for the same reason and one more: an untrusted
  request earns no receipt either, since a reply is a comment somebody else's word paid for and posting one would
  spend the watermark a trusted operator's command is read against. An
  untrusted comment therefore neither shifts the drift hash, sets a
  pending-fix bookmark, routes `in_review` to `workflow:fixing`, resumes an awaiting-human decomposer / developer /
  reviewer / question / documenting session, retries a parked auto-rebase, satisfies the `/orchestrator
  add-review-rounds` review-cap command, renews an exhausted spawn budget, buys an issue past its lifetime agent-run
  ceiling, authorizes an oversized committed candidate to publish unsplit, nor reaches any agent prompt.

`_detect_user_content_change` durably persists the baseline on its FIRST encounter via `gh.write_pinned_state`, so an
early-return tick cannot silently absorb a later edit as the new baseline. Where a stage recorded a reading it acted on
without consuming any of it as `observed_user_content_hash` — a late adjudication carrying on over a quiet reading of
an issue with no baseline — that first encounter compares against the observed reading instead: the current value is
persisted only where it still matches, and anything written since is reported as drift. It also carries a **legacy-hash
normalization** path: a baseline written by the pre-issue-#729 algorithm counted a bare `/orchestrator continue`
comment, so after deploy it would compare unequal to the new hash even with no real edit. Before reporting drift the
helper recomputes with the old algorithm (`_compute_user_content_hash(..., include_bare_continue=True)`); if that
reproduces the stored baseline the delta is purely the algorithm change, so it persists the new baseline and reports no
drift — a bare continue outstanding at deploy time cannot fire one false "issue body/content changed" route. On drift
the action depends on lifecycle position:

- **`workflow:decomposing`** — handled inline at the top of `_handle_decomposing`: drop `decomposer_session_id`, wipe
  `children` / `dep_graph` / `expected_children_count` / `split_attempt` / `umbrella`, clear park flags, post a
  `:pencil2: issue content changed` notice, then fall through in the same tick so the decomposer re-spawns against
  the updated body. An issue
  standing on a `retry_cap` park is held one step ahead of this (see that handler's step 1): the re-spawn it falls
  through to is exactly the spawn that park refused, so the edit waits with everything else the issue carries until
  a human continues it.
- **`workflow:ready` / `workflow:blocked` / `workflow:umbrella`** (no implementation has started) — route back to
  `workflow:decomposing` via `_route_drift_to_decomposing`: same state-wipe + notice, plus a label flip to
  `workflow:decomposing`. `decomposer_agent` is preserved across this transition so a mid-flight `DECOMPOSE_AGENT` env
  flip cannot retarget an in-flight issue. Any previously-tracked children are listed in the notice as ORPHANED — the
  orchestrator no longer tracks them, so the operator must close any that no longer apply. On an umbrella a late
  split made, what the check compares against is the baseline the late adjudication recorded when it last consumed a
  reply — frozen off the reading that reply arrived in, and durable before the split's handoff — so guidance a
  developer revision already answered is not an edit here, while a comment or edit written after that reading is. An
  issue that had no baseline and consumed no reply carries the reading the adjudication went on over as
  `observed_user_content_hash`, which this first check compares against, so a comment or edit written while the
  adjudicator ran is an edit here too.
  Neither reset touches a late split's generation, which is not manifest tracking: its register, its snapshot, and
  `late_consumers` survive whole and go on naming the orphans, so the umbrella the re-decomposition leaves still
  proves that ref against them
  (see [what the terminal waits on](#_handle_umbrella-label-workflowumbrella)). The orphans are never adopted,
  relabelled, or reopened. Nor does either reset touch the `late_ancestry_*` group, which is what the re-derived
  manifest's children are seeded from: the split that answers the reroute asks which late lineage they inherit
  (`late_split/provenance.py`, see [inherited lineage](labels-and-state.md#late-generation-state)) before it creates
  one, and seeds each one level below the parent under the same root rather than as a fresh root at depth 0. Only a
  replacement pointed at the ref the parent's own split holds joins `late_consumers`, and it joins in the write that
  records it in `children`, so the ref is kept for it as well as for the orphans. A lineage the record cannot prove,
  a parent already at `MAX_LINEAGE_DEPTH`, a snapshot the parent's own ledger cannot say is held or released, or
  one held with no recorded base parks `replacement_lineage_unproved` with no child created (see
  [its contracts](../workflow/roles.md#what-an-ordinary-re-decomposition-holds-its-children-to)).
  The reset drops the discarded manifest's `split_attempt`, so no child it left behind is adopted into the next split,
  after writing those children — any unrecorded one found by its receipt — onto `late_consumers` as orphans.
- **`workflow:implementing` / `workflow:validating` / `in_review` / `workflow:resolving_conflict`** (a dev session
  exists and possibly a PR) — post a `:pencil2: issue body changed; resuming dev session` notice (on the issue for
  implementing/validating, on the PR for in_review/resolving_conflict), resume the locked dev session with
  `_build_user_content_change_prompt`, and route the result through `_post_user_content_change_result`. All four take
  a frozen delivery record and settle it after the run, for every outcome that reached an agent and for none that did
  not. Three of them freeze `_drift_resume_prompt` — the bounded issue-thread excerpt alone. `in_review` freezes
  `_pr_drift_resume_prompt`, which is that same excerpt plus the pull request's unread conversation quoted entire
  below it (`_drift_unread_pr_conv`, read before the notice this road posts on that surface), and records the two
  apart, and settles only the half one reading can vouch for: `last_action_comment_id` and the requirements
  revision. `pr_last_comment_id` spans both surfaces and this record read them a moment apart, so it is left to the
  watermark carry, which re-reads both at one moment, crosses exactly the ids the record names, and stops at the
  first it cannot; `pr_last_review_comment_id` / `pr_last_review_summary_id` never move, since no
  prompt on this road quotes an inline comment or a review summary. An outsider's PR comment reaches neither the
  prompt nor the delivered half of the record — it is retained as a refused entry, which is what lets that
  carry cross a comment no reader is ever owed. Whatever the excerpt bound dropped, and whatever
  landed while the agent was out, is in neither record and is still unread on the next tick.
  On `workflow:implementing` an **unspent `retry_cap_continued`** outranks
  the recorded session and sends the edit down the no-session road instead (park cleared, nothing recorded, fall
  through to the gated fresh spawn, which builds its prompt from the body the human just wrote and settles
  that): an issue parked on a spent
  budget sits there for as long as it takes somebody to answer, so the requirements move under it, and what the
  continuation bought is one fresh spawn — the only run the budget counts. Resumed, the agent would run on the
  human's attempt while the grant stayed on the issue, ready to buy a second run nothing charged.
- **`workflow:documenting`** — route back to `workflow:validating` (no docs spawn) — see the handler section below.

Result routing in `_post_user_content_change_result`:

- a shutdown-`interrupted` resume short-circuits before any branch below: the helper self-guards (returns `"parked"`
  without posting, parking, or pushing) and the drift callers in turn bail WITHOUT writing pinned state (in_review /
  resolving_conflict guard ahead of the helper via `_ignore_if_interrupted`), so the killed run leaves durable state
  untouched for the next process to retry;
- a clean pushed fix hands straight back to `workflow:validating` from every stage that runs the drift resume; from
  `workflow:implementing` the drift path publishes through the shared committed-work seam, so the size gate measures
  the resumed commit before `_on_commits` opens/pushes the PR;
- on `workflow:validating`, `in_review` and `workflow:resolving_conflict`, where the caller names what its resume was
  `handed`, a commit this run made is held to the developer report contract (`validating/drift_reports.py`): the
  report is recorded as `developer_report_delivery` BEFORE the size gate reads the candidate, under that stage's route
  and the requirements revision that caller handed it — on all three the fingerprint of the read its own prompt was
  built from, which is also the baseline that read's settlement writes — never the baseline as it stands when
  publication succeeds. Once the push lands the caller writes
  its own bookkeeping — on `in_review` the relabel too, on `workflow:resolving_conflict` the counted round and its
  relabel —
  and only then binds the report to the publication the code-publication receipt names, settling through the
  [reconciliation](#the-developer-report-transaction-every-dispatch) on the same tick
  (`validating/report_settlement.py`). The pull request, its description, and the issue are all read again by number
  first: the description says whether a report VERIFIED on that very body would cost the pull request its closing
  reference and attribution, and the reconciliation proves the requirements over the fresh issue, since the one the
  tick holds was fetched before the resumed run and a title or body edited during it exists only on the new object.
  A run that completed and committed with no usable report parks under `report_undeliverable` with nothing pushed,
  under a notice naming what this road withheld: the pull request stays open on the commit it already carried, which
  is what the same park says nothing was opened of on the implementing seam.
  A run that did NOT complete is parked the same way and publishes the same nothing. The engine exempts an
  incomplete run from the report contract — a nonzero exit, a provider refusal and a launch nothing invoked are
  failures other roads answer, and on the roads that exemption serves nothing is published either way — but this
  road publishes, so a commit pushed for such a run would reach the reviewer with no account of it anywhere and no
  session left to ask. The park says so in its own words rather than the engine's, which speaks for a developer
  that finished and declined to report;
- a no-commit reply whose clean HEAD is strictly ahead of the remote PR branch (a fix a prior parked / interrupted run
  committed but never pushed) is published through the push tail and counted as a pushed fix
  (`validating/stranded._stranded_evidence`), ahead of the ack check — EXCEPT on the requirements-drift road,
  where such a commit is work no report on the pull request describes: there it stays unpublished and the
  undescribed-work flag goes down for it, so the reply keeps its own road as an ack or a question while the review
  hold behind it asks a human for the report. Which run left the commit decides nothing; a reply that IS a report
  publishes it, since a report written over the branch as it stands describes it too;
- on those same three stages a no-commit reply ending on a report outcome is `"reported"`: the report is recorded and,
  behind the caller's bookkeeping, bound to the head the pull request already carries, needing no commit, and routed
  as an ack is. The tree is proved clean first, as every publication's is: a report over loose work describes
  something the pull request does not carry and could never settle, so the run parks on the tree with nothing
  recorded, and the reply resumes the session to finish and report again — the drift prompt
  asks for a report whenever the report has to change to answer the edit, so parking it as a question would stall a
  developer who finished;
- a no-commit reply is otherwise treated as an ack ONLY when it carries the explicit `ACK: <reason>` marker the resume
  prompt instructs the dev to emit when existing work already satisfies the edit and nothing its report says has to
  change;
- any other no-commit response falls back to `_on_question` and parks awaiting human.

Whichever of those ends the tick, the reviewer on `workflow:validating` is held until a report recorded there is
confirmed on the pull request — the report hold in [`_handle_validating`](#_handle_validating-label-workflowvalidating)
step 3 — and an edit or comment landing while the agent is out leaves the report owed rather than stamped with it,
for the next drift resume to answer with a report of its own.

Per-stage specifics:

- For **`in_review`** drift, the "pushed", "ack", and "reported" outcomes all reset `review_round` (a drift
  invalidates the prior approval) and bounce directly back to `workflow:validating` — a pushed head without waiting
  for its report, since the approval is stale either way and it is `validating` that holds the reviewer for it. The
  drift block also captures unread PR-conversation comments past `pr_last_comment_id` BEFORE posting its notice:
  that capture is both how they reach the resume prompt and how the record that prompt is frozen with names them, so
  the watermark carry afterwards may advance over them. The carry is handed that record rather than the read behind
  it, since the bounded half delivered less than it read.
- For **`workflow:resolving_conflict`** drift, ONLY the "pushed" outcome relabels back to `workflow:validating` (with
  `review_round=0`, `conflict_round` bumped). Ack, "reported", and parked outcomes stay on
  `workflow:resolving_conflict` — the rebase work is still unfinished, and the next tick finds the branch on its base,
  or rebases it, and hands it on. The resume is `handed` this stage's route and the revision its frozen record
  fingerprints (`conflicts/resume_reports.py`), so what the session returns is the report the pull request gets —
  recorded ahead of the gate, bound to the head the push left once the round is counted and relabelled, or to the
  head the pull request already carries for a report alone — and see
  [_handle_resolving_conflict](#_handle_resolving_conflict-label-workflowresolving_conflict) for the recovery of
  each window between the record and its settlement. A park this road takes writes no `requirements_drift_open`:
  its reply is this stage's own road, which reads the report the issue owes for itself.
  Three outcomes short-circuit BEFORE `_post_user_content_change_result` and return
  WITHOUT writing pinned state, in this order: a launch the run circuit turned away
  (`_ignore_if_never_invoked` — the refusal it recorded where it was decided is the whole of what the tick says, and
  a disposition reached anyway would park in the name of a process that never started), an `interrupted` resume
  (shutdown sweep killed the run mid-flight; the shared helper also self-guards on interrupted as a backstop,
  returning `"parked"`), and a mid-run `paused` / `backlog` (`pause_guard=True`). None of them settles the frozen
  record, and nothing on this road is staged ahead of the run, so the next process re-detects the same edit and
  re-runs the drift resume. This road reads the issue thread and nothing else, so its
  settlement moves `last_action_comment_id` alone and every pull-request surface stays unread for the round that
  owns it.
- For **`workflow:implementing`** drift, the resume runs only when `dev_session_id` is recorded. With recovered
  unpushed commits but no session the handler parks (the commits were authored against the pre-drift body). With no
  session, no recovered commits, and `awaiting_human=True`, park flags are cleared so the fresh-spawn branch fires
  this tick against the updated body. Clearing that park records NOTHING — not the watermark and not the baseline:
  the pre-session road hands the edit on (`state._EDIT_OWED_BY_THE_SPAWN`) and the fresh spawn settles both, against
  the conversation its own `_build_implement_prompt` quoted and only once that run counts as delivered. So a spawn
  the retry budget refuses, an interrupted one, and a live pause each leave the edit exactly as they found it, and
  the `/orchestrator continue` that buys the refused spawn answers the same edit rather than one nothing still calls
  new. The `stale_recovered_work` refusal records nothing about the edit either, since nothing ran — but it does
  record ITSELF, as a durable `park_reason`, which is the only thing that tells the next tick its own sentence from
  one still owed. Announced once, it then stands down: the road recognizes its park and falls through, so the reply
  it asked for reaches the awaiting-human resume that delivers and settles it, and the quiet `agent_timeout`
  recovery cannot publish those commits behind the operator's back (the reason is no longer `agent_timeout`). A park
  standing for any OTHER reason hears the refusal, which supersedes it: what the issue waits on now is a decision
  about the commits.
- For **`workflow:validating`** drift, the handler defers to the awaiting-human branch when `park_reason` is
  reviewer-side (`reviewer_timeout` / `reviewer_failed`, and a returned verdict's `reviewer_unverified` /
  `reviewer_unrecorded` park — `state._REVIEWER_SIDE_PARK_REASONS`): a "retry" reply after a reviewer failure, or to
  a verdict whose round the reviewer has to redo, must re-spawn the reviewer, not the dev. The two verdict parks
  never retry themselves, so an edit under one nobody replied to leaves the park standing and waits for the reviewer
  that reply buys. A deferral delivers the edit to nobody, so it records nothing about it — no watermark and
  no baseline. What it does record is `validating_reviewer_owes_a_round`, because the park is gone before that
  round runs: the silent recovery clears the flags and ends its tick, a report still owed holds the reviewer behind
  a clear already written, and without the note the edit would take a later tick down the developer's road ahead of
  the retry the park was taken for. The road that clears such a park into a round writes the same note, with the
  value saying a REPLY bought the round rather than a recovery releasing one — and a deferral never writes over a
  claim already standing, or the round would be left with nothing to record. The round that runs drops the note and
  records what bought it — the retry reply or the operator's grant — off the one read its OWN prompt was
  rendered from (`reviewer.py`), whether or not the park outlived the tick that cleared it, while a launch the run
  circuit turned away records neither, so an edit no prompt
  has carried is still an edit on the tick after this one. The cap's `/orchestrator add-review-rounds` is the one
  control road recording anything of its own, and only where the comment IS the command and nothing else
  (`awaiting._is_bare_command`, the test `/orchestrator continue` and `/orchestrator add-agent-runs` are held to):
  THAT COMMENT's words as read when it answers the command on the thread, since a grant nobody can act on must not
  come back forever, while every other comment in the batch goes into the record as an omission — the requirements
  those words arrived beside stay the round's to record, and guidance somebody wrote below the command is nobody's
  to cross. A command written INSIDE a comment of guidance records nothing at all: crossing it would cross a head
  no prompt here carried and the bounded round a grant buys may never quote, so the whole comment stays unread and
  that round delivers and records it. A command the mark is held below outlives the cap it answered — the batch a
  LATER cap freezes reaches back below it and carries the same words again — so the grant records the comment it
  was written for (`review_cap_granted_comment_id`), beside the round reset and in the same write, and reads a
  command that record already names as no command at all (`awaiting._cap_command_to_answer`). Beside rather than
  ahead of the reset because the two have to be durable together:
  the reset is staged for the reviewer's own write, so a launch the run circuit refuses keeps the notice, discards
  both, and leaves the very command an agent-run grant hands back to be honored for real. The invalid-argument
  refusal is the other shape — its write follows its post, so the post standing above the command is what keeps it
  from saying the same thing on every poll. A command written later carries an id of its own and is new either
  way. A
  reviewer-side park's retry records nothing at all — the reply is the round's to read, under
  the round's own excerpt bound, and one that bound cut short must stay unread for the scan that owns the issue
  thread rather than be marked delivered out of the unbounded batch a park froze for a developer prompt.
  One thing outranks the deferral in both shapes: a report this stage still owes its pull request. No reviewer runs
  behind that debt, and the record it is owed was written against requirements a reply has already moved — which
  the reconciliation stands down on until a resume answers the edit — so the edit takes the developer's road, those
  words are delivered and recorded there, and the note stands for the round behind it.
  Where the resume does run, `_finish_validating_drift` settles its frozen
  record before the result handler posts, pushes, or spends a round, and the requirements revision that record
  fingerprints is what the run's report is stamped with: the drift check's own hash was taken a moment earlier, and
  a reply landing in between is in the prompt and in the settled baseline, so a report stamped with the older value
  would be held against requirements its own prompt contained. Both review stages name
  what their resume was `handed`, so the report contract above runs for each: a resume ending PARKED records
  `requirements_drift_open` beside that park, which is what makes the reply clearing it the rest of this resume
  rather than an ordinary fix, and any outcome that answers the edit drops the claim again. The report a `"pushed"`
  or `"reported"` outcome recorded is bound and settled AFTER the stage's own bookkeeping — the round bump and the
  pinned write here, the relabel on `in_review` — so no tick ever finds a settled report beside bookkeeping a crash
  could still lose, or a settled report beside a label still claiming the approval the edit made stale.

On `workflow:implementing`, `workflow:validating` and `workflow:resolving_conflict` the hash is re-persisted by the
settlement of the prompt that answered the edit and by nothing else, so a single edit triggers exactly one re-route
once something has read it, and a tick that delivered nothing leaves it for the next one. `in_review` stages it
ahead of the run beside the marker saying the issue owes `workflow:validating` a move, since a write that made one
durable without the other would leave an approval standing over requirements nobody has reviewed — and the two
short-circuits that persist no pinned state discard both. The `documenting` unwind persists it on every reaction,
because there it is the claim that this stage has already rerouted rather than a claim that anybody read anything.

## `_handle_decomposing` (label `workflow:decomposing`)
- **Trigger**: each tick while the label is `workflow:decomposing`.
- **Input**: issue + comments + pinned state (`decomposer_agent` / `decomposer_session_id`, retry-budget keys,
  `children`, `dep_graph`, `expected_children_count`, `split_attempt`, `umbrella`).
- **Internal flow**: a `retry_cap` park whose sentence was never said is replayed at entry, ahead of every step
  below and of the late route among them (`_replay_owed_notice` — see
  [the retry budget](labels-and-state.md#the-retry-budget)); it says what the park is for and writes, and the tick
  carries on.
  0. **Late adjudication route.** Behind only that replay, and before every step below it, the tick asks which of the
     two questions wearing this label it is about (`_late_adjudication_owns_the_tick`). An issue whose record carries
     a live late generation is not waiting to be decomposed — its implementation is committed and was measured past
     the ceiling — so the whole tick belongs to the late coordinator (`late_coordinator.py`) and no step below runs,
     no scratch worktree is created, and the initial decomposer is never spawned. The coordinator is asked on *every*
     tick rather than only on the ones that look late, because its own first steps are the reconciliations an earlier
     tick left owed — a park notice a refused comment stranded, an owner read nobody could take — and those are owed
     by exactly the records the gates below would route past. On an issue that never entered the size gate it costs
     one pinned read that has already happened and answers immediately. What it does under that label is
     [`../workflow/roles.md`](../workflow/roles.md#what-a-late-adjudication-is-asked-and-what-it-may-answer).

     The spent spawn budget's park is asked inside that route as well as below it, because the two questions wearing
     this label reach an agent by different roads. A live generation standing on `awaiting_human` +
     `park_reason="retry_cap"` is held by `late_retry_cap._park_owns_the_tick`, behind only the reconciliations
     above and the live-generation gate: the tick ends there having proved no frozen pair, re-marked no pull
     request, read no thread as an answer to a question about the requirements, spawned nothing, and written
     nothing. What lifts it is the same trusted `/orchestrator continue`, buying the same single attempt, spent at
     the same gate in front of the adjudicator's own spawn. The refusal that TAKES that park is staged through the
     late park owner, so the generation, the frozen candidate, the hold's record of the pull request, and the
     sentence the thread is owed (`late_park_notice`, not `retry_cap_notice`) all land on one write before a word of
     it is posted — and the redelivery, the already-posted reconciliation, and the audit phases are the ones every
     other late park gets. No session is retired by the grant there: the pre-spawn record already opens a fresh
     conversation for every run that is not answering a question a human has answered.

     Which field the sentence sits on depends on which owner took the park, so the hold reads **both** before it
     reads the thread for a command. A `retry_cap` park the shared parking form took under this label — on an issue
     that had not entered the size gate, or before this owner existed — owes its sentence on `retry_cap_notice`, and
     the entry replay above is the only thing that says it. That replay stands down for exactly one reason, a thread
     it could not read, and this hold is the very next step: reading only its own field there would call the park
     explained, take a second read that may well succeed where the first failed, and buy an adjudication with words
     written before the human was ever asked.

     "Not an adjudication" is not the same answer as "never entered the gate", so one more question stands between
     the two. A record whose candidate the measurement put at or below the ceiling — a developer revision a human's
     guidance bought, re-frozen and re-measured — has had its size question **answered**: there is no verdict to
     earn and no children to create, and the initial decomposer would re-plan an implementation that is already
     written. That issue is relabelled `workflow:implementing` and falls into that handler on the same tick, exactly
     as the kill-switch route below does — so the ordinary publication reconciles the exact commit already on the
     branch. What the handback owes the pull requests first is what an accepted verdict owes them: this generation's
     "do not merge" notice comes off the held PR (a refusal parks under `decomposing` with the record untouched, so
     the retry is free), and `pr_number` is moved to the pull request the measured commit is actually on — or
     dropped where the recorded one is settled, since a merged plan PR carried into `implementing` ends the issue as
     `done` on a design the revision was never published under.

     The record itself is deliberately KEPT across the label, and retiring it is the implementing gate's own step.
     It is the only thing saying this issue's size question was asked and answered, so a tick that dropped it and
     then failed to move the label would leave a `decomposing` issue the initial decomposer could not tell from one
     that never entered the gate. Kept, the gate finds a measurement it recorded for the commit in hand and settles
     it there, retiring it (the generation dropped, its cycle kept as `late_retired_cycle_id`) durably ahead of the
     push it licenses — which is where the freeze on the base refresh and the live-cycle reading a close is answered
     against both end. A restart's fresh cycle is deliberately not this case: it carries an identity and no
     candidate at all, and it really is waiting to be decomposed.
  1. **The spent spawn budget's own park** (`retry_cap._park_owns_the_tick`), asked behind the late route — which
     holds its own copy of this park for an issue under adjudication — and ahead of every step below it. An issue
     standing on `awaiting_human` + `park_reason="retry_cap"` is stopped on its budget, and each of the three steps
     below would walk past that park for a reason of its own: the drift reset clears park flags and wipes the
     manifest, the kill switch clears the same flags and routes the issue to implementation, and the awaiting-human
     resume reads any trusted reply as the answer. None of them is the answer this park asked for, so while it stands
     the tick ends here having written nothing, spawned nothing, and said nothing — which leaves the manifest, the
     children already open on GitHub, the locked decomposer session and its `decomposer_agent` spec, `pr_number`, and
     a late generation's whole record exactly as the park found them. Each held tick emits the `standing` audit phase,
     so a park that goes on refusing is visible as that rather than as a workflow that went quiet.

     A park that still owes the thread its sentence (`retry_cap_notice`) is held before the thread is read for an
     answer at all. The entry replay above is what says that sentence, and saying it moves the response boundary
     past everything written under the old one — so while the obligation stands, a command on the thread is one
     written before the question was asked. The replay leaves it standing for exactly one reason, a thread it could
     not read, and a second read taken here is as likely to succeed as the first was to fail: read clean, it would
     buy an attempt with words nobody wrote in reply and consume the notice they were owed on the way out.

     What lifts it is a trusted `/orchestrator continue` on the thread past `last_action_comment_id`
     (`_grant_continuation` — see [the retry budget](labels-and-state.md#the-retry-budget)): the renewal the park's
     own notice asks for. The command is taken with whatever else its comment carries, since a decision that arrives
     with an explanation is still the decision and the explanation reaches the fresh decomposer through the prompt it
     is spawned on; an untrusted account's copy of it buys nothing. The grant clears the park, retires
     `decomposer_session_id` while keeping the `decomposer_agent` spec — what the attempt buys is the fresh
     conversation the budget refused, and a spawn pins an id of its own only where the backend hands one back, so an
     id left standing would be replayed by the reply to a question or a timeout that surfaced none — and is written
     down BEFORE the spawn it pays for, so a tick that dies (or a run a mid-run `paused` or a shutdown declines)
     leaves the attempt where the human put it. What it buys is one attempt, spent at the same gate in step 5 that
     refused the last one. A thread this tick could not read hands out nothing and holds the park, since a grant
     made on a read that established nothing spends an attempt no human asked for.
  2. **User-content drift check** (inline) — see drift section above.
  3. **Half-finished decomposition recovery.** If `expected_children_count` is set OR `children` is non-empty (a prior
     tick crashed mid-split, or left a child another poller held unseeded), the handler cannot safely respawn the
     decomposer. When `expected_children_count` is set
     and `len(children) < expected_children_count`, look for the one child a crash between a create and the write
     recording it can leave behind: an issue this orchestrator opened whose body carries the receipt naming this
     parent, its `split_attempt`, and the next slice, every issue walked to find it. The only one carrying it, found
     open, still `workflow:blocked`, not already in `children`, and whose last whole receipt is that one is recorded in
     `children` — in a parent write of its own that also records it on
     `late_consumers` wherever the parent's proved lineage points its children at a snapshot, read off that lineage
     rather than off the child's text, which may have been edited since — and repaired below with the rest. Park with
     `decomposition_crash` when the register is still short — the rest were never created, and the manifest is not
     kept to create them from — when no `split_attempt` names this split (an older binary's), when more than one issue
     carries the receipt, or when the candidate is already recorded, was closed, relabelled, or ends on a receipt other
     than that one, naming it without adopting it. (The child
     itself, whose seed is not the one its receipt owes it, is held by the dispatcher under every label but a
     terminal until that seed is there — see [pinned state](labels-and-state.md#pinned-state) — and the write that
     seeds it below clears `awaiting_human` with it.) Otherwise repair any child whose pinned `parent_number` was never
     seeded, once every recorded child is recognized as this split's own — and, where the parent sits inside a late
     lineage, hold every recorded child to the lineage step 7 would have given it, read off the parent's record rather
     than the child's text: while the parent's split still holds its snapshot every recorded child is owed the pointer,
     so one `late_consumers` no longer names is recorded there again (a parent write ahead of the seed and the finalize)
     and one carrying none of the `late_ancestry_*` group, or a pointer at anything else, is seeded with it; once the
     snapshot has passed to a reclamation the lineage alone is owed and a pointer still on a child is dropped with its
     `late_ancestry_mirror_first` stamp; one carrying exactly what it was owed is left — then post the split's summary
     unless a comment of ours carries that `split_attempt`'s summary receipt (a split recorded with no `split_attempt`
     gets none), and finalize to `workflow:umbrella` (when the flag is true) or `workflow:blocked`. A summary GitHub
     refused is posted by the next recovery, and one that landed ahead of a label write that failed is not posted
     again. Each child is repaired under its own writer claim, and one another poller on the host holds stops the
     recovery there — nothing parked, summarized, or finalized — for the next tick to resume. A parent whose record no
     longer proves that
     lineage, or a child it cannot recognize as its own — an unparsed comment, a `parent_number` that is not exactly
     this issue's number (only a missing one is backfilled), text naming a snapshot ref the split cannot keep, any
     other group (any at all on an ordinary split's child), a register naming it twice, or a receipt other than the one
     the split stamped for its slot; the full list is
     [the split's contract](../workflow/roles.md#what-an-ordinary-re-decomposition-holds-its-children-to) — parks
     `replacement_lineage_unproved` instead. Nothing is written to that child, so none of its children is finalized into
     the walk that starts them. Two owners take those markers away from this recovery: an issue already parked awaiting
     a human, and one carrying a live late generation — the split transaction writes the same two markers and resumes
     from its own durable facts, so finalizing on its behalf would hand a parent on before its snapshot, its
     supersession, or what the remote is owed had been settled. Either way the tick ends having changed nothing.
  4. **DECOMPOSE kill switch.** If `config.DECOMPOSE` is off when this handler runs, clear decomposer-side park flags,
     ratchet `last_action_comment_id` past every visible comment, flip the label to `workflow:implementing`, and fall
     into `_handle_implementing`. Step 3 runs first so orphan children are not abandoned. An issue parked on
     `retry_cap` never reaches this step at all (step 1 holds it), so the switch cannot clear a park a human was
     asked to answer — and it loses nothing by waiting, since no decomposition runs while that park stands; the tick
     after a continuation routes it here as usual. An issue carrying a live late generation — recorded, not
     cancelled, and either oversized or still owing the post-agent owner read — takes neither branch: the tick
     returns leaving it exactly where it is, because the legacy route would publish a committed candidate measured
     past the ceiling as though a human had authorized publishing it unsplit. The owed
     read is the half a size-keyed gate misses: a revision that came back UNDER the ceiling is no longer oversized,
     and nobody has established that the issue it belongs to is still open. The same issue relabelled by hand never
     reaches this handler — or any other — at all: the dispatcher puts the label back first. See
     [`../workflow/roles.md`](../workflow/roles.md#what-the-humans-can-still-change-while-a-candidate-is-frozen).
  5. **Awaiting-human resume OR fresh spawn.** Resume on a new comment; otherwise gate on the per-issue retry budget
     (shared with `implementing`; an exhausted one parks the issue durably as `retry_cap`, says so once, and is held
     by step 1 from there on — see [the retry budget](labels-and-state.md#the-retry-budget)), ensure a read-only
     worktree, resolve the spec via `_read_decomposer_session`, persist `decomposer_agent` BEFORE invoking
     `run_agent`, and spawn the decomposer. A
     mid-run `paused` / `backlog` re-check (`_paused_during_agent_run`) right after the run returns short-circuits
     both branches BEFORE the usage fold, timeout / read-only park, manifest parse, child creation, or relabel, so the
     next tick re-runs the decomposer from durable state.
  6. **Read-only check.** If the worktree now has commits or dirty files, park awaiting human and KEEP the worktree for
     operator inspection. The decomposer is read-only — without this guard, `_handle_implementing`'s recovery path
     would later push decomposer-authored work as implementation. A launch that never became a process
     (`invoked=False` — the agent-run circuit refused it) short-circuits ahead of this check and of the pause
     re-check above it: nothing in that worktree is its doing, and a `decomposer_dirty` park in its name would
     overwrite the durable `agent_run_limit` one the refusal took
     ([The agent-run circuit](labels-and-state.md#the-agent-run-circuit)).
  7. **Parse the manifest** via `_parse_manifest` (regex captures the fenced ` ```orchestrator-manifest ` block):
     - invalid manifest → park with the parse error.
     - no fenced block → treat as a question; park.
     - `decision == "single"` → post the collected-context comment (rationale plus the manifest's optional
       `affected_files` / `notes`, built by `_build_single_decision_comment`) so the implementer inherits the
       decomposer's groundwork via `_recent_comments_text`; label `workflow:ready`, stamp `decomposed_at`.
     - `decision == "split"` → first decide the late lineage the children inherit
       (`stages/decomposition/replacement_lineage.py` over `late_split/provenance.py`): an issue no late split
       charged inherits none, and an unprovable record, a parent already at `MAX_LINEAGE_DEPTH`, a split of the
       parent's own whose ledger cannot say whether its snapshot is held or released (or that holds it with no
       recorded base for the reuse instructions to name its change from), or a slice whose own title or body names a
       snapshot ref its child would not be kept (any but the one it is pointed at or this repository's mirror of it,
       read as [the split's contract](../workflow/roles.md#what-an-ordinary-re-decomposition-holds-its-children-to)
       reads every mention) parks `replacement_lineage_unproved` before `expected_children_count` is written, creating
       nothing. Then persist `expected_children_count`, `umbrella`, a freshly minted `split_attempt`, and
       the whole `dep_graph` in one parent write, and for each child call `gh.create_child_issue(...)` with label
       `workflow:blocked` (the child's only birth label) and a body carrying the hidden receipt
       `<!--orchestrator-split-child:issue=<parent>:attempt=<split_attempt>:index=<slice>:lineage=<owed>-->` —
       `<owed>` the late lineage it is seeded with, or `none` — after its declared slice, record it in `children` —
       and in the same write on `late_consumers`, where the parent's own split holds the snapshot it will be pointed
       at — and seed the child's pinned state with `parent_number`, `created_at`, and that lineage, never the
       parent's measurement, exemption, or authorization. The seed is made under the child's writer claim and added
       to the record the child carries by then, lifting the `replacement_lineage_unproved` hold another poller on the
       host may have parked there first; a child that poller still holds is left unseeded while the rest are
       created, and the split then posts no summary, writes no label, and releases nothing, leaving step 3 to seed it
       under the claim, post the summary, and finalize on a later tick. A child owed that snapshot is created with the
       reuse instructions a late split's own children carry appended after its receipt — the ref, its local mirror,
       the commit, the base it was cut against, and how to read and reuse it — since the body is what its implementer
       reads. Otherwise post the split's summary, ending on the hidden receipt
       `<!--orchestrator-split-summary:issue=<parent>:attempt=<split_attempt>-->`, flip the parent to
       `workflow:umbrella` (when the flag is true) or `workflow:blocked`, and activate no-dep children through the
       dependency walk `_handle_blocked` / `_handle_umbrella` run — over
       the same fresh scan of each child's label, so a child a human rejected or closed short of a terminal while its
       siblings were still being created parks the parent and none is relabelled, and with the same lineage recheck
       and per-child recognition as any later release — flipping `workflow:blocked` → `workflow:ready` (best-effort,
       since that walk also treats no-dep children as deps-satisfied on the next poll).
- **Output**: parent → `workflow:ready` / `workflow:blocked` / `workflow:umbrella` / `workflow:implementing`, OR a
  HITL park.

## `_handle_ready` (label `workflow:ready` → `workflow:implementing`)
- **Trigger**: each tick while the label is `workflow:ready`. Reached by a `single`-decision parent or a
  freshly-created child.
- **Action**: post the pickup comment if needed, bump `last_action_comment_id` to the latest visible comment id (so
  comments posted while the issue sat in `workflow:decomposing` / `workflow:blocked` are marked consumed before the
  implementer reads them at spawn), flip to `workflow:implementing`, fall through into `_handle_implementing` on the
  same tick.

## `_handle_blocked` (label `workflow:blocked`)
- **Trigger**: each tick `DEPENDENCY_POLL_EVERY_N_TICKS` makes due while the issue is open on `workflow:blocked` — the
  first poll and every Nth after it (default `5`; `1` is every tick), so a child's activation or the parent's
  completion can wait up to N ticks.
- **Input**: pinned `children` (parent only), optional `dep_graph`, `parent_number` (child only — seeded at
  child-creation time).
- **Internal flow**:
  1. No `children` and `parent_number` is set → no-op (the parent walks the dep graph).
  2. No `children` and no `parent_number` (manual relabel suspected) → park.
  3. Read each child's current label.
  4. Any child `rejected` → park parent awaiting human.
  5. Any child closed but its label is not `done` / `rejected` / `in_review` → retry `_finalize_if_pr_merged` (covers
     an externally-merged child whose own handler has not yet finalized) before falling through to the manually-closed
     park.
  6. Every child `done` → flip parent → `workflow:ready`. A parent that still records a late split's generation —
     the umbrella a split made, re-decomposed by a genuine edit into a manifest that keeps work for the parent — first
     runs the settlement the umbrella's terminal runs (see
     [what the terminal waits on](#_handle_umbrella-label-workflowumbrella)): nothing revisits that ledger once the
     parent has gone back to implementation, so a ref still held for a recorded consumer that has not ended — an
     orphaned original, or a replacement pointed at the ref — keeps the parent on `blocked`, which the next due poll
     asks again, and a reason is logged each time. So does a `late_consumers` list this binary cannot read, whether or
     not a ref is still held beside it — the retirement below keeps that ledger as history, and an unreadable one is
     none — while the superseded branch, which owes no consumer, is still reclaimed. A record whose cycle identity is
     damaged is held exactly as the umbrella's terminal holds it: any ledger left on it — typed entries, or a
     `late_consumers` list, read or not —
     has nothing to correlate a reclamation to, so the parent stays `blocked` and the error is logged. Settled, the
     parent drops its `split_attempt` and retires the split's late cycle in a write of its own ahead of the flip —
     candidate, register, and cycle identity dropped, both ledgers and `late_retired_cycle_id` kept, inside the window
     the umbrella's terminal retires in, a close latched before it or observed during it ending the cycle instead and
     keeping the parent `blocked` — so the implementation it goes back to measures a candidate of its own rather than
     recovering the superseded one, and a later split cuts a register of its own. An issue that never entered the late
     gate owes nothing and flips at once, and so does a record a retirement left once both its ledgers are readable
     and nothing on them is still owed; either drops any `split_attempt` it records in a write of its own while still
     `blocked`, since the flip sets the label before it writes.
  7. Walk children: any `workflow:blocked` child whose recorded dependencies are all `done` gets relabeled
     `workflow:ready`. A child with no recorded deps is also flipped (vacuous all-done over an empty list). Children
     an ordinary split created — anything but a late split's own register — are released only while the lineage and
     snapshot decision their split was proved on still holds off the parent's record: a refusal (a snapshot entry no
     longer held or released, a base gone, an ancestry damaged) releases none and parks the parent
     `replacement_lineage_unproved`, once. Every child the walk would release is held to the recognition step 3's
     recovery applies before the first of them is relabelled, with its parent link required rather than
     backfilled: a comment that will not parse, a `parent_number` that is not this parent's number (a float or a
     bool equal to it included), an ancestry that is not the whole group it was owed (any of it, for an issue no late
     split charged), a pointer the parent's ledger no longer keeps for it (the ref released, or the child off
     `late_consumers`), a title or body naming any other ref, a register naming it more than once, or a receipt other
     than the one its split stamped for its slot — the one the dispatcher would hold its seed to once it runs —
     releases none of them and parks the same way. That costs one pinned read per released child. `_handle_umbrella`
     walks through the same checks, and so does the split's own same-tick release.
- **Output**: parent → `workflow:ready` (all done and nothing a late split recorded still held), OR a sibling
  unblocked, OR a HITL park, OR a no-op for a child still waiting on its dependencies or a parent still holding a
  ref.

## `_handle_umbrella` (label `workflow:umbrella`)
- **Trigger**: each tick `DEPENDENCY_POLL_EVERY_N_TICKS` makes due while the issue is open on `workflow:umbrella`, on
  the same cadence as `_handle_blocked` (only ever a parent — set by the decomposer when the manifest's `umbrella`
  boolean is true).
- **Input**: pinned `children` and optional `dep_graph` on the parent, plus the late generation's obligation ledger
  when the umbrella was made by a late split.
- **Internal flow**: mirrors `_handle_blocked` for the rejected / manually-closed checks and dep-graph walk. The only
  difference is the all-done terminal: when every child reaches `done`, reconcile whatever the issue still owes a
  remote, and only then post a checkmark comment, stamp `umbrella_resolved_at`, set label `done`, and close the issue.
  A `children`-less umbrella is treated as corrupt state and parks.
- **A publication a split superseded is asked about again here.** An umbrella made by a split entered PAST
  publication has two things left that the closed pull request licensed: the children this walk releases, which are
  taking over the work that change carried, and the branch its terminal reclaims, which is the one that change points
  at. The transaction proved the supersession before each of its own steps and then stopped; this handler is what
  runs from then on. So the record's own publication group — which the split's retirement keeps for exactly this,
  alongside the identity, the commits, and both ledgers — is re-read **immediately in front of each of those two
  acts**: by the activation walk before *every* relabel it makes, and by the reclamation before *every* branch it
  deletes. Neither is asked here, one layer up, and that is the point — the child scan this handler takes is a
  request per child and the snapshot rule may spend a read-only probe of its own, so a reading taken before either
  is one the act behind it has already outlived. It is asked a **third and fourth** time on the terminal road — by
  the settlement the terminal waits on, before anything is said, and once more immediately in front of the
  retirement write, since the resolution comment and the latches between them are requests a reopen can land inside.
  A refusal at the second of those writes nothing, so the next dependency poll reads the record exactly as this one
  found it; what it does cost is a sentence already sent, which is why that sentence carries a marker and is gated
  on the **thread** as well as on the stamp the retirement write puts down. That marker names the cycle and
  generation,
  since an operator restarting a rejected cycle keeps the thread, and it is stamped **only** on an umbrella a
  post-publication split made — nothing refuses the others past their sentence, so they keep the stamp as their
  sole gate and spend no listing. Those two are the answer no ledger
  carries: a reclamation that finished owes nothing, so a human who
  restores the branch and reopens the change afterwards finds every entry settled and `done` free to fire — over an
  open change carrying superseded work, with the retirement write behind it dropping the group that could have said
  so. Nothing is written back for it; nothing IS owed the remote, and an entry claiming otherwise would send a later
  pass to delete a branch a human put back on purpose. A pull request somebody reopened, merged, or pushed to holds
  all three:
  the children stay where they are (the walk latches, so a reopen between two relabels releases the first and not
  the second), the branch entry stays owed (nothing was attempted, so nothing is recorded `failed`), the terminal
  stays held, and the reason is logged on every dependency poll that holds. It costs one lookup per release and one
  per delete;
  an umbrella the initial decomposer made, or one from a split entered before publication, reads back as no
  publication and pays nothing.
- **And the record that group sits on is not an unfinished size reading.** The same retirement that keeps the group
  drops the measurement, so what an umbrella a late split made carries on its pinned comment is a whole publication
  group, a candidate, and no count — which is also the shape of a tick that died between the freeze and the diff.
  The reconciliation the dispatcher runs
  [ahead of every handler](#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr) asks whether the
  split has settled before it reads any of that: a `late_phase` of `splitting`, `superseding`, or `cleaning_up`, or
  a non-empty `late_split_children` register, and the tick goes to this handler. Without that question the group
  names the stage the gate was entered from while the issue wears `workflow:umbrella`, so every dispatch is held for
  a human as a reading read off a stage the issue has left, and the walk below never runs — the children of a split
  would be the one thing a split can leave permanently unreleased.
- **What the terminal waits on.** An umbrella made by a late split
  ([`../workflow/roles.md`](../workflow/roles.md#what-a-cleared-split-actually-does)) owes two things — the branch its
  superseded candidate was committed on, and the immutable ref that candidate was preserved under — and this is the
  last tick that could settle either: nothing revisits a closed umbrella, and no other handler reads that ledger. So
  `late_cleanup` retries every `branch` entry that is not `reconciled` — taking down the remote ref, the checkout,
  and the local ref, and settling the entry only once a read afterwards proves all three gone — and deletes each held
  `snapshot_ref` once every recorded direct consumer has **ended** — which all-children-resolved has just made true
  only while the children this handler tracks are the ones the split recorded — proved off the child scan this
  handler already took for every consumer that scan was asked about. A recorded consumer it was not asked about is
  read afresh: after a genuine edit re-decomposed the umbrella the scan is of the replacements, and the originals the
  reroute orphaned are consumers the ref was preserved for — so one of them still open, reopened, or unreadable
  keeps the ref (and the terminal) however finished the replacements are. A replacement the re-decomposition
  pointed at the ref is a recorded consumer too, answered off the scan like any tracked child, so a replacement
  reopened after it resolved keeps the ref the same way. The settlement is asked only where this handler reaches it
  — a poll that finds every tracked child resolved, or one a child's disposition parks — so the ref goes on the first
  such poll after the last recorded consumer (an original, or a replacement pointed at the ref) ends, not on the
  first poll of any kind; an original that ends while replacements are still running frees nothing until they
  resolve or one parks the parent, and the terminal is behind the same settlement, so nothing closes over the ref in
  between. "Ended" is the consumer's
  own issue state, not its label: reaching `done`, being `rejected`, and a human closing it all close the issue, and
  reopening preserves the label — so a child reopened while still wearing `done` is live again and keeps the ref. A
  branch target outside the orchestrator namespace or belonging to another issue is refused rather than deleted; a
  consumer that cannot be proved ended keeps the ref.
- **A park settles the same ledger, and decides no terminal.** All-children-resolved is not the only reading that
  can end every consumer: a child `rejected` and a child closed by hand both park the parent for a human, and both
  closed the child — which is the reading the rule takes wherever that child is one the split recorded. The park
  proves nothing by itself: after a genuine edit the parked child can be a replacement, and an original still open
  or unreadable keeps the ref. Since nothing revisits an *open* umbrella either, a park that returned before settling
  would hold a reclaimable ref and a superseded branch for as long as the human took to answer. So the parked path
  runs the same settlement, handed the fresh scan that parked it and proving the ref against the recorded consumers
  as above, reports only what it actually did, and leaves the park itself untouched: still `awaiting_human`, still
  open, still on `umbrella`.
- **Whether the ledger names every consumer is asked first**, off the record's own phase, because the proof above is
  only as complete as the list it walks. A child is created and then recorded in two writes — it must be, since a
  child on GitHub the parent does not record is a child nothing would come back to — so while `splitting` stands the
  list may be short by one that already exists. Its length decides nothing there: a set of ended consumers says as
  little about the child it has not reached as an empty one does, and nothing on the ref is reclaimed either way.
  Either side of the loop the list is whole — before the split nothing has been created, and past it the loop ran to
  the end — which is also what lets an *empty* list settle a ref no child was ever cut from, the snapshot being
  retained ahead of the first child. A restarted cycle, or a phase this binary cannot type, proves nothing and keeps
  the ref. Nor does any phase while a replacement split of the same owner (its `split_attempt` still on the record) is
  short of its own count or records a child the list lost: that replacement is off the list, so every pass keeps the
  ref.
- **The boundary an interrupted transaction stood at is kept, and a phase before the loop is believed only as far as
  the record bears it out.** A phase is not written only forwards: a transaction re-entered after a crash comes back
  through the whole coordinator, so the hold reconciled before anything spawns, the spawn itself, and the
  claim each completion writes would each name a boundary of their own. None of them is written over
  `snapshotting`, `splitting`, or `superseding` — the record refuses that move itself — so a re-entered split
  carries every one of those steps under the boundary it interrupted. That
  matters most in the window with *nothing* recorded, which no ledger can speak to: a child is created before the
  write that records it, so a loop that died between the two leaves an empty list beside a real issue on GitHub, and
  the phase is all that says so. Beside that, the pre-split phases (`measuring` through `snapshotting`) say "nothing
  has been cut from this ref" only on a record that shows no split ever started — a consumer or a split child on
  the ledgers, or the `expected_children_count` the transaction writes in the same durable step as `splitting`,
  ahead of its first create. That count is what upgrades a pinned comment an EARLIER binary already rewound: the
  guard stops new rewinds and nothing migrates records already in flight, so what has to answer for one of those
  is the evidence no phase write ever touched. That same count is then asked of *every* boundary, ahead of the
  phase, because a record the count proves finished is whole wherever it happens to be standing — and more than
  one boundary needs it. `splitting` is two answers rather than one: the phase goes down before the first create
  *and again beside every child recorded*, the last one included, so a crash between that final write and the
  announcement leaves a complete ledger wearing a mid-loop boundary. `snapshotting` is the same question one retry
  later: a transaction resumed after a park rewrites it over whatever boundary it had reached, so a finished split
  comes back wearing the one it started from. Reading either as mid-flight retains the ref for good and holds the
  terminal with it, since nothing revisits a cancelled owner to move the phase on — so the count is compared
  against the positional register the loop appends to, and a register that reached it is a loop that finished. A
  stale count from an ordinary decomposition of the same issue reads the same way and is meant to — being wrong in
  that direction keeps a ref and holds a terminal, where being wrong in the other deletes the only copy of a
  child's work. Past the loop no corroboration is needed: the transaction reaches `superseding` only once every
  child is created *and* recorded.
- **The delete is a small transaction.** The proof above is a reading of live issues and cannot be reproduced, so the
  entry is written `reclaiming` *before* the delete — which is what stops a tick that died between the push and the
  record of it from leaving a ref the ledger calls retained and the remote no longer has. Every recorded consumer is
  then re-read **past that write and immediately ahead of the delete**, because the scan the pass qualified the ref
  on was taken before the branch half ran and before anything was recorded, and each of those steps is a request a
  human can reopen a consumer during. A consumer that came back inside that window keeps the ref: nothing is asked of
  the remote, the entry stays `reclaiming`, and the terminal is held. What is left is the delete request itself,
  which is irreducible.
- **A recorded decision buys one thing.** A later visit acts on a `reclaiming` or `failed` entry only to **finish a
  delete the remote already took**: past the consumer proof it costs one read-only ask about the ref itself and
  qualifies only if the remote no longer has it. A ref still there is one a reopened child may still be cutting
  from, and no record of a past decision outranks the reading in front of it. A transport that raises rather than
  answering is read as the refusal it is, so no attempt is ever spent without a typed `snapshot_delete_failed`
  behind it.
- **The children are told before the entry closes, and told with a comment.** After a delete the remote accepted,
  and before the entry is written `reconciled`, every recorded consumer gets one comment saying the snapshot has been
  reclaimed and that reuse now needs an explicit new split cycle. It carries a hidden marker naming this owner, cycle,
  and generation, so a consumer already holding one of ours is not told twice. The ref is never recreated.
- **A cancelled cycle tells none of them.** The receipt is what a live split owes children it is still responsible
  for; an ending a human's close forced is responsible for none, and leaves each of them exactly as it found it —
  the entry reconciles on the delete alone. Nothing about the ref goes unsaid: the transport drops this host's
  mirror *before* the remote ref and refuses the whole reclamation if that copy cannot be proved gone, so a child
  reopened afterwards finds no mirror, asks the remote once, and is stopped and told by its own guard — which is
  where the receipt would only ever have been read anyway.
- **This owner never writes a consumer's pinned state.** That comment is written *whole* by whoever writes it, so a
  handler of the child's own that read it before this pass and wrote it after would silently undo anything recorded
  here — and a label is no proxy for "no writer": a terminal finalize sets `done` / `rejected` *before* its last
  write, and closed `workflow:ready` / `workflow:blocked` are swept by nothing, so a consumer left on one never
  becomes terminal at all. A comment is appended rather than rewritten, reaches a consumer in every state a consumer
  can be in, and cannot be lost. What acts on it is the child's own guard (below). A consumer the pass could not
  reach, or whose thread it could not read or post to, leaves the entry `reclaiming` rather than reconciling it —
  reconciling is what stops anything coming back, and for a closed owner this pass is the only thing that would. A
  refused delete tells nobody.

## The agent-run-limit hold (every dispatch, ahead of every handler)
- **Trigger**: `_route_issue_to_handler` on any OPEN issue whose pinned comment carries `awaiting_human` with
  `park_reason="agent_run_limit"` — the durable state an issue is left in once it has spent every agent run its
  lifetime ceiling (`MAX_AGENT_RUNS_PER_ISSUE`) allows. It shares the pinned read the guards beside it take, so it
  costs no extra comment walk. The park itself, the sentence it owes, and the fields behind both are in
  [`labels-and-state.md`](labels-and-state.md#pinned-state). What hands the park an exhausted reading is the tracked
  spawn boundary itself ([The agent-run circuit](labels-and-state.md#the-agent-run-circuit)), never a stage handler:
  the ledger is read where a run is about to be spent, so this hold is what a park taken there leaves behind.
- **Why here and not in a stage**: the issue this is about is one *every* handler below would touch, and each in a
  way that is right about some other park. `awaiting_human` routes `implementing` to a resume on the next trusted
  reply, the conversation stages to the answer their agent asked for, and the spent-budget holds to a command that
  buys another attempt. None of those buys back a run, and a lifetime total is spent once — no window elapses under
  this park — so it is held once, ahead of the table, rather than taught to thirteen handlers. The one command that
  answers it is asked in the same place and for the same reason: the ledger is spent by every role at every stage,
  so there is no one handler a human would say it on.
- **Where in the order**: behind the two guards that RUN rather than merely answer — a cancelled cycle's own ending
  and the restart an operator authorized — because both are endings rather than work, and a park that outranked them
  would leave each owed for as long as the issue is stopped. Ahead of everything else, including the
  live-adjudication and reuse guards.
- **What it does**: replays the sentence the park still owes (nothing below it runs to say one, so a notice a refused
  post or an unreadable thread left owed would otherwise stay owed for good), logs the hold once per dispatch,
  records a `standing` phase on the `agent_run_limit` event stream, and returns before the label's handler is
  reached. A park already explained says nothing more, however many dispatches meet it.
- **Work that has ENDED steps past it**, on the grounds the hold is a question rather than a filter: what an ending
  reaches below is a terminal that finishes the issue rather than a road that spends anything on it, and the park is
  permanent — a lifetime total buys no clock — so an ending this hold refuses is one nothing else reaches. Two facts
  say so and the free one is asked first. A closed ISSUE the object in hand already shows (the poll's own reading
  counts beside it). The PULL REQUEST the record names is the half it cannot: a merge leaves the issue open until a
  stage terminal reads it, and a close nobody merged leaves it open for good, so `implementing`, `validating` and
  `documenting` — which drain both endings at handler entry — would never get to. That reading costs a request per
  parked issue per dispatch and fails *open*: a remote that would not answer leaves the hold where it was.
  Nothing it lets through can spend a run either: the circuit every launch goes through reads the same ledger and
  refuses on it, so what a lifted hold buys is the terminal and nothing else.
- **The one thing that lifts it** is a trusted `/orchestrator add-agent-runs N` (`workflow/engine/run_grant.py`, over
  the request `workflow/engine/run_grant_request.py` reads out of the thread for it), read off the unread thread of an
  OPEN issue once the park's own sentence has been said, and nowhere else — the ended-work exemption above is asked
  first, since what an ending reaches is a terminal rather than a road that spends anything. A thread this tick
  could not read is a park held one more poll: silence buys nothing.
  Valid — an exact positive whole number no larger than `MAX_RUNS_PER_COMMAND` — it persists an allowance of exactly
  `used + N`, takes this park down and puts back the park the refused launch was on (`agent_run_limit_displaced`),
  consumes the batch it read plus the acknowledgement it posts (and nothing that
  arrived in between — the boundary is derived from ids this tick observed, never re-read off the thread), records
  `granted`, and lets the SAME tick reach the stage handler, since the run a human just paid for is the one the
  issue was stopped for. A batch that begins below the park's own notice is the exception: those are replies a
  refused resume had frozen, left unread by the bounded notice and by the grant, and the grant's own tick is that
  resume, run on them from its own frozen batch.
  Anything else leaves both counts untouched: a malformed, zero, negative, or excessive
  request earns one marker-scoped receipt and a `refused` phase under a park that still stands, and an untrusted one
  is answered with nothing at all. The fields, the markers, and the ordering are in
  [`labels-and-state.md`](labels-and-state.md#pinned-state).
- **The one exemption is work that has ENDED**, and it covers two facts rather than one. What an ending reaches
  below is a terminal — the merged, rejected, and human-closed finalizers, and the cleanup sweep that settles a
  generation ledger — and each of those ENDS the issue rather than spending anything on it, so refusing them would
  leave a spent issue permanently mid-ending: a pull request nothing finalizes, a receipt nobody posts, a ledger no
  sweep settles. A closed ISSUE is the free half, and the poll's own closed reading counts beside the object's, since
  an issue closed when it was enumerated is one the tick was routed on the strength of. The recorded PULL REQUEST
  having merged or closed is the half the issue's flag cannot show — described above, read fail-*open*, and asked
  **ahead of** the command below, since reading that command mutates and nothing a human has already decided should
  buy runs it will never spend. What it means turns on the **label** the tick was routed on: a settled `discussion`
  plan is carved out on `workflow:implementing`, where merging one is the agreement that licensed the build, and
  nowhere else — `discussion` itself drains that same pull request through its own terminal.

## The developer-report transaction (every dispatch)
- **Where it sits in a report's life**: the stations every road's report passes — who writes and who publishes it,
  its identity and location, ready versus verified, the evidence, this recovery, review-subject freshness, and the
  round each road spends — are laid out end to end in
  [the developer report lifecycle](../workflow/conversations.md#the-developer-report-lifecycle).
- **Trigger**: `_record_stops_the_tick` on any issue whose pinned comment carries `developer_report_pending`. The
  owner is `workflow/engine/report_transaction.py`; the record it reads is described under
  [pinned state](labels-and-state.md#pinned-state).
- **Why it is here rather than in a stage**: the record is durable and the publication that follows it is not, so a
  tick that dies in between leaves an issue whose pinned comment says a report is owed and whose pull request does
  not carry it. Nothing on the stage that recorded it would go back for that — the handler spawns a reviewer,
  resumes a developer, or reads a pull request it believes is up to date, while the report the next reviewer needs
  sits in a record nobody is reading.
- **What a stage does first**: the publication that records a transaction also tries to complete it, on the tick it
  pushed, over the world it has just proved for itself — the initial implementation delivery is the road that does
  (`_handle_implementing` below). The fix loop on an open pull request binds its report on the tick its push lands, or
  at once for a report alone, and completes it by calling this very reconciliation there rather
  than posting on a proof of its own — a requirements-drift resume (the
  [user-content drift](#user-content-drift-detection) routing, `workflow:resolving_conflict`'s included) and a
  reviewer-requested round on either side of a park
  (`_handle_validating`'s `changes_requested` arc and `_handle_fixing` step 9) both do, with
  `_handle_validating`'s report hold behind them for a delivery a later push carried. The rewritten-head report
  refresh that hold runs (`_handle_validating` step 3) does the same with the report alone it asks the developer for,
  binding and completing it on the tick it records it. So this reconciliation finishes the ones
  that did NOT complete there: a post GitHub refused or never confirmed, a process that died in the window, a
  settlement whose write was lost.
- **Where in the order**: behind the pause (the dispatcher's hard-skip screen, one level up in `_process_issue`),
  the restart and cancellation guards, the agent-run-limit hold above, the live-adjudication refusal, the
  outstanding-publication reconciliation (`late_reconcile._reconciles_published_work`), and **both** readings of
  the auto-rebase anchor — the one ahead of that reconciliation and the one asked again behind it; ahead of the
  reuse guard below it and the stage handler. It is last of the reconciliations because its own evidence asks
  whether the commit the report is about reached the pull request — and a candidate the size gate froze and never
  counted is exactly the case the reconciliation above settles, so asking first would read a commit mid-gate as one
  whose code was never published and stand down every tick. The second anchor reading is the other half of the same
  boundary: a pair settled by the leased push it earns leaves the pull request carrying the replay with the anchor
  still pinned, and a report published between the two would go onto work no recovery has finalized while its own
  evidence proved that world sound. Terminal work is not a guard above it: this owner asks that itself, below.
- **Work that has ended is handed straight back**, ahead of every reading and without a write, and it is asked two
  ways. A **closed issue** is one a human ended, and the stage terminal that drains one runs *behind* every dispatch
  guard. A **`done` or `rejected` label** is the other, and it has to be asked here rather than left to the
  dispatcher: the handler table resolves a terminal label to no handler at all, so the no-op behind this guard
  protects nothing — an open issue somebody has already marked finished would otherwise publish a report and record a
  handoff on its way to that no-op. Either way the record, like the branch and the debt beside it, is left exactly as
  it stands — and for the reopen that may yet make it live again. A `paused` / `backlog` issue never reaches this
  guard at all: the hard-skip screen is one level up, in `_process_issue`, and returns before the routing that runs
  the dispatch guards.
- **What it proves before completing anything**, in this order: the pull request the record NAMES, read by its
  number, still open, on the recorded branch, whose head is in this repository and is standing on the recorded
  commit; then a checkout on this host, clean by a `git status` that actually ANSWERED, standing on that commit; then
  the recorded branch fetched, and one divergence reading against the tip it resolves showing no unpushed commits, no
  remote that has moved on, and a tip that IS the recorded commit; then the code-publication receipt read as one sound
  group and then naming both that commit and that pull request; and finally the issue's requirements still hashing to
  the revision the developer run was handed. Nothing is inferred from an absence, and no reading here answers with an
  exception: computing the requirements revision walks the issue's comments, so a request that raised would otherwise
  leave the guard through the dispatcher and out of the tick instead of holding.

  **The pull request is selected by its number, not searched for by the commit.** A number is unique in a repository
  and a search is not: several pull requests can stand on one branch carrying one commit — a replacement opened
  beside the original, a second thread raised against another base — and a search answering with whichever it
  reached first would refuse this transaction on every tick for the rest of the issue's life while the pull request
  the record names sits open on the very commit the report is about. What a search did prove and a bare number does
  not is that the work actually got there; that is not lost, because the head read off this object has to *be* the
  recorded commit, which is strictly more than carrying it. The branch and the head repository are asked of the same
  object, since a fork carries this repository's ref names over somebody else's commits. Every read of that
  reading sits inside the hold boundary and not just the fetch: the client resolves its repository lazily, and the
  state, head ref, head repository and head SHA read off the pull request are lazy too, so on a worker that has not
  completed the object each is a request that can fail.

  **The pull request is read first, and that is a correctness rule rather than a cost preference.** The terminal that
  drains a merged or closed pull request runs *inside* a stage handler, which is behind this guard — so any refusal
  taken before the pull request has been looked at can hold the tick in front of that terminal. A merge whose branch
  GitHub auto-deleted is the case that bites: the fetch the remote reading takes fails, the tick holds, and an issue
  whose work is finished never reaches the handler that would finalize it. Asked first, a finished pull request
  retires the transaction and the stage runs. The ending is asked before the branch and the head for the same reason:
  a pull request that is over needs no report whatever those now say.

  Two of those are easy to under-ask and are worth naming. *Standing on* the commit is what licenses a report, not
  carrying it: a head pushed past it leaves the commit in history while the work under review is no longer what the
  report describes. And the receipt is asked as a GROUP before either member is believed, because
  `_record_publication` writes all three keys on every receipt and clears all three on none — read member by member, a
  partial group answers "no receipt" and the transaction would defer forever instead of naming the field a human has
  to repair.
- **Outcomes**:
  - **Settled** → for a publication, the report is posted as one comment scoped by the transaction's receipt (so a
    retry finds what an earlier attempt landed instead of repeating it, including the post whose response was lost),
    and the comment id it landed as is required: this road publishes a *comment*, so a location with no comment id
    would be the pull request's description — a different place holding somebody else's text — and recording that
    would be a false "exact" location for every later reread; for a verification, nothing is posted and the named
    location is re-read, requiring both a trusted author and content that still hashes to the revision verified.
    Either way one `developer_report_current`, one `developer_report_handoff`, the consumed watermarks, the
    route's round / bookmark fields, and the debt the record left land in a single write with the drop of the
    pending record. The handoff also names the workflow LABEL the issue was carrying as that write landed, read off
    the issue this road re-reads for the requirements rather than off the copy in hand — a human who relabelled
    while the developer ran is invisible there — and fail-closed, since the labels are a lazy read and a settlement
    raising out of that line would leave the report published with the transaction still outstanding. The
    `fixing_round_settled` mark is REPLACED by the same write, never merely left: retired first and put back up only
    where this record's own frozen spends carry it, so a mark an earlier settlement raised elsewhere cannot outlive
    the handoff it was about. That write is
    composed whole before any of it is installed, so a settled record its own writer refuses lands none of itself
    rather than dropping the pending record beside a report nothing says the pull request carries. Reaching that
    refusal is a record this build did not write, so it is logged at ERROR and the tick is held with the
    transaction still owed rather than retried quietly. The write is the
    [guarded commit](labels-and-state.md#pinned-state) `workflow/engine/report_settling.py` lands over the comment
    read afresh behind the post or re-read: it owns exactly what it settles and is decided on every report record,
    the handoff, the debt and park it may retire, the undescribed-work flag, and the pull request, branch and
    code-publication receipt the evidence proved, so another road's evidence, verdict or usage written meanwhile
    survives, a watermark and the comment-id ledger keep both roads' moves, and anything it was decided on that moved
    refuses it with nothing written — see **Held** below. The tick otherwise carries on to the handler.
  - **Held** (tick stops, nothing written) → a reading nobody could take, and only that: an unreadable worktree or
    head, a fetch that failed, a recorded pull request that would not read, an issue whose comments would not read
    (the requirements revision is computed from them), an issue that would not re-read for the settlement's own
    last look at those requirements, a post or re-read GitHub did not confirm
    (`ReportPresence.UNCONFIRMED`), and a verification whose AUTHOR would not read — `user` comes off the object
    GitHub handed back and `login` comes off that, so either is a request that can fail, and a failure is nobody
    saying rather than an author this deployment refuses. Beside them is the one damaged reading that holds rather
    than parking: a code-publication receipt group with some of its members and not others. And beside those, the
    settlement's own guarded commit or its preparation where it did not land over the comment the tick read — a
    record it was decided on or a field it writes moved by another road, a comment replaced or no longer parsing,
    an edit refused as moved, a final candidate that would leave the reviewer round or the fixing hand-back behind it
    no room — or where it went out and was never confirmed: the tick's state is withheld, so nothing behind it is
    written, and nothing is posted where the preparation refused. Any refusal below that comes *after* the post or
    re-read went out — a reading short of PRESENT, an untrusted author, requirements edited under it — asks the
    comment once more first, and is held here instead where another road wrote it meanwhile: the tick's state is
    withheld, so the stage behind writes nothing back over that road's evidence, verdict or newer record. The next
    tick asks again — a report already posted is found by its receipt rather than posted twice, and a settlement
    that landed after all leaves nothing owed, its round spent and its readers advanced once. A pull
    request nobody could read holds *without* parking anything: the damage is still damage, but whether it stands
    in front of a terminal is exactly what could not be established, so the tick that can establish it is the one
    that decides.
  - **Stood down** (tick carries on, transaction still owed) → every *definite* refusal. The structural ones: a
    dirty tree, a head that moved, a checkout on another host, a commit the pull request does not carry yet, a
    publication receipt naming another commit or another pull request, a recorded pull request on another branch
    or built from a fork, requirements a human edited — asked with the rest of the evidence, and once more over the
    issue read afresh after the post or re-read and before the settlement is written, since that request is long
    enough for an edit to land under it. And the ones about the report itself: a comment of ours under
    this receipt that no longer renders as the report (`CHANGED` — somebody edited it), a verification whose
    location no longer holds anything (`ABSENT` — somebody deleted it), and a location whose author this deployment
    does not trust. And one about the pinned comment itself: a settlement that would no longer fit it. The room was
    measured when the record was accepted, but a transaction that stands down lets the routes behind this guard run
    and each of them writes to that same comment, so what was reserved can be spent by work entitled to spend it —
    and the check is taken again here, *before* the report is posted, since a refusal after it leaves a comment on
    the thread that no write can ever record. It is taken as the settlement's own guarded commit PREPARED over the
    comment read afresh, with the same measurement as its check, so room another road gave back since the tick read
    the comment is room; a comment too full that is still the one the tick read stands down here, while one another
    road moved meanwhile holds (**Held** above). The commit behind the post is held to the same room over its final
    candidate, with the settled records as they land — never more than the measurement before the post — so another
    road that filled the comment during the post refuses it with the transaction kept, rather than leaving the
    hand-back a fixing round's settlement owes no room. Each of those is cleared by a route *behind* this guard, or by
    a human on the thread — the publication gate that pushes the commit, the drift resume that answers the edit, the
    dirty-worktree park, the park whose clearing gives the room back — so holding them would strand the issue behind
    the very handler that fixes them, or in front of every route it has for as long as one edited comment stands.
    Nothing is ever posted twice on that path: the post is scoped by the receipt and only an `ABSENT` reading
    reaches one. One refusal that would
    otherwise park stands down here as well — a damaged record on an issue another route has already parked; see
    **Parked** below.
  - **Retired** → the recorded pull request has merged or closed; the record is dropped rather than retried forever.
    Reading by number is what makes this reachable at all: a thread somebody force-pushed off the recorded commit is
    invisible to a search by commit whether it is open or closed, so an ended one would otherwise stand down on
    every tick for the rest of the issue's life over work that is finished. The drop is a guarded commit decided on
    every report record, the handoff and the park reason, owning only the pending record and this owner's park: what
    another road wrote meanwhile survives, a newer record or park it wrote is never dropped with the one the tick
    read, and a drop that did not land, or landed unconfirmed, holds the tick.
  - **Parked** (`park_reason="report_record_damaged"`) → the issue CLAIMS a transaction this build may not act on,
    or claims a settled record beside it this build did not write. Every one of these is judged *before anything is
    settled* and *behind the pull-request reading*, and both halves of that matter. Before settling, because both
    companions are records a settlement writes over: a damaged current report waved through as an absence is
    replaced the moment this transaction settles — after its report has been posted, which is when the evidence an
    operator would have repaired it from is gone. Behind the pull request, because a park is the one answer the
    tick that takes it cannot take back: taken over work that has already merged it strands the issue in front of
    the terminal that would have finished it, for as long as the damage stands. An **ending retires the
    transaction whatever the records beside it say**, and nothing is written over them on that road, so the
    evidence an operator would repair them from survives the drop. Five shapes reach the park.

    A **pending record that will not read** — the one answered *ahead* of the pull request, and the only one that
    can be, since a record nobody can read names no pull request to ask an ending of. A **settled record claimed
    and unreadable** — `developer_report_current` or `developer_report_handoff` on the comment in a shape its own
    reader refuses; the first waved through as an absence is quietly replaced by this settlement, and the second
    is a completed transaction nobody can recognize whose report is then published a second time. A **settled pair
    that contradicts itself** — both records readable, naming two pull requests, two revisions or two commits;
    they are written in one write off one pending record, so a pair that disagrees is one nothing here produced.
    That one is asked of the pair alone, with no reference to the transaction in hand or to any receipt, because
    under a *previous* transaction's receipt nothing else ever would: such a pair is never compared against the
    record being reconciled, so a disagreement left standing would be replaced by the very next settlement rather
    than seen. A **handoff carrying this transaction's receipt while disagreeing with it** — believed on the
    receipt alone it would drop a record whose report was never published. The current report beside it is held to
    the pending record's **whole subject**, not just the pull request and revision the handoff can also carry,
    since a current report naming another branch, repository or requirements revision would otherwise read as this
    transaction's completion — and to the **content** as well, which is the only half of a settled record that says
    which report actually landed: a publication to the digest of the text it carries, a verification to the exact
    location and revision it read, both of which a settlement copies across unchanged. The KIND of place travels
    with that content. *Which* comment id a publication landed under is not asked — that id is GitHub's answer to a
    request the transaction had not made when it was recorded — but that there **is** one is, because this road
    posts a comment and refuses to settle a post whose comment it could not read. A `null` comment field is the
    pull request's *description*, which a verification legitimately records (it re-reads the pull request's own
    body there) and a publication never writes; accepted on the digest alone it would drop a pending record with
    its report never published. A subject and a revision
    agree between a transaction that published this text and one that published some other text at the same
    revision on the same commit, so without the content a record whose digest and location belong to nothing this
    transaction did would read as its completion. And a handoff is believed only beside a current report at all,
    since the two land in one write and a handoff without one is a settlement that never happened. Last, a
    **record a newer current report has already passed**, which settled would replace the pull request's newest
    report with an older one.

    None of the five is a shape this build produces, so which record to believe is a human's question. Announced
    once and held silently thereafter; repairing the pinned comment, or clearing the field to abandon the report,
    resumes it with no agent run.

    A park **another route** already holds is never replaced, and no park of this owner's is taken beside it: the
    pinned flags are single, so writing over an `agent_timeout` would discard an obligation a stage is still waiting
    on — and the retirement below would then clear `awaiting_human` for a question nobody answered. That case
    **stands down rather than holding**, and the difference is whether either park is ever answered. What clears a
    foreign park is the stage handler *behind* this guard — the awaiting-human branch that reads the human's reply,
    recovers a transient park, or times one out. Held here, that branch never runs, so the park never clears, so
    `awaiting_human` stays set and the next tick holds for the same reason: both parks stand for the life of the
    issue and neither the damage nor the recovery is ever announced. Stood down, the handler runs and answers what
    it is waiting on, and the tick after that park clears is the one that takes this owner's park and announces the
    damage. Nothing is lost by waiting for it — the issue is already awaiting a human, and the record is untouched
    and still unreadable when that park goes.

    This owner's own park is its to retire as well as to take: both endings clear `awaiting_human` and the reason,
    because a park nothing takes back leaves every stage behind the guard reading the issue as waiting on a reply
    nobody owes. No other owner's park is ever touched — each of those belongs to a stage still waiting for what it
    asked for. The retirement is the drop's guarded commit, so it lands beside whatever another road wrote since the
    tick read the comment and never over a record or park that road wrote in its place.
- **Replay**: a handoff already naming the transaction's receipt drops the record without publishing again, which
  is the window where the settlement landed and the process died before the drop. Watermarks only ever move
  forward and the round is applied from the pair the transaction froze, so a replayed settlement counts nothing
  twice and swallows no comment posted since.
- **Output**: no label change, ever. This owner publishes a report and settles a record; which stage runs next is
  the handler's.

## The verification-evidence transaction (every dispatch)
- **Trigger**: `_record_stops_the_tick` on any issue whose pinned comment carries `verification_evidence_pending`,
  directly behind the developer-report transaction and ahead of the reuse guard. The owner is
  `workflow/engine/verification_transaction.py`; the four records and the revision floor are described under
  [pinned state](labels-and-state.md#pinned-state). Its live producers are two. The returned-verdict disposition
  (`stages/validating/review_disposition.py`) records the transaction `review_claims.py` mints from a reviewer's
  declared commands beside its verdict, in the write persisting that verdict, and publishes it through this same
  reconciliation; the recovery of a verdict an earlier tick left waiting (`stages/validating/review_resume.py`)
  records no transaction. And the approval's squash records a carry-forward onto the head the squash published -- of
  the passing run the approval's verify gate made on the approved head, or else of the evidence its approval rests on
  (`stages/validating/squash_evidence.py`, see
  [`_handle_validating`](#_handle_validating-label-workflowvalidating)), in the write settling the squash's handoff,
  for the next tick's reconciliation to publish. An issue without the record passes through reading nothing and
  writing nothing.
- **Why it is behind the report transaction**: evidence answers for a review subject that names the developer
  report, so a report still owed is a subject about to move — the proof defers to it, and the report settles first.
- **Stands aside**: a closed issue, a `done` or `rejected` label, a hard-skip control label, or no workflow label at
  all. Nothing is published or dropped, so a reopen or a relabel finds the record as it was. The settlement asks the
  same again of the issue read afresh after the post, and writes nothing at all where it no longer holds.
- **Outcomes**:
  - **Settled** → the pull request (the one `pr_number` pins), branch, checkout, tested and target trees, configured
    context, the recorded review subject (`review_returned_subject` for a reviewer's account, `review_subject`
    otherwise), the settled report re-read at its location as a reviewer is handed it, the subject passing that reader's
    own rules (requirements the round was due, a report not stale against it -- a report older than a baseline that is
    the subject's own requirements is not stale, since only settling the reply that bought the round leaves one), and
    the requirements all PROVED; the
    artifact is posted (or found where an earlier post's response was lost: a comment of ours under its receipt that
    reads back, in its own format, as exactly this artifact -- identity, commands, transcripts, and digest -- whatever
    body the writer would give it now, and that comment is neither rewritten nor posted again); a carry that copied the
    current evidence's transcript names that source (`copied_from`, which a carried reviewer's account without one
    reads as damage and is dropped), which is re-read ahead of the post and again at the settlement and has to still
    be the current record, its artifact the one that settled and carrying exactly what was copied
    (`verification_current.copied_source_verdict`); the issue and the pinned
    comment are read afresh, the comment has to carry every bound record as the tick held it, the whole proof is taken
    again over them, and the artifact re-read at the comment it landed as has to be exactly this transaction's (edited
    or deleted meanwhile, it stands down); the comment is read once more behind those requests and has to still carry
    every bound record -- `review_approved_subject` among them -- as the proof read it (a subject removed or replaced
    meanwhile stands it down, the move kept); then one guarded commit (`workflow/engine/pinned_commit.py`), composed
    over that last reading, makes it current, moves the earlier current evidence into history as superseded, records
    the handoff, drops the pending record, and merges the artifact's id into the ledger -- laid over the comment read
    once more, which has to still carry every bound record as that last reading did, with every field the settlement
    does not own (a usage total, a watermark, another road's verdict or comment ids) kept as it reads then. The room
    for it was proved before the post: the settlement, staged at its widest with the artifact's ledger entry reserved
    against the ledger as it stands, is prepared over the comment read afresh, and a comment another road filled, or
    whose bound records moved, since the tick read it posts nothing.
  - **Held** → a reading nobody could take: the pull request, the fetch, the divergence, the report's location, the
    requirements, an unconfirmed post, or the issue, the pinned comment, or the artifact re-read before a settling or
    retiring write -- a pinned comment replaced or no longer parsing included, over which nothing is written -- or a
    settling commit that went out and was never confirmed. The next tick asks again, and finds either nothing owed or
    the same transaction to settle over the same artifact, with no second history entry.
  - **Stood down** → a moved head or branch, an absent checkout, an id that is not a commit itself, an unreadable or
    different tree, a moved configuration, a pinned `pr_number` naming another pull request, a report still owed (a
    delivery, a transaction, or an undeliverable park), a review subject absent, replaced, about another head than the
    target, or carrying requirements its round was not due, a report settled after the review, stale against the
    subject, or deleted, edited, or out of step with its handoff, an issue that stopped being live work during the post,
    edited requirements, an edited artifact, a bound record that moved on the pinned comment before or while the
    artifact was posted or under the settling commit, a pinned comment that moved under that commit's edit, or a
    settlement the comment no longer has room for, before the post or behind it. The transaction stays owed for the
    route that answers it, with the artifact's ledger entry committed alone where the comment still reads (a comment
    that entry finds unreadable, replaced, or no longer parsing holds the tick instead) -- save a
    carry onto a head it did not run on, which only an approval's squash records and nothing later makes answer again
    once refused: refused on anything but a reading nobody could take -- its proof ahead of the post, the source it
    copied edited, deleted, or no longer current (a publication retried over a lost response included), its own artifact
    found edited under its receipt, or the proof or either artifact re-read ahead of its settlement -- it is abandoned
    into history and the approval it was recorded for retired in the same guarded commit (`review_approved_subject`
    written `null`, `verification_carries`), so a context, a head, or an artifact put back afterwards moves no label
    over it. That commit is staged on the pinned comment read afresh -- at the settlement, the reading behind the proof,
    recording the artifact's ledger entry too -- and guarded by it: an approval, a transaction, or any other bound
    record another road moved under it refuses it with nothing written and the carry owed (at the settlement, the ledger
    entry is then committed alone), and every field it does not own -- a returned verdict, a usage total, another road's
    comment ids -- is kept as written. A bound record another road moved after the tick read the comment and before or
    during the settlement's proof refuses what the tick decided over rather than the carry: nothing is abandoned, the
    ledger entry is committed alone, and the next tick's proof decides over the comment as it reads then. Only the
    approval the carry was recorded for goes, spelled exactly as the carry recorded it -- one another road recorded in
    its place, of another subject or respelled, stands -- and it goes even where the comment has no room for the carry's
    entry, since that write only shrinks the comment: the carry then stays owed, under an approval nothing acts on, for
    a later tick to abandon.
    A carry left owed for its standing approval -- the settlement had no room, before the post or behind it, a record
    moved under it, or its commit did not land -- holds the squash handoff rather than letting it drop
    (`squash_evidence.carried_onto`), so the next tick with room settles it and moves the label, with no second report
    or reviewer.
  - **Retired** → a record whose revision a settled or retired record already carries (a replay its own handoff
    names, or one a restored comment brought back) is dropped without a second post or history entry; an unreadable
    record is dropped; a record whose pull request ended, past which a revision was spent, or beside a revision floor
    nobody can read is abandoned into history. Every retirement here is one guarded commit staged on the pinned comment
    read afresh, which has to carry every bound record as the tick held it, and guarded by that reading, owning only the
    records it retires: a transaction, a report or a report debt, a review subject, an approval, or a floor another road
    moved before that reading or under the commit -- or the same transaction retired there first -- stands it down with
    nothing written, so a transaction recorded meanwhile is never written away nor a revision indexed twice, while every
    field it does not own is kept as it reads then; a comment that will not read or was replaced holds. A retirement the
    comment has no room for, over that reading or the one the commit takes, writes nothing and leaves the record owed;
    one that went out unconfirmed holds, and the next tick finds the record gone or retires it again, with no second
    history entry. It never parks.
- **Relying on it later**: `current_evidence_verdict` proves the current record again for a reader -- no revision
  past it spent, its handoff, its artifact re-read at the recorded comment with the pass flag its commands earn, and
  then the whole proof above -- so newer evidence posted and never settled, a deleted or edited artifact, or a flag it
  contradicts is not reported as current. Its readers are three: the approval's proof over the evidence its verdict
  names (`stages/validating/approved_evidence.py`); the squash handoff, which proves a settled carry whole again before
  the label moves over it (`stages/validating/squash_evidence.py`); and `stages/validating/review_evidence.py`, which
  hands a reviewer the current evidence only where the record is bound to exactly the subject that reviewer is
  handed -- pull request, head, requirements, and the complete report by revision and digest -- and it proves current,
  then re-reads the artifact for the prompt and holds it to the record again, so an edit between the two reads hands
  nothing. Anything
  short of that, a reading nobody could take included, hands nothing and holds no round, logged with its own reason --
  no record or one that will not read, another subject, the proof's refusal, or a prompt read that could not be taken
  or found the artifact gone or changed. Every reviewer round asks that reader once its launch has recorded the
  subject, and the prompt quotes what it hands over.
- **Carry-forward**: `workflow/engine/verification_carry_forward.py` decides whether current evidence answers for
  another head -- never the one it already answers for -- and only on the full tree identity of that head and of the
  tested commit, read from this repository, and an unchanged configured context, while the evidence being carried is
  still the latest and published (re-read as above, on the pull request standing on the new head). The review it then
  answers for is either a review subject recorded about the new head, or the review the evidence already answers for,
  unchanged -- still the applicable record exactly, about the tested commit -- where that is the subject
  `review_approved_subject` covers: the approval squash's own rewrite, past which no reviewer is handed the new head.
  The approval squash asks for that second way alone, so a review recorded about the new head since -- a later round,
  with whatever report and requirements it was handed -- refuses its carry rather than being adopted. The proof
  accepts a subject about the tested commit for exactly that case, holding the tested commit and the head alike to the
  tested tree. Patch ids, topic diffs, and a rewrite's name are never read. What it licenses is a new
  transaction naming the tested commit and tree unchanged, the new head as its target, and the source artifact's own
  transcript, which this reconciliation proves whole before it is published or current; the artifact says, in its
  visible lines, that the head is an equivalent-tree target the commands never ran on. A local verify run bound to
  the head it tested (`verification_local_runs.py`) is carried by the same rule (`local_run_decision`) save the
  artifact it never had: orchestrator-executed, answering for `review_subject`, with its own transcript. A refusal
  comes back as the proof's own verdict: a pull request or artifact nobody could read HOLDS, and every other refusal --
  an unreadable tree included -- defers. The one stage that asks is the approval squash
  ([`_handle_validating`](#_handle_validating-label-workflowvalidating)).

## The rewritten-head report debt (every dispatch)
- **Trigger**: `_record_stops_the_tick` (`workflow/engine/dispatch_guards.py`) on any issue whose pinned comment claims
  `developer_report_rewrite_debt`, readable or not, directly behind the verification-evidence transaction and ahead of
  the reuse guard. The record is described under [pinned state](labels-and-state.md#pinned-state) and owned by
  `workflow/engine/report_rewrite_debt.py`.
  [`_handle_resolving_conflict`](#_handle_resolving_conflict-label-workflowresolving_conflict) records one for every
  head its own push rewrites, and the per-tick base refresh one for every clean auto rebase whose push lands, before
  it clears its attempt or routes to `workflow:validating` (`workflow/engine/rewrite_finish_debt.py`) -- its crash
  recovery's retry of a replay nothing published and its finish of a push already landed included (see
  [Base refresh](labels-and-state.md#base-refresh)). The authorized settlement of a replay a late generation took over
  from its auto rebase records one for the push it makes, before its label (`late_replay_debt.py`).
  An issue without the record passes through reading nothing.
- **Holds**: `workflow:documenting` and `in_review`, the roads past an approval that would carry a head no report is
  about to the human who merges it. Nothing is written or posted; the claim is left for validating, and the hold is
  logged once a tick.
- **Runs**: every other label -- `workflow:validating` above all, whose report hold
  ([`_handle_validating`](#_handle_validating-label-workflowvalidating) step 3) holds the reviewer against the debt,
  resumes the developer for a fresh report of the rewritten head with no human reply, and pays the debt once a
  published report of the head the pull request stands on settles -- and any issue whose debt is paid (`null`) or was
  never recorded.
- **Why it sits here**: behind the auto-rebase anchor readings, since a replay no recovery has published is no head a
  debt can name yet, and ahead of the handler it keeps off.
- **Approval-squash lineage**: a settled report of the approved commit an approval's squash replaced is of neither
  head the claim names, so it pays nothing and is owed nothing on its own. `lineage_verdict`
  (`workflow/engine/report_squash_lineage.py`) proves whether this orchestrator squashed that commit into the head the
  claim replaced, and the report hold asks it only where that is the one thing left to know: a readable claim naming
  the pinned pull request, the head it stands on, and the branch the issue pins, whose settled report is of neither
  head, on the claim's pull request and branch, and written against the current `user_content_hash` (`squashed` on
  `RewriteDebt.owes_a_refresh`). PROVED makes that claim owed a fresh report of its `rewritten_head`, once the
  report re-reads intact at its location; DEFER leaves the report to the reviewer road's refusal; HOLD holds the
  reviewer with no developer run. It is PROVED only where the claim reads whole and names the pinned pull request,
  the head it stands on, and the settled report's pull request and branch, and a recorded evidence carry -- which
  only the approval squash writes ([evidence transaction](#the-verification-evidence-transaction-every-dispatch)) --
  is of that settled report exactly: the commit it is about, its pull request, revision, digest, and requirements, on
  the same repository and branch, onto the claim's `previous_head`. The carry is read owed, current, or from history
  whatever retired it, since the question is what the squash did rather than whether its evidence is current, and
  both commits read again in the checkout (`verification_world.tree_of`) have to be the tree it recorded. Equal trees
  alone, ancestry, and the `late_collapse_*` recovery fields prove nothing; so does a claim, report, or carry that
  disagrees on any member, or a commit read as another tree, each DEFERRING. A checkout not on this host or a commit
  git would not read HOLDS. The proof writes nothing: `developer_report_current` keeps the commit it was written
  about, and the claim keeps its fields, its actual replaced head, and its retargeting, so a claim a later base
  advance retargeted still proves for the latest head it names.

## The seed hold (every dispatch, ahead of the reuse guard)
- **Trigger**: `_pinned_state_refuses` (`workflow/engine/dispatch_guards.py`) on any issue this orchestrator opened
  whose body carries an ordinary split's child receipt, under any label but `done` and `rejected` — the unlabeled
  pickup included — directly behind the agent-run-limit hold and ahead of the step aside a live adjudication takes
  on `workflow:decomposing`, so a child adjudicating an oversized candidate of its own is held too. The owner is
  `stages/decomposition/split_seeds.py`; the receipt and the seed it is held to are described under
  [pinned state](labels-and-state.md#pinned-state). It is read off the body and the pinned comment the dispatcher
  already holds, so it costs no request, and an issue a human opened, or one with no receipt, passes through.
- **Holds**: a child whose seed is not what the last whole receipt in its body owes it — no `parent_number` naming
  exactly that parent, none of an owed `late_ancestry_*` group, a group partial, rewritten, or naming another place in
  the lineage, any group on a child owed none, or a pointer at a snapshot other than the one that split preserved, or
  half of one. It parks `replacement_lineage_unproved` once and returns before the handler; a park already standing
  holds it silently, and a reply is no seed. A pinned comment that will not parse is held with nothing written, since
  the park's own write would replace whatever it carries.
- **Runs**: a child whose seed is whole — written by the split or by its parent's recovery, either of which clears
  `awaiting_human` in the same write, or by hand — and one whose pointer its own reuse guard dropped, ref and commit
  together, after its ref was released. A restart an operator authorizes on the child's own cancelled cycle keeps the
  seed, so the restarted child runs on its next dispatch.
- **Why it sits here**: a hand relabel or an edit's reroute reaches the child's own handler without its parent's walk,
  and every road that could run it — its own decomposition, its adjudication of a candidate of its own, `ready`,
  `implementing`, pickup — would read the record as an issue no split made, or one at another depth, and mint
  whatever it starts there. Ahead of the reconciliations and the reuse guard, since a seed the reuse guard would
  otherwise ask the remote about is refused before it is believed; behind the restart, the cancellation ending, and
  the agent-run-limit hold, which owe nothing to a lineage nobody proved.

## The reuse guard (every dispatch, ahead of every handler)
- **Trigger**: `_route_issue_to_handler` on any issue whose pinned ancestry still names a snapshot ref. It shares its
  pinned read with the live-adjudication guard beside it, so it costs no extra comment walk. Both step aside for
  `workflow:decomposing` — an issue under adjudication is working from its own candidate, not an ancestor's snapshot —
  but only once that read PROVES the adjudication is the issue's own. The label alone proves nothing: a consumer
  closed while it was being decomposed comes back with the label exactly where it was and no generation at all, and
  waving it through would spawn the decomposer against the reuse instructions in its body naming a reclaimed ref.
- **Why here and not in a stage**: the issue this is about is one no handler would touch. A consumer that ended wears
  `done` or `rejected`; reopening leaves the label exactly where it was, and both are terminal no-ops below. Asking
  before the table also means a relabel straight to another stage cannot route around it.
- **Why the child decides**: the owner that reclaimed the ref cannot make this safe from its side, for the reason
  above. Evaluated on the child's own dispatch there is nobody to race: whatever a concurrent writer did to the
  record, the child reads it again and decides again.
- **What it asks, in order**: first the **receipt** — the comment the reclamation posted on this child, marked with
  the owner, cycle, and generation its ancestry names, and authored by the orchestrator's own account. That is the
  authoritative answer, because it records what *happened* rather than what a later reading suggests: a local mirror
  nobody got round to dropping, or a ref somebody pushed again at the same commit, would both make the world look
  untouched while the guarantee the child was given — that its candidate provably came from one adjudication — is
  gone. It costs one walk of the child's own thread per dispatch, paid only by issues a split created. A thread that
  could not be **read** is not a thread with no receipt on it, and the two may not be collapsed: everything asked
  after this can look untouched while the answer that outranks it sits unseen, so an unreadable thread **holds** the
  dispatch there and then.
- **And when no receipt landed** (a crash, a thread it could not post to): this host's own mirror, which costs
  nothing on the wire. That shortcut is bought by the order a reclamation runs in rather than assumed of it — the
  mirror is dropped *before* the remote ref is touched at all, and a mirror that cannot be proved gone refuses the
  reclamation instead of being logged past, so a mirror still present says nothing has been reclaimed (a ref deleted
  by hand is the one exception, and a child can still read the candidate out of the copy it left). "Still present" is
  read as an identity, not an existence: the copy is a ref in the object store every agent's worktree shares, so it
  is resolved and compared against the exact commit the ancestry records. A copy standing at anything else is
  somebody's write — it says nothing about the ref on the remote and is not a candidate to work from — and goes to
  the ask like an absent one.
- **The shortcut is conditioned on the pointer, not assumed of the world.** It is taken only where the ancestry
  carries `late_ancestry_mirror_first`, the stamp a split writes onto every pointer it seeds. A pointer written
  before that ordering existed belongs to a world where the remote ref went first and the mirror came down
  best-effort afterwards — so a surviving mirror there is as likely to be the residue of a finished reclamation as
  proof one never started, and the child pays the read-only ask instead of trusting it. Nothing migrates: the stamp
  is written by the binary that would do the reclaiming, so its absence is the whole question answered.
- **What the ask decides.** A mirror that is gone (or a pointer with no stamp) is worth one read-only `ls-remote`
  for the exact ref and commit the ancestry records, and the three answers are three different verdicts. `absent` is
  the reclamation this child was not told about, and it parks. `mismatch` is the ref carrying somebody else's commit
  — not the candidate this child was promised, and not something to start work against either — so it parks too,
  under its own reason (`late_snapshot_repointed`) and its own comment; nothing here re-points or deletes that ref,
  exactly as the reclamation refuses one for a human. `unreadable` is an outage, which is evidence of nothing: the
  dispatch is **held** — no park, no comment, no write, and the same question on the next dispatch — because
  parking every late-born child through a rate-limit window would be a self-inflicted stop, while continuing would
  start an agent against a ref nobody could vouch for.
- **A child with no recorded ancestry at all** is not automatically an issue of no lineage. The split records a child
  on the parent's ledger *before* it seeds that child's ancestry — a child on GitHub the parent does not record is a
  child nothing would come back to — so a seed that failed leaves an issue whose **body** carries the split's own
  marker and whose pinned comment carries nothing, while the reclamation still counts it as a consumer and still
  leaves its receipt. The body is what decides whether to look, and it costs nothing: the dispatcher already has the
  issue, and every issue no split created stops there without a request.
- **A body marker is corroborated, never believed.** It is the one lineage claim in this workflow that comes out of a
  field the world can write, while everything it competes with is authenticated — a pinned comment only the
  orchestrator writes, a receipt checked against its author. So the **owner's own generation is read fresh** and has
  to vouch for the claim: the same `late_cycle_id` and generation counter, and this issue's number among
  `late_consumers`. A claim it does not vouch for is a claim about nothing and the guard steps aside — parking an
  issue, comment and HITL mention and all, on the strength of a sentence somebody typed into its body is the
  denial of service this check refuses, and it is also the honest answer for the *other* crash window (a child
  created before its number was recorded), since an owner may not reclaim a ref while its own ledger can be short one
  child. A record that could not be read, one whose consumer list this binary cannot type, and one naming no
  candidate are a different answer: the claim may be true and this tick cannot tell, so the dispatch is **held**.
- **What a vouched claim buys** is the whole pointer the failed seed never wrote — the ref the identity mints, and
  the commit the owner recorded preserving — so the ask is the same ask the recorded shape makes: is *this* candidate
  still obtainable. It has to be asked, because the receipt cannot cover the window it is posted after: a ref is
  deleted first, so a silent thread is what that window looks like, and so is a thread this tick could not read. The
  verdicts are the recorded shape's four, re-pointed included. The park writes back the lineage the body claims —
  never the pointer, which was assembled out of the owner's record rather than out of anything this issue holds —
  which both repairs what the failed seed owed and is what stops the question being asked again.
- **What a refusal does**: drops `late_ancestry_snapshot_ref` / `late_ancestry_snapshot_sha`, parks the issue
  (`awaiting_human`, reason `late_snapshot_reclaimed`, or `late_snapshot_repointed` where the ref survived and its
  commit did not) with a comment naming the ref and the owner, and
  returns before the label's handler is reached. Dropping the pointer is what makes the guard cost nothing on every
  dispatch after — and both writes are taken on the issue's own dispatch, so no second writer can lose them.
- **Anything not `reconciled` holds the terminal**, ref and branch alike — a `retained` ref included. There is no
  reading under which an object still on the remote is settled, and an umbrella closed over one is an object nothing
  would ever come back for: the parent is `done` by then and no pass revisits it. Keeping the label *is* the retry,
  and the reason it is held is logged on every dependency poll that holds, since a hold attempts nothing and so
  writes and emits nothing. An opaque *resource* ledger blocks outright, and so does any ledger entry on a record
  whose cycle identity
  is damaged, a bare `late_consumers` list included; an umbrella with no recorded generation and no ledger owes
  nothing and answers without a write, and one whose record a retirement left (`late_retired_cycle_id`) is held only
  on a ledger this binary cannot read or an entry its ledgers still owe. An
  opaque *consumer* ledger is refused separately, because the two are preserved and written separately: it is what a
  snapshot's proof would be taken from, so the ref stays — while the superseded branch, which owes no consumer
  anything, is deleted and retried as usual.
- **Output**: terminal `done`, OR a sibling unblocked, OR a HITL park, OR a held terminal (something still owed), OR
  a no-op.
- **Two more questions ride the same read**, and both are asked FIRST. One is an owner whose cycle a close already
  ended and whose ending has not been written. Cancellation is irreversible within a cycle, so a human who reopens
  the issue does not get that cycle back, and *every* label it can be wearing — the unlabeled state included — names
  a handler that would act on the issue rather than settle it. That guard runs the cleanup below, reaches no
  handler, and writes that cycle's `rejected` ending from wherever the graph declares the edge — or, from the
  unlabeled state, only where the record shows the terminal was never applied. The other is the **restart** an
  operator authorizes by taking that `rejected` back off
  ([labels-and-state.md](labels-and-state.md#late-generation-state)), which is asked one step ahead of it: a restart
  writes its target label before it retires its own marker, so a tick that crashed in between finds a live-looking
  label over a record that still says cancelled — and the cancellation guard would answer that by handing the issue
  `rejected` again, undoing the authorization the restart is halfway through honoring.
- They come first because they are the ones that have to *run* rather than merely answer, and the two above can
  refuse indefinitely — the reuse guard *holds* a dispatch, writing nothing, for as
  long as an ancestor's ref cannot be asked about, and an owner of its own cancelled cycle nested under one would
  spend that whole outage never reconciling its own held PR, branch, or ref. Nothing is lost by the order: neither a
  cancelled cycle nor a restart mid-transaction starts any work, so neither question above is about anything either
  is going to do, and both are asked again on the tick after the ending or the fresh cycle is written.

## Closed-owner cleanup sweep (no label of its own)
- **Trigger**: an issue that is **closed** while still carrying one of the four cleanup-routed labels —
  `workflow:decomposing` or `workflow:umbrella`, where an adjudication runs, and `workflow:ready` or
  `workflow:blocked`, where an interrupted ending can be *left*. The second pair is the close/agent race made
  recoverable: a decomposition outcome writes one of them, a run spawned before its owner was observed closed lands
  after that observation, and the latch that would route the ending dies with the process — so without the query a
  restart before any cleanup pass loses the ending for good, receipt on the thread or not. Only their **closed**
  issues are asked about; an open `ready` issue is polled and dispatched exactly as ever. It
  is reached past the `backlog` / `paused` filter that parks everything else, because dropping one of these loses
  the close itself — an observed close ends the late cycle irreversibly, and this is the only pass that would ever
  record that, so an owner parked while closed would come back from a reopen and an unpause with a live generation
  and spawn against it. The control label defers what the pass would *do*, not whether the cycle ends: the sweep
  reads the same label and stops at the mark. The
  closed-issue sweep yields those four states beside its own recovery labels, on the same
  `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` cadence and through the same label cache and absent-label throttle, so it costs
  no request on a tick that sweep is skipping anyway (see
  [labels-and-state.md](labels-and-state.md#pollable-issues-and-finalization)).
- **An owner with no cycle left is asked one question before it is stepped over.** That question is the
  retirement's own correlation: a terminal, or a `blocked` parent's hand-back to its own work, that made its
  retirement durable and then died leaves a record naming which cycle it dropped, and a close observed inside that
  write leaves a receipt on the thread naming the same one.
  Where the two agree the cycle goes back cancelled and this pass ends it like any other, `rejected` included.
  Where they do not, what is left is an umbrella whose terminal is due and whose label never landed: that state is
  `umbrella` and closed — exactly what this sweep queries — and the record says which terminal it
  earned (`umbrella_resolved_at`), so `done` is written here. A write GitHub refuses keeps the label, which is the
  retry, so the pass after it writes what this one could not. Anything else with no cycle is left alone: every
  umbrella the initial decomposer made carries no generation and no stamp, and a hand-back writes no
  `umbrella_resolved_at` to finish.
- **Why it is not the label's handler**: every one of the four names a stage handler that would resume the workflow
  the close ended — one spawns the decomposer, one walks the dependency graph and activates children, one hands the
  issue to a developer. The dispatcher
  therefore reads *closed* before it reads the label and routes to `late_sweep._handle_closed_owner_cleanup`
  instead, ahead of even the live-adjudication relabel guard. That classification then **binds**: the submit carries
  a `cleanup_only` route the worker cannot re-derive, so a human who reopens the issue between the poll and the
  refetch cannot turn a cap-exempt submit into an agent-spawning stage handler; a closed reading on any other label
  that finds the issue open again runs no stage either, and waits for the next poll's admission.
- **Reaching this route at all is what says a close was observed**, and an observed close cancels the cycle it
  ended irreversibly. So the handler's own re-read decides how far the pass goes: an issue that is open again is
  marked cancelled all the same and stopped there — nothing external is done to an issue somebody has just reopened,
  and no terminal is written — and the mark is what hands it to the dispatcher's own guard, which owns a reopened
  cancelled owner and settles it from the next tick. The one exception is a record on a cycle the owed close cannot
  be tied to — one another poller, or this process, restarted after it (`late_sweep._settled_elsewhere`): nothing is
  marked, and the reading is settled out of the sweep.
- **A submission no pass settles is latched, not dropped.** The scheduler admits no second worker for an issue one
  is already running, and this is the only submission whose loss costs an *observation* rather than a turn: the poll
  saw the issue closed, and if a human reopens it before the next pass, no later poll sees that again. So the
  dispatcher latches the reading on `workflow/engine/observations.py` instead of discarding it, and the next tick
  reads it back and routes the issue to this sweep on the strength of it — ahead of the label, ahead of the close,
  and out of the family bucket, because the reading those come from is exactly what the reopen took away. What the
  sweep does with an owner that is open again is the bullet above: mark the cancellation and stop, unless the close
  cannot be tied to the cycle the record names.
- **A pass that RETURNED is not a pass that finished the ending, and the reading is kept where nothing else would
  come back.** A cleanup can run every step and leave the ending owed: a consumer that is live again keeps the ref,
  a remote that refuses a delete keeps the branch, and the `rejected` terminal is one more request GitHub can
  decline. What that decides is only whether this reading is the *last* route. An owner still wearing any of the
  four swept labels is one a later tick reaches on the `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` cadence an operator set — the
  label staying put *is* the retry — so the latch is handed back there rather than costing a cleanup pass per tick
  for as long as the ending is owed, which for a live consumer can be indefinitely. An owner that is *open* again
  hands it back too, because the sweep may not advance a reopened issue and the dispatcher's own guard owns it. What
  is kept is an owner that is closed, still owes something, and wears a label no query asks for; a read that could
  not answer is kept for the same reason, since it established nothing.
- **What the ending owes outlives the process holding that reading, so the label is repaired too.** The sweep
  queries four labels, and an owner can be moved outside all of them — by a hand relabel, or by an operator putting
  a closed owner onto a terminal over a cycle that still owes something. Inside this process the held reading is
  what brings a tick back to such an owner; after a restart, nothing would. So a sweep that leaves an obligation
  owed puts the owner back under `decomposing` or `umbrella` (whichever the `umbrella` flag says the record
  reached), unguarded, as the repair of a move this workflow never made — and the reading is handed back once that
  repair landed, because the label is now the durable route. A repair GitHub refuses leaves the reading as the only one
  there is, and it is held and said out loud. An ending that finished is left exactly where it is: it wrote
  `rejected`, which is what takes an owner out of the sweep for good.
- **The latch is a barrier the run in flight is held to, not just a note for the next tick.** The worker that owns
  the issue asks it before every step the remote keeps, through the same owner read those barriers already take
  (`late_owner_reading._read_owner` consults the latch before it asks GitHub). That is the reading GitHub
  cannot give back: a close and a reopen that both happened inside one of the run's own steps leaves the issue
  reporting `open`, and only the poll ever saw otherwise. A latched close therefore ends the cycle where the
  run stands — the cancellation persisted by the worker that owns the pinned comment, and nothing further
  spawned, created, or activated.
- **Where those barriers are, and why each one is there.** Every one of them sits immediately before a step nothing
  takes back, and each covers a window of *remote work* the poll runs beside:
  - **the child loop**, before every child including the first — the write that forces the parent to be an umbrella
    stands ahead of the first create — once more inside the create itself, since the orphan lookup that precedes it
    walks the whole repository on a resumed pass, once *behind* it, and once more between the read of the child's
    own pinned comment and the write that adds to it: the create is a request too, so is that read, and what a close
    inside either leaves is a real GitHub issue. That one is recorded either way (a child nothing names is the one
    state no pass can clean up) and written to never (a cancelled cycle owes its children nothing);
  - **each publication step** — the announcement, the supersession, and the retirement that hands the parent to
    `workflow:umbrella`;
  - **the activation walk** (`activation.py`), before *every* relabel rather than once for the walk: a relabel is a
    request, and a close latched after the first child was released must not release the second. Asked on **both**
    sides of the publication licence a late split's children carry, since that licence is a lookup of its own and a
    close observed inside it would reach nothing else before the relabel landed;
  - **the spawn** (`late_coordinator`), asked twice and the second time right against it — a worktree probe, a
    retry-budget write, a hold reconcile, and the write that records what this attempt IS all stand between a tick's
    own gates and the one step that puts an agent on somebody's repository. What the record then claims is an
    attempt nobody made, which the next tick reconciles for free; an agent that ran is what nothing takes back. Both
    are asked with the retry accounting handed back, since the cancellation a latch takes is itself a write and a
    run nobody started may not cost the issue a counted attempt — or the one a continuation bought;
  - **the developer revision** (`late_revision`), three times: as the tick is entered, again right against the
    resume — the revising notice it posts in between is a request the poll runs beside — and once more when the run
    comes back, which stops the remeasure that would write a fresh candidate over a cycle a close already ended.
    The poisoned-session retry inside the shared resume is guarded with them, since that is a *second* agent and an
    issue somebody closed is owed neither;
  - **an authorized settlement's publication** (`late_settlement`, and `late_handback` behind it) — the road a
    human's `/orchestrator authorize-oversized <commit>` licenses, since an adjudicator's own `single` parks and
    publishes nothing — asked between *each* of its own steps — the reconciliations, the exemption write (which
    carries the identity of the accepted contribution beside it, since the retirement below takes the frozen pair it
    was read over off the record), the handoff label, and the accepted notice — because these are the barriers
    protecting the *record* rather than an effect: the last write drops the generation entirely, and both the sweep
    and a receipt adopted from the thread read that generation to decide there is anything to end. Past that write a
    refusal is too late, so the answer there is a **reinstatement**: the generation is still in the call's own memory,
    and it is written back and cancelled from there. What was published stays published — the exemption, the notice,
    and the handoff label are none of them this owner's to take back;
  - **the reclamation paths** (through `late_cleanup_state._observed_close`), between every obligation it
    settles, between every two of the receipts a reclaimed ref owes its children — each is a comment on
    somebody *else's* issue, so a close observed after the first is one the second may not be written over —
    between the fresh consumer proof and the ref delete it authorizes — a ref that is gone while the record
    still reads live is a reclamation nothing afterwards can attribute to the cancellation that earned it —
    and again between that delete and the receipts behind it — and once more inside each of THOSE, since
    proving a child untold is a thread walk of its own and the comment it authorizes stands behind it — each
    is a request, and the receipts are the one cleanup effect that writes to somebody *else's* issue. The mark
    does not buy a shortcut through the reclamation rules; what it changes is what the settling owes anybody,
    since a cancelled cycle tells its consumers nothing;
  - **the umbrella walk** (`umbrella.py`), past the child scan, behind the settlement its terminal waits on, and
    once more immediately before the write that records the resolution — the scan is a request per child, and so is
    the settlement. `done` is the write that cannot be recovered from, because it takes the issue off every label
    the closed-owner sweep queries, so what makes it safe is the write *ahead* of it: one pinned write that stamps
    the resolution and **retires the cycle** together, carrying the two ledgers across the way the `single`
    publication's own retirement does. A close observed before that write stops the terminal outright and leaves the
    owner on `umbrella` with the mark down, where the ending retires it to `rejected` from a label the sweep still
    queries. One arriving after it is a human closing an issue this orchestrator had already finished — every child
    resolved, every obligation reclaimed, the cycle over — which is not a cancellation, and leaves no live cycle
    under the terminal for anything to have to find. That write is itself a request, so the latch is asked once
    more *behind* it, off the same `retiring_cycles.retiring` window the `single` retirement holds: there the
    answer is a **reinstatement** rather than a refusal — the generation is still in the call's own memory, so it
    goes back cancelled, no terminal is written, and the owner keeps `umbrella` where the ending reaches it. That
    barrier is this process's, so the write records `late_retired_cycle_id` exactly as the `single` retirement does:
    a process that dies before reaching it leaves a record naming the cycle it dropped and a receipt on the thread
    naming the same one, and the sweep adopts the two together rather than finishing a terminal over a close.
    Every window a crash can land in is one the next pass repairs:
    before that write the owner is on `umbrella` with a live cycle, which the sweep and the umbrella poll both
    already own, and after it the owner is on `umbrella` with the resolution recorded and no cycle at all — which
    the sweep finishes by writing the label the record already earned, retrying for as long as GitHub refuses it,
    because the owner keeps the label the sweep asks for until one lands. The closing notice is gated on the same
    stamp, so a terminal resumed after a crash says it once;
  - **the activation's own answer, carried out**. The walk holds the children it has not reached, which is the whole
    of what a shared dep-graph walk may decide; the split transaction asks again behind it and ends the cycle on the
    answer, because reporting settled would send it on to reclaim the superseded branch with no mark saying why.

  The barriers past a claim-bearing read take the latch alone: a claim names `owner_check`, and writing it over
  whatever boundary the tick actually reached is the rewind the record refuses.
- **It is latched where the close is READ**, which is the enumeration that classified the issue — not where the
  reading is later carried. Between the two stands the rest of that enumeration (a label read per issue in the
  repository) and the submit decision itself, and a worker already holding the issue asks the latch before every
  irreversible step it takes for the whole of that window: a reading installed only once the scheduler had refused
  would leave that worker free to spawn, create a child, or activate one against an issue the poll had already seen
  ended. It is taken for every closed issue the enumeration yields and every owed one, a closed issue whose label
  could not be read included: that one falls back to the family bucket, its reading bound to the drain's pass, so a
  refused bucket leaves the reading owed.
- **A close the enumeration never saw is taken at the REFETCH.** An issue open when it was listed carries no
  reading at all — nothing was latched, because there was nothing to latch — and the refetch every route takes on
  its way to a handler can be where that stops being true. From there the reading exists in one place only, and
  everything behind it can fail: the pinned read the guard is built on answers a refusal of its own, and the write
  that marks the cancellation is a request like any other. So both refetching paths take the observation against the
  object they just got back — the sequential loop, which has no hand-off to hold one for it, and the worker, whose
  hand-off carries the poll's *older* reading instead — and hold it across the pass, so a pass that could not mark
  anything leaves the reading for the next tick rather than losing it to a reopen.
- **The durable half is written there too.** A latch is memory, so an accepted submit whose task never starts — a
  scheduler shutdown, a process that dies before the worker takes it — would otherwise leave the observation with
  nothing on the remote saying it happened, and a human who reopens the issue before the next process polls it takes
  the reading away for good. So the receipt goes on the thread while the record can still name the cycle it belongs
  to: one pinned read per closed fan-out issue, off the object the enumeration listed, and an issue read and a second
  pinned read behind it confirming the close where the record names a cycle it would end. The first pinned read
  answers whether the reading is owed at all — an issue whose record says there is nothing to end has its latch
  dropped again right there, so the machinery is carried only by the owners that need it (and the admitted pass skips
  its own end-of-pass probe, since the poll already asked that record).
- **That drop is POSTPONED while a worker holds the issue.** "Nothing to end" is read off the late cycle, which is the
  right answer for the protocol this record was built for and the wrong one for the barriers standing immediately before
  a push: those ask the same latch, and every publication they guard carries no cycle — a first push has none yet, and
  an approved or recovered one retires its own before pushing. So a hold is taken per issue, and a settle arriving under
  it is recorded rather than taken. Nothing is refused and nothing is held for good: the same decision is made again as
  the last hold goes, one moment later, where it can no longer be made out from under the reader it was for — so an
  issue somebody reopens inherits no latch a later poll would never clear. Both production drops are covered, the
  enumeration's and a closed pass's on its way out. A postponed latch keeps its scope but not its read moment, and a
  *fresh* close latched before the last hold goes withdraws the postponed drop, while an owed one handed back leaves it
  to land: the scheduler's hold is given back only after its worker has let go of the issue's writer claim, so another
  poller on the host can restart the cycle in between and this process, refused the claim, read a close of the fresh
  cycle — a reading the drop was never about, left for the next pass under the claim to reconcile.
- **The hold starts at the CLAIM**, which is the scheduler admitting the submit — not where the worker first reads
  anything. The queue, the worker's own refetch and its label checks all sit between the two, and the refused submit
  is refused *because* a worker has the issue, so a reading dropped in that gap is one no barrier ever sees. Holds
  are counted rather than flagged: the dispatch takes one of its own over the handler it runs, which nests inside
  the claim's and is the only one the sequential path has.
- **It is process-wide rather than per-scheduler** because the readers are stage handlers deep inside a worker, and
  the alternative is threading a scheduler through thirteen handler signatures that have nothing to do with it. It
  is dropped by the pass that RAN (`settle_close` from the worker, once its pass returned), never by the submit that
  was accepted: an accepted submit is not a cancellation persisted — the worker refetches the issue first, and that
  read can be the thing that fails — so a pass that raises anywhere latches the reading again. A task that never
  runs at all — a scheduler shutdown, or a process that dies between the submit and the worker taking it — leaves the
  latch standing, which is the point: the next tick routes the issue to the sweep on the strength of it.
- **The cycle a retirement drops is recorded outside the group that write clears.** The window above is memory and the
  barrier behind the write is this process's, so a process that dies between them leaves a receipt naming a cycle and
  a record that no longer names one — and the guard below returns on a record with no cycle, so nothing would ever
  look at that receipt. `late_retired_cycle_id` is the one fact about the dropped generation that outlives the drop
  (like `late_exempt_sha`, deliberately outside `LATE_STATE_KEYS`): a record carrying it is asked once per owner and
  cycle — and again once another poller on the host has held the issue since — whether the thread has that cycle's close
  receipt, unless this process already holds a close scoped to that cycle, and one that does gets the cycle put back —
  cancelled, with the ledgers the retirement carried across — so the ending has something to run from. The correlation
  ends where its window does, and only there: any generation written with an identity supersedes it (the adoption's own
  mark included, which is what consumes it, and an operator's authorized restart with it). Both retirements that drop a
  cycle record one — an authorized settlement's publication and the umbrella terminal's — because what the correlation
  is for is the process that dies before its own barrier, and that barrier belongs to whichever process made the write.
  A terminal retiring cycle N names N and nothing else, so a receipt for any earlier cycle on the same thread matches
  nothing an adoption would read.
- **A retirement in flight is a record that answers for a cycle it no longer names.** A settlement that published the
  accepted candidate drops its generation and then asks the latch, and between those two the record carries no cycle
  identity at all — which is the one thing every reader of a close consults. A poll reading it there would answer
  "nothing to end", drop the observation, and leave the barrier behind the write asking a latch nobody is holding any
  more. So the worker holds `retiring_cycles.retiring(...).held()` across its own write and that barrier: inside the
  window the
  record's silence proves nothing, the reading is kept, and the receipt the poll leaves on the thread is scoped to the
  cycle the window names — which is the only place that cycle can still be read, and what makes the durable half
  survive the retirement at all. Outside the window the same reading IS dropped, and correctly: the publication
  completed, and the ordinary terminal arc the issue's label names owns the closed issue from there.
- **The probe and the receipt are one read.** Whether the reading is still owed and what the receipt should say are
  the same question about the same record, and two reads of a record a worker is writing can disagree — one seeing a
  cycle and keeping the observation while the other sees the retirement behind it and leaves the thread saying
  nothing, which leaves the reading in memory alone for a restart to take. So the owner writes the receipt from the
  read that decides it and answers the dispatcher with what that read established; a read that failed keeps the
  reading, which is the only answer a request that established nothing is entitled to.
- **The durable half is a marked comment on the issue thread.** A latch dies with the process holding it, so the
  first pass to latch a close also posts one cycle-scoped receipt
  (`<!--orchestrator-late-close-observed:issue=N:cycle=C-->`). A *comment* rather than a pinned write for the reason
  the latch exists at all: the pinned comment is written whole, so a second writer racing the worker that owns the
  issue would drop whatever that worker recorded in between, while a comment is added and races nothing. Posting is
  best effort — a receipt GitHub refuses costs durability, not the reading, which is still latched and still ends
  the cycle on the next barrier the run reaches.
- **A refused receipt is retried, not lost.** The post is attempted by every pass that latches a close and settled
  by the first that lands one: the memo suppressing further attempts (`observation_receipts.receipt_written`) is
  written by
  the attempt that succeeded, so a comment GitHub declines is tried again on the next poll. Without that, an
  observation with no durable half would be one a restart takes away entirely — the latch alone does not survive the
  process.
- **The attempt is claimed, and the memo is counted against the reading it was claimed for.** Asking whether the thread
  already carries a receipt and getting one onto it are two operations, and the other two parties are inside that gap: a
  second poll owing the same observation (a worker's failed pass and the following tick's enumeration meet there), and
  the worker running the pass that settles the reading. So `observation_receipts.claim_receipt_post` hands out the sole
  right to attempt the post — one poll walks the receipt-less thread, not two — and it carries the per-owner
  **generation** that reading was taken at. Every `settle_close` moves that generation, so a receipt landing either side
  of a settlement records no memo at all: without it the memo would stand for a reading nobody holds, and the *next*
  close — a fresh cycle an operator authorized by removing `rejected` — would be suppressed into having no durable half,
  which a restart before its worker reaches a barrier takes away entirely. The claim is handed back either way, by the
  write that recorded the memo or by the failure that recorded nothing; a claim left standing would suppress every later
  poll's receipt for good. The memo names the cycle its receipt was for, and suppresses a post only while the record
  still names that cycle: another poller on the host can settle that cycle and an operator restart it while this reading
  is still held, and a close of the fresh cycle is owed a receipt of its own — without one, a restart of this process
  after the issue is reopened would lose that close. The close is confirmed by an issue read between two record reads
  naming the same cycle — a record this process's own writer moved in between binds no scope, receipt, or memo — a post
  is made only for a cycle the held close ends, and a post skipped for either reason records no memo.
- **The receipt is read back once per owner and cycle.** After a restart the fresh process finds an issue a human
  reopened, a record still saying the cycle is live, and nothing in memory; the dispatcher's own cancelled-cycle guard
  therefore scans the thread for a receipt scoped to the cycle the record names, adopts it, marks the cancellation, and
  runs the ending from the mark. The scan is claimed through `observation_receipts.scanning_receipt`, so a thread
  carrying no receipt is walked on the first tick that sees the owner on that cycle and not again while nothing else
  writes the issue — what it recovers is an observation a *dead* process was holding, and every observation this one
  makes is in the latch, which costs no request. Another poller on the host is something else that writes it: it posts
  its receipts under the issue's writer claim and can die before marking what it observed, so once a claim this process
  takes finds that poller held the issue after the walk began, the walk is owed again. A walk for one cycle says nothing
  about another's receipt, and owes that cycle a walk of its own. The claim is held for the length of the walk and
  handed back where the walk established nothing — a listing that raises leaves `observation_receipts.scanning_receipt`
  by exception and the claim goes with it — because a claim standing over a read that established nothing would send
  every later tick straight past the receipt and on to the live stage handler. It is handed back again whenever a
  receipt actually LANDS: a claim taken when the thread carried nothing proved nothing about one posted since, and every
  later pass would read straight past it. The mark an adoption writes is made inside the claim too, so a mark GitHub
  refuses hands the claim back and the next tick walks again. Cycle scoping is what keeps an old close from ending the
  fresh cycle an operator authorized by removing `rejected`. A retirement's correlation is adopted from the latch as
  well as from the thread, where this process holds a close scoped to the very cycle the record says was retired — one
  it read while another poller on the host was retiring that cycle and had noted so on the issue's writer claim.
- **Every path that runs a cleanup holds its observation the same way.** The scheduler's fan-out submit, the
  in-tick parallel one, and the sequential stream all wrap the pass in
  `cleanup_observation._cleanup_observation`, with the refetch *inside* the wrapper — that read is the first
  thing a cleanup spends and the likeliest to fail, and a pass that raised marked nothing. Without the wrapper
  the exception is merely logged and a reopen before the next tick resumes the uncancelled cycle.
- **A closed owner whose label names an ordinary terminal is still cancelled.** The cleanup route takes a closed
  owner on either label an adjudication runs under; what reaches the dispatcher's own guard closed is the one window
  no label covers — an authorized settlement hands its issue to `workflow:implementing` a moment before it retires
  the cycle. Nothing else would end that cycle: the terminal arc that label names drains a merged pull request or a
  human close and writes the late record off nowhere, and the relabel guard beside it merely puts `decomposing`
  back, which a reopen before the next tick takes away again. So the guard marks it from the reading it already has
  — the closed issue it was handed and the record it already read — and the ending runs from the mark.
  The dispatcher covers the same window on both sides of the submit. An **admitted** task carries the poll's closed
  reading with it (`_PollReading`) and applies it on the worker thread before the guard reads the refetched object —
  a human who reopens between the poll and the refetch would otherwise leave the fresh reading saying open with a
  live cycle under it (the reading is tied to the record's cycle first, and one it cannot be tied to on an issue open
  again marks nothing and stops the tick for the cleanup pass its latch routes the issue to) — and it holds that
  reading across the pass, latching it again on the way out unless the pass actually spent it. Spending it is not the
  same as finishing: the pinned read the guard is built on answers a refusal of its own, so a tick that could not read
  the record refuses the issue and marks nothing. A **refused** submit leaves the reading as the enumeration left it,
  which latched it **first** and dropped it again only where the record positively says there is nothing to end. All
  three tick paths do this. The order is the whole of it — the probe is a request, and a request can fail or can land
  after the very retirement it was asking about, so a reading conditioned on it would be lost to either. A latch held
  over an issue with no cycle costs the next tick one cleanup pass that settles it; a reading dropped costs the close
  itself. It is taken on the refusal rather than ahead of admission, because an admitted submit runs the label's own
  handler and settles nothing.
- **A cancelled cycle is refused under every label, and the terminal lands where the graph allows.** Every workflow
  label names a handler that ACTS on the issue rather than settling it, so a cancelled cycle wearing any of them is
  refused whatever it says — a human who relabels such an owner is asking for work on a cycle a close already ended.
  Where `rejected` is *written* is the transition graph's answer for every label a workflow wrote: each state a late
  cycle can be interrupted on declares that edge, and `question` — applied by an operator who wants the issue discussed
  rather than ended — does not, so an owner there is refused and said out loud rather than relabelled out from under
  whoever put it there. `ready` and `blocked` are the exception, and they are not a human's placement: a decomposer
  spawned before the close writes one of them as its ordinary outcome and lands *after* the close, so an ending refused
  there is one refused on every visit the sweep makes, forever — neither label declares the edge, and the sweep is what
  brings a tick back. The terminal is therefore written from both, unguarded, as the repair of a move this workflow
  never made. The **unlabeled** state is refused with every other one, and the RECORD rather than the label decides
  whether the terminal may be written from it: an operator who removed `rejected` to authorize a restart leaves the
  issue wearing nothing, and so does a human who stripped a workflow label mid-cleanup and an ending whose terminal
  write GitHub refused. Where this cycle's terminal is proved applied, re-applying it would undo the one
  authorization a restart has, so it is not written; where the proof is missing, the terminal is still owed and is
  written once the obligations settle. Falling through is what does not happen either way — the pickup path behind
  the guard would greet a cancelled cycle as new.
- **A control label defers everything past the mark, and nothing before it.** `backlog` / `paused` park an issue
  outside the state machine, and the ending is external work — a held pull request closed, a branch deleted, a ref
  reclaimed — so none of it runs while the label is on. The cancellation itself is still persisted, because the pass
  the park would drop is the only one that would ever record the close: an owner parked while closed would otherwise
  come back from a reopen and an unpause with a live generation. That reading also survives the partition filter, so
  a parked *closed* issue is bucketed rather than discarded.

  The waiver is exactly that wide, and it is re-applied behind the mark. A record with no late cycle marks nothing
  at all, and the cancelled-cycle guard answers "not mine" for one — so without a second ask a parked issue would
  reach the stage handler its label names, which is the one reaction an operator applied `paused` to prevent. The
  same is true after a reopen between the poll and the worker: the reading is still the poll's, the record still
  owes nothing, and the park is still the answer.
- **A held observation outranks every filter above the partition.** It is not a reading of the current tick's, so
  what that tick can see about the issue has already been overtaken. A `backlog` / `paused` park no longer drops it
  — the sweep it routes to defers every external step anyway, which is exactly what the park asks for, and never the
  mark. And an issue the enumeration does not yield at all, because a human moved its label off the four the closed
  sweep queries, is added by NUMBER on the strength of the observation alone; the worker's own refetch decides the
  rest. All three tick paths do this: the partition for the scheduler and parallel modes, and the sequential stream
  sweeps whatever its enumeration never reached.
- **Why it fans out rather than joining the family bucket**: that bucket's cap exemption is all-or-nothing, so one
  open `workflow:decomposing` issue sharing the tick would make a closed owner cap-counted — and under a saturated
  cap the whole bucket is skipped, which stops the repository reclaiming refs for as long as its decomposer is busy.
  Partitioned as fan-out, the owner carries its own `cap_exempt=True` submit, for the same reason every other closed
  issue does: nothing on this path spawns an agent or touches a worktree it did not already own.
- **What it does**: it ends the cycle, and nothing about the workflow the close ended. It never spawns, never
  adjudicates, never creates or activates a child, and never touches one that already exists. The ending is
  [`late_cancellation.py`](../../orchestrator/workflow/stages/decomposition/late_cancellation.py), and it runs in
  a fixed order.
  1. **The cancellation is persisted first**, ahead of every external call, and the `late_cancellation` record
     rides that write — so there is one per cycle rather than one per cadence, and every gate below reads a record
     that already says the cycle is over. It carries the moment the obligation was taken on and the boundary it
     interrupted (`late_cancelled_phase`), because `late_phase` is about to name the cancellation itself and the
     boundary is what the whole-ledger rule reads. Both are kept from the *first* observation: a reopen and a
     second close re-mark the same cancellation and move neither.
  2. **A held pull request is released, told once, and closed.** This is the one obligation a cancellation
     owns that no other pass ever sees — every path that reaches an umbrella superseded the pull request its work
     was on along the way, so a cancelled cycle is the only shape where one is still open under a "do not merge"
     notice. The hold comes off
     first, so a pull request that ends up closed is not also left wearing one forever; a release that failed on a
     still-open pull request stops the close, since the preserved description is the only copy of what the hold
     replaced. The notice carries a cycle-scoped marker and is proved from the pull request's own thread, and the
     entry is recorded either way — `reconciled`, or `failed` with `pr_reconcile_failed` behind it. It is re-asked
     on **every** visit, including one whose entry already reads `reconciled`, for the reason the ordinary
     supersession is: that entry records what an earlier visit did, and a human can reopen the pull request behind
     it — an owner the sweep is still visiting for a branch it cannot delete would otherwise reach `rejected`, and
     leave the sweep for good, beside a change that is open again under a cancelled cycle. Re-asking costs one
     fetch and one comment listing and repeats nothing; the write and both sinks stay behind a state that actually
     moved, so a settled pull request adds no record per cadence.
  3. **The branch and the ref are `late_cleanup`'s, unchanged** — the same rules, the same `reclaiming` / release /
     `reconciled` order, the same records, and the same bound on them: what reaches the sinks and the pinned
     comment is a state that *moved*, so a remote that goes on refusing one delete costs a request per visit
     rather than a record and a write per visit, while the log goes on naming what is held. A cancellation buys no
     shortcut through any of it: a consumer that is live again keeps the ref whether or not its owner is closed.
     What it does change is which ledger the rule reads. The count written before the first create can only be
     reached by a loop that ran to the end of its manifest, and a cancelled one never will — so the loop that stops
     writes down that its register is **final**, which it may because every barrier that ends it is asked after the
     write recording the child in hand. The ref then goes once every child the split actually cut has ended. A
     **resumed** walk stopped before it reached the first unrecorded index seals nothing: a create is a request and
     the write recording it is another, so a child an earlier attempt made and never recorded would not be on the
     register, and there the ref stays held on the count.
  3b. **A branch a supersession left unrecorded is taken on here.** The transaction settles the held pull request
     and records the branch that PR carried in two writes — the second is the retirement, and retiring ahead of a
     supersession that might not land would let the children loose beside a change still carrying their work. A
     close landing in that window leaves a cycle whose candidate is preserved on the ref, whose held PR is closed,
     and whose branch nothing on the record names; settling around it would retire the owner over a branch the
     remote keeps for good. So a cancellation whose kept boundary is `superseding` resolves that branch and records
     it as owed — but off the **announcement's own receipt**, not off the phase. A park at the supersession is
     resumed from the top of the transaction, which rewrites `snapshotting` and `splitting` over the boundary while
     stepping over the announcement it already made, so a second failed attempt stands at `splitting` with the
     receipt still set and the phase no longer says what was reached. Not before that receipt, since the snapshot
     is created *and proved* ahead of the first child and the branch stops being the only copy there. Only where
     the record names no branch already, in any state. And only once the held PR of step 2 is actually
     **settled** — the boundary is written before the supersession is attempted, so it says the attempt was reached
     and nothing about whether it landed, and inferring the branch while that pull request is still open would
     delete, out from under a change a human can still see, the branch that change is built on. Nothing is lost by
     waiting: the pull request is re-asked on every visit, and the visit that closes it takes the branch on.
  3c. **The held pull request is asked once more, immediately before the terminal.** Step 2 settled it at the
     top of the pass; what stands between that ask and the write below is a branch delete, a ref delete, and a
     fresh read of every recorded consumer — long enough for a human to reopen the change inside them, which leaves
     the record saying `reconciled` and the remote saying open. `rejected` takes the owner off both swept labels,
     so a terminal taken on the record would leave that pull request standing under a cancelled cycle with nothing
     coming back for it. The re-ask is the same idempotent one: a pull request still where the earlier ask left it
     costs a fetch and a comment listing and moves nothing, while one that is open again is closed again and one
     that will not close goes back to `failed` and holds the terminal for the next visit. It is taken only where
     nothing else is owed, since that is the only visit whose terminal is actually due — an owner still holding a
     branch the remote refuses is one the sweep is bringing back anyway, and the ask at the top of that pass is the
     same ask.
  4. **`rejected` last, and only once nothing is owed** — branch, ref, and *every* unreconciled `plan_pr` entry on
     the ledger, which is a wider reading than what the pass acts on: acting takes the hold's own record, since
     releasing one means knowing which pull request this cycle marked, while being owed takes the ledger, because
     an entry left under a number a later write cleared is still an obligation and a `rejected` owner is one
     nothing revisits. It is what a restart counts too, so retiring over one would refuse the fresh cycle that
     terminal is meant to authorize. A recorded `late_plan_pr_number` with no preserved description beside it is
     owed as
     well, and is the one entry no pass can settle: the description that hold displaced is the only copy there
     was, so nothing may put it back or close over it, and the terminal is held until a human repairs the record.
     An opaque resource ledger blocks outright beside all of them.
  4b. **The child receipts are discharged in the same breath.** Each child is recorded `pending` when it is
     created, and nothing has ever moved one: the reclamation does not look at child entries, rightly, because a
     child is a live issue rather than an object to reclaim. But `rejected` authorizes a restart, and a restart
     projects its fresh cycle only over a ledger with nothing unreconciled on it — child entries included,
     correctly, since the projection drops the ledger and may not discharge an obligation by forgetting it. So the
     ending records what is already true: the children exist, this cycle is over, nothing further about them is
     owed. Not one of them is touched on GitHub.

     That label is the one write this path ever makes, and it is what takes the
     issue out of the sweep for good: every label the sweep queries is one it keeps until this write lands, so a
     terminal taken over an unreclaimed remote would leave that object with nothing coming back for it. A refusal
     keeps the label, keeps the issue swept,
     and says on every visit what is still holding it.
- **Consumer state is re-read, never latched**: this pass fetches every recorded consumer fresh, and a consumer
  reopened before the delete lands has a live claim again, so the ref stays. A consumer whose read *fails* also
  keeps its ref, while the branch half — which owes no consumer anything — is still settled on that same visit.
  The scan is taken only where a ref is actually held, so an owner with nothing but a branch left costs no
  per-consumer request.
- **An issue with no recorded generation is left entirely alone**, which is every umbrella the initial decomposer
  ever made: they wear one of the same two swept labels and own no cycle, so there is nothing to cancel and no
  terminal to rewrite.
- **A reopen does not resume the cycle, and does not skip its ending either.** Cancellation is irreversible within
  its cycle, so a human who reopens the issue does not get that cycle back — and every label the issue could be
  wearing names a handler that would act on it rather than settle it. The reopened owner is caught by the
  dispatcher's own pinned-state guard ([above](#the-reuse-guard-every-dispatch-ahead-of-every-handler) shares that
  read), which runs exactly the reconciliation above, reaches no handler, and writes the same `rejected` a closed
  owner earns. It runs the cleanup rather than merely refusing because this sweep visits *closed* issues only: a
  refusal with nothing behind it would freeze the issue until somebody closed it again. `rejected` is what the
  **cycle** earns rather than what a closed issue earns, and it is what an operator removes to authorize a restart,
  so reaching it is the only way back into ordinary work that does not silently resume a cycle a close already
  ended. The issue is left open; closing one a human just reopened is not this pass's to do.
- **The label decides where the ending is written, not whether it is refused.** A cancelled cycle is refused under
  every label, and the terminal is written from the ones the transition graph declares the edge from, plus `ready`
  and `blocked` — the two the cycle's own decomposer writes as its ordinary outcome, which no query would ever come
  back to. Under a label that is neither (`question`), the refusal stands on its own and the cycle stays cancelled
  where it is. Unlabeled is refused too, and there the record decides what the label cannot: an issue an operator has
  taken `rejected` off, one whose workflow label a human stripped mid-cleanup, and one whose terminal write GitHub
  refused all wear the same nothing. A cycle whose terminal is proved applied is not handed it back — that would undo
  the one authorization a restart has — and one carrying no such proof is owed the write. The restart itself is
  answered one guard earlier ([labels-and-state.md](labels-and-state.md#late-generation-state)); what never happens
  is stepping aside, since the pickup path below would greet a cancelled cycle as new.
- **Output**: the cycle cancelled once, obligations settled or retried (with the same `late_cleanup` /
  `late_failure` records the terminal emits, bounded the same way), no consumer written to or commented on, the
  owner moved to `rejected` once nothing is owed, OR a no-op.

## `_handle_implementing` (label `workflow:implementing`)
- **Trigger**: each tick while the label is `workflow:implementing`.
- **Input**: issue + comments + pinned state.
- **Internal flow**: a `retry_cap` park whose sentence was never said is replayed at entry, ahead of every step below
  (`_replay_owed_notice` — see [the retry budget](labels-and-state.md#the-retry-budget)); it says what the park is
  for and writes, and the tick carries on.
  0. **External-merge / closed-PR / closed-issue short-circuit.** `_pr_terminal_stops_the_tick` decides both
     pull-request endings off ONE guarded reading: a merged PR flips to `done` (`merge_method="external"`), and one
     somebody closed *without* merging flips to `rejected`, emitting `pr_closed_without_merge` and cleaning up the
     branch. `_finalize_if_issue_closed` behind it flips a closed issue to `rejected` and emits the same event +
     cleans up the branch only when the linked PR is also closed (an open PR with a manually-closed issue is left
     alone for operator salvage). The closed-PR ending is the arc `in_review` and `fixing` have always had inline,
     lifted out for the stages that carry none — `implementing`, `validating` and `documenting`: a closed PR leaves
     the ISSUE open, so nothing else here sees it, and the size gate below would measure the committed candidate
     again and push it, opening a second pull request since the first is gone, while the other two would spawn a
     reviewer or a docs agent over work a human has rejected. Both come off one fetch rather than a helper each
     because two fetches are two moments: a merge landing between them reads open to the first and merged to the
     second — which a close arc is right to ignore, while the stage runs anyway. `_finalize_if_pr_merged` keeps its
     own single-ending form for the umbrella / blocked aggregation, which may not be held on a child whose remote
     blinked. A fetch that FAILS writes nothing and falls *through* — the tick carries on to the stage — because
     nothing about a failed read says which ending, if any, it was hiding, and answered as one every issue whose
     remote blinked would stop advancing; the closed-issue terminal behind it is the one that defers the whole tick
     on its own failed read, so a transient failure cannot label a merged-PR issue `rejected`. On `implementing` the
     PR terminals are reached only past the plan question, which two records answer — and on that stage the one
     reading serves both, because what tells a plan from a delivery is the PR's **head** while what the terminals
     decide on is its **state**. Taken from two fetches those are two moments, and a head a human moved in between
     has one snapshot classified and another ended. A live `discussion_plan_path` says the recorded PR is the
     `discussion` stage's plan whatever its head is now, and it is asked *ahead* of the reading and costs nothing —
     the handoff below retires that record durably before anything spawns, so nothing here has pushed yet and a head
     that moved is the humans editing the design they are agreeing to (a corrected plan, a base merged into the
     branch), not work having landed. Past the handoff `discussion_plan_sha` answers, off the same reading the
     terminals use: it is the head that PR was on when the handoff took it — snapshotted there in the path record's
     place, so an amendment the humans made is not read as an implementation by the tick after. A recorded PR still
     on that commit is the plan, and one whose head has moved is this stage's own push. Neither may finalize as work
     having landed while it is still the plan. That read has three answers, not two — a PR that could not be read
     ends the tick where it happened, unfinalized and unspawned, *where the record makes the head the answer*: with
     `discussion_plan_sha` standing there is no telling the plan from a delivery, and neither answer is one to
     guess at. Where no such record stands there is nothing for a head to settle, so a failed reading falls through
     exactly as it does on `validating` and `documenting`.
  1. Awaiting-human resume: on a new human comment past `last_action_comment_id`, resume the dev session via
     `run_agent(dev_agent, ...)`. A `retry_cap` park is the one awaiting-human state this road never sees: the
     spent-budget bullet below owns the tick before it, because a resume is not a fresh spawn and the daily spawn
     budget does not charge it — the lifetime ledger does, like every other process start — so any reply at all would
     take that park down and hand the issue an unbudgeted session. The full spec persisted
     in `dev_agent` is re-parsed via `_read_dev_session` and
     reused; flipping `DEV_AGENT` in env does not migrate in-flight issues. When parked on `agent_timeout` with **no**
     new reply (the `implementing/parked_replies.py` cut the resume delivers from, so our own recorded notice, a pasted
     marker, or an answered `add-agent-runs` does not count), first attempt `_try_recover_implementing_timeout_park`
     (the implementing counterpart to validating's transient-park recovery): on a clean worktree whose HEAD advanced
     past the persisted `pre_implement_sha` **and carries commits `<remote>/<base>` does not**, clear the park and
     hand the recovered commit to the shared committed-work seam — the same one a finished run publishes through, so
     it is measured by the size gate and only then reaches `_on_commits`; otherwise stay parked silently. Both readings
     are taken, because the watermark says the checkout MOVED and not what it moved to: the commonest shape of this park
     is a run killed before its first commit, whose branch carries nothing of its own, so any advance of the base
     fast-forwards the checkout straight onto the new tip and the difference appears with no developer having written a
     line. Published on that reading, the issue gets a branch and a pull request with no diff in them. The pre-tick
     refresh freezes a branch parked like this so the rewrite does not happen at all
     ([labels-and-state.md](labels-and-state.md#base-refresh)); the base reading is what answers for a rebase it did not
     perform — an operator's, another process's, or one from before that freeze — and it fails closed, as does a
     watermark that names no commit (the park writes `""` when the pre-agent head could not be read, and every readable
     head differs from that).
     A recovered commit is not exempt from the gate: nobody read the run that made it, and publishing around the
     measurement is exactly how an oversized candidate would reach a branch and a pull request unadjudicated. This
     recovers a clean
     commit a descendant the timeout cleanup raced finishes *after* the park is recorded (the observed `#77` shape:
     commit timestamp landed after the timeout event) without needing a human "push it" comment. A real human comment
     takes precedence and drives the normal resume.
     - **A spent spawn budget** (`implementing/retry_cap.py`'s `_park_owns_the_tick`, the question
       `_handle_parked_continue_command` opens with — so ahead of the classifier below it, and ahead of the drift
       check and the resume, but BEHIND every step of the preflight above: the terminals still finalize a merged
       pull request or a closed issue over a parked one, and a `paused` / `backlog` issue never reaches a handler at
       all). Once the tick does reach it with `awaiting_human` + `park_reason=retry_cap`
       standing, this park owns it: nothing under this stage can pay for a spawn, so the tick returns having
       written nothing and said nothing (the sentence was said when the park was taken, and is replayed at stage
       entry until the thread carries it), reporting the refusal as one `retry_cap` audit record with
       `phase=standing`. Neither the clock reaching the end of the 24h window, nor a comment from outside
       `ALLOWED_ISSUE_AUTHORS`, nor words that ask for nothing lifts it — the first two answer nobody and the third
       is guidance for a developer this issue can no longer pay to run. The one reply that does is a **trusted
       `/orchestrator continue`**, looked for anywhere in the unread batch and taken with whatever else its comment
       carries: a decision that arrives with an explanation is still the decision, the explanation reaches the fresh
       spawn through the implement prompt's own comment context, and a refused tick consumes nothing — so a rule
       wanting the command alone would let one "on it, give me an hour" sit unread above the watermark refusing
       every command written after it. A park that still owes its notice is held ahead of all of that
       (`_park_is_explained`): the delivery moves the response boundary past everything written under the old
       sentence, so until it lands a command on the thread predates the question and buying an attempt with it would
       also clear the notice the human was owed. What the command buys is what `_grant_continuation`
       grants: one attempt (`retry_cap_continued`), a window reopened at that moment, and the park cleared with its
       stage and notice. The batch it was read out of is consumed in the same durable write that lifts the park —
       read again next tick it would buy a second attempt nobody asked for — up to the last TRUSTED comment, so an
       untrusted one above it stays unread for the next tick to filter out again. The
       tick then carries on to the fresh spawn below, which spends exactly that attempt. While the grant is unspent
       that spawn is the ONLY agent run this stage will make: the body-edit resume stands down for it (see the drift
       routing above), since a resume passes no gate and would leave the attempt on the issue with a run already
       made against it — and the grant is durable, so a process that dies before the spawn comes back owing the same
       one. The same write retires the pinned dev session (`_drop_poisoned_dev_session`, keeping `dev_agent`), because
       a fresh attempt is what was bought and nothing downstream can be relied on to make it one: `_spawn_implementer`
       replaces `dev_session_id` only when the run hands an id back, so a run that returns none would leave the
       transcript the cap stopped pinned for the next human reply to resume. The gate asks the same question again
       for **every** spawn a grant pays for (`spawn._charge_fresh_spawn`), because that write is not always the one
       this spawn follows: a process that dies before it comes back to an unparked issue still owing the attempt,
       and the budget is shared, so an issue can reach this spawn carrying a grant taken out on a `decomposing` park
       with a `dev_session_id` from an earlier cycle still on it. Nothing on either road touches the
       candidate, the pull request, or the late generation. `workflow:decomposing` holds the same park the same way,
       against the three roads it has instead of these
       ([its handler section](#_handle_decomposing-label-workflowdecomposing)). See
       [the retry budget](labels-and-state.md#the-retry-budget).
     - **`/orchestrator continue` operator command** (`_handle_parked_continue_command`, run BEFORE the drift check so
       the bare command is never mis-read as requirement drift). On a retryable session-failure park (`park_reason` in
       `_CONTINUE_PARK_REASONS` = `agent_silent` / `agent_timeout` / `agent_execution_failed`) a content-free continue
       retries the dev intentionally (`_retry_parked_dev_session`): the command watermark is consumed, the session is
       resumed on a
       neutral retry prompt — NOT the bare command text, so the dev is grounded on its transcript (or, once
       `_resume_dev_with_text` rotates it, a fresh respawn preamble quoting the classifier's frozen conversation less
       the commands) rather than the nudge — and the result disposes
       through the normal commit / timeout / question paths, with no "issue body changed" notice. If the failed run
       already committed work before parking, its tip moved past `pre_implement_sha` and above any inherited floor;
       when an intentional retry returns a valid `REPORT: READY` outcome with no HEAD change, that clean ahead-of-base
       commit attributable to the failed run is published through the normal report, size, push, and PR gates, clearing
       `pre_implement_sha` and `park_reason`. A park needing a real
       answer (any other `park_reason`) consumes the command and posts a refusal (`_refuse_parked_continue`) once, then
       stays parked (no per-tick loop). The size gate's own `late_measurement_failed` park is answered one step
       AHEAD of that classifier by `implementing/late_candidate_recovery.py`'s
       `_try_recover_late_measurement_park`, reached through the ordered recovery dispatcher,
       because what failed there is a READING rather
       than a session: a content-free continue re-measures the recorded pair and re-publishes through the same seam,
       and no agent is spawned — the developer that produced the commit finished long ago. A worktree that is gone
       leaves the park exactly where it is rather than measuring something else, and guidance carrying real words
       falls through to the ordinary resume. A comment carrying the command *alongside* genuine guidance falls
       through to the
       normal drift/resume path so the guidance drives the dev (`_continue_command_action` returns `passthrough`). The
       classifier + parser + refusal live in `workflow/engine/messages.py` and are shared with `_handle_fixing` and
       `_handle_documenting`; a bare continue is also dropped from `_compute_user_content_hash` (see above).
  1. **Every park the size gate takes** (`implementing/late_recovery.py`'s `_recovers_a_late_park`, asked ahead of
     the reconciliation below it, ahead of the continue classifier, and ahead of every spawn). Three parks come
     through this one owner and none of them is a park a human can talk their way out of: one owed another READING,
     which the bare continue below asks for; one owed another LOOK at the checkout, which is the handoff's own park
     and says nothing until the worktree is back on the approved commit; and one owed a DECISION nothing but
     `/orchestrator authorize-oversized <commit>` can be. On all three the work is committed already, which is why
     they are answered here rather than inside the spawn: the road below would buy a second developer run for an
     implementation the first one finished. Each hands its answer to the same committed-work seam a finished run
     publishes through, so a recovery reaches exactly the outcomes a fresh disposition does — published, held, or
     parked again with the reason it fails for now — and decides nothing the gate would have decided. None of them
     CREATES a park; the third one is taken by the reading itself, on an oversized candidate whose exemption has no
     operator authorization behind it.
     - The third is the one every poll reaches, because an issue behind it has committed work and no run to dispose:
       nothing else on the tick would measure the candidate again or say a sentence the park still owes. What a poll
       costs is what the thread says — the command is acted on, guidance falls through to the ordinary resume, and a
       thread nobody has written on is held where it stands without a reading, a request, or a word.
     - A checkout the seam would REFUSE stops that road before the seam and holds silently, writing nothing: the
       seam parks under a reason of its own and its notice moves the watermark past whatever it finds, which here
       would take this park's reason off and consume the command still standing, so the operator who fixes the
       worktree would be asked to authorize the same commit a second time. So `late_authorization_recovery` asks the
       seam's own
       questions first — the worktree on this host, its tree provably carrying nothing loose, its head the commit
       the park is about — and the commit it proves travels ON the work handed over, so the gate holds its own head
       read to it rather than to whatever landed in the writable window between the two readings.
     - What the seam does anyway is held across the call on the RECORD rather than in the frame that made it
       (`implementing/late_rollback.py`, `late_held_authorization_park` with the park's reason and watermark, and
       `late_held_authorization_command` for how far the reading behind the command got). Both are written before
       the call and read back after it, and the one question asked is whether the PUBLICATION happened — the write
       that moves the label out of this stage is what spends them, so a record still carrying them is a call that
       never reached it, and a process that died inside the seam is put back by the poll after the crash.
     - The sentences that seam posts carry a **receipt** recorded before each goes out, so one a crash stranded on
       the thread is attributed to this stage rather than read back as somebody's guidance and answered with a
       developer run (`implementing/late_authorship.py`, repairing the ledger ahead of this routing and never
       moving the watermark). Full field-by-field semantics:
       [labels-and-state.md](labels-and-state.md#pinned-state).
  1. **A frozen candidate with no park beside it** (`_holds_unreconciled_candidate`, asked before anything
     spawns). A tick that recorded the `measuring` pair and died before counting or parking it leaves nothing on
     the issue saying the workflow is waiting. On the host that froze it the next tick simply measures again; on
     a rebuilt one the checkout comes back at base, the recorded commit is nowhere in it, and the ordinary flow
     would pay for a SECOND developer over work the first one already finished. So the record is reconciled
     first: the worktree has to be there, both ends of the pair readable in it, and the checkout actually ON the
     recorded candidate — a host without the checkout or without the candidate parks (`late_measurement_failed`)
     asking for the worktree rather than for another run, while a recorded BASE a fetch did not bring back spends one
     of the readings this pair is allowed to lose and stops the tick saying nothing until that bound runs out.
     The head is proved because no developer ran here: unlike a fresh disposition, where
     a head past the record IS a resumed developer's new commit, a moved checkout on this path is one somebody moved,
     and measuring it would answer the size question about a commit nobody froze while discarding the record naming
     the real one. Past all three the tick finishes what the crashed one started, over that exact pair.
  2. Otherwise ensure a per-issue worktree at `<WORKTREES_DIR>/<owner>__<name>/issue-<n>` on branch
     `orchestrator/<owner>__<name>/issue-<n>` (the slug-namespaced branch keeps two RepoSpecs sharing a `target_root`
     from colliding on the same `orchestrator/issue-<n>` ref). Worktrees with unpushed commits are reused (crash
     recovery); otherwise force-removed and recreated from `<spec.remote_name>/<spec.base_branch>`.
  3. If the worktree already has commits (recovered), skip the agent and dispose them as a finished run would be —
     through the committed-work seam, so the size gate measures them before anything is pushed — unless those commits
     are the ones a read-only relabel just certified (`read_only_baseline_sha` still equal to HEAD), which is a branch
     the issue arrived carrying rather than a run to finish, so the implementer spawns normally. That is a
     comparison, so a HEAD that could not be read spends nothing: `_head_sha` reports its own failure as `""`, which
     differs from the certified tip exactly as a checkout the dev has committed on does, and read that way the
     baseline is retired and the design's predecessor republished as the work the discussion just agreed to. A
     baseline stands until something SHOWS the branch has moved off it. The road with no baseline is deliberately
     untouched: there the commits are a previous run's whatever the probe says, and refusing them would buy a second
     developer over an implementation the first one already finished.
  4. Else gate the run on the per-issue retry budget (`MAX_RETRIES_PER_DAY`, default 3); a 24h window opens at the first
     counted spawn. Only fresh spawns count. An exhausted budget parks the issue durably as `retry_cap`, and that
     park is asked before the cap and the window both, so the notice that asked for a human is not answered by the
     clock or by a retuned cap. An issue a continuation has bought attempts for is answered from those attempts and
     from nothing else, so the spawn this step allows on that road is the one the human paid for — and the pinned
     dev session is retired here as it is charged (`_charge_fresh_spawn`), since what the human bought is a fresh
     conversation and this step runs on grants the tick before it did not take out. See
     [the retry budget](labels-and-state.md#the-retry-budget).
  5. Else build the implementer prompt (issue body + recent comments + "commit, do not push"), persist `dev_agent`
     BEFORE invoking `run_agent`, then spawn through the bounded developer run coordinator
     (`_coordinate_developer_run`). An initial AGY run that leaves an active command and no edits or commits is
     resumed in the same worktree with a command recovery prompt without a human reply. Only a recovery that completes
     its command may proceed to ordinary commit or publication disposition; repeated premature exits park retryably as
     `agent_execution_failed` rather than `agent_question`. The daily fresh-spawn gate is charged only once for the
     original fresh spawn, while every process consumes the lifetime agent-run ledger. Non-AGY backends (Codex,
     Claude) and completed runs are untouched. Pause, timeout, shutdown sweep kill, and run-limit refusals stop
     recovery.
  6. Branch on result:
     - `interrupted` (shutdown sweep killed the run mid-flight) → ignore the partial result and return WITHOUT writing
       pinned state, so durable GitHub state stays exactly as the prior tick left it and the next process retries.
       Precedes every branch below and applies to both the awaiting-human and user-content-change resumes. Never posts a
       HITL question, consumes `awaiting_human`, or advances a watermark.
     - `paused` / `backlog` applied mid-run → same short-circuit as `interrupted`: return WITHOUT writing pinned
       state, so no PR opens, no relabel, no park, no watermark bump. `_paused_during_agent_run` re-reads a FRESHLY
       fetched issue (`gh.get_issue`) because the dispatch-time skip only saw the pre-run labels. Applies to the fresh
       spawn, the awaiting-human resume (including the pre-disposition `_resume_dev_with_text` poisoned-session retry),
       and the user-content-change resume. The committed work stays on the branch and republishes through step 3's
       recovered-worktree path once the label is removed.
     - `timed_out` → dispose on whether the run left a commit, which requires command completion
       (`not unfinished_steps`) and two readings (`_timeout_left_commits`): HEAD advanced past the pre-agent SHA
       snapshot **and** the branch carries commits `<remote>/<base>` does not. A clean advance that passes both
       goes through the same committed-work seam — the size gate, and `_on_commits` past it — exactly as a normal
       completion (a clean commit produced just before/around the kill is **not** stranded behind `awaiting_human`);
       an unfinished command, dirty tree, or run leaving nothing parks (`agent_timeout`) with `pre_implement_sha`
       persisted for step 1's next-tick recovery. Neither reading answers alone. The `pre_implement_sha`
       watermark is what tells a
       commit produced by THIS run apart from commits already carried on the branch, which `_has_new_commits` cannot
       (it only compares to `<remote>/<base>`, which a branch can arrive at this stage already ahead of). And
       `_has_new_commits` is what says the head moved onto WORK rather than onto the base — an agent that rebases or
       resets mid-run, its own `git pull`, or another process across an hour-long run moves the checkout with nothing
       written, and read as a difference alone that publishes the base branch as an empty PR. Step 1's recovery asks
       exactly the same pair, over the base a rebase between two ticks left.
       Both readings are COMPARISONS, so both ends have to have been read at all, and either missing parks
       (`_attributable_run`, shared with the clean half). `_head_sha` reports its own failure as `""` — the one value
       that cannot be a commit — so an unread end differs from every commit there is, and on a branch that was
       already ahead of base (one a read-only relabel certified, one a size-gate park left a candidate on, one a
       human's guidance resumed a developer over) that difference publishes work the run never made.
       (`_on_commits` clears the spent watermark + stale reason on publish.) Pairs with the hardened
       `process_groups.terminate_process_group` (SIGKILLs surviving descendants after the leader exits) so a build
       grandchild cannot keep committing into the worktree after the timeout is recorded.
     - new commits + clean tree → the **late size gate** first (`implementing/late_gate.py` and the
       `late_records` / `late_freeze` / `late_evidence` / `late_verdict` / `late_parks` owners under it, plus
       `late_authority` for whether an adjudicated commit has a human behind it and `late_consent` / `late_command`
       for the `late_unauthorized_exemption` park an oversized one without one takes,
       whose standing form the recovery above routes on every poll), the
       one seam
       all three committed dispositions publish through — a run that finished, a timeout that had committed, and a
       branch a crash stranded. With `DECOMPOSE=on` the candidate is proved to be a commit this host holds, the base
       is frozen from what the *remote* says the branch is at, and both are persisted with `late_phase=measuring`
       BEFORE the diff is counted, so a tick that dies over the count comes back to the same pair rather than to one
       re-derived from a branch that has moved. Strictly more than `MAX_ADDED_LINES`
       ([`../configuration.md`](../configuration.md#cadence-and-budgets)) added lines routes the issue to
       `workflow:decomposing` with nothing pushed and no pull request opened; at or below it publishes as below and
       the generation is dropped, leaving `late_retired_cycle_id` so the next candidate cannot answer to the same
       cycle number. Four commits skip the measurement because this workflow already decided about them, each
       named exactly and only by its own record: the one an authorized settlement accepted (`late_exempt_sha`,
       which an adjudicator's own `single` never writes -- that parks for the decision) *and* an operator
       authorized (the `late_override_*` group, whose recorded pair is fingerprinted again here and held to the
       digest it carries — an exemption alone is half a bypass and goes to the ordinary reading), the one the
       gate approved and has still to push (`late_approved_sha`, unless its `late_approved_basis` says the debt
       rests on that same unauthorized exemption), the one this stage already pushed
       (`implementing_published_sha`), and
       the one an open pull request this call froze is already standing on, where the push would move nothing and
       only the bookkeeping behind a publication that has happened is owed. None of the four crosses between issues:
       a child of a split is a separate issue whose pinned comment carries its `late_ancestry_*` group and no record
       that skips a reading, so the slice it commits is measured here like any other candidate — the frozen base
       against the commit being published, across implementation, tests and documentation alike, over however many
       commits the slice took — and the addition budget stated on its body is not something this gate reads at all.
       So does every candidate while `DECOMPOSE=off` — except
       one this issue has a recorded generation for *that same commit*, one it owes a push for, and
       one **answering a reading the gate itself recorded**. A generation naming some OTHER candidate is one a
       resumed developer's fresh commit has moved past, and the fresh commit is new work: published untouched with
       the switch off, named against the checkout like every other switched-off push, and the superseded record
       retired rather than left over a commit nothing will publish. The approval holds the switch back for the
       commit it *names* and no other, so the
       switch is asked twice: once at the door, and once past the proof, where a head that is not the approved commit
       is a resumed developer's new work and bypasses as new work does. The publication drops the stale approval on
       its way past, since a debt recorded for a commit nothing will push freezes the branch and parks every later
       tick asking for it back. A tick answering a reading a previous one recorded (a park a human answered, a
       frozen pair a crash stranded) is never new work, whatever the record says, and reading one as new work is the
       switch failing *open*, publishing the very head whose reading somebody asked for. The switch decides what
       ENTERS the gate; it does not answer a question the gate already asked, nor anything already in it.
       That exemption is *narrower* than "no developer ran": a base rebase, a conflict resolution, a divergence
       publish, and a recovery push are each taken with no agent behind them and are each a commit nothing on the
       record asked for, so with the switch off they publish unmeasured like every other fresh candidate. Reading the
       wider fact as the exemption is the switch failing *closed*, measuring the work an install that turned the gate
       off asked to be left alone and routing a pull request nobody grew into an adjudication it never opted into. A
       recorded candidate
       is proved before anything else, and the current head is never a substitute for it: a host that cannot peel
       that object parks under either switch setting, and a recorded base is retried by asking for that exact object
       rather than by re-reading a remote whose branch has moved on. A reconciliation stays bound to that pair for
       the whole tick — it proves the head against the record before it starts and the gate reads the head again, so
       one that differs on the second reading is a checkout something moved mid-tick rather than a run's output, and
       it is refused under either switch setting instead of being measured or pushed — refused before it is asked
       whether it is readable, since a head that moved onto an object this host cannot peel still names one, and a
       name handed on is what the park downstream would record in the recorded pair's place. A reading that could
       not be taken is never a small candidate: it emits `late_failure` carrying `measurement_failed` — for every
       refusal, under a minted identity where no generation exists yet or where the recorded one is not one a sink
       may carry (a damaged identity would otherwise emit nothing, and one naming another issue would file this
       issue's failure over there) — parks `late_measurement_failed`, and keeps the pair it froze for the retry.
       The record names the step as well as the family: a refusal that WAS a reading carries the
       `MeasurementFailure` it stopped at and the line that step wrote, while one that reached no reading — a pinned
       record too damaged to act on, a debt no push can pay, a receipt group that does not read back whole, a
       receipt whose own publication could not be shown — carries the family alone, since those say what they
       are in their own words rather than in the measurement vocabulary.
       The two steps that name the TRANSPORT rather than the work are the exception, and only for as long as the
       bound allows: a base the remote would not answer for (`base_unreadable`) and one a fetch did not bring back
       (`base_absent`) clear themselves, so the first three consecutive misses on one pair write the pair and the
       incremented `late_measurement_miss_count`, emit the same typed `late_failure`, log at WARNING and stop —
       leaving no `awaiting_human`, no `park_reason`, no comment and no recorded step, so the next tick re-enters
       that exact pair with nothing spawned — and only the fourth parks and mentions a human, recording in the same
       write the `MeasurementFailure` that mention names. Every mention this gate makes is made ONCE PER THING THERE
       IS TO SAY, whatever the cause: the post-publication reconciliation re-enters the pair on every poll after a
       park, and a tick that finds the park already standing over that same pair, stopping at the step
       `late_measurement_failure` already names, is held silently — no further miss counted, no second notice, but
       the typed `late_failure` still reaches both sinks, since those polls exist nowhere else, and a base id the
       remote finally names is recorded even there because it is what the next retry asks for. Without that field a
       candidate this host cannot peel, or a diff nothing here can pin, would mention the same people once a poll
       for as long as it took them to clear it. A poll that stops at a DIFFERENT member is not a repeat: it is a
       different next move for whoever is holding the issue and nothing else would ever tell them, so it is
       announced once and takes that field's place in the write the notice rides out on — which makes the poll after
       it a repeat rather than a second announcement. No miss is counted for it either; the bound is spent. Every
       notice a refused reading makes, on either road, names the member and explains it in a line written for the
       operator — which of a remote, a token, a throttled request, a checkout, or a planted attribute file they are
       looking at, and, for the remote read, the fetch and the two diff steps, the `orchestrator.git_plumbing`
       channel their invocation is logged under — with whatever the failing step wrote for itself, scrubbed, carried
       up beside it.
       The hold is keyed on a human still WAITING — the latch, since a resume consumes it and leaves the reason
       standing — and on the pair the park was taken over. A park failing either test is spent: a fresh candidate,
       which is what answering the park with guidance produces, retires it and starts its own bound, in the same
       durable write that records that candidate: nothing says which commit a park was taken over, so a park left
       behind by one would be read as the fresh pair's own by every tick after it. A base that IS reached
       ends the run of misses in the write that records the pair — the count and only it, since reaching the base is
       not the last step a reading can stop at and the member beside the count says what the thread was told. That
       member is dropped where every failure-prone step is behind it: the verdict a reading that HAPPENED settles,
       which clears it and the count together in the write it settles on, so the record an oversized candidate is
       adjudicated from carries no step at all. The park is retired by that same verdict rather than on the way into
       the gate, since entering it is not answering the
       question the park was taken for and a retirement there would leave an issue durably unparked whose next
       reading can miss again. Every other member parks on its FIRST miss, because a second reading of a candidate
       this host does not hold, or of a diff nothing here can pin, comes back with the same answer — and a reading
       retaken past that park is held silently by the same guard, since the answer it comes back with is the one the
       notice already named. Which readings there are to hold is decided by the road the pair was frozen on, and
       this seam is the one that retakes none by itself: a park taken here owns every tick until a trusted bare
       `/orchestrator continue` arrives, and that command clears the latch and the reason before the pair is
       re-measured, so its own miss is answering a human rather than repeating a sentence and is said out loud.
       The silent hold is the post-publication road's, where the reconciliation ahead of every handler re-enters the
       pair once a poll with nobody asked.
       Which is a pair whenever one can be established at all: a revision that resolved and would not peel comes
       back carrying the id it resolved to, and that id is recorded with the park, so the retry asks for that exact
       object and the reconciliation ahead of the next spawn proves it. A revision that would not resolve names
       nothing, and there the park itself is the record — its bare continue is refused rather than answered, since
       what a retry would take is a *first* reading of whatever the checkout points at by then and nothing ties that
       head to this issue; the way on is guidance, which resumes the developer. Either way the park holds the branch
       out of the pre-tick base refresh until it is answered, or a rebase under it would leave both the exact-pair
       retry and the refusal with nothing to be answered from.
       A count already on the record is acted on only once its identity is whole too: the domain's record gate has
       to accept the cycle, generation, and root, and `late_current_issue` has to name this issue, since a reading
       taken over there is not this issue's answer.
     - past the verdict, the same rule covers the publication the gate licensed. The write that approves a candidate
       records it as `late_approved_sha`, and the checkout is proved to be ON that commit before any later tick
       spawns or republishes — the object alone outlives the branch, so a checkout reset on the very host that made
       the commit still holds it — which is what stops a rebuilt or reset one being published, or being handed to a
       second developer because it reads as a branch with nothing on it. It is a floor as well as a proof: a run
       resumed on top of it is judged against `before_sha` too, so an agent that answered with a question rather
       than an implementation parks that question instead of having the commit it was asked about published. And it
       is spent durably BEFORE the relabel to `validating`, because past that label implementing never sees the
       issue again and a stranded approval would freeze the branch for the rest of its life. Ahead of that write, the
       moment the pull request is known — before one this tick opened is announced, and before the report is bound — a
       durable write records which commit the push carried (`implementing_published_sha`), the head it replaced
       (`implementing_published_lease`, empty for an initial publication, which froze none) and the pull request it
       went onto (`implementing_published_pr`, which is the only write that can name one here, since `pr_number` is the
       relabel's), for the effects that can fail on their own: an announcement, a report or a relabel GitHub would not
       take or never answered, or a process dying in any of them, leaves the issue implementing with its branch pushed
       and its pull request open, and the record is what has the next tick hold to that pull request and land the label
       rather than re-decide a published branch or open a second one. The head rides along because the receipt is never
       cleared and so cannot date itself — read alone it vouches for any pull request somebody later rewound onto the
       commit it names. That commit is decided once, ahead of the push, and is what the push is named against —
       where the gate proved one it is that, and where it did not the checkout names it — so the push, the receipt,
       and the proof taken once the pull request is open are all about the same commit. A checkout that cannot name
       one at all publishes nothing and parks (`late_candidate_moved`): a push named against nothing sends whatever
       the branch has become by the time git runs it, records no receipt, and leaves both proofs around it with no
       commit to hold the checkout to, so every guarantee here is off at once. The pre-push half is durable
       as `late_approved_sha`, and the proof past the pull request is the second half of the moved-checkout refusal:
       the worktree is writable while those requests run, and one that moved is parked rather than handed to review,
       with the publication left standing. Both boundaries ask about the TREE as well as the head, because loose work
       can appear with `HEAD` never moving — so every proof about the commit passes over it, while the checkout the
       handoff passes on is no longer the thing that was measured and nothing past the handoff reads it again. A tree
       that is dirty, or that `git status` could not report on, is parked as `late_candidate_moved` exactly as a
       moved head is: before the push nothing is published, after it the branch and its pull request stand and only
       the label is withheld. See
       [`../workflow/roles.md`](../workflow/roles.md#the-size-gate-a-committed-candidate-passes).
     - new commits + clean tree, past the gate → `_on_commits`: push branch, open PR (or reuse an existing open
       one), comment
       `:sparkles: PR opened: #N`, publish the developer report onto that PR, then set label `workflow:validating`
       (the docs pass runs only as the final-docs handoff after approval). A new PR's body is `Resolves #N` and the
       dev session, plus the agent's closing message wherever no developer report of the issue's is owed or settled,
       since that report is then the authority. A reused PR is only known to be open on the branch — most sharply, an
       issue relabeled out of `discussion` arrives with its plan PR open on the very branch these commits went to —
       and its description is **never rewritten**: GitHub offers no write that cannot overwrite an edit saved a moment
       earlier. It is read again by number before the report is bound and again before the handoff
       (`implementing/pr_description.py`); one that closes this issue (a keyword reference outside literal code,
       bare or qualified with this repository) and names this dev session stands exactly as it is, legacy
       `_Last agent message:_` tails and human annotations included; any other parks under `report_undeliverable`
       with the two lines to add quoted in the notice, and a failed re-read holds silently. Persists `pr_number` /
       `branch` and resets `review_round=0` and `retry_count=0` via `handoff._reset_implementing_counters`.
     - **the report the run wrote** is what the publication owes beside the code (records under [pinned
       state](labels-and-state.md#pinned-state)). It is recorded between the tree reading and the size gate, and BOUND
       to the publication and posted once the pull request is known (`implementing/report_handoff.py`). The requirements
       are proved afresh before the post and again before the settlement, so an edit landing during the run or either
       request leaves it owed for the drift resume. A run that did not COMPLETE — a timeout, a provider refusal, a
       nonzero exit, or a recovery's `invoked=False` synthesis — records nothing. Both the record and the binding are
       guarded commits over the comment as it stands (`engine/report_commits.py`): a comment that will not read, was
       replaced, or moved under the report records the decision was taken on ends the tick with nothing pushed or posted
       and nothing parked -- and nothing written, since every whole-state write the handler takes behind the refusal is
       withheld -- and room is measured on the very candidate sent, so room another road spent since the tick read the
       comment is refused as the record's or the binding's own room, and room it gave back is used. A record or binding
       GitHub took and never confirmed ends the tick before the push or the post with nothing written behind it; the
       next tick republishes with no developer run, binding that very record or publishing that very transaction at the
       run's own revision. A binding that did not land either way withholds the handoff before any of the last readings
       below, saying nothing: a park one of them took behind it -- over an older transaction the delivery supersedes,
       say -- would be a notice no write could record, posted again on every tick. The settlement behind the post is a
       guarded commit too (`engine/report_settling.py`), prepared before the post and committed behind it: one that did
       not land over the comment the tick read, or landed unconfirmed, withholds the handoff the same silent way, and
       the reconciliation ahead of the next handler settles the posted report by its receipt, or finds nothing owed.
       So does a post or re-read that leaves the report owed while another road wrote the comment meanwhile: the
       comment is asked once more behind it, and the tick's state is withheld rather than written back over that road.
     - **a report still owed refuses the handoff**, exactly as a moved checkout does. A bind with no room, a thread read
       or post GitHub refused, a lost response, and a failed requirements re-read leave the branch pushed, the pull
       request open, the receipt and `late_approved_sha` recorded, and the debt standing, with nothing parked; the next
       tick republishes onto the same pull request with no developer run and finishes, the post scoped by its receipt. A
       debt no retry can pay parks under `report_undeliverable` instead: no record left to publish (a resumed session
       that committed and timed out), or a report a human edited, removed, or wrote untrusted. With nothing owed, the
       last readings before the handoff go in the order that leaves each after the requests that could change it: the
       requirements afresh, then the report settled for this commit re-read where it settled — after a recovery's push
       too — then the checkout, which is local, and the description last. A report edited or removed since, or one
       answering moved requirements, parks the same way; a checkout moved or dirtied during those requests parks as
       `late_candidate_moved`. A publication no report covers — the commit a run that never COMPLETED left — has its
       requirements read afresh all the same, put to the drift check against the revision the run was handed: moved,
       or unread, the handoff is held unparked, and the drift check the next tick opens with resumes the session
       against the edit before the owed handoff is republished.
     - **a report this build cannot deliver parks the issue** under `report_undeliverable`. Before the size gate, with
       nothing published: a report that cannot be RECORDED; a run that COMPLETED with no usable report; and every
       recovery — the restart shortcut and each road republishing a candidate a gate record named — finding committed
       work no recorded report describes: no delivery, no transaction, and no settled pair about that commit and branch
       on the pull request its receipt names. A pair that DOES match is re-read first with the requirements; an
       unreadable reading holds, and a report edited, deleted or re-headed, or requirements moved, parks. A commit a
       run that never COMPLETED left, or a timeout park's recovery republishes, is recorded as
       `implementing_incomplete_run_sha` and owed no report — unless a delivery or transaction an earlier run recorded
       is still unsettled: it describes the branch before that commit and is never bound to it, so the commit parks,
       the record kept, until a completed run's report retires the waiver. After the push, with only the handoff
       withheld: an unreadable delivery, a verification on another pull request, a verification on the DESCRIPTION
       this publication needs while it closes nothing — the collision — and a description that does not name the
       implementation. Nothing is discarded, no park is announced twice, and `developer_report_owed` is the debt where
       no record exists, outliving any later park. A resumed run that comes back with a report and moved no head
       publishes the commits already on the branch, so an ordinary question is still a question; the handoff spends
       the reason once the report has reached the pull request. A report that cannot be RECORDED leaves every report
       record as it was, and its notice and log line name the refusal the record's writer gave
       (`workflow/engine/report_refusal_notices.py`). A quoted receipt marker is described rather than quoted back,
       and the reply is asked for the report with every receipt described in prose. A report past `MAX_REPORT_TEXT`
       is told its length and that ceiling. A pinned comment with no room names the write measured (the record, the
       transaction it becomes, or that transaction's settlement), its size against the ceiling, and what frees the
       room. Only a `REPORT: READY` report whose record or transaction overflowed is asked for a rewrite, counted in
       the comment's own characters: the notice gives the report's length beside what its text takes escaped for
       JSON, and asks for escaped text at least the overflow smaller. A verification (location and digest only) and
       a settlement (where the report landed) carry no text, so their notices ask for room freed on the comment
       instead. Any other invalid record is worded with no claim about size and points at the pinned comment and
       the log. No size is named where none was measured, and every recovery is a reply whose resume needs no new
       commit.
     - new commits + dirty files → `_on_dirty_worktree`: park; refuse to publish a partial branch.
     - new commits + a tree `git status` could not report on → `_on_unreadable_worktree`: park under
       `unreadable_worktree`. An unreadable tree is not a clean one: the list form of that read maps its own failure
       to "no paths", which is the answer a clean tree gives, so the seam that publishes asks the status form and
       refuses on either half of "not provably clean". An index entry marked `assume-unchanged` / `skip-worktree`
       comes back as a path AND withholds the reading, so it takes the dirty park and is named there.
     - no new commits → `_on_question`, which parks on the agent result and whose words the last message is. A run
       carrying unfinished command diagnostics (`unfinished_steps`) parks retryably as `agent_execution_failed` with
       an execution-failure notice explaining that cancelled or partial command output was not accepted and the
       operator told to reply `/orchestrator continue`. A quota notice (`_is_session_limit_message`) and a transient
       provider refusal (`agents/provider_failures.py`'s `is_transient_provider_failure` — `API Error: 529 Overloaded`
       and its 5xx siblings) are the CLI's rather than the agent's, so both park retryably as `agent_silent` with the
       operator told to reply `/orchestrator continue`; any other non-empty message is posted as a real HITL question
       (`park_reason=None`); an empty one is the silent-failure park (`agent_silent`).
- **Output**: one of four. A pushed branch + open PR + the report on it + label moved to `workflow:validating`; a
  pushed branch + open PR whose report is still owed, unparked and still on `workflow:implementing` for the next tick
  to finish; an **unpublished** committed candidate held under `workflow:decomposing` for size adjudication, with no
  branch pushed and no pull request opened; or a HITL park — the ordinary question / dirty-tree / unreadable-tree /
  timeout ones, `report_undeliverable` for a report or description the publication could not deliver (before the
  push, where nothing is published, and after it, where the code stands and only the handoff is withheld), plus the
  size gate's own
  `late_measurement_failed` (a reading nobody could take, a record too damaged to act on — a missing base where one
  was recorded, a missing ceiling or boundary either way, an identity the late domain's record gate refuses, or a
  `late_current_issue` naming another issue — or a recorded commit this host cannot show; a base the transport could
  not reach reaches it only once the pair has lost the readings the bounded quiet retry allows it) and
  `late_candidate_moved` (the checkout is not the one the gate
  approved — a head somewhere else, a commit not on this host at all, or a tree carrying work no push would
  publish — so nothing was published and nothing was spawned rather than hand review a checkout the gate never saw
  or buy a second developer run for an implementation that is already written; the approved commit is on the record
  as `late_approved_sha` from the write that approved it, and `implementing/checkout_recovery` clears the park
  itself on the tick the checkout is back on that commit with a provably clean tree, publishing with no agent). The
  retirement that precedes a publication is held inside the observations owner's retirement window, so a close
  arriving as the record stops naming its cycle ends the cycle rather than being dropped: nothing is pushed, no pull
  request is opened, and the issue is not relabelled.

## `_handle_documenting` (label `workflow:documenting`)
- **Trigger**: each tick while the label is `workflow:documenting`. Set only by the **final-docs handoff** in
  `_handle_validating`'s approval branch (after verify + squash); the docs pass runs exactly once per
  reviewer-approval handoff, between approval and `in_review`. A PR may visit `workflow:documenting` more than once:
  if PR feedback bounces the issue to `workflow:fixing` and the dev pushes a fix, the next approval triggers another
  final-docs pass. Also runs on closed-`workflow:documenting` issues so an externally-merged PR finalizes to `done`.
- **Input**: pinned `pr_number`, `branch`, `dev_agent` / `dev_session_id` (the docs pass reuses the locked dev spec —
  there is no separate `documenting_agent`), plus `docs_checked_sha` / `docs_verdict` / `silent_park_count`.
- **Internal flow**:
  0. **What `validating` still owes goes back to it** (`_hands_back_what_validating_owes`), with nothing written --
     asked once steps 1–3 below have let the tick through, so a merged or closed pull request finalizes whatever the
     approval's reading would say, and ahead of step 4's drift block and the docs pass. The approval that moved the
     label here retires its own `review_returned_verdict` ahead
     of that move and drops its own `late_collapse_handoff_sha` in a write BEHIND it, so a readable verdict or
     handoff record still on the comment when this stage runs is that write having failed, that approval leaving
     its own record standing over a report, `pr_number`, or evidence record that moved while the relabel ran, or
     another road's record put down then — a later verdict, or a squash handoff in place of the one being finished —
     and nothing here can tell which. Neither is this stage's to act on or to end, so the label goes back to
     `workflow:validating` with both left standing: the recovery ahead of the reviewer moves the label here again
     only while the approval still covers the report, requirements, and head a handoff names, ending the record
     behind that move, and otherwise drops it for the review; a waiting verdict holds the label there for the road
     that finishes it. That also keeps this stage from ever running with a record standing, which a later return to
     `validating` — step 4's drift unwind among them — would otherwise answer by relabelling the unchanged head
     straight back here. No handoff record stands over what moves once that record is ended behind the relabel —
     nor does a report edited or removed in place, which moves no record at all — so the approval
     itself is asked beside the records (`review_coverage._approval_stands`): one that no longer covers the
     `developer_report_current` the comment records (`review_approved_subject`), or that report as it reads at its
     location now, or whose `review_approved_evidence` no longer stands — the records and the artifact re-read as
     below — or over evidence its squash carried onto the head whose review subject no longer stands
     (`verification_current.carry_answers`), or that no claim names, goes back the same way, for the reviewer —
     `validating` invalidating the carry ahead of any round — and a report or evidence nobody could read holds the
     tick without moving the label. A relabel that fails raises; the records are still there for the next tick. An
     ordinary tick carries neither record and an approval of what the comment carries, and costs one reading of the
     report at its location — and of the evidence, for an approval proved over any — and one of the pinned comment
     behind them (`_approval_still_stands`): those readings are requests long enough for another road to settle a
     later report, persist a verdict, record a later verification revision, or replace or remove a review subject or
     the approval's evidence claim, so where the report, `pr_number`, verdict, evidence, or approval records moved
     the issue goes back too, and whatever else moved is carried onto the state the docs pass writes, rather than
     written back over.
  1. **External-merge / closed-issue short-circuit** (identical to `_handle_implementing`).
  2. **`pr_number` missing → park** with `missing_pr_number`. Documenting only runs against an existing PR worktree.
  3. **`/orchestrator continue` refusal** (`_refuse_parked_continue_command`, run BEFORE the drift block). A bare
     continue on a park needing a real answer consumes the command and posts a refusal (`_refuse_parked_continue`) once,
     then stays parked. A retryable session-failure park (`agent_silent` / `agent_timeout` / `agent_execution_failed`)
     and a command carrying genuine guidance both fall through: because a bare continue no longer shifts
     `user_content_hash`, the drift block below stays silent (no spurious `routing back to validating`) and the retry
     reruns the FULL docs pass through the awaiting-human resume (step 10). The parser + classifier are shared with
     `_handle_implementing` / `_handle_fixing`; documenting has no preserved feedback batch, so only the refusal needs
     interception here.

     The batch that classification reads is cut from what the park ASKED (`parks._asked_since`) rather than from
     the delivery cursor, and on a half-finished drift unwind those are different comments: step 4's failure road
     holds the cursor back over input nobody delivered and records its own notice as `docs_drift_unwind_asked_at`.
     Cut from the cursor instead, the instruction that triggered the unwind would sit in the batch beside the
     command and demote it to "continue plus guidance" — so the operator's bare nudge would fall through and re-run
     the reconcile rather than earning the refusal this step exists for. The refusal delivers nothing either, so on
     that road it moves the unwind's boundary past what it refused and leaves the delivery cursor where the park
     left it, both in one write.
  4. **User-content drift → relabel back to `workflow:validating`** without spawning the docs agent. A title/body edit
     (or fresh human comment) during the final-docs hop invalidates the prior approval, so the reviewer must
     re-evaluate before any docs work can land. Housekeeping: post a `:pencil2: routing back to validating` notice,
     refresh `user_content_hash`, clear park flags, reset `review_round=0`. No feedback watermark moves: no agent
     runs on this road, so the comment that moved the hash was delivered to nobody and stays unread for the reviewer
     the relabel hands the issue to. The refreshed hash is not about that comment — it says this stage has already
     rerouted for the edit, which is what keeps the next poll from announcing it again.
     Reconcile the PR worktree (fetch, then probe ahead/behind; on `ahead > 0`, `behind > 0`, or dirty files run `git
     reset --hard <remote>/<branch>` + `git clean -fd`) so no docs work authored against the pre-drift requirements
     survives. `docs_drift_unwind_pending` is set while the cleanup is in progress and cleared only on the relabel
     back to `workflow:validating` — with `docs_drift_unwind_asked_at` beside it — so an operator unpark on a parked
     cleanup re-enters the drift block instead of falling through to a docs spawn.
  5. Awaiting-human + no new comment → early return BEFORE the fetch so a transient `fetch_failed` / `diverged_branch`
     doesn't re-post its park every tick.
  6. Ensure the PR worktree (`_ensure_pr_worktree`, restored from `<remote>/<branch>` so the dev's commits are intact)
     and refresh via `_authed_fetch`. Failure parks with `fetch_failed`.
  7. Divergence reading vs. the just-fetched `<remote>/<branch>`. The ref is resolved once and HEAD is counted
     against that immutable commit, so the counts and the head they were taken against name the same tip — read
     twice, a ref something moves in between leaves the branch proved against one head and the push pinned to
     another, and where the pull request has moved to the second that lease is satisfied and the force-push lands on
     top of it.
     - **unreadable** → park with `unreadable_divergence`, before the spawn and before any push. A ref nothing could
       resolve, a comparison git refused, and a count in a shape nothing can parse all answer `(0, 0)`, which is what
       an in-sync branch answers — collapsed into that, a stale checkout is spawned over and force-pushed, and the
       head that push is pinned to is empty, which has the size gate adopt whatever the pull request has moved to.
     - `behind > 0` → park with `diverged_branch` (force-pushing would clobber the real PR head).
     - `ahead > 0` recovered commits → synthesize an `AgentResult` and skip the agent; the unified branch below pushes
       the recovered docs commit, pinned to the tip this count was taken against rather than to whatever the pull
       request is standing on by then.
     - `(0, 0)` → fall through.
  8. **A pass whose commit the pull request already carries** (`_finished_settled_docs`), asked between the reading
     above and the run below. A `docs_settled_sha` receipt is left by any tick that published and did not finish. The
     size gate in step 12 **held** an oversized docs commit off the pull request and handed the issue to the late
     coordinator, where an adjudicator's `single` parks for a human's decision and an authorized settlement publishes
     that commit from there and hands the label back here with only the handoff owed. Or the gate **allowed** the
     push, it landed, and the tick died before this stage could record it — the receipt rides the gate's own write
     either way, which is ahead of everything this stage does with a landed push, and it is the write RECORDING the
     pass that drops it, so a receipt read here is one no handoff has been made for. So the receipt is read back, and
     where the branch is in sync AND the checkout is standing on that exact commit this tick stamps `docs_checked_sha`
     / `docs_verdict="updated"`, announces the handoff, and advances to `in_review`, with no agent run and no push.
     Without that receipt the tick would read a branch in sync with its remote as an issue no docs pass has run for
     and spawn a second agent over work that is already published. Ahead of the remote the receipt stands and the
     `ahead > 0` road republishes it through the gate, which is the one road that measures it again; a receipt that is
     not a whole object id, or a head this host cannot peel, likewise leaves it for a tick that can prove it — in sync
     is not the same claim as CARRYING it, since a replacement host rebuilt from a pull request that has moved on
     reads level with its remote too.
  9. Whichever shape runs below, the `docs_verdict` an EARLIER pass left is dropped as this one begins. Every shape
     re-anchors `docs_checked_sha` to the head it is about — the resumed dev that adds nothing to a commit already
     waiting anchors on that very head — so a stale verdict beside it would say a pass has FINISHED for the head this
     one is only starting on — which the in_review merge gate reads as a head this orchestrator has documented, and
     pings as ready for a human to merge, from the moment this pass spawns until it finishes.
  10. Awaiting-human resume: rebuild the FULL docs prompt via `_build_documentation_prompt` (this may be the first time
     the session sees the docs-stage instructions), persist `docs_checked_sha=before_sha` BEFORE the spawn, then
     `_resume_dev_with_text`.
  11. Fresh spawn: snapshot `before_sha`, persist `docs_checked_sha=before_sha` and `dev_agent` BEFORE invoking the
      agent, build the prompt (issue body + recent comments + `DOCS: NO_CHANGE` marker contract), then run.
  12. Branch on result. Every success exit routes to `in_review` via `_advance_after_docs_push` /
      `_advance_after_docs_no_change`, which ratchets `pr_last_comment_id` past any issue-thread reply the resume
      consumed — the reply is dropped by in_review's own delivery-cursor read either way, so what the ratchet buys is
      a watermark that does not leave the next stage re-reading that span. Both end the same way and the order is
      the crash contract: **stamp, announce, persist, relabel** — one durable write, and the relabel behind it. The
      notice comes before the write because posting one RECORDS it: the comment id lands in
      `orchestrator_comment_ids`, which is what has the watermark walk seed past it and the in_review feedback scan
      drop it rather than resume a dev over an informational post of ours, and there is nothing behind the write to
      carry it. The write comes before the relabel because `in_review` repairs nothing it is handed: its merge gate
      pings only for a head that `docs_checked_sha` names with a `docs_verdict` beside it, so a relabel taken first
      strands the issue on a stage whose handler never looks at either. That same write drops `docs_settled_sha`,
      and it has to: the receipt says a published pass still owes a handoff, and held past this write to cover the
      relabel it outlives the handoff whenever the write that would drop it does not land — leaving a record a later
      `validating` approval at the same head consumes, skipping the docs pass that approval just bought. Two windows
      are left and both fail toward doing the work again: a tick that posted its notice and died over the write
      comes back with nothing on the record saying so, and step 8 announces it a second time; a tick whose relabel
      did not land leaves the record a same-head re-entry leaves, so the next tick runs the pass rather than handing
      off on evidence that could belong to either. Branches:
      - `interrupted` (shutdown sweep killed the run mid-flight) → ignore the partial result and return WITHOUT writing
        pinned state (the pre-spawn `docs_checked_sha` / watermark writes are discarded), so the next process
        re-runs the docs pass. Precedes every branch below. The recovered `ahead > 0` path synthesizes a
        non-interrupted result, so it is unaffected.
      - `paused` / `backlog` applied mid-run → same short-circuit as `interrupted`: `_paused_during_agent_run`
        re-reads a FRESHLY fetched issue after the initial-docs and awaiting-human resumes, and on a hit the handler
        returns WITHOUT pushing, posting the docs notice, advancing to `in_review`, ratcheting watermarks, or writing
        pinned state. The committed docs work stays on the branch and republishes through the `ahead > 0` recovered
        path once the label is removed (the recovered path itself runs no agent, so it observes no live-pause window).
      - `timed_out` → park (`agent_timeout`).
      - dirty worktree → `_on_dirty_worktree`: park.
      - new commit on a clean tree → **its subject normalized to one pull-request reference**, then the **size gate**
        every push onto an open pull request goes through (`implementing/late_push._publishes`, reached from
        `documenting/publication._push_docs_and_advance`). Under `PR_REF_IN_SUBJECT` (default on)
        `documenting/subject` hands the subject of the commit this pass read to the shared
        `git/publication/pr_references` normalization — with this issue's number as well as the pull request's, so a
        subject the agent left ending in the tracked issue's reference, alone or beside one an earlier publication
        appended, comes back ending in ` (#N)` for the request alone — and replaces that commit through
        `git/publication/commits`, under the same hardened envelope the approval squash is made with (detached
        global and system config; hooks, fsmonitor, and signing off; `AGENT_GIT_*` as the committer). The
        replacement is bound to that commit by id,
        never to HEAD: `git commit-tree` rebuilds it from the commit's own tree, parents, and author, so only the
        subject and the committer differ and no landing commit is added, and `git update-ref` moves HEAD onto it only
        if HEAD is still that commit. A checkout something committed on after the pass read its head refuses the move
        instead of having the newer commit rewritten and handed to a gate that would accept it for being named. HEAD
        is then read back before the gate is entered, and the replacement's id — the one git created, not the one
        HEAD reads — is handed on only where HEAD is standing on it. The message is read and written back as the
        bytes git stored, so a CR LF body or a lone carriage return survives the rebuild, and only the subject's own
        text changes, its line ending kept. That replacement is what every id past it
        names: the candidate measured, the `docs_settled_sha` a hold leaves, the approval and receipt a push leaves,
        and the pushed revision. `docs_checked_sha` is re-anchored on the published commit before the gate is
        entered, so a routed hold, a failed push, and a receipt each go down beside the commit the rest of the record
        names rather than beside a head the pass merely began at — taken whenever the switch is on rather than only
        where the id moved, since the recovered road anchors no head of its own and would otherwise leave a stale one
        there. A hold the gate REFUSED rather than routed measures, records, and publishes nothing, so that anchor
        goes back to the head the pass began at. A subject the normalization hands back as written — one
        already ending in this request's reference and carrying none to the tracked issue, which is a commit an
        earlier tick amended and never pushed, or the retry of a failed push — is published by the id already read,
        with nothing amended, and the gate still proves the checkout against it; `off` reads
        no message and publishes the commit as made; and `SQUASH_ON_APPROVAL=off` does not reach it, since this is
        the orchestrator's publication either way. A message that cannot be read, a replacement git will not create,
        a moved checkout, or a HEAD that does not read back as the replacement parks `subject_amend_failed` before
        the gate, with nothing measured or pushed. The drift
        unwind (step 4) amends nothing, because the commit it resets away is never published. What the gate counts
        is what the pull request comes to WITH the docs commit in it, against
        `MAX_ADDED_LINES`; the push it
        licenses is named to the commit this pass made and pinned to the head the pass was entered on — the tip the
        step 7 fetch read — so a pull request somebody pushed to while the agent was out refuses the push instead of
        being adopted as its lease. What comes back is `held`, `landed`, or neither, and `held` is **not** one
        outcome — it means only "this tick is finished, publish nothing and hand the issue on to nothing", and the
        three ways to earn it differ in everything else:
        - **oversized** → the adjudication hold. Nothing is pushed, no docs verdict is stamped, no `in_review`
          handoff is made, the issue is relabelled `workflow:decomposing`, and the head the pass produced goes down
          as `docs_settled_sha` inside the gate's own routed write, ahead of that relabel (step 8 reads it back).
        - **a reading the gate could not take** → a park, not a relabel. A tree that is not provably clean, a pull
          request nothing could read or one that is closed or merged, a caller-named head that is no whole object id
          or that disagrees with the head the gate reads, a head that moved off what a live record froze, a count
          that never happened, or an approval whose lease cannot be read: each parks `late_measurement_failed` with
          nothing pushed, no label moved, and no `docs_settled_sha` written.
        - **the push landed and the checkout stopped being what went out** → the publication stands and only the
          HANDOFF stops. The branch and its pull request carry the commit, the receipt and the debt are settled, and
          the issue parks (`late_candidate_moved` for a head that moved, `dirty_worktree` for a tree dirtied under
          the push) so the reconciliation ahead of the next handler restores the checkout rather than handing a
          reviewer one nobody read.

        **Landed**: record `docs_checked_sha` as the commit that went out — the amended one where the subject was
        amended — plus `docs_verdict="updated"`, reset `silent_park_count=0`, drop `docs_settled_sha`, post
        `:books: documenting pass: pushed docs commit.`, persist, and advance — once.
        **Neither** (allowed, and the push itself failed): park
        (`push_failed`), with the commit that is owed a publication and the head to pin it against left on the record
        for the retry.
      - no commit + `DOCS: NO_CHANGE` verdict: when `ahead > 0` the recovered commit goes through that same amendment
        and gate and earns the same answers — the verdict certifies the local tree and says nothing about what the
        remote carries or what its subject names;
        otherwise persist `docs_verdict="no_change"`, post `:books: no docs changes required.`, and advance without
        pushing.
      - no commit + unknown verdict → `_on_question`: park.
- **Output**: label moved to `in_review` (success), OR `workflow:validating` (drift unwind), OR
  `workflow:decomposing` (a docs commit the size gate held), OR terminal `done` / `rejected` (short-circuit), OR a
  HITL park.

The docs pass is deliberately a thin dev-session rerun on the existing PR worktree rather than a separate role: there is
no `documenting_agent` pin and no separate retry budget. The dev session resumes on its locked `(backend, args)` spec,
so `DEV_AGENT` flips made mid-flight do not retarget the docs pass either.

## The size gate on a published pull request (every push onto an open PR)

Every push onto a pull request the remote already carries goes through the same late size gate
(`implementing/late_push._publishes`, over the `late_overflow` entry, the `late_publication` answer, and the
`late_gate` owners that answer for the implementing seam too). There are nine
such pushes and no others:

- the shared dev-fix publication `validating/dev_fix._publish_dev_fix` (the reviewer's `CHANGES_REQUESTED` loop, the
  awaiting-human resume, and the body-edit drift resume an open PR takes). It proves the checkout's tree for itself
  before the push, in both halves — paths git named and a `git status` that established nothing — and parks through
  `implementing/checkout_parks._on_unpublishable_tree` on either. The gate's own tree proof rides the entry it
  freezes, which `DECOMPOSE=off` never takes, so the unreadable half would otherwise reach the remote on exactly the
  installs that measure nothing and be answered by the post-push proof, which holds the handoff over a commit the
  pull request already has;
- the fixing handler's no-feedback bounce `fixing/handler._publish_stranded_fix`;
- the two `validating/recovery.py` retries that finish a deferred push or a commit a timeout killed the disposition
  before it saw, both through `_publish_recovered_fix`;
- the conflict resolution `conflicts/outcomes._finalize_conflict_resolution`;
- the recovered-commit publication `conflicts/divergence._push_recovered_commits`, which ships a resolution an
  earlier tick committed and never pushed;
- the clean-rebase publication `conflicts/publication._publish_clean_rebase` — the last of these is also the only
  seam outside the squash that hands the gate a rewrite's before-state, since it is the only one that ran the
  replay it is publishing — those three, plus the body-edit resume
  through the shared dev-fix seam, are what
  [`workflow:resolving_conflict`'s content updates](#content-updates-onto-the-pull-request-this-stage-already-has)
  are made of;
- the base-sync auto rebase `workflow/engine/rewrite_publication.publishes`, its crash recovery's retry of a
  replay nothing published `workflow/engine/rewrite_retry.retries`, and that recovery's settlement of a push that
  already landed `workflow/engine/rewrite_landed.recovers`, the callers that hand the gate a transport of
  their own -- one and the same (`rewrite_publication.CandidatePush`, an `implementing/late_transport.Transport`): the
  git owner reads the checkout and the remote again
  (`git/base_sync/rewrite_transport._refused_before_the_push`), refusing where the checkout, the base, or the remote
  moved since the candidate was read, and then pushes exactly that candidate leased to the head it replaced
  (`_pushes_the_candidate`) -- or, for a remote already standing on it, proves that with a push of the candidate
  leased to itself (`_proves_the_landing`). The gate asks its ending barrier between that reading and the push,
  whatever the reading answered, so a close or merge landing while the remote is read holds the tick even where the
  reading refused the push, and the proof and settlement after the push are this gate's as for every other caller.
  Of the auto rebase's own crash recovery, the retry of a push that never went out and the leased no-op that receipts
  one that did are both the workflow's, and enter the gate as the ordinary publication does -- the no-op as the proof
  of a remote already standing on the candidate, which sends nothing. The
  recovery is the one caller that can enter `permit_only`, and it does so for the replay of an
  adjudicated commit: it is finishing a publication rather than deciding one, so the cumulative reading is the wrong
  answer twice over and `late_gate`'s `_permitted_only` asks the permit and nothing else. `late_freeze` keeps such a
  caller inside the gate whatever `DECOMPOSE` says, since the permit is asked over the entry only the gate freezes. A
  refusal is handed back as `refused` rather than parked or routed — nothing was measured, nothing was decided — and
  the recovery parks: the reissued push resets onto its anchor first, and the no-op keeps HEAD where the remote
  already carries it;
- and the final documentation pass `documenting/publication._push_docs_and_advance`.

One more seam pushes without measuring, and it skips the reading for a reason and nothing else beside it.
`decomposition/late_verdict_push`'s `_publishes_approved` ships a commit a human's adjudication already accepted:
the checkout is re-proved, the push is named and leased from the record, and the debt is spent exactly as it is here.
`git/publication/squash` is not one of them: the squash-on-approval goes through the whole gate, through
`late_rewrite`. What it publishes is a NEW object — a squash collapses the approved commits into one commit that did
not exist when any earlier push was measured — so that commit is the candidate, proved, frozen against the base the
remote names now, counted, and either pushed or held. Measuring the head it replaces would gate one commit and
publish another. The count it earns is ordinarily the one the last gated push already answered, because the tree is
the same tree; ordinarily is not always, since the BASE moves, and this is the last push before a human is asked to
merge. A **routed** candidate is deliberately not rolled back: the squashed commit is what a settled verdict
publishes from the branch, so restoring the pre-squash head would leave the record naming a commit this host no
longer has — and the approval handoff stops without parking, since the gate owns the issue from there.

One squash is not counted at all, and it is the one the exemption would otherwise punish. Where the head being
rewritten is the exact commit an authorized settlement accepted, the squash hands the gate its own before-state — the
head it replaced, the merge base both sides are read over, and the publication it was entered on — and `late_transfer`
may carry the exemption onto the object it produced. Only over the whole of the evidence: a semantic record whose
exempt commit is the one being rewritten and which proves itself when re-fingerprinted over its own recorded pair, no
authorization this build cannot read already standing for that exemption, a publication this call itself froze and the
issue still records, a provably clean checkout on the squash, an issue re-read open, unpaused and still on the stage
the rewrite was entered from, and a rewritten contribution that fingerprints to the same digest. The PERMISSION is
durable before the push, in ONE write that also records the debt that push is owed — split in two, a crash between
them leaves a one-commit branch the next squash reports success on without pushing. The exemption does not move there:
that rotation belongs to the receipt of the landed push, which `late_rotation` stages into the push tail's own
settlement, so a verdict is never left on a commit no remote carries — and only where the permit itself proved out on
that tick, since a refusal sends the rewrite to the ordinary gate, which publishes it whenever the count is under the
ceiling. What that receipt leaves on both observability streams is one bounded `late_transfer` record naming both
pairs, the pull request, the rewrite kind, and which reading proved the publication — the leased force-push that moved
it, or the leased no-op a recovery finds it already standing on. That record is `late_transfer_telemetry`'s rather
than the rotation's, asked by the push tail past the settling write, so nothing is reported for a move GitHub
refused — and a process lost past that write is reported by the reconciliation ahead of the next handler, from the
proof the settlement kept — best effort, and repeated only where the drop of that proof does not land. A digest the
standing permission already recorded is held to the reading the permit
just took, since a grant that carried on would write its own answer over evidence nobody checked. Refused, nothing
changes and the squash is measured exactly as above. And the permission is droppable in exactly one window — a
force-push the remote refuses
resets the branch back onto the commit the exemption never left, so the rollback takes the permission back and nothing
else, while past the receipt the pull request carries the rewritten commit and there is nothing to take back. The squash
is not the only rewrite decided on those terms: the per-tick base refresh publishes a clean rebase of the same branch
once this stage has handed the issue on, and it hands the same gate the same evidence
([`labels-and-state.md#base-refresh`](labels-and-state.md#base-refresh)).

The conflict stage's clean rebase is the third rewrite an exemption may ride, and it reaches it from the other end.
That refresh does not drive `workflow:resolving_conflict`, so the replay a branch which has stopped merging cleanly
needs is this stage's own — and so is the account of what it replaced. So
`conflicts/publication._publish_clean_rebase` reads the pre-rebase head and the fork point that head's contribution
was read over BEFORE the replay destroys both, and hands them to the gate through `conflicts/evidence`, which builds
the record and decides nothing. That head is also the head the force-push is leased against, which is where this
differs from the squash: there the collapsed head and the lease are two facts. The two contributions are read over
two DIFFERENT fork points, because moving the base is the whole of what a rebase does, and `late_transfer` grants
the permit only over everything above — including that the two fingerprint alike, and that the fork point the replay
landed on is a commit the remote's own base branch reaches. That second one is what a fork point cannot say for
itself: it is taken against `refs/remotes/<remote>/<base>`, which lives in the object store the issue's agent writes
to, and a replay onto a base carrying work no remote has fingerprints as exactly the adjudicated change while the
commit it produced carries that work as well.

The replay also writes itself DOWN, because the tick that runs one is not always the tick that publishes it. The
head it is about to replace, that head's fork point, and the pull request it is being made against go onto the
pinned comment before the rebase runs — the `conflict_replay_*` group in
[`labels-and-state.md`](labels-and-state.md#pinned-state) — and the commit it produced is stamped on before the size
gate is entered. That record is what a crash between the replay and the gate leaves behind, and the tick that finds
it reads it twice. A replay moves the branch off the head it replayed, so the checkout comes back ahead of the pull
request AND behind it — the shape `_guard_diverged_worktree` parks, since a stale branch carrying somebody else's
commit reads the same. The record naming that head, that commit and that pull request is what lets it past, leasing
the force-push to the pre-rebase head; then `conflicts/divergence._push_recovered_commits` reads it again for the
evidence it hands the gate. It is read only where it is about the publication and the commit in hand: the pull
request it names has to be the one the issue still records, the head it names has to be the head that push is leased
against, and the commit it names has to be the one the checkout is standing on. The publication is on the record
rather than read live because `pr_number` can be repointed in between, and a replay offered as a rewrite of some
other open pull request standing on the same head would satisfy every check the permit makes.

Nothing else this stage publishes presents evidence, and the reason is that nothing else can say what it is
publishing. Every other push here carries a commit somebody ELSE made — a resolution an agent authored over
conflicted files, the unpushed FIX commits the `fixing` dead-lock reroute sends over, a commit made on top of a
replay — and no reading off the branch tells those from a replay. Being on base tells them apart least of all: that
reroute fires on an on-base unpushed commit as readily as on a stale-base one, which is exactly why the record
rather than a probe is what the recovery turns on. Past the grant the permission takes over: `late_transfer` falls
back to it when a caller presents nothing and re-asks the whole permit over it. The dev-fix publications, the
reviewer's fix loop, and the documentation pass are the same rule one stage over. All of them go through the
ordinary cumulative gate — and a replay that changed a single covered byte joins them, since it fingerprints to a
different contribution and earns the fresh late adjudication any oversized candidate is owed. So does a descendant of
the exempt commit, and so does a rewrite judged alike on anything short of the fingerprint: an addition count, a commit
subject, a similarity score, and a `git patch-id` can each agree over a different change
([`labels-and-state.md#exemption-identity-and-rotation`](labels-and-state.md#exemption-identity-and-rotation)).

A candidate whose count never came back keeps the rewrite too, and for the same reason read one step earlier: the
freeze is durable and the diff is not, so a reading that fails leaves a live generation naming the **squash** with no
number on it — and the reconciliation ahead of the next handler answers that pair by measuring the checkout it was
frozen on. Restored, the record names a commit the branch no longer has and every later tick refuses it as a
candidate that moved, so the measurement is never retried. The rule the two share is one: the branch may go back only
where nothing durable is left pointing at what is on it.

A **refused** one is that, and is told apart before anything is restored. The entry read that runs before
the reset cannot cover the window the reset and the commit sit in: a human closing the pull request, or somebody
pushing to it, is visible only to the gate's own second reading — and closing one does not move its branch, so no
lease and nothing local would notice. There nothing was measured, nothing was pushed, and nothing was recorded — an
entry that could not prove itself deliberately persists no generation — and leaving the commit on the branch is a
fail-open: a one-commit branch takes the nothing-to-squash road on the next
tick and reports **success** without measuring or publishing anything, so reviewer-approved work reaches the merge
button neither counted nor on the remote. So the branch goes back to the commits the reviewer approved and the retry
squashes, measures, and publishes them afresh. It still reports `held` — the gate has already parked with the notice
its own reading earned, and a squash-failed park on top of that would describe a failure that did not happen. Two
other holds keep the rewrite for the same reason the recorded ones do: a push that LANDED and only held the handoff
(the receipt names the squash, so the remote carries it), and a checkout something committed over (a reset would
destroy work nobody here can account for). The debt counts as a record too, and it has to: a transfer whose grant
landed and whose push the remote took leaves the **approval** naming the squash while the receipt still names the
head that squash was pushed over. A reset there would take the checkout off an object the remote already carries.

The transfer's own write is handled where it happens rather than allowed out: a refused grant puts its staged
payload back and falls through to the ordinary reading, so a lost write costs the permit and not the tick.

The squashed commit is checked on **both sides** of that gate. The gate proves the checkout for itself, and a first
generation has no record to prove it against, so something committing over the worktree between the squash and the
freeze would be measured and published in its place while the caller went on to record the id it made. Refused
before, nothing is measured and nothing goes out; refused after, it is asked of the commit the gate actually decided
about, which is the only reading no window sits inside. Neither rolls back — whatever moved the checkout made a
commit nobody here can account for. A push that was allowed and then FAILED does roll back, and drops the approval
it abandons in the same breath: the gate records the squashed commit as one still owed a publication before the
push, and the reset leaves that commit only in the reflog, so a debt naming it would stop every later tick for a
publication that is never coming.

Every one of those resets takes the **ref and the index and leaves the working tree alone**, which is the difference
between restoring a branch and destroying work. A squash is a collapse rather than an edit — the commit it makes has
the same tree as the head it replaces — so on a checkout nobody touched, taking the working tree too would land in
exactly the same place. The two part where somebody wrote to the worktree between the squash and the reading that
refused it, which is the gate's first refusal: a tree that is not *provably* clean. Taking the working tree there
would throw that edit away to undo a squash it had nothing to do with, and it is the one repair a human cannot get
back. Left where it is, it survives the restore as the uncommitted change it was, and the retry refuses on the same
tree — the planning probes stop on a dirty worktree — rather than collapsing it into a squash nobody asked to carry
it.

The entry is asked twice, and the first time is not redundant. One refusal there is a hole no lease covers:
**closing a pull request does not move its branch**, so a `--force-with-lease` succeeds against a publication nobody
can merge. Asked before the reset that rewrites the branch locally, a closed, merged, or unreadable pull request, a
dirty tree, or a head that moved costs a refusal with the reviewer-approved commits exactly where they were — and
the approval handoff parks and stays in `validating`, which is what it already does for every other squash
failure.

A rebase may not happen inside that window either. `late_collapse_*` freezes the branch out of the pre-tick base
refresh on the same terms the size gate's own records do, and on the strictest reading of the three — the key being
on the comment at all, `null` included — because that is exactly what the squash's own reader counts as a claim it
must refuse. A rebase there replaces the collapse with a commit carrying the base advance too, so the tree proof
below stops answering and the pull request is left on the history the record says was collapsed with the rebase
already force-pushed over it. The freeze ends when the record does.

A squash says what it is about to do before it does it, and that is what closes the window neither reading covers:
the process itself dying. The head being replaced, the base it is rewritten over, and how many commits go in are
written to the pinned comment between the entry and the reset (`late_collapse_head`, `late_collapse_base_sha`,
`late_collapse_count` — see
[`labels-and-state.md`](labels-and-state.md)), because past the reset none of the three can be read
back off anything: the head is off the branch, the base is not derivable from the object that replaced it, and the
count is gone with the commits it counted. That count is **walked** rather than taken from the commit subjects
beside it: `git commit --allow-empty-message` makes a commit that contributes no subject and one commit, so a count
derived from the subjects is short by however many of those a branch carries — which would record three commits as
two and have the recovery refuse a collapse it really made as miscounted, and read a branch of two as the single
commit that takes the nothing-to-rewrite road. The record covers the **one-commit subject rewrite** on identical
terms and records `late_collapse_count=1` for it: that branch carries one commit before the reset and one after, so
it is the shape whose interruption the branch itself cannot show at all. A write GitHub refuses stops the squash
rather than running it unrecorded — the approved commits stay where they are and the next tick tries again.

That write is a **request**, so the head and the tree are proved once more when it comes back. The worktree is
writable for the whole of it, and the reset behind it is `--soft`: the commit that follows takes the INDEX, so a
change staged in that window would be collapsed into the squash and force-pushed onto the pull request as work a
reviewer approved. Both halves refuse, the record of a rewrite that never happened goes with the refusal, and the
notice says which of the two moved — a tree that went dirty leaves the approved commits exactly where a human will
look for them, a head that moved has not been shown to.

The tick that comes back reads that record before it reads what is on the branch, and the order is the whole point:
a rewritten branch and a branch with nothing left to rewrite both carry one commit, under a subject of the same
shape. It also proves the record before it compares it to anything, the road that DROPS the record included — a head
edited onto the commit a finished collapse left reads as a reset that never landed, so a shortcut taken for one
would drop the record and hand on a branch of one commit, which is the nothing-to-rewrite road reporting success
over a remote still carrying the history the record names. What that road still owes is read rather than skipped:
the branch a record is dropped over is entered on its publication before it is handed on, so a remote that moved off
what the record named refuses there. Past that proof, exactly one branch may be dropped over: the one the record
still describes exactly, standing on the head it names over the commits it counted, which is the tick that died
before the reset ever ran. That drop is safe because the branch is the one the record was written over — the ordinary
squash collapses exactly the commits an approval was given for, and it cannot report success without pushing them,
since it goes through the entry, the rewrite, and the push and refuses if any of them will not have it.

Every other shape refuses. A head that matches over a different number of commits is a branch something rewrote
while the record went on naming its old tip. A branch carrying **nothing** over its base is the shape the ordinary
squash could not be trusted with: there is no rewrite left to finish and no history left to rewrite, while the
remote still carries every commit the record names. And a branch that MOVED off the recorded head is refused
whichever way it went, because nothing here can say who moved it — this recovery owns the tick from the moment a
record goes down, ahead of every route that could resume a developer, so work on top of the recorded head is work
nobody in this workflow made and squashing afresh would force-push it onto the pull request as history a reviewer
approved. The two ways it moved are still told apart in the notice, since what an operator does next differs: a
recorded head still reachable from the branch has the approved commits under whatever was committed over them, and
one the branch replaced has them only in the reflog.

The rest are **resumed** through the same leased publication the squash itself would have made — entered on the head
the record names, handed the pair the record holds as the transfer evidence no plan is left to supply, and finished
with the count only the record still has. A collapse that landed locally is measured and pushed; one the gate
already approved publishes on that approval; one an outstanding transfer permission licensed is re-asked in full and
publishes unmeasured; one a receipt says this issue's own push already put on the pull request is entered on the
*rewritten* commit instead, so it is the leased no-op that settles the receipt, the debt, and the exemption rather
than a second reading of work a human already ruled on; and a settled receipt whose handoff never finished is that
same state one step on, finished with the notice and the relabel it was owed.

No road above is taken over a tree this host cannot **prove** clean, the one that hands the branch back to the
ordinary squash included. The planning probes refuse on what git *named*, so a status that established nothing reads
to them as a clean tree; an install with `DECOMPOSE=off` freezes no entry, so nothing behind the rewrite proves
a tree either — and the terminal-safety barrier that *does* read the recorded pull request on every install reads
only whether it has ended, which is no tree proof. Between those two there is nothing else standing between an
unreadable worktree and a force-push, which is why the proof is owed before anything is classified rather than only
before the road that publishes.

None of it runs on the record's **shape** either, and neither does any road above it. A whole-looking record is one
somebody could have written, not one this repository ever produced, so four things it claims are proved against the
objects before any of them are compared to the branch: both recorded ends peel
to commits this host really holds, the recorded base really is a commit the recorded head was built on — a walk
between two histories that never met reports a number like any other, so the count is no ancestry proof — the history
between them really is the number of commits the record counts, and the commit on the branch carries both the tree
the recorded head left *and* that base as its one parent, which is what a squash produces exactly and by
construction. The parent is not decoration: the same tree re-parented onto a base that has since advanced is a commit
that *reverts* whatever that base added, and a tree comparison alone would push it onto the pull request under an
exemption a human granted a different change. A record that fails any of them
leaves the branch untouched and refuses, because every other refusal here knows what the branch is standing on and
can put it back while this one is the answer to not knowing. Anything else refuses on the terms every squash refuses
on — a pull request a human closed, a remote somebody moved off both heads the collapse accounts for, a tree that
stopped being provably clean — and the branch goes back only where nothing durable names what is on it. A record
this build cannot read **whole** refuses outright rather than being waved past, since the branch behind such a claim
is exactly the one commit that reads as nothing to squash.

A resumed publication that does not go out is rolled back like any other, with one exception: where the pull request
already carries the commit, that push sends nothing, so a request that fails is a transport failure over work the
remote has. Reset there, the checkout would come off a commit the pull request carries, the count the notice is still
owed would go with the record, and the next tick would find a remote that moved for reasons nothing on the comment
explains. Two readings say the remote is there and the **entry** is the stronger, since it is a reading of that pull
request taken this tick: a tip it froze equal to the commit about to be pushed, which it admits only where a durable
record accounts for it — so it covers the crash between a push and its receipt, where the receipt is precisely what
is missing. The receipt dated to this attempt is asked beside it for the road that read no remote at all. Neither can
fire on a fresh squash, whose entry was frozen before the commit existed; and the approval the gate writes before a
push, and the permission a transfer holds, are records a reset is *supposed* to drop, so neither is asked.

The record outlives the push, and the **handoff** is what ends it. The count on it is what the
`:package: squashed N commits to 1` notice is worded from and nothing else on the issue has one, and the notice is
owed only where history was actually replaced by less of it — a recorded count of one is the subject rewrite, which
collapsed nothing and announces nothing. A notice that was owed and did not post leaves the record standing and the
label where it is — the next tick republishes the
commit the remote already carries as the leased no-op it is and words the notice again. The write that ends it
lands **before** the relabel, because past the label the issue belongs to `documenting`, a stage that never runs
this recovery: a tick dying between the two would strand a claim nothing there could answer and lose the watermarks
the same write carries.

That write does not leave the boundary empty, though, because the relabel is a second call and can fail on its own,
and the write itself can land with its response lost. What it ends is the **claim**; what it leaves in its place is
`late_collapse_handoff_sha`, the commit the move is owed over — left by an approval that collapsed nothing too, over
the head it was given. An issue left on `validating` with nothing on the comment is one the next tick runs a second
reviewer on, over a branch already approved, squashed, and published — so the recovery route reads that record ahead
of the reviewer and moves the label instead, then drops it in a guarded commit of its own behind the label. Every
write of this tail is such a commit (`squash_writes.py`): decided on the report, `pr_number`, verdict, evidence,
review-subject, claim, report-debt, park, collapse, and handoff records as the reading behind it spells them, owning
only what it declares beside what the tick staged, and refused with nothing written, nothing relabeled, and the tick's
state withheld where any moved under it — what the tail posted then recorded, and its verdict retired where a record
the approval was proved over moved, a report owed among them — while one GitHub never confirmed moves nothing that
tick and is settled by the next from the record it may have left, with no second reviewer, squash, notice, or charge.
The readings ahead of those writes, and the one behind the verify gate, hold the tail to the same records as it last
read or wrote them, so a park or a collapse record another road puts down during any request is never cleared or
ended by the tail: nothing but what it posted is written over either, and the verdict waits. It is spent only while
the pull request is still standing on the commit it names: anything that moved the publication on — a docs pass that
pushed, a fix round, a rebase — has moved the work past the round the record was about, so it is dropped and the
tick goes to the reviewer rather than sending unread work to `documenting`. Being no claim of an outstanding
rewrite, it freezes nothing and refuses nothing — and it is held to the shape every other recorded end is, a whole
object id, because what it is spent on is a comparison against the head the pull request stands on and an issue
with no pull request to read has nothing else between such a value and a label moved past the reviewer.

A squash failure names which of **four** places it left the branch, so the park notice does not send an operator
looking at HEAD for approved commits that are only in the reflog — or to a reflog entry for commits that never left
the branch. The reading is exact rather than a default: an outstanding record read whole whose head is the head the
checkout is on is the rewrite that did not happen, and the approved commits are where a human squashing by hand
will look. A branch that moved off a recorded head this host really holds is two shapes, and the *ancestry* tells
them apart — a recorded head still reachable from HEAD is BURIED, with nothing rewritten and the approved commits
under whatever was committed on top of them, and one the branch replaced is the collapse, whose reflog entry the
notice names. Anything else — a record this build cannot read whole, a recorded head no object here answers to, a
checkout that would not report its own head, or the record-write race, which drops the record as it refuses — is
UNKNOWN, and the notice says so rather than claiming any place at all.

What the gate measures is what the pull request would **come to**: the count is
three-dot from the base the *remote* names to the candidate commit, exactly as it is before the first publication, so
it is the whole pull request rather than the diff this one push adds. Without it a branch could be grown past
`MAX_ADDED_LINES` one small fix at a time, which is the outcome the gate exists to prevent.

**The commit the caller named is the commit the gate decides about.** Every seam that reads a head for itself names
it, whether a developer ran for it or not — the docs pass, the squash, both conflict resolutions, the crash-recovered
conflict push, the auto rebase, the base-sync crash recovery behind it, the shared fix disposition, the no-feedback
bounce naming the commit its branch reading counted and froze, and the timed-out recovery naming the commit it
publishes as the killed round's — and the gate proves the checkout again, because a caller's word is not a proof.
Between those two reads the worktree is writable, so a commit landing there is a *different candidate*: measured,
pushed, and recorded by the gate while the caller goes on to stamp the id IT read as what it published — in the notice
it posts, the audit event it emits, and the round it records. So the caller names it, and a checkout standing anywhere
else parks `late_measurement_failed` — before anything is persisted and before anything is pushed, since a refusal
after the freeze leaves a record about the wrong commit and one after the push leaves the wrong commit on the pull
request.

The approval a crash left owed a push names its commit too, off the record rather than off a read: a debt is a claim
about ONE commit, and the checkout is proved to be standing on it before the gate is entered. Read once and named,
that proof and the gate's own reading are about the same approval — a commit landing between them is refused rather
than published under a decision taken about another one, with the debt dropped as paid. Empty only for the seams
that genuinely read no commit (the reconciliation answering a recorded pair, the failed-push retry whose commit that
approval already identifies), where the head this gate proves is the whole of the answer. A seam that publishes a
checkout it did not just write is not one of those: nothing in that checkout is its own output, so the commit its
reading placed is exactly the one a head moving under it would be measured and pushed in place of.

**The head a round began at is named too, and it is the PUBLICATION's rather than the checkout's.** A fix or docs
round opens with the branch in sync with its pull request — the reviewer just read that head — so the head the run
started on is the head the publication was standing on, and it is what the round hands the gate. Left for the gate to
read afterwards instead, a push somebody else landed while the agent was out becomes the lease: the candidate was
built on the head the branch used to be on, so the force-push puts it there and takes the other push with it. Named up
front, the two readings of that one fact disagree and nothing is measured or pushed at all. The timed-out recovery
and the seams publishing a commit an earlier tick stranded all
name the remote tip their own proof was taken against — the probe fetches the branch and compares HEAD to that tip, so
the tip is what their push replaces, and a head somebody landed between the probe and the push disagrees with it
rather than being adopted as the lease and force-overwritten by work proved against the head it used to be on. A tip
nothing could read is no head either, and refuses there rather than publishing against one.

**A dev fix PROVES that head rather than assuming it.** The in-sync reading holds only while nothing an earlier tick
left is still sitting on the branch. A resume that parked with a commit unpublished, and one a shutdown killed before
anything was recorded, each leave the checkout one commit above the pull request; a retry that commits again leaves it
two above, and the head that retry began at is the stranded commit, which the pull request has never carried. So the
shared fix disposition takes the stranded probe's reading for a run that COMMITTED as well as for one that did not, and
hands the gate the remote tip that reading was compared against. Read off the head the run began at instead, the entry
names a publication the pull request cannot be matched to and parks `late_measurement_failed` — and every retry behind
it parks the same way, so the accumulated code and the report describing it never leave the checkout. Where the probe
refuses about the REMOTE — a failed fetch, a divergence git would not count, a remote that moved, a checkout that
moved under the count itself — a run
that committed falls back to the head it began at, which is the in-sync reading and the one the gate then refuses on
if the pull request has moved at all: none of those is evidence against the commit in hand, and the push they produce
is leased to a head a remote that really moved rejects rather than overwrites. A tree that is not provably clean is
the refusal that is not about the remote at all, and the disposition stops the publication on it before the push
rather than pinning one — that proof is the shared dev-fix publication's own, which is why it holds whatever
`DECOMPOSE` is set to.

**What the gate hands back is spent on the push.** Not merely its permission: the commit it measured, and the head the
entry froze. The push is named against the first, so a checkout another tick, an operator, or a stray descendant moved
between the reading and the push publishes the measured commit rather than whatever it became. It is leased against
the second (`--force-with-lease=refs/heads/<branch>:<sha>`), so a pull request somebody pushed to inside that same
window rejects the push instead of being adopted as the lease and silently overwritten by work measured against the
head it used to be on.

Two of the three frozen facts are the **caller's** where it has them, and both because a fact this gate would
re-read is a fact that can have moved since the caller acted on it. The *head* is the caller's: the conflict and
base-sync publications each read the remote themselves and pin their push to what they read, so freezing anything
else would leave the immediate push refusing a head that moved while a settled adjudication — which re-pins from
the record — pinned to the head that moved and overwrote it. It is **checked** against the head this gate reads
rather than substituted for it: the two are readings of one fact, the tip of the branch the push is going onto, so a
disagreement is somebody else's push landing mid-tick and refuses. Preferring either would freeze a head that is not
what the branch would be pushed onto — and an oversized candidate would then be persisted and routed to the
adjudication on evidence already overtaken. A caller-named head that is not a whole object id refuses for the same
reason one step earlier, rather than falling back to the read: a caller that established a head made its own
decision on it, and a fallback would pin the push to a fact that decision was never taken over.

The *stage* is the caller's on the one route that relabels remotely and then publishes in the same tick (the
reviewer's `CHANGES_REQUESTED`, which flips to `fixing` before the dev spawn): read off an issue object that flip did
not go through, the label would freeze the state the issue has left and a settled verdict would continue there.
Whatever the caller names is still checked, and against the five states that publish onto a pull request the
remote already carries rather than against the transition graph. Where the switch kept the candidate out of the gate
no entry was frozen, so this owner read no pull request and has no head of its own — but the push is neither unnamed
nor unleased. The COMMIT is named off the checkout, because the switch keeps candidates out of the measurement and
not out of a push that knows what it is publishing. The LEASE is whatever the CALLER established: the conflict and
base-sync publications each read the remote for themselves, and dropping that would make `DECOMPOSE=off` the setting
that turns a force-with-lease into a blind force-push. Only a caller that established none leaves the push to lease
against git's own `ls-remote`. Both steps behind the push are claims about that one object id:
the receipt that records what reached the remote, and the proof that the checkout is still standing on it. Handed an
empty name they read a checkout that never moved as one that did, so a landed push would record an empty receipt and
then park the issue for a head sitting exactly where it was left.

**What the caller established is applied before the switch is asked, not after.** *Answering a recorded reading* is
one of the states `DECOMPOSE=off` has nothing left to say about, so such a call is entered, named, and leased
whatever the switch says. Asked over a subject the caller's terms have not been applied to, the switch would read one
as new work and hand back a push with no commit to name and no head to pin — the two races the naming and the lease
exist to close. That is the shape a retry lands in: an entry that refused persists no generation, deliberately, so a
tick taken after the switch was turned off has nothing on the pinned comment to tell it from new work and only the
caller's own terms say which it is.

That claim is carried separately from *no developer ran*, which is the wider fact beside it and decides something
else: whether a head that is not the recorded candidate is a resumed developer's fresh output or a checkout something
moved. Every seam that answers a recorded reading also has no agent behind it, and several that have no agent behind
them answer nothing — a base rebase, a conflict resolution, a divergence publish, a recovery push — so collapsing
the two makes the switch measure exactly the fresh work it exists to leave alone.

**The lease outlives the record that froze it.** The write that approves a candidate retires the generation, and the
head it froze goes with it — while the push that approval licenses has not run yet. So the head is carried on the
approval as `late_approved_lease`, and it is what every later push for that commit is pinned to: the retry after a
failed push, which skips the measurement because the commit is already approved, and the ordinary implementing
publication an authorized settlement hands the candidate back to. Without it both would read the pull request's
CURRENT head and adopt it as the lease, force-overwriting whoever pushed in between with work measured against the
head it used to be on. It is dropped by the same write that drops the approval — the push that lands, an approval
superseded, or a hold that routes the issue to adjudication instead.

**An authorized settlement publishes, then continues at the stage it came from.** The checkout is re-proved first
— provably clean, and standing on the accepted commit — because an adjudication is a human reading a diff over hours
with the worktree writable the whole time, and a verdict settled from a recorded answer has no run behind it for the
read-only proof to run against. Naming the accepted id would put the right commit on the remote either way, and that
is the danger: every stage past this one works from the checkout, so one left on an unmeasured descendant reaches
review, a squash, and a merge with nobody having read it.

It is proved **again** on the road out, and on both roads: a push is a request, and the worktree stays writable
across it, across the pull-request read behind it, and across the whole stretch a retry finishing an interrupted
settlement has left it unwatched. So the reading that decides whether the accepted commit may be handed on is taken
last, after the push — including the leased no-op a pull request already carrying the commit still makes. Failed,
the publication stands and the handoff stops: the branch has the accepted commit either way, the generation stays
live, the label stays on the adjudication (`late_pr_unreconciled`), and a tick taken once the worktree is back on
that commit finds the pull request already standing on it and finishes from there — nothing sent a second time,
no agent re-run. That retry writes the code-publication receipt its push may have died before, as the push would
have: the accepted commit, the head the verdict was measured over, and the pull request it was frozen on. The stage
it continues at reads that receipt -- a conflict round records its rewritten head's report debt off it.

The push belongs to the
settlement because the settlement is the last tick holding the evidence: the verdict was taken against one pull
request standing on one head, the reconciliation a moment earlier proved both are still what they were, and the
retirement behind it takes the record that said so away. So the branch is put where the verdict said it may go —
named against the accepted commit and leased against the frozen head — and only then is the label handed on, to
`late_source_stage` rather than to `workflow:implementing`. That stage is the only owner of the completion the
candidate still owes (the docs watermark and its `in_review` handoff, a conflict round, another reviewer look), and
two of the five have no publication seam a resumed tick would even reach. A push that does not land parks with the
label still on the adjudication: the exemption and the approval are already durable, so the retry asks for the same
commit against the same head.

The window between that push and the label is the one the record alone cannot answer, and it has its own
recognition. A tick that dies in it comes back to a live generation whose pull request is standing on the **accepted
candidate** rather than on the frozen head — which is this settlement's own push, not somebody else's movement. Read
as movement it would refuse the very publication this verdict made, forever, and park the issue
`late_pr_unreconciled`; recognized, the retry finishes the label and the retirement it never reached, records no debt
for a push that already happened, and pushes nothing a second time.

What qualifies that head is a **durable record of the push**, not the commit on its own: `late_approved_sha`, written
with the exemption in the write immediately ahead of the push, or `implementing_published_sha` read with
`implementing_published_lease` and `implementing_published_pr`, the group the push itself writes in the same write
that drops the approval. One of the two is on the comment for every crash past that write.
On a **fresh** pass neither is, and nothing of this workflow's has touched the remote yet — so a pull request that
has left the frozen head for the accepted candidate got there because something else put it there, an agent that
pushed its own commit being the plain case, and it refuses with every other moved head. Taking the commit alone as
proof would hand a stage a publication nobody proved and release a candidate the adjudication never pushed. The
receipt is read with its head for the same reason it is at the gate: it is never cleared, so an accepted candidate
published in an earlier round is one it goes on naming, and a pull request rewound onto that commit would otherwise
read as this settlement's push having landed. The head it replaced has to be the head this verdict was measured
over, and the pull request it names has to be the one the verdict was frozen on: a branch pushed from that head onto
a publication since closed and *replaced* by another on the same ref agrees with both of the others.

**An authorized settlement says what it accepted, then retires the cycle.** Past the handoff label, on either road —
a candidate nothing had published, or one measured onto a pull request the remote already carries — one comment goes
on the issue immediately before the write that drops the generation (`late_handback.py`), so a crash between them
costs at most a repeated comment. It names the accepted commit, the additions measured and the ceiling recorded on
the generation, the human operator whose `/orchestrator authorize-oversized <commit>` is the only road here, and the
exemption's scope: that commit only, with anything committed on top of it measured again. Beneath that, under
`Decomposer rationale:`, it quotes `late_result_rationale` exactly as the record kept it — never a reply, so the
authorization's own tick and a fresh process finishing the settlement after a crash quote the same text, a rationale
cut at `MAX_RATIONALE` still ending in its truncation marker, and neither spawns an agent — through the rendering a
park notice quotes an explanation with (`late_notice.py`): blocked off so a fence line or HTML-comment opener in it is
shown rather than obeyed, with the whole body inside one comment. Where the record holds no rationale a reader can use
— a result written before the key existed, or a blank, non-string, or over-bound value — the comment says
`Decomposer rationale was not recorded.` instead. That sentence is display only: nothing writes it, or anything
derived from the explanation or the verdict category, into the pinned state, and the settlement proceeds exactly as it
would with a rationale. None of this moves the contracts around it — a `single` still parks `late_single_decision`
until that authorization, the barriers and step order above stand, and the label handed on is still
`late_source_stage`, or `workflow:implementing` for a candidate nothing had published. The rationale remains issue
prose and is outside the closed late-event and analytics schemas: no late-split record on either sink carries it
([`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks)). Its storage
contract is in [`labels-and-state.md`](labels-and-state.md#the-late-run).

**An authorized settlement proves its publication before it hands the candidate back.** A pre-publication verdict
searches for the pull request its commit is on and drops a recorded pointer that turns out settled, because losing it
costs nothing: the publication opens the pull request the work needs. A post-publication verdict knows which pull
request the reading was about, so it checks rather than searches, and a check that fails **parks**
(`late_pr_unreconciled`) instead of dropping what it could not confirm. Dropping the number there would push onto a
branch whose pull request a human settled and open a second one for a change that was adjudicated against the first;
publishing over a head that moved would publish on a reading the branch has already overtaken.

Five checks, in the order their costs run. The **receipt group** comes first and asks the remote nothing: this road
reaches the transport without the size gate's own door, so the push it makes writes a fresh group over whatever the
comment carries — and a group that does not read back whole is the one record that write destroys rather than
corrects. Then the reading itself, which has to have come back and to say the pull request is still **open**. Then
the **repository** its head lives in, because a fork carries this repository's ref names over its commits and would
otherwise agree on everything below. Then the **branch**, compared against the one this settlement resolves for
itself and pushes, since the number and the branch are separate fields on one pinned comment and a pull request open
anywhere else is one the push would never touch. And last the **head**, which has to be the one the entry froze.
Every refusal leaves the verdict, the exemption, the approval and the record exactly as they stand.

**An authorized settlement of a taken-over auto-rebase replay records the report debt its push leaves.** A generation
whose `late_auto_rebase_replay_sha` names its own candidate took that candidate over from the auto rebase that made it
(`workflow/engine/rewrite_takeover.py`, see [labels-and-state.md](labels-and-state.md#late-generation-state)), and
the ownership licenses nothing on its own: the replay is published only on this road, under the operator's
authorization of that exact commit, through the same five checks and the same push leased to `late_published_sha`,
so a pull request somebody pushed to refuses it here or at the lease and records nothing. What the ownership adds is
the report the replay leaves owed, since no developer report is about a head this orchestrator rebased: once the push
lands, or a retry finds it landed, `late_replay_debt.py` records `developer_report_rewrite_debt` -- the frozen pull
request, the branch pushed, `late_published_sha` as the head replaced, and the replay -- proved by the
code-publication receipt naming exactly that push, in a write of its own before the label hands the head back to
`late_source_stage`, where the claim is held and paid as every orchestrator rewrite's is (see
[the rewritten-head report debt](#the-rewritten-head-report-debt-every-dispatch)).
The ownership stays on the generation until the retirement drops it, so a retry after a landed push records the same
claim without pushing again; a proved claim with no room on the pinned comment parks `late_pr_unreconciled` with the
push kept and the generation live, and the next tick records it once room is made. That park is measured first -- its
flags, and the ledger entry and watermark its notice adds, at the widest id -- since it grows the same full comment;
where it does not fit either, nothing is posted or written, and the comment as it stands, the receipt and the
generation's ownership on it, is what the next tick asks again from.

The entry is what a call taken past publication has and one taken before it does not, and all three of its facts are
frozen before any effect because a later tick could re-derive none of them: the **stage** the gate is taking the issue
out of (gone the moment `workflow:decomposing` replaces it), the **pull request** the work already has (which is what
the cycle-marked hold then goes on, recorded under `late_plan_pr_number` beside its own head and the description it
displaced), and the **head** that pull request is standing on (which the next push to the branch moves). They are
written as `late_post_publication`, `late_source_stage`, `late_published_pr_number`, and `late_published_sha` beside
the frozen pair, so a record on the pinned comment says which side of publication it
was entered on and an analysis groups on the field rather than on its absence
([`labels-and-state.md`](labels-and-state.md#late-generation-state)). The stage is checked against the five that
publish onto a pull request the remote already carries rather than against "has an edge to `workflow:decomposing`":
`workflow:ready`, `workflow:blocked`, and `workflow:umbrella` each own that edge for reasons of their own and have no
pull request behind them, and `workflow:implementing`'s own push is what *opens* the pull request — so a group frozen
from one of them would send a later reconciliation to measure and push a candidate no post-publication stage ever
committed. The record refuses to be entered on such a stage, and one hand-edited onto the comment reads back as no
publication context at all.

- **At or below the ceiling** → the ordinary push onto the branch, unchanged. The generation is dropped ahead of it,
  and the `late_approved_sha` the retirement recorded is spent by the push that pays it — a debt left standing would
  freeze this branch out of the pre-tick base refresh with nothing coming back to drop it.
- **Unmeasured but published** → the same debt, for the same window. A candidate an adjudication exempted, or one a
  fresh commit superseded with the switch off, froze no generation of its own, so between the gate letting it through
  and the push that carries it there is committed work on the branch and nothing on the issue naming it. So
  `late_approved_sha`, its lease, its `unmeasured` basis, and `late_spends` go down before the push, and the
  reconciliation ahead of every handler pays them: without that a tick dying in the window comes back to an issue that
  has published nothing, resumes a developer over the head the pull request already carries, and hands the gate a
  candidate whose two readings of that publication no longer agree. Recorded only where the push will MOVE the
  publication — one that finds the pull request already standing on the commit has nothing to receive, and a debt
  written there would be paid by a republication closing a round the tick that really published it already closed —
  and never over a debt the issue already carries for that commit, whose lease was frozen by the tick that granted it.
  The head it is recorded against is the one the push is pinned to, which is the entry's where there is one and the
  CALLER's where the switch kept the candidate out of the gate: nothing froze a publication there, but the push still
  moves one, so the window is the same and `DECOMPOSE=off` decides the measurement rather than the account of what a
  push put where.
- **Strictly past it** → nothing is pushed. The pull request stays on the head it was standing on, the measurement and
  the entry are made durable, a notice naming the pull request and that head goes on the issue, and the label moves to
  `workflow:decomposing` — from whichever of `workflow:validating` / `in_review` / `workflow:fixing` /
  `workflow:resolving_conflict` the fix loop was reached under, which is why each owns that edge.
- **Seven refusals**, each a push the gate would otherwise wave through on evidence nobody took, or a stage run over
  a candidate nobody read. A frozen pair whose **checkout is not on this host** stops the tick outright rather than
  letting the stage carry on: the commit is on a host this one is not, so the refusal owes a human — announced once,
  since a checkout that stays gone must not put a fresh notice on the thread every poll. The next five are a tree
  that is not
  *provably* clean (a `git status` that established nothing names no paths, which is what a clean tree names too — a
  dirty one still parks naming its paths one step earlier), a pull request nothing could read, one that is closed or
  merged (nowhere for the push to land), a head the caller named that is not a whole object id or that disagrees with
  the head this gate reads (the two are readings of one fact, so a disagreement is somebody else's push landing
  mid-tick), and a head that has moved off what a live record froze (the frozen pair no longer says what the pull
  request would come to; the record is left naming the head it froze rather than re-entered over the one that
  landed). The disagreement has one carve-out and it takes a **durable record of a push**, never a matching commit: a
  tip named by `late_approved_sha`, by a live generation's candidate, or by `implementing_published_sha` read
  *together with* `implementing_published_lease` — the head that receipt replaced — and `implementing_published_pr`,
  the publication it went onto, is this issue's own push having landed and is finished rather than refused. The
  caller's candidate on its own is not evidence: on a fresh attempt
  no push of this workflow's has run, so a tip that merely happens to BE that commit says an agent pushed it, and
  forgiven there the gate would measure and route the very candidate it is holding back. Nor is the receipt on its
  own, which is never cleared and would read a pull request rewound onto a commit published rounds ago as this tick's
  push arriving — and where the checkout is standing on that same commit, every local fact agrees and none of them is
  about this round. The head the push was PINNED to is what dates the receipt, and a rewind cannot supply the one a
  caller froze; the number it names is what says which publication received it, and a branch pushed from that head
  onto a pull request since closed and replaced satisfies the other two without it. Each parks
  `late_measurement_failed` with nothing
  pushed and no label moved, and the typed failure reaches both sinks under the stage the reading was taken in. The
  seventh is an approval whose **lease cannot be read** — absent, or not a whole object id. The lease is the whole of
  what keeps the push it licenses off a pull request somebody moved, and the one fallback available here is the head
  read NOW, which is exactly the move it exists to catch. So it parks with the rest rather than pinning to the
  present.
- **A reading the gate did take and could not finish is answered one step earlier, and on two of its steps a human is
  not asked at all.** Those seven refuse a record or an entry; this is the diff itself failing, and it goes through
  the same `late_parks` owner the implementing seam's readings do, so what a thread, a stream, and a base refresh see
  here is what they see there: the reason is `late_measurement_failed`, the record is one `late_failure` carrying
  `measurement_failed` with the `MeasurementFailure` step and the line that step wrote beside it, and a notice is an
  ordinary comment carrying the same hidden `<!--orchestrator-comment-->` marker every park's does — so a tick held
  silently posts nothing, leaves no marker, and moves no comment watermark, while an announced one is read back as
  this orchestrator's own exactly as every other notice is. `base_unreadable` and `base_absent` name the TRANSPORT
  between this host and the base rather than the work, and clear themselves, so the first three consecutive misses on
  one pair write the pair and the incremented `late_measurement_miss_count`, emit that record, log at WARNING and
  stop — leaving no
  `awaiting_human`, no `park_reason`, no comment and no step on the pinned record — and only the fourth parks and
  mentions a human, recording the step that mention names in the same write as the count. Every other member parks on
  its first miss, because a candidate this host does not hold or a diff nothing here can pin answers a second reading
  as it answered the first.
- **A park here bounds the mentions rather than the readings.** The frozen-pair reading below runs ahead of every
  handler on all five of these stages and is not gated on the park, so a parked pair is re-measured once a poll — the
  recorded base asked for as that exact object where one was named, and the remote asked again only where the failure
  left none — and a transport that comes back settles the park with nothing said on the thread. What that costs the
  issue is bounded to one sentence per thing there is to say: a reading stopping at the step `late_measurement_failure`
  already names repeats a sentence the human cannot answer any faster, so the tick is held silently — the typed
  `late_failure` still reaching both sinks, since those polls exist nowhere else, and a base id the remote finally
  names still recorded, since it is what the next retry asks for — while one stopping at a *different* member is a
  different next move nothing else would report, so it is announced once and takes that field's place. No miss is
  counted for either: the bound is spent. The refusals on this page that announce once are keyed on the standing park
  and nothing else — a missing checkout, a reading stranded on another stage, and a record nothing can parse are each
  a wall this process cannot walk back from, so any tick finding the reason already there is held. Only the reading's
  own guard asks more, because a reading is the one of them that can come back: the latch as well as the reason, the
  pair the park was taken over, and the step its notice named. A base that IS reached puts the count back to zero and
  leaves the member alone, since reaching the base is not the last step a reading can stop at; the verdict a reading
  that HAPPENED settles clears both, and retires the park with them.
- **A hold closes the caller's own bookkeeping.** The gate holding a candidate is not a park — the commit is on the
  branch and an authorized settlement publishes it from there — so what the caller's tick was in the middle of is
  finished even though its tail never ran, and no later tick of that stage can do it: a settled adjudication
  publishes before handing the issue back, so the resumed stage finds nothing left to push. Each caller therefore
  says up front what its hold owes, as pinned fields written inside the routed hold's own durable write, *ahead* of
  the relabel; applied afterwards they would be lost to any crash in exactly the window the relabel opens. The fix
  loop spends the reviewer round the rejected head superseded. The docs pass leaves `docs_settled_sha`, the head it
  produced, because the pass itself is over and only the `in_review` handoff is still owed. A conflict resolution
  leaves `conflict_settled_outcome` / `conflict_settled_sha`, because the resumed tick reads a published resolution as a
  branch already standing on its base — the no-op flip, which emits `base_up_to_date`, resolves nothing, and stamps no
  `last_conflict_resolved_at`. Each receipt is read back only when the branch is in sync with its remote AND standing
  on the commit the receipt names, since a verdict that parked or a label a human moved leaves the same receipt over
  a commit still on disk; ahead of the remote it stands and the ordinary recovered-commit road carries the commit
  back through the gate. In sync is not the same claim as CARRYING it — a replacement host rebuilds the checkout from
  a pull request that has moved on and gets a branch level with its remote and standing on somebody else's head — so
  the head is proved against the checkout rather than inferred from the counters, and that proof carries the remote
  with it: the caller fetched the branch before counting and refuses a checkout behind it. A receipt that is not a
  whole object id, or a head this host cannot peel, leaves the receipt exactly where it is for a tick that can prove
  it. Spending is asked
  of the measurement rather than of the label, because a reading nobody could take also stops the tick with a
  generation on the pinned comment — and that one IS a park, with the developer's work still pending and nothing of
  its caller's spent.
- **What a hold owes is durable, because the tick that owes it may not be.** The freeze is durable and the count that
  follows it is not, so the same crash the reconciliation exists for lands between them — and that tick has no run
  behind it to re-derive a reviewer round, a cleared fix batch, or a stage tail from. So `late_spends` goes down in
  the same write as the pair, as `[[field, value], ...]`, and the reading ahead of the next handler restores it
  before it re-enters the gate. Written only while the pair still awaits its count, which is exactly the window it
  pays for: a record carrying a number was answered by a routed hold that spent this on the way past, and rewriting
  it there would leave a spent claim for a later reader to apply twice. It sits inside the generation's own key
  group, with the one exception the approval makes: the write that approves a small candidate retires the pair
  before the push it licenses runs, and puts these back inside it, so a push that misses leaves the next tick both
  the commit to publish and what publishing it closes. Restored, an oversized retry routes having closed exactly
  what its caller would have; a landed push closes them in the write that carries its **receipt**.
- **Every landed push closes what its route owed, in the receipt's own write.** Not only the reconciliation's. Past
  that write the approval is gone and so is the generation it was granted under, while the caller still has a relabel
  and a write of its own to make — so a process dying in that window would come back to a published commit, a label
  already moved on, and a round frozen at what the tick before the push had, with nothing left on the comment saying
  one was owed. The routes hand in the value they computed BEFORE the push and re-apply that same frozen pair once
  the call returns, which is a no-op where the gate already wrote it and the count where a push nothing could NAME
  never reached that write. Re-reading a counter there instead would count one round twice, which is why the value is
  read once per route and carried. And the write is skipped where the pinned comment already says all of it — a
  retry over a publication the remote is already standing on, whose round the tick that landed it closed in this
  very write. A push that MOVED the publication is not that retry, and there the receipt alone proves nothing: it is
  never cleared, so a pull request somebody rewound and this tick pushes BACK to a commit published rounds ago
  arrives with the receipt naming it and no debt beside it while the round behind this push is still uncounted and
  its fix batch still pending — and the only write carrying any of that would be the caller's own a tick's work
  later. So a moved publication settles whenever a pair the route owes is not already the value on the comment, and
  a push that had nothing to send does not: the routes that read their owed value off the counter would compute a
  higher one here and count the same round twice.
- **`DECOMPOSE=off`** is asked ahead of all of it, so an install running that way neither reads the pull request for
  the *measurement* nor parks over one. The terminal-safety barrier immediately before the push reads it regardless,
  on every install: what the switch decides is what enters the reading, not whether a pull request somebody merged may
  be force-moved. As at the implementing seam the switch decides only what ENTERS the gate: a record naming the commit
  in hand, or a commit an approval owes a push for, is measured either way — while a record naming some other
  candidate is one this commit supersedes, so it is retired and the fresh commit publishes unmeasured. The squash asks
  it for itself, because `reconciling` cannot answer it there — that seam sets the flag to say no developer ran, and
  the gate reads it as *answering a reading the gate recorded*, which a squash never is: the commit it publishes is
  one it makes itself. Nor does the switch reach the naming. A caller that named its candidate is still proved against
  the checkout, because the proof is local and what it buys is the one comparison the naming exists for — the switch
  keeps candidates out of the measurement, not out of a push that knows which commit it is sending.

**The freeze is a resumable step, not a window.** The pair goes down with `late_phase=measuring` before the diff is
counted, so a tick that dies in between leaves a record naming both commits with no number on it — and nothing on the
stage it was entered on would go back for that by itself. So the dispatcher asks for it, in `_pinned_state_refuses`
beside its other late-domain guards and ahead of every handler: a generation carrying a whole publication group, no
count, and a `late_source_stage` equal to the label the issue is wearing — and one of the five that publish onto an
existing pull request, since a group naming any other state is no context to measure from — is measured *first*. Small
retires the record PUBLISHES it -- named against the commit that was measured and pinned to the head the pair froze --
and the handler runs behind that push; past the ceiling routes the issue to the adjudication and the handler does not
run; a refusal parks, durably, since nothing runs behind it to write the flags, and so does a push that was allowed
and did not land. The publication is the reconciliation's own because nothing goes back for it: the reading is settled
and the record is gone, so a handler run behind an unpublished candidate spawns a reviewer over a pull request that
never received it — and an approval past that finds one commit on the branch, squashes nothing, and hands an unpushed
head to the docs pass, which reads it as recovered work and skips the pass it was relabelled for.

**An approval with no generation behind it is the same window one step on.** The write that approves a candidate
retires its generation in the same breath, deliberately and before the push, so a tick that dies past that write
leaves nothing for the frozen-pair reading to answer — only `late_approved_sha` naming a commit the pull request
never received. So the dispatcher pays it too, ahead of every handler, under the id the gate decided about and the
`late_approved_lease` it decided against: both live only on the approval by then. The **lease** is what says the
approval was taken on the published side at all, so an implementing-seam one — whose push opens the pull request and
reads the remote for itself — is left to the publication that owns it, and an issue under `workflow:decomposing` is
left to the settlement that is still reconciling it. It is paid only from a checkout still standing on that commit,
because an approval is a claim about ONE commit — and a checkout that is absent, unreadable, or standing elsewhere
**parks** rather than standing down. The debt says a commit the pull request does not carry was measured and allowed
to join it, so a handler run behind any of those works from a publication the approved work is not on: the reviewer
votes on a head nobody adjudicated, the merge gate offers a human that head, and the docs pass commits on top of it.
Announced once, since an operator has to put the checkout back before anything changes.

A branch some owner deliberately moved OFF the approved commit never reaches that refusal, because an approval whose
commit was abandoned is superseded and the owner doing the abandoning drops it: the auto rebase's reset — which puts
the branch back on the pre-rebase SHA when its own push is refused, leaving the approved commit only in the reflog —
clears the approval with the whole record of the attempt. Both drops are held to that reset LANDING. A reset git
refused abandoned nothing, so the approval still names a commit the checkout may be standing on and the record beside
it is the only account of which attempt put it there; dropped there, the next tick would have no anchor to bring the
recovery back with and no id to ask for the candidate by (see
[`labels-and-state.md`](labels-and-state.md#pinned-state)).

The same answer is asked at the no-feedback bounce, which reaches a missing checkout on its own: a publication that
finds no worktree has always simply not published, and with a pair frozen and never counted that is not enough. No
developer ran on that tick, so it is taken as a **reconciliation** — a head that is not the recorded candidate is a
checkout something moved rather than a run's output, and it is refused rather than measured.

**A record that CLAIMS a reading it cannot produce stops the tick too, ahead of both.** Every field in this domain
is read fail-closed, and for the readings the gate itself takes that is the whole answer: a value it cannot use is a
value it does not have. Ahead of the HANDLER it is only half of one — a publication group missing its stage, its
pull request, or its head parses as no group, and an approval missing the lease it is spent with parses as no
approval, so both of the questions above answer "nothing owed" and the stage runs. So the raw fields are read first,
on the five stages that publish onto a pull request the remote already carries: a marked group that cannot name all
three, an approval that cannot produce its pair, or a settled transfer's `late_rewrite_proof` standing over a
permission, a phase, or a reading nothing can report from, parks `late_measurement_failed` with nothing pushed and
nothing discarded. None of the pieces is recoverable from anywhere else, so the refusal owes a human — announced
once, since a fresh notice every poll is a mention nobody can answer any faster. Those five are named off the
transition graph's
own set rather than derived from it: `workflow:implementing` has an edge to the adjudication too and is **not** one
of them, because its approval carries no pull-request head by design — its push is the one that opens the pull
request — so a crash between the two leaves exactly the shape this would otherwise call damaged and park instead of
finishing. `workflow:decomposing` is asked only the publication group and the transfer proof, because the settlement
there holds the reading and the approval half-decided, while a group or a proof it did not write is one it cannot
repair.

**Both of those roads end in a push, so what is over is asked ahead of either.** The terminal that drains finished
work runs inside the stage handler, which is *behind* this owner — so without a barrier the crash window the whole
reconciliation exists for becomes the way work reaches a pull request nobody can merge. Two facts are read and both
hand the tick straight back: the issue OBJECT, and the PULL REQUEST the record names, which the issue's own flag
cannot show — a merge leaves the issue open until a terminal reads it, and a merged or closed pull request is nowhere
for this push to land, so without this the road ends in `late_measurement_failed` and parks a human over a
publication that is finished. The pull request is read fail-*open*, so a remote that would not answer falls through
to the road that takes its own reading and parks with the reason it fails for — and it is read *behind* the three
record questions rather than at the owner's door, since it is a request and the only ticks its answer can change are
the ones with something left to reconcile. Behind either, the handler's own terminal marks the issue `done` or
`rejected` with the generation, the receipt, the branch and the debt left exactly as they are.

Everything spent past that point — the stage check, the checkout probe, the remote read, the diff — is time a poll on
another worker can find the world changing in, so the gated publication carries a barrier of its own immediately
before the push and nowhere else in it. Two things can have ended there. The *pull request* is asked first and is the
one nothing above catches: the gate refuses to **enter** a call on one that is already over, so the only way one
reaches the push is by merging or closing in the window behind that reading — and its branch is still at the head
this tick froze, so the lease succeeds and the force-push moves a merged pull request's branch back onto the commits
it merged. That reading is fail-*closed*, the opposite of the same one at the door, since there falling through costs
a poll and here a branch nothing can put back; and it is taken for every push onto a pull request the record names,
`DECOMPOSE=off` included — that switch decides what enters the *measurement*, not whether a merged pull request may
be force-moved. A record that cannot **name** one refuses ahead of that reading, with no absence carved out: every
road reaching this barrier publishes onto a pull request the remote already carries, so a field that is gone and one
the comment carries and no reader will type are the same refusal. Reading the second as "nothing to check" is how the
barrier fails open — every identity here is read fail-closed, so an unusable one comes back as no identity, no
request is spent, and the force-push lands on whatever the branch's pull request has become. The process-wide close
latch is asked **last**, because the reading above it is a request and a close
landing while that request is in flight is one only an answer taken after it can still give. Refused, nothing is
pushed, relabelled or announced, and the record is left for the cleanup it is owed.

The *initial* publication on `workflow:implementing` carries a barrier of its own, which
`implementing/push_barrier.py` owns. Its two endings are the latch and the pull request its push would **join** — the
one the gate proved, or else the one the record names — since the reuse behind that push is a lookup by branch, so one
that ended in the window answers nothing to it and a second pull request is opened with `pr_number` overwritten. There
the two are told apart rather than refused together: an **absent** `pr_number` is an issue that has published nothing
— the first push of all is what opens a pull request, and the window before the relabel leaves the same shape — while
a field that is there and will not type is the record disagreeing with itself and refuses. A `discussion` plan the
humans have **settled** is exempt, on the same grounds the stage's own terminals exempt one: a merged plan is an
agreement rather than a delivery, so the implementation it licenses gets a pull request of its own rather than being
held back for it. *Settled* is the load-bearing word: it is a thing only a reading establishes, so a request that
failed is refused ahead of the exemption and the record does not save it — what the comment says is which pull request
is the design, never what anybody has done with it. Refusing costs the poll that asks again, where a readable plan
gets the exemption it is owed. The latch half covers the window the gate's own cancellation cannot — that one ends a
cycle, and the write that approves a candidate retires the cycle before the push, so an approval whose push failed
comes back with nothing left to cancel. And so does the push a settled adjudication makes from `workflow:decomposing`,
which reaches the transport directly rather than through the gated call: its window is the widest of any, since the
pull request was last read by the settlement's own reconciliation and the exemption, the identity, the debt, the park
persist and both checkout proofs all run between that reading and the push. A refusal there leaves the verdict and its
approval durable for the retry.

**A record read off its own stage stops the tick.** The reading was taken under one publication and one stage, and
both are terms of it, so a pair frozen on `fixing` and read while the issue wears `workflow:validating` may not
simply be re-entered here — it would be measured against a publication it was never taken on. Waving the handler
through instead is worse: the reading is unresolved and the commit it named is unpushed, so `validating` would hand a
reviewer a head the pull request never received, and the roads that publish would push a candidate nobody read. The
label was moved by something outside the gate and only a human can say whether it goes back or the record is dropped,
so the tick stops with nothing pushed, nothing discarded, and one notice on the thread rather than one per poll.

**A settled split's retained publication group is not an outstanding reading.** A candidate the adjudication turned
into children owes no count, and the record says so by carrying none: the split's retirement drops the measurement
on purpose — one still answering "oversized" pins `workflow:decomposing` and would put the umbrella label back on
every dispatch — and keeps the publication group, because the umbrella re-asks it in front of every child it releases
and every branch it deletes. Read as a pair somebody froze, that record is the shape above with the label already
moved: the group names the stage the gate was entered from and the issue is on `workflow:umbrella` by design, so the
stranded-reading refusal would hold every dispatch in front of the walk that releases the children — the one way a
split can leave its own children permanently unreleased. So the reading is asked of the record's own settlement first
(`LateGeneration.split_has_settled`): a `late_phase` of `splitting`, `superseding`, or `cleaning_up`, or a non-empty
`late_split_children` register, and the tick goes to the label's own handler. `snapshotting` is not one of them —
that boundary cuts the ref and creates no child, and a record standing there still carries the reading that sent it
to the adjudication. Neither is the measurement re-added to the settled record: `_adjudication_is_live` and the
`workflow:decomposing` relabel guard are keyed on it. A `late_measurement_failed` park an earlier tick left on such a
record is retired in the same pass, since nothing about it is a human's to answer and the reason is what holds the
branch out of the pre-tick base refresh.

**A push that landed leaves a receipt where it landed.** `implementing_published_sha` is written in the same durable
write that drops the approval, at the moment the push returns, on every seam this gate stands in front of. The window
after it is a whole tick's worth of relabels and comments, any of which can fail — and a tick coming back into it
finds a live branch, a pull request already carrying the work, and a label that still says the stage never finished.
Without the receipt the candidate is measured again against a base that has moved, and an answer past the ceiling
would route a pull request that ALREADY has the work to the adjudication, which is the one outcome this gate exists
to prevent. Recognized, the commit is not re-*measured* and the tick finishes what it was in the middle of. It is
still pushed, and deliberately: the push is a leased **no-op** — named against that commit and pinned to it — so git
has nothing to send and rejects outright if somebody moved the branch between the proof and here. That request is the
only atomic evidence there is that the publication the tick proved is still the one the pull request has; skipping it
would settle the receipt against a remote nothing re-read.

**But the receipt is a local note, and the REMOTE is what it is evidence about.** It records what this stage last
pushed and nothing about where it went or whether it is still there, and it is never cleared — so a branch published
rounds ago carries one for the rest of the issue's life. It is therefore only honoured while the publication it names
is still standing, and what that proof costs differs by seam. A call taken PAST a publication froze the head the pull
request is on, and the two are compared: a receipt naming `C` beside a pull request somebody has since moved to `F`
records a publication that is over, so `C` goes back through the ordinary road, measured against the base as it is now
and pushed leased against what was frozen. The pull request it froze is compared with that head and on the same terms:
a head says the work is *there* and nothing about how it got there, so a receipt naming some other publication vouches
for nothing and the candidate goes back through the reading too. The implementing seam froze neither — its push is
what *opens* a pull request — so there the same question goes to the **remote**, and anything short of an open pull
request of this repository's, on the branch that seam would push, standing on this exact commit, over a receipt
recording no LEASE, **parks** rather than
falling back to the reading: measured and found small the commit would simply be published, which force-pushes a
branch nothing could confirm and opens a second pull request over work the first may already carry.

**The lease scopes the receipt to the call that wrote it.** A lease names the head a push REPLACED, and it is written
only where the call that made that push froze one. The implementing seam froze none, so the only receipt its window
is about is the one an initial publication left — which records no lease at all. A receipt carrying one was written
by some other call entirely, and its commit happening to match the candidate is a coincidence the proof may not
spend: waved through, the candidate skips the reading and the fresh receipt behind the push *clears* the lease, which
is the one field saying which attempt the record was really about.

**Which pull request the receipt is about is the receipt's OWN, written with it.** `implementing_published_pr` goes
down in the same write as the commit and the head it replaced, because `pr_number` is the relabel's write and the
relabel is exactly what this window is missing. It is never searched for: a lookup by branch answers with whatever is
open on that ref, so a REPLACEMENT somebody opened after closing the original would be taken for the publication this
stage made, and the relabel, the debt and the receipt would all be spent against it. So a group that cannot produce a
readable one is *damage* rather than a question the proof can answer, and it is refused one step earlier, at the size
gate's own DOOR — of the record and of no candidate, since every road out of a gate call ends in the write that puts
a fresh group down and the road an install with `DECOMPOSE=off` takes never reaches the candidate question at all.
Told apart from a group that claims nothing at all, since every late field reads fail-closed and published over, the
push would write a fresh group across the damage. The accepted settlement has no gate door of its own,
reaching the transport directly, so its reconciliation refuses the same record on the same terms. Three shapes are
damage: a member whose KEY is gone while its siblings are there — the write puts all three down, `null` included, so a
missing one is a hand edit rather than the empty lease an initial publication records — a member carrying a value
nothing can read, named so the park says which field to repair, and a group that names no PUBLICATION, which is a
commit with no readable number beside it or a lease or number with no readable commit. That last pair is what a
commit-only check walks straight past: where the receipt names some other object id, the road that compares it against
the candidate is never taken and the next push completes the partial group instead of leaving it. Nothing is outside
that hold: an exemption or an approval naming the same commit says the candidate needs no fresh *reading* and nothing
about where the work went. The park writes nothing else — the receipt, the recorded number, the approval and any debt
beside them stand exactly as they are, for the terminal that drains finished work or for the retry once a human has
reconciled the record with the remote.

**Proved, the number is carried rather than looked up again.** The push behind it is leased against the very commit
the proof was about, so a branch somebody moved in the window rejects it instead of being force-overwritten; the
terminal barrier immediately before that push is handed the same number; and the bookkeeping behind it resolves that
number a second time rather than searching the branch — one somebody closed between the proof and here holds the
tick instead of earning a second pull request over work the first already carries. That last reading re-takes the
WHOLE identity rather than the open state, off one fetch and against the object it hands on: what it is about to
write is a receipt naming this commit and a relabel handing a reviewer this pull request, so open, in this
repository, on the branch the push named, and standing on the commit it sent all have to hold together still. A pull
request somebody merely MOVED in that window is open and is not the publication the proof was about.

**The head the pull request is standing on settles a debt no write got to.** The receipt and the approval it replaces
are one write, and a process can die on it: the branch is on the remote and the pinned comment still says the commit
is owed, leased to a head the remote has moved off. Nothing measures that commit again — the approval is exactly what
keeps it out of the gate — so nothing else would ever drop it, and `late_approved_sha` would freeze this branch out
of the pre-tick base refresh for the rest of the issue's life. What answers it is the entry this call already froze:
a pull request standing ON the candidate says the push it licenses was made, whatever any record says. So there is
nothing to push, the debt is settled, the receipt is written, and the tick carries on. Asked ahead of the lease
requirement, because a push nobody is making needs no head to pin — a lease that died with the write that should
have spent it must not park an issue for a publication that already happened.

**The checkout is proved again on the far side of the push.** The pre-push proof is a fact about a moment that has
passed by the time git returns: the push is a request, the worktree is writable while it runs, and a descendant an
agent or a cleanup left — or an unstaged edit beside it — is enough. What went out is the commit that was named, so
the branch and its pull request are right; what is wrong is the CHECKOUT, and the checkout is what every stage behind
this gate reads. A reviewer treats a head ahead of the pushed branch as unpushed work, the squash rewrites what is on
it, the docs pass commits on top. So the publication stands and the HANDOFF stops: the caller is told the tick is
finished and relabels nothing, announces nothing, and spends no round, while the issue parks `late_candidate_moved`.
It is the same pair of questions the initial publication asks past its own push, and both go through
`implementing/checkout_guards` rather than being worded twice.

**And it is asked AHEAD of the settlement, so its answer rides the receipt's own write.** What a failed proof records
is a whole approval, both halves the commit that just landed — that being the head the pull request stands on now —
and it goes down with the receipt rather than one write behind it. Settled the other way round, a process dying
between the two comes back to a published branch, a paid debt, and nothing on the record owing the checkout a proof:
the stage below reads a dirty worktree as no stranded work and relabels to `workflow:validating`, handing a reviewer
a checkout nobody read. The window that remains is the one BEFORE that write, and it is recoverable rather than
silent — every push that moves its publication records the debt for it beforehand, so a crash there leaves an
approval the reconciliation ahead of the next handler pays as a leased no-op and then re-proves.

## `_handle_validating` (label `workflow:validating`)
- **Trigger**: each tick while label is `workflow:validating`. Set by `_handle_implementing` after `_on_commits` opens
  the PR, by `_handle_documenting`'s drift unwind, and by `_handle_fixing` / `_handle_in_review` /
  `_handle_resolving_conflict` on their pushed exits.
- **Input**: PR #, branch, `dev_agent` / `dev_session_id`, `review_round`.
- **Internal flow**:
  0. **External-merge / closed-issue short-circuit** (same chain as implementing / documenting). The reviewer is not
     spawned on either short-circuit. Ahead of even these, a `conflict_handed_sha` that `_handle_resolving_conflict`'s
     lost write behind its relabel left standing is dropped in a write of its own (`conflicts/handoff.py`): the move
     it claims is owed has been made by the time this handler runs, and left standing it would read to the next
     conflict episode over the same head as that move still owed (see
     [_handle_resolving_conflict](#_handle_resolving_conflict-label-workflowresolving_conflict)).
  1. A squash this issue began and did not finish (`late_collapse_*` on the pinned comment) is answered here,
     ahead of every route that could point an agent at the branch — the drift resume, the awaiting-human path, and
     the reviewer spawn (`_recovers_a_recorded_collapse`) — over the same tail the approval road runs. Asked only
     from that road it would be asked on no tick whose reviewer times out, crashes, or votes `CHANGES_REQUESTED`:
     an already-landed collapse would never get its notice, its watermarks, or its relabel, a record nothing can
     read would reach `workflow:fixing` without the park it owes, and a body edit would resume the dev on a branch
     standing on a commit nobody accounted for. It owns the park it takes, too. Its own refusals park under a
     durable `park_reason="squash_failed"`, and it retries them on every tick without saying anything again: what
     the notice asks for — the branch reconciled, or the pinned comment repaired — is proved by the recovery
     getting further, and the park's own writer stays quiet while that reason stands. A park the **size gate**
     worded behind it is held rather than re-entered, since the gate posts a fresh notice for every reading it
     cannot take; the human's reply then clears that park and is spent on the recovery rather than on a dev resumed
     over a branch mid-rewrite. A recovery that finishes clears the park it found, so nothing carries an
     `awaiting_human` into `documenting` — and it moves the label there only while the approval it finishes under
     still covers the evidence it was proved over (`review_approved_evidence` still naming the current, passing
     evidence, where it names any, with no revision past it recorded and the verification context unchanged), the
     report the pull request carries, the requirements the issue carries, and the
     commit the rewrite published, each read afresh (`review_coverage._approval_holds`): the rewrite is finished
     either way, since no
     branch may be left standing mid-rewrite, but the move is held and the handoff it leaves is dropped on the next
     tick — for a fresh reviewer, or for the drift check to answer the edit. An issue with nothing recorded costs one
     lookup on the pinned comment and a reading of `verification_evidence_current`: evidence an approval's squash
     carried onto a head it did not run on, whose review subject no longer stands
     (`verification_current.carry_answers`) or that `review_approved_evidence` no longer names, is invalidated there
     (`squash_evidence.carry_unanswered`), and the approval it was carried for with it (`review_approved_subject`
     written `null`; one another road recorded in its place, of another subject, stands), in a
     guarded commit of its own staged on the comment read afresh and held to the bound evidence records, to
     `review_approved_evidence`, and to the report debt the carry's review subject stands only without
     (`developer_report_owed`, an undeliverable `park_reason`, and the report records) -- a claim, an approval, a review
     subject, or a debt another road moved meanwhile, before that reading or under the commit, holds the tick with
     nothing written, and every field the invalidation does not own is kept -- the tick spent on it, ahead of
     any round it could be handed to —
     the issue the documenting stage or `in_review` hands back over such a carry arrives here; one carrying only
     the `late_collapse_handoff_sha` a finished handoff left moves the label that handoff
     never got to move (and drops the record behind it), or drops it unspent where the pull request has since moved off
     the commit it names — or where the developer report recorded as current is not the one the approval covered
     (`review_approved_subject`), or where the evidence the approval was proved over is outranked by a later
     revision -- settled or still owed -- retired, no longer passing, or minted under a verification context no longer
     configured (`review_approved_evidence`), or where that report no longer reads at its location as it settled,
     since a report settled on that same
     commit since, or edited or removed in place, is work no reviewer has read and the round below reviews it, or
     where the issue read afresh no longer carries both the `requirements` the approval was given and the
     `user_content_hash` baseline — a baseline that moved on to an edit since the approval says nothing about what
     the reviewer read — which the drift check or the reviewer round below then answers; a location, an issue, or a
     pull request nobody could read holds the tick. Both roads hold the move to the evidence the approval rests on
     answering for the commit it is owed over, under the carry-forward rule step 6's approval arc takes behind its
     squash (`squash_evidence`): a carry the recovery records is published by the next tick's reconciliation, which
     runs ahead of this handler, so the handoff finds that evidence current -- and proves it whole again before the
     label moves over it (`current_evidence_verdict`: the tested commit and the head still reading as the tested
     tree, the applicable review subject still recorded and approved, the context, the publication, the report, and
     the requirements) -- and moves the label with no reviewer, or, refused, invalidates it and drops the record in
     a write of its own, for the round below on the next tick. A carry that reconciliation refused is abandoned with
     the approval it was recorded for (`review_approved_subject` written `null`), which leaves
     `review_approved_evidence` naming a transaction that never settled, so the handoff is dropped and a fresh
     reviewer validates the head, as for any evidence that no longer stands. A carry it only stood down on for want of
     room on the pinned comment -- ahead of the post or behind it -- is not refused: it stays owed for an approval
     that still stands, and the handoff HOLDS over it with the record kept (`squash_evidence.carried_onto`), so the
     next tick with room settles it and moves the label with no second report or reviewer. A handoff
     whose carry was never decided -- the pull request or the artifact unread when the squash tail asked -- decides
     it here, over the same proofs, in a guarded commit of its own owning only what that decision writes (recorded,
     or refused with the evidence invalidated and the record dropped), and leaves the move to the next tick; an
     unread reading again, or a commit that does not land, holds the tick. On the recovery
     that evidence is asked FIRST, ahead of the coverage above, since its proof is requests long enough for a push:
     every refusal of it invalidates it whatever else moved beside it -- a context changed before the retry included,
     and a carry onto the handoff's commit that `review_approved_evidence` no longer names (removed, `null`, or
     pointed elsewhere), which is never taken for an approval older than evidence claims -- and the coverage's read of
     the pull request is the last request ahead of the move; where that coverage drops
     the handoff, a settled carry onto its commit goes into history with it, since that evidence answers for the
     commit only on the approval's word. Either road reads the pinned comment once more
     right before the move (`approval._hands_to_documenting`), since the reads ahead of it are time another road can
     settle a later report or evidence revision, repoint the issue, or persist a later verdict in: where it no longer
     carries the report, `pr_number`, `review_returned_verdict`, and `verification_evidence_*` records in hand -- or
     the `review_subject`, `review_returned_subject`, and `review_approved_subject` the comment carried when the tail
     last read or wrote it, which every proof since was taken over -- the label stays and nothing it holds is
     written, and the next tick answers what moved. Neither road holds a returned
     verdict — no reviewer ran behind them — so a `review_returned_verdict` waiting beside the handoff, a later
     round's, is left for the road that finishes it and holds the move, while the handoff record ends.
  2. Awaiting-human path: resume on the dev's locked spec; on a successful pushed fix, bump `review_round` and stay on
     `workflow:validating`. A park standing over an unanswered requirements edit is the one claim that changes what the
     resume's answer MEANS, since a reply to a park is no drift and this is the road that delivers it. Two parks carry
     it: one this stage took over a report it owes, whose notice asked for a report in so many words, and one a drift
     resume ended on without answering the edit at all — a question, a timeout, a tree nobody could publish — which
     `requirements_drift_open` is what records, since nothing else on the comment says which road a park came off. The
     claim is read BEFORE the run, because the resume clears the park it was written beside. Either way the reply is
     read the way the drift resume's is — a report with no commit publishes onto the head the
     pull request carries instead of parking as a question, a commit is held to the same contract before the gate sees
     it, and the report is stamped with the revision that batch delivered, which its own settlement records as the
     baseline. What that publication SPENDS is the round `rounds.py` says it does: nothing where the debt came back
     from `in_review`, whose hand-back already reset `review_round` for the very edit this publication answers —
     counted again, an edit answered a tick late would leave its reviewer one round short of the same edit answered
     at once — and the ordinary next round for a debt this stage's own roads left, where nothing was published when
     the resume parked and the head the reply lands is one no reviewer has read.
     A transient park (`_VALIDATING_TRANSIENT_PARK_REASONS`) with NO new comment goes to
     `_try_recover_validating_transient_park` instead, which retries silently and, on `cleared` / `pushed`, posts the
     **Recovery follow-up** described below before clearing the park. An `agent_timeout` park is answered by the
     BRANCH rather than by the run, whether that run committed or not, and on every road rather than on the
     requirements-drift one alone.
     `pre_dev_fix_sha` decides ONE thing there: whether the killed run committed at all. It is the head that run
     began at, which is where the round found the checkout and not where the pull request is — a resume can commit
     and be interrupted before anything is written, so the round behind it opens on a commit the publication has
     never carried. Read as the publication, a clear taken over it hands the next reviewer a checkout the pull
     request is short of, and a push pinned to it names a head the pull request never had and is refused unmeasured,
     parking a human over work the branch is holding. So the reading decides —
     `validating/stranded._stranded_evidence` again. Level with its publication clears. A commit the pull request has
     not got is work to publish rather than a reason to wait, and goes out through the gate below named by the commit
     that reading froze and leased to the remote tip it counted that commit against, so a pull request somebody moved
     is the moved remote the reading refuses on rather than a lease this push would overwrite. On the drift road that
     commit is also work no report describes, and which run made it decides: one the KILLED run made is published
     with the debt staged into the write the push makes, since nothing here can ask a session that is gone, while one
     an earlier resume stranded leaves the park standing — clearing there would drop the edit's obligation, and the
     human the timeout notice already mentioned is who answers it. Every refusal holds the same way, because a clear
     taken on a reading nobody could take sends the next reviewer to a checkout with no receipt and no gate debt
     behind it. Both holds answer `unsettled` rather than `stuck`, and that word is what keeps them out of the
     worktree-drift reroute below: what stands there is the reading of the branch, so a relabel taken over one would
     clear the park and hand the checkout to `workflow:resolving_conflict`, which publishes it with nothing staged
     for a commit no report describes.
     Its git-touching retries — the deferred push, the commit a timeout killed the disposition before it saw, and
     the commit an earlier interrupted resume stranded under one that committed nothing — publish through the same
     [size gate](#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr) the shared dev-fix publication
     passes. Where the park came off that road the commit a timeout left is work no report describes — the run was
     killed before it could report — so the debt for it is staged into the write the push makes, and the report hold
     below asks a human before any reviewer reads the head it leaves. Such a push spends the round `rounds.py`
     decides for it, which is none where the park was delaying a publication an `in_review` hand-back had already
     reset the budget for, since the retry lands that very publication. A retry that resolves also drops that budget
     record with the park it clears — the publication it was for has happened, or the branch turned out to carry
     none, so a record left standing would spend nothing for the next unrelated publication this stage owes. That is
     also why the retry has a fourth
     answer: `held`, meaning the gate took the candidate and the tick is over.
     The caller then posts no follow-up, clears no park, and moves no label — the gate has already parked on a reading
     nobody could take, or handed the issue to `workflow:decomposing`, and written its own state, so a follow-up would
     announce a recovery that did not happen and a relabel would move the issue off the state the gate just set.
     Exception: on a `review_cap` park the human reply does NOT wake the dev — the operator must post
     `/orchestrator add-review-rounds N` on its own line (honored only from an author `ALLOWED_ISSUE_AUTHORS` lists
     — an outsider's command is filtered out before the parse), which resets
     `review_round` to `max(0, MAX_REVIEW_ROUNDS - N)`, clears the park, and falls through to spawn the reviewer this
     same tick. Values at or above the configured maximum grant one full review budget rather than extending the
     budget past it. Nor does a reply to a reviewer-side park — a reviewer timeout or crash, or a returned verdict's
     `reviewer_unverified` / `reviewer_unrecorded` park — which clears the park into a fresh reviewer round instead
     (`_reviewer_retry_awaiting_action`): a bare `/orchestrator continue` hands that round the thread through it, while
     a reply with words in it is requirements the report never saw, so the round is held for the developer to answer
     them first. The two verdict parks never retry themselves, so that reply is the only thing that ends them. A
     further exception: a bare `/orchestrator continue` on a session-failure dev park (`agent_silent` /
     `agent_timeout` / `agent_execution_failed`) is intercepted (`_continue_command_action`) and retries the dev on
     the neutral `_DEVELOPER_CONTINUE_RETRY_PROMPT` — NOT the literal command, which the dev has no context for — while
     `_handle_dev_fix_result` still publishes any stranded commit; a bare continue on a park needing a real answer
     refuses (`_refuse_parked_continue`) and stays parked. A command carrying real guidance, or a normal reply,
     resumes the dev on that text, with the commit-subject and developer report contracts restated beside it
     (`_build_human_reply_followup`), as they are on the retry prompt above — either resume can rotate into a fresh
     session, which carries no transcript to have read them in. (The classification is shared with `implementing` /
     `documenting` / `resolving_conflict`, the retry prompt is not: `documenting` reruns its docs prompt and
     `resolving_conflict` retries on the plain `_CONTINUE_RETRY_PROMPT` — its agent finishes a rebase and authors no
     subject, so no subject contract rides with it; see the drift-detection section for the bare-continue hash
     exclusion.)
  3. **Report hold.** A developer report this issue recorded and has not seen confirmed on the pull request — a
     `developer_report_delivery` no publication has been bound to, or a `developer_report_pending` the
     reconciliation has not settled — holds the reviewer (`report_hold._report_holds_the_review`). It is asked behind
     the drift resume, which is what supersedes a report written against old requirements, and ahead of the round
     cap and the spawn. A delivery is bound first wherever the code-publication receipt names this pull request and
     the checkout, resolved as the reviewer resolves it, stands on the commit that receipt names — which is what a
     recovered failed push and a settled adjudication leave — and settled through the
     [reconciliation](#the-developer-report-transaction-every-dispatch) on the same tick, so the reviewer can run
     behind it. What no retry settles parks once under `report_undeliverable`: a record written against a
     requirements revision other than the pinned baseline (the drift check has just refreshed it, so the mismatch is
     an edit no resume answered, such as an `ACK:` to a later edit), a receipt naming no publication of this pull
     request, a checkout on a commit the pull request never received, a checkout that has picked up loose work since
     or moved off the commit a bound transaction is about — the reading the reconciliation's own evidence takes,
     which stands DOWN on a mismatch so the routes behind it keep running, and on this stage the only route behind
     it is the reviewer the hold is stopping — a report the THREAD has moved out of reach — our comment under this
     receipt no longer rendering as the report,
     or a verified location gone, changed, or written by an author this deployment does not trust
     (`report_evidence.refuses_for_good`, the reading the implementing handoff takes) — and a debt no record
     describes at all, a run that committed and wrote no report whose park a reply answered without writing one
     either — read as a record of THIS work rather than of any: a delivery or transaction an earlier run left is an
     account of the branch before the commits a later run made, so the undescribed-work flag those commits leave
     outranks it and the report that retires it is one written over the branch as it stands. The loose checkout, the
     checkout a bound transaction can no longer be proved against, and the report the thread moved are each things
     the reconciliation deliberately stands down on rather than holding, so nothing else would ever say so and the
     reviewer would be suppressed for the life of the issue in silence. The binding itself is
     `report_settlement`'s, over the pull request, its description, and the issue read again. A reply resumes the
     session through the drift route, whose report supersedes the undelivered one. Anything else still owed — a
     reading nobody could take, or a pull request somebody moved under the report — holds silently, since the next
     tick is as likely to settle it. So does a binding this tick's settlement sent, or the settlement's own preparation
     or commit, that did not land over the comment it read — refused over a comment another road moved since, or never
     confirmed — and a post or re-read that left the report owed while another road wrote the comment: the tick's state
     is withheld, so a park behind it would be a notice no write could record, and the hold says nothing at all until a
     later tick binds or settles afresh, finding a posted report by its receipt, or finds nothing owed. A park the
     awaiting-human branch cleared into this round is written when the hold stops it, in the one guarded commit step 4
     captures over the comment read afresh
     (`review_resume.settles_a_bought_round`), so its reply is not answered twice.
     Once no report is owed -- on arrival, or once this tick settled it -- a claimed `developer_report_rewrite_debt` is
     asked last (`report_refresh._rewrite_holds_the_review`), against the pull request's head read the way the
     reviewer's subject reads it; a head nobody could read holds for the next tick. A claim that is to be paid or
     refreshed first waits for requirements the drift check stood down for -- an edit behind an owed reviewer round,
     or a reply with words that bought one: nothing is paid over a report that never saw them and nothing is asked
     under a baseline the issue has left, so the tick holds, drops `validating_reviewer_owes_a_round`, and the next
     tick's drift resume answers the change, whose own report of the head pays the debt, or, after an `ACK:`, the
     next refresh asks under the new baseline.
     - **Paid.** A settled report pays the debt where it is about that head on the pinned pull request, was PUBLISHED
       -- a report verified where it already stood pays nothing, since the one standing when the head was rewritten is
       the account of the head before it, and a settlement recorded before its mode was is held the same way -- and
       was written against the `user_content_hash` baseline (`report_rewrite_debt.pays_the_debt`). It is re-read at
       its location as the reviewer road reads it before the key is written `null`, and the reviewer runs on that tick.
       A location nobody could read holds; a report out of step with its handoff, removed, edited, or untrusted pays
       nothing and holds nothing, so step 5 parks for it with the claim still standing.
     - **Refreshed.** A readable claim naming the pinned pull request and the head it stands on, on the branch the
       issue pins (`_resolve_branch_name`) -- the one the resume checks out and binds its report to -- whose settled
       report is of the head the rewrite replaced or of the rewritten head itself without paying
       (`RewriteDebt.owes_a_refresh`), holds the reviewer while the developer is asked for a fresh report of that
       head (`workflow/stages/validating/report_refresh.py`). So does a settled report of neither head, on the
       claim's pull request and branch and written against the current baseline, once the
       [approval-squash lineage](#the-rewritten-head-report-debt-every-dispatch) proves it the approved commit this
       orchestrator's squash collapsed into the claim's `previous_head` and, behind the drift wait, it re-reads intact
       at its location as the reviewer road reads it: that report keeps the commit it is about, and the prompt names
       the approved commit beside the squash. A lineage nothing proves and a report out of reach are left to step 5's
       refusal, and a tree or location nobody could read holds with nobody run. The world is frozen first, before
       any agent runs: a
       code-publication receipt group with a member this build cannot read (`late_receipt_damage._damaged_receipt`,
       the damage the reconciliation would only hold on, with nobody told), one that does not name the rewritten
       head, or a checkout not standing on it clean parks under `report_undeliverable`, naming what to repair; a
       reading nobody could take holds. The checkout is the one the resume runs in, read where it stands and
       recreated only where it is gone (`implementing/worktree._ensure_resume_worktree`), since `_ensure_worktree`
       reclaims an existing directory whose branch carries nothing past the base, loose work included. The
       locked session is then resumed on `_build_report_refresh_prompt` with the live-pause guard; a launch the run
       circuit refused, a shutdown kill, and a live pause write nothing and are asked again next tick. What the run
       left is read by `report_refresh_outcomes.py`: a `REPORT: READY` over a checkout still clean on the head, with
       the pull request's head and the requirements read again unchanged, is recorded through
       `report_delivery.recording_stops_the_tick` under the frozen baseline with no round or watermarks riding it,
       then bound to the receipt's publication and settled through the reconciliation, all on this tick -- so a
       refused post, a lost response, a crash before the binding, or one on the settlement write is finished by the
       reconciliation or the next tick's hold, found by its receipt, with no second developer run and no second
       comment. The per-tick base refresh rebases nothing while that report is recorded and unsettled
       ([base refresh](labels-and-state.md#base-refresh)), so it settles about the head it was written for, and a
       base that moved meanwhile is rebased onto behind it, leaving a debt of its own. A head somebody pushed or an
       edit made while the agent was out records nothing and parks nothing: the reviewer road refuses a head the
       claim no longer explains, and the drift resume answers the edit. A run
       that committed (recorded `developer_report_unreported_work`) or left loose work, one that timed out, one
       that ended on `REPORT: VERIFIED` instead of writing a report, and one whose `REPORT: READY` cannot be recorded
       -- its notice naming the refusal, as the implementing seam's does -- park once under `report_undeliverable`;
       every
       other finished run with no report -- a question, a silent exit, a quota stop, a provider refusal, an unfinished
       command -- takes the agent-failure park `_on_question` classifies (route `report_refresh`). A run that ended
       with a tool step still active, which is what the AGY recovery behind the resume hands back once its one retry
       is spent, is read as that unfinished command ahead of its message, so a `REPORT: READY` block it wrote parks
       `agent_execution_failed` rather than being published. Each park sets
       `developer_report_owed`, so the reply resumes the developer on the requirements-drift reading and the report
       it writes -- a report alone, with no commit -- is published once exactly as written, settles, and pays the
       debt, and the reviewer is handed it, with no later tick posting it again or repeating its settlement; until
       then the tick holds with nothing run. Every refresh tick ends
       there, a settled one included: the next tick finds the debt paid.
     - **Held for nothing.** Anything else -- a claim nobody can read, another pull request or branch than the issue
       pins or the settled report is on, a head somebody pushed over the rewrite, a settled report of neither head
       that no
       [approval-squash lineage](#the-rewritten-head-report-debt-every-dispatch) proof reaches -- holds nothing, so
       the subject resolution in step 5 refuses the stale report as it would with no claim.
  4. A reviewer verdict an earlier tick persisted and never disposed of (`review_returned_verdict`) is finished ahead of
     the cap and the spawn (`review_resume.resumes_a_returned_verdict`), running no reviewer, folding no usage, and
     spending no round: one not yet handed through a run rebuilt of its round over the subject resolved again, in a
     checkout restored only behind that reading, one handed whose relabel never landed by that relabel and the launch of
     its one owed developer, its checkout restored only behind the relabel. A change request is finished from its
     record as persisted -- round, subject, evidence claim and its receipt, and anchor -- and only the words it posts
     and resumes its developer on are formatted (`engine/review_findings.py`): one persisted before findings were
     formatted, its verification declaration still raw, posts the concise findings where its feedback was never
     posted and hands them to its developer, each check not shown passing kept as its diagnostic, with the record's own
     feedback left as persisted and no post made again. A subject that moved and a handed verdict
     whose developer may have run, its subject resolved again, drop the verdict, restoring no checkout, so one that will
     not restore holds nothing up, in a guarded commit over the comment read afresh -- only while it still carries that
     verdict, nothing of the tick's own beside it, and the latter only while that reading's run ledger still shows the
     launch not owed, decided on that ledger too, so a start written away with its charge left unstarted drops nothing
     and the next tick launches the developer owed -- and end the tick, for the next tick's round; a verdict another
     road put in place of a handed one while its cleared anchor is written back, or a park another road recorded --
     before the guarded commit writing it back or under it -- ends the tick with nothing written or handed over; a
     tick a reply cleared a park into, where the report hold stops that round or a verdict waits, ends in one guarded
     commit captured over the comment read afresh against the tick's own reading and decided on the verdict and the
     park's flags -- the cleared park kept, save a park another road recorded there, its flags moved, which stands as it
     wrote it, what another road wrote meanwhile carried, and the verdict the park outlived dropped only where the
     comment still carries it -- the round running next tick (`review_resume.settles_a_bought_round`); a verdict or park
     another road moves after that reading
     refuses it,
     and the next tick answers the reply again. Each of those commits GitHub took and never confirmed is found by the
     next tick as it landed or did not, and finished from there with no second reviewer, post, or developer, and no
     review round but the one the confirmed commit itself leads to -- the round a reply bought, or a fresh one a
     dropped verdict leaves its subject for. A
     park recorded again for the same reason moves no flag and shows only in its notice, so a comment another road
     posted meanwhile that opens with the HITL mentions, as every park notice does and a status line may, writes nothing
     for the next tick to answer the reply again; one naming nobody is no park. A reading nobody could take holds the
     tick with nothing written ([pinned state](labels-and-state.md#pinned-state)). Otherwise, if `review_round >=
     MAX_REVIEW_ROUNDS` (default 3), park (`review_cap`). The park comment surfaces the `/orchestrator add-review-rounds
     N` escape hatch.
  5. Otherwise resolve what the reviewer is handed (`review_report._resolves_the_subject`): the pull request's head, and
     the developer report `developer_report_current` records, re-read from the exact location it settled at and held to
     its digest. A settled record that will not read, one about another pull request, one its own handoff does not
     describe, and a location that reads ABSENT or CHANGED — removed, edited, cut short, or written by an author this
     deployment does not trust — each park under `report_undeliverable` with `developer_report_owed` set, and so does a
     report that reads intact and is STALE: about another commit than the head the pull request stands on, or written
     against requirements the drift baseline has moved past (the rule the hold above holds an owed report to, an `ACK:`
     of an edit included; the baseline rather than the reviewer's own read, which carries the reply that bought a
     retried or granted round). So no reviewer runs and the reply resumes the developer, whose report is then published
     and reviewed; a head or location nobody could read holds the tick silently. The reviewer's own read has to be the
     revision the round was due to hand over — the baseline the drift check measured, or, on a round a control-only
     reply bought — a bare cap grant or `/orchestrator continue` — the thread through that reply
     (`validating_reviewer_round_requirements`), since that reply is the reviewer's to read; a reply carrying words is
     itself a requirements change and moves nothing forward: a thread that moved on past it — a criterion landing after
     the check or after the reply — is held the same way, the owed round stood down, and the next tick's drift check
     resumes the developer on it before any reviewer is handed the report. Every hold writes what the tick staged, so a
     cleared park and a cap grant with its notice are not answered again. A pull request with no settled report on
     record is refused the same way — parked under `report_undeliverable` with the debt set, so the reply resumes the
     developer for one — since a reviewer handed none would be judging work nobody has described. Before any of that
     is decided or written, the pinned comment is read once more (`review_comment._resolved_over`) and has to carry
     the report records and the `review_returned_verdict` the state in hand carries, and point the issue at the same
     `pr_number`: the subject was resolved from the state the tick read when it began, and a later report settled
     since — on the very head, by another road — is there and nowhere in hand, as is the issue pointed at another
     pull request, or a verdict another road persisted, which a later tick finishes. Where it does not,
     or will not read or parse, no reviewer is handed anything and the tick ends WITHOUT writing, since any write would
     put the replaced report or pointer back; the next tick resolves the later one. The reading that agreed is laid
     over the state the tick holds, measured from the comment as the tick read it
     (`review_comment._ResolvedSubject.lays_over`): a run another road charged and folded, the thread it read through,
     or a notice it posted while the subject was resolved is there and nowhere in hand, and every later reading of the
     round is measured from it, so left out here it would be written back over. Then persist
     `config.REVIEW_AGENT_SPEC` to `review_agent` (traceability only — the reviewer is spawned fresh each round with no
     resume) and the resolved subject to `review_subject` (`review_records`), in a guarded commit ahead of the spawn
     over the comment as that reading found it (`review_writes.lands_the_launch`) — the launch charge writes only its
     own fields, and the state the tick holds carries what only the round's own write may land, a cap grant's round
     reset among them, which a launch the run circuit refuses has to discard. The commit is decided on the report
     records, `pr_number`, `review_returned_verdict`, and its own `review_agent` and `review_subject` as that reading
     spells them -- a launch repeated over a subject already recorded stages those two unchanged: one another road
     moves behind
     it, a comment that will not read or was replaced, or an edit GitHub never confirms spawns no reviewer and ends
     the tick with nothing written — a launch recorded and never confirmed is committed again, with nothing sent, by
     the next tick's round, which charges and runs one reviewer. What else the commit landed over is laid over the
     state in hand, measured from that reading, as the binding was. The charge that launch then takes on the comment
     is the round's own write too, so
     it is taken into the reading every later write of the round is measured against
     (`review_comment._ResolvedSubject.carrying`): a run another road charges while the reviewer runs is then a change
     on the comment to keep, not this round's count to write back over it. Behind that write the workflow
     verification evidence current for exactly the subject is asked (`review_evidence`), since evidence is held to the
     subject the launch records. Run the reviewer with the read-only prompt, which quotes that report whole between the
     issue and the inspection commands, then quotes the evidence under its revision or says none covers the subject,
     names the configured `VERIFY_COMMANDS` or says none are configured, and teaches the RUN or REUSED declaration
     (see [the reviewer verification contract](../workflow/conversations.md#the-reviewer-verification-contract)); it
     must end with `VERDICT: APPROVED` or `VERDICT: CHANGES_REQUESTED`. A mid-run `paused` / `backlog` re-check
     (`_paused_during_agent_run`) right after the reviewer returns short-circuits BEFORE the usage fold, session record,
     verdict parse, verify gate, squash, or relabel, so the next tick re-spawns a fresh reviewer from durable state, and
     so does a run the shutdown sweep interrupted. A reviewer that returns has the subject it was handed staged again as
     `review_returned_subject` beside its usage, session, and return time -- by the park a timeout or a missing verdict
     takes, in its own guarded commit prepared before its notice (`review_writes.parks_the_return`), so a comment with
     no room for that park beside the run's records posts nothing, or by the disposition over its own last reading,
     so the usage is folded once: the launch's
     `review_subject` went down before the run budget was asked, so only this one says a reviewer really read the
     report.
     Before the timeout park, the no-verdict park, or anything a verdict earns is written, the pinned
     comment is read again against the reading the subject was bound to (`review_comment._records_stand`), and
     everything it changed since is carried onto the state in hand, whether or not the report records stand — a run
     another road charged or folded, the thread it read through, a round a reply bought — so every write the run
     makes from that state keeps it rather than putting back what the tick read. What a later road does is its own:
     a change request's developer run, below, runs long after this reading and writes the state in hand behind it
     with no reading of its own, so a usage fold, a watermark, or a comment id another road wrote during that run is
     lost. A report record it moved — a later report settled on
     the same head by another road — is carried the same way, so no write puts back the report the reviewer was
     handed, and the verdict is not acted on; a comment that will not read or parse carries nothing, and the tick ends
     with nothing written. A field the reviewer's tick moved too keeps both moves where they add up or only advance —
     the `issue_*` usage totals add, `issue_cost_sources` joins, and a comment-id watermark keeps whichever reading
     went further, each only over values spelled as their writers spell them — and the `orchestrator_comment_ids`
     ledger is merged, an id either side recorded kept once among the newest its bound holds — a ledger already past
     it cut to it even where the merge adds nothing — and an entry naming no comment dropped from either side, so no
     later scan of the ledger fails on it; any other field both moved is the round's
     own where the report records stand and the other road's where they moved. That reading watches `pr_number`
     beside the report records, so a verdict about a pull request the issue no longer points at is not acted on
     either, and `review_returned_verdict`, so a verdict another round persisted while the reviewer ran stays for
     that round's road -- this run is recorded, and its verdict neither persisted over that one nor acted on, since
     the disposition measures the run from this reading on. The round is measured from then on against the comment as
     each reading found it, so every later reading keeps each of those moves once. Every write the run makes from
     there is a guarded commit captured over the last such reading (`review_writes.py`): a field another road writes
     after it is kept beside the run's own -- its usage, watermarks, and comment ids joined as above -- while a report
     record, `pr_number`, or `review_returned_verdict` it moves, a `review_returned_subject` it replaces, the
     `awaiting_human` / `park_reason` flags a park is taken over -- which a round a reply bought over a parked reading
     stages as that reading already spelled them -- a comment that will not read or was replaced, or one filled past
     room for the write refuses the write with nothing written, and a park refused behind its notice leaves that
     notice with no park recorded, for the next tick's reviewer.
  6. Parse the last `VERDICT:` marker (`_parse_review_verdict`):
     - **approved** → handed, with the run, to the returned-verdict disposition (below), which persists it with the
       evidence its declaration earned and publishes that evidence before acting on it. Unless the records moved above,
       the issue has to point at the pull request the subject names, and the whole subject is resolved again
       (`review_coverage._subject_still_stands`), over the issue read afresh, and has to record as the one the reviewer
       was handed — pull request, head, requirements, and the report's revision and digest, its words read again at its
       location, where an edit or a removal refuses the reading itself — and then the pinned comment is read once more
       behind those requests (`review_coverage._verdict_still_stands`), since they are long enough for the issue to be
       pointed at another pull request or a later report to settle. A repoint, a push, an issue edit, or a report edited
       or removed while the reviewer ran or while the subject was resolved again, or a reading nobody could take, means
       the approval is not acted on: the run is recorded over what moved and the next tick resolves the subject as it
       stands. The approval reaches what follows only through its proof, over settled evidence that passed and covers
       every configured `VERIFY_COMMANDS` command, and parks under `reviewer_unverified` otherwise. Then, in order: (1)
       run the local verify gate
       (`verify._runs_the_gate`: `_run_verify_commands(wt, config.VERIFY_COMMANDS, config.VERIFY_TIMEOUT)`), then --
       whatever it said --
       resolve the subject again and read the pinned comment again behind that, watching `review_returned_verdict`
       beside the report records and the pull request pointer, before anything below is written — a comment that will
       not read ends the tick with nothing written, what the comment changed since the last reading is carried first,
       and a `verification_evidence_*` record moved there is a move as surely as a later report, since the approval
       would rest on evidence no longer current -- and so are a review subject or `review_approved_evidence` moved,
       and a `developer_report_owed` recorded, a debt the subject stands only without; a park or a `late_collapse_*`
       record another road put down there ends the tick with nothing written and the verdict kept, since a human or
       the squash recovery answers it and no write behind may clear or end it; an empty command tuple returns
       `not_run`, which advances without
       being evidence that anything passed, and any other non-ok result parks — only where the subject and those
       records stood: a result about a subject that moved while it ran is recorded, not parked on — through the
       funnel a returned verdict's parks take (`review_parks.parks_over_the_subject`, worded by
       `verify._verify_failure_park`), which holds it to the subject once more behind its own notice and lands it only
       behind a notice that was identified, with a typed `park_reason`
       (`verify_failed` / `verify_timeout` / `verify_dirty` / `verify_head_changed` / `verify_tree_changed`) and the
       approval / squash / handoff do NOT fire (see
       [`configuration.md#local-verification-gate`](../configuration.md#local-verification-gate)); otherwise, where
       the subject and the records stood, (2) post `:white_check_mark: codex review approved.`, then resolve the
       subject once more, prove the round's checkout still stands on the head that subject names with nothing left
       uncommitted (`handoff._Held.checkout_stands` — the gate proves the checkout only while its commands run and
       reads nothing where none are configured, the squash is taken from this checkout, and with
       `SQUASH_ON_APPROVAL=off` a checkout ahead of the pull request is one `documenting` would publish as its own
       recovered docs work; a moved or dirty checkout records no approval and squashes nothing, and one nobody could
       read holds), and read the pinned comment behind that comment — held to the report records, `pr_number`,
       `review_returned_verdict`, and the `verification_evidence_*` records in hand, and to the review subjects,
       `review_approved_evidence`, `developer_report_owed`, the park, and the `late_collapse_*` records as the comment
       carried them when the arc last read it, and laid over the comment as read, so a round spent or a run charged
       meanwhile is kept (`handoff._holds_its_records`): a push, an issue edit, a later report or evidence revision, a
       report recorded owed, a verdict put in place, or a park or collapse record another road put down meanwhile
       squashes nothing and records no approval -- the approval's verdict kept waiting behind a park or a collapse
       record, and retired behind anything else the approval was proved over -- and the approval comment stays on the
       ledger wherever the comment reads. The evidence the held
       verdict was proved over is proved again behind the comment as it is behind the gate
       (`handoff._Held.evidence_stands`), since its artifact can be deleted or edited on the pull request where no
       record shows it: evidence that no longer proves retires the verdict and squashes nothing, and evidence nobody
       could read keeps it for a later tick. Only then stage the subject as `review_approved_subject` and the claim
       beside it as `review_approved_evidence`, retiring the `docs_verdict` and `ready_ping_sha` an earlier approval
       left, since both are keyed on a head this approval may share. The approval the arc holds is the
       `review_returned_verdict` of its own run's round and subject, where one waits, and whichever write the arc
       makes sets it to `null` -- the park, the write recording a moved subject, or the squash tail's -- save where the
       subject would not read, which keeps it for a later tick; a verdict another road put in its place stays; (3) when
       `SQUASH_ON_APPROVAL` is on (default), call
       `_squash_and_force_push` (subject reuses the first commit when it carries a reusable `<prefix>:` form —
       Conventional **or** repo-local such as `event:`/`career:` — otherwise `<inferred-prefix>: <issue title>`, where
       the prefix is inferred from recent base-branch history via `_infer_subject_prefix` and falls back to
       `fix:`/`feat:` only when no repo-local prefix dominates; with `PR_REF_IN_SUBJECT` on (default) either subject
       is then normalized by `_subject_with_pr_reference`, handed the tracked issue's number as well as the pull
       request's: the line ends in exactly one ` (#N)` naming the request, one already reading that way is left
       alone, and the issue's own reference is dropped — whether a developer copied it out of recent history or an
       earlier publication left it standing ahead of its own, so `<subject> (#issue) (#PR)` lands as
       `<subject> (#PR)`. `N` is the reviewer run's `pr_number` here, and the pinned one when
       `_recovers_a_recorded_collapse` rewrites the branch afresh, while `off` keeps the selected subject exactly,
       appending nothing and stripping nothing; pushed with
       `--force-with-lease`). A branch of **one** commit is put through that same path for its subject alone whenever
       `PR_REF_IN_SUBJECT` is on and that normalization would write the subject differently — a line missing the
       reference, and one still carrying the tracked issue's beside it: same `reset --soft`, same
       hardened commit, same gate, same leased push, `squashed_count=1`, and no `:package:` notice, since nothing was
       collapsed. With the switch off, or with a subject that already reads as the normalization writes it, or with
       no commits over the base at all, the call is the `squashed_count=0` no-op it has always been and HEAD is
       untouched. That call
       answers
       a squash an earlier tick did not finish first, from the record that squash wrote before it ran, so a
       collapsed-but-unpublished branch is resumed rather than reported as having nothing to squash — and it does
       so whatever `SQUASH_ON_APPROVAL` says, since the switch decides whether a NEW collapse is made and one
       already on the branch has to be finished either way. A branch the recovery hands BACK after dropping a
       record is entered on the publication before it is handed on, since no rewrite follows that drop to read the
       pull request — and that reading is taken whatever `DECOMPOSE` says too, because with no push behind it
       there is no lease to answer a remote somebody moved. The checkout is proved again once the reading comes
       back, since the read is a request and a commit landing in that window is work no reviewer saw on a branch
       this road reports as standing where it planned. On squash / force-push failure, park awaiting human
       under a durable
       `park_reason="squash_failed"` and stay on `workflow:validating`, through
       `review_parks.parks_the_failed_squash`: prepared before its notice as the guarded commit it lands as, beside
       any verdict it does not retire, and landing only behind a notice that was identified, over the records in hand
       read again behind it and — on the approval road — the approved subject resolved again there; a push or an edit
       there drops the approval's verdict and parks nobody, a subject nobody could read or a notice that left no id
       writes what the squash left with the verdict kept and no park, a comment with no room for the park posts and
       writes nothing, and a park whose commit lands unconfirmed reports no human wait and is found standing, and
       mentions nobody again, by the next tick. The
       notice names which of four places
       that left the branch: the approved
       commits are still on it — the ordinary failure, which aborted before anything destructive or restored what it
       rewound, including a record whose reset never ran — or a collapse this tick could not finish is standing
       there instead, with the approved history reachable only from the head the record names, or the branch grew
       PAST that head and the approved commits are under the work on top of them, or none of it has been shown.
       The record, the checkout's own head, the recorded head as an OBJECT, and the ancestry between the two are
       all read, since an outstanding record is not proof the rewrite happened, a recorded head this host does not
       hold is a reflog entry nobody could look in, and one still reachable from HEAD was never rewritten at all.
       Once the squash returns, before that park and before anything below — the write a held squash makes included —
       the pinned comment is read again and has to carry the report records, `pr_number`, `review_returned_verdict`,
       and the `verification_evidence_*` records the state in hand carries, and the review subjects,
       `review_approved_evidence`, `developer_report_owed`, the park, and the `late_collapse_*` records as the tail
       last read or wrote them (`handoff._holds_its_records`): the rewrite and its force-push are time another road
       can settle a later report or evidence revision, record a report owed, repoint the issue, replace the verdict,
       park the issue, or record a squash in. Where it moved them, nothing more is posted and the label stays: the
       one write is the comment as read with the ledger entries of what the tail posted -- and the approval's own
       verdict set to `null`, save behind a park or a collapse record another road put down, which keeps it waiting
       for the human or the recovery that answers it -- and the collapse the squash recorded is the next tick's
       recovery to finish, over what the comment carries then; one that will not read writes nothing. The squash's
       own writes — the collapse record ahead of its rewrite, the size gate's — carry the state in hand whole, and its
       reply does not say whether it made any, so its gate is handed a client that guards and follows them
       (`squash_writes`). Each is held first to the same records,
       laid over the comment as read then, and landed as a guarded commit, exactly as the tail's own writes are, and
       one whose records moved or whose commit did not land is
       refused the way a write GitHub refuses is: the record ahead of the rewrite is not made and nothing is
       rewritten, and past the rewrite the collapse it recorded is left for the next tick's recovery. A refused write
       puts back with the state what the reading ahead of it took in -- the reading the state is synced with and the
       tail's last reading -- so a field another road wrote is kept by whatever lands behind it, a park included,
       rather than read as one the tick deleted. The reading
       behind the squash is measured from the last write it made, or from the reading before it where it made none,
       so a field another road wrote while it ran — a round a reply spent — is kept, and a usage fold the squash's own
       write carried is counted once; the push goes to the pull request the tail was handed. Every
       write behind that reading — the handoff's, the park's, the one a refused notice leaves — is held to the same
       records again, the report debt, the park, and the collapse record among them, laid over the comment as read
       just ahead of it, and landed as a guarded commit decided on them (`handoff.HELD_ON`), so what another road wrote
       behind the notice is kept, and one that moves them under the commit refuses it with nothing posted, written, or
       relabeled behind it. A record of the collapse whose commit lands with its response lost is taken by the squash
       as refused, so nothing is rewritten, announced, or parked; it carried the approval staged beside it, so the
       tail's reading behind the squash records what it posted and retires the approval's verdict, and the next
       tick's recovery finishes that collapse under the approval recorded, with no second reviewer. (4) On success,
       if `squashed_count > 1` post `:package: squashed N commits to 1` — a count of 0 or 1 replaced no history and
       posts nothing — seed the in_review watermarks (inside the
       `gh.get_pr()` try so a snapshot failure leaves them untouched; the walk advances through the leading run of
       the orchestrator's own comments plus the issue-thread ids `last_action_comment_id` already records as
       delivered, and stops at the first unseen human comment on EITHER surface, so a PR-conversation comment
       numbered below a consumed reply holds the seed back rather than being swallowed by it — the scan that
       follows drops the consumed reply on its own), then end the collapse record and persist —
       leaving `late_collapse_handoff_sha` in its place, the approved head for an approval that collapsed nothing —
       and only then, once that commit has landed, relabel to `workflow:documenting`, dropping that record in a
       guarded commit of its own behind the label. A rewrite leaves the evidence the approval rests on
       answering for the head the reviewer was handed, so that write also carries it onto the head the rewrite
       published -- a collapse, a one-commit subject rewrite, or the recovery's finish alike -- under the carry-forward
       decision described under
       [the verification-evidence transaction](#the-verification-evidence-transaction-every-dispatch), taken ahead of
       the comment that write is laid over (`squash_evidence`): only where both the tested commit and
       the published head read, in this repository, as the tested tree, the verification context is unchanged, the
       recorded review subject is still exactly the one the approval covers (its report revision and digest and its
       requirements with it -- a review recorded about the published head since is a later round, and refuses the
       carry), the pull request stands on the published head, and the evidence's artifact is still the one that
       settled. What is carried is the run step (1)'s verify gate
       made on the approved head where it passed whole and binds (`verification_local_runs`): what this orchestrator
       observed, carried as orchestrator-executed evidence naming that head as the commit tested, with its own
       transcript, over the same proofs save an artifact it never had. Where it binds nothing -- an empty
       `VERIFY_COMMANDS`, which runs nothing -- and on the recovery's finish, which runs no gate, the reviewer's
       evidence the approval was proved over is carried instead. The carry is recorded as a new
       `verification_evidence_pending` transaction -- the tested commit and tree unchanged, the published head its
       target, the carried run's transcript -- and `review_approved_evidence` is pointed at it, its digest and flags
       those that transcript earns, only where the very candidate that write's guarded commit sends -- another road's
       writes since included -- has room for the carry's record, its settlement, and the invalidation behind it; one
       without that room is invalidated in its place instead, in a commit of its own carrying no transaction
       (`handoff._Held.settles`), rather than left owed and unpublishable or unrecorded with its handoff, whose
       collapse the next tick would announce again. The relabel is held this tick, and the next tick's reconciliation
       proves the binding whole (the report and requirements included) -- and, for the reviewer's evidence, that the
       artifact its transcript was copied from is still current and says what was copied, ahead of the post and again
       at the settlement, so an edit or a deletion of it refuses the carry -- publishes an artifact naming the commit
       that ran and the new head as an equivalent-tree target, and settles it, so step 1's handoff moves the label over
       evidence answering for that head -- without a second reviewer, however many ticks the publication or the
       relabel take; a carry still owed for its approval, the comment having had no room to settle it, holds that
       handoff until a later tick settles it. A refused carry -- another or an unreadable tree, a context moved
       before or while the squash ran, a review subject replaced, a pull request moved off the head or ended, an
       artifact gone or edited, or a comment with no room for the carry and the approval's claim rebound to it --
       invalidates the current
       evidence into history, retires the approval it answers for with it (`review_approved_subject` written `null`,
       which no reader takes for an approval; one another road recorded in its place, of another subject, stands),
       and drops the handoff in that same write, so the next tick hands the head to a fresh
       review rather than a relabel; a pull request or artifact nobody could read records nothing and leaves the
       handoff for step 1 to decide again. Nothing is carried where the evidence already answers for the head (the
       squash rewrote nothing), save that a context moved meanwhile invalidates it all the same; nor where the
       approval rests on no evidence or on evidence the records no longer carry as the latest, which the coverage
       check below refuses on its own; the gate's run is evidence nowhere else. The relabel is held, with the rewrite
       already finished,
       unless the approval still covers the report as it reads at its location, the requirements over the issue read
       afresh (the approval's own revision and the baseline both), and the head over the pull request read afresh —
       the commit the rewrite published, or the head the approval was given where it rewrote nothing
       (`review_coverage._approval_holds`); an edit or a push during the squash is work nobody reviewed — and unless
       the pinned comment, read last, still carries the report, `pr_number`, `review_returned_verdict`, and
       `verification_evidence_*` records in hand, and the three review subjects as it carried them when the tail last
       read or wrote it; the next tick answers whatever moved, through step 1's handoff reading. A
       `review_returned_verdict` still waiting there is a later review than the approval this handoff finishes, so
       the label is not moved past it and the handoff record ends all the same. That record is ended over the
       comment read again once the label has moved, and only where it still names the commit this handoff
       finished beside the report, `pr_number`, `review_returned_verdict`, and `verification_evidence_*` records the
       move was taken over, and beside the three review subjects as the comment carried them just ahead of the move,
       so what another road wrote during the relabel stands. A verdict or squash handoff another road puts down
       during the relabel is past every reading here, so the move lands over it, and a later report or evidence
       revision settled, or a review subject replaced or removed, then leaves this handoff's record standing; either
       way the next `documenting` tick hands the issue straight back (its step 0), where step 1 answers the handoff —
       dropping it for the reviewer where the approval no longer covers the report, and invalidating a carried
       evidence whose review subject went — and the verdict holds the label.
       A relabel that does not land is not raised
       past the handoff: everything it owed is durable, and step 1 moves the label on the next tick instead of a
       second reviewer being run over a branch already published.
     - **unknown** (no marker) → park, split by whose failure it was
       (`_reviewer_no_verdict_park`). An empty last message with a non-zero exit (a crash), or a message opening with
       a transient provider refusal (`is_transient_provider_failure` — `API Error: 529 Overloaded` and its 5xx
       siblings), is tagged `reviewer_failed` so the next tick's transient-recovery branch re-spawns the reviewer;
       real reviewer text that merely omitted the marker stays `reviewer_no_verdict` for human adjudication.
     - **changes_requested** → handed to the returned-verdict disposition (below) the same way, held to the same
       whole-subject check first, the comment read behind it, since a change request of words the pull request no longer
       carries would pay a developer to answer a review of work that is not there; it is not acted on, and the run is
       recorded, wherever the subject moved while the reviewer ran or while it was resolved again. Otherwise it is
       persisted, the evidence its declaration earned -- a failed run included -- is published, and its handoff
       (`validating/review_handoffs.py`), its guarded commit prepared first so a comment with no room for it posts
       nothing, posts the feedback to the PR -- the reviewer's findings with its verification
       declaration set aside once that is read, each check not shown passing kept as its diagnostic, and the very words
       the fix prompt quotes (`engine/review_findings.py`) -- then flips the label to `workflow:fixing` BEFORE spawning
       the dev so the active job is observably "fixing reviewer-requested changes". Resume the dev with the fix
       prompt (routed through `implementing/execution.py`'s bounded coordinator to recover premature AGY command exits
       before disposition), and read what it hands back through `validating/fix_reports.py`, which holds the round to
       the developer report contract as the requirements-drift disposition holds a body-edit resume to it: on a new
       commit + clean tree the report is recorded as `developer_report_delivery` BEFORE the
       [size gate on a published pull request](#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr)
       reads the candidate, and on a push, bump `review_round`, clear the reviewer anchor, flip back to
       `workflow:validating`, and only then bind the report to that publication and settle it through the
       [reconciliation](#the-developer-report-transaction-every-dispatch) (`validating/report_settlement.py`). A
       no-commit run that finds a stranded unpushed fix on a clean HEAD (see `_handle_fixing` step 9) publishes it the
       same way; the report contract is the RUN's only where that run committed or reported, since the commit an
       earlier round stranded owed its report to that round and the debt it left is what holds the reviewer off the
       head this lands on.
       A no-commit run that ends on a **report outcome** is the one handover with no code in it: the fix prompt asks a
       reviewer item naming report content and no repository change to be answered in the report, so the report is
       recorded for the head the pull request is PROVED to be standing on and routed exactly as a pushed fix is,
       because the next reviewer reads the report as well as the diff. That proof is affirmative on both halves
       (`validating/fix_report_evidence.py`): the branch standing exactly where its remote is — a clean tree, a local
       HEAD, a fetched tip, a divergence git counted as zero both ways, and HEAD equal to that tip — AND the
       code-publication receipt naming that same commit on this pull request. Nothing is inferred from an absence,
       because "this run committed nothing publishable" is the same answer the disposition gives a checkout nobody
       could read, a fetch that failed, a divergence git refused and a remote that moved — each of which may be a
       branch carrying a commit the pull request has not got, which a report published over would describe a head no
       reviewer will ever see. Short of all of it the round parks under `report_undeliverable` with the debt recorded
       and the report NOT written, and the commit under it reaches the pull request through the ordinary gate once the
       reading that refused can be taken. A **verified** outcome names a report already on the pull
       request: it is re-read at that exact location, held to the digest and the author trust the developer named, and
       settled with nothing posted a second time. The round and the reviewer anchor are frozen once, and WHEN they are
       written is what tells the two handovers apart. A pushed fix spent its round on a commit the pull request now
       carries, so the size gate's own write beside its receipt is where they are durable and this route only
       re-applies the same pair for the one push that write could not carry. A report with no code in it has bought
       nothing until it is on the pull request, so NOTHING of the handover is written before it lands: the pair rides
       the record and is applied by the write that settles the report, confirmed or replayed — a post GitHub refused, a
       re-read that failed, a requirements edit landing mid-run, or a crash leaves the round unspent and the replay
       anchor intact for the round to be finished again. The label moves before the binding either way, and it is the
       only road to confirmation: the review hold on `workflow:validating` is what binds a delivery and settles it, and
       it refuses every reviewer while the report is owed — so a replayed publication or handoff counts no second
       round and no reviewer reads unconfirmed work. The record freezes the `fixing_round_settled` mark beside that
       pair, as `_handle_fixing`'s own rounds do. Settled under `workflow:validating` it is a mark no correlation
       places, and the next fixing tick retires it unspent; but a relabel that never lands — a process dying on it, a
       label write GitHub refused — leaves the delivery unbound on `workflow:fixing`, where `_handle_fixing` step 4
       binds it and hands the round back on that mark, rather than letting its scan read whatever arrived since
       under a route the settlement has just closed. The dev spawn records `stage="fixing"` for analytics.
       On any park (timeout, premature execution exit, no-commit, dirty, push-fail) the label STAYS
       `workflow:fixing` with `awaiting_human=True` and `_handle_fixing` owns the awaiting-human cycle thereafter. A
       premature AGY exit with unfinished tool steps triggers an immediate in-session continuation in the existing
       worktree; if unfinished steps persist across the continuation, the run is not publishable and parks under
       retryable `agent_execution_failed` while preserving reviewer anchors, feedback watermarks, and uncommitted
       edits. When a fix is committed and published, feedback watermarks are settled and `pre_implement_sha` is
       cleared on return to `workflow:validating`. A run that
       COMMITTED and handed over no usable report — including one that did not finish, which the engine exempts from
       the contract because the roads that exemption serves publish
       nothing either way — parks under `report_undeliverable` with nothing pushed, the commit in the worktree and
       the round unspent, in this road's own words rather than the engine's. Every park a reporting round earns carries
       the input its prompt delivered into the park's OWN write rather than a caller's afterwards: durable over
       feedback that still reads as unanswered, the park is one the next tick reads as fresh and resumes the developer
       over again, with nobody having replied and another agent run spent. An `interrupted` dev resume is ignored:
       the handler returns WITHOUT writing
       the post-spawn state (no resume-budget charge, no watermark, no park), so the pre-spawn `workflow:fixing` flip
       stands and the next tick re-runs the cycle; any commit the killed run left is republished later via the
       stranded-fix tail, not this run.
     - **the returned-verdict disposition** (`validating/review_disposition.py`), which every verdict a live round
       returns is handed to, prepares an approval or change request of a standing subject and then acts on it or parks
       it (`disposes_of_the_verdict`). A run that does not name, as a whole number, the pull request its subject is on
       is refused before anything is minted, written, or published. Otherwise the preparation takes the transaction its
       declared commands are minted as, then the subject held to what stands and the comment read again behind that
       resolution -- a `verification_evidence_*` record moved since refusing it as surely as a report -- then the run's
       own records staged, its usage folded over whatever usage that reading carries, and the verdict persisted as
       `review_returned_verdict` with that transaction in ONE guarded commit before anything is published
       (`review_writes.lands_the_verdict`), decided on the report, pull-request, verdict, and evidence records as that
       reading spells them: one another road moves after it, or a comment that will not read or was replaced, refuses
       the commit with nothing written or published, and an edit never confirmed publishes and acts on nothing, the
       next tick's reconciliation and recovery publishing and finishing the verdict and transaction it may have left
       with no second reviewer, artifact, fold, charge, or round. A subject that moved by then records the run with no
       verdict, and one nobody could read writes nothing; a verdict whose record would not read back as written, or
       that the comment has no room for beside its transaction -- measured again over the very candidate the commit
       sends -- is written and published nowhere, and parks under `reviewer_unrecorded` (below), saying which. The
       transaction is published through the
       [evidence reconciliation](#the-verification-evidence-transaction-every-dispatch), and the verdict is ready to act
       on only while the comment still carries it as persisted, its subject -- held to it once more, the comment read
       again last -- still stands, and its claim, judged over that last reading, has settled, or it declared none: a
       settlement of the very evidence it claims readies it, and a push, a later report, or a later revision
       superseding that evidence drops it. A later tick asks the same of a waiting verdict from the pinned comment alone
       (`waiting_verdict_ready`), holding the standing subject to the one the record names, and finishes a ready one
       (`finishes_the_verdict`) only beside a run its caller rebuilt of the verdict's own round and subject, naming the
       pull request that subject is on, each read as the record spells it: through any other -- of another round,
       subject, or pull request, naming none, or of a round `False` for `0` or a report revision `True` for `1` -- it
       acts on nothing and writes nothing. An owed transaction holds it for a later tick while its subject stands and
       drops it once that subject is proved to have moved, and a lost claim, published or reused, whichever the verdict
       -- superseded by a later revision included -- drops it for a fresh reviewer. The subject's pull request has to be
       the one the issue points at: `pr_number` moved to another -- while the verdict waited or between ticks -- drops
       it, since every road acting on it reads the pull request off the comment. Every write it makes is a guarded
       commit captured over the comment read again just before it, keeping what another road wrote there, before that
       reading or after it -- a round a reply bought included, both moves of a usage total, its cost tags, or a
       comment-id watermark, and the comment-id ledger merged -- refused with nothing written where a record it was
       decided on moved after that reading, and every drop names only the verdict this road holds, never one another
       road put in its place. The two parks a verdict takes instead of being acted on are filed in
       `validating/review_parks.py`: an approval relying on no valid evidence under `reviewer_unverified`, and a verdict
       that could not be persisted under `reviewer_unrecorded`, with nothing published or acted on -- its notice asking
       for room on the pinned comment only where room is what refused the verdict, and not where it would not read back
       as written. Each is measured before its notice is posted at the park's own write -- its flags beside the notice's
       ledger entry and watermark, each at the widest id, with the verdict it refuses dropped -- and taken over the
       comment as it stands, the returned run's usage and session unrecorded, where it has no room beside what that run
       staged, but only while that reading carries the report, pull-request, verdict, and evidence records the tick last
       read; nothing is posted or written where there is room for no park. Behind the notice the subject is resolved
       again and the comment read last: a push, a repoint, a later report, a verdict put in the place of the one parked,
       or a `verification_evidence_*` record moved there lands no park and drops only the verdict held, over the newer
       records, whether or not the notice left an id; where nothing proved a move, a subject nobody could read, or a
       notice that left no id and so may have reached nobody, lands none either and leaves the verdict waiting -- in a
       write measured there, since keeping the verdict can take more room than the park's own write, and not made where
       it does not fit. The write is the park's guarded commit over the comment as it stands -- a round another road
       spent behind the notice kept, both moves of a usage total or a watermark kept, the ledger merged -- measured
       again with what it carries, and not made where that no longer fits or a record the park was decided on moved
       after its last reading; the measurement before the notice is that commit prepared.
       Only a park that lands sets `awaiting_human` and `park_reason`, drops the verdict it holds (a
       `reviewer_unrecorded` park holds none, and leaves whatever record stands there as it is, and a
       `reviewer_unverified` park holds only the approval of its run's round and subject, posting and writing nothing
       where that is not what waits), and reports `park_awaiting_human`, once its write is down. Neither park retries
       itself: a bare `/orchestrator continue` buys a fresh reviewer, and a reply with words in it is requirements the
       developer answers first. An approval reaches the approval arc above only through its proof
       (`validating/unverified_approvals.py`), over a gate built on its run's checkout: the evidence its claim names has
       to be `verification_evidence_current` exactly, prove current again, show `passed` on its artifact re-read at the
       comment it settled as, and cover every configured `VERIFY_COMMANDS` command exactly, exiting 0 -- the claim's own
       flags refusing it early but never standing in for the artifact -- and the pinned comment, read last behind the
       proof, has to carry the report, pull-request, verdict, and evidence records the proof was taken over. A refusal
       comes back in the words the `reviewer_unverified` park carries, and the disposition parks it only once it has
       held the approval to its subject and claim again, measured from the comment its readiness was proved over: a
       refusal over a push, a later report, or a later revision is a fresh reviewer's to answer, so the verdict is
       dropped instead. An approval whose declaration earned no evidence parks with no proof asked, in the words its
       returning tick has for why; a later tick's record keeps no copy of them, so its refusal names what is true of
       every such declaration. A proof nobody could read holds the verdict, untouched, for a later tick; and a proved
       approval is handed to the arc measured from that last reading. A ready change request reaches its developer
       through its handoff (`validating/review_handoffs.py`): only the decision the request was persisted from -- its
       round, verdict, subject, and feedback -- is handed over in the tick its reviewer returned, and a later tick,
       holding no decision, hands the request over from the record alone, in the checkout the issue's developer resumes
       in -- restored only behind the relabel, once the launch is held to its subject, so a moved subject drops the
       verdict with no checkout restored. Nothing is posted, written, relabelled, or launched while the state in hand
       shows a park standing -- another road's, which the reading that proved the request ready carried onto it -- and
       the request waits for the reply that clears it. The handoff's guarded commit is prepared over the comment read
       afresh before anything is posted -- the verdict at its widest handoff, the developer's charge beside it -- so a
       comment another road filled, moved, parked, or replaced posts nothing; then the feedback is posted on that
       subject's pull request -- or, on a later tick, the post an earlier one made for this very request is found there
       -- in the words it posts, the line naming the review held to the request's round alone whichever reviewer and
       round cap it names, and the hidden receipt below them naming the request's round, subject, and evidence claim, so
       another request's receipted post in the same findings is never taken, or in the words a tick before receipts
       posted it in, raw or
       concise, only where that post stands behind the report and evidence the request was reviewed over and no landed
       handoff's ledger entry accounts for it -- this orchestrator's own and no copy another author wrote, read off the
       whole thread so findings quoting the pinned state's marker are found too, and taken instead
       (`validating/feedback_posts.py`) -- and a post that failed, left no positive whole id, or had no such pull
       request to go on holds the verdict unhanded with nothing written; the subject -- with the pull request the issue
       points at and the evidence the request claims -- is held again behind that post; the verdict is committed as
       `handed`, with the id of that post as its `anchor`, beside the `pending_fix_reviewer_comment_id` anchor BEFORE
       the relabel to `workflow:fixing`, decided on the report,
       pull-request, verdict, and evidence records, the anchor, the run ledger, and `awaiting_human` and `park_reason`
       as that reading spells them, and held to the room its preparation was -- another road moving one after it, or
       filling the comment past that room, refuses the commit with nothing relabelled or launched, and an edit never
       confirmed is resumed by the next tick from the comment, or handed again behind the post it finds; and the
       launch -- subject, evidence, run ledger, anchor, and no park standing, over the comment read again, and at the
       run circuit's charge and start the park's flags where the last reading had them -- is held to what stands
       before that relabel and once more before the developer launch, so the issue is never relabelled for a launch
       another write behind the handed one already ruled out, and a park another road recorded meanwhile is kept for
       its reply with nobody launched under it, a move behind any of those requests dropping the verdict and the
       anchor naming its post over the newer records -- unless the reading that proved the move records
       `agent_run_owed_started` at `handed`: that developer's own push moved it, and the verdict is retired as launched
       (below), its anchor kept for that developer's replay. Each such drop, and the retirement below, is a guarded
       commit decided on the verdict and `agent_run_owed_started` as the comment spells them -- a drop on the records
       and the anchor besides -- so another road's verdict in this one's place, or a start moved, refuses it with
       nothing written; a drop clears the anchor
       only where the verdict it dropped was this road's. A verdict already `handed`
       posts nothing again, and relabels and launches that developer
       — or, where `agent_run_owed_started` records that developer's start at `handed`, drops the verdict in a guarded
       commit over the comment as it stands, keeping what another road wrote since, the developer already launched
       (another road's run
       charged meanwhile under an `agent_run_fingerprint` of its own, a reviewer's say, records no such start, and a
       charge still standing as an unstarted `agent_run_reservation` under the launch's own fingerprint recorded none:
       the launch stays owed, honoring that reservation; a charge whose record no reader takes -- its fingerprint gone
       or unreadable, an unstarted reservation included, its phase unreadable under that fingerprint, or a run count
       below `handed` -- may be that very launch, and holds it), which is asked again right before every launch so a
       developer another road launched behind the relabel is not launched twice -- and once more by the run circuit, on
       the readings it charges and starts the launch from, which refuse it with nothing started or written over them
       where another road started that developer, charged a run over its reservation, started a run of that launch's
       very identity with no owed count, or left a charge whose record no reader takes -- a continuation of the launch's
       own start excepted -- after the handoff's last reading, pinned another comment in its place, or where the
       verdict, the anchor, the report records, the pull request the issue points at, or the claimed evidence moved
       there, the whole subject resolved again right behind the charge (`validating/review_launch_hold.py`;
       [The agent-run circuit](labels-and-state.md#the-agent-run-circuit)). What else another road wrote on a reading
       the launch stands on is carried onto the state the developer's run is written back from, and the developer's run
       retires the verdict only in a guarded commit decided on it, the pull request the issue points at, the start of
       its launch, the anchor, and the park's flags (`review_writes.ANSWERED`): the commit recording its report, which
       writes the retirement itself (`report_records.HandedRun.retires`), the commit landing a park the round takes
       instead -- a timeout's, a question's, or one over a tree or a push it could not publish -- or, where no report
       was recorded first, the hand-back behind the relabel. It is prepared over the comment read afresh right behind
       the run (`HandedLaunch.retires`), and every write recording or holding the report is decided on the same records
       (`HandedRun.decided_on`), so a verdict another road put in this one's place, a repoint, a start written away, the
       anchor repointed, or a park recorded -- behind the run or right ahead of the record -- writes, posts, pushes,
       relabels, and spends nothing of that result, and a hand-back refused over what another road wrote while the label
       moved settles nothing and keeps it; a park recorded over a repointed anchor would have a failed run's
       `/orchestrator continue` replay another comment, or none. The verdict stays until that write lands with it, so a
       commit never confirmed leaves both or neither and the ticks behind answer it as they would a confirmed one --
       never a retired verdict with nothing recorded, handed back for a review nobody asked for; a run paused, killed by
       the shutdown sweep, or refused at the circuit retires nothing. The parks the report domain takes over a report
       the run still owes -- none written, one it cannot record, an unfinished round, or an unproved head -- are that
       domain's guarded commit too (`report_delivery.parks_the_debt`), retiring the verdict in the park's own commit
       (`ReportWrite.behind`), so a lost park response leaves both or neither as well. Either launch is made only behind
       that anchor, still naming, as a whole comment id, the post the verdict
       records, which the fixing stage clears with the round's other bookmarks: a handoff that lost it, whose anchor
       names another comment, whose anchor is no whole id, or recorded before handoffs anchored their post, naming none,
       is held, nothing relabelled or launched, since no failed run could replay the feedback, or one would replay
       another comment as it. The record and both parks are described under
       [pinned state](labels-and-state.md#pinned-state).
  7. `paused` / `backlog` applied mid-run → each of the three dev resumes (the drift resume, the awaiting-human
     resume, and the CHANGES_REQUESTED fix resume) re-checks a FRESHLY fetched issue via `_paused_during_agent_run`.
     On a hit the handler returns WITHOUT running its result handler (`_post_user_content_change_result` /
     `_post_requested_fix_result` / `_handle_dev_fix_result`), so nothing is recorded of the report the run wrote,
     no comment posts, no push, no `review_round` bump, no relabel, and no pinned-state
     write. The committed work stays on the branch; the CHANGES_REQUESTED path leaves the pre-spawn `workflow:fixing`
     flip standing and `_handle_fixing` owns the issue once the label is removed — its no-feedback exit (step 7 there)
     is what publishes the discarded run's commit, since the reviewer comment that started the round is filtered out
     of every later rescan.
- **Output**: label moved to `workflow:documenting` (approval after verify + squash) OR `workflow:fixing`
  (CHANGES_REQUESTED, then back to `workflow:validating` with `review_round` bumped on the round's handover — a
  pushed fix or a report delivered with no commit) OR `workflow:decomposing` (the size gate held a fix or a
  transient-park recovery push) OR no
  label change with `review_round` bumped (awaiting-human resume, drift, transient-park recovery push — except where
  an `in_review` hand-back already reset the budget for exactly that publication) OR no label
  change and no reviewer (a developer report still owed) OR a HITL park.

## `_handle_in_review` (label `in_review`)
- **Trigger**: each tick while label is `in_review`. Set by `_handle_documenting` on the final-docs hop. Also runs on
  closed-`in_review` issues for external-merge finalization.
- **Input**: pinned `pr_number`, `branch`, `dev_agent` / `dev_session_id`, and three watermarks (`pr_last_comment_id`,
  `pr_last_review_comment_id`, `pr_last_review_summary_id`) — one per id namespace GitHub uses for PR feedback. Mixing
  any two namespaces under one watermark would silently drop or replay one side. `last_action_comment_id` is read
  beside them but is not a fourth watermark: it is the issue thread's own delivery cursor (see
  [`labels-and-state.md`](labels-and-state.md), **In-review watermarks**), so the thread is scanned past
  `pr_last_comment_id` with everything at or below that cursor dropped, and the PR conversation is scanned past
  `pr_last_comment_id` alone. A comment on the pull request numbered below a reply an implementing or validating
  resume already answered is unread, not delivered.
- **Internal flow**:
  1. If `pr_number` is missing → park awaiting human.
  2. Read the PR via `gh.get_pr` and delegate the terminal arcs to the shared `_drain_review_pr_terminals` helper (also
     called by `_handle_fixing` and `_handle_resolving_conflict`). The orchestrator never merges from here, so any
     `merged` state observed was produced externally. Branch on `gh.pr_state(pr)`:
     - `merged` → stamp `merged_at`, set label `done`, write pinned state, emit `pr_merged`
       (`merge_method="external"`), close the issue, `_cleanup_terminal_branch`.
     - `closed` → stamp `closed_without_merge_at`, set label `rejected`, emit `pr_closed_without_merge`, close,
       cleanup.
     - `open` BUT the issue was closed manually → set label `rejected` WITHOUT branch cleanup so the operator can
       salvage the still-open PR.
     - `open` with an open issue → fall through.
  3. **A stale approval → relabel back to `workflow:validating`.** Asked right behind the terminals and ahead of
     everything below (`_hands_a_stale_approval_back`), on any of three readings. A report a requirements-drift
     resume recorded and this issue still owes its pull request — a delivery its push never carried, a transaction
     not yet settled, or the debt of a run that committed with no report. Or `in_review_handoff_pending`, the marker
     a hand-back leaves until its own relabel has landed, which is what an outcome recording NO report needs: an
     `ACK:` whose relabel failed leaves no debt, no drift to re-detect, and nothing else to say the move is owed, and
     a resume that PARKED — a question, a timeout — leaves the same silence over an edit it answered with nothing.
     Or a `review_approved_subject` recorded against another developer report than the one
     `developer_report_current` records now — another revision, other words, or a report where the approval saw
     none — or of that very report since edited or removed at its location, which the stage re-reads there every
     tick an approval of a report stands, or of one its `developer_report_handoff` no longer describes, the pair a
     reviewer spawn refuses too (`review_coverage._approval_stands`); the head can be the very one
     the approval, its docs verdict, and its ping were about, and nothing keyed on the commit alone would notice. Or
     one over evidence its squash carried onto the head whose review subject no longer stands
     (`verification_current.carry_answers`), which the same reading asks and `validating` then invalidates. Or
     one given other requirements than `user_content_hash` holds the issue to now
     (`state.approval_covers_requirements`) — requirements somebody was handed since, a developer resumed on an edit
     or a reply spent on a park, that no reviewer was. A
     location nobody could read holds the whole tick, since every route below would act on an approval nothing could
     vouch for. An approval recorded before that record existed carries none, and is handed back on this reading
     whenever a report is recorded — nothing says that report was the one approved. Each way the issue stands on an
     approval earned against requirements or a report that no longer stand. Left here the report is never bound, since
     the hold that binds it is `validating`'s, and the ready ping below could invite a merge on the stale approval. So
     `review_round` resets to 0 and the marker goes down in a write taken
     BEFORE the label moves — the two cannot be one operation, and only this order is recoverable: a label moved
     first and a write then lost would put the issue under a reviewer with the budget the stale approval was earned
     under, while a relabel that does not land leaves both durable on an issue this same step moves on the next
     tick. The marker comes off in a write of its own behind the move; lost, it costs one spurious hand-back — a
     re-review rather than a ping on an approval that is over — and that tick clears it. The label then moves with
     any park standing beside it: `validating` retries a failed push, binds and
     settles what a publication carried — a candidate an adjudication published included — and holds its reviewer
     until the pull request carries the report. This is what a failed drift push, a held candidate, and a process
     that died between the record and the relabel all come back through.
  4. **Fresh PR feedback (including any human CI-fix request) → route to `workflow:fixing`.** Read four sources
     independently: issue thread, PR conversation (shares the IssueComment id space but not its delivery record —
     each is read against its own cursors and merged only afterwards), inline review comments, PR review summaries
     (filtered to non-empty `CHANGES_REQUESTED` / `COMMENTED`). If any source is newer
     than its watermark, record `pending_fix_at` + per-namespace `pending_fix_*_max_id` bookmarks (and the full
     `pending_fix_*_ids` batch lists) and flip to `workflow:fixing`. The handler does NOT honor
     `IN_REVIEW_DEBOUNCE_SECONDS` here or spawn the dev — `fixing` owns debouncing, the dev resume, and the DIRECT
     bounce back to `workflow:validating`. Watermarks are NOT advanced on this route so `fixing` can re-discover the
     triggering comments.

     A first-tick migration runs ahead of the scan for an issue that reached the stage before the handoff seeded
     watermarks, and it seeds each missing cursor only as far as it can go without crossing input nobody has read.
     `pr_last_comment_id` gets validating's own approval-handoff walk (`_latest_pr_comment_ids`), so the two writers
     of that field cannot disagree: past the leading run of the orchestrator's own comments and the issue-thread ids
     `last_action_comment_id` records as delivered, stopping at the first human comment on EITHER surface that
     nothing vouches for, and 0 where there is no pickup anchor to walk from. `pr_last_review_comment_id` and
     `pr_last_review_summary_id` are seeded at 0 outright: the orchestrator posts on neither surface, so there is no
     leading run of ours to walk and nothing a seed could advance past that is not somebody's review — a legacy PR
     carrying review feedback no developer was ever shown routes it to `workflow:fixing` rather than losing it. 0 is
     persisted rather than left unset so the surface reads as already seeded.
  5. **User-content drift → relabel back to `workflow:validating`.** Reached when no fresh PR-side ID surfaced a
     comment but `_detect_user_content_change` still reports a hash change (a title/body edit, or an edit to an
     existing issue-thread comment whose id is already below the watermark). Capture unread PR-conversation comments
     past `pr_last_comment_id` BEFORE posting the notice — they are quoted into the prompt below, and the same list is
     what tells the watermark carry those ids were delivered rather than leaving it stopped under the lowest. Stage
     `in_review_handoff_pending` with the refreshed `user_content_hash`, before the resume: every write the
     disposition below makes persists the whole comment, that hash included, and once it is durable no later tick
     re-detects this edit — so the issue has to already carry something saying the move is owed. A report a run
     recorded, or the debt of work it withheld, says it on the roads that leave one (a nonzero-exit run that
     committed publishes nothing and records `developer_report_unreported_work` beside the debt); an `ACK:` and a
     park with no report at all leave none, and the marker says it for them. Staged together, a death past the
     first durable write leaves an issue that knows it owes the move, and
     a death before it leaves one that simply re-detects the edit. Resume
     the locked dev session with `_build_user_content_change_prompt` (quoting issue body + recent comments + the
     captured PR-conversation comments). The carry over that list is taken TWICE, once before the disposition and
     once after: the disposition writes durably — the report ahead of the size gate, the receipt the push leaves, a
     park's own state — and a process dying past one of those writes with the carry still to come leaves a report
     and a push standing over feedback marked unread, which buys a `fixing` round next time the issue is in review
     for words the prompt already quoted. The early pass crosses what the prompt delivered so the first durable
     write carries it; the late one crosses the notices the disposition posts, which do not exist yet. Both stop at
     the first comment nothing vouches for, so the early pass can only ever cross less.
     All three successful outcomes — a pushed fix, an `ACK: <reason>` no-commit
     reply, and a no-commit reply ending on a report outcome (`"reported"`) — reset `review_round=0` and bounce
     directly back to `workflow:validating` — the reset and the handoff marker persisted before the relabel, for the
     reason step 3 carries, so an `ACK:` whose relabel does not land is still handed back by step 3 next tick.
     The session's report is recorded before the push and bound only after the relabel, so no tick finds a settled
     report beside a label still claiming the stale approval; `validating`
     holds its reviewer until the report is confirmed. A no-commit response without the `ACK:` marker or a report
     outcome parks via `_on_question`, and a push that fails parks here for that tick — step 3 hands it on after, on
     the handoff marker every parked outcome writes: the edit is unanswered, so the approval is stale and only
     `validating` reads the reply as the rest of that resume, ahead of the feedback scan that would otherwise route
     it to `workflow:fixing`. An
     `interrupted` resume short-circuits via `_ignore_if_interrupted` BEFORE `_post_user_content_change_result` and
     the watermark bump, returning WITHOUT writing pinned state so the drift stays unconsumed for the next process to
     retry. A mid-run `paused` / `backlog` (`pause_guard=True`)
     short-circuits the same way, right after the interrupted check.
  6. **Manual-merge HITL path** (only reached with no owed report, no fresh PR feedback, AND no drift):
     - `pr_is_mergeable` is `None` → try next tick.
     - `False` → park with `unmergeable`; HITL ping mentioning every `HITL_HANDLE`, then carry the issue-side
       watermark over the park comment — unless the pinned comment, read again first, no longer carries the report,
       verification evidence, or approval records (the review subjects and `review_approved_evidence`) in hand or
       points the issue elsewhere (`review_comment._records_in_hand`),
       since the park writes the state in hand whole and would put a report settled, a revision recorded, or a
       pointer moved, during the request back; nothing is
       posted or written then, and the next tick hands the issue back. The park is a **bounded** one
       (`bounded=True`): the feedback scan that let the tick reach here ran several GitHub round-trips ago, so a
       reply written since is numbered below this
       notice, and stamping `last_action_comment_id` at the notice id would put that reply under both cursors the
       next scan reads.
     - `True` → check `gh.pr_has_changes_requested(pr, head_sha=head_sha)` (a standing human CHANGES_REQUESTED on the
       current head vetoes the ping). The ping requires either `docs_checked_sha == pr.head.sha` with `docs_verdict` set
       OR `gh.pr_is_approved(pr, head_sha=pr.head.sha)` (a human/bot APPROVED review on the current head). When the
       gate passes, post a one-shot `:bell:` ping de-duplicated by `ready_ping_sha` — which a fresh approval
       retires, so a report re-reviewed on an unchanged head is pinged again — once the subject the approval covered
       has been read again right before it (`merge_gate._still_ready`): the approved report still reads at its
       location, the issue read afresh still carries the requirements the approval was given and
       `user_content_hash` holds, and the pull request read afresh still stands on the head the ping names
       (`review_coverage._approval_holds`), the evidence the approval was proved over included, and — last,
       directly ahead of the write — the pinned comment still carries the report, verification evidence, and approval
       records in hand and points the issue at the same pull request (`review_comment._records_in_hand`). The
       mergeability, review, report, and evidence requests ahead of the ping are time in which another road can
       settle a later report or record a later verification revision, a human can edit that report or the issue, or
       a push can move the head; any of those, or a reading nobody could take, pings nobody and writes nothing -- so
       no older revision floor is written back over a later one -- and the next tick hands
       the issue back, resumes the developer on the edit, weighs the new head, or reads it again. The ping is NOT a
       park: `awaiting_human` stays false so subsequent ticks still react to new comments / an external merge.
       Unlike park branches, the ready ping does NOT call `_bump_in_review_watermarks`. It posts an issue comment
       like a park does, but it is not a park and owes the thread no "everything below here is read" claim: the ping
       is recorded in `orchestrator_comment_ids`, so the next tick's id-set filter drops it with no mark having to
       move — and a mark that moved could only cross a human comment that landed since the scan above.
  7. Every park inside this handler carries `pr_last_comment_id` over the orchestrator's own park comment, so the next
     tick does not see it as fresh PR feedback. The carry is a walk, never a jump to the newest comment: it starts at
     the mark already persisted and advances only through comments it can vouch for — ours by the id ledger or the
     hidden marker, quoted into this tick's own prompt, already recorded on `last_action_comment_id` (issue thread
     only), or a bare `/orchestrator add-agent-runs` — and stops at the first it cannot. Both IssueComment surfaces
     share one id space, so a human PR comment written while the tick was deciding is numbered BELOW the notice
     posted after it; a mark carried to the newest comment would take that PR comment with it and no later poll could
     go back for it. A thread the walk cannot re-read leaves the mark where it was rather than raising, since the
     notice is already posted and the park still has to be recorded.
- **Output**: label moved to `done` / `rejected` (terminal), OR `workflow:fixing` (fresh PR feedback), OR
  `workflow:validating` (drift — a pushed fix, an ACK no-commit reply, or a report with no commit — or a stale
  approval: a developer report still owed, or a handoff marker whose relabel did not land; each resets
  `review_round=0`), OR a HITL park (unmergeable, missing pr_number, drift-resume
  failure), OR a HITL ping (no relabel), OR a no-op tick.

**Recovery follow-up.** Both callers of `_try_recover_validating_transient_park` — the `workflow:validating`
awaiting-human branch and the `workflow:fixing` parked branch — post one short issue comment on a `cleared` / `pushed`
outcome, before the pinned write that clears the park, so the HITL mention that filed the park is not the thread's
last word after the system has healed itself. The wording is chosen by `_recovery_followup_comment(gh, issue, state,
park_reason, outcome)` from the (reason, outcome) pair: the failed push retried, a commit the branch was carrying
unpublished pushed, the branch proving it carries nothing the pull request has not got, or the reviewer being
re-spawned. Both timeout clauses are about the BRANCH rather than about the run, because one outcome covers two
histories — the killed run committed before it died, or it committed nothing and stood on a commit an earlier
interrupted resume left — and only the branch is left to say which. It carries no @mention (closing the loop must not
notify a second time), and it is skipped entirely when pinned state carries no `last_action_comment_id` — nothing then
says a mention was posted (the pickup anchors one on every issue it starts, so only a legacy issue can lack it) — or
when the pair has no wording. The outcomes that healed nothing — `stuck`, `unsettled`, and `held`, the
`_RECOVERY_HOLDS_THE_PARK` set — post nothing at all, so a still-failing retry stays silent poll after poll.

Exactly one lands per park episode, and the receipt for that is the thread rather than pinned state. The post and
the write that clears the park are two operations, so a process that dies between them leaves GitHub holding a
comment no local record names — any receipt written beside the clear would die with it. So every follow-up carries
`_RECOVERY_FOLLOWUP_MARKER` (`<!--orchestrator-recovery-followup-->`), and `_episode_already_announced` looks for it
among the comments past `last_action_comment_id` before wording a new one. That watermark is the park's own mention
id — the bounded walk every such park takes reaches that mention whenever nothing unread sits under it, and an unread
reply is what keeps the recovery from firing at all — which scopes the search to this episode: a later park stamps a
higher one, so an older follow-up sitting below it cannot silence the next recovery. A forged marker costs its author
the notification they would have been spared anyway.

The late size gate's `late_owner_unreadable` park heals the same way and by the same rules, from its own owner
(`late_owner_settlement.py`) and under its own marker (`<!--orchestrator-late-owner-recovery-->`), so a follow-up
from one mode's episode cannot silence the other's. Two things differ. Its retry hangs off a durable
`late_owner_check_pending` on the generation rather than off the park, since the routes it has to survive skip the
park entirely; and its follow-up is posted *before* the write that clears the park rather than after, so the crash
window loses the write instead of the sentence — which the thread-marker check then makes free to repeat. A park
whose own notice GitHub refused (`late_park_notice` still owed) heals silently: it told nobody anything, so there is
no alarming last word to retire and a follow-up would be the first thing the episode said. What that park is and why
its retry re-reads rather than re-running anything is in
[`../workflow/roles.md`](../workflow/roles.md#the-owner-read-a-finished-run-has-to-pass).

The same failure window is why the batch `_AwaitingValidation.build` freezes drops the orchestrator's own comments
— by recorded id AND by `_ORCH_COMMENT_MARKER`, the pair `_rescan_fixing_feedback` already uses. Every
awaiting-human decision helper reads a non-empty batch as "a human replied", and a follow-up whose id-recording write
never landed is still ours; the marker is what says so when the id ledger cannot. The dev resume those decisions fall
through to is handed that same frozen batch rather than reading the thread again, and `consume_comments` settles it
through the batch, which advances the issue watermark alone.

What that settlement waits for is the RUN. `_resume_developer_on_human_reply` records the batch as consumed after
`_resume_dev_with_text` returns, and only for an outcome that counts the input as delivered: a launch the run circuit
refused (`invoked=False`), a shutdown-killed run (`interrupted`), and a live pause consume nothing, while a timeout, an
empty result, and a question park all do. Delivery is not resolution: the park's reason and the question it poses are
written by the disposition behind the resume and are untouched by the settlement, which is `engine/prompt_delivery.py`'s
ordinary pinned ratchet (the report transaction a run may record carries no consumed watermarks). A batch the
authorization or the measurement park reserves is neither resumed on nor consumed. An explicit `/orchestrator continue`
retry keeps its own semantics — it consumes the command and re-issues the orchestrator's continue prompt — and where its
session is missing or retired it is re-grounded off the conversation the SAME freeze took less the commands it consumes
(`_ReplyBatch.retry_thread_text`), so a comment written after the classification is neither quoted nor crossed. A launch
the lifetime agent-run circuit refuses keeps the batch unread end to end: its notice is bounded, the repair of its lost
write walks rather than ratchets, and the `/orchestrator add-agent-runs` grant puts back the park the refusal displaced,
so its own tick is that resume, run on the same reply. The REFUSAL that answers a bare continue on a park needing real
guidance is handed the batch its caller classified and consumes that, then walks through its own note with
`park_watermarks`, rather than reading the thread's tip.

Each stage takes that batch ONCE per parked tick and hands it on: `workflow:implementing`'s handler freezes it before
`_handle_parked_continue_command`, whose passthrough hands the same batch to the drift check and the resume, and
`workflow:validating`'s handler builds `_AwaitingValidation` before its drift check. A command or reply landing after
that read is in no part of the tick. The drift check on a parked tick measures the requirements by what the park had
already read — the frozen comments at or below its watermark (`_ReplyBatch.answered`) — so replies to the park are the
batch's to deliver rather than an edit that takes the drift road, which would quote those replies inside a
whole-thread excerpt (control commands included) as the body edit they are not, and settle THAT read once its run is
back — the reply crossed under a prompt cut at 4000 characters where the batch it belongs to is deliberately
uncapped so nothing the followup quotes can be recorded as an omission. Only a change the replies do not
explain — the title, the body, a comment the park had already read — is drift. The batch's delivery record names the
requirements revision it answers — the fingerprint of the frozen read through the last reply it delivers — and the
settlement records it as `user_content_hash`, so a delivered reply never comes back as an edit, on this stage or the one
a handoff reaches. Every classifier on the thread — the parked-continue classifier, the measurement park's
`_answers_the_measurement_park`, the quiet timeout recovery's no-reply gate, and the reservation inside the freeze —
reads the batch a developer would be HANDED, cut by `implementing/parked_replies.py`: `prompt_delivery.human_replies`
less a bare `/orchestrator add-agent-runs`. A park notice lands ABOVE a command written while the agent was out, and a
forged `<!--orchestrator-comment-->` can be pasted over one; counted as somebody's words, either makes the batch look
mixed, and the resume then delivers the bare command to a developer as prose. A grant's command the grant left unread is
cut out the same way on every road. The authorization park reads the last reply the id ledger leaves, less an answered
grant, and the freeze asks it the same; while that park stands its command is in no developer prompt, even where a later
reply demoted it.

`_park_awaiting_human` posts on the issue (not the PR) so the HITL ping appears alongside the rest of orchestrator
state. The PR comment that triggers a route to `workflow:fixing` is the human signal; awaiting-human is reserved for
*unrecoverable* states (unmergeable / missing pr_number).

## `_handle_fixing` (label `workflow:fixing`)
- **Trigger**: each tick while label is `workflow:fixing`. Two routes set this label:
  - `_handle_in_review` when fresh PR feedback (any of the four surfaces, including a human CI-fix request) arrives —
    records `pending_fix_at` + per-namespace `pending_fix_*_max_id` bookmarks and the full `pending_fix_*_ids` batch
    lists.
  - `_handle_validating` on a `CHANGES_REQUESTED` verdict, flipped BEFORE the dev spawn. This route does NOT set
    `pending_fix_at`; it records `pending_fix_reviewer_comment_id` (the id of the reviewer-feedback PR comment) as its
    lone replay anchor. The dev runs inline and on a pushed fix validating flips the label back itself (clearing the
    anchor). Only the parked outcomes leave the fixing handler to own the awaiting-human cycle.

  Also runs on closed-`workflow:fixing` issues so an externally-merged PR finalizes to `done`.
- **Input**: pinned `pr_number`, `branch`, `dev_agent` / `dev_session_id`, `pending_fix_at` + per-namespace bookmarks
  (in_review route only), the three in_review watermarks (left behind so the rescan can re-discover the triggering
  feedback), `IN_REVIEW_DEBOUNCE_SECONDS`.
- **Internal flow**:
  1. PR-state terminals mirror `_handle_in_review` (shared `_drain_review_pr_terminals`). `_handle_fixing` catches its
     own `gh.get_pr` exceptions and hands `pr=None` to the helper, which is a no-op.
  2. Closed issue with no resolvable PR → no-op.
  3. Open issue with no `pr_number` (manual relabel) → park (`missing_pr_number`).
  4. **Everything this issue's report obligation owes**, ahead of the scan below
     (`stages/fixing/report_recovery.py`). The position is the whole point: what a dead tick consumed rides the same
     record, so a scan running past it reads that feedback as unread, pays a second developer to answer it, and
     replaces the first developer's report with the second's.

     Three questions, in the order they can be asked. A round whose **hand-back was written and whose relabel never
     landed** is relabelled to `workflow:validating` and nothing more: the hand-back's own write already retired the
     mark, took down the parks a publication answers, and stamped `fixing_round_handed_back`, so the move is all it
     still owes -- and scanned past instead, feedback that landed meanwhile would resume a developer ahead of the
     reviewer that round's report is owed. That comment reads the same after a relabel that DID land and an
     anchorless move back onto this label, so what decides is `review_returned_subject`: a round whose report no
     reviewer has returned over is still owed that review, while one a reviewer read is not, and a deliberate move back
     after the review is answered as usual (`round_marks.py`). `review_subject` would not do, since a launch the run
     budget refused writes it too. A round whose report **SETTLED** while nobody was looking is
     finished and handed back: that settlement closed this route's bookkeeping -- `pending_fix_at`, the bookmarks and
     `review_round` -- while the issue stayed on `workflow:fixing`, so a scan running on past it would answer an
     in_review batch as a validating one. What licenses the hand-back is the `fixing_round_settled` MARK that
     settlement raised and nothing weaker: the settled report and the code-publication receipt both outlive the
     transaction that made them, and a delivery is claimed by one key whoever wrote it, so the record settling there
     can be an implementing candidate's or a drift resume's -- closing THAT route's bookkeeping and raising no mark of
     this stage's. The reviewer-requested round `_handle_validating` runs inline under this label freezes the mark on
     its record too, so the delivery it leaves unbound here when its relabel back to `workflow:validating` never
     lands is handed back by the binding below exactly as one of this stage's own rounds would be. The mark is placed
     through `round_marks.py` before it is acted on and CONSUMED either way, since a mark this stage may not place is
     the mark of a round that is over regardless and only the relabel is withheld.

     A record a crash left **UNBOUND** is answered next. Whether the code went out is RE-PROVED against the checkout
     rather than remembered off the persistent receipt -- a tree provably clean and a head it could name -- while where
     that head stands is the binding's to ask, over a pull request it reads AFRESH (`report_publication.py`), because
     the only one this tick holds was fetched before it began. A binding that settles ends the tick through the
     hand-back above; one whose post did not land relabels nothing, since the transaction is the
     [reconciliation](#the-developer-report-transaction-every-dispatch)'s to finish and the bookmarks it replays from
     have to outlive this tick. A binding whose guarded write did not land over the comment this tick read -- refused
     over a comment another road moved since, or sent and never confirmed -- ends the tick saying and writing nothing,
     since the tick's state is withheld and a notice behind it could never be recorded; the next tick binds afresh, or
     the reconciliation publishes the transaction where the binding landed after all. A settlement whose guarded
     commit or its preparation did not land ends the tick the same silent way: the reconciliation ahead of the next
     handler finds the posted report by its receipt and settles it, or finds nothing owed where the commit landed after
     all, and the mark that settlement raised hands the round back once. A post or re-read that leaves the report owed
     -- its answer lost, the requirements edited under it -- while another road wrote the comment ends it the same way,
     since the comment is asked again behind it and the tick's state is withheld rather than written back over that
     road's evidence, verdict or newer record. A record nobody can READ parks
     under `report_undeliverable` with the record untouched, since the debt is claimed by the key alone and reading it
     as an absence lets the scan through. The two refusals no later poll takes back -- a worktree GONE, and a tree this
     host proved DIRTY -- announce once and RELEASE the record as they park, with the pairs it froze applied in that
     same write: left there, restoring or cleaning the checkout would publish the report and send the issue to review,
     which is the decision the notice exists to put in front of a human. That write is the park's own guarded commit
     (`engine/report_delivery.parks_the_debt`), owning the delivery and the transaction it superseded beside the park
     and decided on every report record this tick read: what another road wrote meanwhile survives, a newer record it
     wrote is never released with the one this tick found -- no notice is posted and nothing is dropped -- and a
     release that did not land, or landed unconfirmed, ends the tick silently. A reading nobody could TAKE is neither,
     and buys nothing at all: nothing published, nothing released, no notice, and the poll behind it asks again.

     A reviewer's change request handed over to this label (`review_returned_verdict` with `handed`) is answered right
     behind that, still ahead of the scan (`validating/review_resume.finishes_a_handed_request`): its feedback is a
     comment this orchestrator posted, which the scan filters out, so the no-feedback bounce would pay a second reviewer
     for a round already reviewed. It stands down while a park stands, whose own dispatch answers first -- the run
     circuit's `agent_run_limit` over a launch it refused, say. A developer launch still owed is made once
     (`validating/review_handoffs.HandedLaunch.owed`), with no relabel: the issue is on this label already, and writing
     it again would emit a `stage_enter` nothing made, and its checkout is restored only once the launch is held to its
     subject, so a moved subject drops the verdict with no checkout restored; one that may have started -- a run ledger
     whose record of that launch no reader takes included -- is never made again. The owed launch resumes its developer
     on the record's feedback as `engine/review_findings.py` shows it, so a request handed before findings were
     formatted is answered on the concise findings, while the post it was handed over with stays as it was posted --
     the `/orchestrator continue` replaying it quotes its findings formatted too (`validating/feedback_posts.py`). One
     that may have started is held to the subject resolved
     again, the evidence its request claims, and the branch: a move, a commit the pull request has not got, loose work
     in the checkout, or a remote that moved past it (`validating/review_launch_park.has_moved_on`) drops the verdict in
     a guarded commit over the comment read afresh -- only while it still carries that verdict -- and the next tick's
     bounce publishes that work, or holds over it, and hands
     the pull request back, while a subject or branch nobody could read -- a fetch, a status, or a count that did not
     return -- holds the tick with the verdict kept. Anything else parks under `agent_execution_failed`
     (`validating/review_launch_park.parks`) in one guarded commit, prepared before its notice as the verdict parks are,
     and held to the subject and the comment's
     report, pull-request, verdict, and evidence records, and to the branch, once more behind its notice, the comment
     read behind the branch so a verdict another road put in place there is kept -- a commit that reached it there
     dropping the verdict for the bounce, a branch that would not read holding it, and a park another road recorded
     there kept as it wrote it -- and to the feedback anchor `/orchestrator continue` replays: one cleared, before the
     notice or behind it, is written back from the record in the park's own commit, and one naming another comment
     holds the launch with no park. A run ledger that reads behind the notice as the launch owed again -- its start
     written away, its charge standing unstarted under the launch's own fingerprint -- lands no park either, and the
     request waits handed for the next tick to launch, honoring that charge. That commit is decided on those records,
     the anchor, the park's flags, and the run ledger as the reading behind the notice spells them, so a move after it
     refuses the park with nothing written or reported, and one GitHub never confirmed is found standing, or not, by
     the next tick, which posts no second notice.
     A cleared anchor an owed launch needs is written back ahead of it in a guarded commit of its own, decided on the
     park's flags too and never made over a reading that shows a park standing, and every write here refused withholds
     the tick's state.
  5. Rescan unread feedback across all four surfaces, each past the reader or readers it answers to, reading the two
     IssueComment-space surfaces through the same per-surface cursors `_handle_in_review` uses — the issue thread
     past `pr_last_comment_id` with everything at or below `last_action_comment_id` dropped, the PR conversation past
     `pr_last_comment_id` alone. That is what a manual relabel straight into `workflow:fixing` depends on: no
     handoff seeded a PR-side watermark, so reading the pull request past the issue-thread cursor would hide every PR
     comment numbered below the last reply a developer answered. Orchestrator comments are filtered by
     recorded id AND the hidden `<!--orchestrator-comment-->` body marker, and the pinned record itself is dropped by
     IDENTITY beside them — it carries a marker of its own and nothing writes its id into the ledger, so an issue
     whose cursors sit below it would otherwise quote this stage's own bookkeeping to a developer, which the
     settlement then refuses as the pinned comment and records for nobody. The batch (`_FixingFeedback`) keeps each
     surface as its own list and derives the merged issue-space and prompt orders from them, because the settlement in
     step 10 owes a different reader for each surface.

     The two REVIEW surfaces are read through the delivery owner's own classifier
     (`prompt_delivery.classify_review_trust`) rather than through the trust gate beside it, because that classifier
     is what the settlement applies: an item the scan admitted and the settlement refused is quoted to a developer
     and recorded for nobody — a refused entry is neither delivered nor blocking, so the surface's watermark does not
     move and the next tick hands the identical comment to a second developer. That classifier carries no
     forged-marker rule, and its absence is deliberate: the orchestrator posts no review and no inline comment, so a
     body quoting `<!--orchestrator-comment-->` there is a reviewer quoting it and nothing else. On the two
     IssueComment surfaces, where the orchestrator does post and the id ledger evicts, the marker rule stands.
  6. If `awaiting_human`, first handle the **`/orchestrator continue` operator command** (`_handle_continue_command`).
     It is matched as an EXACT LINE (`^\s*/orchestrator continue\s*$`), so a comment carrying the command line AND real
     guidance still counts as the command; the command is handled on BOTH routes so a session-limit / session-failure
     park (`agent_silent` / `agent_timeout` / `agent_execution_failed`) is never resumed on the bare command text.
     Unfinished command executions are parked `agent_execution_failed` by `_on_question`, and two dev final messages
     are parked `agent_silent` rather than as a real `park_reason=None` question, because neither is the agent's own
     words: a recognized Claude session/usage-limit notice (`_is_session_limit_message`), and a transient provider
     refusal such as `API Error: 529 Overloaded` (`agents/provider_failures.py`'s `is_transient_provider_failure`,
     which prefers the terminal result event's `is_error` flag and otherwise requires a non-zero exit beside the prefix,
     so a successful answer that merely quotes the error stays an answer). A quota reset, a provider that came back,
     and a retryable command failure are therefore retried here rather than refused as needing human guidance.
     The helper returns one of three
     actions: **replay** — an eligible session-failure park **with a reconstructable batch** (the in_review route's
     `pending_fix_*` bookmarks, or the validating route's `pending_fix_reviewer_comment_id` anchor): drop the poisoned
     dev session (`_drop_poisoned_dev_session` — so the retry re-grounds a fresh session on the committed branch), clear
     the park, and **replay the preserved feedback batch** (`_reconstruct_pending_fix_batch`) — the validating route's
     anchor quoted as `validating/feedback_posts.ShownPost` shows it, its findings formatted and everything else, its
     id included, the posted comment's, so a post made before findings were formatted reaches the fresh developer
     concise while it stays on the pull request as posted, and the batch settles exactly as over it — carrying the fresh
     feedback that says something (`_carried_fresh_feedback`) — any guidance posted with or beside the command,
     verbatim — but NEVER the bare command itself: a replay renders what it is handed as PR feedback to implement, so
     the command line would read as work to do. The rebuilt issue-thread half is cut from the SCAN's own read of that
     surface rather than a second one, for the reason step 9 takes everything else off it: a bookmarked comment
     edited or deleted in between would reach the developer in the prompt while the requirements fingerprint beside
     it never saw it. Dropping the bare command strands nothing, because what the resume settles is the
     replayed batch JOINED with the whole fresh rescan, each item against the reader of the surface it was posted on —
     so the command is recorded as answered on the surface it was typed into and does not re-fire next tick. Resume
     the fresh dev on that batch, skipping the debounce; **refuse** — a content-free continue (every fresh comment is
     a bare command) on a park it cannot retry (an unsafe park needing real human guidance, both `park_reason=None`;
     or an eligible reason with **no reconstructable batch**, e.g. a validating-route park whose reviewer anchor was
     never recorded or has since been deleted): the command comment is consumed on the surface it was posted on (so
     the refusal does not re-fire, and a later route reads the answered command as answered) and a note is posted, and
     the issue stays parked; **passthrough** — the command arrived alongside genuine guidance on a park with no
     replayable batch. That one is RESOLVED here rather than left to fall through: the park comes down and the resume
     below is handed the fresh reading minus the bare command itself, skipping the debounce exactly as a replay does.
     The command line is dropped because the prompt renders whatever it is given as pull request feedback to
     implement, and the operator wrote it to the orchestrator; dropping it strands nothing, since the resume settles
     what it was handed joined with the whole fresh rescan. Falling through instead would put the guidance behind
     the stay-parked default below, which refuses an operator's retry as "nothing new" for as long as an owed
     report's own pairs cover the rescan.

     What counts as "nothing new" is the reading the readers cannot give on their own. While a report is OWED they
     are held back until its publication lands, so the batch that report was written over still reads as unread: the
     record's own frozen pairs are what say so, and a rescan with nothing above them clears no park. An accepted
     `/orchestrator continue` is therefore resolved above rather than falling through — the stay-parked default would
     refuse the operator's retry as "nothing new" — and a comment that landed ABOVE those pairs runs as usual.

     Otherwise branch on `park_reason` AND the route discriminator `pending_fix_at`:
     - **Transient reason** (`push_failed` / `agent_timeout` / `reviewer_timeout` / `reviewer_failed` — the
       `_VALIDATING_TRANSIENT_PARK_REASONS` set) **and a park this road may answer** → call
       `_try_recover_validating_transient_park`. The validating route (`pending_fix_at` unset) always is, and so is
       one shape of the in_review route: a `push_failed` park with a report still OWED, where both groups the route
       would mis-account are frozen on that report's record and the default would otherwise hold the issue on a park
       nothing clears. On `cleared` or `pushed`, post the recovery follow-up (see the
       **Recovery follow-up** note above) and clear the park. With no report owed, clear `pending_fix_*` and flip back
       to `workflow:validating` (the helper bumps `review_round` on `pushed`). With one owed, nothing is cleared or
       counted here at all: the report the retry's own push is the publication for goes out first — bound to the
       commit THAT attempt's receipt names, never the standing value — and the hand-back behind it applies the pairs
       the record froze and takes the park down with the mark. On `stuck`, fall through to the worktree-drift check
       below. On `unsettled` — the reading of the BRANCH is what withheld the clear, either because nothing could
       place the checkout against its pull request or because a drift park stands over a commit the pull request has
       not got — the tick stops with the park exactly as it was filed and nothing announced: the reroute below may
       not re-read that park as a base advance, since reconciling it publishes the checkout with no report debt
       staged for whatever it carries. On `held` — the size gate
       took the candidate the retry was about — the tick stops outright: no follow-up, no clear, no drift reroute, and
       no relabel, because the gate has already parked the issue or moved it to `workflow:decomposing` and written its
       own state.
     - **Any other awaiting-human shape** (transient reason on the in_review route, non-transient reason like a real
       agent question, dirty-worktree park, or silent-crash park) → return silently and keep waiting for a human
       reply. We cannot distinguish "agent has a real question" from "agent reported nothing to change" by inspection
       (both surface through `_on_question` with `park_reason=None`), so auto-routing either would silently bypass the
       HITL contract.

     **Worktree-drift dead-lock breaker** (`_reconcile_parked_fixing`). Reached only from the
     stuck-validating-route-transient branch above — an `unsettled` answer stops in the dispatch instead — so the
     park that arrives is one whose self-recovery could not clear the condition, and whose
     underlying cause may be a base advance that landed mid-park (the per-tick base sync deliberately stands down on
     every `awaiting_human` park — `_sync_pr_worktree_to_base` returns at its `awaiting_human` gate — so nobody else
     will sync this worktree). On a clean worktree the breaker routes to `workflow:resolving_conflict` — seeding
     `conflict_round` when absent, clearing the park, posting a PR notice, emitting `conflict_round`
     `action="entered"` (`stage="fixing"`) — in either of two shapes, both reconciled by the conflict handler, which
     owns rebasing AND publishing a PR branch:
       - **behind `<remote>/<base>`** (a local `rev-list HEAD..<remote>/<base>`) → needs a rebase;
       - **already on base but local HEAD ≠ the live `pr.head.sha`** (a rebase a prior run ran but never pushed) →
         needs a force-publish (see `_handle_resolving_conflict` below).

     The routing decision is cheap — no extra fetch, since `pr` was already fetched this tick. With no drift (the
     worktree is in sync with the PR head), or a dirty worktree, the park is left intact and the issue keeps
     awaiting a human. An operator who wants to freeze this reconciliation applies `paused`, which hard-skips the
     issue at dispatch so the breaker never runs. The `pending_fix_*` bookmarks and in_review watermarks are left
     untouched so the eventual in_review re-entry still re-discovers the feedback.
  7. If there is nothing this tick may act on — the watermarks already cover the bookmarks, or a report the issue
     OWES has already answered every item the rescan found (its record's frozen pairs again; an explicit
     `/orchestrator continue` still replays) — publish any **stranded fix** first —
     `validating/stranded._stranded_evidence` against the worktree the issue already has on disk, i.e. a commit
     an earlier run left unpushed (a dev run whose outcome the live-pause guard discarded, a run killed before its
     push) — through the same [size gate](#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr)
     the shared dev-fix publication passes, since this is the second seam a candidate reaches a
     published pull request through and a
     bounce that pushed unmeasured would be the way past a ceiling every other route holds to. The gate is named
     BOTH ends that reading placed the branch between: the remote tip as the lease, and the local commit the count
     was taken over as the candidate. That commit is frozen BEFORE the count and re-proved after it, since `HEAD`
     is re-resolved by every command that reads it — and the checkout's cleanliness is re-proved beside it,
     since the fetch and the count are time enough for a tree to pick up loose work without its head moving
     at all. No developer ran on this tick, so nothing in the checkout is
     this route's output — and left unfrozen or unnamed, a commit landing between the count and the gate's own
     proof is what gets measured, pushed and receipted as the stranded work, with nothing here having read it. On a
     successful push adjust `review_round` per the same route discriminator the pushed-fix exit uses (`pending_fix_at`
     read BEFORE the clear: in_review route resets to 0, validating route bumps by 1). Then clear `pending_fix_*` and
     bounce back to `workflow:validating`. While a report is OWED none of that happens: the gate is handed nothing to
     close, the push is still made — this bounce is the one tick left that republishes such a commit — and the report
     that push is the publication for is BOUND to it, off the receipt this attempt wrote. Where that binding settles a
     round of this route's, the write which took it already applied the pairs the record froze and the hand-back goes
     out through the same mark correlation every other settlement-driven relabel does; where it settles some other
     route's record it closes nothing here, and the bounce carries on to spend the round its own push earned. Where
     the branch PROVED it is carrying nothing to publish and the report is still owed, the relabel is held and the
     wait nothing left can end is announced once under `report_undeliverable` rather than kept in silence. That park
     is taken only on a proof: a reading that REFUSED is answered by the retryable hold below it instead, since the
     report is owed a publication and the refusal is the whole reason there is none -- held as a report no road can
     move, the retry never happens and a reading that comes back a poll later ends nothing.

     A worktree that is not on disk and a failed push bounce without pushing and without touching the round — the
     commit stays on the branch for a later push to carry. A probe REFUSAL does not bounce: a tree nobody could read,
     a tree holding loose work, a fetch that failed, a divergence git would not count, a remote that moved, and a
     checkout whose own HEAD read as something other than the tip the counts were taken against are
     each a branch that may be carrying the commit this exit is the last tick to publish, and every one of them reads
     identically to an empty branch. So the relabel is held with nothing spent, nothing cleared and no watermark
     moved, and the hold is announced once under `stranded_unproved` with the notice naming which reading refused.
     That park waits on a READING rather than on a person, so step 6's parked dispatch sends every later quiet poll
     straight back to this exit with the flags untouched: the branch is placed again, whatever the reading places is
     published, and the hand-back retires the park in the write that relabels — a refusal that comes back the same
     holds again in silence, and a human reply still takes the ordinary resume road. A report owed over such a
     branch rides that same park and that same retry: the record is untouched, so the poll that publishes the commit
     binds the report to it and hands the round back in one go. Only a
     branch PROVED to be standing where its publication is lets the relabel through. A candidate the gate HELD stops
     the bounce outright: the issue is on
     `workflow:decomposing` by then, and relabeling over it would publish the very question the gate just opened.
     This exit is the validating route's LAST chance at that commit: the
     reviewer feedback that started the round is orchestrator-authored, so the step-4 rescan filters it out and no
     later tick re-runs the dev on it.
  8. **Quiet window**: compute the newest `created_at` (or `submitted_at` for review summaries); if younger than
     `IN_REVIEW_DEBOUNCE_SECONDS`, return.
  9. **Resume**: build a `_build_pr_comment_followup` prompt over ALL unread surfaces, resume the locked dev via
     `_resume_dev_with_text` (`pause_guard=True`), and fingerprint the requirements that prompt was handed. Everything
     this stage derives from the issue thread comes off the SCAN's one read of it — the batch the prompt quotes, the
     watermarks that batch settles, the fingerprint, and the conversation a retired session's fresh spawn is
     re-grounded on — because a read taken later in the tick is newer: a comment landing in between enters whichever
     answers were taken late and none taken early, which is a comment an agent is shown and no watermark records, or
     one recorded as requirements nobody answered. That one fingerprint is written to `user_content_hash` (so an
     issue-thread comment just fed to the dev doesn't re-fire validating's drift check) and is the revision a report
     this round writes is STAMPED with: read back after the run, the settlement comparing its own fresh read against
     the record would find them equal, publish, and hand the reviewer a head over feedback no session ever saw.

     Three outcomes are ignored entirely BEFORE the ACK
     fast path, the stranded-fix check, and the settlement below, and each returns WITHOUT writing pinned state, so
     nothing is settled, `awaiting_human` is untouched, and the next tick re-discovers the same feedback: an
     `interrupted` resume a shutdown killed, a launch the run circuit never invoked
     (`guards._ignore_if_never_invoked`), and a mid-run `paused` / `backlog`. Past them the prompt reached an agent, so
     the batch it quoted is delivered and is **settled** right there (`_settle_consumed_feedback`), ahead of every
     disposition below, because the size gate's own durable write and a park's both land inside that disposition and a
     settlement taken afterwards would be lost to a crash in the window a hold's relabel opens. The one outcome that
     settles nothing is a run that finished on a **report outcome** (`report_outcomes._finished_on_a_report`): a
     `REPORT: READY` / `REPORT: VERIFIED` reply owes a publication this tick cannot promise, and feedback recorded as
     answered for a report no reviewer has is the reading that fork refuses. Then the two replies this round may act
     on no half of, held for a human ahead of every road below (`stages/fixing/reporting.py`): a message that reached
     for the report contract and MISSED, and a round that COMMITTED over a report an earlier tick recorded, whose
     record describes the branch before that commit. The head is read on every finished run for that second one, a
     timed-out one included: a timeout is a way to commit like any other, and the park it earns has a recovery that
     PUSHES what the run left -- read as a run that committed nothing, that work reaches the pull request under a
     report written before it existed, since the road that publishes it reads only the debt the earlier report still
     satisfies. A run nobody heard the end of is held to nothing else here: its own park answers it, and the recovery
     behind that park is what a missing-report park would take away.

     Then the report contract itself — the report of a commit this
     run made is recorded ahead of the size gate, and a run that committed with none parks instead, an unfinished one
     in this road's own words since the engine exempts it and this road publishes. Resumed developer runs execute
     through `implementing/execution.py`'s bounded coordinator, recovering premature AGY command exits with unfinished
     steps in the existing worktree before inspecting commits or reports; runs that exit with unfinished steps across
     the continuation do not count as valid reports and park under retryable `agent_execution_failed` while
     preserving reviewer context, feedback watermarks, and uncommitted edits until a completed fix is published.
     Then the disposition: a no-commit reply first checks for a **stranded fix**
     (`_stranded_evidence`): when the worktree is clean and HEAD
     is strictly ahead of the fetched remote PR branch (a fix committed by an earlier parked run whose publish was
     blocked — e.g. a dirty-park whose stray files were cleaned up afterwards), the handler publishes it through the
     normal push tail and treats the run as a pushed fix — this outranks the ACK fast path on both routes, so an acked
     stranded fix is published rather than relabeled. **ACK fast path** (in_review route only, a branch PROVED to be
     carrying nothing unpublished, and no
     report outcome, and no report OWED — a debt read off the RECORD rather than off this run, since a round standing
     on a report an earlier tick could not deliver would otherwise present the pull request as needing nothing while
     that report sits on the pinned comment): if the
     dev makes no commit this tick could READ but ends its message with the `ACK: <reason>` marker (the prompt
     instructs it to emit this when
     the comments name no actionable change — a vague "continue" / "ok" — and neither the branch nor its report has to
     change), clear `pending_fix_*`, post the ack as an
     FYI, and relabel straight to **`in_review`** without parking. Every probe refusal stands the fast path down with
     the stranded reading itself, because the ack vouches for the FEEDBACK and this road makes a claim about the
     branch: an unreadable or loose tree, a failed fetch, an unreadable divergence, a remote that moved, and a
     checkout that moved between the ahead/behind count and the read of its own HEAD each leave
     a pull request that may be short of a commit, so the reply falls through to the disposition and parks on the
     question instead of answering it. A run that ended on a report outcome is excluded
     by that same debt reading: the contract step just recorded its report, so the issue owes one from that line
     onwards — a report is a handover the next reviewer has to read, and it takes the publication road below rather
     than re-arming a ready ping on the approval it supersedes. A run that REACHED for the report contract and
     missed — a report block with an `ACK:` line beside it, text after the outcome, a marker that may render as code,
     which `report_outcomes._reached_for_a_report` is the reading for — never reaches this path at all: it is one
     broken contract rather than two answers, so it is held for a human AHEAD of everything here, under the misread
     park. Taken as the acknowledgement instead it would clear the bookmarks and hand the pull request back to
     `in_review` over work whose report nothing carries. Only a reply that never used the contract at all, on an
     issue owing no report, is the ordinary non-actionable `ACK:` that keeps the road it always had.

     Otherwise `stages/fixing/reporting.py` disposes the round: a report with no commit in it is published onto the
     head a FRESH reading proved the pull request to be standing on -- that reading's three HOLDS (a pull request
     this poll could not fetch, a head the
     checkout would not name, a tree status that established nothing) leave everything where it stands rather than
     parking, and a tree this host PROVED dirty ends a reported round -- committed or not -- on the terminal park
     its report owns, with the record released and the batch it delivered applied in that same write; a commit goes
     out through the gate, which is handed NOTHING to close while a report is owed;
     and the report the push is the publication for is bound and settled behind it, with the round, the bookmarks and
     the readers applied by that one write and the relabel held until it lands. Any other unmarked no-commit reply
     falls through to
     `_on_question` and
     parks awaiting human — a no-ACK reply may be a real dev question, and we cannot tell by inspection (a dirty tree,
     failed fetch, or a remote that moved past the local view also falls back to this park rather than pushing blind).
  10. **Delivery settlement** (`_settle_consumed_feedback`, applied in step 9 ahead of the disposition): regardless of
      dev outcome, each reader advances ONLY to the max id consumed on the surface that reader owns, ratcheted forward
      — tighter than a broad bump so a concurrent human comment that landed mid-handler survives to the next tick.
      Issue-thread items settle `last_action_comment_id` beside `pr_last_comment_id`, so moving the issue between
      `workflow:fixing`, `workflow:validating` and drift handling does not spawn a second developer merely to deliver a
      reply this round already quoted; PR-conversation items settle `pr_last_comment_id` alone, and the inline-review
      and review-summary items settle only their own watermarks, since nothing that advances the issue-action boundary
      has read the pull request. The pairs are derived through `workflow/engine/prompt_delivery.py`, the same producer
      a durable report transaction's recorded watermarks come from. A round that finished on a **report outcome**
      settles nothing here, because the report it owes is a publication this tick cannot promise and feedback recorded
      as answered for a report no reviewer has is the reading that fork refuses: those same pairs are frozen onto the
      report's own record instead — beside the round and the bookmarks — so the readers move in the one write that
      settles the report, and a reporting round whose report could NOT be recorded at all (a report over a tree
      carrying loose work, one this build cannot write down) settles the batch on its park, since nothing else would.
      The `pending_fix_*` bookmarks are NOT touched here:
      an explicit `/orchestrator continue` retry rebuilds its batch from them after these readers have moved past it,
      and what such a retry settles is the batch it REPLAYED joined with the fresh rescan — so the bare
      `/orchestrator continue` the prompt deliberately drops is still recorded as answered, on the surface it was
      posted on.
  11. **On a published report**: the write that completes the publication applies the pair the record froze — the
       bookmarks the consumed batch clears, and `review_round` per the route discriminator (in_review route resets to
       0, since the previous approval was for the prior head; validating route bumps by 1, same review cycle) — and
       raises the `fixing_round_settled` mark, the one thing that write cannot do for itself being to move a label.
       The hand-back behind it retires that mark in a write of its own, takes down the `push_failed` park that
       publication is the answer to — that one and no other, since an `agent_timeout` park belongs to whichever round
       left it and a LATER round can leave one over feedback this report says nothing about — and only then flips to
       `workflow:validating`: a tick dying between the two has to leave a round nothing can mistake for one that just
       settled. What such a tick does leave -- the mark down, the round stamped handed back, the label unmoved -- is
       the first thing step 4 asks about on the next poll, which takes the relabel again while no reviewer has
       returned over that round's report. On a round that PUSHED and owes no report, the round and the
       bookmarks were already closed by the size gate's own receipt write and this exit re-applies the identical
       frozen pair, which is a no-op rather than a second count. Re-applying is what makes a replayed publication or
       handoff safe. Docs do not run on this exit.
- **Output**: terminal `done` / `rejected`, OR label flipped to `workflow:validating` (a published report, a pushed
  fix owing none, the hand-back a round whose report settled earns -- its own, the recovery's (step 4), or the retry
  that landed a failed push -- the relabel a written hand-back never landed (step 4), OR no-new-feedback bounce),
  OR label flipped to `workflow:resolving_conflict` (stuck validating-route transient park while the worktree
  is out of sync with the PR — behind base or an unpushed local rebase), OR label flipped to `workflow:decomposing`
  (the size gate held a fix, a stranded-fix bounce, a transient-park recovery push, or a candidate that recovery
  published), OR label flipped to
  `in_review` (in_review route, ACK fast path on this tick only), OR a HITL park (`report_undeliverable` for a record
  nobody can read, a checkout that refuses for good, a reply that missed the report contract, a run that committed
  and did not finish, a commit over a standing record, or a report no road left on this issue can move; and
  `stranded_unproved` where the bounce could not place the branch against its pull request, which is the one park
  here waiting on a READING rather than on a person), OR a no-op
  (quiet-window wait, missing-PR park already set, or a reading this poll could not take).

## `_handle_resolving_conflict` (label `workflow:resolving_conflict`)
- **Trigger**: each tick while label is `workflow:resolving_conflict` (set by an operator relabel, by
  `_refresh_base_and_worktrees` when the auto rebase actually left conflicted files — a merely-behind-base PR rebase +
  push lands directly on `workflow:validating` — or by `_handle_fixing`'s worktree-drift dead-lock breaker when a
  validating-route transient `workflow:fixing` park whose self-recovery returned `"stuck"` is found out of sync with
  the PR head). Also runs on closed-`workflow:resolving_conflict` issues for terminal handling.
- **Input**: pinned `pr_number`, `branch`, `dev_agent` / `dev_session_id`, `conflict_round`. `MAX_CONFLICT_ROUNDS` from
  config.
- **Internal flow**:
  1. If `pr_number` is missing → park.
  2. Read the PR and hand it to the shared `_drain_review_pr_terminals` helper. `resolving_conflict` rebases the PR
     branch onto `<remote>/<base>` — it never merges, so any `merged` state was produced externally. Branch on
     `pr_state`: `merged` → `done` + close + cleanup; `closed` → `rejected` + close + cleanup; `open` → fall
     through.
  3. If the issue itself was closed manually while the PR is still open, flip to `rejected` without branch cleanup
     (operator may salvage). The closed-issue sweep does not surface `rejected`, so the operator must clean up the
     worktree / branch by hand if the PR later closes.
  4. **The two dev resumes** — a body edit mid-rebase, and a human reply on a park — are decided *inside* the
     reconciliation below (step 8), not in front of it. Both start an agent whose commit this stage force-pushes, so
     neither may run over a checkout nobody has placed against the remote. On a branch the remote has moved **past**,
     the push drops the commits that moved it and **no lease catches that** — the tip it is pinned to is the tip the
     resume itself read, so git has nothing to refuse. On a branch **ahead** of its remote, the head the round began
     at is a local commit the remote has never seen; leased against it, the resume's own commit is refused by the size
     gate as somebody else's movement, with the edit that prompted it already consumed. So an ahead branch ships its
     recovered commits first (step 8) and the human waits a tick. Every road out of this stage therefore runs behind
     one reading of the branch. What an *ahead* branch costs differs by resume, though, and only the **body edit**
     defers: it leases against the head the round began at, read off this checkout, while the reply's publication
     freezes the pull request's own head before the agent runs — so an unpublished commit under it changes nothing
     and the resolution goes out carrying it. Deferring the reply too would push a commit the reply was never fed to
     as finished work, which is exactly what an `agent_timeout` park over a clean commit leaves. And the edit *falls
     through* to the reply rather than ending the tick, because the drift hash covers the thread as well as the body:
     **every reply moves it**, so on a parked issue a reply arrives looking like an edit, and ending the tick there
     would drop it into the recovered push with the pre-reply commit shipped and the reply neither fed to anybody nor
     consumed. The one thing that does stop a reply on an ahead branch is a settled round still owed, since the
     recovered push is what pays it and they share the one receipt slot. The body edit is asked first, because it
     changes what
     "resolved" means and the reply may answer a question the edit has already overtaken; a pushed answer hands back
     to `workflow:validating`, and a bare acknowledgement — or a report with no commit — stays here without parking
     so a harmless clarification does not stall the rebase. The body edit's resume is held to the developer report
     contract (see *A body edit's report reaches the pull request with it* below). The reply
     path uses the same `_post_conflict_resolution_result` helper as the fresh path — except over a park that left
     a report owed, which it answers as the rest of the body edit's road — and a bare `/orchestrator
     continue` on it is intercepted like `validating`'s: a session-failure park (`agent_silent` / `agent_timeout` /
     `agent_execution_failed`) retries the dev on the neutral `_CONTINUE_RETRY_PROMPT` instead of the literal command,
     a park needing a real answer refuses, and an auto-rebase park is left to the refresh retry-unpark
     (`_continue_command_action` / `_refuse_parked_continue`). A park left by a *reading* rather than a question is
     not answered here at all — see the transient-park note below.
  5. Ensure the PR worktree, refresh the refs, and read the divergence (steps 6–8 below). The **cap check** comes
     after all of it, immediately in front of the rebase in step 10 and behind the settlement of a report this issue
     still owes: what `MAX_CONFLICT_ROUNDS` refuses is another *attempt*, and everything step 8 does is work already
     done that this stage still owes an effect for — a round a settlement published, commits an earlier tick never
     pushed, a report a resume saved, a human whose edit or reply is waiting. Refused with the attempts, none of
     those ends the loop; they strand, since nothing else pays a receipt, publishes a stranded commit, settles a
     saved report, or answers a person. Once step 8 is through and `conflict_round >= MAX_CONFLICT_ROUNDS`, park.
     Escape: (a) operator relabels off `workflow:resolving_conflict`, or (b) a new issue comment unparks via the
     resume branch, which step 8 reaches before the cap.
  6. Ensure the PR worktree via `_ensure_pr_worktree` (restores from `<remote>/<branch>` when THIS tick's fetch of it
     landed, NOT base — `_ensure_worktree` would discard the PR's commits — and never from a remote-tracking ref a
     failed fetch left behind, which resolves perfectly well while naming whatever was last seen; and from
     `<remote>/<base>` only when the remote itself says the branch is gone, which is a merged PR whose branch GitHub
     deleted seen from a host without the local ref: naming a ref nobody has would fail the `worktree add` on this
     tick and every one after it, and what
     that branch carried is in the base by then).
  7. Refresh `<remote>/<branch>` over `_authed_fetch` so a stale local ref doesn't mis-classify a "remote moved"
     situation as in-sync.
  8. Compare HEAD to the freshly-fetched `<remote>/<branch>`, through the one reading that resolves that ref once
     and counts against the commit it named. A reading that did not happen parks (`unreadable_divergence`) rather
     than answering `(0, 0)`: no rebase runs, no agent is spawned, and nothing is pushed over a branch nothing
     compared.
     - `behind > 0` (worktree diverged) → normally park (`diverged_branch`) since force-pushing could clobber the real
       PR head. **Exception — already-rebased-but-unpushed:** when the worktree is also `ahead > 0` AND already sits
       on top of base (`_already_rebased_onto_base` re-fetches base and checks `HEAD..<remote>/<base>` is empty) AND the
       stale remote head is one the orchestrator itself produced (`_pr_head_orchestrator_produced`:
       `pr.head.sha == docs_checked_sha` — the only key production code persists for an orchestrator-pushed head,
       written by `_handle_documenting`'s success exits and, under `PR_REF_IN_SUBJECT`, by a publishing pass that
       re-anchors it on the commit it hands the size gate; a commit that gate held or failed to push is on no remote,
       so it is the equality with the pull request's own head that makes the key proof here, not where it was
       written), the "behind" commits are the orchestrator's own superseded
       pre-rebase commits — there is nothing external to lose, so fall through to the `ahead > 0` push and
       force-publish instead of parking. PR heads from earlier in the lifecycle (the initial implementing push, an
       intermediate fixing push) are not currently recorded anywhere in pinned state, so the exception declines those by
       design. If either guard fails (not on base, or an unrecognized head that might carry a direct push), keep the
       `diverged_branch` park. Two RECORDS license the same force-push without either guard: this stage's own replay
       record (see the `conflict_replay_*` group), and the publication a body edit's resume recorded beside the report
       it returned (`conflict_resume_*`, `conflicts/resume_records.py`) while the issue still owes that report. Each
       names the head it replaced, the commit it produced, and the pull request; a remote still standing on that head
       and a checkout on that commit is a branch whose dropped commits are exactly the ones that rewrite replaced. So
       a developer's own rebase, cut short by a crash before its push or parked for the report it left out, is
       published without a final-docs pass having vouched for the head.
     - `ahead > 0` (recovered unpushed commits, or the already-rebased fall-through above) → dirty-tree check, then
       push the recovered work and flip to `workflow:validating` with `review_round=0`, `conflict_round += 1`. The
       push is **pinned to the tip this comparison was taken against**, read from the same `<remote>/<branch>` ref the
       fetch a step earlier put there and carried on the sync record beside the counts. "Ahead and not behind" is a
       claim about that one commit and it is the whole of what licenses the force-push: left unnamed, the gate reads
       the pull request for itself and a foreign push landing in between becomes both the head it freezes and the
       lease — so commits an interrupted tick left would be measured, published over somebody else's work, and handed
       to the reviewer as a resolved round. The already-rebased exception outranks it with the head it validated as
       orchestrator-produced, which is a stronger claim about the same fact; where NEITHER names a head the push
       refuses (`unpinnable_recovery`) rather than letting git take its own reading at push time.
       The commit the recovered push leaves the branch on is read *before* the push and **named** to the gate on
       every road, and a reading that failed parks `unreadable_head`. Naming it is what makes the push and the record
       of it one decision: the gate proves the checkout independently and the worktree is writable in between, so an
       unnamed push publishes whatever landed in that window — under a lease proved against the head the branch used
       to be on — while nothing on this road ever read it. Where the push also leaves the branch **on its base** it
       finishes a round of its own, and the same id is what that round is recorded under, in the audit event and in
       the `conflict_settled_outcome` / `conflict_settled_sha` receipt a size-gate hold leaves behind. That receipt
       goes down in the push's own durable write, so a crash between it and the tail would come back to
       `("recovered_push", "")` — a pair no later tick can prove, on a branch that is in sync by then, so the round a
       push really landed is reported as the no-op flip instead. Only what the push *owes* turns on the behind-base
       reading: still behind, it records no round and the rebase behind it owns the round. The report debt is not the
       round's, though: a recovered push that landed records the debt of the head it published either way, since the
       rebase behind a still-behind push may end the tick without a tail of its own -- and a still-behind push hands
       the gate that head as `conflict_preamble_sha`, so the debt survives a crash before its own write and a hold the
       adjudication publishes later.
     - `(0, 0)` → fall through.

     Behind the body edit's resume, and ahead of the reply wait, the recovered push, and the cap, a developer report
     a resume saved about the head the pull request carries is settled (`rebase._settles_the_saved_report`,
     through the hold of step 10) over a checkout not ahead of its remote. A report-only result whose binding a
     crash cut short is owed whatever this stage waits on next: behind the cap it would park `conflict_cap` over it,
     and behind a human's park it would wait on a reply nobody was asked for, with the base refresh frozen on its
     records. It waits for an edit, though: once the requirements move past it the reconciliation defers it for
     good, and held in front of the edit it would hold the resume whose report replaces it. That resume leaves it
     where it is until the replacement is recorded over it, so a question or an `ACK:` leaves it to the hold, which
     parks it for the requirements it no longer answers. A report the issue is parked `report_undeliverable` for is
     left to the reply that replaces it, and one whose `conflict_resume_*` record names a commit the pull request
     does not carry is left to the roads that refuse it, so neither turns a standing park into the report's.
  9. Read the **pre-rebase HEAD**, and park `unreadable_head` when nothing could. It is not bookkeeping: it is the
     head both exits of this round lease their force-push against, and the size gate reads "no head" as a caller that
     established none — pinning the push to whatever the pull request is standing on when *it* looks, which is after
     the rebase or after an agent that was out for minutes. A commit somebody else landed in that window would become
     the lease and be force-overwritten by work never proved against it. Refused here nothing is rebased and no dev
     session is resumed, so the checkout is left exactly as it was found. The body-edit resume reads the same head
     for the same reason, and refuses *before* it refreshes `user_content_hash` or marks the drift comments consumed,
     so the edit is still there for the next tick to detect.
  10. Refresh `<remote>/<base>` and run `git rebase <remote>/<base>` under `_git_hardened` (drops global / system
      config, disables hooks / fsmonitor / credential helpers / commit signing / autostash — the agent owns the
      worktree and could otherwise plant a hook to execute attacker code mid-rebase). A developer report this issue
      recorded and has not settled is settled FIRST (`resume_reports._holds_the_rewrite`, through the same hold
      `workflow:validating` takes ahead of its reviewer): a report binds to whatever the code-publication receipt
      names when it settles, so one left for after the rebase would be bound to the head the rebase left and handed
      to a reviewer as that head's account. While it cannot settle nothing is rebased; where it never can, the hold
      parks for a human under `report_undeliverable`. The cap is asked behind it (`rebase._capped`), so a counter
      that has spent every round settles what it owes before it parks.
  11. **Clean rebase succeeded**: a PROVED clean tree first — a status read that established nothing names no
      paths, exactly as a tree with nothing in it does, so only a reading that happened AND named nothing gets past
      it, and either failure parks `dirty_worktree`. Then the post-rebase HEAD, proved rather than assumed: one that
      would not resolve parks `unreadable_head` rather than reading as "already up-to-date", which would hand the
      round back with nothing having established whether the rebase left a rewritten commit the PR never received.
      If HEAD did not move (already up-to-date), skip the push and flip to `workflow:validating` (`review_round=0`,
      `conflict_round += 1`). Counting no-ops against the cap surfaces a perpetually-unmergeable-due-to-branch-
      protection PR within `MAX_CONFLICT_ROUNDS` ticks; nothing was rewritten, so it records no report debt and leaves
      a standing one as it is. If HEAD moved, force-with-lease push, record the report debt the rewritten head owes
      (see *A rewrite owes its report* below), and flip to `workflow:validating`.
  12. **Conflicted rebase**: build a conflict-resolution prompt via `_build_conflict_resolution_prompt`, resume the dev
      with it (`pause_guard=True`), then run `_post_conflict_resolution_result`.
  13. `_post_conflict_resolution_result`: `interrupted` (shutdown sweep killed the run mid-flight) → ignore the
      partial result and return WITHOUT writing pinned state, leaving durable state retryable (this is the one branch
      that does not write; it precedes all others); timeout / unfinished rebase / no commit / dirty / push fail →
      park; success → force-with-lease push, record the report debt the resolved head owes, increment
      `conflict_round`, reset `review_round=0`, flip to `workflow:validating`. Fresh-rebase pushes pin the lease to
      the pre-rebase PR head; awaiting-human resume
      pushes pin it to the head the pull request was standing on when the tick fetched it, which is read BEFORE the
      session resumes — the local `before_sha` may be an intermediate SHA on a worktree that is mid-rebase or already
      ahead of its publication, and a head left for the size gate to read after the agent returns is whatever landed
      while it was out, so the force-push would adopt a concurrent update as its own lease. On BOTH
      resume paths (fresh conflict and awaiting-human), a mid-run `paused` / `backlog` returns in the handler BEFORE
      `_post_conflict_resolution_result` runs, so the resolved commit stays on the branch and no push / relabel /
      write happens until the label is removed.
- **Output**: label moved to `workflow:validating` (any pushed resolution OR no-op rebase), OR
  `workflow:decomposing` (a content update the size gate held), OR no label change (drift
  ACK / drift report with no commit / `_on_question` park: rebase still unfinished), OR `done` / `rejected`
  (terminal), OR a HITL park.

The rebase path deliberately rewrites the PR branch to keep history linear after other issue PRs land. Every pushed
rebase resets `review_round`, so the reviewer must re-approve the rewritten head before the in_review ready-ping gate
can fire, and leaves the report debt that holds that reviewer until a report of the rewritten head settles.

### Content updates onto the pull request this stage already has

Every commit this stage publishes joins a pull request the remote already carries, so all four of its changed-head
publications pass the [size gate on a published pull
request](#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr) before anything reaches the remote —
`conflicts/publication._publish_clean_rebase` for a rebase that produced a new head,
`conflicts/outcomes._finalize_conflict_resolution` for a resolution an agent wrote (both the fresh conflict and the
awaiting-human resume behind it), `conflicts/divergence._push_recovered_commits` for commits a crashed tick never
pushed, and the body-edit resume in `conflicts/resume.py` through the shared dev-fix publication. One of the four
also hands the gate what it REPLACED, built by `conflicts/evidence`: the rebase is history this stage replayed
itself, so an adjudicated change may be recognized in the object that replaced it rather than measured past the same
ceiling twice. The other three hand in nothing, because none of them can say what the commit it is publishing is.
What the gate counts is what the pull request would **come to** — three-dot from the base the *remote* names to the
candidate — so the ceiling is cumulative and a two-line resolution onto an already-large branch is held exactly as a
large one is. Growing a branch past `MAX_ADDED_LINES` one small conflict round at a time is the outcome that
measurement exists to prevent.

- **The lease stays this stage's.** Each of the four reads a head for itself and pins its force-push to it — the
  pre-rebase head for the fresh rebase and the resolution behind it, the tip the pull request was fetched at for the
  awaiting-human resume, the tip the ahead/behind comparison was taken against for the recovered push — and the gate
  *checks* that head against the one it reads rather than substituting for it. Two readings of one fact that disagree
  are a pull request somebody moved mid-tick, and the call refuses instead of freezing a tip the branch would not be
  pushed onto. `DECOMPOSE=off` turns the measurement off and neither the naming nor the lease with it.
- **A round is counted only after a push.** `conflict_round`, the `last_conflict_resolved_at` stamp, and the
  `conflict_round` audit event all live on the pushed-round tail (`_hand_resolved_round_to_validating`), so a held
  candidate and a failed push each leave the counter alone — spending one for a push that never happened brings
  `MAX_CONFLICT_ROUNDS` forward by a round nobody ran. The single exception is the no-op flip, which counts a round
  *because* nothing was published; see below. The count is durable BEFORE the label moves (`conflicts/handoff.py`):
  the tail writes it with `conflict_handed_sha`, the head it hands on, then emits the `conflict_round` event, then
  relabels, then drops that claim in a write of its own. The event follows the write, so a count write that never
  landed has reported nothing and the tick that counts the round again behind the push's receipt emits it once; a
  process ending between the write and the event loses the event rather than duplicating it. Moved first, a write
  lost behind the relabel would leave `workflow:validating` holding the head
  with the round uncounted and the old `review_round` -- and nothing there reads a conflict receipt. Written first, a
  relabel that never landed leaves the claim on `workflow:resolving_conflict`, and the next tick, finding the branch
  in sync and standing on that head, makes the move ahead of every receipt, resume, and rebase without counting
  again; a claim about any other head is dropped, and a head nothing could prove holds the tick with the claim kept
  — read as no claim, the branch would be resolved again, counting the round a second time through the no-op flip or
  parking it at the `MAX_CONFLICT_ROUNDS` that round reached. A drop lost behind a landed relabel leaves the claim on
  `workflow:validating`, whose handler retires it in a write of its own before anything else: the move has been made
  by then. Left standing, it would outlive the review, the approval, and the docs pass, and the next conflict episode
  over that same head would read it as the move still owed and hand the head back to review with nothing rebased.
  The base refresh that routes an issue into a new episode drops it in the same write, for an issue it routes there
  before `workflow:validating` ever ran.
- **A rewrite owes its report.** A clean rebase, a resolution the dev finished one with, and a recovered push each
  leave the pull request on a head no developer report is about -- the conflict prompt asks for none, and nothing on
  the recovery road can say whether the commits it finds ever had one -- so each records
  `developer_report_rewrite_debt` (`conflicts/report_debt.py`) before the hand to `workflow:validating`, whose report
  hold then asks the developer for a fresh report of that head with no human reply. What names the rewrite is the
  code-publication receipt the size gate's write left, and nothing the caller read for itself:
  `implementing_published_sha` has to be the round's head, `implementing_published_pr` the pinned pull request, and
  `implementing_published_lease` -- the head the push was leased against -- becomes `previous_head`. A receipt short of
  any of those proves no rewrite of this stage's and records none, so the reviewer road holds the report it finds to
  the head as it would with no claim. A standing claim goes through `report_rewrite_debt.records_rewrite`: a rewrite of
  the head it names retargets it, so repeated rounds leave one debt naming the latest head, and a claim about a head
  somebody else pushed, or one nobody can read, is left as it stands.
  The debt goes down in a write of its own **ahead of the relabel**, since the label is what hands the head on, and a
  round whose push landed and whose tail a crash cut short -- before that write or before the relabel -- comes back
  through `_finished_settled_round`, which reads the same receipt the push's own write left beside the settled round;
  a debt already naming the head is left unwritten. A crash after the push and before that write of the gate's leaves
  the approval the gate took ahead of the push -- the commit, the head it was leased against, and the route's spends
  in `late_spends` -- and the reconciliation ahead of the next handler republishes that same commit under a lease,
  writing the receipt against the original head with the spends beside it, so the stage behind it records the debt
  the same way. An adjudication's accepted push cut short the same way is finished by the settlement's own retry,
  which finds the pull request already on the accepted commit and writes the receipt that push never got to, against
  the head the verdict was measured over. A proved debt the pinned comment has no room for is neither of the
  refusals above: it parks `unrecorded_report_debt` with nothing counted or relabelled, and every later tick tries
  the write again -- through the settled round, or the preamble head, the push's own write left -- before anything
  else runs, handing the round on once it fits. A recovered push that lands still *behind* base records its debt
  at once rather than at a tail, since the rebase behind it may end the tick without one -- a no-op flip, a conflict
  the dev cannot finish, a failed push -- and a rebase that does move the head retargets it. That push finishes no
  round, so no settled receipt brings a later tick back for it; what does is `conflict_preamble_sha`, the head it
  hands the gate as its spend, written in the gate's write that carries the receipt on landing and in the one a
  hold makes ahead of its relabel. `_finished_settled_round` reads it first, ahead of every resume and rebase: once
  the receipt names that head it is dropped, and the debt is recorded where the pull request was just fetched
  standing on it -- after a crash before the debt's own write, or once an adjudication has published the held push.
  A pull request somebody has moved off it owes that head nothing. The no-op flip, a held candidate, and a push that
  failed record nothing, since no head of this stage's reached the pull request; a held one's debt is recorded by
  the settled round, or the preamble head, the tick after its publication reads. A body edit's round
  (`drift_resolved`) records none either: its commit is the developer's own answer to the edit, not a rewrite of the
  head, and the report describing it is the one its resume returned (below).
- **A body edit's report reaches the pull request with it.** The body-edit resume names what it was `handed` —
  `workflow:resolving_conflict` as the route and the requirements revision its frozen record fingerprints — so the
  shared drift disposition holds it to the report contract the review stages' drift resumes are held to
  (`conflicts/resume_reports.py`). A rebase the session ran itself, a change the edit asked for, or both: the report
  it returned is recorded as `developer_report_delivery` before the size gate reads the candidate, and once the push
  lands the round is counted and relabelled through the shared tail, and only then is the report bound to the head
  the code-publication receipt names and settled through the
  [reconciliation](#the-developer-report-transaction-every-dispatch). So the reviewer `workflow:validating` spawns
  next is handed that report, settled for the rewritten head: no `report_undeliverable` park over a report about the
  head the rebase replaced, no human reply, and no developer run to write the report again. A run that commits
  nothing and reports is `"reported"` — the report goes onto the head the pull request already carries, which a
  rebase already published, nothing is pushed, no round is spent, and the issue stays here as on an `ACK:` until
  the next tick's no-op flip or rebase hands it on. A finished run that committed with no usable report, a report no
  record can carry, and a commit an incomplete run left all publish nothing and park under `report_undeliverable`,
  as on the review stages. The reply that answers such a park — or a `push_failed` park behind a recorded report —
  is the rest of the same road rather than a conflict resolution: `_resume_awaiting_human` asks whether the issue
  owes a report before the run, and where it does the reply's run goes through the same disposition and publishes
  the commit the first run left under the report the reply wrote -- unless the run left the rebase mid-flight, which
  parks `rebase_in_progress` as the resolution funnel does, recording no report and pushing nothing, as the body
  edit's own resume does too. A timeout reads ahead of that, as in the funnel: the run parks `agent_timeout`, which
  `/orchestrator continue` retries rather than refusing. The reply's publication is leased against the head the
  pull request stood on before the run, which the divergence guard ahead of the resume admitted, so a rebase past
  that head goes out even where the reply commits nothing more: the shared stranded-commit proof reads such a
  branch as a remote that moved, so a lease its caller names is never asked of that proof
  (`validating/dev_fix._replaced_head`). The body edit's resume names the head it began at the same way. A pull
  request somebody pushes to while either run is out is therefore refused by the size gate rather than adopted as
  the head the push replaces, even where the candidate still descends from it. A run that commits
  nothing and reports — the body edit's or a reply's — writes the head the pull request carries as both ends of the
  `conflict_resume_*` record in the write that saves its report, over the record of an earlier candidate. The
  record holds whatever report is unbound to its head, and nothing retires it while one is — not the settlement of
  an older transaction beside a newer report of the same head — so a crash before its binding leaves the
  report to settle on that head, and a checkout that gains a commit meanwhile parks `report_undeliverable` as any
  head the record does not name does, with nothing pushed or bound, for the reply that reports the branch as it
  stands. A crash after the binding and before the post leaves a transaction held to the head it was bound to, and
  a recovered push of a commit gained since would leave it a head it can never settle on, so that push waits for
  the transaction to settle through the review hold's settling half, which parks `report_undeliverable` where the
  checkout has moved off that head. A run that reports over a head nothing could read records nothing at all: no
  record could hold that report to a commit, so the issue parks `report_undeliverable` with the run's work marked
  undescribed, the recovered push refuses to carry out whatever the checkout holds by the next tick, and the reply's
  report is the one published. A report written with a tool step still running is no finished run either: it parks
  `agent_execution_failed`, as the question road parks such a run that reports nothing, and nothing is recorded,
  pushed, or published, over the head the run began on or a commit it left. An `ACK:` saves no report and leaves the
  record, and the earlier report parked. The reply's run is
  resumed on the frozen drift prompt, as the edit's own resume was: the issue and its conversation -- the reply among
  it, and a body changed while the branch was ahead -- quoted off one read whose record stamps the report and is
  settled once the run is back, so no later drift check reads the reply or that body as an edit nobody answered.
  That read keeps every reply past the watermark whole, the excerpt bounding only the context ahead of them, and the
  replies are marked read by its settlement rather than ahead of the read: a reply the bound cut would otherwise be
  marked read without ever reaching the developer. A
  rotated or poisoned session's fresh spawn is re-grounded on that same frozen text, so the stamp is what the run was
  given however it was launched. A bare `/orchestrator continue` that retries such a run's session failure — a
  timeout behind the reply, the report still owed — keeps the retry it is on every other park: the commands it
  consumes come out of that one read by id, out of the conversation it quotes, its record, and the re-grounding text
  alike, and `_CONTINUE_RETRY_PROMPT` leads the drift prompt in their place, so the developer is never handed the
  command as the last thing a human said. The bare command never moved the requirements fingerprint, so the stamp is
  the same with it gone. This orchestrator's own notices are no reply: a bounded park cannot carry the
  watermark over a human comment that landed ahead of it, so its notice can stand above the watermark, and the
  reply road drops it by the id ledger rather than resuming a developer nobody asked for. The resolution funnel reads no
  report, so taken down it the commit would go out undescribed and the report would be parked as a question. A reply
  that only acknowledges the edit answers the park without writing the report, so the debt stands with the flags
  down: the recovered push then refuses the commit it would carry out undescribed and parks `report_undeliverable`
  again, so nothing reaches the pull request, and no round is counted, until a usable report exists.
  A park that owes no report — a question, a timeout —
  keeps the resolution road and writes no `requirements_drift_open`, since nothing on this stage reads that claim.
  The crash windows between the record and the settlement are recovered as follows. Past the record and before the
  push, the commit is ahead of the remote or, rebased, diverged from it, and the recorded report is durable beside
  the settled baseline and the `conflict_resume_*` publication: the next tick's recovered push publishes it -- over
  a divergence, under the lease that record licenses, and never a head other than the commit it names: a checkout
  that moved on, or was put back on the head the push would have replaced, parks `report_undeliverable` with nothing
  pushed or bound and the record kept, for the reply that reports the branch as it stands -- and records the
  rewrite's report debt under the
  `recovered_push` outcome, and `workflow:validating`'s report hold binds the saved report to that head and settles
  it, which pays the debt, before any reviewer runs. Where the base moved again in the meantime the recovered push
  lands still behind it, and the rebase behind that push waits for the saved report to settle about the recovered
  commit (step 10): the head the rebase or the resolution behind it leaves is then owed a fresh report, which
  `workflow:validating` asks the developer for with nobody involved. Past the count and before the binding, the issue
  is on `workflow:validating` with the report recorded and unbound, and the per-tick base refresh runs ahead of the
  hold that binds it: the refresh leaves the branch where it is while `developer_report_delivery` or
  `developer_report_pending` stands, so the hold binds the report to the head it describes, and the refresh rebases
  on a later tick, leaving that head's own debt for `workflow:validating` to refresh. Where the relabel itself was
  lost, the round is counted and the issue is still here with the report unbound: the counting tail leaves the
  `conflict_resume_*` record standing while that report is unbound, so a commit the checkout gains meanwhile is
  refused as any head the record does not name is — `report_undeliverable`, nothing pushed, bound, or counted
  again — rather than recovered and handed the report. Past the push, the gate's own
  write left the
  `drift_resolved`
  settled round: the next tick finishes it through `_finished_settled_round`, and the hold, or the transaction's own
  reconciliation where the binding had landed, settles the report off its receipt. Past the count, see *A round is
  counted only after a push* above. In none of these does a later tick post the report twice, launch another
  developer, charge another run, or count the round again; a window the gate's own pre-push approval covers is the
  publication reconciliation's, ahead of the handler.
- **A hold ends the tick here.** The commit stays on the branch, the issue is on `workflow:decomposing`, and neither
  the hand back to `workflow:validating` nor the rebase behind a held recovered push is this tick's to make. What the
  round would have been is written inside the gate's own durable write, ahead of the relabel, as
  `conflict_settled_outcome` / `conflict_settled_sha` — `base_rebased_clean`, `agent_resolved`, `recovered_push`, or
  `drift_resolved`, with the head it produced. The resumed tick cannot re-derive either: an authorized settlement
  publishes the accepted commit, so the branch the label comes back to already carries its base, which is the no-op
  flip's own reading. A recovered push that leaves the branch still *behind* base records no round — it is the
  preamble to a rebase that owns the round and leaves its own receipt — only the head it would publish, as
  `conflict_preamble_sha`, for the report debt that head is owed once the adjudication publishes it.
- **One receipt slot, so one outstanding round.** `conflict_settled_outcome` / `conflict_settled_sha` is a single
  pair, and every content update that can be held writes into it — so a tick that starts a *new* resume while a
  receipt is still standing would record its own outcome over the round a settlement already published, and the
  earlier one would never be counted. Ordering is what keeps them apart, all of it inside
  `_reconciled_before_the_rebase`: `_finished_settled_round` is asked before either dev resume, and a checkout that is
  *ahead* of its remote — the one shape where the receipt cannot be paid on the spot — defers both resumes to the
  recovered push below, which pays it. Either way the edit or the reply is left unconsumed for a tick that can act on
  it. Nothing is lost by waiting: a standing receipt says this stage's last resolution is already on the pull request,
  so there is no in-flight resolution for the dev to reconsider. A receipt that cannot name both ends is no receipt —
  `_settled_round_owed` declines it, and the ordinary road clears it by reaching a tail of its own.
- **The cap guards the rebase, and nothing above it.** `MAX_CONFLICT_ROUNDS` refuses another *attempt* — the rebase and
  the dev run behind it — so it is asked once the reconciliation is done, inside `_rebase_and_dispose` behind the
  settlement of a saved report and immediately in front of the rebase. Everything the reconciliation does is work
  already done that this stage still owes an effect for, and refusing those does not end the loop, it strands them:
  nothing else pays a receipt, publishes a commit an earlier tick made, settles a saved report, or answers a person. A
  body edit on a spent counter is still resolved, so a hold there records a receipt at the ceiling; and where that
  receipt sits on an *ahead* branch, the recovered push is the only road that pays it. Counting it takes
  `conflict_round` one past the ceiling, which is correct: the round was spent on a push that really landed, and the cap
  fires on the next attempt. Whichever tail finally pays a round also clears the park it ran under, so
  `workflow:validating` is never handed an issue that reads as waiting on somebody.
- **A tree nobody read is not a clean one.** A `git status` that established nothing names no paths, and so does a
  tree with nothing in it — so every probe reporting the paths alone answers the same for both, and taken as clean a
  checkout carrying uncommitted edits is published as a commit that silently omits them. The size gate proves the
  tree for itself, but only as part of freezing an entry, which an install running `DECOMPOSE=off` never does: there
  the push goes out and a proof taken afterwards can park without taking the remote update back. So this stage takes
  the reading itself, ahead of the effect, on both roads that end in a publication from the checkout — the recovered
  push requires a *provably clean* tree, and either dev resume requires one that at least **read**. A merely dirty
  tree is not this: that is the park a reply exists to unstick, and the dev is resumed over it to clean it up.
- **A park is not always a person.** The refusals this stage takes over a reading that *did not happen* —
  `fetch_failed`, `unreadable_divergence`, `unreadable_head`, `unreadable_worktree`, `unpinnable_recovery` — and over
  a write that did not, `unrecorded_report_debt`, name nothing a reply could answer: what clears them is the same
  reading or write taken again. Their reason is recorded durably
  (`park_reason`, re-set after `_park_awaiting_human` clears it) and a tick that finds one standing carries on with
  its ordinary work rather than consuming itself as an awaiting-human resume — which is what would otherwise leave a
  repaired checkout parked for good, with the thing the notice asked for already done. Because those retries run every
  poll, each is announced **once** — both fetches included, the base ref's as much as the pull request branch's — and
  "once" means once per *reason*: an issue already parked for an agent question that then becomes externally diverged
  is told about the divergence, since that is new and it is what now blocks the reply it was waiting to give.
  Diverged is not transient, though, and a transient refusal taken over a park somebody **owes an answer to** records
  nothing at all: the standing reason is what the next tick reads, so a fetch that failed for one poll while an
  agent's question waited would otherwise hand the tick behind it a branch that reads as nobody waiting, and it would
  rebase, push, count the round, and hand `workflow:validating` work the human was asked about — with the reply
  swallowed too, since re-parking ratchets the consumed-comment watermark past everything on the thread.
  `_park_conflict` and the awaiting-human resume ask one predicate for "is this park a person's", so the two
  cannot drift apart.
- **What it refuses is a handoff, not a round.** The settlement is asked over a branch **in sync** with its remote and
  standing on the head the receipt names. Behind the remote it declines and the divergence guard behind it parks
  `diverged_branch` — and there the round is not what fails. A remote standing on a *descendant* of the settled commit
  still carries it, so the round did land; what cannot be handed on is this **checkout**. The tail hands
  `workflow:validating` the worktree as it stands, and `_ensure_worktree` behind the reviewer *reuses* a checkout
  rather than fast-forwarding it to the tip — so waving it through counts the round correctly and then shows a human
  a verdict taken over the commit the pull request has already moved past. The receipt keeps standing instead, the
  park asks for the branch to be reconciled, and the same reading settles the round on the tick after that. Ahead of
  the remote it declines too, and there the recovered-commit push carries the commit back through the gate.
- **`single` and `split` settle through the shared protocols, and they do not settle alike.** Nothing about the
  adjudication is this stage's: the hold, the verdict, and what each earns belong to `workflow:decomposing`. A
  **`single`** parks there for a human's decision, and an authorized settlement publishes the accepted
  commit and settles at the stage the record names, which puts
  `workflow:resolving_conflict` back — and `_finished_settled_round` is the whole of what this stage then does with
  the answer. Asked before the rebase, over a branch in sync with its remote AND standing on the head the receipt
  names, it runs the tail its own tick never reached and drops the receipt. Ahead of the remote the receipt stands
  and the recovered-commit push carries the commit back through the gate, which is the one road that measures it
  again. A **`split`** never comes back here: it snapshots the candidate on an immutable ref, supersedes and closes
  the pull request the conflict round was being fought over, and retires the generation in the write that hands the
  parent to `workflow:umbrella` with its children released — so the receipt is left standing on an issue this stage
  will not run again, and the round it names is one no `conflict_round` ever counts.
- **A reading nobody could take parks, and the retry costs no agent.** A failed count leaves the pair frozen with its
  publication group and no number on it; the reconciliation ahead of the next handler
  (`implementing/late_reconcile._reconciles_published_work`) re-measures *that recorded pair* — asked for by id, not
  re-derived from a branch the base refresh has moved under — and publishes, routes, or parks it without rebasing and
  without resuming the developer who already finished. A publication that MOVED under a live record (somebody pushed
  to the pull request, or the issue was repointed at another one) is refused with the record left exactly as it
  stands, since re-entering it would stamp this tick's reading over the evidence the count was actually taken on.
- **Neither no-publish exit enters the gate.** A rebase that left HEAD where it found it has nothing to push, so
  nothing is read, frozen, or counted — and it still bumps `conflict_round`, which is what surfaces a pull request
  blocked by branch protection rather than by content within `MAX_CONFLICT_ROUNDS` ticks. A body edit the dev answers
  with `ACK:` and no commit is the same: no measurement, no round, and no park.
