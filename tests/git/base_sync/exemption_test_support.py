# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The adjudicated issue one refresh-time rebase is decided over, as doubles.

The composed refresh takes the readings a transfer turns on and no other
base-sync case seeds: which commit each revision proves to, what the REMOTE
says the base branch is at, and what each of the two contributions
fingerprints to. They are answered here as one world -- the ordinary one, in
which the replay contributes exactly what the adjudication accepted -- so a
case about a refusal moves the single answer it is about and says nothing
else.

The revisions are keyed rather than sequenced because the permit asks about
two different things: the checkout's own head and the pre-rebase anchor its
force-push is leased against. A positional double would silently swap them the
moment that order changed.

The base is answered by the freeze rather than by peeling a local ref, because
that is the reading the production evidence takes: the ref a rebase names
lives in a store the agent writes to, so what a transfer is granted over has
to be the base the remote itself answers for.
"""
from __future__ import annotations

from orchestrator.git.measurement import (
    commits as _measurement_commits,
    fingerprint as _measurement_fingerprint,
)
from orchestrator.git.measurement.models import (
    ContributionFingerprint,
    FrozenCommit,
)
from orchestrator.workflow.late_split import exemption as _exemption
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    BEFORE_SHA,
    ISSUE,
    _patched,
)
from tests.support.authorization import _authorize

SHA_LENGTH = 40
DIGEST_LENGTH = 64

# The base the adjudication measured the accepted commit over, and the base
# the rebase replayed it onto. Two commits, because that is what a base
# advance is -- and what makes the digest, rather than the pair, the thing the
# equality is read from.
ACCEPTED_BASE_SHA = "acce97ed" * 5
REPLAYED_BASE_SHA = "5eba5ed0" * 5

# A commit a human ruled on that is NOT the head the rebase found. The two are
# ordinarily one, and the record never says so: what a transfer is granted on
# is the equality of two contributions, which two distinct commits can carry.
ACCEPTED_SHA = "a55e55ed" * 5

# What the contribution a human ruled on fingerprints to, and what a base
# advance that changed it fingerprints to instead.
ACCEPTED_DIGEST = "d" * DIGEST_LENGTH
CHANGED_DIGEST = "c" * DIGEST_LENGTH

# The revision a checkout's own head is named by. Every other revision the
# permit asks about is a commit some record names by id.
HEAD_REVISION = "HEAD"


class Readings:
    """What each revision proves to, what the remote answers, and the digests.

    `base` is the freeze, and it is a whole `FrozenCommit` rather than a SHA
    because the ways it fails are the point: a remote that would not name the
    branch, and an object this host does not hold even after a fetch, each
    leave the evidence with no base to read a contribution over.
    """

    def __init__(self) -> None:
        self.proved = {
            HEAD_REVISION: AFTER_SHA,
            BEFORE_SHA: BEFORE_SHA,
        }
        self.base = FrozenCommit(sha=REPLAYED_BASE_SHA)
        self.digests = {
            (ACCEPTED_BASE_SHA, BEFORE_SHA): ACCEPTED_DIGEST,
            (REPLAYED_BASE_SHA, AFTER_SHA): ACCEPTED_DIGEST,
        }

    def prove(self, _worktree, revision: str) -> FrozenCommit:
        """The commit one revision names."""
        return FrozenCommit(sha=self.proved.get(revision, revision))

    def freeze(self, _spec, _worktree) -> FrozenCommit:
        """The commit the remote says this spec's base branch is at."""
        return self.base

    def fingerprint(
        self, _worktree, base_sha: str, candidate_sha: str,
    ) -> ContributionFingerprint:
        """What one pair contributes, as the digest naming it."""
        return ContributionFingerprint(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            digest=self.digests.get(
                (base_sha, candidate_sha), CHANGED_DIGEST,
            ),
        )


def readings(test_case) -> Readings:
    """Install the world an equivalent replay is granted in, and hand it back."""
    answers = Readings()
    _patched(
        test_case, _measurement_commits, "_prove_candidate_commit",
        answers.prove,
    )
    _patched(
        test_case, _measurement_commits, "_freeze_base_commit", answers.freeze,
    )
    _patched(
        test_case, _measurement_fingerprint, "_fingerprint_contribution",
        answers.fingerprint,
    )
    return answers


def adjudicated(
    test_case, *, identity: bool = True, accepted: str = BEFORE_SHA,
) -> None:
    """Record the verdict a settled `single` left, on the head it accepted.

    `identity=False` is the legacy shape: a comment written before the
    semantic record existed, so the exact commit is exempt and nothing on it
    says what that commit contributes.

    The terms an operator authorized the publication on go down with it
    either way, since an exemption is half a bypass and a rewrite of a commit
    only it names earns no transfer.

    `accepted` is the commit a human ruled on, and it defaults to the head the
    rebase finds because that is the ordinary case rather than the rule. A
    case naming another commit is seeding the world where the two are distinct
    carriers of one contribution, and it seeds the digest for that pair too.
    """
    issue = test_case.gh._issues[ISSUE]
    state = test_case.gh.read_pinned_state(issue)
    _exemption.record_exemption(state, accepted)
    if identity:
        _exemption.record_semantic_identity(
            state,
            base_sha=ACCEPTED_BASE_SHA,
            candidate_sha=accepted,
            fingerprint=ACCEPTED_DIGEST,
        )
    _authorize(state, accepted, ACCEPTED_BASE_SHA, ACCEPTED_DIGEST)
    test_case.gh.write_pinned_state(issue, state)
