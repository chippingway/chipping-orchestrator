# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fork point one revision left the base at, read out of a real repository.

The base a contribution is measured over, and the one reading a rebase moves:
the commit it replayed forked at the tip the base used to be, and the commit
it produced forks at the tip it is now. A double that answered either would be
answering what a case seeded rather than what the objects say, and the whole
use of this probe is that the two really differ.

The refusals are read here too, because "" has to mean a reading that did not
HAPPEN rather than a base of no length: a revision this store does not hold,
and a base ref nothing ever fetched, are each evidence a caller cannot produce
and must not fingerprint over.
"""
from __future__ import annotations

import unittest

from orchestrator.config import models as _config_models
from orchestrator.git.publication import probes
from tests.support.replay_repository import ReplayRepositoryMixin, base_tip

# A whole object id no repository built here holds, which is what work made on
# another host reads back as.
SHA_LENGTH = 40
ABSENT_SHA = "d" * SHA_LENGTH

# A base branch this remote has never carried, so the ref the probe names
# resolves to nothing.
UNFETCHED_BASE = "release-9"


class ForkPointRealGitTest(ReplayRepositoryMixin, unittest.TestCase):
    """What git answers for each end of one replay, and for readings it cannot take."""

    def setUp(self) -> None:
        super().setUp()
        self.replay = self.build_replay()

    def test_a_replay_moves_the_fork_point(self) -> None:
        # The two ends really are read over different commits, which is what
        # makes a rewrite record carry two bases rather than one.
        replayed = probes._fork_point(
            self.replay.spec, self.replay.worktree, self.replay.replayed,
        )
        accepted = probes._fork_point(
            self.replay.spec, self.replay.worktree, self.replay.accepted,
        )

        self.assertEqual(replayed, self.replay.replayed_base)
        self.assertEqual(accepted, self.replay.accepted_base)
        self.assertNotEqual(accepted, replayed)

    def test_the_replayed_end_forks_at_the_base_tip(self) -> None:
        # A branch that has just been replayed carries its base, so the fork
        # point IS the tip -- which is what makes the rebased contribution the
        # diff a reviewer would be handed against the branch it merges into.
        tip = base_tip(self.replay.worktree)

        self.assertEqual(self.replay.replayed_base, tip)

    def test_a_revision_this_host_lacks_reads_nothing(self) -> None:
        forked = probes._fork_point(
            self.replay.spec, self.replay.worktree, ABSENT_SHA,
        )

        self.assertEqual(forked, "")

    def test_a_base_ref_nothing_fetched_reads_nothing(self) -> None:
        # Not a base of no length: a reading that did not happen at all, which
        # every caller answers with no evidence rather than with a range.
        unfetched = _config_models.RepoSpec(
            slug=self.replay.spec.slug,
            target_root=self.replay.worktree,
            base_branch=UNFETCHED_BASE,
        )

        forked = probes._fork_point(
            unfetched, self.replay.worktree, self.replay.replayed,
        )

        self.assertEqual(forked, "")


if __name__ == "__main__":
    unittest.main()
