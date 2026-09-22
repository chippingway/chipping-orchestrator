# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one fresh reading of the pull request a fixing report is about.

Two roads in `reporting` need it and neither may carry a copy: the round that
would publish with no commit at all, which has to prove the pull request is
still standing where its run found it, and the binding, which has to prove the
same pull request is the publication the record is about before it posts onto
it. Answered twice, the two would come to disagree, and the disagreement they
would reach is a report on a thread nobody meant.

Read AFRESH rather than off the copy the preflight fetched, because that copy
was taken before the developer ran: a push, a merge, a close and a description
edit in those minutes are each invisible in it.

What the reading establishes is the whole IDENTITY of the publication, the way
`engine/report_publication_evidence.py` establishes it for a transaction the
reconciliation is finishing. The thread has to be OPEN, since one somebody
merged or closed mid-run keeps the head it had and every other comparison
passes on a publication that is over. Its head ref has to be this issue's
branch and its head repository has to be ours, because a pull request's number
is the only thing that brought this object back: a second thread on another
branch, or a fork's -- which carries this repository's ref names over somebody
else's commits -- can stand on the very commit a caller proved, and a report
bound to one of those is published onto a thread the record was never about,
with the branch and repository of the one it was. And the head has to BE that
commit rather than merely carry it, since a push landing between the proof and
this reading leaves the commit in the thread's history while the work under
review is no longer the work the report describes.

EVERY read is inside one boundary, the fetch included and nothing only around
it. A fetched pull request asks GitHub nothing; what can fail is the attribute
read behind it -- the state, the head ref, the head repository, the head sha,
the body -- and the client resolves its own repository lazily too. Wrapped
around the lookup alone, any one of those leaves this reading by an exception
rather than by an answer, through the dispatcher and out of the tick, which is
the one thing a reading here may never do. Assembled from parts that each fell
back to an answer of their own it would be no better: a publication proved
against a world nobody saw whole.

The DESCRIPTION rides the same boundary for that reason, and because a caller
that has to ask it has to ask it of this object: one report this workflow
cannot both keep and manage is a `REPORT: VERIFIED` naming that very body, and
the binding refuses that one only if it is told -- the reading it assumes
otherwise is that the description is safe.

No dispatched fixing road reaches this owner, exactly as none reaches the two
in `reporting` that ask it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.workflow.engine import report_locations as _report_locations
from orchestrator.workflow.stages.fixing import models as _models
from orchestrator.workflow.stages.implementing import dev_pr as _dev_pr

log = logging.getLogger("orchestrator.workflow")

# The one pull request state a report may be published onto. A merged or
# closed thread keeps the head it had, so nothing else this reading compares
# would notice that the publication it is about is over.
_PR_OPEN = "open"


@dataclass(frozen=True)
class _Standing:
    """What one fresh reading of this issue's pull request established.

    `pull_request` is the object the reading was taken ON, and its presence is
    the whole of what says the reading PROVED: this is the publication the
    record is about, it is open, it is on this repository's own branch, and it
    is standing on the commit the caller proved. It travels rather than being
    fetched again, so what a caller refuses on and what it writes to are one
    reading.

    `describes_the_issue` rides with it because it is a reading of the same
    object under the same boundary: whether the description still closes this
    issue and names the session that wrote the branch.

    `unread` is the one refusal a caller may not act on. Every other answer
    here is a reading this call TOOK -- a thread that ended, a branch that
    disagrees, a fork, a head that moved -- and the tick carries on to
    whatever answers it. A request that failed says nothing about the branch,
    the description or the head, so a caller that spent it on a park would
    tell a human this issue is stuck on the strength of a read that did not
    happen.
    """

    pull_request: Any = None
    describes_the_issue: bool = True
    unread: bool = False


def _stands_on(ctx: _models._FixingContext, commit: str) -> _Standing:
    """Read this issue's pull request afresh and hold it to `commit`.

    One boundary around the whole reading, which is what the split below is
    for: the fetch, every lazy member behind it, and the repository the client
    resolves to answer whose fork a head is in are all requests, and a caller
    is owed the same answer on any of them failing.
    """
    try:
        return _identified(ctx, ctx.gh.get_pr(ctx.pr.number), commit)
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%s to say whether it is the "
            "publication this round's report is about and standing on %s; "
            "holding everything where it stands for a tick that can",
            ctx.issue.number, getattr(ctx.pr, "number", None), commit,
        )
        return _Standing(unread=True)


def _identified(
    ctx: _models._FixingContext, published: Any, commit: str,
) -> _Standing:
    """Prove the object that came back is the publication in hand.

    Spelled apart from the boundary above so that every read it makes is under
    that one boundary rather than each being wrapped where it stands, and
    taken up front rather than one comparison at a time for the same reason:
    a reading assembled as it goes is one whose later members are only asked
    where its earlier ones agreed, and what a caller is owed on any of them
    failing is the same answer.

    Four facts, and a publication this report may go onto has all four. The
    thread is OPEN, since one somebody merged or closed keeps the head it had.
    Its head ref is this issue's branch and its head repository is ours, which
    is what says this is the publication the record is about rather than one
    wearing its number. And its head IS the commit the caller proved, which is
    what says the work under review is the work the report describes.
    """
    state = _pr_reads.pr_state(published)
    head = getattr(published, "head", None)
    standing = getattr(head, "sha", None)
    own_branch = getattr(head, "ref", None) == _naming._resolve_branch_name(
        ctx.state, ctx.spec, ctx.issue.number,
    )
    own_repo = ctx.gh.is_own_repository(
        getattr(getattr(head, "repo", None), "full_name", None),
    )
    if state != _PR_OPEN or standing != commit or not (own_branch and own_repo):
        log.warning(
            "issue=#%d proved its developer report on commit %s and PR #%s is "
            "%s, standing on %s, on this repository's own branch: %s; holding "
            "the report rather than publishing it onto a publication it is "
            "not about",
            ctx.issue.number, commit, getattr(published, "number", None),
            state, standing or "a head nothing could read",
            own_branch and own_repo,
        )
        return _Standing()
    return _Standing(
        pull_request=published,
        describes_the_issue=_report_locations.describes_the_issue(
            published, ctx.issue.number,
            _dev_pr._dev_pr_attribution(ctx.state), ctx.gh.repo_slug,
        ),
    )
