# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""From a landed push to the handoff: the report it owes, and the last readings.

Reached once `publication` has pushed a named commit and knows the pull request
it reached -- the first moment the developer's report has a publication to be
about. The description is judged first, read afresh by number, because the
binding has to be told whether it names this implementation: a report verified
on a description that does not is the one report this stage can neither keep
nor route around. Then the report is bound and posted, or verified, by the
engine.

What follows is asked last, immediately before the relabel, because every one
of it is a human's to change at any moment: the issue's requirements first --
whether or not a report exists to hold them to, since a run that never
completed leaves a commit and no report; then the report -- owed, or settled
and still standing where it settled -- read after the requirements request
rather than before it, so an edit landing during that request is still seen;
then the checkout, which is local and so is read after both of those requests;
and the description last, since a human may have named it, or unnamed it, since
the first reading. Anything short of all of them withholds the handoff, which
`publication` records as owed; the next tick republishes the same commit onto
the same pull request with no developer run and nothing new opened. A debt no
retry can pay parks once for the reply that resumes the developer to write the
report again.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
    pull_request_reports as _pr_reports,
)
from orchestrator.workflow.engine import (
    drift as _engine_drift,
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _report_evidence,
    report_record_state as _record_state,
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import (
    checkout_guards as _checkout,
    handoff as _handoff,
    pr_description as _pr_description,
)

log = logging.getLogger("orchestrator.workflow")

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


def _hands_on(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    reached: _report_binding.ReportPublication,
    wt: Path,
) -> bool:
    """Deliver the report onto the publication, then relabel if all still holds.

    True is a handoff made. False is one withheld, for the caller to record as
    owed: a report still owed, or no longer standing where it settled or under
    the requirements it answers; requirements that moved under a publication
    no report covers, or could not be read; a checkout that moved or dirtied
    after the push -- read after the report's requests, so one that moved
    during them is seen; or a description that does not close this issue and
    name this session, or one nobody could read.
    """
    pr = reached.pull_request
    described = _pr_description._names_the_implementation(gh, issue, state, pr)
    if described is not None:
        _report_binding.binds_and_publishes(
            gh, issue, state, replace(reached, describes_the_issue=described),
        )
    if (
        _remote_readings_hold(gh, issue, state, reached)
        or _checkout._moved_after_the_push(gh, issue, state, reached.commit, wt)
        or _checkout._dirtied_after_the_push(gh, issue, state, reached.commit, wt)
        or not _pr_description._names_the_implementation(gh, issue, state, pr)
    ):
        return False
    _handoff._advance_to_validating(gh, issue, state, pr, reached.branch)
    return True


def _remote_readings_hold(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    reached: _report_binding.ReportPublication,
) -> bool:
    """Hold the handoff on the report or the requirements; True where it held.

    A report still owed holds: nothing under `validating` comes back for one,
    so the handoff is refused as a moved checkout's is, and the next tick
    republishes onto the same pull request with no second developer run --
    the reconciliation or the binding posting the report on the way.

    Unless no retry can pay it: a debt with no record left to publish -- a
    resumed session that did not finish -- or a transaction whose report on
    this pull request a human edited, removed, or wrote untrusted. Those park
    for the reply that resumes the developer to write the report again.

    With nothing owed the requirements are read afresh either way. The report
    settled for this commit on this pull request is held to its own revision
    and read again where it settled, `_holds_a_moved_settlement`; a
    publication no report covers -- the commit a run that never completed
    left -- is held to the revision the run was handed,
    `_holds_moved_requirements`.
    """
    number = getattr(reached.pull_request, "number", 0) or 0
    if not _report_delivery.owes_a_report(state):
        current = _settlement.read_current_report(state)
        if current is not None and (
            current.subject.pr_number, current.subject.source_sha,
        ) == (number, reached.commit):
            return _holds_a_moved_settlement(gh, issue, state, current)
        return _holds_moved_requirements(gh, issue, state)
    pending = _record_state.read_pending_report(state)
    recordless = not (
        _delivery_state.carries_delivered_report(state)
        or _record_state.carries_pending_report(state)
    )
    if recordless or (
        pending is not None
        and pending.subject.pr_number == number
        and _report_evidence.refuses_for_good(gh, pending, reached.pull_request)
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
        issue.number, reached.commit, number,
    )
    return True


def _holds_moved_requirements(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Hold a publication no report covers whose issue moved; True where held.

    What a commit with no report was written against is the revision pinned
    for the run that made it, so the issue is read again and put to the same
    drift check every tick opens with -- the issue in hand was fetched before
    that run, and an edit during it or during the publication is invisible
    there. A moved revision holds UNPARKED: that check, asked again at the top
    of the next tick, is the road that answers an edit, resuming the session
    against the requirements as they stand. A read nobody could take holds
    too, since nobody could say the issue is unchanged.
    """
    try:
        moved = _engine_drift._detect_user_content_change(
            gh, gh.get_issue(issue.number), state,
        )
    except Exception:
        log.exception(
            "issue=#%s could not be re-read for its requirements before the "
            "handoff; holding it rather than handing on unread", issue.number,
        )
        return True
    if moved is None:
        return False
    log.warning(
        "issue=#%s requirements moved since the run whose commit this "
        "publication carries; holding the handoff for the drift resume",
        issue.number,
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
    The requirements are read afresh first and the report where it settled
    second, so an edit to the report landing while the issue is read is still
    seen. A reading nobody could take holds silently; a definite refusal parks
    for a report-only reply, naming the report where that is what moved.
    """
    edited = _report_evidence.fresh_requirements_verdict(
        gh, issue, state, settled,
    )
    if edited is not None and edited.holds:
        return True
    presence = _settled_reading.still_carries(gh, state, settled)
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return True
    carried = presence is _pr_reports.ReportPresence.PRESENT
    if carried and edited is None:
        return False
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _STUCK_REPORT_PARK.format(
            mentions=config.HITL_MENTIONS, pr=settled.subject.pr_number,
            detail=_MOVED_REQUIREMENTS if carried else _UNSETTLEABLE,
        ),
    )
    return True
