# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stable import surface for the in-memory GitHub test doubles.

The doubles are split across the modules of `tests.support.github`; this module
is the one name the rest of the suite reaches all of them through.
"""
from __future__ import annotations

from tests.support.github import (
    client as _client,
    factories as _factories,
    lazy as _lazy,
    models as _models,
    pull_request_models as _pull_request_models,
)

FakeGitHubClient = _client.FakeGitHubClient
FakeComment = _models.FakeComment
FakeIssue = _models.FakeIssue
FakeLabel = _models.FakeLabel
FakePR = _pull_request_models.FakePR
DEFAULT_PR_HEAD_SHA = _pull_request_models.DEFAULT_PR_HEAD_SHA
FakePRRef = _pull_request_models.FakePRRef
FakePRRepo = _pull_request_models.FakePRRepo
FakePRReview = _pull_request_models.FakePRReview
FakeUser = _models.FakeUser
LazyPullRequest = _lazy.LazyPullRequest
make_issue = _factories.make_issue
