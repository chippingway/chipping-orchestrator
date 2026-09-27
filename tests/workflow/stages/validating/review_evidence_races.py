# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road does while a review round is between two of its requests.

A round reads, posts, and reads again, and the windows between those requests
are where a later report can settle on the same head or a human can rewrite
an artifact the round is about to quote. Each double here stands in for one
request and does that other road's write first, so a case about the window is
visibly about the request it opens beside.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages.validating import review_evidence_test_support as _world

# Which artifact reread finds the edit, and what the edit makes the output read.
EDITED_ON_READ = 2

EDITED_OUTPUT = "13 passed"


class SettlesALaterReport:
    """An artifact post during which a later report settles on the same head.

    What another road -- a developer report published meanwhile -- leaves on
    the pinned comment while this tick's post is in flight.
    """

    def __init__(self, case, text: str) -> None:
        self._case = case
        self._text = text
        self._post = case.github._post_verification_artifact

    def __call__(self, pull_request, body):
        _published_reports.republishes_the_report(self._case.github, self._case.issue, self._text)
        return self._post(pull_request, body)


class EditsTheArtifactOnReread:
    """Artifact rereads, the second of which finds the artifact edited into another valid one.

    The first is the proof that the evidence is current; the second is the
    reading the reviewer's prompt quotes. Between them a human rewrites the
    comment into an artifact that still renders exactly -- same identity,
    other output -- which only a comparison with the settled record can tell.
    """

    def __init__(self, case, current) -> None:
        self._case = case
        self._current = current
        self._reread = case.github.reread_verification_artifact
        self._reads = 0

    def __call__(self, pull_request, comment_id):
        self._reads += 1
        if self._reads == EDITED_ON_READ:
            posted = next(
                found for found in self._case.pull_request.issue_comments
                if found.id == self._current.comment_id
            )
            artifact = _artifacts.verification_artifact_from_comment(
                posted, bot_login=self._case.github._bot_login,
            )
            posted.body = _artifacts.render_verification_artifact(replace(
                artifact, commands=(_evidence.VerifiedCommand(_world.SUITE, 0, EDITED_OUTPUT),),
            ))
        return self._reread(pull_request, comment_id)
