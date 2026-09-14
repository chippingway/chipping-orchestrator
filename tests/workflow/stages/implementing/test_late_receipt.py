# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the publication receipt vouches for, and what it may not.

`implementing_published_sha` is the note this stage leaves naming the commit it
pushed, and the window it exists for is the one between that push and a relabel
that never landed: the branch is on the remote, a pull request carries it, and
the record still says implementing. A tick reading that as fresh work would
measure a published commit and, finding it oversized, route it into an
adjudication with nothing left to hold back.

That window is real and nothing here closes it. What is proved is that the tick
is still IN it: the note says what this stage last pushed and nothing about
where it went or whether it is still there, and it is never cleared -- so a
branch published rounds ago carries one for the rest of the issue's life.
Answered on the note alone, the candidate skips the reading, is pushed
unmeasured and unleased, opens a SECOND pull request over work the first
already carries, and the issue is handed on as though all of it had been
published all along.

So the same proof stands behind every road that rests on it: the pull request
the record names, open, on the branch this seam would push, standing on this
exact commit. And because a reading is a moment, what the answer carries is the
NUMBER -- the push behind it is leased against that commit, and the bookkeeping
is bound to that pull request.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.implementing import (
    late_overflow as _overflow,
    publication as _publication,
)
from tests.support.fakes import FakePR, FakePRRef, FakePRRepo
from tests.workflow.fixtures import (
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _issue_branch,
)
from tests.workflow.interleaving import _RacesPastTheStep, _RacesTheStep
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
# What a proven-delivery attempt makes durable BEFORE it pushes, and what a
# tick dying in that window leaves behind: the commit named as owed a push,
# with no lease beside it -- the head it would have been pinned to was the
# pull request the proof named, and that proof is what the retry can no
# longer take.
_KEY_APPROVED_SHA = "late_approved_sha"
# The other record that names a commit and says nothing about where it went:
# an adjudication's verdict that the change ships as one change.
_KEY_EXEMPT_SHA = "late_exempt_sha"

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

_VALIDATING = (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING)

# The two keywords a push names its commit and pins its ref by, and the one
# guarded reading the bookkeeping behind the proof resolves its pull request
# through -- the same request that answers whether it is open, so a check and
# a fetch cannot describe two different moments.
_REVISION = "revision"
_LEASE = "force_with_lease"
_STANDING_EXACTLY_ON = "standing_exactly_on"

# The last step this seam takes before its barrier, which is the window a poll
# on another worker can end the publication in.
_PUBLICATION_INTENT = "_publication_intent"

# What a pull request reads as once somebody has ended it.
_CLOSED = "closed"

# A receipt outside this domain's object-id vocabulary: what a hand edit or a
# half-written crash leaves, and what every late commit field reads back as an
# absence rather than as the claim it is.
_MALFORMED_RECEIPT = "not-a-sha"

# Somebody else's copy of this repository: where a fork's head lives, which is
# the only fact that tells its pull request from one of this issue's own.
_FORK_REPO = "somebody-else/orchestrator"

# The setting an install turns the measurement off with, which is the one road
# out of the gate that never reaches the candidate question.
_DECOMPOSE_SWITCH = "orchestrator.config.settings.DECOMPOSE"

# This very repository, spelled the way an operator types a setting rather
# than the way GitHub answers: the same repository, and the one shape an
# exact comparison reads as a stranger's.
_SHOUTED_REPO = "ChippingWay/Orchestrator"

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


class DeliveredReceiptTest(_ReceiptCase, unittest.TestCase):
    """The window the note exists for, proved rather than assumed."""

    def setUp(self) -> None:
        super().setUp()
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)
        self._seed(**_PUBLISHED_BY_THIS_STAGE)

    def test_a_proved_receipt_finishes_up(self) -> None:
        # Read from the far end: this stage pushed the commit, the pull
        # request it opened is standing on it still, and the relabel never
        # landed. Nothing is measured, nothing new is opened, and the issue
        # is handed on -- which is what a hold here would strand.
        mocks = self._oversized()

        self._assert_unmeasured(mocks)
        self.assertIn(_VALIDATING, self.github.label_history)
        self.assertEqual(self.github.opened_prs, [])
        self.assertEqual(self._pinned()[_KEY_PR_NUMBER], _PR_NUMBER)

    def test_the_push_is_leased_to_that_commit(self) -> None:
        # Left to the transport's own reading, a tip somebody moved in the
        # window is adopted AS the lease and the candidate is force-pushed
        # over it. Pinned to the commit the proof was about, the same push
        # sends nothing where the branch has not moved and is refused where
        # it has.
        pushed = self._oversized()[support.PUSH_BRANCH].call_args

        self.assertEqual(pushed.kwargs[_LEASE], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[_REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.args[2], _BRANCH)


class DeliveredWindowRaceTest(_ReceiptCase, unittest.TestCase):
    """What another poll can do between the proof and the bookkeeping.

    The gate reads the publication once and everything past that line spends
    a barrier, a push and a write. A pull request somebody settles or moves in
    there is open and standing where the proof left it to the reading that
    admitted the candidate, and something else entirely by the time the record
    is written -- so the terms are re-read where they are acted on rather than
    carried forward as still true.
    """

    def setUp(self) -> None:
        super().setUp()
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)
        self._seed(**_PUBLISHED_BY_THIS_STAGE)

    def test_one_closing_before_the_push_sends_none(self) -> None:
        # The barrier the push itself owes, raced into the window it exists
        # for: the gate proved the pull request open, and a poll on another
        # worker closes it before the transport runs. The lease makes no
        # difference there -- a branch nobody moved accepts the push whatever
        # became of the pull request over it -- so the reading is retaken
        # immediately before the push rather than only at the bookkeeping
        # behind it.
        with patch.object(
            _publication,
            _PUBLICATION_INTENT,
            _RacesPastTheStep(
                _publication._publication_intent, self._closes_it,
            ),
        ):
            mocks = self._oversized()

        self._assert_held(mocks)
        self.assertEqual(self.github.opened_prs, [])
        self.assertNotIn(_VALIDATING, self.github.label_history)

    def test_a_pull_request_closing_opens_none(self) -> None:
        # The far end of the same window. Looked up by branch a moment later,
        # a pull request somebody closed answers None and the seam opens a
        # SECOND one over work the first already carries. Pinned to the number
        # the proof named, the same window holds the tick instead and leaves
        # the record exactly as it stands.
        with patch.object(
            _overflow._PublicationReading,
            _STANDING_EXACTLY_ON,
            _RacesTheStep(
                _overflow._PublicationReading.standing_exactly_on,
                self._closes_it,
            ),
        ):
            mocks = self._oversized()

        self._assert_unmeasured(mocks)
        self.assertEqual(self.github.opened_prs, [])
        self.assertNotIn(_VALIDATING, self.github.label_history)

    def test_a_pull_request_moving_records_none(self) -> None:
        # The same window and the ending the open state cannot show: somebody
        # pushes to the branch between the leased no-op and the bookkeeping,
        # so the pull request is open still and standing somewhere else.
        # Recorded on the open state alone, the receipt would name a commit
        # the branch no longer carries and a reviewer would be handed a head
        # this issue never published.
        with patch.object(
            _overflow._PublicationReading,
            _STANDING_EXACTLY_ON,
            _RacesTheStep(
                _overflow._PublicationReading.standing_exactly_on,
                self._moves_it,
            ),
        ):
            mocks = self._oversized()

        self._assert_unmeasured(mocks)
        self.assertEqual(self.github.opened_prs, [])
        self.assertNotIn(_VALIDATING, self.github.label_history)
        self.assertEqual(
            self._pinned()[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA,
        )

    def _closes_it(self) -> None:
        """Close the pull request the proof named, as another poll would."""
        self.github.get_pr(_PR_NUMBER).state = _CLOSED

    def _moves_it(self) -> None:
        """Push to the branch under the tick, as another author would."""
        self.github.get_pr(_PR_NUMBER).head.sha = _MOVED_HEAD


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

# A number outside this domain's identity vocabulary, which is what a hand
# edit leaves where the pull request belongs.
_MALFORMED_NUMBER = "not-a-number"

# Every way a receipt group stops being one, and exactly what the comment
# holds in each. One table because what they cost is one thing: read as no
# receipt at all the candidate is measured and published, and the write behind
# that push puts a whole fresh group down over the damage.
#
# Three shapes. A member CARRYING a value nothing here will type, spelled in
# that member's own vocabulary -- the two commits are object ids and the pull
# request is an identity. A member whose KEY has gone, which is the one no
# value reader can see: `null` and "not on the comment" read back identically
# to all of them, and only the first is something a write here produced. And a
# group that names no publication -- a commit with no number beside it cannot
# say where the work went, and a lease or a number with no commit cannot say
# what was published. An empty LEASE is in none of them: an initial
# publication froze no head and records `null`.
_DAMAGED_GROUPS = MappingProxyType({
    "a commit nothing can read": {
        _KEY_PUBLISHED_SHA: _MALFORMED_RECEIPT,
        _KEY_PUBLISHED_LEASE: None,
        _KEY_PUBLISHED_PR: _PR_NUMBER,
    },
    "a lease nothing can read": {
        _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
        _KEY_PUBLISHED_LEASE: _MALFORMED_RECEIPT,
        _KEY_PUBLISHED_PR: _PR_NUMBER,
    },
    "a number nothing can read": {
        _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
        _KEY_PUBLISHED_LEASE: None,
        _KEY_PUBLISHED_PR: _MALFORMED_NUMBER,
    },
    "a commit key that is gone": {
        _KEY_PUBLISHED_LEASE: None, _KEY_PUBLISHED_PR: _PR_NUMBER,
    },
    "a lease key that is gone": {
        _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
        _KEY_PUBLISHED_PR: _PR_NUMBER,
    },
    "a number key that is gone": {
        _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
        _KEY_PUBLISHED_LEASE: None,
    },
    "a lease orphaned by a cleared commit": {
        _KEY_PUBLISHED_SHA: None,
        _KEY_PUBLISHED_LEASE: _MOVED_HEAD,
        _KEY_PUBLISHED_PR: None,
    },
    "a number orphaned by a cleared commit": {
        _KEY_PUBLISHED_SHA: None,
        _KEY_PUBLISHED_LEASE: None,
        _KEY_PUBLISHED_PR: _PR_NUMBER,
    },
    # An EARLIER commit with no number beside it, which is the shape the road
    # that reads a receipt against the candidate never sees: the receipt names
    # some other object id, so nothing below would meet the record at all
    # before the push wrote over it.
    "no publication named at all": {
        _KEY_PUBLISHED_SHA: _MOVED_HEAD,
        _KEY_PUBLISHED_LEASE: None,
        _KEY_PUBLISHED_PR: None,
    },
    "no publication named, spelled empty": {
        _KEY_PUBLISHED_SHA: _MOVED_HEAD,
        _KEY_PUBLISHED_LEASE: None,
        _KEY_PUBLISHED_PR: "",
    },
})

# What a member can hold once a hand edit or a half-written crash has been at
# it, beyond the plain string that is not an object id. The payload is JSON,
# so every one of these is FALSY in Python while being exactly the damage an
# "empty means absent" reading waves straight through.
_FALSY_MEMBERS = (False, 0, [], {})


class RecordedPullRequestRaceTest(_ReceiptCase, unittest.TestCase):
    """The pull request an ordinary publication would REUSE, ending mid-tick.

    Nothing here was proved by the gate: the record names a pull request this
    issue arrived carrying -- the `discussion` stage's plan PR sitting on the
    very ref the dev commits go to, or this stage's own from a round that
    crashed before its relabel -- and the seam reuses it by looking the BRANCH
    up. So an ending landing between the tick's first reading and the push
    leaves that lookup answering nothing: a second pull request is opened over
    the work and `pr_number` overwritten with it, which loses the pointer to
    whatever a human just closed.
    """

    def setUp(self) -> None:
        super().setUp()
        self._stand_the_pull_request_on(_MOVED_HEAD)
        self._seed(pr_number=_PR_NUMBER, branch=_BRANCH)

    def test_an_ending_before_the_push_opens_none(self) -> None:
        # Every state a reuse may not find, raced into the window the barrier
        # exists for -- the unreadable one included, since this reading fails
        # closed: what refusing costs is the poll that asks again, and what
        # falling through costs is a branch and a pull request nobody asked
        # for.
        for described, ending in (
            ("closed", self._closes_the_recorded_pr),
            ("merged", self._merges_the_recorded_pr),
            ("unreadable", self._loses_the_recorded_pr),
        ):
            with self.subTest(pull_request=described):
                self.setUp()

                mocks = self._raced(ending)

                self._assert_held(mocks)
                self.assertNotIn(_VALIDATING, self.github.label_history)
                self.assertEqual(
                    self._pinned()["pr_number"], _PR_NUMBER,
                )

    def test_one_still_open_publishes_as_ever(self) -> None:
        # The other side, so the barrier is about the ending rather than about
        # an issue that records a pull request at all: nothing raced, and the
        # push lands onto the pull request the reuse finds.
        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        mocks[support.PUSH_BRANCH].assert_called_once()
        self.assertEqual(self.github.opened_prs, [])

    def _raced(self, ending):
        """Run one tick, ending the recorded pull request past the intent."""
        with patch.object(
            _publication,
            _PUBLICATION_INTENT,
            _RacesPastTheStep(_publication._publication_intent, ending),
        ):
            return self._run_gate(added_lines=support.SMALL_ADDITIONS)

    def _closes_the_recorded_pr(self) -> None:
        self.github.get_pr(_PR_NUMBER).state = _CLOSED

    def _merges_the_recorded_pr(self) -> None:
        merged = self.github.get_pr(_PR_NUMBER)
        merged.merged = True
        merged.state = _CLOSED

    def _loses_the_recorded_pr(self) -> None:
        self.github.pulls.pop(_PR_NUMBER, None)


class UnprovableReceiptTest(_ReceiptCase, unittest.TestCase):
    """Every record the note stands beside that proves nothing at all.

    Held fail-CLOSED rather than measured, and the size of the candidate is
    exactly why. Falling through to the reading is not a neutral answer: a
    count under the ceiling PUBLISHES, which force-pushes a branch nothing
    here could confirm and opens a second pull request over work the first may
    already carry -- the outcome the whole proof exists to close, reached by
    the commonest reading there is.
    """

    def test_an_unprovable_receipt_is_held(self) -> None:
        # Each half of the proof, missing on its own, against a candidate the
        # ceiling would wave straight through. No pull request recorded at
        # all, one this host cannot read, one the branch has moved off, one
        # open where this seam would never push, and one somebody closed.
        for described in _UNPROVABLE:
            with self.subTest(record=described):
                self._seeded(described)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)

    def test_the_record_is_left_for_the_retry(self) -> None:
        # What the park may not cost: the receipt, the pull request it names,
        # and the commit itself are what a terminal drains and what a repaired
        # record republishes from, so the refusal writes the park and nothing
        # else.
        self._seeded("one the branch moved off")

        self._run_gate(added_lines=support.SMALL_ADDITIONS)

        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(
            pinned[support.PARK_REASON], support.PARK_MEASUREMENT_FAILED,
        )
        self.assertEqual(pinned[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[_KEY_PR_NUMBER], _PR_NUMBER)

    def test_an_oversized_one_is_held_the_same_way(self) -> None:
        # The same answer on the road that would have been held anyway, so the
        # refusal reads as one rule rather than as a size question.
        self._seeded("one open somewhere else")

        mocks = self._oversized()

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)


    def test_a_case_shifted_repo_still_publishes(self) -> None:
        # Owner and repository names are case-insensitive on GitHub, so the
        # same repository is one spelling in a hand-typed setting and another
        # in every answer the API gives. Compared exactly, this repository's
        # OWN publication reads as somebody's fork and the bookkeeping behind
        # a landed push is held for a human who has nothing to reconcile.
        self._stand_the_pull_request_on(
            MEASURED_CANDIDATE_SHA, repo=_SHOUTED_REPO,
        )
        self._seed(**_PUBLISHED_BY_THIS_STAGE)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_unmeasured(mocks)
        self.assertIn(_VALIDATING, self.github.label_history)
        self.assertEqual(self.github.opened_prs, [])

    def test_a_fork_at_the_same_head_is_held(self) -> None:
        # The shape every other term agrees on: a fork carries this
        # repository's ref names over its commits, so the branch and the head
        # both match while the pull request points at a publication this issue
        # never made. Admitted, the seam would call the work delivered, skip
        # the reading, and hand a reviewer somebody else's change.
        self.setUp()
        self._stand_the_pull_request_on(
            MEASURED_CANDIDATE_SHA, repo=_FORK_REPO,
        )
        self._seed(**_PUBLISHED_BY_THIS_STAGE)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)

    def test_a_tip_no_receipt_names_is_measured(self) -> None:
        # The other half, and it is not widened either: a head the remote
        # happens to agree with says nothing about how it got there, so
        # without the note beside it any branch somebody else pushed the
        # commit to would wave the candidate past. Nothing here claims a
        # publication, so nothing is held back either.
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)
        self._seed(pr_number=_PR_NUMBER, branch=_BRANCH)

        mocks = self._oversized()

        self._assert_measured(mocks)
        self._assert_held(mocks)


class ReceiptIdentityTest(_ReceiptCase, unittest.TestCase):
    """Which pull request the receipt is about, and what happens with none.

    `pr_number` is the relabel's write, and the relabel is exactly what this
    window is missing: a push that landed and a process that died before it.
    So the identity goes down WITH the receipt, and where it is absent or
    unreadable the proof refuses rather than looking one up.

    Looking one up is the failure this pins. A lookup by branch answers with
    whatever is open on that ref -- so a replacement somebody opened after
    closing the original satisfies every other term here, and the relabel, the
    debt and the receipt behind the answer would all be spent against a
    publication this stage never made.
    """

    def test_a_receipt_with_no_identity_is_held(self) -> None:
        # Absent, and unreadable: a field an older build never wrote, and one
        # a hand edit or a half-written crash left outside this domain's
        # vocabulary. Neither names a publication, and there is no second
        # place to look that is not a search.
        for described, identity in (
            ("names none", None),
            ("names one nothing can read", _MALFORMED_RECEIPT),
        ):
            with self.subTest(receipt=described):
                self._receipt_naming(identity)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)

    def test_a_replacement_is_never_adopted(self) -> None:
        # The shape a branch lookup cannot tell from the real thing: the pull
        # request this stage published was closed, and another was opened over
        # the same branch at the same commit. Every other term agrees -- the
        # repository, the branch, the head -- and only the identity the
        # receipt carries says it is somebody else's publication.
        self._receipt_naming(None)
        self.github.get_pr(_PR_NUMBER).state = _CLOSED
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)

    def test_pr_number_is_not_a_substitute(self) -> None:
        # `pr_number` naming the very same pull request does not answer for
        # the receipt either: it is the relabel's write, so trusting it here
        # would be trusting exactly the write this window proves is missing.
        self._receipt_naming(None)
        self._seed(**{
            _KEY_PUBLISHED_SHA: MEASURED_CANDIDATE_SHA,
            _KEY_PR_NUMBER: _PR_NUMBER,
            "branch": _BRANCH,
        })

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)

    def _receipt_naming(self, identity) -> None:
        """A proved publication whose receipt carries `identity` as its PR."""
        self.setUp()
        self._stand_the_pull_request_on(MEASURED_CANDIDATE_SHA)
        self._seed(**{
            **_PUBLISHED_BY_THIS_STAGE, _KEY_PUBLISHED_PR: identity,
        })


class CollidingRecordTest(_ReceiptCase, unittest.TestCase):
    """A decision naming the same commit does not answer for where it went.

    An exemption says a human ruled the change one change; an approval says
    this gate already counted it and owes it a push. Both are about whether
    the candidate needs a fresh READING, and neither says a word about which
    pull request carries it -- which is the question the proof just failed.

    Waved past on either, the retry publishes with nothing to lease against
    and reuses whatever pull request a branch lookup finds. That window is
    reachable rather than theoretical: the road that admits a delivered
    candidate records the commit as a debt before it pushes, so a tick dying
    there leaves exactly this approval with exactly this empty lease.
    """

    def test_a_crashed_delivery_debt_is_held(self) -> None:
        # The approval the crash left, over a pull request that moved while
        # the tick was down. Read as licence to publish, the push goes out
        # unleased -- the lease it would have used was the proof -- and the
        # branch lookup behind it hands the work to whatever it finds.
        for described, standing, branch in (
            ("moved off the commit", _MOVED_HEAD, _BRANCH),
            ("open somewhere else", MEASURED_CANDIDATE_SHA, _ANOTHER_BRANCH),
        ):
            with self.subTest(pull_request=described):
                self._collided(_KEY_APPROVED_SHA, standing, branch)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_held(mocks)
                self._assert_record_stands(_KEY_APPROVED_SHA)

    def test_a_colliding_exemption_is_held(self) -> None:
        # The same hole one field over, and the commonest on the road this
        # proof exists for: an adjudicated commit whose publication cannot be
        # shown is one nothing may republish blind either.
        for described, standing, branch in (
            ("moved off the commit", _MOVED_HEAD, _BRANCH),
            ("open somewhere else", MEASURED_CANDIDATE_SHA, _ANOTHER_BRANCH),
        ):
            with self.subTest(pull_request=described):
                self._collided(_KEY_EXEMPT_SHA, standing, branch)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_held(mocks)
                self._assert_record_stands(_KEY_EXEMPT_SHA)

    def _collided(self, key: str, standing: str, branch: str) -> None:
        """A receipt and one of those records, over a publication that moved."""
        self.setUp()
        self._stand_the_pull_request_on(standing, branch=branch)
        self._seed(**{
            **_PUBLISHED_BY_THIS_STAGE,
            key: MEASURED_CANDIDATE_SHA,
        })

    def _assert_record_stands(self, key: str) -> None:
        """The park spent nothing: every record is there for the repair."""
        pinned = self._pinned()
        self.assertEqual(pinned[key], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[_KEY_PR_NUMBER], _PR_NUMBER)
        self.assertNotIn(_VALIDATING, self.github.label_history)


class DamagedReceiptTest(_ReceiptCase, unittest.TestCase):
    """What the receipt GROUP can hold, and which shapes claim a publication.

    Three fields written in one call and cleared in one call, so a group that
    reads back partial is not a record with a gap in it but one nothing here
    produced. Read fail-closed each member comes back as its value or as
    nothing, which is right for a reader deciding whether a commit may publish
    and exactly wrong for one deciding whether the record is sound. The gap
    between "carries a value" and "carries one this build can use" is what
    says a record CLAIMS a publication it cannot name -- and published over,
    the push writes a fresh group across the damage.
    """

    def test_every_damaged_shape_is_kept(self) -> None:
        # One rule over every way the group stops being one, because what
        # each of them costs is the same: read as no receipt at all the
        # candidate is measured, published, and the write behind that push
        # puts a whole fresh group down over the damage -- which completes
        # the record rather than repairing it, and destroys the one piece of
        # evidence an operator had.
        for described, group in _DAMAGED_GROUPS.items():
            with self.subTest(group=described):
                self._seeding(group)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self.assertEqual(self._receipt_group(), group)

    def test_a_falsy_member_is_held_too(self) -> None:
        # The set the value shapes above cannot be spelled with: a member
        # holding one of these is present damage that reads back as an
        # absence, so an "empty means absent" check walks straight past it.
        for damaged in _FALSY_MEMBERS:
            with self.subTest(receipt=repr(damaged)):
                group = {
                    _KEY_PUBLISHED_SHA: damaged,
                    _KEY_PUBLISHED_LEASE: None,
                    _KEY_PUBLISHED_PR: _PR_NUMBER,
                }
                self._seeding(group)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self.assertEqual(self._receipt_group(), group)

    def test_the_switch_reaches_the_same_hold(self) -> None:
        # The road that answers before the candidate question the rest of the
        # proof hangs off: `DECOMPOSE=off` with no caller-named candidate
        # freezes nothing and measures nothing, so the guard has to stand at
        # the gate's DOOR rather than beside that question. Falling through,
        # this install pushes the checkout's own head and the receipt behind
        # that push puts a fresh group down over the damage.
        group = _DAMAGED_GROUPS["a number nothing can read"]
        self._seeding(group)

        with patch(_DECOMPOSE_SWITCH, False):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertEqual(self._receipt_group(), group)

    def test_the_park_says_how_to_repair_it(self) -> None:
        # The advice every other refusal here gives is wrong for this one: the
        # group is read before any candidate is compared against it, so a
        # fresh commit earns the same hold and an operator told to commit
        # again would loop. What ends it is the record.
        self._seeding(_DAMAGED_GROUPS["a commit nothing can read"])

        self._run_gate(added_lines=support.SMALL_ADDITIONS)

        said = self.github.posted_comments[-1][1]
        self.assertIn(_KEY_PUBLISHED_SHA, said)
        self.assertIn(_KEY_PUBLISHED_PR, said)
        self.assertNotIn("commit again so the candidate is measured", said)

    def test_a_cleared_group_is_not_damage(self) -> None:
        # The other end of the same gap, so the refusal is about damage rather
        # than about a field being empty: `null` and `""` are what a build
        # that published nothing leaves, and a group cleared to them claims
        # nothing to be held to.
        for absent in (None, ""):
            with self.subTest(receipt=repr(absent)):
                self._seeding(dict.fromkeys(_RECEIPT_MEMBERS, absent))

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_measured(mocks)
                self._assert_published(mocks)


if __name__ == "__main__":
    unittest.main()
