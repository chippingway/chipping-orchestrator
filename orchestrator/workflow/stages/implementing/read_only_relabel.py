# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a conversation stage's park is checked before an implementing relabel is trusted.

The `question` and `discussion` stages both park with `awaiting_human=True` and
a stage-prefixed reason so their own next tick can pick the conversation back
up. Implementing's resume path cannot read those flags -- they mean nothing to
it -- so a relabel out of either stage has to clear them or refuse, and the two
are handled here together because the hazard is the same: what either agent may
write is narrow and neither stage ships it as dev work. The question agent may
write nothing at all. The discussion agent may commit one file, the plan its
humans confirmed, and only its own stage publishes that -- through a check of
what the branch carries, and onto a PR of the plan alone. Anything else either
of them leaves behind is for an operator to look at, never for this stage to
push.

Which of the two happens is decided by the worktree and the branch, never by
the park reason alone: `relabel_hazard` takes those readings against what
`relabel_evidence` can vouch for, and `relabel_refusal` owns what a
finding costs an operator to clear.

A clean pair means the relabel IS the unblock signal: the flags are dropped and
`last_action_comment_id` is ratcheted past what that agent posted, or the later
validating -> in_review seed would replay it as fresh PR feedback. The round
anchor is retired here rather than discarded -- it becomes
`read_only_baseline_sha`, the floor the dev run that follows is measured
against, since the branch it inherits is already ahead of base.

A published plan asks one more question before any of that, and `plan_reading`
answers it, because between the publication and the relabel the humans have had
that design on a PR: they can correct the Markdown on it, or merge the base
into its branch to make it mergeable, and either leaves the PR on a head this
orchestrator never wrote. So the PR is read before anything is ruled on, and
what it carries now is used twice. The checkout is brought forward onto it -- a
developer handed the commit we published would build on a design its reviewers
have moved past, and push a tip that does not contain the head they approved.
And that head replaces `discussion_plan_sha` in the very write that retires
`discussion_plan_path`, because the path record is what answered the merged-PR
question until now: a later tick with the path gone and the old commit still
recorded would read the humans' own edit as this stage's work and close the
issue as `done` with no developer having run. The baseline then names where the
branch really ended up, which is the anchor again whenever that head could not
be fetched at all.

Reading GitHub before the guard rules is also what makes the move crash-safe.
The branch is anchored ahead of the write that records it, so a tick that dies
in between leaves a tip past the anchor -- and the next one, holding the same
reviewed head, recognizes that tip as certified rather than convicting the
branch of it. A read that fails ends the tick where it happened, writing
nothing, since every decision behind it is durable.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.discussion.state import (
    _PLAN_PATH,
    _PLAN_SHA,
    _PUBLISHING_SHA,
    _ROUND_BRANCH,
    _ROUND_OPEN,
    _ROUND_SHA,
)
from orchestrator.workflow.stages.implementing import (
    plan_reading as _plan_reading,
    relabel_hazard as _relabel_hazard,
    relabel_refusal as _relabel_refusal,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

# The stages whose parks this guard answers for, named by the prefix their
# reasons carry in pinned state. Both are operator-applied conversation
# labels neither of which produces dev work, so an issue can arrive at
# implementing from either one by a human relabel.
_READ_ONLY_PARK_STAGES: tuple[str, ...] = (
    str(WorkflowLabel.QUESTION), str(WorkflowLabel.DISCUSSION),
)


def _parked_read_only_stage(state: PinnedState) -> str | None:
    """Return the conversation stage whose unfinished work this issue carries.

    A park is the ordinary form of it, and the flags are what say so. An
    unfinished ROUND is the other form, and it says so with no flags at all: an
    opening round leaves the issue unparked by design, and a publication's
    marker is written from the disposition of one. So a discussion tick that
    died mid-round -- after the agent committed, or after its plan PR was
    opened -- leaves an issue with `awaiting_human` false and a branch carrying
    the very commits this guard exists to keep out of a dev push.
    """
    if _discussion_in_flight(state):
        return str(WorkflowLabel.DISCUSSION)
    if not state.get(_state._AWAITING_HUMAN):
        return None
    park_reason = state.get(_state._PARK_REASON)
    if not isinstance(park_reason, str):
        return None
    for stage in _READ_ONLY_PARK_STAGES:
        if park_reason.startswith(f"{stage}_"):
            return stage
    return None


def _discussion_in_flight(state: PinnedState) -> bool:
    """True while a discussion round or publication is unfinished here.

    Both records are written BEFORE the thing they describe and retired by the
    disposition that reports it, so an issue still carrying one is an issue
    whose last discussion tick did not get that far. Neither depends on
    `awaiting_human`, which is why reading the park alone lets exactly the
    crashed rounds through -- the ones whose commit is sitting on the branch
    with nothing published, nothing reported, and no park to find it by.
    """
    return bool(state.get(_ROUND_OPEN)) or bool(state.get(_PUBLISHING_SHA))


def _handle_stale_read_only_park(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Clear a stale conversation-stage park left by a relabel to
    `implementing`, or refuse the relabel when it would ship what that stage's
    agent wrote.

    `_handle_question` and `_handle_discussion` park with `awaiting_human=True`
    and `park_reason="<stage>_*"` so their own next tick can pick the
    conversation back up; those flags are opaque to implementing's resume path
    and would mis-fire it. When no such park is present this is a no-op
    returning False.

    The clear must check the actual worktree, NOT just the park reason. Both
    agents write nothing a human has not asked for, but a misbehaving run can
    park as `question_commits` / `discussion_plan_invalid` / `*_dirty` (or a
    `*_timeout` that committed before being killed) with unreviewed code state
    on the per-issue branch. Silently dropping the park would let the fresh-spawn
    branch's recovered-worktree shortcut (`_has_new_commits` -> push) publish
    those commits as if a dev session had authored them -- work no human
    confirmed and no check of the stage that produced it ever passed.

    Returns True when the caller must return this tick: the unsafe relabel was
    re-parked as `<stage>_unsafe_relabel` and pinned state written here.

    Returns False otherwise: either no conversation-stage park is present, or the
    worktree and branch are both clean so the relabel IS the unblock signal --
    the park flags are dropped and `last_action_comment_id` ratcheted past the
    agent's last comment (so the eventual validating->in_review watermark seed
    cannot replay it as fresh PR feedback) before the caller falls through to
    the fresh-spawn path.

    It also returns True, writing nothing at all, when the plan PR this issue
    records could not be read, or when what it carries could not be put on the
    branch. What that PR is on decides both what the developer inherits and what
    the write below records in place of the path record it retires, and guessing
    either is worse than waiting: the next tick asks again from the same durable
    state. Accepting the handoff on a checkout still sitting behind the reviewed
    head is the case that costs something -- the developer would build on a
    design its reviewers replaced, and the ordinary push that followed would
    read their head off the remote as its own lease and overwrite it.
    """
    stage = _parked_read_only_stage(state)
    if stage is None:
        return False
    reviewed = _plan_reading._reviewed_plan(gh, issue, state)
    if reviewed is None:
        return True
    hazard = _relabel_hazard._read_only_relabel_hazard(
        spec, issue, state, reviewed,
    )
    if hazard is not None:
        return _relabel_refusal._refuse_read_only_relabel(
            gh, issue, state, stage, hazard,
        )
    inherited = _plan_reading._inherited_tip(spec, issue, state, reviewed)
    if inherited.pending:
        return True
    _clear_stale_read_only_park(gh, issue, state, reviewed.head, inherited.sha)
    # Written HERE, before the caller reaches the spawn, because accepting the
    # handoff is a durable fact and not a staged one. The tick after it can end
    # without writing pinned state at all -- a mid-run pause or a shutdown
    # interruption drops every staged mutation on purpose -- and if this went
    # with them the next tick would read the park and anchor back, find the
    # dev's commit sitting past that anchor, and convict the developer of a
    # violation it would then ask the operator to reset away.
    gh.write_pinned_state(issue, state)
    return False


def _clear_stale_read_only_park(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    reviewed_sha: str,
    inherited_sha: str | None,
) -> None:
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    # The round anchor is retired here -- the branch is the dev's from now on,
    # so nothing is holding that tip still any more -- but it is handed over
    # rather than dropped. What it certified is exactly what the fresh-spawn
    # path must NOT read as a previous dev run: a discussion held on its PR's
    # branch leaves commits ahead of base, and the recovered-worktree shortcut
    # would skip the implementer and republish them as its work.
    state.set(_state._READ_ONLY_BASELINE_SHA, inherited_sha)
    state.set(_ROUND_BRANCH, None)
    state.set(_ROUND_SHA, None)
    _retire_plan_records(state, reviewed_sha)
    latest = gh.latest_comment_id(issue)
    if isinstance(latest, int):
        prior = state.get(_state._LAST_ACTION_COMMENT_ID)
        if not isinstance(prior, int) or latest > prior:
            state.set(_state._LAST_ACTION_COMMENT_ID, latest)


def _retire_plan_records(state: PinnedState, reviewed_sha: str) -> None:
    """Spend the `discussion` stage's records, and leave the plan's head behind.

    The path record exists to stop that stage acting while the design is with
    the humans on its PR, and the relabel IS them deciding -- left standing, it
    would hold the stage inert for good if an operator ever moved the issue
    back.

    Retiring it is what hands the plan question over to the recorded commit, so
    the head that PR is on NOW is what goes in its place. The humans may have
    amended their own plan on it, and the commit publication recorded would
    then read as somebody's implementation from the next tick on -- closing the
    issue as `done` on their edit, with no developer having run. Both go in the
    one write, or an interruption between them would leave exactly that gap.

    The two mid-flight records go with them: a round or a publication nobody
    finished is one the relabel has just answered another way, and a flag
    outliving it would have that stage claim a commit the dev made.
    """
    if reviewed_sha:
        state.set(_PLAN_SHA, reviewed_sha)
    state.set(_PLAN_PATH, None)
    state.set(_PUBLISHING_SHA, None)
    state.set(_ROUND_OPEN, None)
