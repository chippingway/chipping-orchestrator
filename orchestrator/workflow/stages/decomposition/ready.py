# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `ready` decides before anything implements: whether the requirements still read as the baseline says.

Every legitimate entry to `ready` -- a child its parent released, a parent
whose children are all done, an issue its decomposer voted `single` -- is
asked here, on the reading taken under the issue's writer claim and held to
admission, before a pickup is announced, a comment is consumed, or an
implementer is launched. The trusted requirements are fingerprinted by the
drift check's own definition (`engine/content_hash`), off the issue fetched
afresh and one reading of its thread (`ready_readings`), and compared against
the baseline the record preserves. Requirements that read unchanged are
handed on (`ready_handoff`), which compares again on every issue it fetches
ahead of an effect -- the pickup, the reading its checkpoint consumes, the
relabel -- and hands back a change that landed meanwhile. Requirements that
changed take the decomposition route: the manifest is reset against them and
the issue goes back to `decomposing`. A thread nobody could read holds the
decision with nothing done.

A split's child carrying no baseline at all -- neither its creation's nor an
observed reading standing in for it (`engine/drift._unbaselined`) -- takes the
same route. A child is created to carry the requirements its split cut for it,
and its seed records them off the create itself; one seeded without them, by a
recovery or a resumed walk, has nothing proving it still says what it was cut
for, so its current content is never taken as an unchanged baseline here. An
issue no split made keeps the drift check's own first-encounter answer, the
observed reading included, and so does every other stage.

The reroute is the reset `_route_drift_to_decomposing` describes -- the locked
decomposer spec kept, the late generation, ancestry, and snapshot left whole,
every child the discarded manifest may have pointed at a snapshot written onto
its consumer ledger first (`stages/decomposition/drift._account_discarded`) --
landed before anything else as one guarded commit over the claimed reading
(`ready_handoff.lands`), decided on what the decision read and on every field
the reset wipes. A change the handoff read only behind its own checkpoint is
rerouted over the record that checkpoint landed, its pickup and consumed
reading kept, so nothing that landed is put back and no implementer runs. The same commit records the reroute itself
(`_READY_REROUTE`): the children the reset stopped tracking, why it ran, and a
receipt minted for its notice. The reset carries the new baseline, so a
`ready` tick reading it with no marker beside it would read requirements
nobody changed and hand the issue to implementation; with the marker, that
tick knows the reset is in place and finishes the relabel instead.

Only a write GitHub confirmed, and read back as the issue's record still
carrying the reset and its marker, licenses the relabel -- a first pin another
pin posted meanwhile shadows licenses nothing -- and the notice goes out
behind the relabel, best-effort, carrying the receipt in a hidden marker
(`ready_notice`): refused, never confirmed, or read back as another record,
nothing is relabelled or said, the tick's state is withheld, and the next tick
reads what stands -- the marker, and the relabel it owes; or nothing, and the
decision asked afresh.
Whichever tick says the notice looks for that receipt on the thread first and
says nothing where a comment of ours carries it, so the notice is said once
however often the issue comes back to `ready` -- an operator's relabel
included -- before the marker is retired. The issue's labels are read again
ahead of the commit, ahead of the relabel, and behind it ahead of the notice
(`ready_readings.held`): a `paused` or `backlog` applied meanwhile stops the
reroute there, its recovery included, and a notice a hold stopped behind a
relabel that landed is said by the `decomposing` tick ahead of retiring the
marker (`drift._retires_ready_reroute`), which it drops ahead of its drift
check, recovery, and decomposer, so no later entry to `ready` reads a reroute
already finished.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    drift as _drift,
    report_commits as _commits,
)
from orchestrator.workflow.stages.decomposition import (
    drift as _decomposition_drift,
    ready_handoff as _handoff,
    ready_notice as _notice,
    ready_readings as _readings,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

# Every field the reset wipes. A parent its children all finished reaches
# `ready` still carrying their register, which the next `decomposing` tick's
# half-finished recovery would otherwise read as a crashed split and flip back
# to `blocked` without running the decomposer. Each is decided on as well as
# owned: one staged as the claimed reading already spelled it is no move of the
# write's, and a record a human moved there since would otherwise ride the
# reset unread.
_WIPED = frozenset((
    "decomposer_session_id",
    _state._CHILDREN,
    "dep_graph",
    *_drift._SPLIT_MARKERS,
    _state._AWAITING_HUMAN,
    _state._PARK_REASON,
))

# The reroute: the reset, the baseline it records, and the marker saying the
# relabel is owed, decided on what the decision read and on what it wipes. The
# consumer ledger the accounting extends is the tick's own move, owned with it.
_REROUTING = _commits.ReportWrite(
    owned=_WIPED | {_drift._USER_CONTENT_HASH, _state._READY_REROUTE},
    decided_on=_handoff.DECIDED_ON | _WIPED,
)


def enters(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> None:
    """Reroute `issue` to `decomposing` or hand it to implementation, off its claimed, admitted reading `state`.

    A reroute an earlier tick landed and never relabelled is finished first,
    with nothing compared, reset, or written again. Everything is decided on
    the issue fetched afresh first (`ready_readings.fresh`) -- its title and
    body as GitHub holds them now, not as the dispatched object read them --
    and a hold standing on it already stops the decision before any effect.
    """
    fetched = _readings.fresh(gh, issue)
    comments = None if fetched is None else _readings.thread(gh, fetched, state)
    if comments is None:
        return
    owed = state.get(_state._READY_REROUTE)
    if owed is None:
        fingerprint, unbaselined = _compared(gh, fetched, state, comments)
        if fingerprint is None:
            fingerprint = _handoff.hands_off(gh, spec, fetched, state, comments)
        if fingerprint is None:
            return
        owed = _reset(gh, fetched, state, fingerprint, unbaselined=unbaselined)
        if owed is None:
            return
    _relabels(gh, fetched, state, owed, comments)


def _compared(
    gh: GitHubClient, issue: Issue, state: PinnedState, comments: list,
) -> tuple[str | None, bool]:
    """The fingerprint a reroute records, and whether no baseline stood; None where the requirements read unchanged.

    Taken off `comments`, the decision's reading of the thread. A child whose
    record carries no baseline is fingerprinted without being compared.
    Anything else is the drift check's answer over that reading: a first or
    normalized baseline it stages on `state` lands in the handoff's own
    checkpoint.
    """
    if _state._names_an_issue(state.get(_state._PARENT_NUMBER)) and _drift._unbaselined(state):
        ids = _comments._orchestrator_ids(state)
        return _content_hash._compute_user_content_hash(issue, ids, comments=comments), True
    return _drift._detect_user_content_change(gh, issue, state, reading=comments), False


def _reset(
    gh: GitHubClient, issue: Issue, state: PinnedState, current: str, *, unbaselined: bool,
) -> dict | None:
    """Land the reroute's reset to `current` with its marker; the marker, or None where the write did not land.

    The discarded manifest's children are accounted for first, through the
    owner every reset takes that account through, so the marker names every
    child the notice will. A hold applied since the tick began lands nothing,
    and a write the issue's record does not read back as -- a first pin some
    other pin shadows above all -- answers None too (`ready_handoff.lands`).
    """
    owed = _notice.minted(_decomposition_drift._account_discarded(gh, issue, state), unbaselined=unbaselined)
    _drift._reset_decomposition_for_drift(state, current)
    state.set(_state._READY_REROUTE, owed)
    if _readings.held(gh, issue):
        state.withheld = True
        return None
    if not _handoff.lands(issue, _commits.ReportCommit(gh, issue, state), _REROUTING, "reroute"):
        return None
    return owed


def _relabels(gh: GitHubClient, issue: Issue, state: PinnedState, owed: object, comments: list) -> None:
    """Relabel `issue` to `decomposing` for the reroute recorded as `owed`, and say its notice where none is said.

    A hold read ahead of the relabel stops it with nothing relabelled or said;
    one applied while the relabel ran stops the notice, which the
    `decomposing` tick then says ahead of retiring the marker
    (`ready_notice.says`).
    """
    current = _readings.fresh(gh, issue)
    if current is None:
        return
    gh.set_workflow_label(current, WorkflowLabel.DECOMPOSING)
    _notice.says(gh, current, state, owed, comments)
