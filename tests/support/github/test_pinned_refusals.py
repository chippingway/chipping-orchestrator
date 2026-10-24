# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What this double's pinned record refuses, as the real writer refuses it.

A case drives a stage through the in-memory client and reads back what it
pinned, so a record the double would overwrite where production preserves it
is a case asserting on a write production never makes. A record that would not
parse -- built the way a case builds one, as an unparsed state and nothing
more -- and one refused admission both stand: the whole-state write raises
`RecordRefused` as the real writer does, counted nowhere, and the record reads
back refused.
"""
from __future__ import annotations

import unittest

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, AdmissionStatus, PinnedState
from tests.support.fakes import FakeGitHubClient, make_issue

_ISSUE = 703
_BRANCH_KEY = "branch"
_RECORDED = "orchestrator/recorded"
_STAGED = "orchestrator/staged"


def _unparsed(client: FakeGitHubClient, issue) -> None:
    """The pinned comment edited in place into something that does not parse."""
    client.seed_state(issue, **{_BRANCH_KEY: _RECORDED})
    recorded = client.read_pinned_state(issue).comment_id
    client._pinned[_ISSUE] = PinnedState(comment_id=recorded, parsed=False)


def _another_version(client: FakeGitHubClient, issue) -> None:
    """A record written under a version this build does not admit."""
    client.seed_state(issue, raw=True, **{SCHEMA_VERSION_KEY: 2, _BRANCH_KEY: _RECORDED})


# Each refused record, and what it reads back as.
_REFUSED = (
    (_unparsed, AdmissionStatus.MALFORMED),
    (_another_version, AdmissionStatus.UNSUPPORTED),
)


class PinnedRefusalTest(unittest.TestCase):
    """The whole-state write lands over a current record and over nothing refused."""

    def test_a_refused_record_stands(self) -> None:
        for refuses, admitted_as in _REFUSED:
            with self.subTest(refused=admitted_as):
                client = FakeGitHubClient([make_issue(_ISSUE)])
                issue = client.get_issue(_ISSUE)
                refuses(client, issue)
                pinned = client._pinned[_ISSUE]

                with self.assertRaises(_pinned_refusal.RecordRefused):
                    client.write_pinned_state(issue, PinnedState(pinned.comment_id, {_BRANCH_KEY: _STAGED}))

                self.assertEqual(client.write_state_calls, 0)
                self.assertIs(client._pinned[_ISSUE], pinned)
                self.assertIs(client.read_pinned_state(issue).admission_status, admitted_as)

    def test_a_current_record_is_rewritten(self) -> None:
        client = FakeGitHubClient([make_issue(_ISSUE)])
        issue = client.get_issue(_ISSUE)
        client.seed_state(issue, **{_BRANCH_KEY: _RECORDED})
        staged = client.read_pinned_state(issue)
        staged.set(_BRANCH_KEY, _STAGED)

        client.write_pinned_state(issue, staged)

        self.assertEqual(client.write_state_calls, 1)
        self.assertEqual(client.read_pinned_state(issue).get(_BRANCH_KEY), _STAGED)


if __name__ == "__main__":
    unittest.main()
