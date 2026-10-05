# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification artifact published as tracked orchestrator output.

An artifact carries the orchestrator marker in its own rendering, which is
what identifies it as ours once its id has aged out of the bounded ledger.
The id is the other half, and it is the half an edit cannot take away: a
maintainer who deletes the marker from a published artifact leaves a comment
every "is this ours?" scan would otherwise read as somebody's fresh feedback,
and the workflow would then answer this orchestrator's own evidence as though
a human had asked for something.

So a caller publishes through here rather than straight at the client, exactly
as a developer report's publication goes through `comments`. This sits beside
that owner rather than inside it because what it answers for is one domain's
publication, while that owner answers for the marker, the id list, and the
plain comment posts every stage makes -- and it records through that owner, so
an id is still tracked in one place.

The ledger is a set every road adds to, so a guarded write of it lays this
domain's entries over the ledger the comment carries when the write lands
(`MERGED_LEDGER`) rather than putting back the ledger the tick read: an id
another road recorded meanwhile is kept, and one the bound evicts is evicted
again. The publication's measurement ahead of the post reserves the entry the
artifact will take against that same merged ledger (`RESERVED_LEDGER`). The
settlement installs the artifact's entry in the same commit as the evidence it
makes current (`verification_settling`); where that commit is refused, the
entry is committed alone (`records_the_artifact`).
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from github.Issue import Issue
from github.PullRequest import PullRequest

from orchestrator.github import pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    report_record_values as _record_values,
    verification_durable as _durable,
)


def _publish_verification_artifact(
    gh: GitHubClient,
    pr: PullRequest,
    state: PinnedState,
    artifact: VerificationArtifact,
) -> _pr_reports.ReportLookup:
    """Publish one verification artifact onto `pr` and record its comment as ours.

    Recorded whenever the reading shows the artifact on the thread, not only
    after the post that made it. A post whose response was lost hands back no
    id, so the retry that finds the comment an earlier attempt landed is the
    ledger's one chance to learn it; readings after that add nothing, since
    recording an id twice keeps one entry. Recorded on `state` only: the
    caller commits it, with the settlement or alone (`records_the_artifact`).

    The marker is not appended here: it is part of the artifact's own format,
    and a retry finds the comment only where it reads back exactly in that
    format, so a marker added here would leave a body no format spells.

    The id is read off the LOOKUP rather than off the object it carries. That
    read is a request on a worker holding an uncompleted object, and this runs
    inside a dispatch guard where one that raised would leave by an exception
    rather than by an answer -- out of the tick entirely. It happens here,
    before the caller ever sees the reading, so a boundary the caller put
    around its own read would be the second one and this the raise.
    """
    lookup = gh.publish_verification_artifact(pr, artifact)
    posted_id = lookup.landed_id
    if lookup.presence is _pr_reports.ReportPresence.PRESENT and posted_id is not None:
        _comments._track_orchestrator_comment(state, posted_id)
    return lookup


def records_the_artifact(
    gh: GitHubClient, issue: Issue, state: PinnedState, comment_id: int,
) -> bool:
    """Commit the artifact at `comment_id` onto the ledger alone, over the comment as it stands; True holds the tick.

    For a settlement that did not land: the artifact is on the thread all the
    same, and the tick that next proves the world may defer before it ever
    reads the thread again. Guarded by nothing but the comment `state` was
    read from, since recording our own comment is right whatever else moved.
    Where it lands, the reading it landed as becomes the state in hand. A
    comment with no room for the entry is left as it stands, for the retry to
    read the id back off the thread. One that will not read, no longer parses,
    or is not the comment `state` was read from holds the tick, and so does a
    write nobody confirmed (`verification_durable.refusal_of`): nobody can say
    what the record carries, so nothing behind the reconciliation may act on
    it this tick.
    """
    guard = _commit_models.PinnedCommit.capture(state, owned=MERGED_LEDGER)
    staged = PinnedState(state_data=dict(state.data))
    _comments._track_orchestrator_comment(staged, comment_id)
    outcome = _commit.commit(gh, issue, guard, staged.data, MERGED_LEDGER)
    if outcome.status is _commit_models.CommitStatus.COMMITTED:
        state.data = outcome.reading.data
        return False
    return _durable.refusal_of(outcome).holds


def _merged_ledger(fresh: Any, _captured: Any, staged: Any) -> Any:
    """The ledger `fresh` carries, with every comment id the caller staged tracked onto it.

    Every id rather than only the ones the caller added: one the fresh ledger
    lacks was either never recorded there or evicted by the bound, which
    evicts it again.
    """
    return _tracked(fresh, staged).get(_comments._ORCH_COMMENT_IDS, _commit_models.ABSENT)


def _reserved_ledger(fresh: Any, captured: Any, _staged: Any) -> Any:
    """The ledger `fresh` carries, every comment id the capture held tracked onto it, and one more entry reserved.

    For a measurement taken before the post, of the entry the artifact's id
    will take. The slot is chosen against this merged ledger rather than the
    reading the caller staged over: an id reserved against that older reading
    may be one the ledger as it stands already holds, and reserving it again
    would reserve nothing (`comments._reserve_comment_slot`).
    """
    ledger = _tracked(fresh, captured)
    _comments._reserve_comment_slot(ledger, _record_values.MAX_RECORDED_NUMBER)
    return ledger.get(_comments._ORCH_COMMENT_IDS)


def _tracked(fresh: Any, offered: Any) -> PinnedState:
    """A state carrying the ledger `fresh`, with every comment id `offered` holds tracked onto it.

    An entry naming no comment is nobody's post, so it is never offered.
    """
    merged = PinnedState(state_data={})
    if fresh is not _commit_models.ABSENT:
        merged.set(_comments._ORCH_COMMENT_IDS, fresh)
    entries = offered if isinstance(offered, list) else []
    _comments._track_orchestrator_comment(merged, *(
        entry for entry in entries if isinstance(entry, int) and not isinstance(entry, bool)
    ))
    return merged


# The comment-id ledger as a guarded write of this domain commits it: merged
# over the fresh one rather than staged whole.
MERGED_LEDGER = MappingProxyType({_comments._ORCH_COMMENT_IDS: _merged_ledger})

# The same ledger as a measurement ahead of the post prepares it: merged over
# the fresh one, with the artifact's entry reserved against the result.
RESERVED_LEDGER = MappingProxyType({_comments._ORCH_COMMENT_IDS: _reserved_ledger})
