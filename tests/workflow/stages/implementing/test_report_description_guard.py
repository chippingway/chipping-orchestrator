# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reused pull request's description keeps when this implementation names it.

A body that does not name this implementation gets the closing reference and the
attribution put above it, and the edit is the one step of a publication nothing
can take back: GitHub keeps no copy of the text it replaces. So what stays
beneath them is the description as it stands NOW -- read afresh right before the
write, so an edit a human lands after the lookup is the text kept -- and a
description nobody could re-read is not written over at all.
`test_report_publication` covers the bodies left alone because of what they
SAY; the last case here is one left alone because a record nobody can read may
still name it as its report's location.
"""

from __future__ import annotations

import copy
import unittest
from types import MappingProxyType
from unittest.mock import patch

from tests.workflow.fixtures import LABEL_VALIDATING, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

REUSED_PR = 71

# What a human wrote over the body: no closing reference, no attribution.
HUMAN_DESCRIPTION = "### Notes\n\nRewritten by hand, and meant to stay."

# What the body said when the lookup fetched it, before that edit landed.
LOOKED_UP_DESCRIPTION = "### Plan\n\nThe description the lookup fetched."

EARLIER_HEADING = "_Description before this implementation:_"

GET_PR = "get_pr"

# A record whose location still names the reused pull request's description
# while the rest of it will not read.
DAMAGED_RECORD = MappingProxyType({
    "location_pr": REUSED_PR,
    "location_comment": None,
    "revision": "damaged",
})


class DescriptionGuardTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_an_edit_after_the_lookup_is_kept(self) -> None:
        # The lookup handed over the body as it was when GitHub answered it,
        # and a human replaced it before the write. Built from the body in
        # hand, the edit would put back the version they replaced; read
        # afresh, what they wrote is what stays beneath this implementation's
        # lines, and the report goes out beside it.
        github, issue = self._edited_after_the_lookup()

        self.deliver(github, issue, support.ready_message())

        self.assertEqual(len(github.edited_pr_bodies), 1)
        named, earlier = github.edited_pr_bodies[0][1].split(EARLIER_HEADING)
        self.assertEqual(
            (
                named.startswith(f"Resolves #{support.REPORT_ISSUE}"),
                support.DEV_SESSION in named,
                earlier.strip(),
            ),
            (True, True, HUMAN_DESCRIPTION),
        )
        self.assertEqual(len(support.published_reports(github, REUSED_PR)), 1)
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_an_unreadable_description_holds(self) -> None:
        # Nobody could say what the description says now, so nothing is
        # written over it and nothing is handed on: the push stands, and the
        # commit it named is owed for the next tick to finish.
        github, issue, reused = self._reused_over()

        with patch.object(github, GET_PR, _Unreadable(REUSED_PR, github.get_pr)):
            self.deliver(github, issue, support.ready_message())

        self.assertEqual(
            (github.edited_pr_bodies, reused.body), ([], HUMAN_DESCRIPTION),
        )
        self.assertEqual(support.published_reports(github, REUSED_PR), [])
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_damaged_record_keeps_the_description(self) -> None:
        # The roads that park a damaged record run after the rewrite, so a
        # record read as no claim is a description destroyed before anything
        # says the record was damaged. The body stays, the record stays -- a
        # settlement would write over it -- and the work is not handed on.
        for record, run in (
            (support.DELIVERY_RECORD, self.republish),
            (support.CURRENT_RECORD, self._delivers),
        ):
            with self.subTest(record=record):
                github, issue, reused = self._reused_over(
                    dev_session_id=support.DEV_SESSION,
                    **{record: dict(DAMAGED_RECORD)},
                )

                run(github, issue)

                self.assertEqual(
                    (
                        github.edited_pr_bodies,
                        reused.body,
                        github.pinned_data(support.REPORT_ISSUE)[record],
                    ),
                    ([], HUMAN_DESCRIPTION, dict(DAMAGED_RECORD)),
                )
                self.assertNotIn(
                    (support.REPORT_ISSUE, LABEL_VALIDATING),
                    github.label_history,
                )

    def _reused_over(self, **pinned):
        """An issue carrying `pinned`, with a human's pull request on its branch."""
        github, issue = self.seeded()
        github.seed_state(support.REPORT_ISSUE, **pinned)
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=REUSED_PR,
        )
        reused.body = HUMAN_DESCRIPTION
        github.existing_open_pr[support.BRANCH] = reused
        return github, issue, reused

    def _edited_after_the_lookup(self):
        """A reused pull request a human edited after the lookup fetched it.

        The lookup's object is a copy holding the body it was fetched with,
        which is what a pull request GitHub handed back is: a snapshot.
        """
        github, issue, live = self._reused_over()
        looked_up = copy.copy(live)
        looked_up.body = LOOKED_UP_DESCRIPTION
        github.existing_open_pr[support.BRANCH] = looked_up
        return github, issue

    def _delivers(self, github, issue):
        """Run the ordinary tick, whose developer reports for publication."""
        return self.deliver(github, issue, support.ready_message())


class _Unreadable:
    """A pull-request read GitHub leaves unanswered for one number."""

    def __init__(self, number: int, reads) -> None:
        self._number = number
        self._reads = reads

    def __call__(self, number):
        """Read the pull request, unless it is the one nobody can read."""
        if number == self._number:
            raise RuntimeError("GitHub did not answer the pull-request read")
        return self._reads(number)


if __name__ == "__main__":
    unittest.main()
