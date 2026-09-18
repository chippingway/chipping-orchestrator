# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The descriptions a reused pull request keeps, whatever they say.

The reuse rewrites a body that does not name this implementation, and that
rewrite is the one step of a publication nothing can take back: GitHub keeps no
copy of the text it replaces. `test_report_publication` covers the bodies it
leaves alone because of what they SAY -- this implementation's own, and a
report verified there. These are the bodies it leaves alone because of what
the pinned comment says about them: a pull request this stage has already
pushed onto, whose description the pushing tick settled, and one a record
nobody can read may still name as its report's location.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from tests.workflow.fixtures import LABEL_VALIDATING, SHA_LENGTH, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

REUSED_PR = 71

# What a human wrote over the body: no closing reference, no attribution.
HUMAN_DESCRIPTION = "### Notes\n\nRewritten by hand, and meant to stay."

# The receipt an earlier push of this issue's left, onto the reused pull
# request: a commit the branch has since moved past.
EARLIER_RECEIPT = MappingProxyType({
    "implementing_published_sha": "e" * SHA_LENGTH,
    "implementing_published_pr": REUSED_PR,
    "implementing_published_lease": None,
})

# A record whose location still names the reused pull request's description
# while the rest of it will not read.
DAMAGED_RECORD = MappingProxyType({
    "location_pr": REUSED_PR,
    "location_comment": None,
    "revision": "damaged",
})


class DescriptionGuardTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_pushed_onto_description_is_left_intact(self) -> None:
        # The tick that pushed onto this pull request wrote, adopted or
        # preserved its description, so a body without the attribution now is
        # one a human changed since. The report goes out as a comment beside
        # it, and the work is handed on.
        github, issue, reused = self._reused_over(**EARLIER_RECEIPT)

        self.deliver(github, issue, support.ready_message())

        self.assertEqual(
            (github.edited_pr_bodies, reused.body), ([], HUMAN_DESCRIPTION),
        )
        self.assertEqual(len(support.published_reports(github, REUSED_PR)), 1)
        self.assertIn(
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

    def _delivers(self, github, issue):
        """Run the ordinary tick, whose developer reports for publication."""
        return self.deliver(github, issue, support.ready_message())


if __name__ == "__main__":
    unittest.main()
