# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a comment has to say before anything reads it as a request for runs.

The reading is pinned apart from the spending it pays for, because it is the
whole of what stands between a line somebody typed and agent time: a line of
its own, an exact whole count inside the bound, and the last such line in the
batch. Everything else buys nothing, and buys the same nothing however it
fails.
"""
from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.workflow.engine import (
    run_grant as _run_grant,
    run_grant_request as _run_grant_request,
)
from tests.workflow.engine import (
    run_grant_test_support as grant,
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)

# Text that mentions the command without asking for anything: a line has to be
# the command and nothing else, which is what keeps the receipts below -- both
# of which spell it -- from being read back as fresh requests.
_NOT_A_REQUEST = (
    f"do we just run `{grant.VALID}` here?",
    "/orchestrator add-agent-runs3",
    "/orchestrator continue",
    "/orchestrator add-review-rounds 3",
    # Both receipts the owner beside this one writes. The thread they land on
    # is the one the next tick reads for a request, and a deployment that
    # trusts every author trusts the orchestrator's own account too.
    _run_grant._GRANT_NOTICE.format(
        added=grant.ADDED,
        allowance=grant.GRANTED_ALLOWANCE,
        used=_limit_seeds.ALLOWANCE,
        marker=_run_grant._GRANTED_MARKER.format(
            issue=support.ISSUE_NUMBER, comment=grant.FIRST_ASK,
        ),
    ),
    _run_grant._REFUSAL_NOTICE.format(
        mentions=config.HITL_MENTIONS,
        maximum=_run_grant_request.MAX_RUNS_PER_COMMAND,
        marker=_run_grant._REFUSED_MARKER.format(
            issue=support.ISSUE_NUMBER, comment=grant.FIRST_ASK,
        ),
    ),
)


class CommandGrammarTest(unittest.TestCase):
    """What a comment has to say before anything reads it as a request."""

    def test_only_an_exact_bounded_count_buys_runs(self) -> None:
        for asked in grant.UNBUYABLE:
            with self.subTest(asked=asked):
                self.assertIsNone(_run_grant_request._added_runs(asked))
        bound = str(_run_grant_request.MAX_RUNS_PER_COMMAND)
        for asked in ("1", "007", bound):
            with self.subTest(asked=asked):
                self.assertEqual(
                    _run_grant_request._added_runs(asked), int(asked),
                )

    def test_a_request_is_a_line_and_nothing_else(self) -> None:
        for body in _NOT_A_REQUEST:
            with self.subTest(body=body):
                self.assertIsNone(
                    _run_grant_request._requested([grant.command(body)]),
                )

    def test_the_last_command_is_the_request(self) -> None:
        # A batch is read in thread order, so a human who wrote the command
        # twice meant the second one -- and a count corrected below a typo is
        # the request rather than the line it corrects.
        request = _run_grant_request._requested([
            grant.command(
                "/orchestrator add-agent-runs 9", comment_id=grant.FIRST_ASK,
            ),
            grant.command(
                f"scratch that\n{grant.VALID}\n/orchestrator add-agent-runs 7",
                comment_id=grant.SECOND_ASK,
            ),
        ])

        self.assertEqual(request.asked, "7")
        self.assertEqual(request.added, 7)
        self.assertEqual(request.comment_id, grant.SECOND_ASK)


if __name__ == "__main__":
    unittest.main()
