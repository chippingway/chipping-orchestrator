# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Community-contribution classification and deduplication."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.labels import COMMUNITY_CONTRIBUTION_LABEL
from orchestrator.workflow.engine import community
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine.community_test_support import (
    ALLOWED_LOGIN,
    ALLOWLIST_CONFIG,
    BARE_MARKER,
    OUTSIDER_LOGIN,
    TEST_SPEC,
    make_pr,
    record_label_lookups,
)

_ALLOWED_LOGIN = ALLOWED_LOGIN
_ALLOWLIST_CONFIG = ALLOWLIST_CONFIG
_BARE_MARKER = BARE_MARKER
_OUTSIDER_LOGIN = OUTSIDER_LOGIN
_TEST_SPEC = TEST_SPEC
_pr = make_pr
_record_label_lookups = record_label_lookups


def _label_names(pr) -> list[str]:
    return [label.name for label in pr.labels]


class SweepCommunityContributionPRsTest(unittest.TestCase):
    """`_sweep_community_contribution_prs` labels open PRs whose authors
    are not in `ALLOWED_ISSUE_AUTHORS` and posts a HITL ping comment once
    per PR. An empty allowlist trusts everyone, so the sweep is a no-op
    there.
    """

    def test_no_op_when_allowlist_is_empty(self) -> None:
        gh = FakeGitHubClient()
        gh.add_pr(_pr(1, author=_OUTSIDER_LOGIN))
        with patch.object(config, _ALLOWLIST_CONFIG, ()):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertEqual(gh.pulls[1].labels, [])
        self.assertEqual(gh.posted_pr_comments, [])

    def test_outsider_pr_gets_labeled_and_hitl_pinged(self) -> None:
        gh = FakeGitHubClient()
        gh.add_pr(_pr(7, author=_OUTSIDER_LOGIN))
        with patch.object(config, _ALLOWLIST_CONFIG, (_ALLOWED_LOGIN,)), \
             patch.object(config, "HITL_MENTIONS", f"@{_ALLOWED_LOGIN}"):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertTrue(
            gh.pr_has_label(gh.pulls[7], COMMUNITY_CONTRIBUTION_LABEL)
        )
        self.assertEqual(len(gh.posted_pr_comments), 1)
        pr_number, body = gh.posted_pr_comments[0]
        self.assertEqual(pr_number, 7)
        self.assertIn(f"@{_ALLOWED_LOGIN}", body)
        self.assertIn(f"@{_OUTSIDER_LOGIN}", body)

    def test_allowed_author_is_skipped(self) -> None:
        gh = FakeGitHubClient()
        gh.add_pr(_pr(1, author=_ALLOWED_LOGIN))
        gh.add_pr(_pr(2, author="Geserdugarov"))  # case-insensitive
        with patch.object(config, _ALLOWLIST_CONFIG, (_ALLOWED_LOGIN,)):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertEqual(gh.pulls[1].labels, [])
        self.assertEqual(gh.pulls[2].labels, [])
        self.assertEqual(gh.posted_pr_comments, [])

    def test_bot_authored_pr_is_skipped(self) -> None:
        # Dependabot (and other Bot-account) PRs open structurally and are
        # not community contributions. They must not earn the label or a
        # HITL ping even though their author is outside the allowlist.
        gh = FakeGitHubClient()
        gh.add_pr(
            _pr(5, author="dependabot[bot]", user_type="Bot")
        )
        with patch.object(config, _ALLOWLIST_CONFIG, (_ALLOWED_LOGIN,)):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertEqual(gh.pulls[5].labels, [])
        self.assertEqual(gh.posted_pr_comments, [])

    def test_canonical_marker_suppresses_ping(self) -> None:
        # The namespaced label is the sweep's one dedup marker: a PR
        # carrying it has had its HITL ping, and is asked about that label
        # alone.
        gh = FakeGitHubClient()
        gh.add_pr(
            _pr(3, author=_OUTSIDER_LOGIN, labels=(COMMUNITY_CONTRIBUTION_LABEL,))
        )
        looked_up: list[str] = []
        with (
            patch.object(config, _ALLOWLIST_CONFIG, (_ALLOWED_LOGIN,)),
            _record_label_lookups(gh, looked_up),
        ):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertEqual(
            _label_names(gh.pulls[3]), [COMMUNITY_CONTRIBUTION_LABEL],
        )
        self.assertEqual(gh.posted_pr_comments, [])
        self.assertEqual(looked_up, [COMMUNITY_CONTRIBUTION_LABEL])

    def test_bare_marker_is_repository_metadata(self) -> None:
        # A bare `community_contribution` marks nothing: the PR carrying only
        # it is pinged and earns the namespaced marker beside the bare label,
        # which it keeps, and the next sweep finds the namespaced marker and
        # pings no more. The bare name is never asked about.
        gh = FakeGitHubClient()
        gh.add_pr(_pr(4, author=_OUTSIDER_LOGIN, labels=(_BARE_MARKER,)))
        looked_up: list[str] = []
        with (
            patch.object(config, _ALLOWLIST_CONFIG, (_ALLOWED_LOGIN,)),
            _record_label_lookups(gh, looked_up),
        ):
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
            community._sweep_community_contribution_prs(gh, _TEST_SPEC)
        self.assertEqual(
            _label_names(gh.pulls[4]),
            [_BARE_MARKER, COMMUNITY_CONTRIBUTION_LABEL],
        )
        self.assertEqual(
            [pr_number for pr_number, _ in gh.posted_pr_comments], [4],
        )
        self.assertEqual(set(looked_up), {COMMUNITY_CONTRIBUTION_LABEL})
