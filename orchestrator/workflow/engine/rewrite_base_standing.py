# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a landed base rewrite's head still stands on the base it was counted against, as its evidence is held to it.

The finish counts the landed head against the base as its tick fetched it, and
routes a head the base has advanced past to another rebase instead of to
review (`rewrite_finish`). Verification evidence decided for the head rests on
that count as much as on the head itself, so the base is read again where a
decision is about to be recorded or routed: before the configured commands run
and after they complete (`rewrite_evidence`), and where a recovery takes up a
decision an earlier finish captured (`rewrite_finish_captured`). The reading
is the git owner's (`git/base_sync/rewrite_facts._standing_on_the_remote_base`);
what each answer means for the evidence is decided here, in the proof's own
verdicts:

- A remote base somewhere else than the tip the head was counted against --
  advanced while the commands ran, or since the tick that captured the
  decision -- HOLDS, and so does a reading nobody could take. Nothing is
  recorded or routed and the attempt stands: the next tick's fetch counts the
  head again, and a head the base advanced past is continued to the next
  rebase, which replaces it.
- A base on that tip that no longer carries what the replay was made onto --
  rewound before the tick's fetch, so the head carries commits over it beyond
  the anchor's own -- DEFERS. No later tick moves that base back, so the
  decision is refused for good: nothing is run or recorded for the head, a
  captured decision is abandoned, and the fresh reviewer owes the evidence.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.base_sync import rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import report_evidence_models as _evidence_models
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

_REFUSALS = MappingProxyType({
    _BaseStanding.MOVED: _evidence_models.ReportEvidence(
        _HOLD, "the base moved after the rebased head was counted against it",
    ),
    _BaseStanding.UNREAD: _evidence_models.ReportEvidence(
        _HOLD, "the base the rebased head was counted against could not be read again",
    ),
    _BaseStanding.DROPPED: _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the base no longer carries the commits the rebased head was replayed onto",
    ),
})


def standing_refusal(finish: LandedFinish) -> _evidence_models.ReportEvidence | None:
    """Why `finish`'s landed head no longer stands on the base it was counted against, or None where it does."""
    standing = _rewrite_facts._standing_on_the_remote_base(
        finish.spec, _worktree_paths._worktree_path(finish.spec, finish.issue.number), finish.landed.candidate,
    )
    return _REFUSALS.get(standing)
