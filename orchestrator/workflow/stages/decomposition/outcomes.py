# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Run settlement and manifest outcomes for a finished decomposer reply.

The pause and timeout settlement runs before the caller's worktree check.
It leaves a live pause intact, and a run whose accounting is unresolved with
it. The run's usage is not settled here: every exit, an interrupted or
timed-out one included, was accounted as it returned, at the tracked boundary
(`usage._run_agent_tracked`), and a decomposition held here buys no replay by
it. After the caller proves the read-only checkout, the reply reaches the
manifest dispositions below.

A reply either carries a usable manifest or it does not, and both halves of
that split are dispositions the issue leaves this tick on. `single` posts the
sizing rationale and the context the decomposer already gathered, then hands
the issue to `ready` -- the comment rather than a body edit, because rewriting
the body would move the user-content hash and re-decompose the issue on the
next tick -- clearing any rationale an earlier split recorded, since the
decision supersedes that split. `split` creates the children and leaves the
parent waiting on them.

A `split` is usable only once every child states its `depends_on` list, since
a child read as having no prerequisites is released at once. One that leaves
the list missing or null is a malformed manifest naming the child and the
field, rejected before the split writes a marker or creates a child.

A malformed manifest -- the parser's concrete error over a completed,
accounted, read-only run -- first earns one correction
(`correction_road.requests`): the same session resumed under its pinned
command with the exact error and the whole output contract, its run disposed
of exactly as this one is, on the same plan, so its answer passes every hold,
park, and check here and its usable manifest reaches the ordinary `single` or
`split` handling once its attempt is spent over an issue that still stands
(`correction_settlement.clears`). It earns no correction of its own.

Everything else parks awaiting a human, and the park distinguishes two cases
the parse cannot: a malformed manifest is the agent getting the contract wrong
-- one that earned no correction, or a correction's own, whose park quotes the
latest error and rejected answer -- while no manifest at all is the agent
asking a question -- or saying nothing, which is a backend failure wearing a
question's clothes. Only the silent case carries stderr diagnostics, because
an operator answering a real question does not need to read subprocess noise
to do it. All failed-run parks (timeout, dirty checkout, silent, question, and
invalid manifest) enrich the shared park funnel with typed correlation fields
(`agent_role`, `session_id`, `retry_count`), and one taken over a correction
attempt ends on its receipt (`correction_notices`) and exhausts the attempt
only once it has landed.

A run handed a tick's frozen read -- the resume of the parked session, or the
fresh decomposition an edit to it or a continuation buys -- settles what it was
handed past the holds and ahead of any of those parks, and a held run consumes
none.
Every park behind it is bounded by the scope its caller opens
(`run._process_decomposer_run`): it walks the reply boundary from what that
settlement recorded through our own notice and no further, since the notice
lands above anything a human wrote while the decomposer was out, which is the
next resume's to deliver.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    agent_diagnostics as _agent_diagnostics,
    comments as _comments,
    decomposition_prompts as _decomposition_prompts,
    guards as _guards,
    messages as _messages,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    correction_notices as _correction_notices,
    correction_records as _correction_records,
    correction_road as _correction_road,
    correction_settlement as _correction_settlement,
    manifest as _manifest,
    split as _split,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# What a question or silence asks of the correction road: nothing.
_NO_CORRECTION = _correction_road.CorrectionAsk()

# What a correction's own invalid manifest adds to the park it takes.
_CORRECTED = " after its one automatic correction"

# The role every park here is attributed to, and the budget count it correlates with.
_ROLE = "decomposer"
_RETRY_COUNT = "retry_count"


def _park_unparsed_manifest(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run_plan: _DecomposerRunPlan,
    given_up: _correction_records.CorrectionAttempt | None = None,
) -> None:
    """Park awaiting human when the decomposer produced no usable manifest.

    Either a malformed manifest (the parser names an error) OR no manifest at
    all (question / silence). Both park; the resume on the next comment runs
    through the awaiting_human branch of `_handle_decomposing`. Forwards typed
    correlation fields (`agent_role`, `session_id`, `retry_count`) through the
    shared park funnel.

    A malformed manifest reaches here only where it earned no correction --
    none was armed or launched for it -- or is itself a correction's answer.
    A park over an attempt -- the correction's own, or one armed with no
    launch granted (`given_up`) -- ends on that attempt's receipt
    (`correction_notices`), and the attempt is exhausted only once the park
    has landed (`correction_settlement`), so a lost exhaustion leaves a park
    standing over a pending attempt rather than an attempt spent beside no
    park.
    """
    decomposer_result = run_plan.agent_result
    _parsed, error = _manifest._parse_manifest(decomposer_result.last_message or "")
    message, reason = _unparsed_notice(issue, run_plan, error)
    _guards._park_awaiting_human(
        gh, issue, state, _correction_notices.receipted(message, run_plan.correction or given_up),
        reason=reason,
        agent_role=_ROLE,
        session_id=decomposer_result.session_id,
        retry_count=_guards._safe_int(state.get(_RETRY_COUNT)),
    )
    gh.write_pinned_state(issue, state)
    _correction_settlement.spends_behind_park(gh, issue, state, run_plan, given_up)


def _unparsed_notice(issue: Issue, run_plan: _DecomposerRunPlan, error: str | None) -> tuple[str, str]:
    """What the park over an answer with no usable manifest says, and the reason its event names.

    A malformed manifest quotes the parser's `error` and the rejected answer
    -- a correction's own says it was that answer, so the human reads the
    latest error and the latest rejected manifest, the session it ran in left
    pinned for their reply to resume. No manifest at all is the decomposer's
    question, or its silence, and only the silent case carries stderr
    diagnostics, because an operator answering a real question does not need
    to read subprocess noise to do it.
    """
    decomposer_result = run_plan.agent_result
    last_msg = (decomposer_result.last_message or "").strip()
    if error is not None:
        corrected = "" if run_plan.correction is None else _CORRECTED
        invalid = (
            f"{config.HITL_MENTIONS} decomposer manifest invalid "
            f"({error}){corrected}; manual adjudication needed.\n\n"
            f"_Last decomposer message:_\n\n{_messages._as_blockquote(last_msg)}"
        )
        return invalid, "decomposer_invalid_manifest"
    if last_msg:
        return (
            f"{config.HITL_MENTIONS} decomposer needs your input to proceed:\n\n{_messages._as_blockquote(last_msg)}",
            "decomposer_question",
        )
    return _silent_notice(issue, decomposer_result), "decomposer_silent"


def _silent_notice(issue: Issue, decomposer_result: AgentResult) -> str:
    """What the park over a decomposer that said nothing says: its stderr tail and exit code, logged as well."""
    log.warning(
        "issue=#%s decomposer produced no final message; "
        "exit_code=%d timed_out=%s stderr_tail=%r",
        issue.number,
        decomposer_result.exit_code,
        decomposer_result.timed_out,
        _agent_diagnostics._stderr_log_tail(decomposer_result),
    )
    quoted = _messages._as_blockquote("(decomposer produced no final message)")
    diag = _agent_diagnostics._format_stderr_diagnostics(decomposer_result, "Decomposer")
    return f"{config.HITL_MENTIONS} decomposer needs your input to proceed:\n\n{quoted}{diag}"


def _park_dirty_worktree(gh: GitHubClient, issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan) -> None:
    """Park a run that left commits or edits in its read-only checkout, the checkout kept by the caller.

    The caller decides the cleanup policy before calling, since the park's
    own writes can raise. A correction's attempt is exhausted behind the park.
    """
    _guards._park_awaiting_human(
        gh, issue, state,
        _correction_notices.receipted(
            f"{config.HITL_MENTIONS} decomposer left commits or "
            "uncommitted changes in the worktree, but it must be "
            "read-only. Reset the worktree before resuming.",
            run_plan.correction,
        ),
        reason="decomposer_dirty",
        agent_role=_ROLE,
        session_id=run_plan.agent_result.session_id,
        retry_count=_guards._safe_int(state.get(_RETRY_COUNT)),
    )
    gh.write_pinned_state(issue, state)
    _correction_settlement.spends_behind_park(gh, issue, state, run_plan)


def _finalize_single_decision(
    gh: GitHubClient, issue: Issue, state: PinnedState, parsed: dict,
) -> None:
    """Finalize a `single` manifest: post the rationale and flip to `ready`.

    Surface the decomposer's rationale AND the context it already gathered
    (affected files, implementation notes) so the develop agent that picks
    this up in `implementing` starts from that groundwork instead of
    re-deriving it. The builder tolerates missing / malformed optional
    fields -- the single decision is already valid, so no cosmetic field
    should park it.

    The decision supersedes any split this issue recorded before it, so the
    rationale that split kept is cleared: the implementation `ready` leads
    to would otherwise read back residual scope no split owes it. Cleared in
    a write of its own while the issue still wears `decomposing`, because
    the flip sets the label before it writes and a pass that died between
    the two would leave that account standing on a `ready` issue. An issue
    recording none costs no write here.
    """
    _comments._post_issue_comment(
        gh, issue, state,
        _decomposition_prompts._build_single_decision_comment(parsed),
    )
    state.set("decomposed_at", _usage._now_iso())
    if state.get(_state._SPLIT_RATIONALE) is not None:
        state.set(_state._SPLIT_RATIONALE, None)
        gh.write_pinned_state(issue, state)
    gh.set_workflow_label(issue, WorkflowLabel.READY)
    gh.write_pinned_state(issue, state)


def _dispatch_decomposer_manifest(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run_plan: _DecomposerRunPlan,
) -> bool:
    """Parse the decomposer's final message and route on the outcome; whether a correction's run now needs disposing.

    Parks awaiting human on an invalid / silent / question manifest,
    finalizes a `single` decision to `ready`, or creates the `split`
    children and finalizes the parent to `blocked` / `umbrella`.

    A manifest the parser refuses with a concrete error first asks for the
    one correction it may earn (`correction_road.requests`): where that
    launches, its run is laid onto `run_plan` and True asks the caller to
    dispose of it as it disposed of this one, so its answer passes through
    every check this one did. A tick the request holds ends here, and only a
    request that earned nothing parks. A correction's own usable manifest is
    acted on only once its attempt is spent over an issue that still stands
    (`correction_settlement.clears`).
    """
    parsed, error = _manifest._parse_manifest(run_plan.agent_result.last_message or "")

    if parsed is None:
        asked = _NO_CORRECTION
        if error is not None:
            asked = _correction_road.requests(gh, spec, issue, state, run_plan)
        if asked.launched is not None:
            run_plan.corrected_by(asked.attempt, asked.launched)
            return True
        if not asked.held:
            _park_unparsed_manifest(gh, issue, state, run_plan, asked.attempt)
        return False

    if not _correction_settlement.clears(gh, issue, state, run_plan):
        return False

    if parsed["decision"] == "single":
        _finalize_single_decision(gh, issue, state, parsed)
        return False

    # decision == "split".
    split_plan = _split._create_child_issues(gh, spec, issue, state, parsed)
    if split_plan is not None:
        _split._finalize_split(gh, spec, issue, state, split_plan)
    return False


def _settle_decomposer_run(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run_plan: _DecomposerRunPlan,
) -> bool:
    """Stamp this run and park on a timeout; hold on a live pause or unresolved accounting.

    Returns True when the caller must return (held or timed out), False
    to continue to the dirty-worktree check and manifest dispatch. None of
    these paths preserve the decompose worktree: the caller's `finally`
    tears it down on return. The read-only dirty/commits park (which DOES
    preserve the worktree, `_park_dirty_worktree`) is taken by the caller
    once it has set `keep_worktree`, so the policy is decided BEFORE the
    park's side effects run. Timeout parks forward typed correlation fields
    (`agent_role`, `session_id`, `retry_count`) through the shared park
    funnel. A held correction leaves its attempt pending with its start on
    the ledgers, for the next tick to give up behind a human park
    (`correction_reconcile`); a timed-out one is spent behind its park.

    What a run was handed off a tick's frozen read is settled here,
    past the holds and ahead of every park the run can earn
    (`DecomposerReplies.settle`): a held run consumes none of it, while a
    timeout, a question, a dirty worktree, an invalid manifest, and a split's
    own park all answer a prompt the decomposer read. Settled first, the reply
    boundary stands at the newest reply delivered, so the bounded park behind
    it walks from there through its own notice and stops at a comment written
    while the run was out.
    """
    decomposer_result = run_plan.agent_result
    # Live pause: an operator applied `paused` / `backlog` while the
    # decomposer ran (fresh spawn or awaiting-human resume). Dispatch only
    # saw the pre-run labels, so re-check a freshly fetched issue and return
    # WITHOUT parking on timeout, creating child issues, relabeling, or
    # writing pinned state -- durable GitHub state stays exactly as the prior
    # tick left it, save the accounting the tracked boundary already landed,
    # and the next tick re-runs the decomposer once the label is removed. A
    # run whose accounting is unresolved is held the same way. The read-only
    # decompose worktree is torn down by the caller's `finally` as on any
    # normal exit and recreated on the re-run.
    if decomposer_result.unaccounted or _guards._paused_during_agent_run(gh, issue):
        return True

    if run_plan.replies is not None:
        run_plan.replies.settle(state, decomposer_result)
    state.set("last_agent_action_at", _usage._now_iso())

    if decomposer_result.timed_out:
        _guards._park_awaiting_human(
            gh, issue, state,
            _correction_notices.receipted(
                f"{config.HITL_MENTIONS} decomposer timed out after "
                f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
                run_plan.correction,
            ),
            reason="decomposer_timeout",
            agent_role=_ROLE,
            session_id=decomposer_result.session_id,
            retry_count=_guards._safe_int(state.get(_RETRY_COUNT)),
        )
        gh.write_pinned_state(issue, state)
        _correction_settlement.spends_behind_park(gh, issue, state, run_plan)
        return True
    return False
