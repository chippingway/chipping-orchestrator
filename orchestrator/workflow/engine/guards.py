# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished agent run is allowed to leave behind.

Three of these decline a run's outcome and one publishes it, but all four live
in the same window -- after the spawn returns, before the handler's
`gh.write_pinned_state` -- and they share one rule: the handler owns that
write. `_ignore_if_never_invoked`, `_ignore_if_interrupted`, and
`_paused_during_agent_run` say "not this
run" by returning True and letting the caller `return` without writing, so the
in-memory `PinnedState` mutations it already staged are dropped and the next
tick re-derives the run from the state the prior tick left. `_park_awaiting_human`
goes the other way -- it posts the HITL comment, sets `awaiting_human`, forwards
explicit bounded correlation fields to the emitted event and analytics sink, and
ratchets `last_action_comment_id` past it -- or, for a park that follows an
agent run, only as far as `park_watermarks` can walk our own identified
comments -- and still leaves the write to the
caller, so a park composes with whatever else that handler staged rather than
committing ahead of it.

The three refusals answer different questions and none covers the others.
A launch that never became a process is read off the result the agent-run
circuit hands back in place of one. Interruption is read off the result the
shutdown sweep produced. A mid-run
`paused` / `backlog` is visible only on a FRESHLY fetched issue: the dispatcher
screened the hard-skip labels once at tick start, and the handler has been
holding that snapshot for however long the agent ran.

The first two are asked in that order wherever a stage inspects the worktree
before it asks about interruption -- and several do, deliberately. What a
killed run left on disk is the operator's to see; what a launch that never
started left is nothing, so the tree it would be read on says nothing about it.

The correlation vocabulary a park reports beside its reason is declared here
too, and screened here for every road -- including the implementing question
and checkout parks, which own watermark and state writes `_park_awaiting_human`
does not and so emit for themselves. One allow-list is what keeps the two
sinks' payloads bounded and comparable whichever seam wrote them.
"""
from __future__ import annotations

import contextlib
import logging
import math
from typing import Any, NamedTuple

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, park_watermarks as _park_watermarks
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _ignore_if_interrupted(issue: Issue, agent_result: AgentResult) -> bool:
    """True when `agent_result` came from a run the shutdown sweep killed
    mid-flight (SIGTERM/SIGKILL -- `AgentResult.interrupted`).

    Such a run carries no trustworthy outcome: `last_message` is empty or a
    partial transcript chunk and no commit / question / timeout signal can be
    read from it. Dev-resume stage handlers call this BEFORE their
    timeout/question/dirty/push branches and `return` WITHOUT writing pinned
    state on a True result, so durable GitHub state stays exactly as the prior
    tick left it and the next orchestrator process re-runs the resume from
    scratch. Returning quietly here is what keeps the interrupted path from
    posting an agent-question HITL comment, consuming an `awaiting_human`
    park, advancing an action/comment watermark, or interpreting partial
    `last_message` content -- all of which the in-memory `state` mutations the
    caller already made would persist on a normal `write_pinned_state`.

    Logs once at INFO so the interruption is visible without being mistaken
    for a real silence/timeout park.
    """
    if not agent_result.interrupted:
        return False
    log.info(
        "issue=#%d agent run interrupted by shutdown sweep; leaving durable "
        "state untouched for retry by the next process",
        issue.number,
    )
    return True


def _ignore_if_never_invoked(issue: Issue, agent_result: AgentResult) -> bool:
    """True when no process was ever invoked for `agent_result`.

    The answer a launch the agent-run circuit turned away carries
    (`workflow/engine/run_circuit.py`): the lifetime ledger was spent, the
    pinned comment could not be read, or the charge could not be written, and
    nothing was spawned.

    Asked BEFORE any inspection of what a run left behind, which is the one
    place it differs from `_ignore_if_interrupted` below it. Several stages
    read the worktree ahead of that guard on purpose -- a run the shutdown
    sweep killed can have written before it died, and a contaminated tree is
    an operator's to see whether or not the run counted. A launch that never
    started wrote nothing, so a tree dirty for some older reason is not its
    doing, and a park taken in its name would replace the durable one the
    circuit had already recorded with a reason about a process that never
    existed.

    Callers `return` without writing pinned state, exactly as they do for an
    interruption. Nothing is logged loudly here: the refusal was already
    recorded where it was decided, and this is that decision arriving.
    """
    if agent_result.invoked:
        return False
    log.debug(
        "issue=#%d agent launch was refused before any process started; "
        "leaving durable state to whatever refused it",
        issue.number,
    )
    return True


def _paused_during_agent_run(gh: GitHubClient, issue: Issue) -> bool:
    """True when a hard-skip control label (`paused` / `backlog`) was applied
    to `issue` while an agent run was in flight.

    The dispatcher and `_process_issue` read the issue's labels once, at tick
    start, and skip a hard-skipped issue before any handler runs. But a stage
    that spawns an agent holds that label snapshot for the whole run -- minutes,
    typically -- so an operator who applies `paused` mid-run would otherwise not
    take effect until the run's results were already published: PR opened, label
    flipped, HITL park posted, action watermark consumed, pinned state advanced.

    Stage handlers call this right after an agent run returns, BEFORE any of
    that disposition, and `return` WITHOUT writing pinned state on a True result
    -- mirroring `_ignore_if_interrupted`. Durable GitHub state is left exactly
    as the prior tick had it and the agent's committed work stays on the branch,
    so once the operator removes the label the next tick republishes it through
    the normal recovered-worktree path.

    The label is read from a FRESHLY fetched issue (`gh.get_issue`), never the
    stale handler `issue` whose labels were snapshotted before the run -- the
    whole point is to catch a label applied mid-run. A fetch failure returns
    False (publish as before): the guard is an additive safety net and must not
    itself strand a run that would otherwise have completed.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:  # noqa: BLE001 - the guard is additive and must not strand a finished run
        log.debug(
            "issue=#%d not retrievable for post-agent pause check; proceeding",
            issue.number,
        )
        return False
    skip_label = hard_skip_control_label(fresh)
    if skip_label is None:
        return False
    log.info(
        "issue=#%d acquired %r during the agent run; leaving durable state "
        "untouched until the label is removed",
        issue.number, skip_label,
    )
    return True


# The roads a developer run reaches a self-emitting park from: the implementing
# question park and the two checkout refusals, each of which several stages
# hand a run to. They are the values the `route` field below may take, spelled
# once here so a literal cannot drift between the stages that name one.
# A fresh or resumed developer run under `workflow:implementing`.
_ROUTE_DEV_RUN = "dev_run"
# A resume the issue body changing mid-flight earned, from whichever stage was
# holding the issue when the edit landed.
_ROUTE_DEV_DRIFT_RESUME = "dev_drift_resume"
# A fix round: reviewer feedback, or a human's reply asking for one.
_ROUTE_DEV_FIX = "dev_fix"
# The single documentation pass before the merge gate.
_ROUTE_DOCS_PASS = "docs_pass"
# A dev resume inside the rebase-conflict loop.
_ROUTE_CONFLICT_RESUME = "conflict_resume"
# The shared seam every committed candidate publishes through.
_ROUTE_CANDIDATE_PUBLICATION = "candidate_publication"


class _ParkedRun(NamedTuple):
    """A finished run handed to a park, and the road it came off.

    The route travels because nothing downstream can re-derive it: the workflow
    label a park's record already reports says which stage held the issue, and
    a single stage reaches the same park from a fresh run, a body-edit resume,
    a fix round, a docs pass, a rebase resume, and the publication seam alike.
    It lives out here with the vocabulary rather than in a stage, because four
    stage packages hand one of these in.

    `conflict_round` rides here rather than being read back out of pinned state
    because the rebase loop counts that field on its success path alone: a
    round that parks leaves the durable counter on the round BEFORE the one
    that just ran, so the caller that handed the resume its number is the only
    place the round a park belongs to is known. None everywhere else, which
    both sinks drop.
    """

    agent_result: AgentResult
    route: str
    conflict_round: int | None = None


ALLOWED_CORRELATION_FIELDS: frozenset[str] = frozenset((
    "route",
    "agent_role",
    "backend",
    "agent_spec",
    "session_id",
    "resume_session_id",
    "review_round",
    "retry_count",
    "pr_number",
    "conflict_round",
    "dirty_files",
    "exit_code",
    "timed_out",
    "sha",
    "reservation_id",
))


def _screened_correlation(correlation: dict[str, Any]) -> dict[str, Any]:
    """Return `correlation` once every field in it is one of the above.

    The allow-list is what keeps a `park_awaiting_human` record bounded. Both
    sinks carry whatever a park hands them, so a field nobody declared would
    reach two durable logs unreviewed -- and a free-form one would carry an
    agent transcript into both. Raising rather than dropping is what corrects
    the caller before anything is posted or emitted.

    The direct emitters screen through here rather than repeating the list.
    The implementing question and checkout parks cannot hand their notice to
    `_park_awaiting_human` below -- each owns a watermark read and durable
    state writes it does not -- so one vocabulary covering both roads is what
    makes their records comparable to a funnelled one.
    """
    unsupported = set(correlation) - ALLOWED_CORRELATION_FIELDS
    if unsupported:
        raise TypeError(
            f"park_awaiting_human received unsupported correlation field(s): "
            f"{sorted(unsupported)}"
        )
    return correlation


def _safe_int(candidate: object) -> int | None:
    """Strictly normalize candidate to an int fail-open, dropping non-integers."""
    if isinstance(candidate, bool) or candidate is None:
        return None
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, float) and math.isfinite(candidate) and candidate.is_integer():
        return int(candidate)
    if isinstance(candidate, str):
        with contextlib.suppress(ValueError, OverflowError):
            return int(candidate)
    return None


def _park_awaiting_human(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    message: str,
    **correlation: Any,
) -> None:
    """Post `message` and mark the issue as awaiting a human reply.

    Caller is responsible for `gh.write_pinned_state` afterwards (mirrors the
    existing _on_question / _on_dirty_worktree contract). Clears any stale
    `park_reason` -- a transient park (e.g. in_review `unmergeable`)
    followed by a follow-up question/timeout park would otherwise leave
    the transient reason behind. Callers that re-park for a transient
    reason re-set `park_reason` immediately after this call.

    `reason` is recorded only in the emitted `park_awaiting_human` audit
    event; the durable `park_reason` field in pinned state is still cleared
    here (callers that need a transient reason re-set it themselves -- see
    above), so passing a reason does not change observable behavior.
    Explicit bounded correlation fields passed via keyword arguments
    (`correlation`) forward to the emitted event and fan out to the analytics
    sink, sharing the same correlation payload across audit and analytics.
    They go through `_screened_correlation` above, so an unsupported field
    raises `TypeError` before anything is posted or emitted -- and so a park
    that emits for itself carries the same vocabulary this one does.

    The watermark is the id of the notice this call POSTED, not the id the
    thread happens to end on afterwards. The two differ in exactly one case
    and it is the one that matters: a human replying between the post and this
    write. Read off the thread, their reply becomes the watermark and is
    skipped for good -- on a park whose whole point is waiting for a reply,
    that is the answer being thrown away by the question. Read off the comment
    we wrote, their reply is still there for the next poll.

    A post this call could not identify moves the mark nowhere. What a park
    may record itself as having read past is a comment actually posted and
    identified, and reading the tip for one nothing named would cross whatever
    else stands on the thread -- while our own unrecorded sentence is refused
    as forged by every reading that builds a prompt, its marker carrying no
    ledger entry to vouch for it.

    `bounded=True` asks for the other answer, and every park that follows an
    agent RUN asks for it. The notice-id answer above is right for a refusal
    decided between two of one tick's own steps and wrong after minutes of
    somebody's compute: there the notice lands above whatever a human wrote
    while the agent was out, and crossing them is the answer being thrown away
    by the question. So a bounded park records the thread read only as far as
    `park_watermarks` can walk it -- through our own identified comments and no
    further. It is popped like `reason` rather than admitted as a correlation
    field: it decides a WRITE, so it belongs to neither the event nor the
    analytics payload the rest of this blob is.
    """
    reason = correlation.pop("reason", None)
    bounded = correlation.pop("bounded", False)
    screened = _screened_correlation(correlation)
    said_before = _comments._orchestrator_ids(state)
    posted = _comments._post_issue_comment(gh, issue, state, message)
    state.set("awaiting_human", True)
    state.set("park_reason", None)
    if bounded:
        _park_watermarks._stamp_read_this_far(gh, issue, state, said_before)
    else:
        _park_watermarks._stamp_the_notice(state, posted)
    # Read the label AFTER the comment post and state writes so the
    # captured stage reflects the handler that drove the park (the label
    # itself is unchanged by this call -- callers relabel only after the
    # `write_pinned_state` they do next).
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        reason=reason,
        **screened,
    )
