# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a pull request is owed because this orchestrator rewrote its head.

A rewrite this orchestrator publishes -- a rebase, a conflict resolution, or
commits an earlier tick left unpushed -- moves the pull request onto a commit no
developer report is about: the report the issue last settled names the head the
rewrite replaced, and a reviewer is right to refuse it for the one standing now.
Left to that refusal, the rewrite parks the issue for a human whose reply only
restarts a report for a commit this orchestrator made itself. So the rewrite is
recorded as DEBT instead -- the pull request, its branch, the head the rewrite
replaced, and the exact head it published -- and the debt holds the review and
the roads past an approval until a report about that head settles, rather than
parking because the settled report still names the head before it.

`developer_report_rewrite_debt` is one nested object, and additive: an issue
without the key owes no rewrite a report, which is what every issue predating it
says without a migration having reached it. `null` is the resting state a paid
debt leaves, as it is on the pending transaction, so only a payload that is
present and not `null` is a CLAIM. Every member is read fail-closed and the
record all-or-nothing, so a claim short of a member, one carrying another, or
one whose two heads are the same commit is a claim nobody can describe -- which
`carries_rewrite_debt` tells apart from an issue that owes none, and which no
reader here takes for either the head it names or the head it replaced.

A later rewrite of the head the debt already names RETARGETS it: the claim
moves onto the head that rewrite published and keeps the head it replaced
first, since that is still the head the settled report is about. So repeated
base advances leave one debt naming the latest head. A rewrite back onto that
first head is refused there, since the settled report covers the head the pull
request returns to and the validating hold pays the standing debt. Where a
report of the head the debt names has settled since, that report paid the debt,
and the later rewrite's own debt takes its place instead -- a rewrite back onto
the first head included, since the settled report no longer covers it.

Idempotency is by the head a rewrite PUBLISHED: a rewrite onto the head the
claim already names, on its pull request and branch, is the claim unchanged
whatever head it says it replaced. The claim already records that head as this
orchestrator's, and the head the settled report is about is not a replay's to
move, so accepting it asserts nothing the claim did not -- which is what lets
the replay of whichever write recorded or retargeted the claim succeed. A
rewrite of any other head onto one the claim does not name, of another pull
request or branch, or over a claim nobody can read is refused and leaves the
claim standing as it is, since recording it would say this orchestrator made a
head somebody else pushed, and replacing the claim would lose the debt it
records.

What pays the debt is a report settled about the head the pull request stands
on -- whichever head that is, since a debt for a head the pull request has left
is owed to nothing -- PUBLISHED as a report of its own and written against the
requirements the issue carries now. A report verified where it already stood
pays nothing: the one standing when the head was rewritten is an account of the
head before it, and verifying it again carries it forward on nobody's proof. So
does a report of an older requirements revision. Where the settled report is of
either head the debt names and pays nothing, a fresh report of the head it
published is what the debt is owed (`RewriteDebt.owes_a_refresh`). The
validating stage is where both are asked, and where that report is obtained
(`stages/validating/report_refresh.py`). The conflict stage records one for
every head its own push rewrites (`stages/conflicts/report_debt.py`), and the
base refresh one for each clean auto rebase whose push lands before the
attempt is cleared or the issue routed, through the one finish every landing
gets (`rewrite_finish_debt.py`) -- of a rebase the tick published itself, of
a replay its crash recovery pushed again, and of a push that recovery found
already landed. A settled report of the commit an approval's squash replaced
is of neither head, so it pays nothing and is owed nothing here; whether this
orchestrator's own squash links it to the head the debt replaced is a dormant
proof beside this owner (`report_squash_lineage.py`) that nothing consults yet.
This owner is the record, its reader, its retargeting, and its drop.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_delivery as _prompt_delivery,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The report debt a rewrite of the pull request's head left and no settled
# report has paid yet.
REWRITE_DEBT = "developer_report_rewrite_debt"

_PR = "pr"

_BRANCH = "branch"

_PREVIOUS = "previous_head"

_REWRITTEN = "rewritten_head"

_MEMBERS = frozenset((_PR, _BRANCH, _PREVIOUS, _REWRITTEN))

# The pull request the issue pins, which is the one a reviewer is handed.
_PINNED_PR = "pr_number"


@dataclass(frozen=True)
class RewriteDebt:
    """One rewrite of a pull request's head, owed a report about the head it left.

    `previous_head` is the head the rewrite replaced -- the first one, across a
    retargeting -- and `rewritten_head` the exact commit it published.
    """

    pr_number: int
    branch: str
    previous_head: str
    rewritten_head: str

    def recorded(self) -> dict:
        """The pinned object this debt is written as."""
        return {
            _PR: self.pr_number,
            _BRANCH: self.branch,
            _PREVIOUS: self.previous_head,
            _REWRITTEN: self.rewritten_head,
        }

    @classmethod
    def read(cls, recorded: object) -> RewriteDebt | None:
        """The debt a recorded object names, read whole, or None."""
        if not isinstance(recorded, dict) or set(recorded) != _MEMBERS:
            return None
        debt = cls(
            pr_number=_record_values.as_recorded_number(recorded[_PR]),
            branch=_record_values.as_branch(recorded[_BRANCH]),
            previous_head=_payloads.as_hex(recorded[_PREVIOUS], _formats.COMMIT_LENGTHS),
            rewritten_head=_payloads.as_hex(recorded[_REWRITTEN], _formats.COMMIT_LENGTHS),
        )
        read_whole = (
            debt.pr_number is not None,
            debt.branch is not None,
            debt.previous_head is not None,
            debt.rewritten_head is not None,
            # A rewrite that left the head where it was moved nothing a report
            # is owed for.
            debt.previous_head != debt.rewritten_head,
        )
        return debt if all(read_whole) else None

    def retargeted(self, state: PinnedState, rewrite: RewriteDebt) -> RewriteDebt | None:
        """What this debt becomes once `rewrite` is recorded over it in `state`, or None where it is refused.

        A rewrite that published the head this debt names, on its pull
        request and branch, is this debt unchanged whatever head it says it
        replaced: the replay of whichever write recorded or retargeted it.
        Every other rewrite has to be OF that head. Where the report `state`
        last settled is about it, that report paid this debt and the
        rewrite's own debt takes its place, a rewrite back onto
        `previous_head` included. Otherwise this debt moves onto the head
        the rewrite published and keeps `previous_head` -- except onto that
        very head, which the settled report covers, so the validating hold
        pays this debt instead.
        """
        if (rewrite.pr_number, rewrite.branch, rewrite.rewritten_head) == (
            self.pr_number, self.branch, self.rewritten_head,
        ):
            return self
        chained = (rewrite.pr_number, rewrite.branch, rewrite.previous_head) == (
            self.pr_number, self.branch, self.rewritten_head,
        )
        if not chained:
            return None
        if rewrite.follows_the_report(state):
            return rewrite
        if rewrite.rewritten_head == self.previous_head:
            return None
        return replace(self, rewritten_head=rewrite.rewritten_head)

    def follows_the_report(self, state: PinnedState) -> bool:
        """Whether the report `state` last settled is about the head this rewrite replaced.

        On this rewrite's pull request and branch. It is what a debt has to be
        able to explain, and what paid the debt of the rewrite before it.
        """
        return self._settled_head(state) == self.previous_head

    def explains(self, state: PinnedState, head: str) -> bool:
        """Whether this debt is exactly why the report `state` last settled is about another head than `head`.

        Only where the pull request `state` pins is the one this debt is
        about, `head` is the commit the rewrite published, and the settled
        report is of the head it replaced, on the same pull request and
        branch. Anything else is a head this debt says nothing about.
        """
        pinned = (pinned_pull_request(state), head) == (self.pr_number, self.rewritten_head)
        return pinned and self.follows_the_report(state)

    def owes_a_refresh(self, state: PinnedState, head: str) -> bool:
        """Whether a fresh report of `head` is what this debt is owed.

        Where the debt explains the settled report, and where that report is
        already of the head this debt names, on its pull request and branch,
        and still pays nothing (`pays_the_debt`) -- a report verified where an
        earlier one stood, or written against requirements the issue has since
        moved past. Asked once the settled report is known not to pay, so a
        report of either head is one only a fresh report of `head` replaces.
        A settled report of neither head is one this debt says nothing about.
        """
        pinned = (pinned_pull_request(state), head) == (self.pr_number, self.rewritten_head)
        return pinned and self._settled_head(state) in {self.previous_head, self.rewritten_head}

    def _settled_head(self, state: PinnedState) -> str:
        """The head the report `state` last settled is about, on this debt's pull request and branch, or ""."""
        settled = _settlement.read_current_report(state)
        if settled is None:
            return ""
        subject = settled.subject
        if (subject.pr_number, subject.branch) != (self.pr_number, self.branch):
            return ""
        return subject.source_sha


def carries_rewrite_debt(state: PinnedState) -> bool:
    """Whether this issue CLAIMS a rewrite's report debt, readable or not.

    Presence rather than meaning, for the reason the report records beside it
    are asked that way: the reader below answers None both for an issue that
    owes nothing and for a claim nobody can describe, and a guard holding the
    roads past an approval may not confuse the two. `null` is no claim, since
    it is what a paid debt leaves.
    """
    return state.get(REWRITE_DEBT) is not None


def read_rewrite_debt(state: PinnedState) -> RewriteDebt | None:
    """The debt this issue carries, or None for none readable."""
    return RewriteDebt.read(state.get(REWRITE_DEBT))


def records_rewrite(state: PinnedState, rewrite: RewriteDebt) -> bool:
    """Stage the debt `rewrite` leaves, or carry the standing one onto it; False, untouched, where neither may be.

    Refused unless `rewrite` reads back as exactly itself, and, over a claim
    already standing, unless that claim reads and `rewrite` is a replay of it
    or a rewrite of the head it names (`RewriteDebt.retargeted`). Measured
    against the comment it lands on, and refused rather than truncated where
    GitHub would refuse the write. The caller writes.
    """
    staged = rewrite if RewriteDebt.read(rewrite.recorded()) == rewrite else None
    if staged is not None and carries_rewrite_debt(state):
        standing = read_rewrite_debt(state)
        staged = None if standing is None else standing.retargeted(state, rewrite)
    if staged is None:
        return False
    if not _report_record_state.fits_the_comment({**state.data, REWRITE_DEBT: staged.recorded()}):
        return False
    state.set(REWRITE_DEBT, staged.recorded())
    return True


def pinned_pull_request(state: PinnedState) -> int | None:
    """The pull request this issue pins, or None where it pins none readable."""
    return _payloads.as_identity(state.get(_PINNED_PR))


def pays_the_debt(state: PinnedState, head: str) -> bool:
    """Whether the report `state` last settled pays a rewrite's debt for `head`.

    A report about `head` on the pull request the issue pins, asked of the
    head the pull request stands on whatever head the claim names -- or
    whether it can be read at all: once such a report settles, the head a
    reviewer would be handed has its report, and a debt for any other is owed
    to nothing. It has to have been PUBLISHED, and against the requirements
    baseline the issue carries now. A verified report is somebody's earlier
    text read where it stood, the report of the head before the rewrite
    included, so it proves nothing about this one; a settlement recorded
    before its mode was is held to the same reading. A report of older
    requirements is the one the reviewer road would refuse as stale.

    The settled report is read as the pinned comment records it; whoever
    drops the debt on it re-reads it at its location first.
    """
    settled = _settlement.read_current_report(state)
    if settled is None or not head:
        return False
    subject = settled.subject
    return (subject.pr_number, subject.source_sha, subject.requirements_revision, settled.mode) == (
        pinned_pull_request(state), head,
        state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH), _records.ReportMode.PUBLISH,
    )


def drops_rewrite_debt(state: PinnedState) -> bool:
    """Stage the end of the debt this issue claims, where it claims one; whether it did.

    `null` rather than the key's removal, so a reader can tell a debt that was
    paid from an issue that never carried one. The caller writes.
    """
    if not carries_rewrite_debt(state):
        return False
    state.set(REWRITE_DEBT, None)
    return True
