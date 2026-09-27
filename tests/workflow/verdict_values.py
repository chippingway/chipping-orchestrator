# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Review verdict values and messages shared by workflow tests.

An approval is acted on only beside verification the reviewer declares, so the
approving message runs the suite on the head a pull request stands on by
default; `approved_on` spells the same approval for another head.
"""

from tests.support.github.pull_request_models import DEFAULT_PR_HEAD_SHA

VERDICT_APPROVED = "approved"
VERDICT_CHANGES_REQUESTED = "changes_requested"
VERDICT_UNKNOWN = "unknown"

# The command the approving reviewer declares, and what it printed.
REVIEWER_SUITE = "uv run pytest tests"
REVIEWER_SUITE_OUTPUT = "12 passed"


def approved_on(head: str, *, exit_status: int = 0) -> str:
    """An approval declaring one run of the suite on `head`, exiting `exit_status`."""
    return (
        "LGTM\n\n"
        f"VERIFICATION: RUN {head}\n"
        f"COMMAND: {REVIEWER_SUITE}\n"
        f"EXIT: {exit_status}\n"
        f"{REVIEWER_SUITE_OUTPUT}\n"
        "VERIFICATION: END\n\n"
        "VERDICT: APPROVED"
    )


REVIEW_APPROVED_MESSAGE = approved_on(DEFAULT_PR_HEAD_SHA)
REVIEW_CHANGES_REQUESTED_MESSAGE = (
    "1. Fix typo\n\nVERDICT: CHANGES_REQUESTED"
)
