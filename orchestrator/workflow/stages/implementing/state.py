# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state keys and CLI markers the implementing owners share.

Every field name here is a key in the JSON comment live issues already carry,
so these are wire strings, not internal spellings: renaming one is a migration
of every open issue, not a refactor. They sit in one module because the owners
that write them and the owners that read them are different files -- the park
that sets `park_reason` is not the preflight that clears it, and the timeout
that persists `pre_implement_sha` is not the recovery that publishes off it.

The marker tuples are the other half: each is a set of CLI phrasings one
classifier in `session_read` matches a failed run against, and each is grouped
by the recovery it selects (drop the session, wait for a quota reset, park a
question) rather than by the backend that emits it.
"""
from __future__ import annotations

_SILENT_PARKS_BEFORE_FRESH_SESSION = 2

# How many consecutive readings one frozen pair may lose before the size gate
# stops retrying quietly and hands the issue to a human. Only the two steps
# that name the TRANSPORT between this host and the base are counted against
# it -- a remote that would not answer for the branch, and a fetch that did
# not bring the object back -- because those are the ones that clear
# themselves while nobody is watching; every other step names something a
# second reading cannot change and parks on its first miss.
#
# It is bounded because a transport that has missed this many readings in a
# row is not one this process is going to reach, and a candidate whose size is
# unknown is not a small one, so committed work would wait behind it
# indefinitely. Past the bound what stops is the counting and the silence
# rather than the reading itself: the published road re-reads the pair on
# every poll, reporting each failure on both sinks, so the transport coming
# back settles it with no human at all -- but it is said out loud once.
_MEASUREMENT_MISSES_BEFORE_PARK = 3

_CLAUDE_STALE_SESSION_STDERR_MARKERS: tuple[str, ...] = (
    "no conversation found with session id",
    "no conversation found with id",
    "no conversation with session id",
    "conversation not found",
)

_CLAUDE_CONTEXT_OVERFLOW_MARKERS: tuple[str, ...] = (
    "prompt is too long",
    "input is too long",
    "input length and `max_tokens` exceed context limit",
)

_CLAUDE_SESSION_LIMIT_MESSAGE_MARKERS: tuple[str, ...] = (
    "you've hit your session limit",
    "you've hit your usage limit",
    "you've reached your session limit",
    "you've reached your usage limit",
    "claude usage limit reached",
    "claude ai usage limit reached",
)

_DEV_AGENT = "dev_agent"

_DEV_SESSION_ID = "dev_session_id"

_CODEX_SESSION_ID = "codex_session_id"

_SILENT_PARK_COUNT = "silent_park_count"

_DEV_RESUME_COUNT = "dev_resume_count"

_RETRY_WINDOW_START = "retry_window_start"

_RETRY_COUNT = "retry_count"

_AWAITING_HUMAN = "awaiting_human"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# The receipt this stage stamped on a sentence it has not recorded posting,
# written before that sentence goes out and dropped by the write that would
# have recorded it. Every road on the authorization park posts before anything
# persists the id of what it posted, so a process dying in between leaves a
# sentence of ours on the thread that no later reader can attribute -- and one
# standing over the command this park waits on is read as somebody's fresh
# guidance and resumed a developer against.
#
# Recorded FIRST is what makes it mean anything: present, a tick died between
# recording the sentence and recording having said it, so something may still
# be owed; absent, the write past the post ran and nothing is. Which side of
# the post that tick died on is then asked of the THREAD, which is the only
# place that knows.
#
# What this field may never be built into is a claim that some comment is
# OURS, and the reason is where it lives rather than what it says. The record
# is itself a comment on the issue, so a receipt written here as plain text is
# published by the very write that records it -- readable, before the sentence
# it names exists, by the human whose consent this park collects, from a login
# they may share with us. Anything attributing a comment on that basis hands
# them the power to have their own retraction deleted from the reading, with
# the authorization beneath it publishing on consent withdrawn. Only
# `orchestrator_comment_ids` says a comment is ours, and the one road that
# adds to it without a write of its own is `late_recovery`, which proves what
# it claims by a secret this field never holds.
_HELD_RECEIPT = "late_held_authorization_receipt"

# What a handoff into the publication seam has said and not yet accounted
# for: one digest per comment, each recorded before the comment carrying its
# secret goes out and dropped by the write the instant that post returns. What
# it marks is the one API call in between, where a sentence of ours is on the
# thread and nothing on the record names it.
#
# One that survives that write is answered by the LEDGER repair `late_recovery`
# runs ahead of its own routing: the earliest comment whose body is that
# sentence goes into `orchestrator_comment_ids`, no watermark moves, and the
# entry is dropped. Cleared anywhere else -- with the park a publication
# handoff was held across, say -- nothing is left able to find that comment,
# and the next poll pays a developer to answer the orchestrator's own park
# notice and consumes every human reply underneath it.
#
# What the digest commits to is the SENTENCE and not the sender -- the secret
# AND the exact body it goes out on -- and that is the whole of what makes
# recognizing one safe. A secret is unforgeable only until it is disclosed, and
# posting the sentence discloses it: from that moment a reply quoting our
# comment carries the secret too, and the login beside both is a token this
# repository says may be shared with the human whose consent this park
# collects. Ordering told the two apart only while our comment stood, and
# ordering does not survive that comment being DELETED. Bound to the body,
# their reply answers nothing -- a quote carries their words as well as ours.
# What can still answer is a verbatim copy, which carries nobody's words to
# lose, so passing over it takes nothing from anyone.
#
# So what the repair records IS a permanent claim against a comment id, in
# `orchestrator_comment_ids` beside every comment this process posted itself,
# and the body is what licenses one: the id it writes down names a comment
# whose text is our sentence and nothing else, which carries nobody's words to
# lose. The EARLIEST such comment is claimed, and a copy can only follow what
# it copies, so reaching one takes our own comment being deleted first --
# available to somebody already holding the token that authorizes publication
# outright, over a body that was never theirs. What may never license an entry
# there is the receipt above: that string is deterministic public text, so an
# id recorded off it would let the human whose consent this park collects have
# their own retraction deleted from every later reading.
#
# A LIST because the seam says more than one thing on the road that matters,
# and a digest of one body is answered by that body alone.
#
# The FIRST entry is recorded before the seam is entered at all, in the same
# write as the held park below -- a promise about the secret, which the client
# refines to the sentence once there is a body to name. The seam can post the
# moment it is called, so a receipt minted no earlier would leave the one
# sentence nothing else covers.
_HELD_PUBLICATION = "late_held_authorization_publication"

# What the authorization park was before a handoff to that seam, recorded
# ahead of the call and dropped by the same write. The seam parks under
# reasons of its own DURABLY, so a rollback kept only in the frame that made
# it dies with the process: the poll after a crash would find an issue waiting
# under the seam's reason, over a watermark its notice moved past the command
# an operator already wrote, and nothing anywhere saying what it had been.
_HELD_PARK = "late_held_authorization_park"

# How far the reading behind that handoff GOT, recorded in the same write and
# spent by the one that ends this stage's hold on the issue.
#
# The seam consumes the command itself wherever it records an authorization
# from it, and two of its roads publish without reading the thread at all: a
# candidate the ceiling now lets through settles on its own count, and one an
# authorization already on the record covers publishes as decided. On either,
# the reply that ended the park is still above the watermark when the label
# moves -- and the stage it moves to reads it as somebody's fresh feedback and
# pays for a developer to answer a command nothing there can act on.
#
# Staged BEFORE the call for the reason the park beside it is. The handoff
# writes durably and moves the label before this stage gets an answer back, so
# a boundary applied on the way out is one a crash in that window loses, on an
# issue implementing never sees again. Written down first, it is spent in that
# same write, ahead of the label.
#
# What it may consume to is what the reading LOOKED at and no further, since a
# tick consuming past whatever the tip has become since would swallow a reply
# posted in between. And it is spent only where nobody is waiting any more: a
# park the seam replaced is put back over the watermark it was found on, and
# one the gate's own reading held is still owed the reply, so both drop this
# rather than spending it.
_HELD_COMMAND = "late_held_authorization_command"

_AGENT_TIMEOUT = "agent_timeout"

# The park a handoff refuses on: the checkout is not the commit the size
# gate approved. It is its own reason because the recovery is neither a
# session retry nor a re-measurement -- what it asks for is the worktree
# back on that commit, and until then no stage past this one may read it.
_CANDIDATE_MOVED = "late_candidate_moved"

# The commit this issue owes a publication and no push has carried yet. It
# goes down in the same write that APPROVES one -- the retirement a small
# candidate earns, and the exemption an authorized settlement records --
# because
# both of those writes drop the record that used to name the commit, and the
# push they license runs after them. Without it a tick that died in that
# window would leave nothing on the issue naming the work: a replacement host
# rebuilds the checkout from the base or the plan pull request, finds a head
# nothing contradicts, and publishes it or pays for a second developer over an
# implementation the first one already finished.
#
# So it is proved before anything spawns and it is what the park that refuses
# an unpublishable checkout is answered by: a worktree put back on that commit
# is the one the reading was taken over, so the recovery republishes it rather
# than asking a human for guidance. Dropped by the handoff that spends it, and
# by the adjudication that supersedes it.
_APPROVED_SHA = "late_approved_sha"

# What the approval beside it RESTS on, so a later tick can tell the gate's own
# answer from an adjudication's publication debt without inferring it from the
# records standing around them. The two are written in different places and
# mean different things: a reading this gate took needs nobody's permission to
# be spent, while a debt an authorized settlement recorded is the exemption
# wearing another field and is worth exactly what that exemption is worth.
#
# Inferred instead -- "an approval naming a commit some exemption also names is
# the settlement's" -- it is wrong in both directions: a candidate the gate
# measured small on an issue that still carries an older binary's exemption
# would have its own approval refused and be re-judged against a base that has
# moved, and a settlement's debt whose exemption somebody hand-edited would
# read as the gate's own and publish unmeasured. So the owner that grants one
# says which it is, and only a value from this build's own vocabulary reads
# back: an approval an older binary wrote carries none, and the exemption is
# the only evidence left for those.
#
# Written, dropped, and spent with the approval it describes, never on its own.
_APPROVED_BASIS = "late_approved_basis"

# The head the pull request stood on when the approval beside it was written,
# for a candidate the gate approved on the PUBLISHED side. It outlives the
# generation that froze it for exactly as long as the push it licenses is
# still owed, and it is what that push is leased against.
#
# Without it the retry after a failed push has nothing but the pull request's
# CURRENT head to pin to -- and the retry skips the measurement, because the
# commit is already approved -- so a head somebody moved in between would be
# adopted as the lease and force-overwritten by work measured against the head
# it used to be on. Recorded, the retry pins to what was frozen and git
# refuses the push, which is the answer a moved publication is owed.
#
# Written, dropped, and spent with the approval it belongs to, never on its
# own: an approval with no lease is a pre-publication one, which is what every
# implementing-seam approval is and what the push there correctly takes its
# own reading for.
_APPROVED_LEASE = "late_approved_lease"

# The commit this stage last PUSHED, written durably ahead of the relabel that
# hands the issue to review. Between those two the branch is on the remote and
# a pull request carries it, while the label still says implementing and every
# record the gate decided by is spent -- so a relabel that failed, or a process
# that died in between, leaves the next tick reading a published branch as work
# nobody has ruled on. Measured again there against a base that has moved or a
# ceiling that was retuned, it can be routed to adjudication with the push and
# the pull request already made, which is the one outcome the size gate exists
# to prevent.
#
# It names one commit and only it, which is the whole invalidation rule: work
# committed on top is work this stage has not published, and is measured as
# the fresh candidate it is. So there is no clearing step -- the next
# publication overwrites it, and a developer's next commit moves the head off
# it.
_PUBLISHED_SHA = "implementing_published_sha"

# The head the recorded publication REPLACED -- the one the entry it was made
# under froze, which is the head the push was pinned to. Written and dropped
# with the receipt beside it, never on its own, because it is what scopes that
# receipt to one publication attempt.
#
# The receipt alone cannot say which attempt it is evidence for. It is never
# cleared, so a pull request a revert or a rewrite rewound onto a commit this
# stage published rounds ago reads exactly as this tick's own push having
# landed -- and where the checkout is standing on that same commit, the
# rewound head would be adopted as a publication nobody moved and the
# candidate handed on unmeasured. Paired with the head it replaced it answers
# for one window and no other: a push made from THIS head, on a tick that died
# before the relabel behind it.
#
# Empty for an initial publication, whose push froze no head to be pinned to.
_PUBLISHED_LEASE = "implementing_published_lease"

# The pull request the recorded publication went ONTO, written with the
# receipt beside it and never on its own.
#
# The receipt says a commit reached a remote and the lease dates it to one
# attempt; neither says WHICH pull request now carries the work, and that is
# what the bookkeeping behind a landed push has to be bound to. Recorded only
# by the relabel, it is missing for the whole window the receipt exists for --
# a push that landed and a process that died before the handoff -- and a
# reader with no identity there has nothing to fall back on but a lookup by
# branch, which answers with whatever open pull request is on that ref: a
# REPLACEMENT somebody opened after closing the original satisfies it, and the
# bookkeeping is spent against a publication this stage never made.
#
# Written with the receipt, the identity covers exactly the window the receipt
# does. Absent or unreadable it is refused rather than searched for: what a
# refusal costs is a park a human repairs, and what a search costs is binding
# a relabel, a debt and a receipt to somebody else's pull request.
_PUBLISHED_PR = "implementing_published_pr"

_PARK_REASON = "park_reason"

_PRE_IMPLEMENT_SHA = "pre_implement_sha"

# The tip a read-only stage's relabel certified as "what the branch already
# carried". The recovered-worktree shortcut reads commits ahead of base as a
# previous dev run's, which an issue arriving from `discussion` on its PR's
# branch would trip on its first tick -- the dev would be skipped and the
# inherited commits republished as its work. Written by
# `read_only_relabel._clear_stale_read_only_park` from the round anchor it
# retires; spent by `spawn._prepare_active_dev_run`.
_READ_ONLY_BASELINE_SHA = "read_only_baseline_sha"

# The head an accepted plan handoff is moving the branch onto, written before
# the move and retired by the write that records where it landed. Without it,
# the tick after a crash in between cannot tell the branch that move left --
# sitting on the plan PR's live head -- from a developer's own commit, and the
# recovered-worktree shortcut would push the reviewers' amendment as the
# implementation with no agent having run. Written and spent by
# `plan_handoff._readvance_plan_handoff`.
_HANDOFF_ANCHOR_SHA = "read_only_anchor_sha"

_BRANCH = "branch"

_PR_NUMBER = "pr_number"

_IMPLEMENTING_STAGE = "implementing"

_REASON_STUCK = "stuck"

_PR_BODY_AGENT_MESSAGE_CAP = 60000

_PR_BODY_TRUNCATION_MARKER = "_…(message truncated)_"
