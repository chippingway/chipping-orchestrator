# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park reasons, pinned-state keys, and run identity the owners share.

The keys go into the pinned JSON comment live issues already carry, so renaming
one is a migration rather than a refactor -- and none of them has a single
owner: the park is written by one module and read by the handler that decides
whether a tick has a round to run at all, and `discussion_agent` /
`discussion_session_id` record which backend and conversation this issue's
discussion belongs to. Spelling them once is what keeps a typo from reading as
"never parked", "never spawned", or "nobody has replied yet".

`_LAST_ACTION_COMMENT_ID` is the one key here every other stage writes too: the
thread position a round's replies are read after, stamped by the shared park
helper on the way out and moved past the replies a resumed round was handed on
the way in. Spelling it anything but what that helper writes would leave a
conversation answering comments the park before it already consumed.

The reasons share a prefix because that prefix is what `_parked_by_discussion`
asks about -- and what `workflow/stages/implementing/read_only_relabel.py` asks
about from outside the package, refusing to ship what one of these parks left
behind as dev work. Pinned state outlives a relabel, so an issue an operator
moves here arrives carrying whatever park the stage before it wrote; reading
bare `awaiting_human` would leave such an issue inert forever, waiting on a
reply to a question this stage never asked.

`_ROUND_BRANCH` / `_ROUND_SHA` are the round anchor: the branch this stage last
opened a round on and the SHA that branch was at when it did. They are written
BEFORE the spawn and survive every exit this stage takes, which is what lets
one record answer both questions asked of it.

On an issue with no discussion park, a non-empty anchor means a round opened
and never reached a disposition (withheld by a mid-run pause, or cut short by a
crash), and comparing it to the branch says whether that round left a commit.
On a parked issue it is a statement about the branch: everything the branch
carries AT that SHA predates this stage, so a tip still sitting there is
certified and one that has moved is not.
`workflow/stages/implementing/relabel_evidence.py` reads it that way, which is
how a discussion held on an inherited PR branch is relabeled to implementing
without being accused of the dev's commits.

That is also why a park that DID find a commit keeps it rather than spending
it. The anchor is the only recorded point dividing what the agent wrote from
what the branch arrived with, so it is the reset target the commit parks quote
and the tip this guard re-measures against once an operator has reset. Dropped
there, a PR-backed issue would be left with commits ahead of base and nothing
able to certify them: refused forever, with the only remaining remedies --
reset to base, delete the branch -- destroying the PR. The relabel that
succeeds is what finally clears the pair, in `_clear_stale_read_only_park`.

The branch is recorded beside the SHA because a SHA alone does not say which
ref it belongs to: an issue whose pinned `branch` is the legacy
`orchestrator/issue-N` form has its round open there, and a probe that answered
for the slug-namespaced ref instead would report an unchanged tip while the
commit sat on the branch the round actually used.

`_PLAN_PATH` is the publication's own record, and it is what the next tick
reads to know the conversation has produced its artifact. It is written with
`branch` and `pr_number` in one durable write, which is why `_plan_published`
consults the pair: an issue relabeled here from a PR stage arrives carrying
somebody else's `pr_number`, and a stage that read that alone would never open
the round it was labeled for. The path is spelled by `_plan_path` rather than
stored as a constant because it names the issue, and it is spelled HERE rather
than beside either of its two users so the prompt that promises the agent a
path and the check that refuses to publish anything else cannot drift apart.

`_PLAN_SHA` is the commit that publication put on the PR, and both records are
read from outside this stage: implementing asks whether the PR this issue
records is still just the plan before its merged-PR terminal fires, because
merging a plan is a human agreeing to a design and would otherwise close the
issue as `done` before a developer ever ran. `_PLAN_PATH` answers that first,
and answers it whatever the PR's head is now. It is retired by that stage's own
handoff, which is durable and comes before it spawns anything, so while it
stands nothing there has pushed -- and a head that has moved is the humans
editing the design they are agreeing to, a corrected plan or a base merged in to
make it mergeable, not work having landed.

`_PLAN_SHA` answers for the ticks after that handoff, and it records the commit
rather than the PR number so the answer reconciles itself against GitHub
instead of depending on a write. The recorded PR's head moves the moment
implementing pushes onto it, which is exactly when it stops being a plan -- so a
tick that pushes and then dies before persisting anything still leaves a PR that
reads as an implementation, and the merge that follows finalizes as it should.

`_ROUND_OPEN` rides the same pre-spawn write as the anchor and says the round
it describes has not reported yet. Every park clears it, so it is true only
between a spawn and the disposition that follows it -- or forever after a
disposition that never came, which is the case it exists for. An OPENING round
needs no such flag: it leaves the issue unparked, and an anchor on an unparked
issue already means a round opened and never reported. A RESUMED round runs
with the previous park still durable, where that reading is unavailable, so a
commit found under a park is somebody else's until this flag says otherwise --
and without it a resumed round that wrote the agreed plan and was then paused
or cut short would be reported to the humans as a violation to reset away.

`_BASE_SHA` rides that same pre-spawn write and is what the round's work is
finally measured against: the commit the REMOTE said the base branch was at,
read through the token rather than off `refs/remotes/<remote>/<base>`. That
local ref names the base but lives in the object store the issue's worktree
shares, so an agent can commit code, repoint it at that commit, and then commit
the plan -- leaving a base-relative diff that shows one file while the branch
carries two commits. Persisted rather than re-read, because the tick that
publishes may not be the tick that ran: a recovery has to measure against the
base the round was given, and re-reading it would let the same local ref answer
after all.

What is recorded is an id this clone can read, not merely one the remote named.
The diff that spends it is local, and the base advances between the tick's fetch
and the round that opens minutes later, so an absent object would fail that diff
-- and a failed diff reports no paths, which is what a branch changing nothing
reports too. The round pins a base it has fetched, or it pins none.

`_PUBLISHING_SHA` is the other half of that record and the shorter-lived one:
the tip a publication is in flight on, written durably before the push and
cleared by the write that records the PR. It exists because a commit alone
cannot say who made it. On an issue this stage has parked, the round that
earned the park is over, so a plan-shaped commit appearing on the branch
afterwards is somebody else's -- an unrelated session, an operator's hand --
and publishing it would attribute a design to a conversation that never agreed
to one. The marker is what narrows that to the two commits this stage really
owns: one whose publication it began and did not finish (a tick that died
between opening the PR and recording it), and one whose push failed and is
being retried by the reply to that park.

`_DISCUSSION_PUBLISHING` rides that same write, and what it is there to do is
stop being `_DISCUSSION_PUSH_FAILED`. That reason means "an operator has to fix
this and reply", so the recovery path refuses to resume a publication carrying
it -- and the write that begins the retry has already consumed the reply that
would otherwise carry one. Left standing through that write, a crash straight
after it would leave a publication nothing resumes and no unread answer to
resume it with, waiting for a human to say the same thing twice. Every ending of
the attempt writes its own reason over it, so it is durable only inside that
window and never says anything to anybody.

While it stands it answers for the branch outright rather than merely failing
to vouch for it. A tip that does not match parks `_DISCUSSION_STALE_PUBLISH`,
because the alternatives all publish something nobody proved: a second
plan-shaped commit over an unfinished publication would otherwise be read by
the checks below as a round's own work and go out as the agreed design.

The stage and role names sit here for the opposite reason: they are not pinned
state at all. `_DISCUSSION_STAGE` is what an audit event and an analytics row
attribute the run to, and `_DECOMPOSER_ROLE` is the role whose configured agent
runs it -- the discussion is the decomposer thinking out loud before anything
is decomposed, so it answers under that role rather than one of its own.

The two route names beside them are the same kind of value: the road a tick
reached its park from, which a park's record carries because nothing downstream
can re-derive it. The stage on that record says which handler wrote the park,
never whether the tick was opening the conversation or answering the humans in
it -- and every ending of this stage is a park, so without the road the two
kinds of tick are indistinguishable in the sink.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState

_DISCUSSION_STAGE = "discussion"

_DECOMPOSER_ROLE = "decomposer"

_ROUTE_DISCUSSION_ROUND = "discussion_round"

_ROUTE_DISCUSSION_RESUME = "discussion_resume"

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The two keys a published plan lands on, shared with every stage that opens a
# PR: `pr_number` is also read before one is written -- to tell an issue whose
# branch has a remote PR head to restore from, from one whose branch exists
# nowhere but locally (see `run._ensure_round_worktree`) -- and `branch` is
# recorded beside it so a later tick resolves the ref the PR is open against
# rather than falling back to the legacy name.
_PR_NUMBER = "pr_number"

_BRANCH = "branch"

_PLAN_PATH = "discussion_plan_path"

_PLAN_SHA = "discussion_plan_sha"

_PUBLISHING_SHA = "discussion_publishing_sha"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

_DISCUSSION_AGENT_KEY = "discussion_agent"

_DISCUSSION_SESSION_KEY = "discussion_session_id"

_ROUND_BRANCH = "discussion_round_branch"

_ROUND_SHA = "discussion_round_sha"

_ROUND_OPEN = "discussion_round_open"

_BASE_SHA = "discussion_base_sha"

_LAST_DISCUSSION_AT = "last_discussion_at"

_DISCUSSION_PARK_PREFIX = "discussion_"

_DISCUSSION_RESPONSE = "discussion_response"

_DISCUSSION_COMMITS = "discussion_commits"

_DISCUSSION_DIRTY = "discussion_dirty"

_DISCUSSION_SILENT = "discussion_silent"

_DISCUSSION_STRANDED = "discussion_stranded"

# What a checkout `git status` could not report on parks under, and it is its
# own reason rather than the stranded one because the operator's next move is
# not a reset: nothing was named to reset off, and what has to be found out is
# why the read failed at all.
_DISCUSSION_UNREADABLE = "discussion_unreadable_worktree"

_DISCUSSION_TIMEOUT = "discussion_timeout"

_DISCUSSION_PLAN_PUBLISHED = "discussion_plan_published"

_DISCUSSION_PLAN_INVALID = "discussion_plan_invalid"

_DISCUSSION_PUSH_FAILED = "discussion_push_failed"

# What the reason says while a publication is actually being attempted. It is
# never a message to anybody: every ending of that attempt writes its own reason
# over this one, so it is durable only in the window a crash falls into.
_DISCUSSION_PUBLISHING = "discussion_publishing"

_DISCUSSION_STALE_PUBLISH = "discussion_stale_publication"

_DISCUSSION_PLAN_UNATTRIBUTED = "discussion_plan_unattributed"

# The parks whose comment names a checkout to repair -- with the command to
# repair it with, where there is one to give. A reply arriving into a tree
# still in that state earns no second copy of those instructions; every other
# park does have to say it once. The timeout park is deliberately absent: it
# tells an operator to inspect the worktree without claiming anything is wrong
# with it, which is not the same as reporting the tree as the thing that
# blocks the round. The unreadable park is present on exactly that test -- it
# names no reset target, because the probe that would have found one is the
# thing that failed, but the checkout IS what it reports. The
# failed push is present for the opposite reason to the rest: its commit is a
# valid plan, so the reply that arrives on it retries the publication rather
# than being answered, and repeating the reset instructions under a retry
# would read as the only way out when it is the destructive one.
_REPAIR_PARK_REASONS = frozenset((
    _DISCUSSION_COMMITS,
    _DISCUSSION_DIRTY,
    _DISCUSSION_PLAN_INVALID,
    _DISCUSSION_PLAN_UNATTRIBUTED,
    _DISCUSSION_PUSH_FAILED,
    _DISCUSSION_STALE_PUBLISH,
    _DISCUSSION_STRANDED,
    _DISCUSSION_UNREADABLE,
))


def _parked_by_discussion(state: PinnedState) -> bool:
    """True when THIS stage is the one waiting on a human reply.

    A park written here is the round on the thread the humans are answering, so
    the next tick has nothing to open: it has a reply to look for instead, and
    only a trusted one past the watermark makes it this stage's turn again. A
    park written by any other stage is not: the operator relabeled a parked
    issue into a discussion, and the reply that park is waiting for is one
    nobody is going to send here.
    """
    if not state.get(_AWAITING_HUMAN):
        return False
    park_reason = state.get(_PARK_REASON)
    return str(park_reason or "").startswith(_DISCUSSION_PARK_PREFIX)


def _repair_already_requested(state: PinnedState) -> bool:
    """True when the park on this issue already said how to fix the checkout.

    What it gates is whether a reply into an unrepairable tree is worth a
    comment. Told once, an operator does not need telling again every time
    somebody answers -- and the park written to tell them is itself one of
    these, so the telling stops on its own.
    """
    return str(state.get(_PARK_REASON) or "") in _REPAIR_PARK_REASONS


def _round_in_flight(state: PinnedState) -> bool:
    """True when a round of this stage opened and has not reported yet.

    Read where the park would otherwise answer for it: under a park, a commit
    on the branch is not this stage's on its face, and this is the record that
    says one of its rounds was running when that commit appeared.
    """
    return bool(state.get(_ROUND_OPEN))


def _plan_path(issue_number: int) -> str:
    """The one path a discussion round is allowed to commit, for one issue.

    Spelled once because two owners have to agree on it exactly: the prompt
    that tells the agent where to write the plan, and the check that refuses
    to publish a branch changing anything else. A path the agent was promised
    and a path the diff is compared against that disagree by a character would
    park every plan ever written.

    Named after the issue rather than after the branch or the round, so a
    second discussion on the same issue rewrites the same file and the diff
    against base stays one path -- and so an operator reading the repository
    finds the plan by the issue number they already have.
    """
    return f"plans/issue-{issue_number}.md"


def _plan_published(state: PinnedState) -> bool:
    """True when this stage has already published this issue's plan PR.

    The pair is read rather than either half, because each alone means
    something else. An issue relabeled here from a PR stage arrives carrying a
    `pr_number` that is its dev's, and reading that as a published plan would
    freeze a discussion that has not had a round yet; a plan path with no PR
    beside it is a record no publication ever wrote, since both land in the
    same durable write.

    What it gates is the whole tick: the design is with the humans on a PR
    now, so no round is opened and no agent is spawned. What happens instead
    is that `terminal` hands the tick to `plan_terminal`, which asks GitHub
    what they did with that PR -- the only thing that ends this conversation,
    and the only thing that moves the label off `discussion` without a human's
    hand.
    """
    return bool(state.get(_PLAN_PATH)) and state.get(_PR_NUMBER) is not None
