# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The release of a report no checkout can publish, landed over the comment as it stands.

A checkout this host proves gone or dirty parks the issue and releases the
report it recorded in that park's own write. The write is a guarded commit
decided on every report record the tick read: what another road wrote outside
it meanwhile survives, a report record another road wrote since is never
released with the one the tick found -- no notice, no park, the tick ended --
and a release GitHub took and never confirmed is announced once, the next tick
finding nothing left to release.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType

from orchestrator.workflow.engine import report_records as _records
from orchestrator.workflow.stages.fixing import report_recovery as _recovery
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.stages.fixing import (
    report_crash_support as crash,
    report_settlement_support as support,
)
from tests.workflow.stages.implementing_fixing_test_cases import (
    posted_comment_contains,
)

_GONE = partial(crash.a_checkout, present=False)

# Fields another road writes that the release neither owns nor is decided on:
# another domain's evidence, and a usage total.
_UNOWNED = MappingProxyType({
    "verification_evidence_current": {"revision": 3},
    "issue_total_tokens": 150,
})

# Report records another road writes since the tick read the comment, each a
# record the release was not decided on and may not drop.
_NEWER = (
    ("a newer delivery", MappingProxyType({_records.DELIVERED_REPORT: "delivered since"})),
    ("a transaction", MappingProxyType({_records.PENDING_REPORT: "bound since"})),
    ("a settled report", MappingProxyType({_records.CURRENT_REPORT: "settled since"})),
)


class GuardedReleaseTest(unittest.TestCase, support.FixingReportCase):
    """The release lands beside another road's writes, and never over a record it was not decided on."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        self.records_the_report()

    def test_a_release_lands_beside_another_road(self) -> None:
        # Evidence and usage another road wrote since the tick read the
        # comment stay as it wrote them; the record is released, the reader
        # it consumed advanced, and the park announced once.
        commit_support.another_road(self.gh, self.issue, **_UNOWNED)

        with _GONE():
            self.assertFalse(_recovery._recovers_an_unbound_delivery(self.ctx()))

        released = self.pinned()
        self.assertEqual(
            (
                {field: released[field] for field in _UNOWNED},
                released[_records.DELIVERED_REPORT],
                released[support.PR_WATERMARK],
                released[support.PARK_REASON],
                len(self.gh.posted_comments),
            ),
            (dict(_UNOWNED), None, support.CONSUMED_ID, crash.UNDELIVERABLE, 1),
        )

    def test_a_newer_record_is_never_released(self) -> None:
        # A report record another road wrote since the tick read the comment
        # refuses the release before its notice: nothing posted, nothing
        # released, the comment that road's, and the tick ended over a state
        # it may no longer write.
        for newer, fields in _NEWER:
            with self.subTest(newer=newer):
                self.setUp()
                left = commit_support.another_road(self.gh, self.issue, **fields)

                with _GONE():
                    self.assertTrue(_recovery._recovers_an_unbound_delivery(self.ctx()))

                self.assertEqual(
                    (self.pinned(), self.gh.posted_comments, self.state.withheld),
                    (left, [], True),
                )

    def test_a_lost_release_is_announced_once(self) -> None:
        # GitHub took the release and its answer never came back, so the tick
        # ends with the notice posted once. The next tick finds the record
        # released and the park standing: nothing left to release or announce.
        self.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)
        with _GONE():
            self.assertTrue(_recovery._recovers_an_unbound_delivery(self.ctx()))
        self.gh.pinned_failures.lost.discard(support.ISSUE_NUMBER)
        self.state = self.gh.read_pinned_state(self.issue)

        with _GONE():
            self.assertFalse(_recovery._recovers_an_unbound_delivery(self.ctx()))

        self.assertEqual(
            (
                self.pinned()[_records.DELIVERED_REPORT],
                self.pinned()[support.PARK_REASON],
                len(self.gh.posted_comments),
            ),
            (None, crash.UNDELIVERABLE, 1),
        )
        self.assertTrue(posted_comment_contains(self.gh, crash.UNPUBLISHABLE_PHRASE))


if __name__ == "__main__":
    unittest.main()
