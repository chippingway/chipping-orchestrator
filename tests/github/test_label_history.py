# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one question about an issue's PAST this client answers.

A label removed leaves the issue looking exactly like one that never carried
it, so a caller deciding whether a write of its own ever landed has nothing on
the issue's surface to read. The events endpoint is what remembers, and what
this reads back off it is the newest workflow label THIS orchestrator applied
-- which is a narrower thing than "was that label ever there", in the two ways
that matter.

The events are shaped as PyGithub serves them, because every filter here is
over a field of that shape: the event kind, the actor's login, and the label's
name. A double that carried only what a caller happened to need would answer
the same for a collaborator's label as for the orchestrator's own.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.github.client import GitHubClient

_BOT_LOGIN = "orchestrator"

_COLLABORATOR = "a-maintainer"

_REJECTED = "rejected"

_DECOMPOSING = "workflow:decomposing"

_PAUSED = "paused"

# A label the repository names its own issues by, which this vocabulary does
# not recognize at all.
_HOUSE_LABEL = "needs-triage"

# A bare name matching a namespaced state, which this account may have applied
# under an earlier build. It is no current state either.
_OBSOLETE_LABEL = "implementing"

_LABELED = "labeled"

_UNLABELED = "unlabeled"

_ISSUE_NUMBER = 41


def _event(kind: str, label: str, actor: str = _BOT_LOGIN):
    """One issue event as PyGithub hands it over.

    The label is built and then named, since `name` is the one attribute a
    mock's constructor claims for itself.
    """
    named = MagicMock()
    named.name = label
    return MagicMock(
        event=kind, label=named, actor=MagicMock(login=actor),
    )


def _client_over(*events) -> tuple[GitHubClient, MagicMock]:
    """A bare client and the issue whose timeline serves these events."""
    client = GitHubClient.__new__(GitHubClient)
    client._bot_login = _BOT_LOGIN
    issue = MagicMock(number=_ISSUE_NUMBER)
    issue.get_events.return_value = iter(events)
    return client, issue


class LastAppliedTest(unittest.TestCase):
    """Which application the reading answers with, over a real event shape."""

    def test_the_newest_of_ours_wins(self) -> None:
        # An issue reaches the same state more than once, and every state this
        # workflow moves it to is itself an application -- so a label applied
        # after another is proof the first is not the latest.
        client, issue = _client_over(
            _event(_LABELED, _REJECTED),
            _event(_UNLABELED, _REJECTED),
            _event(_LABELED, _DECOMPOSING),
        )

        self.assertEqual(
            client.last_workflow_label_applied(issue), _DECOMPOSING,
        )

    def test_a_collaborators_label_is_not_ours(self) -> None:
        # The one a caller may not read as a write of its own. A collaborator
        # is free to apply and remove any name by hand, and adopting one as
        # this orchestrator's terminal would let somebody outside the workflow
        # forge the record of a write it never made.
        client, issue = _client_over(
            _event(_LABELED, _DECOMPOSING),
            _event(_LABELED, _REJECTED, actor=_COLLABORATOR),
            _event(_UNLABELED, _REJECTED, actor=_COLLABORATOR),
        )

        self.assertEqual(
            client.last_workflow_label_applied(issue), _DECOMPOSING,
        )

    def test_a_control_or_house_label_is_no_state(self) -> None:
        # A control label is an operator's modifier rather than a state this
        # workflow put the issue in, so a `paused` applied over a terminal may
        # not displace it -- and a name this vocabulary does not know is not a
        # state at all, an obsolete bare one this account applied included.
        client, issue = _client_over(
            _event(_LABELED, _REJECTED),
            _event(_LABELED, _PAUSED),
            _event(_LABELED, _HOUSE_LABEL),
            _event(_LABELED, _OBSOLETE_LABEL),
        )

        self.assertEqual(
            client.last_workflow_label_applied(issue), _REJECTED,
        )

    def test_a_walk_that_failed_establishes_nothing(self) -> None:
        client, issue = _client_over()
        issue.get_events.side_effect = RuntimeError("no")

        with self.assertLogs("orchestrator.github"):
            self.assertIsNone(client.last_workflow_label_applied(issue))

    def test_an_unknown_account_asks_nothing(self) -> None:
        # The reading is about a write this orchestrator made, so a client
        # that could not establish which account it writes under has no way to
        # attribute one -- and answers nothing rather than trusting every
        # actor.
        client, issue = _client_over(_event(_LABELED, _REJECTED))
        client._bot_login = None

        self.assertIsNone(client.last_workflow_label_applied(issue))
        issue.get_events.assert_not_called()


if __name__ == "__main__":
    unittest.main()
