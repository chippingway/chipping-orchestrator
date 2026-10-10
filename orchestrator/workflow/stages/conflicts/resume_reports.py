# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a resume under this stage hands back, carried into the report transaction.

A body edit that lands while the pull request is being rebased resumes the
developer over a pull request that is already open, and that session hands
back a report as well as, perhaps, a commit: a rebase it ran itself, the change
the edit asked for, or both. The report is the reviewer's only account of that
work, and the session is gone once the tick moves on -- so it is held to the
contract both review stages hold their own drift resumes to, through the same
disposition (`validating/drift_outcomes.py`) named with this stage's route. It
is recorded on the pinned comment before the size gate reads the candidate,
stamped with the requirements revision the resume's own prompt was cut from,
bound only to the publication the code-publication receipt proves, and settled
before any reviewer reads the head. What the run hands back is the report that
gets published: no developer is asked to write it again, and no human is asked
to restart it.

The publication goes down beside the report (`resume_records`): the head the
push is leased against, the commit it sends, and the pull request. A rebase the
developer ran diverges the branch from the head it replaced, so a tick that
dies between the record and the push comes back to a checkout the divergence
guard would otherwise park as somebody else's -- the record is what tells it
the commits a force-push drops are the ones that resume replaced.

A commit is this stage's round, and the report is bound behind it. The round is
counted and the label handed to `validating` first, through the tail every
pushed round shares, and the binding follows the write that tail makes. A
process ending between the two leaves the report recorded and owed, which the
review hold binds and settles before a reviewer runs. A body edit's round
records no report debt, since its commit is the developer's own answer to the
edit and the report describing it is the one recorded here.

A report with no commit goes onto the head the pull request already carries,
which a rebase this stage or an earlier resume has already published, and the
issue stays here exactly as it would on an `ACK:`: the next tick finds the
branch on its base, or rebases it, and hands it on.

The reply that answers a park this road left with a report still owed -- a run
that committed and wrote none, a report no record could carry, a push that did
not land behind a recorded one -- is the rest of the same road rather than a
conflict resolution. The resolution road reads no report at all, so a reply
taken down it would push the commit undescribed and park the report it wrote
as a question. Its publication is leased against the head the pull request
stood on before the run, which the divergence guard has admitted, so a rebase
the first run left goes out under the report the reply writes even where the
reply commits nothing more. And it is resumed on the frozen drift prompt, as
the edit's own resume was: the issue and its conversation, the reply among it
and any edit made since, quoted off one read whose record stamps the report and
is settled once the run is back -- every reply in it whole, and marked read by
that settlement rather than ahead of the read. A rotated or poisoned session's fresh spawn is
re-grounded with that same frozen text, so the stamp is what the run was given
whichever way it was launched. A bare `/orchestrator continue` retrying such a
run's timeout is out of that read, with the neutral retry prompt leading it.

A report so recorded and not yet settled is settled as soon as the next tick
has placed the branch and answered any body edit, ahead of the reply wait and
the cap (`_holds_the_saved_report`), so a report-only result whose binding was
cut short is never stranded behind a park, nor a later edit behind it.

Either run that comes back with the rebase still mid-flight records nothing and
pushes nothing: it parks as the resolution funnel parks it, a timeout read
first there as it is here, so the session it killed parks as a timeout that
`/orchestrator continue` retries. And a report that
is recorded but not yet settled -- one a crash left ahead of its push, carried
out since by the recovered push -- is settled before the rebase this stage
makes of the head it is about (`_holds_the_rewrite`), since a report binds to
whatever head the receipt names when it settles. The per-tick base refresh,
which runs ahead of every handler, holds still for the same records
(`git/base_sync/frozen.py`), so no crash between a publication and its
report's settlement hands the report a head somebody else rewrote.
"""
from __future__ import annotations

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    outcomes as _outcomes,
    resume_records as _resume_records,
    state as _state,
    transitions as _transitions,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
    parks as _dev_parks,
)
from orchestrator.workflow.stages.validating import (
    drift_outcomes as _drift_outcomes,
    drift_reports as _drift_reports,
    report_hold as _report_hold,
    report_settlement as _report_settlement,
    state as _validating_state,
)
from orchestrator.workflow.state import WorkflowLabel

# What a round a body-edit resume finished is recorded as, in the audit event
# and in the receipt a hold leaves for the tick that resumes behind it.
_DRIFT_RESOLVED = "drift_resolved"


def _owes_a_report(state: PinnedState) -> bool:
    """Whether the park a reply is about to answer left this issue owing a report.

    Read before the run, since the resume clears the park the debt may be
    standing as.
    """
    return _report_delivery.owes_a_report(state)


def _answers_the_reply(
    ctx: _models._ConflictContext,
    run: _models._ConflictResumeRun,
    before_sha: str,
    lease: str,
) -> None:
    """Finish a report-owed park with the reply's run, as the body edit's resume would have.

    The run was resumed on the frozen drift prompt, and its report is stamped
    with that record's revision: the issue and conversation as that one read
    gave them, which is what the run was handed whether its session resumed
    or a fresh spawn was re-grounded on the same frozen text. A launch the run
    circuit turned away read no reply, and parks nothing over the park this
    issue is already waiting under.
    """
    if _guards._ignore_if_never_invoked(ctx.issue, run.dev_result):
        return
    _disposes(ctx, run, before_sha, run.delivered.requirements_revision, lease)


def _disposes(
    ctx: _models._ConflictContext,
    run: _models._ConflictResumeRun,
    before_sha: str,
    revision: str,
    lease: str,
) -> None:
    """Publish what a resume left under the report it wrote, and hand it on.

    `revision` is the requirements revision the run was handed, which both
    callers pass as `run.delivered.requirements_revision`: the record of the
    frozen drift prompt the run was resumed on, for a body edit and for the
    reply that finishes its park alike. `lease` is the head the publication
    replaces, which this caller proved: the head a body edit's resume began at,
    in sync with its remote, or the head the pull request stood on before a
    reply's run, behind the divergence guard. It stays the lease whatever the
    remote reads as afterwards (`dev_fix._replaced_head`), so a pull request
    somebody moved while the run was out refuses the push rather than being
    adopted as the head it replaces. The head the run left is read
    once and travels to all three things that have to agree about it: the
    candidate the gate measures and pushes, the receipt a hold leaves for the
    tick that resumes behind it, and the SHA the round is counted under. A run
    that left it where `lease` stands committed nothing, and the report it
    saves records that head in the same write, over the record of any earlier
    candidate. Whichever it is, the record holds that report to its head for
    as long as the report is unbound.

    The round rides the gate's own durable write as well, for the exit where
    the tail below never runs: a held candidate is relabelled to the
    adjudication, and the resumed tick reads the published commit as a branch
    already standing on its base -- the no-op flip, which resolves nothing and
    stamps no `last_conflict_resolved_at`.

    A shutdown-killed run writes nothing at all, so the next process finds the
    park, or the edit, exactly as this tick did. A run that left the rebase
    mid-flight parks as the resolution funnel parks it, ahead of the report
    and the push alike: a head that moved during an unfinished rebase is no
    branch a report may describe or a push may send. A timeout reads ahead of
    that, as it does in the funnel: the shared disposition parks it as the
    session failure it is, which `/orchestrator continue` retries, where the
    unfinished rebase would refuse the command for an answer only a human can
    give. A report from a run that did not finish, or that left a head nothing
    could read, is refused before it is recorded (`_refuses_the_report`).
    """
    if _guards._ignore_if_interrupted(ctx.issue, run.dev_result):
        return
    if not run.dev_result.timed_out and _outcomes._parks_an_unfinished_rebase(ctx, run):
        return
    after_sha = _verification_probes._head_sha(run.worktree)
    if _drift_reports._reports(run.dev_result) and _refuses_the_report(ctx, run, before_sha, after_sha):
        return
    pr_number = ctx.state.get("pr_number")
    _resume_records._stages_the_candidate(ctx.state, lease, after_sha, pr_number)
    alone = _resume_records._saved_by_a_report_alone(ctx.state, lease, after_sha, pr_number)
    outcome = _drift_outcomes._post_user_content_change_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree,
        run.dev_result, before_sha,
        after_sha=after_sha,
        published_head=lease,
        spends=_transitions._settles_the_held_round(_DRIFT_RESOLVED, after_sha),
        handed=_records.HandedRun(
            WorkflowLabel.RESOLVING_CONFLICT, revision,
            retires=alone,
        ),
    )
    if outcome == _validating_state._OUTCOME_PUSHED:
        # Pushed branch diff -> hand straight back to validating; the single
        # docs pass runs after final reviewer approval.
        _transitions._hand_resolved_round_to_validating(
            ctx, int(ctx.state.get(_state._CONFLICT_ROUND) or 0), pr_number,
            outcome=_DRIFT_RESOLVED,
            sha=after_sha,
        )
        label = WorkflowLabel.VALIDATING
    else:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        label = WorkflowLabel.RESOLVING_CONFLICT
    # Bound only once the round and its write are behind it, so no tick finds
    # a settled report beside a round nothing has counted.
    if outcome in _validating_state._REPORTING_OUTCOMES:
        _report_settlement._settles_the_report(
            ctx.gh, ctx.spec, ctx.issue, ctx.state, label,
        )


def _refuses_the_report(
    ctx: _models._ConflictContext,
    run: _models._ConflictResumeRun,
    before_sha: str,
    after_sha: str,
) -> bool:
    """Park a report no record may hold; True where it parked.

    A run that left a tool step running did not finish, whatever its last
    message says, so its report describes work still in flight: it parks as
    the execution failure the question road parks it as for a run that
    reports nothing, and no report is recorded -- neither one alone over the
    head the pull request carries, nor one ahead of a commit the run left.
    A run whose head nobody could read is refused by the record's own owner
    (`resume_records._refuses_an_unread_head`), since no record could hold
    its report to the commit it describes.
    """
    if run.dev_result.unfinished_steps:
        _dev_parks._on_question(ctx.gh, ctx.issue, ctx.state, _guards._ParkedRun(
            run.dev_result, _guards._ROUTE_DEV_DRIFT_RESUME, before_sha=before_sha,
        ))
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return True
    return _resume_records._refuses_an_unread_head(ctx, after_sha)


def _holds_the_saved_report(ctx: _models._ConflictContext) -> bool:
    """Settle a saved report of the head the pull request carries; True where it is still owed.

    Asked once the branch is placed in sync with its remote and any body edit
    has been answered, ahead of the reply wait and the cap. A report this
    issue recorded about the head the pull request already carries -- a
    report-only result, its binding cut short -- is owed whatever else this
    stage is waiting on: behind the cap it would park `conflict_cap` over it
    for good, and behind a reply wait it would wait on a human nobody asked
    about it, with the base refresh frozen on its records all the while. So it
    is settled first, through the same guards the hold ahead of a rebase takes.

    Behind the edit, though. A report the requirements have since moved past
    is one the reconciliation defers for good, and held in front of the edit
    it would hold the very resume whose report replaces it. The edit's resume
    leaves the saved report exactly where it was until that replacement is
    recorded over it, so a resume that ends in a question or an `ACK:` leaves
    it to this hold, which parks it for the requirements it no longer answers.

    Two reports are left to the roads that already own them. One this issue
    is parked for (`report_undeliverable`) is the reply's to replace. One
    whose record names a commit the pull request does not carry would only be
    refused here, which would turn whatever park stands -- a timeout a
    `/orchestrator continue` retries -- into the report's; the recovered push,
    the hold ahead of the rebase, and the reply road each refuse it already.
    """
    if ctx.state.get(_state._PARK_REASON) == _report_delivery.UNDELIVERABLE_REPORT:
        return False
    recorded = _resume_records._read_candidate(ctx.state)
    published = _late_publication_state._published_commit(ctx.state)
    if recorded is not None and recorded[1] != published:
        return False
    return _holds_the_rewrite(ctx)


def _holds_the_rewrite(ctx: _models._ConflictContext) -> bool:
    """Settle a report this issue recorded before anything rewrites the head it is about; True where it is still owed.

    Asked ahead of the rebase, which is the rewrite this stage makes of a head
    it has already published. A report recorded and not yet settled -- the
    one a body edit's resume saved before a crash took its push, carried out
    since by the recovered push, or one a transaction left outstanding -- is
    bound to whatever the code-publication receipt names when it settles. Let
    the rebase and the push behind it go first and that is the head they
    left, so the report of one commit is handed to a reviewer as the account
    of another, and the report debt the rewrite records is paid by it.

    So it is settled first, through the hold `validating` takes ahead of its
    reviewer, and only then is the head rewritten: the rewrite's own debt then
    follows a report of the head it replaced, and `validating` asks the
    developer for a report of the new head with nobody involved. Where it
    cannot settle yet, nothing is rewritten this tick; where it never can, the
    hold parks for a human, as it does on `validating`. A saved report whose
    candidate the last publication is not is never bound to it
    (`resume_records._refuses_another_head`). Committed work the issue owes a
    report nobody recorded is the recovered push's to refuse
    (`recovery_guards._parked_undescribed_push`), since that push is the one
    road that would carry it to the pull request.
    """
    recorded = _delivery_state.carries_delivered_report(
        ctx.state,
    ) or _record_state.carries_pending_report(ctx.state)
    if not recorded:
        return False
    return _resume_records._refuses_another_head(
        ctx, _late_publication_state._published_commit(ctx.state),
    ) or _report_hold._owed_report_holds(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, WorkflowLabel.RESOLVING_CONFLICT,
    )
