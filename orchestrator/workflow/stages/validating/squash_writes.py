# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commit an approval's tail lands each write through, and the client its squash is handed.

The tail writes the pinned comment at points requests apart -- behind the
verify gate, the approval comment, the squash and its force-push, the notice,
the watermarks' reads, the relabel -- each decided on a reading of the
comment. Written whole from the state in hand, each would put back every field
another road moved since that reading: a report settled, a round spent, a
usage total, another verdict or approval. So each lands through the guarded
commit (`pinned_commit`) over a fresh reading instead (`lands`), under the
tick-state guard the developer report's and the reviewer round's commits use
(`report_commits.ReportCommit`): captured over the reading the tick last synced
with the comment, which every reading the tail takes lays its moves into
(`review_comment._Reread.lays_over`), owning every field the tick staged since
beside the fields each write declares, and decided on the records each write
declares (`handoff.HELD_ON`). One of those that moved under the write, an owned
field another road moved meanwhile, a comment that will not read or parse or
was replaced, and a candidate past what one comment holds refuse it with
nothing written, and the tick's state is withheld from every whole-state write
behind it. So does an edit GitHub took and never confirmed: nothing acts on it,
and the records it may have left settle it on a later tick.

The squash writes the state in hand wherever it writes -- the collapse record
ahead of its rewrite (`COLLAPSE_RECORDS`), the size gate's own records -- and
what it hands back does not say whether it wrote at all: a branch with nothing
to rewrite, or an install that makes no new collapse, writes nothing. Every
write the tail makes behind it is laid over the comment measured from the
comment as the tail last read or wrote it (`handoff._Held`), so that last
write has to be known rather than guessed. Measured from the comment read
before a squash that wrote, a move the squash's write already carried -- a
usage total -- reads as another road's and is added a second time. Taken whole
over the comment behind a squash that wrote nothing, a field another road
wrote while it ran -- a round a reply spent -- is written back over.

Nor may a write of the squash's own put back what another road wrote ahead of
it. Its first write comes a request or more after the tail last read the
comment, and a report settled, a round spent, or a verdict replaced in that
time would be written over by the older state in hand -- and then read back
by the tail as the records its approval stands on. So each write is held
first to the report, pull-request, verdict, and evidence records the state in
hand carries, laid over the comment as read then, and landed through the same
guarded commit (`handoff._Held.follows`), exactly as the tail's own writes are.
One whose records moved, or whose commit did not land, is refused the way
GitHub refusing it would be: the squash already answers that by not rewriting
where the write is the record ahead of its rewrite, and past the rewrite by
leaving the collapse it recorded for the next tick's recovery, which holds the
relabel to an approval that no longer covers the report. A refused write
leaves behind it nothing it took in on the way: the reading that held it laid
the fresh comment over the state in hand and took it as the one the state is
synced with and the tail last read, and the squash puts back only the state's
fields -- so left advanced, a field another road wrote would read to the next
commit as one the tick deleted, and be taken off the comment. The state, the
reading it is synced with, and the comment as the tail last read it are put
back together.

So the squash is handed its gate with a client that passes every call through,
and guards each write of the issue's own pinned comment and hands it on, once
it lands, as the one the tail last wrote. A write of another issue's -- a
child the size gate files -- is not this comment, and is neither.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit_models as _commit_models, report_commits as _commits
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs

log = logging.getLogger("orchestrator.workflow")

# The collapse a squash records ahead of its rewrite, and the handoff its tail
# leaves in that record's place once the rewrite is published and announced.
COLLAPSE_RECORDS = frozenset((
    _collapses.LATE_COLLAPSE_HEAD,
    _collapses.LATE_COLLAPSE_BASE_SHA,
    _collapses.LATE_COLLAPSE_COUNT,
    _late_handoffs.LATE_COLLAPSE_HANDOFF,
))


class _Unwritten(RuntimeError):
    """A squash's write refused: the comment moved the records it was taken under, or its commit did not land."""


class _FollowsItsWrites:
    """`gh` for one squash of `issue`'s branch: every call passed through, each write of its comment guarded."""

    def __init__(
        self,
        gh: GitHubClient,
        issue: Issue,
        holds: Callable[[PinnedState], bool],
        lands: Callable[[PinnedState], bool],
        held,
    ) -> None:
        self._gh = gh
        self._issue_number = issue.number
        self._holds = holds
        self._lands = lands
        self._held = held

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def write_pinned_state(self, issue: Issue, state: PinnedState) -> PinnedState:
        """Land `state` through `lands` where `holds` lets it; a write of another issue's comment passes through.

        One `holds` refuses, or whose commit does not land, raises rather than
        being taken for a write that landed, with `state`, the reading it is
        synced with, and the comment as the tail last read it each put back as
        the write found them.
        """
        if issue.number != self._issue_number:
            return self._gh.write_pinned_state(issue, state)
        fields = copy.deepcopy(state.data)
        synced, comment = state.synced, self._held.comment
        if not (self._holds(state) and self._lands(state)):
            state.data.clear()
            state.data.update(fields)
            state.synced = synced
            self._held.comment = comment
            raise _Unwritten(
                f"issue #{issue.number}'s pinned comment did not take the write its squash made: it no longer "
                "carries the report, pull-request, verdict, or evidence records the squash was taken under, "
                "or the guarded commit did not land",
            )
        return state


def followed(
    gate,
    holds: Callable[[PinnedState], bool],
    lands: Callable[[PinnedState], bool],
    held,
):
    """`gate` with a client asking `holds` before each write of its issue's comment, and landing it through `lands`.

    `held` is what the tail holds (`handoff._Held`), whose last reading of the
    comment a write that does not land leaves as it found it.
    """
    return replace(gate, gh=_FollowsItsWrites(gate.gh, gate.issue, holds, lands, held))


def lands(
    gh: GitHubClient, issue: Issue, state: PinnedState, write: _commits.ReportWrite,
) -> _commit_models.CommitOutcome:
    """Commit what `state` staged as `write` over the fresh comment; the commit's outcome.

    Where it is COMMITTED `state` reads as the comment does, and is synced
    with it. Where it is not -- refused, or sent and never confirmed --
    nothing was written over the comment, `state` is withheld from every
    whole-state write behind it (`report_commits.ReportCommit.withholds`), and
    the caller posts, relabels, and reports nothing that depends on the write.
    A candidate `write.admits` refused is answered as the refusal it is
    (INADMISSIBLE), its answer kept on the outcome.
    """
    landed = _commits.ReportCommit(gh, issue, state).lands(state, write)
    if not isinstance(landed, _commit_models.CommitOutcome):
        landed = _commit_models.CommitOutcome(
            _commit_models.CommitStatus.REFUSED,
            refusal=_commit_models.CommitRefusal.INADMISSIBLE,
            inadmissible=landed,
        )
    if landed.status is not _commit_models.CommitStatus.COMMITTED:
        log.warning(
            "issue=#%d its approval's write did not land (%s); posting, relabeling, "
            "and acting on nothing behind it", issue.number, (landed.refusal or landed.status).value,
        )
    return landed
