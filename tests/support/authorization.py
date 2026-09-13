# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The operator authorization a settled exemption carries, written once.

An exemption is half a bypass: the size gate publishes a commit without a
reading only where the terms an operator authorized name it too, and the
rewrite transfer moves one only where the same is true of the commit it came
from. So every fixture that puts an accepted candidate in front of either has
to seed both, and they reach the writer through here rather than each spelling
the group out -- a seed short of a member is not an authorization, and a
fixture that drifted into one would be testing the legacy road while claiming
to test the settled one.

A seed carrying the exemption alone is that LEGACY road: the shape a `single`
verdict left before a human's own decision was required at publication. Cases
about it ask for it by name.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import overrides as _overrides

# The reading a human was shown when they authorized, and the ceiling it was
# counted against. Strictly past it, because a record at or under its own
# threshold describes a candidate the gate publishes untouched and reads back
# as no authorization at all.
AUTHORIZED_ADDITIONS = 9123
AUTHORIZED_THRESHOLD = 4000

# The comment the authorization was written in, which is what makes it
# attributable to one gesture at one address.
AUTHORIZING_COMMENT_ID = 5150


def _authorize(
    state: PinnedState, candidate_sha: str, base_sha: str, fingerprint: str,
) -> None:
    """Record what an operator authorized this accepted candidate on.

    Written through the record's own owner rather than spelled as literals, so
    a seed is exactly what `late_consent` would have produced and a value this
    domain refuses never reaches a test as though it had been recorded.

    The pair and the digest are the caller's because they are the fixture's:
    the same three the exemption's identity was seeded with, so the two groups
    describe one change. The reading and the comment are this module's, since
    nothing either reader asks turns on how large the authorized change was.
    """
    _overrides.record_publication_override(
        state,
        _overrides.LateOversizedPublication(
            candidate_sha=candidate_sha,
            base_sha=base_sha,
            fingerprint=fingerprint,
            additions=AUTHORIZED_ADDITIONS,
            threshold=AUTHORIZED_THRESHOLD,
            comment_id=AUTHORIZING_COMMENT_ID,
        ),
    )
