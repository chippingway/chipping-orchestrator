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
"""
from __future__ import annotations

from github.PullRequest import PullRequest

from orchestrator.github import pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.workflow.engine import comments as _comments


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
    recording an id twice keeps one entry. Caller is still responsible for
    `gh.write_pinned_state`.

    The marker is not appended here: the artifact's own rendering carries it,
    because that rendering is what a retry compares byte for byte.

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
