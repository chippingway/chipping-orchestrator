# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick does with an issue whose pinned record admission refuses.

Nothing it would need the record for -- no reconciliation, park, greeting,
handler, comment, pinned write, relabel, close, or reopen -- on every dispatch
mode, labelled or not, open or closed, and one local line naming the
repository, the issue, and the version found against the one supported. What
decides is the record read once the issue's writer claim is granted, never what
was read before it. A fresh issue and a current record beside a refused one
run as ever.
"""
from __future__ import annotations

import functools
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import SUPPORTED_SCHEMA_VERSION, PinnedState
from orchestrator.workflow.stages.decomposition import split_receipts as _split_receipts
from tests.support.fakes import make_issue
from tests.workflow.engine.grant_edit_support import edited_at_grant
from tests.workflow.engine.writer_claim_test_support import (
    CANONICAL_SLUG,
    DISPATCH_MODES,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_IMPLEMENTING

_WORKFLOW_LOG = "orchestrator.workflow"

# A version this build does not admit, and what a record of the issue's own
# work carries beside it: fields that would read as live work -- a branch, a
# pull request, spent runs -- to anything that took the record as current.
_ANOTHER_VERSION = 2

_RECORDED = MappingProxyType({
    "branch": "orchestrator/acme__widget/issue-21",
    "pr_number": 210,
    "agent_runs_used": 3,
})

# Refused records, each beside a road it would otherwise reach: a newer
# version on a fan-out stage's handler, an unversioned record on an unlabelled
# split's child whose seed check would park it, a comment that will not parse
# on family work, and a newer version on a closed issue whose stage would end
# it.
_VERSIONED = 21
_UNVERSIONED_CHILD = 22
_UNPARSED = 23
_CLOSED_VERSIONED = 27

# The version each is reported with: none where its record carries none or
# does not parse.
_FOUND = MappingProxyType({
    _VERSIONED: _ANOTHER_VERSION,
    _UNVERSIONED_CHILD: None,
    _UNPARSED: None,
    _CLOSED_VERSIONED: _ANOTHER_VERSION,
})

# What runs beside them: a fresh labelled issue, a current record, and a
# fresh unlabelled issue on its way to pickup.
_FRESH = 24
_CURRENT = 25
_FRESH_UNLABELLED = 26
_RUNNABLE = frozenset((_FRESH, _CURRENT, _FRESH_UNLABELLED))

# The split the unversioned child's receipt says seeded it.
_PARENT = 20
_ATTEMPT = "0123456789abcdef"

_HANDLED_LABELS = (None, LABEL_IMPLEMENTING, LABEL_DECOMPOSING)

# Two issues whose record moves before the claim is granted: one current when
# polled and refused by the grant, and one the other way about.
_REFUSED_BY_THE_GRANT = 31
_ADMITTED_BY_THE_GRANT = 32


class RefusedRecordDispatchTest(WriterClaimDispatchCase):
    """A refused record is dispatched nowhere, beside issues that run."""

    def test_refused_records_are_left_as_they_stand(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._seeded()
                standing = self._standing()

                self.assertEqual(
                    self._ticked_and_reported(limit, scheduled=scheduled),
                    (_RUNNABLE, set(_FOUND)),
                    "only the fresh and current issues run, and each refused one is reported with its version",
                )
                self.assertEqual(self._standing(), standing, "no refused issue is written, relabelled, or reopened")
                self.assertEqual(self._posted_on() & set(_FOUND), set(), "nothing is posted on one")

    def _seeded(self) -> None:
        """The four refused records and the three issues that run, in a fresh repository."""
        self.fresh_repository()
        stamp = _split_receipts.receipt(_PARENT, _ATTEMPT, 0, None)
        self.github.add_issue(make_issue(
            _UNVERSIONED_CHILD, body=f"the slice\n\n{stamp}", author=self.github._bot_login,
        ))
        for issue_number, label in (
            (_VERSIONED, LABEL_IMPLEMENTING),
            (_UNPARSED, LABEL_DECOMPOSING),
            (_FRESH, LABEL_IMPLEMENTING),
            (_CURRENT, LABEL_IMPLEMENTING),
            (_FRESH_UNLABELLED, None),
        ):
            self.github.add_issue(make_issue(issue_number, label=label))
        self.github.add_issue(make_issue(_CLOSED_VERSIONED, label=LABEL_IMPLEMENTING, closed=True))
        for versioned in (_VERSIONED, _CLOSED_VERSIONED):
            self.github.seed_state(versioned, raw=True, schema_version=_ANOTHER_VERSION, **_RECORDED)
        self.github.seed_state(_UNVERSIONED_CHILD, raw=True, parent_number=_PARENT)
        _unparsed(self.github, _UNPARSED)
        self.github.seed_state(_CURRENT, **_RECORDED)

    def _ticked_and_reported(self, limit: int, *, scheduled: bool) -> tuple[set[int], set[int]]:
        """One tick, answering the issues a handler ran on and the refused issues a warning reported."""
        stand_in = StandInHandler()
        with self.assertLogs(_WORKFLOW_LOG, level="WARNING") as logged:
            self.ticked(stand_in, limit=limit, scheduled=scheduled, labels=_HANDLED_LABELS)
            reported = {
                refused for refused, found in _FOUND.items()
                if _said_refused(logged.output, refused, found)
            }
        return set(stand_in.ran), reported

    def _standing(self) -> dict:
        """Each refused issue's record, admission, labels, and whether it is closed."""
        return {
            issue_number: (
                self.github.pinned_data(issue_number),
                self.github.read_pinned_state(self.github.get_issue(issue_number)).admission_status,
                [label.name for label in self.github.get_issue(issue_number).labels],
                self.github.get_issue(issue_number).closed,
            )
            for issue_number in _FOUND
        }

    def _posted_on(self) -> set[int]:
        """The issues anything was commented on or relabelled."""
        relabelled = {entry[0] for entry in self.github.label_history}
        return relabelled.union(_commented_on(self.github))


class ClaimedAdmissionTest(WriterClaimDispatchCase):
    """Admission is decided by the record read once the claim is granted, whatever came before it."""

    def test_the_grant_reading_decides(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                stand_in = StandInHandler()

                with edited_at_grant(self._moving_at_the_grant()):
                    self.ticked(stand_in, limit=limit, scheduled=scheduled)

                self.assertEqual(stand_in.ran, [_ADMITTED_BY_THE_GRANT])
                self.assertEqual(
                    (self.github.pinned_data(_REFUSED_BY_THE_GRANT), _commented_on(self.github)),
                    (dict(_RECORDED), [_ADMITTED_BY_THE_GRANT]),
                    "the refused record is left unwritten and nothing is posted on it",
                )

    def _moving_at_the_grant(self) -> dict:
        """Both issues seeded as the poll reads them, and the edit that moves each record as its claim is granted."""
        self.fresh_repository()
        self.github.add_issue(make_issue(_REFUSED_BY_THE_GRANT, label=LABEL_IMPLEMENTING))
        self.github.add_issue(make_issue(_ADMITTED_BY_THE_GRANT, label=LABEL_IMPLEMENTING))
        self.github.seed_state(_REFUSED_BY_THE_GRANT, **_RECORDED)
        self.github.seed_state(_ADMITTED_BY_THE_GRANT, raw=True, **_RECORDED)
        return {
            _REFUSED_BY_THE_GRANT: functools.partial(
                self.github.seed_state, _REFUSED_BY_THE_GRANT, raw=True, **_RECORDED,
            ),
            _ADMITTED_BY_THE_GRANT: functools.partial(
                self.github.seed_state, _ADMITTED_BY_THE_GRANT, **_RECORDED,
            ),
        }


def _unparsed(github, issue_number: int) -> None:
    """Pin a comment on the issue that will not parse, as a hand edit leaves one."""
    github.seed_state(issue_number, **_RECORDED)
    pinned = github.read_pinned_state(github.get_issue(issue_number))
    github._pinned[issue_number] = PinnedState(comment_id=pinned.comment_id, parsed=False)


def _commented_on(github) -> list[int]:
    """The issue each comment this tick posted went onto, in the order they went."""
    return [issue_number for issue_number, _body in github.posted_comments]


def _said_refused(output: list[str], issue_number: int, found) -> bool:
    """Whether a warning names the repository, the issue, and the version found against the one supported."""
    return any(
        f"repo={CANONICAL_SLUG} issue=#{issue_number} pinned comment" in line
        and f"found schema_version {found!r}, supported {SUPPORTED_SCHEMA_VERSION}" in line
        for line in output
    )


if __name__ == "__main__":
    unittest.main()
