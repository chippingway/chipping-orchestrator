# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a session-limit park leaves behind, read back the same way on every stage that takes it.

The park is the shared question park's quota branch, and each stage reaches it
from its own timeout or stalled-run branch, so the stage regressions read one
outcome: the retryable `agent_silent` pinned, `agent_session_limit` reported,
and a notice that names the exhausted account quota.
"""

from orchestrator.git.verification.status import _WorktreeStatus

# A tree read clean ahead of a resume and nobody's to read once the run is
# back: what a quota stop's unpublishable-tree regression seeds where the stage
# refuses an unreadable tree before it runs anyone.
_READ_CLEAN = _WorktreeStatus(readable=True, paths=())
READ_THEN_UNREADABLE = (_READ_CLEAN, _WorktreeStatus(readable=False, paths=()))

_PARK_EVENT = "park_awaiting_human"
_SESSION_LIMIT = "agent_session_limit"
_QUOTA_NOTICE = "account quota is exhausted"


def assert_session_limit_park(case, github, issue_number: int) -> None:
    """Assert `issue_number` parked on its quota as the session limit, and reported nothing else last."""
    pinned = github.pinned_data(issue_number)
    case.assertTrue(pinned.get("awaiting_human"))
    case.assertEqual(pinned.get("park_reason"), "agent_silent")
    notices = [body for _, body in github.posted_comments if _QUOTA_NOTICE in body]
    case.assertTrue(notices)
    parks = [record["reason"] for record in github.recorded_events if record["event"] == _PARK_EVENT]
    case.assertEqual(parks[-1:], [_SESSION_LIMIT])
