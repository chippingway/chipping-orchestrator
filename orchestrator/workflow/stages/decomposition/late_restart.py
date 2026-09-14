# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Admit and resume authorized restarts of fully settled cancelled cycles.

Hard-skip labels defer the attempt. Restart identity is durable before
notice and label effects, and the predecessor is retired only after both
have been applied.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github import (
    client as _client,
    issues as _issues,
    labels as _labels,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    events as _events,
    phases as _late_phases,
    restart as _restart,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import LateFailure, LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_cancellation as _late_cancellation,
    late_restart_effects as _late_restart_effects,
    late_restart_state as _late_restart_state,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")


def _restarts(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this dispatch is one cancelled cycle's restart and nothing else.

    Asked by the dispatcher ahead of the refusal a cancelled cycle otherwise
    earns, because the two would answer the same issue differently in the
    window between the marker and the retirement. A restart applies its target
    label BEFORE it retires the marker, so a tick that crashed in between
    finds an issue wearing `workflow:decomposing` over a record that still
    says cancelled -- and the refusal beside this one would hand that issue
    `rejected` again, undoing the very authorization it is halfway through
    honoring.

    True means the issue was this owner's this tick and reaches no stage
    handler. The transaction below writes the label and the fresh cycle; the
    next tick dispatches the issue on them like any other.

    False is every issue that is not a restart, which is nearly all of them --
    the answer costs the record read the dispatcher had already taken and no
    request at all.
    """
    generation = _late_state.read_late_generation(state)
    if not _restartable(issue, state, label, generation):
        return False
    if _deferred(spec, issue):
        return True
    log.warning(
        "repo=%s issue=#%s carries an authorized restart of its cancelled "
        "cycle %d (%s was taken off); starting a fresh cycle rather than "
        "dispatching it",
        spec.slug, issue.number, generation.cycle_id, WorkflowLabel.REJECTED,
    )
    begun = _begun(gh, issue, state, _late_restart_state._identified(issue, state, generation))
    if _applied(gh, issue, state, begun):
        _late_restart_state._retired(gh, issue, state, begun)
    return True


def _restartable(
    issue: Issue,
    state: _pinned_state.PinnedState,
    label: str | None,
    generation: LateGeneration,
) -> bool:
    """Whether this issue's own record authorizes a fresh cycle right now.

    The cycle has to exist and to be one a close already ended, and then three
    things have to be true of it.

    It has to owe nothing, which is `_unsettled` on the cancellation owner --
    one question over two readings, because neither contains the other. What
    the ending lists counts a pull request this generation names and cannot
    show it ever held, an obligation no ledger entry carries and only a
    human can repair; projecting the fresh cycle over one would delete the
    last thing on the issue pointing at a pull request this orchestrator left
    marked and open. What the domain's settled-ledger answer adds is a child
    receipt and a consumer ledger this binary could not type, and a restart
    that reached its retirement over one of those would be refused there with
    the marker already down and the label already applied. Asking the
    cancellation owner rather than restating its rule is what keeps the two
    guards exactly complementary: the tick that stops here is the tick that
    guard runs its ending on, and no state falls between them.

    The terminal has to be PROVED applied, which the record says and the label
    cannot. `rejected` is what an operator removes to authorize a fresh cycle,
    and an issue they took it off is indistinguishable on its surface from one
    whose workflow label a human stripped while the cleanup was still running,
    and from one whose terminal write GitHub refused. None of those three got
    `rejected`, and restarting any of them would start a cycle on a gesture
    nobody made. So it is the PROOF half of the terminal record that answers
    here -- the receipt a pass writes for a `rejected` it can see on the issue
    -- and not the decision half, which is only an attempt.

    And the gesture itself is read off the issue: an OPEN issue wearing no
    workflow label at all is one an operator reopened and took that terminal
    off, which is the only way a stamped cycle loses it. A closed one is the
    cleanup sweep's, whatever its record says.

    A marker already standing answers the gesture and the stamp for itself,
    whatever label the issue now wears. It is a record only this owner writes,
    and only after both were proved, so an issue carrying one is a restart
    this orchestrator began and owes the rest of.
    """
    if _issues.issue_is_closed(issue):
        return False
    if not generation.is_present or not generation.cancelled:
        return False
    if _late_cancellation._unsettled(generation):
        return False
    if generation.restart_pending:
        return True
    proved = _endings.terminal_confirmed(state, generation.cycle_id)
    return label is None and proved


def _deferred(spec: _config_models.RepoSpec, issue: Issue) -> bool:
    """Whether a control label says now is not the time to restart.

    `backlog` and `paused` park an issue outside the state machine, and every
    step of a restart is a write: a comment, a label, and a pinned comment
    projected onto a cycle that will then spawn an agent. Nothing here has to
    happen before the label comes off -- the authorization is durable on the
    issue's own surface, since the operator's removal of `rejected` is not
    something a later tick can lose.
    """
    skip_label = _labels.hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r over an authorized restart; the fresh "
        "cycle waits for the label to come off",
        spec.slug, issue.number, skip_label,
    )
    return True


def _begun(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> LateGeneration:
    """Make the cycle this restart intends durable before anything acts on it.

    Create-or-keep, and the keeping is the whole point: a marker this owner
    could have written already IS this restart, so a tick re-entering after a
    crash resumes that cycle rather than minting a second one and posting a
    second notice. A record whose marker could not have been written here --
    a pending cycle no audit line was ever issued for, a predecessor naming
    ancestry nothing wrote -- is re-minted from the cycle in hand, which costs
    one notice rather than a fabricated lineage.

    The boundary moves with it. `restarting` is what says this record is
    mid-transaction rather than merely cancelled, and it is safe to write over
    the cancellation's own `cancelling` precisely because nothing is owed: the
    boundary a reclamation reads is kept beside the stamp, and a restart is
    reachable only from a cycle with nothing left to reclaim.

    The record of it rides the write that made the marker true rather than
    every visit that reads it back, so a restart held by a label GitHub keeps
    refusing is one `late_restart` rather than one per tick.
    """
    begun = _restart.begin_restart(
        generation, target=str(_selected_target()),
    )
    if begun == generation:
        return generation
    begun = begun.at_phase(_late_phases.LatePhase.RESTARTING)
    _late_restart_state._persisted(gh, issue, state, begun)
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.RESTART,
            restart_step=_events.LateRestartStep.PENDING,
        ),
        begun,
        stage=stage_name(gh.workflow_label(issue)),
    )
    return begun


def _selected_target() -> WorkflowLabel:
    """The state the current `DECOMPOSE` setting puts a restarted issue in.

    The same choice an unlabeled issue's first pickup makes, and made here
    rather than by reaching that path: pickup mints a pinned comment of its
    own, greets the issue as new, and asks the author allowlist -- none of
    which is what a restart is.
    """
    if config.DECOMPOSE:
        return WorkflowLabel.DECOMPOSING
    return WorkflowLabel.IMPLEMENTING


def _applied(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> bool:
    """Carry out both external halves of the restart, or say one did not.

    The notice comes before the label so a human watching the issue reads why
    it moved before they see it move, and both are idempotent, so the pass a
    failure keeps bringing back costs only the half that is actually still
    owed.

    A refusal from either is reported and returned rather than raised: the
    marker is durable by now, so the next visit resumes exactly here, and the
    only thing missing is an effect GitHub declined. Retiring over it would
    project the fresh cycle onto an issue that was never told and never
    relabelled -- an issue nothing would ever dispatch, since a workflow with
    no label on it is one the next tick greets as new.
    """
    try:
        _late_restart_effects._effects(gh, issue, state, generation)
    except Exception:
        log.exception(
            "issue=#%d could not be restarted onto %r this visit; the marker "
            "stands and the next one resumes at whichever half is still owed",
            issue.number, generation.restart_target,
        )
        _telemetry.emit_late_event(
            gh,
            _events.LateEvent(
                family=_events.LateEventFamily.FAILURE,
                failure=LateFailure.RESTART_FAILED,
            ),
            generation,
            stage=stage_name(gh.workflow_label(issue)),
        )
        return False
    return True
