# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The completion report a reviewer-requested fix hands back, recorded first.

An automated reviewer that requests changes resumes the developer under the
`fixing` label, and what that session hands back is a report as well as,
perhaps, a commit. The reviewer behind the next round is handed the report as
its account of what this round did, and the session is gone the moment the tick
moves on -- so it is recorded on the pinned comment ahead of the size gate and
the push, exactly as an initial implementation's and a drift resume's are.

What this road publishes is work a report on the pull request describes, or it
publishes nothing. A run that committed and wrote no report parks for the reply
that resumes the session to write one, and that holds whether or not the run
finished: the engine exempts an incomplete run from the contract because the
roads it serves publish nothing either way, while this road publishes, so a
nonzero exit, a provider refusal and a launch nothing invoked are each parked
here as the missing report they also are.

A run that committed NOTHING and wrote a report is the one publication with no
code in it. The fix prompt asks for exactly that where a reviewer's item names
report content and no repository change -- a missing explanation, a verification
detail -- so reading such a reply as the question it is not would park an issue
whose developer finished.

What that road publishes onto is the head the pull request already carries, and
that head has to be PROVED rather than assumed. "This run committed nothing" is
what the disposition beside it answers, and it answers the same way for a
checkout nobody could read, a fetch that failed, a divergence git refused and a
remote that moved -- every one of which may be a branch carrying a commit the
pull request has not got. So this road asks for the affirmative reading instead:
a clean tree, a local HEAD that reads, a remote tip that reads, the two equal,
and the code-publication receipt naming that same commit on the pull request the
report will go onto. Short of all of it the round parks rather than reporting,
because a report published over work nobody has seen describes a head no
reviewer will ever read -- and the commit under it reaches the pull request the
way every other does, through the gate, once the reading that refused can be
taken.

A commit an EARLIER run left unpublished is a different question asked of a
different run. The report of it was that run's to record, so this road
publishes it through the ordinary gate whether or not the reply describes it --
withheld instead, it would sit in the checkout with the one tick that could
have sent it spent on a park -- and the debt the run that made it left is what
holds the reviewer off the head it lands on. A reply that IS a report is
recorded and bound to that publication, since a report written over the branch
as it stands describes that commit too.

Nothing is bound here, and on the road with no code in it nothing is SPENT here
either. What happens to the report once it is recorded -- bound to the
publication and settled, `report_settlement`'s, asked by the caller behind the
relabel, or held in front of the reviewer until it is, `report_hold`'s -- is
also where the round and the bookmarks that handover closes are written, from
the pair frozen onto the record: a report nothing confirmed has bought no
handover, so nothing of one may be durable before it lands. A pushed fix is the
other way round -- its round was spent by a commit that reached the pull
request, in the write the size gate made beside its own receipt.

Every park this owner takes carries the input the run's prompt delivered into
its own write. A park durable over feedback that still reads as unanswered is
one the next tick reads as fresh, resuming the developer again over the very
comments this round answered, with no human having said anything.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.implementing import (
    checkout_parks as _checkout_parks,
    parks as _dev_parks,
)
from orchestrator.workflow.stages.validating import (
    dev_fix as _dev_fix,
    drift_reports as _drift_reports,
    fix_report_evidence as _evidence,
    models as _models,
    state as _state,
)

# Why a run that did not finish leaves its commit where it is. The engine's own
# notice speaks for a developer that finished and declined to report, and would
# tell this human their session wrote something it never did.
_UNFINISHED_PARK = (
    "{mentions} this issue's developer left committed work on the branch "
    "answering the reviewer's requested changes and did not finish -- a "
    "nonzero exit, a provider refusal, or a launch nothing invoked -- so no "
    "completion report of that work exists. Nothing was published: whatever "
    "this run committed is still in the worktree, the branch is untouched, "
    "and the pull request still stands on the commit it already carried. Work "
    "a review round earns reaches the pull request with the report of it or "
    "not at all, because a reviewer handed a commit nobody described has no "
    "account of what was done and no session left to ask. Reply and the "
    "orchestrator resumes the session; the report it writes then is the one "
    "that gets published, and it publishes this commit with it."
)


def _records_the_fix(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> bool:
    """Record the report a fix round wrote, ahead of the gate; True where held.

    True where nothing may be published. A report this run wrote is recorded
    and the gate reads the candidate behind it; a report this build cannot
    record parks, as it does on every road.

    A run that wrote NO usable report publishes nothing at all, and that holds
    whether or not the run finished. The engine leaves an incomplete run alone
    -- a nonzero exit, a provider refusal, a launch nothing invoked are
    failures other roads answer, and on the roads it serves nothing is
    published either way -- but this road publishes, and a commit it pushed
    for such a run would reach the next reviewer with no account of it
    anywhere and no session left to ask. So the failure is parked as the
    missing report it also is, and the reply that answers it resumes the
    session, which writes the report and publishes the work with it.
    """
    if _report_delivery.recording_stops_the_tick(
        gh, issue, state, run.agent_result, run.handed,
    ):
        return True
    if _drift_reports._reports(run.agent_result):
        return False
    _drift_reports._owes_the_undescribed(state)
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state,
        _UNFINISHED_PARK.format(mentions=config.HITL_MENTIONS),
        consumed=run.handed.watermarks,
    )
    return True


def _records_a_report_alone(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Record the report of a fix that committed nothing, and say how.

    `reported` once it is recorded, whether or not it settles later: the
    reviewer is held until it does, so the caller routes the head exactly as
    it routes a landed fix -- back to `validating` for a fresh round over the
    report and requirements being handed on.

    The head is PROVED before anything is recorded, because this road publishes
    onto one it does not push: a clean tree, a local HEAD, a remote tip, the two
    equal, and the receipt naming that commit on this pull request. Every
    refusal short of all of it -- loose work, a reading nobody could take, a
    branch carrying a commit the pull request has not got -- is a head a report
    would describe and no reviewer would read, so the round parks with nothing
    recorded but the debt, and the reply that answers the park resumes the
    session to finish the work and report again.
    """
    tree = _worktree_status._worktree_status(run.worktree)
    if not tree.is_clean:
        # The debt outlives the tree park, which names the loose files rather
        # than the report: this run DID report, and refusing to record it
        # leaves the pull request owed one all the same. Recorded here, the
        # reply that answers the park is read as the answer to the report it
        # asked for, and the park's own write carries it -- with the input this
        # prompt delivered, so the park is not one the next tick resumes over.
        state.set(_report_delivery.OWED_REPORT, True)
        _evidence._consumes_the_delivered(state, run)
        _checkout_parks._on_unpublishable_tree(
            gh, issue, state,
            _guards._ParkedRun(run.agent_result, _guards._ROUTE_DEV_FIX),
            tree,
        )
        return _state._OUTCOME_PARKED
    if not _evidence._proves_the_published_head(
        spec, issue, state, run.worktree,
    ):
        return _evidence._parks_the_unproved_head(gh, issue, state, run)
    if _records_the_fix(gh, issue, state, run):
        return _state._OUTCOME_PARKED
    state.set("silent_park_count", 0)
    return _state._OUTCOME_REPORTED


def _dispose_reported_fix(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Read what a fix round left, holding its code to the report of it.

    The disposition order is the shared one -- an interrupted run first, so a
    shutdown-killed agent parks nothing and the next tick simply retries it,
    then the timeout park -- because those two are answered before any report
    is in question. What changes behind them is only what a run with nothing
    to publish MEANS: a report is an answer this road publishes, where every
    other no-commit reply is still the question it always was.
    """
    if run.agent_result.interrupted:
        return _state._OUTCOME_PARKED
    if run.agent_result.timed_out:
        _evidence._consumes_the_delivered(state, run)
        _dev_fix._park_dev_fix_timeout(gh, issue, state, run.before_sha)
        return _state._OUTCOME_PARKED
    publishable = _dev_fix._publishable_dev_fix(spec, issue, state, run)
    if publishable is None:
        return _reads_the_silent_reply(gh, spec, issue, state, run)
    return _publishes_the_fix(gh, spec, issue, state, publishable)


def _reads_the_silent_reply(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Read a fix round that left nothing to publish: a report, or a question.

    A report comes first, because the fix prompt asks for one whenever a
    reviewer's item names report content and no repository change -- and a
    report needs no commit to be delivered, so reading it as the question it
    is not would park an issue whose developer finished.

    Nothing reaches here that the branch has anything to publish from: a
    commit an earlier run stranded is a candidate, and it goes through the
    gate whether the reply describes it or not.

    Everything else is the question this road has always read it as. The
    reviewer asked for a concrete change, so a silent reply is not an
    acknowledgement of anything: an `ACK:` on the human-feedback route is
    answered ahead of this owner, by the route that owns it.
    """
    if _drift_reports._reports(run.agent_result):
        return _records_a_report_alone(gh, spec, issue, state, run)
    _evidence._consumes_the_delivered(state, run)
    _dev_parks._on_question(
        gh, issue, state,
        _guards._ParkedRun(run.agent_result, _guards._ROUTE_DEV_FIX),
    )
    return _state._OUTCOME_PARKED


def _publishes_the_fix(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Push what the round left through the gate, its report recorded first.

    The report goes onto the comment before the gate reads the candidate,
    since past that line the gate can hold it, the push can fail, and the
    process can die -- and the session that wrote it is already gone. Binding
    it to the publication the push left is the caller's, behind its own
    bookkeeping and its relabel.

    What this prompt DELIVERED is recorded first of all, because every park
    behind this line is durable the moment it is taken: the gate's own, the
    tree's, the push's. Left to a caller's write afterwards, a process dying in
    between leaves an issue parked over feedback that still reads as unread,
    which the next tick resumes the developer over again.
    """
    _evidence._consumes_the_delivered(state, run)
    if _owes_a_report_of_its_own(run) and _records_the_fix(
        gh, issue, state, run,
    ):
        return _state._OUTCOME_PARKED
    if not _dev_fix._publish_dev_fix(gh, spec, issue, state, run):
        return _state._OUTCOME_PARKED
    return _state._OUTCOME_PUSHED


def _owes_a_report_of_its_own(run: _models._DevFixRun) -> bool:
    """Whether the report contract is THIS run's to answer before the gate.

    A run that COMMITTED owes the report of what it committed, whatever else
    the branch was already carrying, and is held here before anything of it
    may go out.

    A run that committed nothing owes one only where it wrote one. What is
    being published then is a commit an EARLIER run left unpublished, whose
    report was that run's to record -- so a reply that brought none is the
    question its own road already reads it as, and holding this run to a
    contract it never entered would park the one tick left to publish work
    the pull request is short of. The debt that earlier run left is what the
    review hold reads, and it asks a human for the report before any reviewer
    sees the head this publishes. A reply that IS a report is recorded and
    bound to that publication, since a report written over the branch as it
    stands describes the commit it sends.
    """
    if run.after_sha != run.before_sha:
        return True
    return _drift_reports._reports(run.agent_result)


def _post_requested_fix_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    *context_args,
    **fields,
) -> str:
    """Post-agent handling for a fix round that owes its report.

    Returns one of:

    * ``"pushed"`` -- a new commit, or one an earlier run stranded under a
      report that describes it, passed the size gate and reached the pull
      request. The caller closes its round and bookmarks, hands the issue back
      to `validating`, and binds the report to that publication.
    * ``"reported"`` -- the run committed nothing and ended on a report
      outcome, which is recorded for the head the pull request already
      carries. Routed exactly as a pushed fix is -- back to `validating` for a
      fresh round over the report and requirements being handed on -- with the
      reviewer held until the report is confirmed.
    * ``"parked"`` -- a timeout, a dirty tree, a push that did not land, a
      question, a report this build cannot record, or a run that committed and
      reported nothing. State already carries the park flags. A
      shutdown-killed (interrupted) run also returns ``"parked"`` but WITHOUT
      setting any park flags, posting, or publishing, so the next tick re-runs
      the round from durable state.

    The caller names what its resume was `handed`, which is what holds the run
    to the report contract: the report of a commit this run made is recorded
    before the gate, and a run that committed with none parks instead. A commit
    an EARLIER run stranded is not held to this run's contract -- its own
    report was that run's to record -- so it reaches the gate either way, and
    the debt that run left is what holds the reviewer off the head it lands on.
    """
    state, run = _models._dev_fix_run(context_args, fields)
    return _dispose_reported_fix(gh, spec, issue, state, run)
