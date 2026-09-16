# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a squash hands back, in the three shapes it can end in.

One record rather than a tuple, because the third shape is what a tuple of
flags could not carry honestly: a candidate the size gate held is neither the
success a caller hands on nor the failure it parks over, and reading it as
either is how an adjudication ends up with a park notice on top of it or a
handoff underneath it.

It sits here rather than beside the owner that builds it because three owners
read it -- the entry point that composes the squash, the rewrite that produces
it, and the stage handler that acts on it -- and a record every one of them is
typed by belongs to none of them. `planning._SquashPlan` stays with the owner
that builds it for the opposite reason: nothing outside that step reads a plan.
"""
from __future__ import annotations

from dataclasses import dataclass

# The four places a failed squash can leave the branch, named because the
# notice behind one is what an operator acts on and no two of them are the
# same errand. INTACT is the ordinary failure: it aborted before anything
# destructive or restored what it rewound, so the commits a reviewer approved
# are at HEAD and squashing by hand starts from them. COLLAPSED is a failure
# taken over a rewrite an earlier tick left standing -- the approved history is
# off the tip, and reachable only from the head the record names. BURIED is a
# branch that grew PAST that head instead: nothing was rewritten and the
# approved commits are in the branch's own history, under whatever was
# committed on top of them, so an operator sent to the reflog would be sent
# past the commits they are looking for. UNKNOWN is none of them shown: a
# record this build cannot read whole, a recorded head no object here answers
# to, or a checkout that would not report the head it is on. Told apart rather
# than folded into a flag, because a notice that guesses between them sends a
# human looking for commits that are not where it says.
BRANCH_INTACT = "intact"

BRANCH_COLLAPSED = "collapsed"

BRANCH_BURIED = "buried"

BRANCH_UNKNOWN = "unknown"


@dataclass(frozen=True)
class _SquashOutcome:
    """What one squash-and-publish did.

    `success` with a `sha` is the ordinary shape: the branch was rewritten and
    the remote force-pushed to match, `count` naming how many commits the one
    commit on it replaced and 0 meaning there was nothing for this call to
    rewrite -- no commits over the base, or a single one already committed
    under the subject a publication gives it. One is the branch rewritten for
    its SUBJECT alone: a commit was made and pushed, and no history was
    replaced by less of it, which is why the notice a handoff posts is owed
    only above that. A failure carries the `error` its caller parks with and
    leaves the original commits on the branch.

    `standing` is what a FAILURE says about the branch it is leaving behind,
    and it names one of three places rather than answering yes or no. The
    caller words a human's notice from it, and each of the three sends an
    operator somewhere different.

    `held` is neither, and it is the gate having taken the issue out of this
    caller's hands in one of two shapes. RECORDED, something durable names the
    squashed commit -- an oversized generation the adjudication is deciding
    about, or a frozen pair whose count never came back -- and the commit
    stays on the branch for the verdict or the reconciliation that answers it.
    REFUSED, the gate could not take its reading at all and froze nothing -- a
    pull request a human closed mid-rewrite, a head somebody moved under it --
    and it has already parked with the notice that reading earned, while the
    branch has been put back where the squash found it so the retry has
    commits to squash, measure, and publish afresh. On both the caller must
    neither park over the gate's own answer nor carry on with a handoff.
    """

    success: bool = False
    sha: str | None = None
    count: int = 0
    error: str | None = None
    held: bool = False
    standing: str = BRANCH_INTACT
