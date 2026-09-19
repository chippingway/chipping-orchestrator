# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication receipt setup and assertions over one already-pushed issue branch."""
from __future__ import annotations

from types import MappingProxyType

from tests.support.fakes import FakePR, FakePRRef, FakePRRepo
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _issue_branch,
    _named_description,
)
from tests.workflow.stages.implementing import late_gate_test_support as support

_KEY_PUBLISHED_SHA = "implementing_published_sha"
_KEY_PR_NUMBER = "pr_number"
# The pull request the receipt itself names, written with it by the push that
# landed. `pr_number` is the relabel's write, which is the one this window is
# missing, so this is the only identity a recovery has that is not a search.
_KEY_PUBLISHED_PR = "implementing_published_pr"
# The head that push replaced, the third member. An initial publication froze
# none and records none, so it is absent rather than damaged there.
_KEY_PUBLISHED_LEASE = "implementing_published_lease"

_DEV_BACKEND = "codex"

# The pull request that note was written about, and the branch it is on.
_PR_NUMBER = 812
_BRANCH = _issue_branch(support.GATE_ISSUE_NUMBER)

# Where the remote is standing instead: a commit of the right shape that no
# record on these seeds names, which is what "the head has moved" looks like
# from the issue's side.
_MOVED_HEAD = "e" * SHA_LENGTH

# The branch a pull request nobody opened for this issue is on: the shape a
# record whose `branch` and `pr_number` disagree leaves, and the one that
# would have the seam push where nothing has published.
_ANOTHER_BRANCH = f"{_BRANCH}-elsewhere"

# What a pull request reads as once somebody has ended it.
_CLOSED = "closed"

# A receipt outside this domain's object-id vocabulary: what a hand edit or a
# half-written crash leaves, and what every late commit field reads back as an
# absence rather than as the claim it is.
_MALFORMED_RECEIPT = "not-a-sha"

# What a branch this stage has pushed before carries: the note naming the
# commit it sent, the pull request that push opened, and the branch both are
# about. All three, because the remote reading behind them is what tells work
# this issue delivered from a tip somebody else moved the branch to.
# The receipt group's three members, in the order a refusal names them.
# `_record_publication` puts all three keys down on every receipt, `null`
# included, so presence is a term of its own and a fixture writes the group
# as a whole rather than a member at a time.
_RECEIPT_MEMBERS = (
    _KEY_PUBLISHED_SHA, _KEY_PUBLISHED_LEASE, _KEY_PUBLISHED_PR,
)

_PUBLISHED_BY_THIS_STAGE = MappingProxyType({
    _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
    # `null`, which is what an initial publication records for the head it
    # froze none of -- and the key goes down all the same, since the three
    # members are one write.
    _KEY_PUBLISHED_LEASE: None,
    _KEY_PUBLISHED_PR: _PR_NUMBER,
    _KEY_PR_NUMBER: _PR_NUMBER,
    "branch": _BRANCH,
    # The session that wrote the branch, which the description it opened names.
    "dev_agent": _DEV_BACKEND,
    "dev_session_id": support.DEV_SESSION,
})


class _ReceiptCase(support._GateCase):
    """An issue whose branch this stage has pushed before."""

    def _stand_the_pull_request_on(
        self, head: str, branch: str = _BRANCH, repo: str = "",
    ) -> None:
        """Put this issue's open pull request on `head`, or take it away.

        `branch` is what the pull request's own head names, which a case about
        a record disagreeing with itself moves off the branch the seam would
        push -- the one shape that would have the answer license a push onto a
        branch nothing has published.

        `repo` moves the head into somebody else's copy of this repository,
        which is the shape that agrees on every other term: a fork carries the
        same ref names over the same commits.
        """
        if not head:
            return
        opened = FakePR(
            number=_PR_NUMBER,
            head_branch=branch,
            head=FakePRRef(
                sha=head, ref=branch, repo=FakePRRepo(full_name=repo),
            ),
            body=_named_description(
                support.GATE_ISSUE_NUMBER, support.DEV_SESSION, _DEV_BACKEND,
            ),
        )
        self.github.add_pr(opened)
        self.github.existing_open_pr[branch] = opened

    def _oversized(self):
        """One gate run over a candidate no count would ever let through."""
        return self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

    def _seeding(self, group: dict) -> None:
        """A fresh case whose receipt group is exactly `group`.

        The members are written from the group rather than merged over a
        whole one, because an OMITTED key is one of the shapes: a group the
        write here always fills and the comment does not is a hand edit, and
        a fixture that could not express it would leave that rule untested.
        """
        self.setUp()
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)
        self._seed(**{
            member: held
            for member, held in _PUBLISHED_BY_THIS_STAGE.items()
            if member not in _RECEIPT_MEMBERS
        }, **group)

    def _receipt_group(self) -> dict:
        """Whichever members of the receipt group the comment carries now."""
        pinned = self._pinned()
        return {
            member: pinned[member] for member in _RECEIPT_MEMBERS
            if member in pinned
        }

    def _seeded(self, described: str) -> None:
        """One record whose receipt names a publication nothing can show."""
        standing, branch, recorded = _UNPROVABLE[described]
        self.setUp()
        self._stand_the_pull_request_on(standing, branch=branch)
        if described == "one somebody ended":
            self.github.get_pr(_PR_NUMBER).state = _CLOSED
        self._seed(**{
            **dict.fromkeys(_RECEIPT_MEMBERS),
            _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
            **recorded,
        })


# Every way the publication a receipt names can fail to be shown, each named
# by what the pinned comment and the remote disagree about.
_UNPROVABLE = MappingProxyType({
    "one this host cannot read": ("", _BRANCH, _PUBLISHED_BY_THIS_STAGE),
    "a lease no call here froze": (
        MEASURED_CANDIDATE_SHA, _BRANCH,
        {**_PUBLISHED_BY_THIS_STAGE, _KEY_PUBLISHED_LEASE: _MOVED_HEAD},
    ),
    "one the branch moved off": (
        _MOVED_HEAD, _BRANCH, _PUBLISHED_BY_THIS_STAGE,
    ),
    "one open somewhere else": (
        MEASURED_CANDIDATE_SHA, _ANOTHER_BRANCH, _PUBLISHED_BY_THIS_STAGE,
    ),
    "one somebody ended": (
        MEASURED_CANDIDATE_SHA, _BRANCH, _PUBLISHED_BY_THIS_STAGE,
    ),
    "a receipt nothing can read": (
        MEASURED_CANDIDATE_SHA, _BRANCH,
        {**_PUBLISHED_BY_THIS_STAGE, _KEY_PUBLISHED_SHA: _MALFORMED_RECEIPT},
    ),
})
