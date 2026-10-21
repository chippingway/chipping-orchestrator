# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared values and builders for community-contribution sweeps."""
from __future__ import annotations

from functools import partial
from unittest.mock import patch

from tests.support.fakes import FakeGitHubClient, FakeLabel, FakePR, FakeUser
from tests.workflow.repo_values import _TEST_SPEC

OUTSIDER_LOGIN = "outsider"
BARE_MARKER = "community_contribution"
ALLOWED_LOGIN = "geserdugarov"
ALLOWLIST_CONFIG = "ALLOWED_ISSUE_AUTHORS"
COMMENT_RETRY_PR_NUMBER = 11
TEST_SPEC = _TEST_SPEC


def make_pr(
    number: int,
    *,
    author: str,
    labels=(),
    user_type: str = "User",
) -> FakePR:
    return FakePR(
        number=number,
        user=FakeUser(author, type=user_type),
        labels=[FakeLabel(name) for name in labels],
    )


def fail_first_label_write(calls, original, pr, label) -> None:
    calls.append(pr.number)
    if pr.number == 1:
        raise RuntimeError("boom")
    original(pr, label)


def _record_label_lookup(looked_up, original, pr, label_name) -> bool:
    looked_up.append(label_name)
    return original(pr, label_name)


def record_label_lookups(gh: FakeGitHubClient, looked_up: list[str]):
    """Patch `gh` to collect every label name a pull request is asked about."""
    recording = partial(_record_label_lookup, looked_up, gh.pr_has_label)
    return patch.object(gh, "pr_has_label", side_effect=recording)
