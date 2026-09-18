# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Turning a committed worktree into a pushed branch, a PR, and a handoff.

The order here is what makes the step re-runnable. The push comes first and a
failed push parks instead of continuing, because the commits stay in the
worktree and would otherwise keep `_has_new_commits` true and re-comment on
every poll. The PR is then reused if one is already open on the branch, so a
tick that died between `open_pr` and the relabel recovers instead of 422-ing on
a duplicate. Only then is the handoff written.

None of it happens without ONE named commit, which is what the first line
here establishes: a push named against nothing sends whatever the branch has
become by the time git runs it, records no receipt, and leaves both proofs
around it with nothing to compare against -- so a checkout that cannot say
what it is on publishes nothing rather than publishing unnamed.

What that checkout IS gets proved twice around all of it, because the worktree
stays writable while the push and the two pull-request requests run. What each
proof looks at -- the commit AND the tree, since work can appear beside a
commit without moving it -- and what a refusal says and parks under belongs to
`checkout_guards`. This owner decides only WHERE the two are taken: before
the push, where nothing is published and the tick simply stops, and once the
pull request is open, where the publication stands and only the handoff stops.
Everything past that handoff reads the checkout and none of it measures again.

What the pull request itself says -- its title, its body, and the dev session
the body attributes the branch to -- is `dev_pr`'s, along with the verdict on a
description somebody else wrote. This owner decides only WHEN one is opened,
which is once the push has landed, and WHEN its description is judged: before
the report is bound, which is told the answer, and once more last, before the
handoff, since settling the report is what can free a description to be named.

What the handoff itself writes -- the pull request and the branch it records,
the records it spends, the counters it resets, and the relabel it goes out
ahead of -- is `handoff`'s, for the same division: this owner decides only WHEN
it is reached, which is once both proofs taken around the push have passed and
the report the run wrote is on the pull request.

That report is the third thing a publication owes, bound and posted here
because until the push lands the report names no publication at all. Binding
and publishing are the engine's; this owner decides only WHEN, which is once
the pull request is known, and what an unpublished one COSTS: the handoff.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
    pull_request_reports as _pr_reports,
)
from orchestrator.workflow.engine import (
    guards as _guards,
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _report_evidence,
    report_publishing as _report_publishing,
    report_record_state as _record_state,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import (
    checkout_guards as _checkout,
    dev_pr as _dev_pr,
    handoff as _handoff,
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_publication_state as _late_publication_state,
    models as _models,
    push_barrier as _barrier,
)

log = logging.getLogger("orchestrator.workflow")

_UNPROVABLE_HEAD_PARK = (
    "{mentions} this issue's worktree could not say which commit it is on "
    "({failure}), so nothing was published. A push named against no commit "
    "sends whatever the branch has become by the time git runs it, and leaves "
    "nothing on the issue afterwards saying which commit that was -- so the "
    "two proofs taken around the push have nothing to hold the checkout to "
    "either, and review is handed whatever is there. Nothing was discarded, "
    "the commit is still in the worktree, and the branch is untouched. Clear "
    "what is stopping the read, then reply and the orchestrator will resume "
    "the session."
)


# A report the handoff waits on that no retry can deliver, and why.
_STUCK_REPORT_PARK = (
    "{mentions} this issue's code is published on PR #{pr}, and the developer "
    "report it owes cannot be delivered as things stand: {detail}. The work is "
    "held rather than handed to review. Reply and the orchestrator resumes the "
    "session; the report it writes then is the one that gets published, and "
    "it needs no new commit to deliver it."
)

_UNRECORDED = (
    "no report of it is recorded anywhere -- the session resumed to write one "
    "did not finish"
)

_UNSETTLEABLE = (
    "the report it went out as was edited, removed, or written by an author "
    "this deployment does not trust"
)

_MOVED_REQUIREMENTS = (
    "the issue's requirements have moved since the run that wrote it"
)


def _leased_against(
    state: _pinned_state.PinnedState,
    approved: _models._ApprovedWork,
    published: str,
) -> str | None:
    """The SHA the remote ref has to be at for this push to be allowed.

    Three answers, and the one that matters is the one a bare `None` gets
    wrong. `None` lets the transport take its OWN reading of the remote and
    lease against whatever it finds, which is right for the ordinary initial
    publication -- there is no pull request yet, and the lease is there only
    so a self-restart's re-push is not refused as a non-fast-forward.

    It is wrong for a publication the gate admitted BECAUSE the pull request
    is already standing on the commit. That answer is a reading, and between
    it and this push the branch is somebody else's to move: leased against a
    fresh reading, a tip that moved in the window is adopted as the lease and
    the candidate is force-pushed over it. Leased against the commit the proof
    was about, the same push sends nothing where the branch has not moved and
    is refused outright where it has.

    The third is an approval taken on the PUBLISHED side, which a settled
    adjudication sends back here: the reading it was measured under is only
    worth what the head it was taken over still is, so the push is pinned to
    that head and a pull request somebody moved during the adjudication
    rejects it instead of being force-overwritten.
    """
    if approved.delivered_pr:
        return published
    return _late_approval_reading._approved_lease(state) or None


def _publication_intent(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    approved: _models._ApprovedWork,
    worktree: Path,
) -> str | None:
    """The one commit this publication is about, durable before it is pushed.

    Everything past this line is named against what it returns: the push, the
    record the handoff leaves, and the proof taken once the pull request is
    open. Deciding it once and up front is what keeps those three about the
    same commit -- a checkout re-read at any of them is a checkout that may
    have moved since.

    The gate names it wherever it proved one. Where it did not -- a candidate
    the switch kept out of the gate -- the checkout names it, because the
    alternative is a push that names nothing and therefore publishes whatever
    the branch has become by the time git runs it, with nothing on the issue
    afterwards saying which commit that was. The switch keeps candidates out
    of the MEASUREMENT; it does not make them unnameable, and it is an
    operator's to turn back on between one tick and the next.

    Then it is made durable, and only where the record does not already say
    it. Between this line and the handoff the branch goes to the remote and a
    pull request opens over it, and a tick that died in there would leave an
    issue whose branch is published and whose record says nothing was owed --
    which the next tick reads as work nobody has ruled on. The roads that
    were approved or adjudicated already wrote this commit down and pay
    nothing here; the ones that were not pay one write.

    None is the answer that stops the publication, and both roads reach it.
    The checkout is not on the commit the gate approved, so nothing may be
    pushed from it -- or the checkout cannot say what it is on at all, which
    is a repository to look at rather than a commit to name. Neither publishes
    anything.

    That second one is a refusal rather than a fallback because of what a
    nameless push COSTS. Named against nothing, git sends whatever the branch
    has become by the time it runs, and nothing goes on the issue saying which
    commit that was -- so the receipt the handoff leaves is empty, the proof
    taken once the pull request is open has no commit to hold the checkout to,
    and the one taken before the push has none either. Every guarantee this
    owner exists to make is about one named commit, and a publication with no
    name is outside all of them at once.
    """
    if approved.candidate_sha:
        if _checkout._moved_off_the_candidate(
            gh, issue, state, approved, worktree,
        ):
            return None
        return _recorded_intent(gh, issue, state, approved.candidate_sha)
    proved = _measurement_commits._prove_candidate_commit(
        worktree, _checkout._HEAD,
    )
    if proved.is_frozen:
        return _recorded_intent(gh, issue, state, proved.sha)
    log.error(
        "issue=#%s worktree cannot name the commit it is on (%s); refusing to "
        "publish a branch under no commit", issue.number, proved.failure,
    )
    _checkout._park_for_the_checkout(
        gh, issue, state,
        _UNPROVABLE_HEAD_PARK.format(
            mentions=config.HITL_MENTIONS, failure=proved.failure,
        ),
    )
    return None


def _recorded_intent(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: str,
) -> str:
    """Make the commit about to be pushed durable, if it is not already.

    It is recorded as the commit this issue owes a push, because that is what
    it is right up to the moment the push lands -- the same field an approval
    writes, spent by the same handoff, and read by the same pre-spawn proof if
    this tick does not get that far. A record already naming it is left alone,
    which is every road the gate proved and decided a commit on, and which is
    also what keeps the grounds those roads recorded: the write below is for a
    debt this owner is minting, not for one it is re-asserting.
    """
    if _late_approval_reading._approved_commit(state) == published:
        return published
    _owes_the_handoff(state, published)
    gh.write_pinned_state(issue, state)
    return published


def _on_commits(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    approved: _models._ApprovedWork,
) -> None:
    """Push the branch, open or reuse its PR, and hand off to validating.

    One commit is decided on before any of this runs, and the push, the
    record the handoff leaves, and the proof taken once the pull request is
    open are all about that one. The commit on `approved` is it wherever the
    size gate proved one; where the gate proved none -- a candidate the switch
    kept out of it -- the checkout names it instead. A checkout that cannot
    name one publishes nothing at all, because a push that names nothing sends
    whatever the branch has become by the time git runs it and leaves every
    proof past this line with no commit to hold it to.
    `_publication_intent` is where that is settled and made durable.

    Naming the commit is only half of it, because what the handoff passes on
    is the CHECKOUT. Every stage past this one reads that checkout: the
    reviewer treats a head ahead of the pushed branch as unpushed work to
    publish, the squash rewrites what is on it, and the docs pass commits on
    top. So a worktree sitting on a descendant would hand review an
    implementation the size gate never saw, one publication later and with no
    measurement between. That is asked twice, because the window is the three
    requests in between: before the push nothing is published and the commit
    stays where it is, and after the pull request is open the publication
    stands while the HANDOFF stops, so review never reads the descendant.

    Both boundaries ask it of the TREE as well as of the head, because the
    head answers only half of what "this checkout" is. Uncommitted work can
    appear while `HEAD` never moves, so every proof about the commit passes
    over it -- and the stage this hands to takes no reading of its own, so a
    tree carrying work the pull request does not show reaches the squash and
    the docs pass, which commit it or destroy it. Cleanliness proved at the
    top of the disposition is a fact about a moment that has passed by the
    time either effect runs.

    The report the developer wrote is bound and posted once the pull request
    is known, and a report still owed refuses the handoff exactly as a moved
    checkout does: nothing past the relabel comes back for one.

    Work that ENDED is refused immediately before the push, on the same terms
    every gated publication onto an open pull request refuses one. A close a
    poll observed is one half: the gate's own barrier ends the CYCLE, which
    answers every candidate a record is still live for -- and the roads this
    seam reaches it by are exactly the ones where none is, since an approval
    whose push failed retires its generation before that push. The pull
    request this push would JOIN is the other, whichever of the two the tick
    has -- one the gate proved, or one the record names and the reuse below
    would find by branch. Either ending in the window between the tick's first
    reading and here leaves that lookup answering nothing, so a second pull
    request is opened over the work and `pr_number` overwritten with it. What
    work nobody wants may never earn is this effect, so the refusal is held:
    nothing pushed, no pull request opened, no handoff, and the receipt and
    debt left exactly as they stand for the cleanup or the retry they are
    owed. `push_barrier` owns both readings and the one ending that is not an
    ending for this push.
    """
    wt = _worktree_paths._worktree_path(spec, issue.number)
    published = _publication_intent(gh, issue, state, approved, wt)
    if published is None:
        return
    if _checkout._dirtied_before_the_push(
        gh, issue, state, published, wt,
    ) or _barrier._ended_before_the_push(gh, spec, issue, state, approved):
        return
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    if not _branch_transport._push_branch(
        spec, wt, branch, revision=published,
        force_with_lease=_leased_against(state, approved, published),
    ):
        # Park on awaiting_human like the timeout/question paths. Otherwise the
        # worktree's commits keep _has_new_commits() true, so every poll would
        # re-enter _on_commits() and re-comment indefinitely until a human acts.
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} git push failed; see orchestrator logs.",
            reason="push_failed",
        )
        # _handle_implementing writes pinned state after we return.
        return
    pr = _dev_pr._reuse_or_open_pr(
        gh, spec, issue, state,
        _models._PRWork(
            approved.agent_result, wt, branch, approved.delivered_pr, published,
        ),
    )
    if pr is None:
        return
    # The push landed, so what was an intent is now a receipt: staged here so
    # the handoff write below carries it, and so a relabel that does not land
    # leaves the next tick something to recognize an already published branch
    # by rather than work nobody has ruled on. It names no head it replaced --
    # an initial publication froze none and reads the remote for itself -- and
    # says so rather than leaving whatever the last published-side push wrote,
    # which would date this receipt to an attempt it was not made under.
    #
    # The pull request goes down WITH it, and this is the only line that can
    # write it: `pr_number` is the relabel's, which is the very write the
    # window this receipt exists for is missing. Recorded here, a tick that
    # dies before that relabel leaves an identity the next poll can prove
    # instead of a branch it would have to search.
    _late_publication_state._record_publication(
        state, published, "", getattr(pr, "number", 0) or 0,
    )
    # The report can now say where it goes: bound, written durably, and posted
    # -- ahead of the checkout proofs below, since it is about the commit that
    # is already on the remote.
    #
    # What its DESCRIPTION says travels with it, read afresh rather than off
    # the object in hand: a report verified on that body is the one report this
    # stage cannot both keep and edit around.
    described = _dev_pr._names_the_implementation(
        gh, issue, state, approved.agent_result, pr,
    )
    if described is not None:
        _report_binding.binds_and_publishes(
            gh, issue, state, _report_binding.ReportPublication(
                pr, spec.slug, branch, published, described,
            ),
        )
    # And proved AGAIN, last: settling a report elsewhere is what frees a
    # description a report was verified on to be named. Anything short of one
    # that closes this issue and names this session holds the handoff.
    if (
        _checkout._moved_after_the_push(gh, issue, state, published, wt)
        or _checkout._dirtied_after_the_push(gh, issue, state, published, wt)
        or _still_owes_its_report(gh, issue, state, published, pr)
        or not _dev_pr._names_the_implementation(
            gh, issue, state, approved.agent_result, pr,
        )
    ):
        _owes_the_handoff(state, published)
        return
    _handoff._advance_to_validating(gh, issue, state, pr, branch)


def _still_owes_its_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: str,
    pr,
) -> bool:
    """Whether this publication is unfinished because its report is unpublished.

    Nothing under `validating` comes back for a report, so the handoff is
    refused as a moved checkout's is: the debt is re-recorded, and the next
    tick republishes onto the same pull request with no second developer run
    -- the reconciliation or the binding posting the report on the way.

    Unless no retry can pay it: a debt with no record left to publish -- a
    resumed session that did not finish -- or a transaction whose report on
    this pull request a human edited, removed, or wrote untrusted. Those park
    for the reply that resumes the developer to write the report again. With
    nothing owed, the report settled for this commit on this pull request is
    asked whether it still stands: `_holds_a_moved_settlement`.
    """
    number = getattr(pr, "number", 0) or 0
    if not _report_delivery.owes_a_report(state):
        current = _settlement.read_current_report(state)
        return current is not None and (
            current.subject.pr_number, current.subject.source_sha,
        ) == (number, published) and _holds_a_moved_settlement(
            gh, issue, state, current,
        )
    pending = _record_state.read_pending_report(state)
    recordless = not (
        _delivery_state.carries_delivered_report(state)
        or _record_state.carries_pending_report(state)
    )
    if recordless or (
        pending is not None
        and pending.subject.pr_number == number
        and _report_evidence.refuses_for_good(gh, pending, pr)
    ):
        _report_delivery.parks_an_undeliverable_report(
            gh, issue, state, _STUCK_REPORT_PARK.format(
                mentions=config.HITL_MENTIONS, pr=number,
                detail=_UNRECORDED if recordless else _UNSETTLEABLE,
            ),
        )
    log.warning(
        "issue=#%s published %s on PR #%s and still owes it a developer "
        "report; holding the handoff for the tick that publishes one",
        issue.number, published, number,
    )
    return True


def _holds_a_moved_settlement(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    settled,
) -> bool:
    """Hold a settled report that no longer stands; True where it held.

    Asked last before any handoff -- this publication's and a recovery's --
    since a human can edit the report or the issue the moment after it settled.
    Read where it settled, then the requirements afresh: an unread one holds
    silently, a definite refusal parks for a report-only reply.
    """
    presence = _report_publishing.still_carries(gh, state, settled)
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return True
    edited = None
    if presence is _pr_reports.ReportPresence.PRESENT:
        edited = _report_evidence.fresh_requirements_verdict(
            gh, issue, state, settled,
        )
        if edited is None:
            return False
        if edited.holds:
            return True
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _STUCK_REPORT_PARK.format(
            mentions=config.HITL_MENTIONS, pr=settled.subject.pr_number,
            detail=_UNSETTLEABLE if edited is None else _MOVED_REQUIREMENTS,
        ),
    )
    return True


def _owes_the_handoff(
    state: _pinned_state.PinnedState, published: str,
) -> None:
    """Record the commit a checkout this stage may not hand on still owes.

    The whole approval group rather than the commit alone, because that is
    what a later tick reads it as: a commit with a lease left over from some
    other attempt beside it is the pair disagreeing with itself, and one with
    no account of its grounds is a debt whose provenance the tick that spends
    it has to guess.

    The lease is empty, which is what an INITIAL publication can promise: the
    push above is the one that opened this pull request, and the head the
    quiet republication would be pinned to is whatever that push reads off the
    remote for itself when it runs. A pull request the remote already carried
    is the other side of the gate, and it records both -- the reconciliation
    ahead of every handler reads the pair as the claim it is, and half of one
    there is damage rather than a debt.

    Which grounds it rests on, and the carrying rule behind them, belong to
    the approval group's own owner -- this seam has a second caller in the
    guard that refuses a moved checkout, and a debt written two ways would be
    two debts.
    """
    _late_approval_state._owes_a_publication(state, published)
