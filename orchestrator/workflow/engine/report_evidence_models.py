# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one reading of the world says about finishing a report transaction.

Four answers rather than two, because what a refusal is OWED differs and a
caller that could not tell them apart would either strand the issue or publish
over an unproved world.

PROVED is the only answer that licenses a publication, and it is the only one
that carries anything: the pull request it was proved against travels with it,
because the caller's next step is a request and re-fetching would be a second
moment. A publication proved against one reading and made against another is
exactly the window this evidence exists to close.

HOLD is a reading nobody could take -- a pull request GitHub would not serve, a
`git status` that failed. The tick stops quietly and the next one asks again,
because the condition is usually gone by then and there is nothing a human could
do about it meanwhile.

DEFER also refuses to complete, and lets the tick carry on. It is the answer for
everything structural: a dirty tree, a head that moved, a commit the pull request
does not carry yet, requirements somebody edited. What would CLEAR each of those
is a route behind this evidence -- the publication gate that pushes, the drift
resume that answers the edit, the dirty-worktree park -- so holding them would
strand the issue behind the very handler that fixes them.

ENDED is the pull request being over. A report published onto a merged or closed
thread is a comment nobody reads, so the transaction is retired rather than
retried.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ReportEvidenceVerdict(StrEnum):
    """Which of the four answers one reading gave."""

    PROVED = "proved"
    HOLD = "hold"
    DEFER = "defer"
    ENDED = "ended"


@dataclass(frozen=True)
class ReportEvidence:
    """One reading, what it refused for, and the pull request it proved.

    `refusal` is the sentence a log or a park quotes. It names the reading that
    failed rather than the value it failed on, so a diagnostic never repeats
    content this owner was protecting.
    """

    verdict: ReportEvidenceVerdict
    refusal: str = ""
    pull_request: Any = None

    @property
    def proved(self) -> bool:
        """Whether this reading licenses the transaction to complete."""
        return self.verdict is ReportEvidenceVerdict.PROVED

    @property
    def holds(self) -> bool:
        """Whether this reading stops the tick rather than letting it carry on."""
        return self.verdict is ReportEvidenceVerdict.HOLD
