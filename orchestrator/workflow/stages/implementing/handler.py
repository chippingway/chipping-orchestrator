# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One implementing tick, in the order its questions have to be asked.

Every check ahead of the spawn is there because running the agent first would
make it unanswerable. A `discussion` this stage's own terminals cannot answer
for comes first of all: an unfinished round or publication is a record written
before the thing it describes, so an issue carrying one has a plan on its
branch and possibly a pull request open for it, and neither is anything a
terminal here may finalize on. A pull request that ENDED, either way, or a
closed issue ends the issue, so all three are read next, before anything
spends tokens. The two pull-request endings come off ONE guarded reading with
the head that tells the `discussion` plan from a delivery: a merge finalizes
`done`, a close nobody merged finalizes `rejected`, and reading the head and
the state apart would classify one snapshot and finalize another. A stale read-only park
(`question_*` or `discussion_*`) has to be cleared or refused before the
fresh-spawn path's recovered-worktree shortcut can publish that agent's commits
as a dev implementation. A spent spawn budget has to answer for itself before
the resume below lifts its park on a reply that pays for nothing, and an
operator's `/orchestrator continue` has to be recognized before drift handling
mistakes the bare command for changed requirements. Only then is a body edit
considered, and only if that does not own the tick does the run get prepared.

After the run the order matters just as much: the interruption and live-pause
refusals both come BEFORE the disposition, and both return without writing
pinned state, so the staged in-memory mutations -- the cleared park, the
advanced watermark, the persisted session -- are dropped and the next process
re-derives the whole tick from what durable state still says.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    drift as _engine_drift,
    guards as _guards,
    retry_budget as _retry_budget,
    terminal_reading as _terminal_reading,
    terminals as _terminals,
    usage as _usage,
)
from orchestrator.workflow.stages.discussion.state import (
    _PLAN_PATH as _DISCUSSION_PLAN_PATH,
    _PLAN_SHA as _DISCUSSION_PLAN_SHA,
)
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    continue_command as _continue_command,
    disposition as _disposition,
    drift as _drift,
    late_recovery as _late_recovery,
    plan_handoff as _plan_handoff,
    read_only_relabel as _read_only_relabel,
    spawn as _spawn,
)
from orchestrator.workflow.stages.implementing.resume_batch import _ReplyBatch
from orchestrator.workflow.stages.implementing.state import (
    _PR_NUMBER,
)

log = logging.getLogger("orchestrator.workflow")


def _recorded_pr_is_the_plan(
    state: PinnedState, head_sha: str | None,
) -> bool:
    """True while the PR this issue records still carries only the plan.

    The `discussion` stage publishes the agreed design as a PR and records its
    number in `pr_number`, so an issue relabeled here can arrive pointing at a
    PR that says what to build rather than a build -- and merging it is a human
    agreeing to the design, which is precisely when they relabel.

    Two records answer it, in the order they stop being true.
    `discussion_plan_path` is the durable one, and it is retired by THIS
    stage's own handoff, which is written before anything is spawned: while it
    stands nothing here has pushed, so the PR is the plan whatever its head
    says now. That distinction is the whole point of asking it first. A human
    correcting the Markdown on the plan PR, or pressing "update branch" before
    merging it, moves that head -- and read as this stage's work, the merge that
    follows would close the issue as `done` and clean up the branch with no
    developer ever having run.

    Past the handoff the commit is what settles it. `discussion_plan_sha` is
    what publication put on that PR, and the PR's head is asked for rather than
    assumed. That is what makes the answer right without depending on a write:
    the head moves the moment this stage pushes onto the same PR -- which is
    exactly when it stops being a plan -- so a tick that pushed and then died
    before persisting anything still leaves a PR that reads as an
    implementation here.

    `head_sha` is the caller's, always, and this owner takes no reading of its
    own. The head is a mutable thing -- a human can push to a plan PR at any
    moment -- so a caller that classified one read and then ACTED on another
    has classified something it did not touch. Fetching here would be exactly
    that: every caller goes on to do something to the pull request it just
    asked about, and a second read is a second moment. Given the head it
    holds, the answer is about that read and there is nothing left to fail.
    """
    if state.get(_PR_NUMBER) is None:
        return False
    if state.get(_DISCUSSION_PLAN_PATH):
        return True
    plan_sha = state.get(_DISCUSSION_PLAN_SHA)
    return bool(plan_sha) and head_sha == plan_sha


def _recorded_pr_holds_the_tick(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """True when the PR this issue records is why nothing else may run.

    Three answers, because the question ahead of the PR terminals has three. A
    PR that is still the `discussion` stage's plan -- by its live record, or
    by the commit that record names -- lets the tick continue but must not
    finalize: closing the issue as `done` on a merged plan would end it
    without a developer ever running, on the strength of a document whose
    content is work still to do. A PR that is something else is
    handed to the terminals, which decide on it as they always have. And a
    PR that could not be read at all ends the tick here, unfinalized and
    unspawned, where the record makes the HEAD the answer: with
    `discussion_plan_sha` standing, a reading that established no head cannot
    tell the plan from a delivery, and neither answer is one to guess at.
    Where no such record stands there is nothing for a head to settle, so a
    failed reading falls through exactly as it does for the stages behind
    this one. Nothing is written either way, so the next tick asks again from
    the same durable state.

    All three answers come off ONE reading, and that is the whole shape of
    this owner. What tells a plan from a delivery is the HEAD, what the
    terminals decide on is the STATE, and both are facts about a pull request
    somebody can move at any moment: read twice, this stage classifies one
    snapshot and ends another -- a plan whose head a human corrected reads as
    an implementation to the first read and merged to the second, and the
    issue is closed `done` on the strength of a design document. So the
    reading is taken here and handed on.

    The live plan record is asked AHEAD of it and costs nothing: while
    `discussion_plan_path` stands nothing here has pushed, so the pull request
    is the plan whatever its head says, and there is no reading worth taking.

    TWO terminals off that one reading, because a pull request ends in two
    ways and this stage carries no arc of its own for either. A merge
    finalizes to `done`. One somebody CLOSED without merging finalizes to
    `rejected`, and both have to be answered here rather than further down:
    everything below reaches the size gate, which would measure the committed
    candidate again and push it -- and with the pull request gone, the push
    would open a second one over work a human has already rejected.
    """
    if _recorded_pr_is_the_plan(state, None):
        return False
    linked = _terminal_reading._linked_pull_request(
        gh, issue, state, "telling a plan from work that has ended",
    )
    if linked.unreadable:
        return bool(state.get(_DISCUSSION_PLAN_SHA))
    if _recorded_pr_is_the_plan(state, linked.head):
        return False
    return _terminals._pr_terminal_stops_the_tick(
        gh, spec, issue, state, linked,
    )


def _unfinished_discussion_holds_the_tick(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Screen a crashed `discussion` before any terminal can answer for it.

    The same guard the preflight runs further down, hoisted ahead of the
    terminals for the one state that cannot wait for it. Both in-flight records
    are written BEFORE the thing they describe and neither depends on
    `awaiting_human`, so a tick that died after the plan commit -- or after the
    pull request it opened -- leaves an unparked issue whose branch carries the
    plan and whose `pr_number` is still whatever it arrived with.

    A relabel onto that state reaches the merged-PR terminal first, and the PR
    it reads is somebody else's: an implementation from a previous cycle, or a
    plan PR from a discussion that ran before this one. Merged, it closes the
    issue as `done`, deletes the branch the unfinished publication is sitting
    on, and leaves the marker standing on a terminal issue nothing will come
    back for. The plan is gone and the pull request it was published to is
    orphaned, on the strength of a merge that had nothing to do with either.

    So the records are read first and answer for the whole tick. What follows
    is the ordinary refusal -- the issue parks as `discussion_unsafe_relabel`
    naming the label that finishes what was started -- or, for a round that
    died before writing anything to the branch, the handoff those records are
    retired by, after which the terminals below run against a state that no
    longer claims an unfinished conversation.
    """
    if not _read_only_relabel._discussion_in_flight(state):
        return False
    return _read_only_relabel._handle_stale_read_only_park(gh, spec, issue, state)


def _implementing_preflight(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Everything asked before the recorded PR can be ruled on, in order.

    The read-only park is asked twice, and exactly one of the two does any
    work: the screen above returns immediately on an issue carrying no
    in-flight discussion record, and the call in `_terminal_or_relabel_holds`
    returns immediately on one that screen has just handed over.

    An accepted handoff the developer has not published on yet is caught up to
    its plan PR between them, ahead of the question that reads that PR: what
    the humans did to it since the handoff decides both what the PR IS and
    where the developer starts, and reading the first against a record their
    own edit moved is what would close the issue on a design.
    """
    if _unfinished_discussion_holds_the_tick(gh, spec, issue, state):
        return True
    if _plan_handoff._reconcile_open_plan_handoff(gh, spec, issue, state):
        return True
    if _recorded_pr_holds_the_tick(gh, spec, issue, state):
        return True
    return _terminal_or_relabel_holds(gh, spec, issue, state)


def _terminal_or_relabel_holds(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """The rest of the preflight: the closed-issue terminal, then the relabel.

    Each owns the tick outright when it answers, so they are asked in the order
    the cheapest irreversible one comes first -- a closed issue ends the issue,
    and there is nothing to hand over on one.

    The size gate's own park is answered ahead of the generic continue, and
    that order is the whole point: what failed there was a reading rather than
    a session, so the bare command has to reach a re-measurement of the commit
    that already exists. Left to the generic handler it would be refused as a
    continue with no guidance on it, and the committed candidate would sit
    parked behind a question nobody could answer.

    The handoff's own park is answered beside it, and quietly: what it refused
    was a checkout that had left the approved commit, so what settles it is
    the checkout coming back rather than anything a human could write. It is
    asked every tick and says nothing until the answer changes.

    A frozen candidate with NO park beside it is reconciled next, and it is
    the crash window the park would otherwise have covered: a tick that
    recorded the pair and died before counting it leaves nothing on the issue
    saying the workflow is waiting, so an ordinary tick on another host would
    rebuild the checkout at base and pay for a second developer over work the
    first one already finished. It is asked before the spawn because that is
    the only place it can be.

    The parked-continue command handler is asked right after this, over the
    tick's one frozen reply batch, and it answers two parks rather than one:
    the spent spawn budget it opens with holds the tick outright, since the
    resume below would otherwise lift that park on any reply at all and start
    a session nothing charges.
    """
    if _terminals._finalize_if_issue_closed(gh, spec, issue, state):
        return True
    if _read_only_relabel._handle_stale_read_only_park(gh, spec, issue, state):
        return True
    if _late_recovery._recovers_a_late_park(gh, spec, issue, state):
        return True
    return _candidate_recovery._holds_unreconciled_candidate(gh, spec, issue, state)


def _handle_detected_implementing_drift(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    batch: _ReplyBatch | None,
) -> bool:
    """Whether a requirements edit owns this tick, judged off the parked read.

    On a parked tick the replies past the watermark are the frozen batch's to
    deliver, so what the park had already read is what the edit is measured
    by (`_ReplyBatch.answered`).
    """
    new_hash = _engine_drift._detect_user_content_change(
        gh, issue, state, answered=None if batch is None else batch.answered,
    )
    return new_hash is not None and _drift._handle_user_content_drift(
        gh, spec, issue, state, new_hash,
    )


def _handle_implementing(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    state = gh.read_pinned_state(issue)
    # A retry-cap park whose sentence was never said, first of all: the park
    # routes this tick to a resume or to nothing, and neither road passes the
    # gate that took it, so a notice left owed here is owed forever.
    _retry_budget._replay_owed_notice(gh, issue, state)
    if _implementing_preflight(gh, spec, issue, state):
        return
    # The one read an awaiting-human tick answers from: the continue
    # classifier, the drift check, and the resume behind them all read this
    # batch, so a reply landing between two of them is in none of them.
    batch = _continue_command._parked_batch(gh, issue, state)
    if _continue_command._handle_parked_continue_command(gh, spec, issue, state, batch):
        return

    # User-content drift: a human edited the issue title/body after the dev
    # session was spawned. `_handle_user_content_drift` persists the new hash
    # and either resumes the locked session against the updated requirements
    # (returning True), parks recovered pre-edit work, or -- when no dev
    # session exists yet -- clears any park and returns False so the fresh-
    # spawn path below picks up the new body via `_build_implement_prompt`.
    if _handle_detected_implementing_drift(gh, spec, issue, state, batch):
        return

    prepared = _spawn._prepare_dev_run(gh, spec, issue, state, batch)
    if prepared is None:
        return

    state.set("last_agent_action_at", _usage._now_iso())

    # Shutdown-sweep interruption: a run the orchestrator killed mid-flight
    # has no trustworthy result, so ignore it and return WITHOUT writing
    # pinned state (the in-memory `awaiting_human=False` / watermark / session
    # mutations in `_prepare_dev_run` are discarded) so the next process
    # retries from durable state. Must precede the disposition below.
    if (
        _guards._ignore_if_interrupted(issue, prepared.agent_result)
        or prepared.paused
    ):
        return

    _disposition._dispose_agent_result(gh, spec, issue, state, prepared)
