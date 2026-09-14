# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recorded adjudications and live pull requests used to authorize rewrite transfers."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.workflow.late_split import (
    exemption as _exemption,
)
from orchestrator.workflow.stages.implementing import (
    state as _state,
)
from tests.support.authorization import _authorize
from tests.support.fakes import (
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.stages.implementing import late_transfer_payloads as _transfer_payloads


@dataclass(frozen=True)
class Adjudicated:
    """The issue a settled `single` verdict left, and what it was recorded on."""

    github: FakeGitHubClient
    issue: object
    state: object


def adjudicated(
    *,
    identity: bool = True,
    authorized: str | bool = True,
    digest: str = _transfer_payloads.ACCEPTED_DIGEST,
    base: str = _transfer_payloads.MERGE_BASE_SHA,
    labels: tuple | None = None,
) -> Adjudicated:
    """The pinned comment a settled `single` verdict leaves behind.

    `identity=False` is the legacy shape: a comment written before the
    semantic record existed, or one whose fingerprint could not be taken, so
    only the exact commit is exempt.

    `authorized=False` is the OTHER legacy shape, one policy further back: an
    exemption a `single` verdict recorded before an operator's own
    authorization was required at publication. The exemption is there and no
    gesture stands behind it, so the accepted commit goes to the ordinary
    cumulative gate like any other candidate.

    A DIGEST there is the hand edit a shape check cannot catch: the group
    parses, names the accepted commit, and describes a decision nobody made
    over a pair nobody read. `True` writes the identity's own, since the two
    describe one contribution wherever a real settlement wrote them.

    `base` is the pair's other end, replaceable because it is the one field a
    hand edit can move without the record refusing to read back: a whole
    object id naming some other commit types exactly as the frozen base does.

    `labels` is what the issue reads back as when the transfer re-fetches it,
    seeded on the issue rather than written through the client because the
    relabel that put the stage there happened long before this tick.
    """
    github = FakeGitHubClient()
    issue = make_issue(_transfer_payloads.ISSUE_NUMBER)
    named = (str(_transfer_payloads.SOURCE_STAGE),) if labels is None else labels
    issue.labels.extend(FakeLabel(name) for name in named)
    github.add_issue(issue)
    github.seed_state(_transfer_payloads.ISSUE_NUMBER, **{_state._PR_NUMBER: _transfer_payloads.PR_NUMBER})
    state = github.read_pinned_state(issue)
    _exemption.record_exemption(state, _transfer_payloads.ACCEPTED_SHA)
    if authorized:
        _authorize(
            state, _transfer_payloads.ACCEPTED_SHA, base,
            digest if authorized is True else authorized,
        )
    if identity:
        _exemption.record_semantic_identity(
            state,
            base_sha=base,
            candidate_sha=_transfer_payloads.ACCEPTED_SHA,
            fingerprint=digest,
        )
    github.write_pinned_state(issue, state)
    return Adjudicated(github=github, issue=issue, state=state)


def open_pull_request(github, standing: str = _transfer_payloads.LEASED_SHA) -> None:
    """Stand this issue's open pull request on one head.

    `standing` is the whole of what a settlement case is about: the head the
    permit was granted against is the ordinary remote, and the rewritten
    commit is the one a tick that pushed and died before its receipt comes
    back to.
    """
    github.add_pr(FakePR(
        number=_transfer_payloads.PR_NUMBER,
        head_branch=_transfer_payloads.BRANCH,
        head=FakePRRef(sha=standing),
    ))
