# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When a receipt is evidence of THIS issue's own push having landed.

A pull request standing anywhere but where a call was entered is somebody
else's branch move, and every owner that freezes or proves a publication
refuses one. There is a carve-out, and it is the window a tick that pushed and
died before its own bookkeeping leaves: the remote is standing exactly where
this issue put it, so refusing that would stop the recovery that exists to
finish it.

Three owners rest on the carve-out -- the size gate's entry freeze, the
settlement's proof, and the squash resume -- and what they share is the rule
rather than the road. So the rule is pinned here, once, at the reader they all
call: a receipt excuses a moved head only when every member of the receipt
group says the push was this issue's, onto the publication the caller is
proving against.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, SHA_LENGTH

_KEY_PUBLISHED_SHA = "implementing_published_sha"
_KEY_PUBLISHED_LEASE = "implementing_published_lease"
_KEY_PUBLISHED_PR = "implementing_published_pr"

# The publication the caller is proving against, and the head the recorded
# push replaced -- which is what dates a receipt to one attempt.
_PR_NUMBER = 812
_MOVED_HEAD = "e" * SHA_LENGTH

# A value outside this domain's identity vocabulary: what a hand edit or a
# half-written crash leaves where a number belongs.
_MALFORMED_RECEIPT = "not-a-number"


class OwnPushCarveOutTest(unittest.TestCase):
    """What the receipt group has to say before it excuses a moved head.

    Three owners rest on this one reader and each refuses somebody else's
    branch move without it: the gate's entry freeze, the settlement's proof,
    and the squash resume. Asked here rather than through all three, because
    what they share is the rule -- a receipt is evidence of THIS issue's own
    push having landed only when every member of the group says so.

    The commit and the head it replaced are not enough between them. A branch
    pushed from that head before, onto a publication since closed and replaced
    by another on the same ref, satisfies both while the push it records went
    somewhere else -- so the pull request the receipt names is the third term,
    and the caller supplies the one it is proving against.
    """

    def test_the_whole_group_vouches(self) -> None:
        self.assertEqual(
            self._vouched(_PR_NUMBER, pull_request=_PR_NUMBER),
            MEASURED_CANDIDATE_SHA,
        )

    def test_anything_short_of_it_does_not(self) -> None:
        # Every way the identity can fail to name the publication being proved
        # against: another pull request, a field an older build never wrote,
        # one a hand edit left unreadable, and a caller that can name none.
        for described, recorded, expected in (
            ("another pull request", _PR_NUMBER + 1, _PR_NUMBER),
            ("no identity at all", None, _PR_NUMBER),
            ("one nothing can read", _MALFORMED_RECEIPT, _PR_NUMBER),
            ("nothing to prove against", _PR_NUMBER, 0),
        ):
            with self.subTest(receipt=described):
                self.assertEqual(
                    self._vouched(recorded, pull_request=expected), "",
                )

    def _vouched(self, recorded, *, pull_request: int) -> str:
        """What the reader makes of a receipt group naming `recorded`."""
        return _late_publication_state._publication_from(
            PinnedState(data={
                _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
                _KEY_PUBLISHED_LEASE: _MOVED_HEAD,
                _KEY_PUBLISHED_PR: recorded,
            }),
            _MOVED_HEAD,
            pull_request,
        )


if __name__ == "__main__":
    unittest.main()
