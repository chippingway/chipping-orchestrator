# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real git: where a fetched snapshot lands, and what reclaims it.

A remote ref is unique inside the repository that holds it, so three numbers
are enough there. The clone those repositories are fetched into is not: several
`REPOS` entries may share one `target_root` -- a single checkout with a public
and a private remote is the shape the per-issue branch namespace already exists
for -- and their ref stores are the same store. These cases drive two real
repositories through one clone and assert that neither ends up reading the
other's candidate.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import commands
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors, namespace, refs
from tests.git.snapshots.snapshot_test_support import real_remote

REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# Where that ref lands once the first repository fetches it. The segment is the
# sanitized slug the per-issue branch namespace is built from.
MIRROR = (
    "refs/orchestrator/late-split-local/owner__repo/issue-41/cycle-3/gen-1"
)

# A slug longer than the segment a local ref may carry. Configuration bounds
# `owner/name` at nothing, so this is a shape an operator may really write.
_OVERLONG = namespace.MAX_REPOSITORY_SEGMENT * 3

LONG_SLUG = "owner/{}".format("n" * _OVERLONG)

# What git exits with when a command fails outright instead of answering.
_FATAL = 128

# What every local command answers with once the ref store cannot be read at
# all: a git directory pruned out from under a running tick, a clone taken
# away while this process still held a path into it. The one failure real git
# will not stage on request, and the one a teardown must not read as success.
UNREADABLE_STORE = subprocess.CompletedProcess(
    args=(), returncode=_FATAL, stdout="",
    stderr="fatal: not a git repository",
)


def _preserved(remote) -> None:
    """Create this repository's snapshot and fetch it back into the clone."""
    refs.create_snapshot_ref(
        remote.spec, remote.clone, ref=REF, sha=remote.sha,
    )
    refs.prove_snapshot_ref(
        remote.spec, remote.clone, ref=REF, sha=remote.sha,
    )


def _mirrored(remote) -> str:
    """What this repository's copy of the snapshot resolves to here."""
    return _snapshot_mirrors._local_ref_sha(
        remote.clone, _snapshot_mirrors.local_snapshot_ref(remote.spec, REF),
    )


class LocalSnapshotNameTest(unittest.TestCase):
    """The local name says which repository the snapshot came from."""

    def test_it_qualifies_the_remote_name(self) -> None:
        with real_remote() as remote:
            self.assertEqual(_snapshot_mirrors.local_snapshot_ref(remote.spec, REF), MIRROR)

    def test_a_fetched_snapshot_resolves_under_it(self) -> None:
        with real_remote() as remote:
            _preserved(remote)

            self.assertEqual(
                _snapshot_mirrors._local_ref_sha(remote.clone, MIRROR), remote.sha,
            )


class BoundedRepositoryTest(unittest.TestCase):
    """A slug configuration does not bound still produces a usable ref."""

    def test_a_long_slug_stays_short_and_unique(self) -> None:
        # Configuration imposes no length on `owner/name`, and a segment
        # merely truncated to fit would put two long-named repositories back
        # on one local ref -- so the rewrite carries the slug's own digest.
        near = f"{LONG_SLUG}x"

        first = _snapshot_mirrors.local_snapshot_ref(_spec_for(LONG_SLUG), REF)
        second = _snapshot_mirrors.local_snapshot_ref(_spec_for(near), REF)

        self.assertNotEqual(first, second)
        for built in (first, second):
            with self.subTest(ref=built):
                self.assertTrue(namespace.is_local_snapshot_ref(built))

    def test_a_long_slug_fetches_and_reclaims(self) -> None:
        # The failure this closes: creation succeeded and the proof raised
        # while building a name too long to be one, retried forever.
        with real_remote(slug=LONG_SLUG) as remote:
            _preserved(remote)

            self.assertEqual(_mirrored(remote), remote.sha)
            self.assertEqual(
                refs.delete_snapshot_ref(
                    remote.spec, remote.clone, ref=REF, sha=remote.sha,
                ),
                refs.SnapshotOutcome.DELETED,
            )
            self.assertIsNone(_mirrored(remote))


def _spec_for(slug: str) -> config.RepoSpec:
    """A spec naming one repository, for the local name it produces."""
    return config.RepoSpec(
        slug=slug, target_root=Path("/tmp"), base_branch="main",
    )


class SharedTargetRootTest(unittest.TestCase):
    """Two repositories sharing one clone do not share one local snapshot.

    An unqualified local name would have the second fetch force over the
    first, so a verification would answer for a candidate this call never saw
    -- and the child told to copy paths out of it would take them from the
    other repository's work.
    """

    def test_each_repository_fetches_onto_its_own_ref(self) -> None:
        with real_remote() as first, real_remote(clone=first.clone) as second:
            _preserved(first)
            _preserved(second)

            self.assertNotEqual(
                _snapshot_mirrors.local_snapshot_ref(first.spec, REF),
                _snapshot_mirrors.local_snapshot_ref(second.spec, REF),
            )
            self.assertEqual(_mirrored(first), first.sha)
            self.assertEqual(_mirrored(second), second.sha)

    def test_each_proof_answers_for_its_own_candidate(self) -> None:
        # The failure an unqualified name produces is a false MISMATCH: the
        # ref the proof resolves carries the other repository's commit.
        with real_remote() as first, real_remote(clone=first.clone) as second:
            _preserved(second)

            refs.create_snapshot_ref(
                first.spec, first.clone, ref=REF, sha=first.sha,
            )

            self.assertEqual(
                refs.prove_snapshot_ref(
                    first.spec, first.clone, ref=REF, sha=first.sha,
                ),
                refs.SnapshotOutcome.PROVEN,
            )

    def test_one_reclamation_leaves_the_other_alone(self) -> None:
        with real_remote() as first, real_remote(clone=first.clone) as second:
            _preserved(first)
            _preserved(second)

            refs.delete_snapshot_ref(
                first.spec, first.clone, ref=REF, sha=first.sha,
            )

            self.assertIsNone(_mirrored(first))
            self.assertEqual(_mirrored(second), second.sha)


class LocalSnapshotReclamationTest(unittest.TestCase):
    """This host's copy goes with the remote ref it mirrors, and goes first.

    A child of a split reads a surviving mirror as proof that nobody has
    reclaimed its ancestor's ref, which is what keeps a per-tick guard off the
    network. Taken the other way round -- remote first, mirror after, on a
    delete that is best-effort against this host's disk -- a local teardown
    that failed left exactly the state that guard cannot tell from an
    untouched world, and the child ran on against a candidate nobody vouches
    for. So the mirror is dropped first, and one that will not go -- or that
    a failed read cannot tell from one already gone -- stops the reclamation
    instead.

    The reading on the other side of that guarantee is an identity: this
    checkout's ref store is one the agents' own worktrees share, so a copy
    proves only the commit it carries.
    """

    def test_it_drops_this_host_s_copy_too(self) -> None:
        # A mirror nothing deletes holds the snapshot's objects against `gc`
        # for as long as the clone lives.
        with real_remote() as remote:
            _preserved(remote)
            self.assertEqual(
                _snapshot_mirrors._local_ref_sha(remote.clone, MIRROR), remote.sha,
            )

            refs.delete_snapshot_ref(
                remote.spec, remote.clone, ref=REF, sha=remote.sha,
            )

            self.assertIsNone(_snapshot_mirrors._local_ref_sha(remote.clone, MIRROR))

    def test_an_absent_remote_drops_a_stranded_copy(self) -> None:
        # The crash between the push that deleted a ref and the write that
        # would have recorded it leaves this host's copy behind.
        with real_remote() as remote:
            _preserved(remote)
            remote.drop_remote_ref(REF)

            self.assertEqual(
                refs.delete_snapshot_ref(
                    remote.spec, remote.clone, ref=REF, sha=remote.sha,
                ),
                refs.SnapshotOutcome.ABSENT,
            )
            self.assertIsNone(_snapshot_mirrors._local_ref_sha(remote.clone, MIRROR))

    def test_a_mirror_that_survives_keeps_the_ref(self) -> None:
        # The state the guard cannot read: remote reclaimed, mirror standing,
        # no receipt yet. It is unreachable because the remote is never asked
        # while this host's copy is still here -- staged with the lock file a
        # crashed git leaves behind, which is what a ref store other worktrees
        # of the same clone share really refuses a delete with.
        with real_remote() as remote:
            _preserved(remote)
            remote.lock_ref(MIRROR)

            reclaimed = refs.delete_snapshot_ref(
                remote.spec, remote.clone, ref=REF, sha=remote.sha,
            )

            self.assertEqual(reclaimed, refs.SnapshotOutcome.REFUSED)
            self.assertEqual(remote.remote_ref_sha(REF), remote.sha)
            self.assertEqual(_mirrored(remote), remote.sha)

    def test_a_teardown_it_cannot_prove_keeps_the_ref(self) -> None:
        # The same state through the check rather than through the delete: a
        # ref that is not there and a store nothing can read answer a
        # resolution alike, so a check reading "could not ask" as "already
        # gone" is what takes the remote ref on the one tick where both halves
        # of the teardown failed -- and what stands after it reads, to every
        # child, as a reclamation that never happened.
        with real_remote() as remote:
            _preserved(remote)

            with patch.object(
                commands, "_git_hardened", return_value=UNREADABLE_STORE,
            ):
                reclaimed = refs.delete_snapshot_ref(
                    remote.spec, remote.clone, ref=REF, sha=remote.sha,
                )

            self.assertEqual(reclaimed, refs.SnapshotOutcome.REFUSED)
            self.assertEqual(remote.remote_ref_sha(REF), remote.sha)
            self.assertEqual(_mirrored(remote), remote.sha)

    def test_a_repointed_mirror_is_not_this_snapshot(self) -> None:
        # The half the guard rests on, and the reason it is not an existence
        # check: anything with this checkout can point a ref in it wherever it
        # likes. A copy at another commit is not the candidate a child was
        # promised, and reading it as one would start that child on work
        # nobody adjudicated AND skip the remote read that would have parked
        # it -- the mirror answers before the wire is touched at all.
        with real_remote() as remote:
            # Planted rather than fetched: what is under test is the reading,
            # and the fetch that ordinarily puts a copy here is proved above.
            remote.point_local_ref(MIRROR, remote.sha)
            self.assertTrue(_snapshot_mirrors.local_snapshot_present(
                remote.spec, remote.clone, ref=REF, sha=remote.sha,
            ))

            remote.point_local_ref(MIRROR, remote.other_sha)

            self.assertFalse(_snapshot_mirrors.local_snapshot_present(
                remote.spec, remote.clone, ref=REF, sha=remote.sha,
            ))
            self.assertEqual(_mirrored(remote), remote.other_sha)

    def test_a_repointed_ref_keeps_this_host_s_copy(self) -> None:
        # Which is why the read comes before the drop rather than after it: a
        # ref carrying another commit is somebody else's, and a mirror dropped
        # ahead of finding that out would throw away this host's only copy of
        # a candidate the call then refuses to reclaim.
        with real_remote() as remote:
            _preserved(remote)
            remote.drop_remote_ref(REF)
            remote.plant_ref(REF, remote.other_sha)

            reclaimed = refs.delete_snapshot_ref(
                remote.spec, remote.clone, ref=REF, sha=remote.sha,
            )

            self.assertEqual(reclaimed, refs.SnapshotOutcome.MISMATCH)
            self.assertEqual(_mirrored(remote), remote.sha)


if __name__ == "__main__":
    unittest.main()
