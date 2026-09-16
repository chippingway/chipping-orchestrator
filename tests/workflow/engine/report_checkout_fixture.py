# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The git world one report transaction is reconciled against.

The local readings say what is on this host; the fetch result and the
divergence say what the ref the pull request is built from looks like. They
travel on one record so a case that moves either side is writing a divergence
rather than a race, and so the case class beside this keeps an attribute count
a reviewer can hold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.verification.status import _WorktreeStatus


@dataclass(frozen=True)
class Fetched:
    """What `_authed_fetch` hands back, as far as this evidence reads it."""

    returncode: int = 0


@dataclass
class Checkout:
    """Every git reading the report evidence takes, answered from one record."""

    path: Path
    head: str
    status: _WorktreeStatus
    fetched: int = 0
    remote: _BranchDivergence = field(default_factory=_BranchDivergence)


def fresh_checkout(path: str, head: str) -> Checkout:
    """A clean checkout standing on `head`, in sync with a remote on it too."""
    return Checkout(
        path=Path(path),
        head=head,
        status=_WorktreeStatus(readable=True),
        remote=_BranchDivergence(tip=head, readable=True),
    )
