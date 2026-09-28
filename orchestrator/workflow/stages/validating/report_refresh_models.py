# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a report refresh freezes for the helper that reads its run.

`_ReportRefresh` carries what the refresh proved before the developer was
asked, because every one of those facts is one the helper reading the run has
to hold the world to again. `debt` is the claim the refresh answers, and its
`rewritten_head` is the commit the pull request, the code-publication receipt,
and a clean checkout were each proved to stand on before the run -- the head the
report is asked about and recorded for. `requirements` is the baseline the
drift check had just proved current, which the report is stamped with: re-read
once the agent is back, it could be an edit the session never saw.

It is also where the requirements are read again once the run is back --
whether the issue, fetched afresh since an edit made while the agent was out
exists only on a new read, says anything the baseline does not -- and where a
refusal parks, under `report_undeliverable` with the debt recorded, since both
helpers park the same way.

The boundary against `models.py` is the one `drift_models.py` draws: this
record is built and read inside the refresh route alone, so it stays beside
that route rather than charging every importer of the stage's shared records
for it.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import drift as _drift
from orchestrator.workflow.engine.report_rewrite_debt import RewriteDebt
from orchestrator.workflow.stages.validating import report_settlement as _settlement


@dataclass(frozen=True)
class _ReportRefresh:
    """One refresh of the report a rewritten head is owed, frozen before its run."""

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    debt: RewriteDebt
    requirements: str

    @property
    def head(self) -> str:
        """The commit this orchestrator rewrote the pull request onto."""
        return self.debt.rewritten_head

    def requirements_moved(self, issue: Issue) -> bool:
        """Whether `issue` says anything the frozen baseline does not."""
        return _drift._detect_user_content_change(self.gh, issue, self.state) is not None

    def parks(self, detail: str) -> None:
        """Park the report this refresh cannot deliver, once, for a human (`report_undeliverable`)."""
        _settlement._parks(self.gh, self.issue, self.state, detail)

    def write(self) -> None:
        """Write what the refresh staged onto the pinned comment."""
        self.gh.write_pinned_state(self.issue, self.state)
