# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed scheduler submissions and the normalization slot accounting reads them through."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SubmissionRequest:
    """Caller-facing request for one issue worker."""

    repo_slug: str
    issue_number: int
    fn: Callable[[], None]
    family: bool = False
    cap_exempt: bool = False
    per_repo_cap: int | None = None


@dataclass(frozen=True)
class Submission:
    """Normalized request used by slot reservation and completion release."""

    repo_slug: str
    issue_number: int
    fn: Callable[[], None]
    family: bool
    cap_exempt: bool
    per_repo_cap: int

    @property
    def key(self) -> tuple[str, int]:
        return self.repo_slug, self.issue_number


def normalize_submission(
    request: SubmissionRequest,
    default_per_repo_cap: int,
) -> Submission:
    """Normalize integer fields and the optional per-repository override."""
    selected_cap = (
        default_per_repo_cap
        if request.per_repo_cap is None
        else max(1, int(request.per_repo_cap))
    )
    return Submission(
        repo_slug=request.repo_slug,
        issue_number=int(request.issue_number),
        fn=request.fn,
        family=request.family,
        cap_exempt=request.cap_exempt,
        per_repo_cap=selected_cap,
    )
