# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue one adjudicated squash runs on, and the writes it makes.

A `single` verdict leaves an exemption naming the commit a human ruled on and
the canonical digest of what that commit contributes. Every case about a
transfer starts from exactly that comment, so the seeding lives here rather
than in whichever module happened to need it first.

The two write doubles are the other half. A squash's durable writes are the
crash boundaries it can be interrupted at, so a case says WHICH write it is
about -- the terms of the collapse, the permission that licenses the push, or
the receipt that settles it -- rather than counting to one.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.workflow.late_split import exemption as _exemption
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_gate_support import (
    PublicationSeed,
    _squash_gate,
)
from tests.support.authorization import _authorize

MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The fixture's topic branch adds one line per commit over three commits, so
# a ceiling below that is what an adjudicated candidate was oversized against.
ADDED_LINES = 3
PAST_THE_CEILING = ADDED_LINES - 1

LABEL_DECOMPOSING = "workflow:decomposing"

# A whole digest that is not the one the accepted contribution really takes,
# which is what a hand-edited or stale semantic record reads back as.
DIGEST_LENGTH = 64
UNRECORDED_DIGEST = "0" * DIGEST_LENGTH

# The client call every durable record of a tick goes through, which is what a
# case standing in for an outage replaces.
PINNED_WRITE = "write_pinned_state"

# The durable writes one squash-on-approval makes, in the order it makes them:
# the terms of the collapse it is about to run, the permission that licenses
# the push it earns, and the receipt that settles what landed.
COLLAPSE_WRITE = 1
GRANT_WRITE = 2
RECEIPT_WRITE = 3


class _RecordsEachWrite:
    """What the pinned comment said at each durable write of one squash.

    A squash makes several, and what a crash could take is everything the
    writes behind one would have added -- so the question a case has to be
    able to ask is what a given write alone left behind, not what the comment
    says once the tick has finished.
    """

    def __init__(self, gate) -> None:
        self.durable: list[dict] = []
        self._gate = gate
        self._writes = gate.gh.write_pinned_state

    def __call__(self, issue, state):
        written = self._writes(issue, state)
        self.durable.append(dict(self._gate.gh.pinned_data(issue.number)))
        return written

    def nth(self, ordinal: int) -> dict:
        """The comment as the run's nth durable write left it."""
        return self.durable[ordinal - 1]

    def held(self):
        """Record every write the client makes, for the duration of one run."""
        return patch.object(self._gate.gh, PINNED_WRITE, self)


class _RefusesOneWrite:
    """A comment GitHub refuses at one point in the tick and takes otherwise.

    The narrow outage, and the one that says WHERE a lost write is handled.
    Refusing the GRANT loses only the transfer's permission, so a tick that
    carries on has the ordinary size gate to fall back to and a tick that lets
    the exception out has nothing. Refusing the RECEIPT loses the account of a
    push that already landed, which is the one window where the branch must be
    left exactly where the rewrite put it.
    """

    def __init__(self, gate, ordinal: int = 1) -> None:
        self.writes = 0
        self._ordinal = ordinal
        self._writes = gate.gh.write_pinned_state

    def __call__(self, issue, state):
        self.writes += 1
        if self.writes == self._ordinal:
            raise RuntimeError("pinned comment rejected")
        return self._writes(issue, state)

    def held(self, gate):
        """Refuse the write at this point of one run, and take the rest."""
        return patch.object(gate.gh, PINNED_WRITE, self)


class _AdjudicatedSquashMixin:
    """One issue whose exemption names the commit the squash is about to eat."""

    def _adjudicated(
        self, *, digest: str | None = None, base: str = "", accepted: str = "",
    ):
        """The gate for an issue whose exemption names the pre-squash head.

        The pinned comment is exactly what a settled `single` verdict leaves:
        the accepted commit, the canonical digest of what it contributes over
        the base the adjudication was measured from, and the terms an operator
        authorized that publication on -- an exemption is half a bypass, and a
        squash of a commit only it names earns no transfer.

        `base` replaces that end, which is the one field of the record a hand
        edit can move without the reader refusing it: another commit in this
        repository types exactly as the frozen base does.

        `accepted` names an EARLIER commit than the tip, which is what an
        issue that went on committing after its verdict looks like: the
        publication is seeded on the tip the squash would collapse, and the
        exemption on the one commit a human actually ruled on.
        """
        gate = _squash_gate(self, PublicationSeed())
        accepted = accepted or self._head_sha()
        recorded_base = base or self._base_sha()
        recorded_digest = digest or self._contribution(accepted)
        _exemption.record_exemption(gate.state, accepted)
        _exemption.record_semantic_identity(
            gate.state,
            base_sha=recorded_base,
            candidate_sha=accepted,
            fingerprint=recorded_digest,
        )
        _authorize(gate.state, accepted, recorded_base, recorded_digest)
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return gate

    def _one_commit_back(self) -> str:
        """A real commit in this repository that is not the frozen base."""
        return squash_support.run_git(
            "rev-parse", "HEAD~1", cwd=self.work,
        ).strip()

    def _contribution(self, candidate: str) -> str:
        """What that candidate really contributes over the frozen base."""
        fingerprinted = _fingerprint._fingerprint_contribution(
            self.work, self._base_sha(), candidate,
        )
        self.assertTrue(fingerprinted.is_fingerprinted)
        return fingerprinted.digest

    def _squashes(self, gate, **run_options):
        """Squash under a ceiling the accepted candidate is already past."""
        return self._squash(
            publication=PublicationSeed(gate=gate),
            **{MAX_ADDED_LINES: PAST_THE_CEILING},
            **run_options,
        )

    def _pinned(self, gate) -> dict:
        """The pinned comment as it durably stands."""
        return gate.gh.pinned_data(gate.issue.number)

    def _assert_exempts(self, gate, commit: str) -> None:
        """The commit the comment durably exempts, whatever else moved."""
        self.assertEqual(
            self._pinned(gate)[_exemption.LATE_EXEMPT_SHA], commit,
        )
