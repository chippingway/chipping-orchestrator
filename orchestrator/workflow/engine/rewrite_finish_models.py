# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the finish of a landed automatic PR base rewrite is handed, and what it comes to.

A finish is handed one landing (`rewrite_handoffs._LandedRewrite`): the
candidate the rebase left -- the head the pull request stood on, the head the
replay produced, the branch, the base that head was counted against, and the
attempt's own terms -- and what its lease-pinned publication came to. Beside
it is the issue that landing finishes, read under the caller's writer claim,
and the road that reached it: the ordinary publication of a rebase this tick
made, or the recovery of one an earlier tick left. The two roads are one
policy (`rewrite_finish`); what they differ in is only what they say about it.

Data and the issue it is about, nothing to call back into. Dormant with the
finalizer: nothing hands one over until the workflow's base-rewrite
coordinator (`base_rewrite`) takes the publication over.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite, _PushOutcome, _RewriteRefusal
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel

# What a push this tick sent and saw land comes back as: git's own accepted
# answer, or a failure answered with the remote then read on the candidate.
_SENT = frozenset((_PushOutcome.ACCEPTED, _PushOutcome.UNCERTAIN))


class FinishRoad(StrEnum):
    """Which road reached a landed rewrite's finish.

    PUBLICATION is the tick that rebased the branch and published the replay
    itself; RECOVERY is a later tick finishing a landing an interrupted one
    left -- a push it reissued, or one it found already standing.
    """

    PUBLICATION = "publication"
    RECOVERY = "recovery"


class FinishOutcome(StrEnum):
    """What one finish came to, and so what its caller does next.

    ROUTED finished the attempt with the landed head on `workflow:validating`.
    CONTINUED finished it over a base that advanced past the landed head
    again: the caller's ordinary rebase goes on from that head. PARKED is a
    debt the pinned comment had no room for, parked with the push and the
    attempt standing. REFUSED and UNCONFIRMED are a guarded write that did not
    land -- refused with nothing written, or sent and never confirmed -- and
    nothing that depends on it was made. UNFINISHABLE is a landing the pinned
    record does not account for, and nothing at all was made for it.
    """

    ROUTED = "routed"
    CONTINUED = "continued"
    PARKED = "parked"
    REFUSED = "refused"
    UNCONFIRMED = "unconfirmed"
    UNFINISHABLE = "unfinishable"


@dataclass(frozen=True)
class LandedFinish:
    """One landed rewrite, the issue it finishes, and the road that reached it.

    `state` is the issue's pinned state as the caller holds it; every write a
    finish makes is a guarded commit captured over the reading that state was
    last synced with. `label` is the label the issue wears, which the notice
    and the audit event are attributed to. `lag` is how many commits the head
    the publication replaced was behind its base, which only the publication's
    notice reports. `retry` is the human reply a recovery re-entered on, which
    the finish spends; None where there is none.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    landed: _LandedRewrite
    label: WorkflowLabel | None
    road: FinishRoad = FinishRoad.PUBLICATION
    lag: int = 0
    retry: int | None = None

    @property
    def head(self) -> str:
        """The commit the rewrite published, which the remote stands on."""
        return self.landed.candidate.rewritten_head

    @property
    def anchor(self) -> str:
        """The head the rewrite replaced, which the publication was leased against."""
        return self.landed.candidate.original_head

    @property
    def pr_number(self) -> int:
        """The pull request the attempt was made for."""
        return self.landed.candidate.attempt.pr_number

    @property
    def behind(self) -> int | None:
        """How far the base has advanced past the landed head, as the candidate counted it; None where it was not.

        A comparison that did not happen is not one that found the head level
        with its base, though both carry a zero count: read as current, a head
        nobody showed current would be routed to review and its attempt
        retired.
        """
        base = self.landed.candidate.checkout.base
        return base.behind if base.readable else None

    @property
    def pushed(self) -> bool:
        """Whether this tick's own push is what the remote was shown standing on.

        An accepted push, or one whose answer was lost and the remote was then
        read on the replay. A push whose answer was lost and whose remote could
        not be read after is not known to have landed at all. An observation
        sends nothing, and neither does a publication refused because the
        remote already stood on the candidate: both find a push an earlier tick
        made.
        """
        return self.landed.outcome in _SENT and self.landed.landed

    @property
    def moved(self) -> bool:
        """Whether the rewrite published another head than the one it replaced.

        One that did not replayed nothing, and has nothing to announce or route.
        """
        return self.head != self.anchor

    @property
    def refused(self) -> bool:
        """Whether a guard stopped the publication for anything but the remote already standing on it."""
        landed = self.landed
        return landed.outcome is _PushOutcome.REFUSED and landed.refusal is not _RewriteRefusal.PUBLISHED
