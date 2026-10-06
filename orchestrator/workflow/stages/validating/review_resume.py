# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a reviewer's verdict an earlier tick persisted and never disposed of, spending nothing twice.

A returned reviewer's verdict is persisted before its evidence is published or
the verdict acted on (`review_disposition`), so a tick that ended in between
-- a publication GitHub never confirmed, a proof nobody could read, a feedback
post that failed, a relabel or a developer launch that never landed, a
process that died -- leaves it on the pinned comment. The next tick finishes
it here and runs no reviewer: the one that returned was charged for its run,
its usage and session were written with the verdict, and the round it ran as
is the one the verdict names, so nothing here charges a run, folds usage, or
spends a round of its own. By then the dispatcher's reconciliation has
published and settled the evidence the verdict claims, or held the tick before
any handler, so what is left is the disposition itself.

A change request is finished from its record alone, and held to the round,
subject, claim, receipt, and anchor that record was persisted and handed
with, read as written. Only the words it hands on are formatted as they go
out (`review_handoffs.HandedLaunch.of`): a record persisted before findings
were formatted, its verification declaration still raw, posts -- where its
feedback was never posted -- and resumes its developer on the concise
findings, with the record's feedback never rewritten, no evidence read again
off those words, and a post already made never made again -- a park's
`/orchestrator continue` quoting that post's findings formatted
(`feedback_posts`).

On `workflow:validating` (`resumes_a_returned_verdict`) it is asked ahead of
the round-cap check and the spawn. A verdict never handed over is finished
through a run rebuilt of its own round over the subject resolved again exactly
as a round resolves it -- the pull request's head, the settled report re-read
at its location, and the requirements of the issue fetched afresh -- which has
to be the subject the verdict records: a push, a new or edited report, or an
edit of the issue since is work nobody reviewed, so the verdict is dropped for
good and the tick ends there, for the next tick to hand a fresh reviewer the
subject as it stands, or refuse it. That drop is a guarded commit
(`engine/pinned_commit.py`) captured over the comment read afresh, made only
while it still carries that verdict (`_drops_it`), with nothing of this tick's
in it but the drop: staged instead, it would ride the round's writes and put
`null` back over a verdict another road recorded in its place meanwhile, and
one recorded between that reading and the commit refuses it with nothing
written. A reading nobody could take ends
the tick with nothing written, for the next one to ask again. The checkout the
verdict is finished in is restored only behind that reading, since a stale
verdict is dropped over GitHub's readings alone: a checkout that will not
restore ends the tick, the verdict waiting, only where the subject still
stands. A change request already handed, whose relabel to `workflow:fixing`
never landed, is relabelled and its developer launched without its feedback
posted again (`review_handoffs.hands_the_waiting_request_over`), its checkout
restored only once the handoff has held it to its subject -- while that launch
is still owed (`review_handoffs.HandedLaunch.owed`). One whose developer may
have been launched is dropped the same way instead, for the next tick's round,
once its subject is read afresh -- a reading nobody could take holds it: the
relabel is made before the launch, so only a relabel from outside brings such
a verdict back. That drop rests on the run ledger, so the comment read for it
has to show the launch not owed still, and its commit is decided on the
ledger as well (`_LAUNCHED_DROP`): a start written away, its charge left
unstarted, drops nothing, and the next tick launches the developer owed,
honoring that charge. Nor is a verdict finished on a tick an awaiting-human park was
cleared into: that reply bought a fresh round of its own, so the verdict the
park outlived is dropped, only where the comment still carries it, in the one
guarded commit that settles the tick -- captured over the comment read afresh,
keeping the cleared park and carrying what another road wrote meanwhile, a
park it recorded kept as it wrote it, and decided on the verdict and the
park's flags as that reading spells them (`_BOUGHT_ROUND`), so a verdict
another road records, or a park it records or clears, after that reading
refuses it, and the next tick answers the reply again -- and the round runs on
the next tick (`settles_a_bought_round`).

On `workflow:fixing` (`finishes_a_handed_request`) it is asked ahead of the
feedback scan, whose no-feedback bounce would otherwise walk past it: the
feedback is a comment this orchestrator posted, which the scan filters out, so
the bounce would return an unchanged head to review and pay a second reviewer
for a round already reviewed. A handed request whose developer is still owed
has that one developer launched, with no relabel: the issue is on
`workflow:fixing` already. One whose launch may have run is never launched
again, and is held to what it was reviewed on first: the subject resolved again
as the validating tick resolves it, the evidence it claims still the settled
evidence, and the branch read against its pull request. A moved subject or
claim, a commit the pull request has not got, loose work in the checkout, or a
remote that moved past it -- the developer's own work, or a review nobody is
asking about any more -- drops the verdict for good, the same way and on the
same ledger, and the next
tick's own road publishes that work, or holds its bounce over it, and hands the
pull request back for review; a reading nobody could take -- the branch's
included: a fetch, a status, or a count that did not return -- holds the tick,
the verdict kept for a later reading (`review_launch_park.has_moved_on`); and
anything else parks the launch for `/orchestrator continue`
(`review_launch_park.parks`). While a park
stands -- the run circuit's over a spent allowance it refused the launch on,
say -- the hook stands down: the park's own dispatch answers the reply it waits
on, and the launch is asked for again once it clears.

Either launch is made only behind the feedback anchor the handoff was written
beside, and a pinned `pending_fix_reviewer_comment_id` something cleared since
-- the fixing stage's bookmark clear, a report settlement writing the
bookkeeping it froze -- is written back first from the record's own `anchor`,
which names that very post, in a guarded commit captured over the comment read
again (`_ANCHOR_BACK`) -- only once the subject is established, since that is
the first write this road makes, and a subject nobody could read holds the tick
with nothing written; the park writes it back in its own commit, since that
anchor is what its `/orchestrator continue` replays. Records that moved on
that comment -- a verdict another road put in this one's place, say -- end the
tick with nothing written or handed over, for the next tick to read the
comment as it stands, and so do records, or an anchor, another road moves
between that reading and the commit. An anchor another road pointed elsewhere
is left for the handoff, or the park, to hold.

Every write here lands through that guarded commit under the tick-state guard
the validating reviewer writes share (`review_writes.lands`), so a refusal
writes nothing and withholds the tick's state from every whole-state write
behind it, and a commit GitHub took and never confirmed is acted on no
further: the next tick reads what the comment carries and finishes it from
there -- the round run, the verdict found dropped, the anchor found written and
the launch made -- with no second reviewer, post, developer, or charge, and no
review round but the one the confirmed write itself leads to: the round a
reply bought, or the fresh round a dropped verdict leaves its subject for.
"""
from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_context as _prompt_context,
    report_commits as _commits,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_disposition as _disposition,
    review_handoffs as _handoffs,
    review_launch_park as _launch_park,
    review_report as _review_report,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
)

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

_AWAITING_HUMAN = "awaiting_human"

# The write that settles a tick a reply bought a fresh round on: the round,
# the cleared park, and whatever else the tick staged, and the verdict the
# park outlived dropped. Decided on that verdict and on the park's flags as
# the reading behind the reply spells them, so a verdict another road put in
# its place, or a park recorded or cleared meanwhile, refuses it.
_BOUGHT_ROUND = _commits.ReportWrite(
    owned=frozenset((_verdicts.RETURNED_VERDICT,)),
    decided_on=_review_writes._PARK_FLAGS | {_verdicts.RETURNED_VERDICT},
)

# The drop of a handed request whose developer the run ledger shows may have
# run: decided on that ledger as well, the proof the launch is no longer owed,
# so a start written away -- its charge put back unstarted -- before the
# commit refuses the drop, and the next tick launches the developer owed.
_LAUNCHED_DROP = _review_writes.DROP.deciding_on(*_handoffs.RUN_LEDGER)

# The write-back of a handed request's anchor something cleared: decided on
# what the request stands on, on that anchor, still cleared, and on the park's
# flags, as the comment spells them -- a park another road recorded is a
# human's to answer, and no launch is readied under it.
_ANCHOR_BACK = _commits.ReportWrite(
    owned=frozenset((_verdicts._FEEDBACK_ANCHOR,)),
    decided_on=_review_writes.VERDICT_STANDS_ON | _review_writes._PARK_FLAGS | {_verdicts._FEEDBACK_ANCHOR},
)

# The run a waiting verdict is finished through: no process was invoked for
# it, and nothing a disposition reads comes from its output -- the feedback a
# change request hands on is the persisted verdict's own.
_RESUMED_RUN = AgentResult(
    session_id=None,
    last_message="",
    exit_code=0,
    timed_out=False,
    stdout="",
    stderr="",
    invoked=False,
)


def settles_a_bought_round(
    gh: GitHubClient, issue: Issue, state: PinnedState, read: dict, held: bool,
) -> bool:
    """On a tick a reply cleared a park into a fresh round: whether the tick ends here rather than running that round.

    `read` is the pinned comment as the tick read it, and `held` whether the
    report hold stops the round. The round runs this tick only where the hold
    lets it and no verdict waits. Otherwise one guarded commit settles the
    tick (`_BOUGHT_ROUND`), captured over the comment read afresh against
    `read` (`review_comment._records_stand`): what another road wrote there meanwhile
    -- a run charged, an allowance granted, a verdict recorded -- is carried,
    and this tick's own moves -- the cleared park and the round the reply
    bought -- are kept, save a park another road recorded there, told by its
    flags moving (`review_comment._Reread.parks_anew`), which is kept as that
    road wrote it: the clear answers the park the reply was to, not one
    recorded since. The verdict the park outlived is dropped in that write,
    only where the comment still carries it: the round is the reply's own, and
    a verdict another road recorded in its place is kept for the next tick to
    finish. The round the reply bought runs on the next tick, over the comment
    as it stands then. A park recorded again for the same reason moves no
    flag, and shows only in its notice, which nothing on the comment names: so
    a comment another road posted meanwhile naming the human a park waits on,
    which a status line may do too, writes nothing, and the next tick answers
    the reply again over the comment as it stands -- the grant or
    `/orchestrator continue` the reply was, unrecorded, answered then. So does
    a comment that will not read, or a thread of another road's posts that
    will not, and a commit refused over a verdict, or a park, another road
    moved after that reading.
    """
    waiting = _verdicts.read_returned_verdict(state)
    if not held and waiting is None:
        return False
    ours = _comments._orchestrator_ids(state)
    reread = _review_comment._records_stand(gh, issue, state, read)
    if reread is None:
        return True
    # What another road posted meanwhile is in the ledger that reading merged
    # onto `state`, and nowhere in `ours`.
    parked = reread.parks_anew(gh, issue, read, _comments._orchestrator_ids(state) - ours)
    if parked is None:
        return True
    if parked:
        log.warning(
            "issue=#%d another road parked it, or moved its park, while the round "
            "its reply bought was settled; keeping that park as it was written", issue.number,
        )
        reread.keeps_the_park(state)
    if _verdicts.drops_the_verdict(state, only=waiting):
        log.info(
            "issue=#%d drops the reviewer verdict it had waiting: a reply to its "
            "park bought a fresh round", issue.number,
        )
    _review_writes.lands(gh, issue, state, _BOUGHT_ROUND)
    return True


def resumes_a_returned_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """On `workflow:validating`, finish the verdict this issue has waiting; whether this tick is over.

    False where there is none to finish -- a record no reader takes is none,
    and is left as it stands. One dropped for a fresh round is dropped for
    good before that round runs (`_drops_it`), and the tick ends there, so the
    next tick's round reviews the subject as it stands -- ahead of the
    checkout's restore, which only a verdict still standing is finished in. A
    handed one whose developer may have run is dropped so too, but only over
    its subject resolved again, like any other (`_resumed_run`): a reading
    nobody could take holds it with nothing written.
    """
    waiting = _verdicts.read_returned_verdict(state)
    if waiting is None:
        return False
    launch = _handoffs.HandedLaunch.of(gh, spec, issue, state, waiting)
    if waiting.handed is not None and launch.owed():
        return _hands_over(launch)
    held, run = _resumed_run(gh, issue, state, waiting, launch.context.wt)
    if run is None:
        return held
    if waiting.handed is None:
        # Restored only behind the subject: a verdict whose subject moved is
        # dropped over GitHub's readings alone, so a checkout that will not
        # restore never keeps a stale verdict pinned.
        wt = _worktree_creation._ensure_worktree(
            spec, issue.number, branch=_naming._resolve_branch_name(state, spec, issue.number),
        )
        _disposition.finishes_the_verdict(gh, spec, issue, state, run.in_checkout(wt))
        return True
    log.info(
        "issue=#%d drops the reviewer verdict it had waiting: the developer "
        "it was handed to may have run", issue.number,
    )
    _drops_it(gh, issue, state, waiting, launch)
    return True


def finishes_a_handed_request(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """On `workflow:fixing`, launch the developer a handed change request never reached; whether this tick is over.

    False where there is nothing to hand -- no verdict, or one never handed --
    and while a park stands: the stage's own road runs then, and a park's own
    dispatch answers the reply it waits on -- a spent run allowance the launch
    was refused over, say -- with the launch asked again once it clears. One
    whose launch may have run and has moved on is dropped for good
    (`_drops_it`), and the next tick's road publishes whatever work is there
    and hands the pull request back.
    """
    handed = _verdicts.read_returned_verdict(state)
    if handed is None or handed.handed is None or state.get(_AWAITING_HUMAN):
        return False
    launch = _handoffs.HandedLaunch.of(gh, spec, issue, state, handed)
    if launch.owed():
        return _hands_over(launch)
    run = _resumed_run(gh, issue, state, handed, launch.context.wt)[1]
    if run is None:
        return True
    moved_on = partial(_launch_park.has_moved_on, spec, issue, state, handed, run.wt)
    moved = moved_on()
    if moved is None:
        log.warning(
            "issue=#%d could not read where the branch stands for the developer its "
            "handed change request owed, which may have run; holding the verdict",
            issue.number,
        )
    elif moved:
        log.info(
            "issue=#%d the developer its handed change request owed may have run "
            "and left work, or its claim moved; dropping the verdict for the stage's road",
            issue.number,
        )
        _drops_it(gh, issue, state, handed, launch)
    else:
        _launch_park.parks(launch, moved_on)
    return True


def _hands_over(launch: _handoffs.HandedLaunch) -> bool:
    """Relabel and launch the one developer `launch` owes, its lost anchor written back first; whether the tick is over.

    The anchor is written back only once the subject the request stands on is
    established, since that write is the first this road makes: a subject or
    thread nobody could read holds the tick with nothing written, and a moved
    one drops the verdict for good (`_resumed_run`). It is committed over the
    comment read again, and only where the anchor is still cleared there --
    another road's anchor is the handoff's to hold (`_writes_the_anchor_back`).
    Nothing is handed over where that comment will not read, where the records
    moved there, or where the commit did not land: a verdict another road put
    in this one's place is that road's to finish, and the next tick reads the
    comment as it stands. Past that the
    handoff holds the launch to what stands itself -- the subject, the
    claimed evidence, the run ledger, and the anchor -- and drops, retires, or
    holds the verdict as what moved says.
    """
    context, handed = launch.context, launch.handed
    if handed.anchor is not None and context.state.get(_verdicts._FEEDBACK_ANCHOR) is None:
        held, run = _resumed_run(
            context.gh, context.issue, context.state, handed, context.wt,
        )
        if run is None:
            return held
        if not _writes_the_anchor_back(launch):
            return True
    log.info(
        "issue=#%d hands its waiting change request to the developer it owes, "
        "without a second reviewer", context.issue.number,
    )
    _handoffs.hands_the_waiting_request_over(context.gh, context.spec, context.issue, context.state)
    return True


def _writes_the_anchor_back(launch: _handoffs.HandedLaunch) -> bool:
    """Write back the feedback anchor `launch`'s request records, over the comment read again; whether to hand over.

    The comment is read against the state in hand (`review_comment.
    _records_stand`): one that will not read, or whose records moved -- a
    verdict another road put in this one's place, say -- hands nothing over,
    and the next tick reads it as it stands; so does one showing a park
    another road recorded since the tick read the comment, which is a human's
    to answer and is left exactly as it was written. An anchor that reading
    carries is another road's, and the handoff's to hold, so nothing is
    written over it. A cleared one is written back from the verdict's own in
    a guarded commit (`_ANCHOR_BACK`) captured over that reading, which a
    record moved after it, a park recorded, or an anchor written meanwhile
    refuses with nothing written; one GitHub never confirmed is written back
    again, or found written, by a later tick.
    """
    context = launch.context
    reread = _review_comment._records_stand(
        context.gh, context.issue, context.state, dict(context.state.data), persisted=True,
    )
    if reread is None or not reread.stood:
        return False
    if context.state.get(_AWAITING_HUMAN):
        log.warning(
            "issue=#%d a park stands on its pinned comment; writing back no "
            "feedback anchor and handing nothing over under it", context.issue.number,
        )
        return False
    if context.state.get(_verdicts._FEEDBACK_ANCHOR) is not None:
        return True
    log.info(
        "issue=#%d writes back the feedback anchor its handed change "
        "request records, comment %s", context.issue.number, launch.handed.anchor,
    )
    context.state.set(_verdicts._FEEDBACK_ANCHOR, launch.handed.anchor)
    return _review_writes.lands(context.gh, context.issue, context.state, _ANCHOR_BACK)


def _drops_it(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    waiting: _verdicts.ReturnedVerdict,
    launched: _handoffs.HandedLaunch | None = None,
) -> None:
    """Drop `waiting` for good, in a guarded commit over the comment read afresh, only while it still carries it.

    Staged on the state in hand instead, the drop would ride the writes of
    whatever runs behind it -- a fresh reviewer's round, the fixing stage's
    bounce -- and put `null` back over a verdict another road recorded in its
    place meanwhile. So the comment is read again and committed with nothing
    of this tick's in it but the drop (`review_writes.DROP`), decided on the
    records the verdict stands on as that reading spells them, and the caller
    ends the tick: the next one reads the comment as it stands. Nothing is
    written where it will not read, where it carries another verdict than
    `waiting`, or where one of those records moves before the commit lands.

    `launched` is the launch the request owes where the drop rests on its run
    ledger showing that launch may have run. That reading has to show it
    still: a launch owed there again -- its start written away, its charge
    left standing unstarted -- drops nothing, and the next tick launches the
    developer owed, honoring that charge. The commit is decided on the run
    ledger too (`_LAUNCHED_DROP`), so a move of it after that reading refuses
    the drop with nothing written.
    """
    fresh = _review_comment._read(gh, issue, state, "drop the reviewer verdict it had waiting")
    if fresh is None:
        return
    if launched is not None and launched.owed(fresh):
        log.info(
            "issue=#%d the run ledger read afresh owes the developer launch its "
            "handed change request may have run; dropping nothing", issue.number,
        )
        return
    if _verdicts.drops_the_verdict(fresh, only=waiting):
        _review_writes.lands(gh, issue, fresh, _review_writes.DROP if launched is None else _LAUNCHED_DROP)


def _resumed_run(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    waiting: _verdicts.ReturnedVerdict,
    wt: Path,
) -> tuple[bool, _models._ReviewerRun | None]:
    """The run `waiting` is finished through in `wt`, rebuilt over the subject standing now, or why there is none.

    `(False, run)` where the subject the verdict records stands, and
    `(True, None)` where the tick ends: a reading could not be taken, which
    writes nothing, or the subject moved, which drops the verdict for good
    (`_drops_it`) for the next tick's road to review the subject as it
    stands -- the validating round, or the fixing stage's bounce back to it.
    """
    # The requirements are read off the issue fetched afresh, as a returned
    # reviewer's subject is resolved again: the issue in hand was fetched
    # before anything else this tick asked, and an edit since is a subject
    # nobody reviewed.
    try:
        delivered = _prompt_context._delivered_thread(gh, gh.get_issue(issue.number), state)
    except Exception:
        log.exception(
            "issue=#%d could not read the issue or its thread to resolve the "
            "subject its waiting reviewer verdict is about; holding the verdict",
            issue.number,
        )
        return True, None
    subject, refusal = _review_report._reads_the_subject(
        gh, issue, state, state.get(_PR_NUMBER), delivered.requirements_revision or "",
    )
    if subject is None and not refusal:
        return True, None
    if subject is None or subject.recorded() != waiting.subject:
        log.info(
            "issue=#%d the subject its waiting reviewer verdict is about no "
            "longer stands; dropping it for a fresh review", issue.number,
        )
        _drops_it(gh, issue, state, waiting)
        return True, None
    resolved_over = _review_comment._resolved_over(gh, issue, state, "finish the reviewer verdict it has waiting")
    if resolved_over is None:
        return True, None
    return False, _models._ReviewerRun(
        wt=wt,
        round_n=waiting.round_n,
        pr_number=state.get(_PR_NUMBER),
        agent_result=_RESUMED_RUN,
        delivery=delivered,
        subject=subject,
        resolved_over=resolved_over,
    )
