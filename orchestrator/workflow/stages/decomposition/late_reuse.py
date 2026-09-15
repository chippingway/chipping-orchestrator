# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hold or park child dispatch when its inherited snapshot cannot be reused.

Reclaimed and repointed snapshots have distinct notices and park reasons.
Unrecorded children use the parent and reclamation evidence before starting.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.late_split import ancestry as _ancestry, lineage as _lineage
from orchestrator.workflow.stages.decomposition import late_reuse_reading as _late_reuse_reading

log = logging.getLogger("orchestrator.workflow")

# The reason the `park_awaiting_human` audit record carries for a child whose
# snapshot was reclaimed before it came back to it.
PARK_SNAPSHOT_RECLAIMED = "late_snapshot_reclaimed"

# And for the other way the promise can be broken: the ref is still there and
# carries a commit nobody preserved. Kept apart from the reclamation because
# an operator reading a park has to know which world they are in -- one is
# this orchestrator finishing its own work, and the other is a ref in its
# namespace that somebody else wrote.
PARK_SNAPSHOT_REPOINTED = "late_snapshot_repointed"

_RECLAIMED_PARK = (
    "{mentions} the immutable snapshot this issue was created to reuse "
    "(`{ref}`, from the split on #{owner}) has been reclaimed -- it is "
    "deleted once every issue cut from it has ended. That ref is never "
    "recreated: what made it worth reusing was that it provably carried one "
    "exact commit, and a ref pushed again from whatever is reachable now "
    "proves nothing. Implement this issue as an ordinary change, or start an "
    "explicit new split cycle on #{owner}, which preserves a candidate of its "
    "own. The reuse instructions in the issue body no longer apply."
)

# And what it is told when the ref is still there under another commit. It
# says what is true rather than that the snapshot is gone: the name survived
# and what it stands for did not, which is a state this orchestrator never
# produces -- a reclamation refuses a re-pointed ref exactly as this does --
# so the ref is left where it is and the sentence is about the promise.
_REPOINTED_PARK = (
    "{mentions} the immutable snapshot this issue was created to reuse "
    "(`{ref}`, from the split on #{owner}) no longer carries the commit it "
    "was preserved at, so the candidate this issue was cut from cannot be "
    "obtained from it. Nothing here re-points or deletes that ref: a ref in "
    "this namespace carrying somebody else's commit is a question for a "
    "human. Implement this issue as an ordinary change, or start an explicit "
    "new split cycle on #{owner}, which preserves a candidate of its own. The "
    "reuse instructions in the issue body no longer apply."
)

# What the same child is told when its own record of WHICH snapshot never
# landed. It names no ref because none was ever written down: the evidence is
# either the reclamation's own receipt on the thread above or the remote no
# longer carrying the ref that split's identity names, and the sentence has
# to be true whichever of the two this tick read.
_UNRECORDED_PARK = (
    "{mentions} this issue was created by the split on #{owner} to reuse an "
    "immutable snapshot of that issue's committed candidate, and that "
    "snapshot has been reclaimed -- it is deleted once every issue cut from "
    "it has ended. This issue never recorded which snapshot it was; what says "
    "the ref is gone is the reclamation's receipt above, or the remote "
    "itself where no receipt reached this issue. That ref is never "
    "recreated: what made it worth reusing was that it provably carried one "
    "exact commit. Implement this issue as an ordinary change, or start an "
    "explicit new split cycle on #{owner}, which preserves a candidate of "
    "its own. The reuse instructions in the issue body no longer apply."
)

# How each verdict that stops a child for a human says so: what the thread is
# told, and what the audit record is filed under. Paired here because they are
# one decision -- a park an operator filters as a reclamation has to be the
# park whose comment says the ref was reclaimed.
_VERDICT_PARKS = MappingProxyType({
    _late_reuse_reading._Reuse.RECLAIMED: (_RECLAIMED_PARK, PARK_SNAPSHOT_RECLAIMED),
    _late_reuse_reading._Reuse.REPOINTED: (_REPOINTED_PARK, PARK_SNAPSHOT_REPOINTED),
})


def _refuses_reuse(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this child must be answered for before it may start.

    True tells the caller to return, and covers two different states. One is
    a verdict: the ref is gone, or carries a commit nobody preserved, and the
    issue is parked for a human with its pointer dropped -- dropping it is
    what makes this cost nothing on every dispatch after, since an ancestry that
    goes on naming a ref the child may not use is one every later reader would
    follow. The other is the absence of a verdict, where nothing at all is
    written and the same question is asked again on the next dispatch.

    An issue with no recorded ancestry at all is not automatically an issue of
    no lineage -- see `_refuses_unrecorded`, which is what the crash window
    between recording a child and seeding it leaves behind.

    The write is this handler's own, on its own issue, so there is no second
    writer to lose it to -- which is the whole reason the guard lives here
    rather than on the owner that did the reclaiming.
    """
    ancestry = _lineage.read_late_ancestry(state)
    if not ancestry.is_present:
        return _refuses_unrecorded(gh, spec, issue, state)
    if not ancestry.has_snapshot:
        return False
    verdict = _late_reuse_reading._verdict(gh, spec, issue, ancestry)
    if verdict is _late_reuse_reading._Reuse.ALLOWED:
        return False
    if verdict is _late_reuse_reading._Reuse.DEFERRED:
        log.warning(
            "issue=#%s was cut from %s and nobody could say whether that ref "
            "is still there; holding this dispatch rather than starting work "
            "against a promise nothing vouched for",
            issue.number, ancestry.snapshot_ref,
        )
        return True
    log.warning(
        "issue=#%s was cut from %s, which it may not reuse (%s); parking it "
        "rather than starting work against it",
        issue.number, ancestry.snapshot_ref, verdict.value,
    )
    notice, reason = _VERDICT_PARKS[verdict]
    return _parked(
        gh, issue, state, ancestry.without_snapshot(), (
            notice.format(
                mentions=config.HITL_MENTIONS,
                ref=ancestry.snapshot_ref,
                owner=ancestry.parent_issue,
            ),
            reason,
        ),
    )


def _refuses_unrecorded(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether an issue with no recorded ancestry is a child of a split anyway.

    The split records a child on the parent's ledger BEFORE it seeds that
    child's ancestry, because a child on GitHub the parent does not record is
    a child nothing would ever come back to. The window between the two is
    durable: a seed that failed leaves an issue whose BODY tells it to reuse a
    snapshot and whose pinned comment says nothing at all -- and the
    reclamation that later takes that ref still counts it as a consumer, and
    still leaves its receipt.

    So the body decides whether to look, and it costs nothing: the dispatcher
    already has the issue, and the marker the transaction stamped into it
    names the owner, the cycle, and the generation. Every issue no split
    created stops right there, without a request.

    A body is a field the world can write, so nothing here acts on what it
    claims until the SPLIT's own record says the same thing -- see
    `_unrecorded_verdict`. What the marker buys is the right to ask, and the
    asking is what decides.

    The park writes back the lineage the body claims, and only the lineage:
    the pointer this tick worked from was assembled out of the owner's record
    rather than out of anything this issue holds, and leaving half of it in
    the pinned comment is leaving a ref every later reader would follow. It is
    both the repair the failed seed owes -- an issue that now says which split
    made it -- and what stops the question being asked again, since a lineage
    with no snapshot on it returns above at once.
    """
    claimed = _ancestry.child_lineage(getattr(issue, "body", None))
    if claimed is None:
        return False
    verdict, vouched = _late_reuse_reading._unrecorded_verdict(gh, spec, issue, claimed)
    if verdict is _late_reuse_reading._Reuse.ALLOWED:
        return False
    if verdict is _late_reuse_reading._Reuse.DEFERRED:
        log.warning(
            "issue=#%s claims the split on #%s made it, and nobody could say "
            "what that split still holds; holding this dispatch",
            issue.number, claimed.parent_issue,
        )
        return True
    log.warning(
        "issue=#%s was created by the split on #%s and never recorded which "
        "snapshot; the ref that split preserved is one it may not reuse (%s), "
        "so it is parked rather than started",
        issue.number, claimed.parent_issue, verdict.value,
    )
    return _parked(
        gh, issue, state, claimed,
        _unrecorded_park(verdict, vouched, claimed.parent_issue),
    )


def _unrecorded_park(
    verdict: _late_reuse_reading._Reuse,
    vouched: _ancestry.LateAncestry | None,
    owner: int,
) -> tuple[str, str]:
    """What this child is told, and what the park is filed under.

    The reclaimed sentence is its own, because what this issue is missing is
    its own record of WHICH snapshot -- so the notice names none, and what
    says the ref is gone is the receipt above it or the remote. A ref that is
    still there under somebody else's commit is the recorded shape's sentence
    exactly: the ref can be named, because the owner's ledger is what named
    it.
    """
    if verdict is _late_reuse_reading._Reuse.REPOINTED and vouched is not None:
        return (
            _REPOINTED_PARK.format(
                mentions=config.HITL_MENTIONS,
                ref=vouched.snapshot_ref,
                owner=owner,
            ),
            PARK_SNAPSHOT_REPOINTED,
        )
    return (
        _UNRECORDED_PARK.format(mentions=config.HITL_MENTIONS, owner=owner),
        PARK_SNAPSHOT_RECLAIMED,
    )


def _parked(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    ancestry: _ancestry.LateAncestry,
    park: tuple[str, str],
) -> bool:
    """Record what is left of the lineage, park the issue, and say why.

    `park` is what the thread is told and what the audit record is filed
    under, handed over as one value because they are one decision: a park an
    operator filters as a reclamation has to be the park whose comment says
    the ref was reclaimed, and a call site free to pair either message with
    either reason is free to file one as the other.

    Always True: the caller has already decided, and returning the decision
    keeps every refusal one statement at its call site.
    """
    notice, reason = park
    _lineage.write_late_ancestry(state, ancestry)
    _guards._park_awaiting_human(gh, issue, state, notice, reason=reason)
    gh.write_pinned_state(issue, state)
    return True
