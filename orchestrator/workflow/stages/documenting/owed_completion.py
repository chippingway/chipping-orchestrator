# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A docs pass already finished whose completion a later tick still owes, finished with no second agent run.

Three records say a pass finished and its completion was not seen through,
and each is finished from what it proves rather than by running the pass
again -- which would commit a second time over published work, and spend a
run the issue already paid for.

The receipt the size gate leaves (`docs_settled_sha`) says a pass published a
docs commit, or had it held: the gate writes it in its own routed write,
ahead of everything this stage does with a landed push, so a push whose
answer was lost, a completion refused, never confirmed, or cut short, and the
authorized settlement that publishes a held commit and hands the label back
here all leave it standing. It is told apart from an unpublished candidate two
ways. Where the code-publication receipt names it as published on the pinned
pull request, no park stands, and this host's checkout stands on it, the
completion is finished at once (`_finishes_an_owed_completion`), ahead of
every question about the approval it followed: a run of the docs commit is
evidence the approval's own claim was never given, and asked first it would
send the issue back to review over its own verification. Otherwise by the
checkout (`_finished_settled_docs`): a commit still ahead of the remote is
republished through the gate, and only one the branch is level with AND
standing on is completed without a second pass -- which is also how a park
standing over a published pass is answered once a human replies.

A completion whose write landed and whose relabel did not leaves no receipt:
the write consumed it. What it leaves is the completion record itself
(`docs_final_provenance`) and the stamp beside it, and together they say the
pass finished -- the record still following the approval this issue records,
naming the stamped head as the one it completed on, with the verdict that
head earns stamped beside it (`_established`). So the relabel is finished
from them, writing nothing. A later approval of any subject is distinguished
by the verdict it retires (`review_subjects.record_approved`), and a pass
that has begun since drops it too (`run`), so neither is ever taken for this
one, and the pass the later approval bought runs.
"""
from __future__ import annotations

import logging

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import final_docs_records as _final_docs
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.documenting import (
    final_completion as _final_completion,
    handoff as _handoff,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The revision a checkout's own head is named by.
_HEAD = "HEAD"

_SETTLED_DOCS_NOTICE = (
    ":books: documenting pass: docs commit `{commit}` is already on this pull "
    "request; this tick finished the handoff it was still owed. No second "
    "pass was run."
)


def _finishes_an_owed_completion(ctx: _models._DocumentingContext) -> bool:
    """Finish a completion the records prove owed, ahead of every question about its approval; True where handled.

    A published pass whose receipts prove its publication, with no park
    standing and this host's checkout on it, is completed -- verified,
    recorded, announced, and handed to `in_review` behind a landed write --
    whether or not that write lands. A completion whose write already landed
    is relabelled to `in_review` and nothing else (`_established`). Anything
    else is left to the ordinary road.
    """
    settled = _payloads.as_hex(ctx.state.get(_state._SETTLED_DOCS_SHA), _formats.COMMIT_LENGTHS)
    unparked = not ctx.state.get(_state._AWAITING_HUMAN)
    if settled and unparked and _publication_proved(ctx.state, settled):
        wt = _worktree_creation._ensure_pr_worktree(ctx.spec, ctx.issue.number, branch=ctx.branch)
        if not _standing_on(wt, settled):
            return False
        _final_completion._completes_published(ctx, settled, _SETTLED_DOCS_NOTICE.format(commit=settled))
        return True
    if not _established(ctx.state):
        return False
    log.info(
        "issue=#%d its final docs pass's completion landed with its relabel lost; finishing the relabel to `%s`",
        ctx.issue.number, WorkflowLabel.IN_REVIEW,
    )
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.IN_REVIEW)
    return True


def _finished_settled_docs(ctx: _models._DocumentingContext, wt, ahead: int) -> bool:
    """Finish a docs pass whose commit the pull request already carries, completing it into `in_review`.

    The receipt says the pass is over: an agent ran, it committed, and the
    only thing left between that commit and `in_review` is its completion.
    The receipt the next tick's opening proves published is finished there
    (`_finishes_an_owed_completion`), so what reaches this road is a park's
    reply over a published pass, or a receipt nothing proves.

    `ahead` is what says the commit reached the remote, and it is asked
    because the receipt cannot: a verdict that parked, or a human who moved
    the label by hand, leaves the same receipt over a commit still on disk
    only. Ahead of the remote the receipt is left exactly where it is and the
    recovered-commit path republishes it through the gate, which is the one
    road that measures it again.

    In sync is not the same claim as CARRYING it. A replacement host rebuilds
    the checkout from a pull request that has moved on, and what it gets is a
    branch level with its remote and standing on somebody else's head -- so
    the receipt is proved against the commit the checkout is on, not merely
    against the counters. The caller fetched the branch before counting and
    parks a checkout behind it, so a head that is in sync AND is the settled
    commit says the remote is standing there too. A receipt that is not a
    whole object id, and a head this host cannot peel, leave the receipt
    exactly where it is for a tick that can prove it.

    A park over a docs commit its own run did not pass on is the one park this
    road leaves to the pass instead (`final_completion._reruns_the_pass`): the
    continue that answers it resumes the docs pass over that commit, and what
    the pass leaves is verified again.

    True once the completion is handed the receipt, whether or not its write
    landed: the tick is handled either way, and a write that did not land
    leaves the receipt standing for the next tick to read.
    """
    settled = _payloads.as_hex(ctx.state.get(_state._SETTLED_DOCS_SHA), _formats.COMMIT_LENGTHS)
    if not settled or ahead > 0 or _final_completion._reruns_the_pass(ctx.state):
        return False
    if not _standing_on(wt, settled):
        return False
    _final_completion._completes_published(ctx, settled, _SETTLED_DOCS_NOTICE.format(commit=settled))
    return True


def _established(state: PinnedState) -> bool:
    """Whether a pass's completion landed whole with no receipt left: its record, its stamp, and its approval agree.

    The record reads whole and still follows the approval `state` records, on
    the pull request it pins (`FinalDocs.follows`); the stamp names the head
    it completed on, with the verdict that head earns -- `no_change` for an
    unchanged head, `updated` for a docs commit -- and no receipt or park
    stands beside them. Read off the pinned comment alone.
    """
    final = _final_docs.read_final_docs(state)
    if final is None or state.get(_state._AWAITING_HUMAN):
        return False
    if state.get(_state._SETTLED_DOCS_SHA) is not None:
        return False
    verdict = _handoff._NO_CHANGE if final.final_head == final.entry_head else _final_completion._UPDATED
    stamped = (state.get(_state._CHECKED_DOCS_SHA), state.get(_state._DOCS_VERDICT))
    return stamped == (final.final_head, verdict) and final.follows(state)


def _publication_proved(state: PinnedState, settled: str) -> bool:
    """Whether the code-publication receipt names `settled` as published onto the pull request the issue pins.

    Only a whole commit id on the pinned pull request, each read fail-closed.
    """
    number = _late_publication_state._recorded_pull_request(state)
    published = (
        _late_publication_state._published_commit(state),
        _late_publication_state._published_pull_request(state),
    )
    return bool(number) and published == (settled, number)


def _standing_on(wt, settled: str) -> bool:
    """Whether this checkout is the commit a settled receipt names.

    Proved rather than read, because everything past it is a claim about one
    object id: a revision this host cannot peel is not a head that matches
    anything, and a host that never had the commit answers exactly that.
    """
    proved = _measurement_commits._prove_candidate_commit(wt, _HEAD)
    if proved.is_frozen and proved.sha == settled:
        return True
    log.error(
        "the checkout at %s stands on %s rather than the settled docs commit "
        "%s; leaving the receipt for a tick that can prove it",
        wt, proved.sha or "an unreadable head", settled,
    )
    return False
