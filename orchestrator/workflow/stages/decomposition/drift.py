# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a body edit resets on an issue that is already `decomposing`.

The reset runs at the very top of the tick, ahead of the half-finished
recovery, because the manifest markers recovery reads are exactly what an edit
invalidates: a body rewritten during a crash window would otherwise be
finalized to `blocked` or `umbrella` against a split the human has already
moved on from. Everything the fresh spawn would read back is wiped in one
step -- the children, the dep graph, the expected count, the seal that says
that count is final, the umbrella flag, the split's recorded rationale, and
the park flags -- so the tick falls through and re-derives a manifest against
the updated body rather than returning the way the pre-implementation drift
routes do.

Three things survive it. The locked agent spec stays, since a mid-flight
`DECOMPOSE_AGENT` flip must not retarget an issue whose pinned session id was
written by another backend; only the session id is retired, and through the
session owner, which is where that retirement is spelled for every caller that
decides the next run is a fresh one. Children the wiped manifest tracked stay
open on GitHub: the orchestrator stops tracking them, so the notice names them
as orphans and leaves it to the operator to decide which no longer apply.

And a late generation a split left stays exactly as it was written, because
it is not manifest tracking. Its register, its snapshot, and its consumer
ledger are what the remote is owed and who that ref was preserved for, and an
edit changes neither: the orphans the notice names are still the consumers
the umbrella's cleanup proves the ref against, whatever manifest replaces
them. Nothing here adopts, relabels, or reopens one of them -- but a split of
this issue's own that pointed its replacements at that ref may have one the
ledger does not name yet, and the attempt this reset drops is what held the
ref for it, so it is written onto that ledger first (`_account_discarded`).

The notice is posted before the reset touches state, so a tick that dies
between the two re-detects the same edit next time rather than throwing a
manifest away nobody was told about.

An issue `ready` rerouted here arrives with that reset already landed, beside
the marker saying its relabel was owed (`ready.py`). The label now answers
it, so the marker is dropped before the reset is asked -- and before recovery,
the kill switch, or a decomposer run -- in a guarded commit of its own
(`_retires_ready_reroute`): left standing, the next entry to `ready` would read
a finished reroute as one still owed and send the issue straight back here.
The reroute's notice is said first where the thread does not carry it yet --
a hold may have stopped the `ready` tick between its relabel and its notice --
found by the receipt the marker names, so it is said once
(`ready_notice.says`). A thread nobody could read, a hold read ahead of the
notice, behind it, or behind the retirement, or a retirement that does not
land holds the tick, and the next one asks again.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
)
from orchestrator.workflow.late_split import (
    formats as _formats,
    keys as _keys,
    ledger_encoding as _ledger_encoding,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import (
    ready_notice as _ready_notice,
    ready_readings as _ready_readings,
    session as _session,
    split_receipts as _split_receipts,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# The retirement of a `ready` reroute's marker, decided on that marker alone.
_RETIRING = _commits.ReportWrite(
    owned=frozenset((_state._READY_REROUTE,)), decided_on=frozenset((_state._READY_REROUTE,)),
)

# What the discarded split wrote beside its register. The seal is a fact
# about that count, the attempt about the receipts its children carry, and
# the rationale about the scope it kept for the parent against the body this
# edit replaced, so all of them go with it: a register called final, a child
# a recovery would adopt, or residual scope a later implementation would
# read belongs to the manifest this reset is throwing away.
_SPLIT_MARKERS = (
    "expected_children_count",
    _state._SPLIT_LEDGER_SEALED,
    _state._SPLIT_ATTEMPT,
    _state._SPLIT_RATIONALE,
    _state._UMBRELLA,
)


def _decomposition_drift_notice(orphans: list) -> str:
    notice = (
        ":pencil2: issue content changed; re-running decomposer against "
        "the updated body."
    )
    if not orphans:
        return notice
    orphan_list = _state._issue_ref_list(orphans)
    return (
        f"{notice} The previously-tracked children ({orphan_list}) will be "
        "ORPHANED -- the orchestrator no longer tracks them; please close "
        "any that no longer apply to the updated requirements."
    )


def _clear_decomposition_manifest(state: PinnedState) -> None:
    _session._retire_decomposer_session(state)
    state.set(_state._CHILDREN, [])
    state.set("dep_graph", {})
    for marker in _SPLIT_MARKERS:
        state.set(marker, None)
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)


def _retires_ready_reroute(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Drop the marker of a reroute `ready` landed, now the label it owed reads `decomposing`; whether the tick goes on.

    An issue carrying none costs nothing. The notice the marker records is
    said first where the thread does not carry its receipt yet, and its
    ledger entry rides the retirement. A thread nobody could read, or a hold
    -- read ahead of the notice and again behind it -- holds the tick with
    the marker standing; so does anything but a write GitHub confirmed, with
    the tick's state withheld: a decomposer run, or a decision handing the
    issue back to `ready`, would otherwise leave behind a marker that sends
    the next entry to `ready` straight back here. A hold read once more
    behind a retirement that landed holds the tick too, the marker gone: the
    next tick, once the hold is off, has nothing to retire and goes on.
    """
    owed = state.get(_state._READY_REROUTE)
    if owed is None:
        return True
    comments = _ready_readings.thread(gh, issue, state)
    if comments is None or not _ready_notice.says(gh, issue, state, owed, comments):
        return False
    if _ready_readings.held(gh, issue):
        return False
    commit = _commits.ReportCommit(gh, issue, state)
    staged = commit.staging()
    staged.data.pop(_state._READY_REROUTE)
    landed = commit.lands(staged, _RETIRING)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return not _ready_readings.held(gh, issue)
    state.withheld = True
    log.warning(
        "issue=#%d the retirement of its ready reroute came back %s; holding the tick, with the pinned comment "
        "left as it stands for the next one to read",
        issue.number, (landed.refusal or landed.status).value,
    )
    return False


def _reset_decomposing_on_drift(
    gh: GitHubClient, issue: Issue, state: PinnedState
) -> None:
    """Detect a user-content edit and clear what it invalidated, in place.

    Returns having changed nothing when the body still matches the recorded
    baseline. Otherwise the caller falls through with a state that carries no
    manifest and no park, which is what makes the decomposer spawn this tick
    read the updated body -- the pre-implementation handlers answer the same
    edit by relabelling and returning, but this issue already wears the label
    that re-derives a manifest.
    """
    new_hash = _engine_drift._detect_user_content_change(gh, issue, state)
    if new_hash is None:
        return
    _comments._post_issue_comment(
        gh, issue, state, _decomposition_drift_notice(_account_discarded(gh, issue, state)),
    )
    state.set("user_content_hash", new_hash)
    _clear_decomposition_manifest(state)


def _account_discarded(gh: GitHubClient, issue: Issue, state: PinnedState) -> list:
    """Put every child the discarded split may have pointed at the snapshot on its consumer ledger; those children.

    The manifest a reset throws away takes `split_attempt` with it, and that
    is what held the snapshot for a replacement the ledger does not name --
    see `late_cleanup_proof`. So first every child that split recorded goes
    onto `late_consumers`, a lost slot included, and so does every issue this
    orchestrator opened carrying the receipt of the slice a crash can leave
    created and unrecorded, found as a recovery would find it. Each then holds
    the ref until it ends, as an orphan the notice names. A split an older
    binary made, an issue no late split charged, and a consumer ledger nobody
    can type owe the ledger nothing.
    """
    register = state.get(_state._CHILDREN) or []
    recorded = [number for number in register if _state._names_an_issue(number)]
    generation = _late_state.read_late_generation(state)
    if state.get(_state._SPLIT_ATTEMPT) is None or not generation.is_present:
        return recorded
    if generation.obligations.opaque_consumers is not None:
        return recorded
    discarded = [*recorded, *_unrecorded_children(gh, issue, state, len(recorded))]
    owed = generation.obligations.with_consumers(tuple(discarded))
    state.set(_keys.CONSUMERS, _ledger_encoding.ledger_fields(owed)[_keys.CONSUMERS])
    return discarded


def _unrecorded_children(gh: GitHubClient, issue: Issue, state: PinnedState, recorded: int) -> list[int]:
    """Every issue carrying the receipt of the slice a crash can leave unrecorded, while the register is short.

    Asked only of an attempt this binary minted whose register has not
    provably reached its count, since that is the one window such a child can
    exist in; the walk it costs is the one a recovery would have made.
    """
    attempt = state.get(_state._SPLIT_ATTEMPT)
    expected = state.get("expected_children_count")
    if not isinstance(attempt, str) or _split_receipts._ATTEMPT.fullmatch(attempt) is None:
        return []
    if _formats.whole_number(expected) and recorded >= expected:
        return []
    lookup = _split_receipts._LOOKUP.format(issue=issue.number, attempt=attempt, index=recorded)
    return [candidate.number for candidate in gh.find_issues_carrying(lookup)]
