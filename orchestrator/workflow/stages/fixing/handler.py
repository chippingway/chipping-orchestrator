# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One fixing tick, in the order its questions have to be asked.

The preflight runs before anything else, and everything inside it outranks the
fix-loop rather than merely preceding it. A merged or closed PR is the answer
to every remaining question, so the terminal arcs are drained BEFORE the
rescan -- otherwise a closed issue whose PR merged sits closed and labeled
`fixing` forever. A closed issue with no resolvable PR is left alone instead of
parked, because parking a closed issue helps nobody. A `fixing` label with no
pinned `pr_number` can only have come from a manual relabel (in_review holds
the PR before it routes here), so it parks once and waits for a human to put
the label back.

A failed PR fetch ends the tick the same way, deliberately quietly: PyGithub
failures here are transient, and because no watermark has moved yet the next
tick re-fetches and picks up exactly where this one stopped.

Past the preflight and ahead of the rescan stands the one state this stage may
not resume over: a developer report delivered and nobody being waited for,
which is what a crash anywhere past a reporting round's own write leaves
behind. That round is finished rather than repeated -- whatever commit it
recorded a report of and never published goes out through the same size gate it
would have passed, and the issue is then handed to `validating`, where a
delivery is bound and settled without a developer. It fails CLOSED: a checkout
that can vouch for nothing reads exactly like a branch with nothing to send, so
short of an affirmative proof that the pull request carries the work the report
is about, the round is held for a human instead.

Then the rescan, the parked dispatch, and the resume. The empty-feedback exit
between them is the one that is easy to miss: nothing unread means a prior tick
already consumed the batch (or an operator advanced the watermarks by hand), so
the issue would otherwise sit in `fixing` with no work. It clears the route
bookkeeping and bounces to `validating` for a fresh reviewer read of the
current head -- after publishing whatever an earlier run committed and never
pushed, because on the validating route this exit is the only tick left that
can. That route's feedback is a reviewer comment the orchestrator authored
itself, which the rescan filters out, so a run whose outcome was discarded (a
`paused` label applied mid-run) is never re-run: without the publish here the
reviewer would read a head that is missing the fix it asked for.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    terminals as _terminals,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    parked as _parked,
    resume as _resume,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_reconcile as _late_reconcile,
    late_records as _late_records,
)
from orchestrator.workflow.stages.validating import (
    fix_report_evidence as _fix_evidence,
    stranded as _stranded,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

# Why a report a crashed round recorded is held here rather than handed on. Its
# own notice rather than the disposition's: what this road cannot prove is not
# that a run committed nothing, but that the work a report already written
# describes is on the pull request at all.
_UNPROVED_RECOVERY_PARK = (
    "{mentions} a fix round on this issue recorded its completion report and "
    "ended before the work that report describes reached PR #{pr} -- and this "
    "orchestrator cannot prove what the branch is standing on now. Either the "
    "checkout is gone or could not be read, or the branch and its remote do "
    "not agree on the commit the pull request was last published at. Nothing "
    "was published and nothing was discarded: the report is still on the "
    "pinned comment, and the branch and the pull request are exactly as they "
    "were. Handed on from here it would be published against a head that may "
    "be missing the very work it is about. Reply and the orchestrator resumes "
    "the session; the report it writes then is the one that gets published, "
    "and any commit the branch is carrying goes out through the ordinary "
    "measurement with it."
)


def _park_fixing_without_pr(gh: GitHubClient, issue: Issue, state) -> None:
    """Park a `fixing` issue that carries no pinned `pr_number`.

    `fixing` is only ever entered with a recorded PR (in_review holds the PR
    before routing), so reaching here means a manual relabel from outside that
    route. Park once and surface to a human -- the dev-resume path needs the
    PR to push a fix. A no-op when the issue is already awaiting human input.
    """
    if state.get(_state._AWAITING_HUMAN):
        return
    _guards._park_awaiting_human(
        gh, issue, state,
        # The two names the human has to type into GitHub are the labels
        # verbatim; the prose before them names the stage.
        f"{config.HITL_MENTIONS} `{WorkflowLabel.FIXING}` without a pinned "
        "`pr_number`; manual relabeling suspected. Set the workflow "
        f"label back to `{WorkflowLabel.IN_REVIEW}` (or "
        f"`{WorkflowLabel.VALIDATING}`) after attaching a PR.",
        reason="missing_pr_number",
    )
    gh.write_pinned_state(issue, state)


def _fixing_preflight(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state):
    """Fetch the PR and run the pre-rescan guards shared with
    `_handle_in_review`: PR-state terminals, a closed issue with no
    resolvable PR, and a `fixing` label with no pinned `pr_number`.

    Returns the fetched PR to continue the fix loop on, or ``None`` when
    the tick is fully handled -- a terminal finalized, a closed issue was
    left alone, a missing-PR park was posted, or the PR fetch failed -- and
    the caller must return immediately.
    """
    pr_number = state.get(_PR_NUMBER)
    # Bind `pr` up front so the post-terminal guard below can branch on
    # it even when `pr_number` is None (in which case the fetch is
    # skipped entirely).
    pr = None

    # PR-state terminals (mirrors `_handle_in_review`). Run BEFORE any
    # rescan / debounce so a closed-fixing issue with a merged PR
    # finalizes to `done` on this tick instead of sitting closed +
    # `fixing` forever, and an external merge on an open issue also
    # short-circuits the resume cycle.
    #
    # PyGithub failures here are typically transient (network blip, rate
    # limit, 5xx). Catch and bail with `pr=None` so the caller also
    # short-circuits -- the next tick re-fetches and picks up wherever we
    # left off; the watermarks are unchanged so no feedback is lost.
    if pr_number is not None:
        try:
            pr = gh.get_pr(int(pr_number))
        except Exception:
            log.exception(
                "issue=#%s could not fetch PR #%s in fixing terminal "
                "branch; falling through", issue.number, pr_number,
            )
            pr = None
        if _terminals._drain_review_pr_terminals(
            gh, spec, issue, state, pr, stage="fixing",
        ):
            return None

    # Closed issue with no PR (or a PR lookup failure): nothing to
    # finalize via the PR-state arcs above. Leave alone rather than
    # parking a closed issue.
    if getattr(issue, "state", "open") == "closed":
        log.info(
            "repo=%s issue=#%s closed fixing issue with no resolvable PR; "
            "leaving alone (relabel manually to finalize)",
            spec.slug, issue.number,
        )
        return None

    if pr_number is None:
        _park_fixing_without_pr(gh, issue, state)
        return None

    # `pr_number` was set but `gh.get_pr` raised above. The exception is
    # already logged; bail this tick so the caller's rescan does not
    # dereference `None`. PyGithub failures here are typically transient
    # (network blip, rate limit, 5xx), so the next tick re-fetches and
    # picks up wherever we left off; the watermarks are unchanged so no
    # feedback is lost.
    if pr is None:
        return None

    return pr


def _publish_stranded_fix(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state, spends,
) -> _models._StrandedPublication:
    """Push a fix an earlier run committed to the worktree but never published.

    The live-pause guard promises that work committed while `paused` was on
    reaches the PR once the label comes off, and on the validating route the
    bounce below is the only tick left to keep it: the reviewer feedback that
    started the round is orchestrator-authored, so the rescan filters it out
    and no later run rediscovers it. Probing here is what makes the bounce
    honor that promise instead of relabeling over a head the fix never reached.

    It is one of the seams a candidate reaches a published pull request
    through, so the size gate stands in front of this push exactly as it does
    in front of the shared dev-fix one -- a stranded commit is work nobody
    measured, and a bounce that pushed it would be the way past a gate every
    other route passes. A held candidate stops the bounce outright: the gate
    has moved the issue to the adjudication, and relabeling over that would
    publish the very question it just opened.

    `pushed` is True only when the branch actually moved, so the caller counts
    a reviewer round for a fix the reviewer can now see. `spends` is that same
    round handed to the gate up front, for the exit where the caller never
    gets to count it: a hold relabels, so bookkeeping applied afterwards is
    lost to any crash in that window and no later tick goes back for it.

    The worktree may be gone (a terminal cleanup, a fresh host), the stranded
    probe refuses every shape it cannot vouch for, and a failed push leaves the
    commit on disk for the next round's push to carry rather than claiming a
    publish that did not happen.
    """
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not wt.exists():
        # Nothing to publish is the ordinary answer, and it is not the whole
        # one: a pair this issue froze and never counted has no checkout to
        # be measured in either, and bouncing on it would hand the reviewer a
        # head the pull request never received.
        return _models._StrandedPublication(
            held=_late_reconcile._holds_absent_checkout(gh, spec, issue, state),
        )
    stranded = _stranded._stranded_fix_unpushed(spec, wt, state, issue)
    if not stranded:
        return _models._StrandedPublication()
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    published = _late_push._publishes(
        _late_records._gate(gh, spec, issue, state, wt), branch,
        # The remote head the stranded proof was taken against, which is the
        # branch this push replaces. Left for the gate to read afterwards, a
        # head somebody landed between that proof and this push becomes the
        # lease and is force-overwritten by work proved against the head it
        # used to be on.
        _late_gate_models._Entered(spends=spends, head=stranded),
    )
    if published.held:
        return _models._StrandedPublication(held=True)
    if published.landed:
        return _models._StrandedPublication(pushed=True)
    log.warning(
        "repo=%s issue=#%s could not push the stranded fix on the "
        "no-feedback bounce; leaving it on the branch",
        spec.slug, issue.number,
    )
    return _models._StrandedPublication()


def _hands_a_delivered_report_back(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state,
) -> bool:
    """Send an issue holding a delivered report this stage may not resume over back.

    True where this owner took the tick, and the caller must return. What it
    answers is the one state this stage can arrive in that its own next step
    would make worse: a developer report DELIVERED and still unbound, with no
    human being waited for.

    That state is a window this stage's own ordering opens and cannot close.
    The round that reports writes the delivery durably ahead of the size gate,
    and the relabel to `validating` comes after the push -- so a process dying
    anywhere past that write leaves `workflow:fixing`, `awaiting_human` cleared
    by the resume, the triggering reply still unread because a reporting
    round's readers ride the report rather than the tick, and a report nothing
    has published. The rescan behind this guard reads that reply as fresh
    feedback and resumes the developer again: another run charged, and a SECOND
    report written over the first, with the reviewer handed whichever landed.

    So the round is finished here instead, which is the publication it may
    still owe and then the hand-back. `validating` is the stage that finishes a
    delivery without a developer -- its review hold binds it to the publication
    the receipt names, settles it through the reconciliation, and parks for a
    human where no retry can -- and it spawns no reviewer while the report is
    owed. Nothing of the handover is written here: the round and the bookmarks
    it owes are frozen on the record already, and the write that settles the
    report is what closes them.

    A park is left alone, which is what `awaiting_human` asks. A delivery can
    stand beside one -- a report written and then a push that failed, or a
    candidate the gate held -- and the routes that answer those are BEHIND this
    guard: the transient recovery that retries the push, and the reply a human
    owes the notice. Handed back over either, the recovery would never run.

    A TRANSACTION is left alone too, though it is a report owed just the same,
    because it already has a route across this boundary and that route is not
    this one. The reconciliation runs ahead of every stage handler, and what it
    does with a refusal it cannot clear is stand DOWN -- deliberately, so the
    roads that clear one keep running, and on this stage those roads are the
    gate's own push and the resume below. Relabeling over it here would reverse
    that stand-down into a hand-off and the transaction would wait for a
    publication no tick makes.

    A debt with no record at all is left alone for the opposite reason. What
    that is short of is a report nobody has written, and the only thing that
    supplies one is the developer this stage resumes -- so it is this stage's
    to answer rather than a state to hand on.
    """
    if state.get(_state._AWAITING_HUMAN):
        return False
    if not _delivery_state.carries_delivered_report(state):
        return False
    if _publishes_what_the_report_describes(gh, spec, issue, state):
        return True
    log.warning(
        "repo=%s issue=#%s carries a delivered developer report and no human "
        "to wait for; handing it to `%s` rather than resuming a developer over "
        "a report nobody published",
        gh.repo_slug, issue.number, WorkflowLabel.VALIDATING,
    )
    gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)
    return True


def _publishes_what_the_report_describes(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state,
) -> bool:
    """Send a commit the crashed round never published out, ahead of the hand-back.

    True where the gate took the issue and this tick is over; False where the
    hand-back may go ahead. What it exists for is the EARLIER half of the same
    window: the report is written before the gate reads the candidate, so a
    process dying in between leaves a report about a commit sitting in the
    checkout -- and `validating` has exactly one answer to a delivery whose
    commit no publication carries, which is to park it for a human. Handed on
    unpublished, the crash would cost a human reply and a second session for
    work that was only ever one push short.

    So the candidate goes out the way every other one does, through the size
    gate and leased to the head the pull request is standing on. It is measured
    because it is work nobody measured: the tick that would have measured it
    died in front of the gate, and a recovery that pushed around it would be
    the way past a ceiling every other route passes.

    What the push spends is read off the RECORD rather than recomputed, because
    the round and the bookmarks this handover lands on were frozen onto it by
    the run that wrote the report. Handed to the gate, they go into the same
    receipt write a first attempt would have made, and the settlement re-applies
    the identical pair later as a no-op -- where a round read afresh off the
    pinned counter would be a second count for one handover. A record nobody
    can READ names no such pair and publishes nothing: that one is `validating`'s
    to park, with the commit left where it stands for the human who repairs it.

    A held candidate ends the tick: the gate has moved the issue to the
    adjudication, and a hand-back over that would publish the very question it
    just opened.

    Nothing published is where this FAILS CLOSED, because the probe answers ""
    for a branch with nothing to send and for a checkout that vouches for
    nothing alike -- a tree nobody could read, a checkout gone with the host, a
    fetch that failed, a divergence git refused, a remote that moved. Read as
    "no commit was stranded" the report would be handed on, and the binding
    behind it recreates a lost checkout from the remote and finds its head
    equal to the receipt: the report of a commit that never passed the gate
    would be published against the head the pull request had all along. So the
    same affirmative proof a report with no code in it must pass is asked here
    (`validating/fix_report_evidence.py`) -- the branch standing exactly where
    its remote is, and the receipt naming that commit on this pull request --
    and short of it the round is held for a human with the record intact. The
    reply resumes the session, whose fresh report supersedes this one and takes
    its round and its readers with it, and whatever the branch is carrying goes
    out through the ordinary measurement then.
    """
    delivered = _delivery_state.read_delivered_report(state)
    if delivered is None:
        return False
    owed = _late_gate_models._Spends(fields=delivered.spends)
    stranded = _publish_stranded_fix(gh, spec, issue, state, owed)
    if stranded.held:
        # The gate owns the issue from here -- parked, or handed to the
        # adjudication -- and it spent the round inside its own write, ahead of
        # the label it moved. The write is still this caller's: a park posts
        # its notice and leaves the flags in memory.
        gh.write_pinned_state(issue, state)
        return True
    if stranded.pushed:
        _late_gate_models._spend(state, owed)
        gh.write_pinned_state(issue, state)
        return False
    if _fix_evidence._proves_the_published_head(
        spec, issue, state, _worktree_paths._worktree_path(spec, issue.number),
    ):
        return False
    log.warning(
        "repo=%s issue=#%s cannot prove PR #%s carries the work its recorded "
        "developer report describes; holding it for a human rather than "
        "handing that report to `%s`",
        gh.repo_slug, issue.number, state.get(_PR_NUMBER),
        WorkflowLabel.VALIDATING,
    )
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _UNPROVED_RECOVERY_PARK.format(
            mentions=config.HITL_MENTIONS, pr=state.get(_PR_NUMBER),
        ),
    )
    return True


def _bounce_without_feedback(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state,
) -> None:
    """Drop the route bookkeeping and hand the issue back to `validating`.

    The stranded publish runs first because a commit that reaches the PR here
    spends a reviewer round exactly like one a dev run pushed -- the head the
    reviewer is about to read is not the head it rejected -- so it earns the
    same `review_round` bookkeeping the pushed-fix exit applies. The route
    discriminator is read BEFORE the clear below drops it, which is what keeps
    the in_review route's reset apart from this route's bump.
    """
    pending_fix_at_was_set = state.get(_state._PENDING_FIX_AT) is not None
    # Frozen before the push and re-applied after it, so the gate's own write
    # and this tail cannot disagree: re-applying a value already written is a
    # no-op, where recomputing the round from the pinned comment would count
    # it twice.
    owed = _resume._spends_fix_round(state, pending_fix_at_was_set)
    stranded = _publish_stranded_fix(gh, spec, issue, state, owed)
    if stranded.held:
        # The gate owns the issue from here -- parked, or handed to the
        # adjudication -- and the relabel below belongs to a bounce that is
        # not happening. The round it would have counted was spent inside the
        # gate's own write, ahead of the label it moved. The write still is
        # this caller's: a park posts its notice and leaves the flags in
        # memory for its caller to persist.
        gh.write_pinned_state(issue, state)
        return
    if stranded.pushed:
        _late_gate_models._spend(state, owed)
    else:
        # Nothing was published, so no round was landed -- but the bookmarks
        # this bounce read are consumed either way, and a later
        # in_review->fixing route must write fresh values rather than mix
        # rounds with them.
        _bookmarks._clear_pending_fix_bookmarks(state)
    gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)
    gh.write_pinned_state(issue, state)


def _handle_fixing(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    state = gh.read_pinned_state(issue)

    pr = _fixing_preflight(gh, spec, issue, state)
    if pr is None:
        return

    # A DELIVERED report and nobody being waited for is the one state this
    # stage may not resume over: it is what a crash anywhere past a round's
    # report write leaves, and the rescan below would read the reply that round
    # already answered as fresh feedback. The publication that round may still
    # owe is made here, and `validating` binds and settles the delivery behind
    # it; neither is a thing this stage's resume can do.
    if _hands_a_delivered_report_back(gh, spec, issue, state):
        return

    feedback = _feedback._rescan_fixing_feedback(gh, issue, pr, state)

    # `replay_batch` is set only by an accepted `/orchestrator continue`
    # command inside `_dispatch_parked_fixing`: the PRESERVED PR-feedback batch
    # (plus any genuinely new feedback that arrived with the command) to resume
    # the fresh dev on, instead of the per-tick rescan. It carries its surfaces
    # apart exactly as the rescan does, because the resume settles what it
    # replayed. It skips the debounce and re-grounds a dropped session in the
    # resume tail.
    #
    # `_dispatch_parked_fixing` bails (`stop=True`) unless something new has
    # arrived since the park bump: the watermarks were advanced past the
    # previously-consumed feedback, so `feedback` can only carry genuinely new
    # content, and without that guard a single poisoned tick would loop on
    # every poll, spamming the same dev-resume prompt.
    replay_batch: _models._FixingFeedback | None = None
    if state.get(_state._AWAITING_HUMAN):
        parked = _parked._dispatch_parked_fixing(
            _models._FixingContext(gh, spec, issue, state, pr), feedback,
        )
        if parked.stop:
            return
        replay_batch = parked.replay_batch

    # Watermarks already cover the triggering bookmarks (a prior tick consumed
    # them, or an operator advanced them manually). Nothing left to address;
    # publish whatever is stranded on the branch and bounce back to
    # `validating` so the reviewer re-evaluates against the current head
    # instead of leaving the issue stuck in `fixing` with no work.
    if not feedback.all_items:
        _bounce_without_feedback(gh, spec, issue, state)
        return

    if _feedback._fixing_debounce_open(feedback, replay_batch):
        return

    _resume._resume_fixing_and_dispatch_result(
        _models._FixingContext(gh, spec, issue, state, pr), feedback, replay_batch,
    )
