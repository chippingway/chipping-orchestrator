# Conversation stage handlers

`question` and `discussion` are the two operator-applied labels: nothing routes an issue into either, neither is in
`_FAMILY_AWARE_LABELS`, and both run the decomposer's backend under a pin of their own. This page is what each
handler does with a round — the park reason every outcome writes, the probes a round's branch is read by, the plan PR
a confirmed design earns, and how a tick that died mid-publication recovers.

What each prompt grants and forbids, and how a session is continued across rounds, are in
[`../workflow/conversations.md`](../workflow/conversations.md). The delivery stages are in
[`delivery-stages.md`](delivery-stages.md), the labels and pinned-state keys in
[`labels-and-state.md`](labels-and-state.md), and the compact lifecycle reference in
[`lifecycle.md`](lifecycle.md).

## `_handle_question` (label `question`)
- **Trigger**: each tick while the label is `question`. Also runs on closed-`question` issues — that's the terminal
  signal the handler consumes.
- **Input**: issue + comments + pinned state (`question_agent` / `question_session_id`, awaiting-human keys). The label
  is operator-applied — no other handler routes into `question` automatically, and `question` is deliberately NOT in
  `_FAMILY_AWARE_LABELS` so fan-out concurrency is preserved.
- **Internal flow**:
  1. **Terminal close.** If the issue is closed, stamp `question_closed_at`, set label `done`, write pinned state, tear
     down the per-issue worktree + local branch via `_cleanup_question_worktree`. Do NOT spawn the agent.
  2. **Awaiting-human resume.** If `awaiting_human`, scan for new comments past `last_action_comment_id`. No new
     comments → return (the `_question_run_cleanup` context manager still tears down any worktree from a prior safe
     tick). New comments → advance the watermark BEFORE spawning, then resume the locked session via
     `_build_question_followup_prompt`.
  3. **Fresh spawn.** Ensure the per-issue worktree, resolve the question spec via `_read_question_session` (falls back
     to the decomposer's spec on the first-ever spawn), persist `question_agent` BEFORE invoking `run_agent`, build the
     read-only `_build_question_prompt`, spawn, and persist `question_session_id`. A mid-run `paused` / `backlog`
     re-check (`_paused_during_agent_run`) right after the run returns short-circuits the resume and fresh spawn alike
     BEFORE the usage fold, park, or pinned-state write, so the next tick re-runs from durable state (the
     `_question_run_cleanup` context manager still disposes the worktree per `keep_worktree`).
  4. Branch on result:
     - a launch that never became a process (`invoked=False` — the agent-run circuit refused it) → return WITHOUT
       writing, ahead of the pause re-check and every reading below it. Nothing in the worktree is that launch's
       doing, and a park in its name would overwrite the durable one the refusal took.
     - `timed_out` → `_park_question` with `question_timeout`. **Keep** the worktree for operator inspection.
     - new commits → `_park_question` with `question_commits`. **Keep** the worktree: this stage is read-only.
     - dirty tree → `_park_question` with `question_dirty`. **Keep** the worktree.
     - empty `last_message` → `_park_question` with `question_silent` (worktree torn down).
     - clean answer → post the agent's quoted message to the issue (pinging `HITL_MENTIONS`), park with
       `question_answer`, tear the worktree down.

  The `_question_run_cleanup` context manager runs `_cleanup_question_worktree` unless one of the three unsafe-park
  branches set `keep_worktree=True`.
- **Cross-stage interaction (relabel to `workflow:implementing`).**
  [`_handle_implementing`](delivery-stages.md#_handle_implementing-label-workflowimplementing) carries an
  explicit guard:
  when it inherits `awaiting_human=True` + a `park_reason` starting with `question_`, it inspects the worktree AND the
  local branch. A clean worktree + clean branch drops the question-stage park flags, ratchets `last_action_comment_id`
  past the question agent's answer, and falls through to fresh dev-spawn. A dirty worktree OR a branch with commits
  beyond `<remote>/<base>` re-parks with `question_unsafe_relabel`.
- **Output**: an issue comment with the answer / follow-up question + a HITL park, OR a terminal flip to `done` on a
  manual close, OR a no-op tick. Every park goes out through `_park_question`, which forwards a bounded correlation
  payload to the emitted `park_awaiting_human` record and its analytics row: the road the tick came off
  (`question_round` for the conversation's own round, `question_resume` for a reply answering an earlier park, read
  at the top of the tick before the resume clears `awaiting_human`), `agent_role="question"`, the pinned
  `question_session_id`, and any `pr_number` the issue arrived carrying. Unheld fields are dropped rather than
  written as nulls, and nothing in the payload comes from the agent's answer — see
  [event streams](../observability/event-streams.md).

The locked session resumes across every teardown because session state lives in pinned state, not in the worktree, so
the per-issue checkout only has to survive a tick when an unsafe park keeps it for inspection.

## `_handle_discussion` (label `discussion`)
- **Trigger**: each tick while the label is `discussion`. Like `question` the label is operator-applied — no handler
  routes into it, there is no pickup route to it, and it is deliberately NOT in `_FAMILY_AWARE_LABELS`, so fan-out
  concurrency is preserved.
- **Input**: pinned `awaiting_human` + `park_reason`, the consumed `last_action_comment_id` watermark, the
  `orchestrator_comment_ids` list the stage's own comments are recognized by, and the trust-filtered issue thread —
  quoted whole by the full prompt, and from the watermark forward by a resume.
- **Plan-PR terminal**: a recorded `discussion_plan_path` **and** `pr_number` end the tick before anything else — no
  round, no agent — and what that pull request has become is polled first, ahead of every local reading. Both halves
  are read because either alone means something else: an issue relabeled here from a PR stage arrives carrying its
  dev's `pr_number`, and a plan path without a PR is a record no publication ever wrote (they land in one durable
  write). A MERGED plan PR is the humans taking the design and finalizes to `done`; one CLOSED without merging is
  them turning it down and finalizes to `rejected`. Both take the terminal tail every other stage takes, in that
  order: the `merged_at` / `closed_without_merge_at` stamp, the label, the cumulative usage receipt posted BEFORE the
  single pinned write so its comment id rides the same state, the `pr_merged` (`merge_method="external"`) /
  `pr_closed_without_merge` event with `stage="discussion"`, the issue close, and only then
  `_cleanup_terminal_branch` — the worktree plus the local and remote branches. Teardown last is the contract: an
  operator who finds a leftover checkout still has an issue that says what happened to it.
  An OPEN plan PR is neither, and is a strict no-op — no comment, no write, no label — that KEEPS the worktree and
  both branches, since they are what that pull request is open against. That holds whether or not the ISSUE is still
  open: a human closing the issue out from under an open plan PR has said nothing about the design, so the stage
  keeps the `discussion` label (which is what leaves the issue inside the closed-issue sweep) and its checkout until
  the PR itself resolves. A `gh.get_pr` failure is that same hold, since every ending below it is a claim about a
  pull request nobody could read; the tick after this one asks again.
- **Pre-PR close**: a closed issue with no recorded plan PR is finalized to `rejected` — the
  `closed_without_merge_at` stamp, the label, the receipt, one write — ahead of the publication recovery and every
  turn-taking gate below it, since a human stop signal outranks whatever the stage was about to do. No event, because
  there is no pull request for one to name, and no teardown: the branch may be carrying an unpublished plan commit,
  or belong to a PR the issue merely arrived here holding, and neither is something a closed issue alone justifies
  deleting. The `rejected` flip is what takes the issue back out of the closed-issue sweep.
  **A standing `discussion_publishing_sha` is read first, though, and it is what makes "no recorded plan PR"
  different from "no plan PR".** The publication opens its pull request before it writes the number down, so a tick
  that died in that window leaves a real one with nothing pinned pointing at it — and the humans can decide the issue,
  or that pull request, inside the same window. So the marker's commit is looked up across every state
  (`find_pr_for_commit`, the same lookup the publication's own recovery uses) and what comes back decides: a MERGED or
  CLOSED one is finalized here exactly as a recorded one is, with `pr_number` and `branch` written first because the
  event names one and the cleanup resolves the branch from the other. That branch is resolved ONCE, before either is
  set, and the same value serves the lookup and the reap: `_resolve_branch_name` falls back to the pre-namespace
  `orchestrator/issue-N` whenever it finds a `pr_number` with no `branch` beside it, so a branch worked out after the
  recovered number was written would name a ref this stage never pushed and leave the real local and remote branches
  standing. An OPEN one holds the tick exactly as a recorded
  open one does, label and checkout intact; and a lookup GitHub declined decides nothing and is asked again next tick.
  Only "no pull request carries that commit" — a push that never landed, or a tick that died before it — reaches the
  pre-PR ending above. Taken for a discussion that never published, an open one would be flipped out of the sweep with
  its branch and worktree left for nothing to reap, while its plan sat on a pull request nobody would come back to.
- **Interrupted-publication resume**: a `discussion_publishing_sha` naming the tip the checkout is on now, on any park
  other than `discussion_push_failed`, finishes that publication before the turn-taking below runs — no agent, no
  round. It has to run there rather than behind a reply, because the marker's own write persists whatever the round
  staged, the consumed watermark included: an issue whose publication died after that point has nothing unread, so
  waiting for a reply would mean waiting for a human to answer the same round twice. The failed push is the one
  exception, since retrying it every tick would push at a remote already refusing us and comment each time; its
  retry is the reply to its park. A retry already under way is not that state: the write that begins one replaces the
  reason with `discussion_publishing`, in the same write that spends the reply, so a crash inside the retry resumes
  here like any other unfinished publication instead of waiting for a human to say the same thing twice. Every ending
  of the attempt writes its own reason over that one, so it is durable only inside that window.
  While the marker stands it answers for the branch outright: a tip that is neither
  the commit it names nor the round's own anchor parks `discussion_stale_publication` — written once, since its own
  reason is what the repeat reads — rather than falling through to a reading that would publish a second plan-shaped
  commit nobody checked. A tip back AT the anchor is the operator taking the remedy — but only once the REMOTE agrees
  nothing went out: the push sends the SHA it validated rather than `HEAD`, so a plan committed on a detached head
  reaches the remote while the local ref never moves, and a checkout restored later comes back on that ref instead of
  the head just fetched. So the branch is asked for, and the marker is spent only when the remote has no such branch
  or the branch it has does not carry the commit the marker names (asked by containment, since a human amending their
  own plan on its PR moves that tip past it — and asked of an object, so the branch is fetched unless that tip is
  already here, because git refuses an id this clone has never seen and the refusal reads exactly like a branch that
  dropped the commit). A remote that could not be read, or a tip nothing could bring here, establishes nothing and
  keeps the record. Otherwise the pull request carrying the commit is asked for once more — a merge or an amended-open
  head is already settled above, so what is left to find is one the humans CLOSED, which the reset above could also
  have explained and which this reading has now ruled out. Finding it records the number and lets `plan_terminal` finish
  the issue `rejected` on the next tick; finding none writes the same `discussion_stale_publication` park, saying
  that the plan is out
  there and that dropping it means closing its pull request rather than resetting a branch here. A new round retires
  the marker for the same reason the reset does, since a round only opens on a tree the publication's commit has
  already been reset off.
- **Gate**: `awaiting_human` short-circuits the tick's *opening* round **only when `park_reason` carries the
  `discussion_` prefix**. That park is the round already on the thread, which the humans are answering, so nothing new
  is opened over the top of it; what the tick looks for instead is their answer. Issue comments past
  `last_action_comment_id` that survive both `filter_trusted` and the orchestrator's-own-comment drop are what makes
  it this stage's turn again — an empty batch, or one entirely from authors `ALLOWED_ISSUE_AUTHORS` excludes, spawns
  nothing, comments nothing, and writes nothing, leaving the reply (if any) unconsumed for the tick after the
  allowlist changes. A park any *other*
  stage wrote does not gate at all: pinned state outlives a relabel, so an issue an operator moves here while it is
  parked elsewhere is awaiting a reply nobody will send it here, and reading `awaiting_human` alone would leave it
  inert for good.
- **Resume hold**: a parked issue WITH a reply asks the two preflight questions below before opening its round, and a
  yes to either stops the round — opening one anyway would rewrite `discussion_round_sha` with the moved tip
  (spending the reset target the earlier park quoted and the implementing relabel guard re-measures against) or have
  `_ensure_worktree` force-remove the dirty tree the operator was parked to inspect. Ahead of both, and ahead of every
  local reading, `discussion_publishing_sha` is settled. This is the only path that resumes a failed push — the
  interrupted-publication resume above steps around that park deliberately — and "the push failed" is a claim about
  the request, not about the remote: the branch may well be published. On a host that has since lost the checkout AND
  the local ref, every local probe then reads as though nothing ever happened: no tree, no branch, and an anchor
  nothing has moved off. Gated on the moved tip, such an issue opens another round instead, and the round's own
  pre-spawn write retires the marker with it — leaving the plan pushed with no PR, no record, and nothing left that
  knows to look for it. What the marker answers is the branch itself: finished when it names the tip the checkout is
  on now (restored from `<remote>/<branch>` when the directory is gone), spent when the branch is back at the round's
  anchor AND the remote no longer carries the commit it names, and parked `discussion_stale_publication` for any other
  tip rather than that tip being read as the round's own work. Before that refusal, the same pair of questions the
  live publication asks is asked of the COMMIT THE MARKER NAMES rather than of the tip on disk — merged anywhere, or
  open on a head that descends from it — because a checkout rebuilt from the remote after the host lost it comes back
  on the reviewer's own head, which is neither the marker's commit nor the anchor. Asked of that tip instead, the
  ancestry question becomes whether their head descends from itself, and a plan the humans are reading on an open pull
  request is refused for good with no `pr_number` and no plan path ever written.
  A moved tip with no marker standing is the question after it, and
  `discussion_round_open` is what says a round of this stage was still in flight when that commit appeared —
  the resumed-round case. It is read on EVERY moved tip, not only under this stage's own parks: "no discussion park"
  is not "no park at all", and an issue relabeled out to `question` and back arrives awaiting a human under that
  stage's park, still carrying this stage's anchor and session id from a conversation that finished. Read as a round
  of this stage that never reported, a commit the question agent made on the plan path would go onto a plan PR under
  a session that never saw it, so a tip that moved with no round in flight parks `discussion_commits` naming the
  anchor to reset to. The reply that drove a retry is
  consumed by the push it asks for, or a failed one would be asked
  for again by the same comment on every poll. The marker is also how a
  tick that died between `open_pr` and the pinned write stops telling the operator to reset away the commit its PR is
  already open against. A tip neither record accounts for is not published however plan-shaped it looks — the park
  means this stage's round is over, so what appeared on the branch afterwards was put there by something else, and a
  human's next reply (a rejection, even) must not turn it into a published design. Otherwise, whether the hold is
  *reported*
  depends on what the standing park already said: a `discussion_commits` / `discussion_dirty` / `discussion_stranded`
  / `discussion_unreadable_worktree` / `discussion_plan_invalid` / `discussion_push_failed`
  park (`_repair_already_requested`) has already named the paths and quoted the reset command, so the reply is held
  silently rather than earning a second copy of those instructions. Any other park — a round that ended cleanly and
  had its tree dirtied or committed to afterwards — earns one `_park_blocked_resume` comment carrying the paths and
  the reset target, recorded under `discussion_dirty` or `discussion_commits` by which probe fired. A `git status`
  that could not run at all is the third of those and records `discussion_unreadable_worktree` with no reset target
  quoted: the read that would have named one is the thing that failed, so what the comment asks for is an inspection.
  That reason is
  itself a repair request, so the report is written once and every reply after it is held silently. No path here
  consumes the reply, so once the operator resets, the answer they already wrote is picked up on the next tick with
  no further action from them.
- **Preflight** (two halves, both WITHOUT spawning). First, a `discussion_round_sha` on an unparked issue means a
  round opened and never reached a disposition; if the checkout's HEAD has moved off it — or, when the directory is
  gone, the tip of the recorded `discussion_round_branch` has, which is asked instead of whether the branch is ahead
  of base so an issue relabeled here from a PR stage is not convicted of its dev's commits — that round committed, and
  the tick settles that commit now rather than letting the next round adopt it as its own baseline. Settling it means
  the same publication check the disposition runs: a valid plan is published exactly as the ended round would have
  published it (restoring the checkout first when only the directory is gone), and anything else parks
  `discussion_plan_invalid` naming what the branch carries. A
  matching HEAD just means the withheld round left nothing, and the tick replays it as the pause promised. Second,
  uncommitted changes already in the `issue-N` checkout park `discussion_stranded`: every park this stage writes
  suppresses the next tick, so a dirty tree at the top of a tick
  came either from a round that died before it could park on what it wrote or from the stage the issue was relabeled
  out of — and `_ensure_worktree` force-removes a dirty checkout that carries no commits, which would destroy it. The
  park names the paths and leaves the tree untouched for the operator to inspect and reset. That read is the STATUS
  form (`_worktree_status`), not the path list: the list form maps its own failure to "no paths", which is exactly
  what a clean tree reports, so a `git status` that could not run — a corrupt index, a half-removed directory — would
  be recreated over before anyone saw why it failed. An unreadable tree therefore parks
  `discussion_unreadable_worktree` on the same terms, and the post-round write checks are entitled to their
  assumption that this preflight proved the tree empty. It is asked FIRST of the two halves, and a `HEAD` that will
  not resolve is the same answer: `rev-parse` reports failure as the empty string, empty compares unequal to every
  anchor, so the commit question asked on it answers "a round of ours committed here" — and what follows that answer
  is a publication of whatever the branch arrived carrying, under a session that wrote nothing. The anchor is
  therefore compared only on a checkout that could be read, and a read that failed parks rather than being read
  either way.
- **Action**: spawn one agent per tick (`agent_role="decomposer"`, `stage="discussion"`) — the configured
  `DECOMPOSE_AGENT` on the conversation's first round, and on every round after it whatever `discussion_agent` pinned
  then, resuming `discussion_session_id` when there is one — in the
  per-issue `issue-N` worktree on the issue's own branch. A resumed round reuses that checkout as it stands — the tree
  the operator was reading while they composed the reply, already established clean and on the anchor by the hold
  above — and only a directory that has gone is restored at all. Restoring it (for an opening round, or a resumed one
  whose directory vanished) goes through `_ensure_pr_worktree` from the PR head if the issue carries a `pr_number` and
  `_ensure_worktree` from the base branch if it does not, since an issue relabeled here from a PR stage is discussed
  on the branch its PR is open against and a base-branch rebuild would hide the PR's commits from the round and from
  the anchor it writes next. A standing `discussion_publishing_sha` counts as the same thing before there is a
  `pr_number` to read: the marker is written before the push and the number only after the PR is open, so a crash in
  that window leaves a pushed branch and an open PR that nothing pinned names. Lose the worktree and the local ref
  too — a restart, an operator's cleanup, a fresh clone — and a base rebuild would refuse the publication for a tip
  it cannot find and open another round over the top of the PR. So that window asks the remote: a branch that is
  there is restored from, and "no such branch" (the push never landed) falls back to base, spends the marker, and
  lets the conversation carry on.
- **Prompt**: the opening round — and any later one with no `discussion_session_id` to resume — is given
  `_build_discussion_prompt` over the issue body, title, and trust-filtered thread; a round WITH a session id to
  resume is given `_build_discussion_followup_prompt` and passed `resume_session_id`, which quotes only the trusted
  replies since the live session already holds the issue and its own prior analysis. What each one asks the agent for,
  and the plan clause both of them carry, are in
  [`../workflow/conversations.md#discussion-stage`](../workflow/conversations.md#discussion-stage). The degrade to
  the full prompt matters because `_run_agent_tracked` starts a *fresh* agent when no session id is passed, and a
  followup handed to that would arrive with no issue body, no design, and no frontier to fold an answer into; it
  carries the plan clause too, because a round with nothing cached can still be the round a human confirms on. The
  thread behind either prompt is read ONCE, and the same snapshot supplies both the text and
  the ceiling the round records as read — a second read is a thread minutes older or newer than the one the agent saw,
  and the disagreement between them is a comment either shown and re-sent next tick or consumed and never shown. The
  orchestrator's own analyses are retained in that text past `ALLOWED_ISSUE_AUTHORS` by their recorded
  `orchestrator_comment_ids` (not by the body marker, which anyone can paste), because a deployment that allowlists
  its humans and not its bot account would otherwise rebuild the conversation with the human's answers by number and
  the numbered questions they answer missing.
- **Records**: `discussion_agent` (the full spec) and `discussion_round_branch` + `discussion_round_sha` (the branch
  the round opened on and the SHA it was at) are WRITTEN before the spawn: a round can end with no disposition at all
  — a mid-run `paused` withholds every one by contract, a crash takes them with it — and the next tick reuses the same
  checkout, so without that anchor a commit the ended round made becomes the new round's own baseline and reads as
  work the branch arrived carrying. `discussion_agent` and `discussion_session_id` are re-read from pinned state on
  every round after the first rather than re-resolved, so a `DECOMPOSE_AGENT` flip between two rounds can retarget
  neither a replayed one nor a resumed one. `discussion_session_id` is staged after the spawn and rides the park's
  write, so it never outlives the analysis it points at — and a round that was NOT resumed writes it either way,
  absence included, since whatever it opened is a new conversation and an issue relabeled out of this stage and back
  arrives unparked still carrying the previous one's id. The consumed watermark is staged after the pre-spawn write
  for the same reason as the session id and lands with that same park: a round that never reaches a disposition is
  replayed, and it has to be replayed against the same replies rather than against an answer already recorded as
  read. Both round shapes stage one, over what their own prompt read — a resume consumes the batch it quotes, an
  opening round the whole trusted thread the full prompt rebuilt, which it has to or the comments it just answered
  would read as unanswered replies on the next tick. No developer or reviewer is ever spawned.
  `discussion_round_open` rides the pre-spawn write beside the anchor and says the round it describes has not
  reported yet; every park clears it, as does the one ending that writes records without parking -- the adoption of a
  pull request the humans have already decided.
  `discussion_base_sha` rides it too: the commit the REMOTE said the base branch
  was at, read through the token before the agent could touch the checkout, and the commit this round's work is
  finally measured against. `refs/remotes/<remote>/<base>` names the same thing but lives in the object store the
  per-issue worktree shares, so an agent could commit code, repoint that ref onto it, and commit the plan — leaving a
  ref-relative diff that shows one file while the branch carries two commits. It is persisted rather than re-read
  because the tick that publishes need not be the tick that ran: a recovery has to measure against the base its round
  was given. What is pinned is an id this clone holds, not merely one the remote named — the base advances between the
  tick's own fetch and the round that opens in it, and a diff naming an absent commit fails, which the path read
  reports as no paths at all: the same answer a branch that changes nothing gives, and enough to refuse a plan written
  exactly as asked. So the object store is asked, one authenticated fetch of the base supplies what it lacks (the tip
  read moments ago is an ancestor of whatever the remote has now), and an id still unreadable after that is recorded as
  no base rather than as a reading nobody could take. The same write settles the session the round runs under, in the
  one direction
  knowable before it does: a resumed round keeps the id it is resuming, and a round resuming nothing drops whatever
  was pinned, since the conversation it opens has no id yet and the previous one's would otherwise be what a recovered
  publication named. An opening round needs no such flag — it leaves the issue unparked, and an
  anchor on an unparked issue already means a round opened and never reported — but a RESUMED round runs with the
  previous park still durable, where that reading is unavailable. Without it, a resumed round that committed the
  confirmed plan and was then paused or cut short would come back to the humans as a violation to reset away.
  A publication writes twice. `discussion_publishing_sha` goes first, on its own, naming the tip it is about to push:
  everything after that write can leave the world changed, so it is what makes a half-finished publication both
  recoverable and attributable, and it carries whatever the round staged beside it since those records describe the
  publication it precedes. The rest go down in one further write, which also retires the marker — the park's, when the
  pull request is still open and the humans are being told where to read the plan, and a write of its own when the
  recovery adopts one they have already decided, since a "review the plan there" message would then be answering a
  verdict with instructions (`plan_terminal` reads those records on the next tick and finishes the issue instead).
  The records are `discussion_plan_path`
  and `pr_number` (the pair the
  hold at the top reads, and the pair that also tells the implementing stage its recorded PR is still a design however
  that PR's head has moved since), `discussion_plan_sha` (the commit that PR carries — read against the PR's head once
  the implementing handoff has retired the path record, so its merged-PR terminal does not take a plan being agreed to
  for work having landed, and asking GitHub is what makes that answer right even for a tick that pushed onto the same PR
  and died before recording it),
  `branch` (so a later checkout is restored from the ref the PR is open against rather than
  the legacy name), and the round anchor moved onto the published tip — the branch's new position is exactly what
  this stage now vouches for, and an anchor left behind would have the implementing relabel guard convict the branch
  of the commit this stage just published.
- **Disposition** (in order): a launch that never became a process (`invoked=False` — the agent-run circuit refused
  it) is declined first of all, ahead of the pause and every reading under it: no head, tree, or reply below is
  about a process that did not exist, and a park in its name would overwrite the durable `agent_run_limit` one the
  refusal took. Then a `paused` / `backlog` label applied mid-run suppresses every disposition below and
  returns without writing anything — the anchor above is what keeps that safe for a round that committed. Otherwise
  `last_discussion_at` is stamped and a non-interrupted run's usage is folded, then whether the commit question can
  be answered at all — both ends of it are `HEAD` reads, and either failing parks `discussion_unreadable_worktree`
  with nothing published, since the empty string a failed `rev-parse` returns compares unequal to the SHA the round
  opened on and would publish the branch's existing commit as this round's — then the commit (a run that
  wrote outranks how it ended, so it is judged before the timeout and before the response), then
  `discussion_timeout`, then `discussion_dirty` — checked before the
  interruption guard and before the response, so a round that wrote outside the one path it may commit parks on what
  it wrote rather than
  being published as a design — then an interrupted run returns silently, then a non-empty response parks
  `discussion_response` and an empty one parks `discussion_silent` with stderr diagnostics. Both write checks are
  measured against the checkout THIS round opened on: a HEAD read before the spawn and compared after (not
  `_has_new_commits`, which is base-relative and would blame the agent for dev commits an issue relabeled here from a
  PR stage already carried), and a tree the preflight above already established was clean.
- **Publication** (what a commit is judged by, from the disposition and from the preflight alike): the branch is read
  once, by four probes, and every one of them has to answer for it to be publishable. The tip is read first and then
  NAMED to the two commit-level probes rather than each re-reading `HEAD`, because it is also the revision the push
  publishes: `HEAD` between two `git` invocations is whatever the branch is on by then, and a verdict carried from one
  commit to another is what would let an unchecked commit go out under a checked one's name. The worktree status
  has to have
  been READ and to be clean — an unreadable one (a corrupt index fails `git status` while a commit-to-commit diff
  still succeeds) is not a clean one, and a push may not rest on a probe that never ran.
  `HEAD` also has to BE the branch: a commit made on a detached head, or on any other ref, is the plan by every
  other reading here, but the push sends a SHA to
  `refs/heads/<branch>` and that branch stays where it was — so the records would name a commit its own ref does not
  carry, the implementing relabel guard would convict the stale tip of being unreviewed work, and a checkout rebuilt
  from that ref would come back without the plan. Nothing here advances a ref an agent left behind, so such a commit
  parks `discussion_plan_invalid` naming which ref HEAD is on. The paths its commits change
  against `discussion_base_sha` — three-dot and `--no-renames`, so a base that moved on is not counted and a file
  renamed onto the plan path does not pass as one, and `--ignore-submodules=none` so a gitlink the commit moved is
  not hidden by a `diff.ignoreSubmodules=all` the agent can write into the worktree's own config (the status read
  spells `--untracked-files=all` for the same reason) — have to be exactly `plans/issue-<number>.md`. Every one of
  those reads asks for `-z`, since git's default output quotes an unusual path and joins a rename onto one line: an
  untracked file named ` -> ` comes back as `?? " -> "`, which is that same line format's rename spelling, and read
  as one it strips to nothing — a dirty tree reporting clean with the plan beside it published. A round with
  no base recorded at all has no reading, and parks rather than publishing paths measured from nothing. And that path
  has to be in HEAD **as a regular file**, because deleting a plan the base branch already carries changes exactly the
  path writing it would, and a deletion published as the agreed design is the "missing plan" case wearing the right
  diff — as is a symlink (whose blob is a target string, so what a reviewer opens is whatever it points at) or a
  gitlink (a commit id for a submodule nobody fetches) left at that path, both of which resolve as objects there while
  carrying no document. Anything
  else parks `discussion_plan_invalid` quoting both readings and the anchor to reset to, and pushes nothing. A
  publishable one is published only under a session that can be named: `discussion_session_id` is pinned before a
  resumed round spawns and recorded from what a fresh one opened, and a round that dropped the previous id and was cut
  short before recording its own leaves none — so does a backend that hands none back. Without it the publication
  parks `discussion_plan_unattributed` with the commit untouched, since a PR body that cannot say which conversation
  produced the plan fails the one thing that body is for. Otherwise it first records `discussion_publishing_sha` — the
  tip about to be published, written durably before
  anything can change the world, so a later tick can tell a commit this stage began publishing from one it merely
  found — then goes through the hardened `_push_branch`, with the lease pinned to a tip the remote was just read at.
  What makes that tip publishable is not which record names it but whether the commit being published CONTAINS it: a
  branch the remote does not have yet is the ordinary first publication, and anything else has to be an ancestor of the
  plan commit — true of a publication being replayed after a crash (the tip is that commit) and of an inherited PR
  branch the plan sits on top of. A lease cannot stand in for that check, since it proves only that the ref has not
  moved since it was read, so a round that reset an inherited branch to base before committing its plan would pass
  every other reading and delete the PR's history. Every other tip parks `discussion_push_failed` naming what is
  there. Pinning is the other half: left to the push's own `ls-remote`
  fallback, the lease would be whatever the remote had become, so a retry would send its older validated commit
  straight over a reviewer's push to that branch. The refusal comes AFTER the marker write for the same reason the
  failed push does — the reply that retries it is carried there by the in-flight record, and a park with no marker has
  no publication to finish, no round open, and a reason that suppresses the repair request as well.
  `_push_branch` is handed that same SHA as the revision to publish
  rather than pushing `HEAD`: the reading and the push are separate git invocations, and a branch that moves between
  them would otherwise put a commit no check ever saw on the PR while the records named the one that passed. A
  failed push parks `discussion_push_failed` with the
  commit left intact, since resetting it would discard the agreed design -- and it is that same write, the one carrying
  the marker, that first replaces a standing `discussion_push_failed` with `discussion_publishing`, because it also
  consumes the reply a retry was asked for by. Before any of that, the publication asks GitHub whether the commit
  it is about to push has already MERGED on a pull request: a tick that opened the plan PR and died
  before recording its number leaves nothing pinned pointing at it, and a human merging that PR closes it and (with
  auto-delete on) takes the head branch with it — so an open-state lookup finds nothing, the push recreates a branch
  GitHub deleted, and the open that follows asks for a second PR with no commits between its two refs. Searched by
  the publication's own commit across every state — and by the commits a pull request CARRIES rather than the head it
  is on, since a human pushing to that branch, or merging the base into it, moves the head inside the same window
  while the published commit stays in the PR — that PR is found and its number simply recorded, with no push and
  no open. That commit list is a request to GitHub, and one it can decline -- as is the enumeration the candidates
  come from, page by page. Either failure answers `PR_LOOKUP_UNREADABLE` rather than "no pull request carries this",
  because the amended-and-squash-merged PR this lookup exists to find has a moved head and a deleted branch, so the
  commit list is the only place it is still visible, and a walk that never reached it says only that nobody asked.
  On that answer the publication stops where it stands — nothing pushed, nothing opened, nothing said on
  the thread — after writing the marker, which is both what the next tick retries from and what persists the round's
  own staged records (a session id a fresh round holds only in memory would otherwise be lost, and the retry would
  refuse the plan as unattributable). The retry is the next poll; a marker already standing on this tip under
  `discussion_publishing` is not rewritten, so a GitHub outage costs one read a tick and no pinned-comment edits.
  An OPEN pull request whose head a human moved past this commit while still carrying it gets the same
  ending, and for the sharper reason: the branch already has what would have been pushed, so the lease is right to
  refuse the older SHA — but refusing alone parks `discussion_push_failed` with no `pr_number`, leaving a plan that is
  published and reviewable and unreachable from the issue that produced it. Both readings are required to say so: the
  remote head has to contain the commit (a tip that merely differs is somebody else's branch, and the divergence park
  is right about it), and a pull request has to carry it. Containment is a local question about an id that came off
  the remote, so the branch is fetched first unless that head is already in the store: their commit was made after
  this checkout was, and a retained worktree asked about an id it cannot resolve answers the same "no" a real
  divergence gives — which would park `discussion_push_failed` on every retry with `pr_number` never written. The
  lease below reads the same way for the same reason, and a tip nothing can fetch is refused there rather than adopted
  here on a reading that was never taken.
  A PR closed WITHOUT merging is the same answer to the PUSH, and for a sharper reason than the merge: pushing at one
  opens a REPLACEMENT proposing the very design a human just turned down, and the issue is then held on that
  replacement with their rejection left with nothing pointing at it. So the close is recorded like the merge, and
  `plan_terminal` reads it on the next tick to finish the issue `rejected`. The reading taken where the branch has
  MOVED off the marker's commit takes the same three answers but holds the close back, because there the caller's
  other answer is an operator's reset — the remedy the stale-publication park asks for — and answering that park can
  mean closing the stray pull request as well as resetting the branch, so a close read as a verdict on the spot would
  finish the issue on debris somebody was tidying. It is taken up once the reset has been ruled out (the branch is not
  back at the anchor, or the remote still carries the commit), and then it IS the verdict: without that, a reviewer
  who amends the plan and then closes it leaves an issue parked `discussion_stale_publication` for good — no
  `pr_number`, no terminal label, no event, and no branch anything will reap. Neither DECIDED ending is parked with
  the "review the plan there" message an open one earns: the humans have already decided, and the records go down on
  their own for the terminal to speak from. An adopted PR is made to name the publishing session before it is
  recorded, through the same check the
  reuse below runs: the lookup proves branch, base and commit and nothing about who opened it, so a hand-opened pull
  request on the plan's branch that a human merged or wrote on top of would otherwise be recorded as the artifact and
  described by a body about something else. And nothing is adopted at all without a session to name — the same
  `discussion_plan_unattributed` refusal the push earns, asked here too because this path reaches a pull request
  BEFORE the push does: a round cut short before recording the conversation it opened would otherwise have its plan
  recorded as published and the PR body rewritten to say `session None`. That refusal is written once, since the
  adoption is reached ahead of the turn-taking gate by a marker no reply has spent.
  Otherwise the PR is found-or-opened on the
  branch — a tick that died between `open_pr` and the pinned write re-derives the same artifact and reuses its own PR
  rather than 422-ing. What that lookup returns is only known to be open on the branch, though — an issue can arrive
  here carrying a PR, an operator can open one by hand — so a reused PR whose body does not already name the
  publishing session has that body rewritten to the plan's; one that names it is left as it stands, annotations and
  all. Its body names the `discussion_agent` backend and `discussion_session_id` that wrote the plan
  and carries no closing keyword — what a merge meant is this stage's own terminal to record, and the keyword outlives
  the label, so on a PR handed to a developer by a relabel it would let a merge of the plan alone close the issue as
  finished work. The body says what deciding it does instead: merging finishes the issue `done`, closing it unmerged
  finishes it `rejected`, and having the plan built is a relabel made before either. Its title comes from the plan
  commit's own subject, less the tracked issue's own trailing reference — a plan commit ending in the discussed
  issue's number does not put that number on the title, since the body beside it is already what says which issue
  the plan is for — and `pr_opened` is emitted with `stage="discussion"` only on the branch that really opened
  one. The label is untouched throughout: no `validating`, no `documenting`, no `in_review`.
- **Output**: the agent's response quoted in an issue comment pinging `HITL_MENTIONS`, or the matching park comment;
  `awaiting_human=True` with the durable `park_reason` re-set after `_park_awaiting_human` clears it. Or, on the
  terminal arcs above, the usage receipt plus the flip to `done` / `rejected` — and on the holds, nothing at all. That
  helper also stamps `last_action_comment_id` at the id of the notice it just posted, and this stage's park funnel
  puts back the value it was entered with: the ceiling this round's prompt was BUILT from, not the thread as it
  stands minutes of agent run later. A comment posted in that window — a human's second thought, or an outsider's the
  allowlist may later admit — is never in front of the prompt, and this stage reads no comment twice, so recording it
  as consumed would mean it is answered never. That funnel is also where the emitted `park_awaiting_human` record
  and its analytics row pick up their bounded correlation: the road the tick came off (`discussion_round` for a tick
  opening the conversation's round, `discussion_resume` for one answering a reply into this stage's own park),
  `agent_role="decomposer"`, the `pr_number` of the plan's own PR — read off the plan path and the number together,
  exactly as the round gate reads it, so a developer's PR the issue merely arrived carrying is not reported as this
  conversation's — and the `sha` of the commit the artifact stands on, `discussion_publishing_sha` while a
  publication is in flight and `discussion_plan_sha` otherwise, so a failed push or a stale publication names the
  commit its park asks an operator to restore rather than one an earlier plan of the same issue left pinned (the
  implementing handoff retires the plan PATH and keeps that SHA, so both records can stand at once). Unheld fields
  are dropped rather than written as nulls, and nothing in the payload comes from the round's analysis; see
  [event streams](../observability/event-streams.md). Leaving the mark below the stage's own posted analysis is safe
  because `_new_trusted_replies` drops the orchestrator's own comments by recorded id and by the
  `_ORCH_COMMENT_MARKER` in their body (never by author login, which a PAT shared with a human's account would turn
  against that human's real replies), so a conversation cannot resume on itself. Every round after the opening one
  ends the same way until the humans confirm the design; what that confirmation buys is a plan PR, not a transition,
  so the stage decides no transition of its own until that PR is decided — and then it decides only the terminal the
  humans wrote on it.
  Everywhere else, leaving this stage is a human relabel. The `issue-N` worktree is PRESERVED on every ROUND exit —
  the tree the discussion read is the tree its next round and the operator both look at — so the only thing that ever
  tears one down is the plan-PR terminal above, and only once that pull request is gone; the per-tick base sync stands
  down on the `discussion` label (alongside `question`, in `_issue_skips_base_sync`) so `<remote>/<base>` is never
  rebased over that state. That same gate also stands down on an unconsumed `discussion_*` / `question_*` park
  whatever the current label is, because the refresh runs before the handlers: an operator's relabel to
  `workflow:implementing` removes the label a full tick before the guard below rules on the branch, and a rebase in
  that gap would move the tip off the recorded anchor and convict a branch nobody touched. It stands down on the two
  in-flight records as well — `discussion_round_open` and `discussion_publishing_sha`, whatever `awaiting_human` says
  — because both are written BEFORE the thing they describe: a tick that died after the agent committed leaves one
  standing with no park at all, and the commit it died holding on the branch. Clearing the park does not lift the
  freeze either: it becomes `read_only_baseline_sha`, and the branch stays put until that is spent on published work.
- **Exit**: either terminal above — the plan-PR verdict, or the pre-PR close — to `done` or `rejected`, the two edges
  `ALLOWED_TRANSITIONS` grants the state; or a human relabel: to either of those same two by hand, or, through the
  GitHub UI, to `workflow:implementing` once the thread settles on building it. That last one is not a
  graph edge, so it arrives as an operator relabel and is screened by the read-only guard in
  `workflow/stages/implementing/read_only_relabel.py` — over the readings `relabel_hazard.py` takes, against the tips
  `relabel_evidence.py` can vouch for, and refused through `relabel_refusal.py`: a `discussion_*` park whose worktree
  is dirty, whose recorded branch no longer sits at the SHA the round anchored on, or whose CHECKOUT is on a commit no
  record vouches for, re-parks as `discussion_unsafe_relabel` rather than
  letting the recovered-worktree shortcut push that work as a dev implementation; a clean one clears the park and the
  dev spawns fresh. The checkout is read for its own `HEAD` because a commit does not have to be on a ref anybody here
  names: an agent that committed while detached leaves every branch exactly where the round opened it and the plan in
  the tree, which is what the creators keep and what the shortcut pushes. An unreadable `HEAD` counts against it for
  the same reason a dirty tree does, and so does a `git status` that failed: the list form of that read maps its own
  failure to "no paths", which is what a clean tree reports, and accepting on it would let worktree creation
  force-remove the very tree an operator was parked to inspect. Proving a checkout carries nothing cannot rest on a
  probe that did not answer. A park with no recorded tip to match (the question stage's) is certified the older way
  instead, by the checkout not being ahead of base. The screen answers for the two in-flight records on the same
  terms, and with no park to find them by: an opening round leaves the issue unparked, so a tick that died after the
  agent
  committed — or after its plan PR was opened — would otherwise arrive here looking like an ordinary relabel, and one
  push later the plan would be a dev PR closing the issue. A standing publication marker is refused on the record
  alone, without waiting for a local reading to convict: that marker is written before the push, so the branch may be
  on the remote with a PR open against it, and on a fresh clone every local probe reads clean at once — no checkout,
  nothing ahead of base, no tip to compare. Handed over there, the developer builds from base and the push takes a
  lease read live off the remote: the published plan is overwritten and its PR adopted as the implementation's. So the
  refusal names which half died and leads with the way out that finishes it — relabel back to
  `discussion`, whose own recovery restores the checkout from the PR head, adopts that PR, and records it — rather
  than a reset that would destroy the plan. Those two records are read AHEAD of the terminals rather than behind
  them, which is the one place the guard's position in the preflight is not enough: the `pr_number` such an issue
  carries is whatever it arrived with — a previous cycle's implementation, or an earlier discussion's plan PR — and
  merged, it would close the issue as `done`, delete the branch the plan is sitting on, and leave the marker standing
  on an issue nothing comes back for. A round that died before committing anything is handed over like any clean
  park, and its records are retired with it, after which the terminals run against a state that no longer claims an
  unfinished conversation. A published plan passes that screen because publication moved the anchor
  onto the tip it pushed, so the branch carrying the plan commit is exactly what the record certifies — and when that
  plan PR has MERGED the handoff anchors the checkout on the base instead of leaving it there, since the design landed
  along with everything else that has since, and the baseline the handoff records would otherwise freeze the branch
  behind the one it is being built for. The anchor is
  checked whatever the branch's relation to base now is — a reset all the way to base
  is not ahead of base, but on a PR-backed issue it discarded the very commits the round was certified against — while
  a recorded ref that no longer exists is not a violation, since nothing local is left to attribute and the checkout is
  rebuilt from the PR head. A plan PR that has MERGED takes the older ahead-of-base question back, and has to: its own
  handoff moves the branch to the base and records where it landed in the write AFTER the move, so a tick that dies in
  between leaves a branch on a tip no record names — matched exactly, the base itself reads as unreviewed work and the
  refusal tells the operator to reset backwards off the commit the merge produced. A branch carrying nothing beyond
  base carries nothing of anybody's, and the move is idempotent, so the next tick simply makes it again.
  The refusal names the anchor as the reset target, so an issue whose branch legitimately
  carries a PR's commits has a way back that does not discard them, and the clear hands that same tip on as
  `read_only_baseline_sha` so the shortcut does not then mistake those inherited commits for a dev run to finish. The
  clear also drops `discussion_plan_path`: that record exists to stop this stage acting while the plan is with the
  humans, and the relabel IS them deciding — left behind, it would hold the stage inert for good if the issue ever
  came back. Dropping it is what hands the plan question over to `discussion_plan_sha`, and the order is the point:
  the guard runs behind the merged-PR question above — except on an issue whose in-flight records hoisted it, where
  the write happens first and the same PR is then read against the commit it just recorded — so every tick that has
  not reached this write still reads the recorded PR as a design however its head has moved, and only the ticks after
  it can read a moved head as this stage's own push. Which is why the head that PR is on NOW is read before the guard
  rules — `plan_reading.py` owns that read, and the accepted handoff takes the same one every tick after — and
  recorded in the path record's place. Between the publication and the relabel the humans have the design
  on a PR and can move its head —
  a correction to the Markdown, the base merged in to make it mergeable — and the commit publication recorded would
  then be a stale answer: the tick after the handoff would read their own edit as an implementation and close the issue
  as `done` with no developer having run. The same read anchors the checkout, through
  `worktrees/anchoring._anchor_pr_worktree`: one authenticated fetch of the branch, a re-read of what the remote says
  that branch is on, and a `reset --hard` onto that head
  (an `update-ref` when the worktree is gone), both under the hardened envelope like every other reset here — the
  checkout is agent-writable and a linked worktree can write the common repo, so an `fsmonitor` on the reset's index
  refresh or a `reference-transaction` hook on the ref update would otherwise run with this process's environment. The
  reset also NAMES its tree with `--work-tree`, which the envelope cannot do for it: `core.worktree` in the
  per-worktree config redirects every path operation and no `-c` override beats it, so a reset left to discovery
  reports success and moves the ref while writing the reviewed commit's files into whatever directory it was pointed
  at — the issue's checkout stays on the plan it had, the recorded baseline names a tip the tree is not on, and
  somebody else's files are overwritten on the way past. The
  developer then builds on the design its reviewers approved rather
  than on a tip whose push would take their amendment back out. The re-read is what keeps that true across the gap
  between the two: the head was read off GitHub a moment earlier, and a human pushing to that branch in between
  leaves the fetch bringing THEIR commit while the one just read still resolves underneath it as an ancestor — so
  "the object is here" would anchor on a head the PR has moved past, and the push that followed would read their
  commit off the remote as its own lease and overwrite it. Only a remote still on that head anchors; anything else
  holds the handoff for a tick that reads the pull request again. `read_only_baseline_sha` then records where the branch
  really ended up — the reviewed head when the move landed, and `<remote>/<base>` when the remote confirms that branch
  is gone and what it carried has landed there, which is a base this tick FETCHED or no answer at all: a cached
  remote-tracking ref resolves perfectly well after a failed fetch and names the base from before the merge, the one
  base a plan that has just landed is not in — since a
  baseline naming any other commit would have the spawn path read the difference as an interrupted dev run and push it
  with no agent. The base is reached only when the handoff names NO head at all, which is how it says the design
  landed: a named head whose branch the remote no longer has is a pull request somebody closed and cleaned up after,
  so what it carried went with the branch and anchoring at base would retire the plan records and start the developer
  from a tree the plan was never in. A move that established NEITHER holds the handoff: the tick ends having written
  nothing, plan record intact, because accepting it would put the developer behind the reviewers and the ordinary
  push that follows reads
  their head off the remote as its own lease. A plan PR that could not be READ ends the tick the same way, because
  every one of those decisions is durable and none of them may rest on a stale reading. Reading it before the guard
  is also what makes the move crash-safe: the branch is anchored ahead of the write that records it, and a tick that
  dies in between leaves a tip the next one recognizes as the reviewed head rather than convicting the branch of it.
  The plan's own `pr_number` and `branch` stay, so the dev continues on the branch the plan PR is open
  against and its implementation lands on that same PR.
  **Removing the label is not an exit.** The stage records `discussion_agent` / `discussion_round_sha` in the
  issue's pinned comment, and
  [`_handle_pickup`](delivery-stages.md#_handle_pickup-no-label--workflowdecomposing-or-workflowimplementing)
  starts an unlabeled issue on a fresh `PinnedState`, so the pickup would
  write a *second* pinned comment while `read_pinned_state` keeps returning the first — the discussion's. Closing the
  issue IS a terminal signal, and `discussion` is in `CLOSED_SWEEP_LABELS` so the closed issue keeps being polled
  until that signal is drained: with no plan PR the close finalizes to `rejected`, and with one it waits for the
  pull request (see the terminal bullet at the top of the handler above).

The two stages share their shape and part on what a round may leave behind: an operator-applied bare label nothing
routes into, the decomposer's backend under a pin of the conversation's own (`question_agent` / `discussion_agent`
and their session ids, each an independent pair), a park that suppresses the next tick until a trusted reply arrives,
the read-only base-sync gate, no developer and no reviewer at any point, and the same guard screening a relabel to
`workflow:implementing` — around a question that never writes and a discussion that writes once. What each prompt
grants and forbids, and why the plan the relabel hands over is an artifact nothing downstream parses, are in
[`../workflow/conversations.md`](../workflow/conversations.md).
