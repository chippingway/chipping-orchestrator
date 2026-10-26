# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pair an earlier build stranded under its own park, which the handoff and retry-baseline journeys start from.

The changed-contribution journey refreshed up to the handoff and parked the
way an earlier build's dispatcher parked such a pair, plus the requirements
baseline a stage may have recorded over a bare continue it read before that.
"""
from __future__ import annotations

from orchestrator.git.base_sync import persistence as _persistence
from orchestrator.workflow.engine import comments as _comments, content_hash as _content_hash
from tests.git.base_sync.journey_adjudication_support import replies
from tests.git.base_sync.journey_handoff_support import ChangedContributionJourney
from tests.git.base_sync.journey_push_support import BEFORE_THE_HANDOFF

# The park an earlier build's dispatcher stranded a pair under, and what its
# notice asked for: a reply, with anything in it.
PARK_STRANDED = "auto_base_rebase_failed"
STRANDED_NOTICE = "put the issue back on the stage the rebase was made under and reply on this issue"

# The operator's content-free nudge, which the requirements baseline leaves out.
BARE_CONTINUE = "/orchestrator continue"


def reads_a_bare_continue(fixture, *, spelled=_content_hash._compute_user_content_hash) -> str:
    """Have a stage read a bare continue, recording the watermark past it and the requirements baseline; that baseline.

    `spelled` computes the baseline over the issue and the orchestrator's
    comment ids -- the current fingerprint, which leaves the continue out,
    unless a case hands in the spelling of a producer that counted it.
    """
    nudged = replies(fixture, BARE_CONTINUE)
    durable = fixture._durable()
    durable.set("last_action_comment_id", nudged)
    baseline = spelled(fixture._issue(), _comments._orchestrator_ids(durable))
    durable.set("user_content_hash", baseline)
    fixture._gh.write_pinned_state(fixture._issue(), durable)
    return baseline


class StrandedJourney(ChangedContributionJourney):
    """A pair an earlier build stranded under its own park."""

    def setUp(self) -> None:
        super().setUp()
        self._refreshes(BEFORE_THE_HANDOFF)
        self.replay = self._wt_head()
        self._strands()

    def _strands(self) -> None:
        """Park the pair under the stranded park's notice."""
        _persistence._park_auto_rebase_failure(
            self._gh, self._issue(), self._durable(), message=STRANDED_NOTICE, reason=PARK_STRANDED,
        )
