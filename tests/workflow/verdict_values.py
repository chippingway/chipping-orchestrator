# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Review verdict values and messages shared by workflow tests.

An approval is acted on only beside verification the reviewer declares, so the
approving message runs the suite on the head a pull request stands on by
default; `approved_on` spells the same approval for another head, or under
another configuration.
"""

from orchestrator import config
from tests.support.github.pull_request_models import DEFAULT_PR_HEAD_SHA

VERDICT_APPROVED = "approved"
VERDICT_CHANGES_REQUESTED = "changes_requested"
VERDICT_UNKNOWN = "unknown"

# The command the approving reviewer declares, and what it printed.
REVIEWER_SUITE = "uv run pytest tests"
REVIEWER_SUITE_OUTPUT = "12 passed"


def approved_on(head: str, *, exit_status: int = 0) -> str:
    """An approval declaring its run on `head` of what the repository requires, each exiting `exit_status`.

    What the repository requires is the `VERIFY_COMMANDS` configured as the
    message is built -- an approval has to declare every one of them -- or
    the suite where none are.
    """
    steps = "".join(
        f"COMMAND: {command}\nEXIT: {exit_status}\n{REVIEWER_SUITE_OUTPUT}\n"
        for command in tuple(config.VERIFY_COMMANDS) or (REVIEWER_SUITE,)
    )
    return (
        "LGTM\n\n"
        f"VERIFICATION: RUN {head}\n"
        f"{steps}"
        "VERIFICATION: END\n\n"
        "VERDICT: APPROVED"
    )


REVIEW_APPROVED_MESSAGE = approved_on(DEFAULT_PR_HEAD_SHA)
REVIEW_CHANGES_REQUESTED_MESSAGE = (
    "1. Fix typo\n\nVERDICT: CHANGES_REQUESTED"
)
