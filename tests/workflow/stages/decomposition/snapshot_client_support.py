# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The in-memory client with every issue fetch a snapshot of its own, the way each real fetch is an object.

The plain double hands every caller the one issue object, so a label applied
"on GitHub" shows up on readings taken before it -- which no real client does.
Here a label a case applies to the issue as GitHub holds it reaches only the
fetches taken after it, and a relabel is written through off the labels of
the snapshot it was made on, so a write made on an older reading drops a label
applied since, exactly as a real label write would.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from tests.support.fakes import FakeGitHubClient, FakeIssue, FakeLabel


class SnapshotClient(FakeGitHubClient):
    """The in-memory client, every fetch of an issue a snapshot of its own.

    A relabel is written through to the issue as GitHub holds it, off the
    labels of the snapshot it was made on.
    """

    def get_issue(self, number: int):
        """A snapshot of the issue as GitHub holds it now, with labels of its own."""
        fetched = copy.copy(super().get_issue(number))
        fetched.labels = list(fetched.labels)
        return fetched

    def set_workflow_label(self, issue, label, **options) -> None:
        """Relabel the snapshot, and write its labels through to the issue as GitHub holds it."""
        super().set_workflow_label(issue, label, **options)
        self._issues[issue.number].labels = list(issue.labels)

    def remote(self, number: int) -> FakeIssue:
        """The issue as GitHub holds it, which a human's label edit lands on."""
        return self._issues[number]

    def applied(self, number: int, label: str) -> None:
        """Apply `label` to the issue as GitHub holds it, the way a human would."""
        self.remote(number).labels.append(FakeLabel(label))

    def lifted(self, number: int, label: str) -> None:
        """Take `label` off the issue as GitHub holds it."""
        remote = self.remote(number)
        remote.labels = [kept for kept in remote.labels if kept.name != label]

    def label_names(self, number: int) -> list[str]:
        """The names of the labels the issue carries as GitHub holds it."""
        return [kept.name for kept in self.remote(number).labels]


@dataclass(frozen=True)
class Applied:
    """A human applying `label` to issue `number` as GitHub holds it, landing behind a request.

    In the shape `ready_test_support.LandsAfter` calls a landing with.
    """

    number: int
    label: str

    def __call__(self, gh: SnapshotClient, issue) -> None:
        """Apply the label, whichever request it landed behind."""
        gh.applied(self.number, self.label)
