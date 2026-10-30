# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Account one agent invocation's usage on its issue exactly once, in one guarded commit.

The increment and its receipt (`usage_receipts`) land together through the
guarded pinned-state commit (`pinned_commit.commit`) or not at all, so no
reading shows a run counted with nothing saying which, or receipted with
nothing counted. The commit owns the usage totals and the ledger alone:
every other field -- the lifetime launch ledger, its allowance and parks, a
session, a watermark the caller staged -- is the fresh reading's, so this
writes nothing a held return withholds and refunds no charge. The counters are
added over their fresh values, so another invocation's count since is kept.

Keyed by the invocation's identity (`AgentResult.invocation`), never by its
request fingerprint or session id. Every call reads the receipt back before
anything it sends, over the comment the caller holds read afresh and admitted
again, so asking again after an UNCONFIRMED write -- or a lost response, a
restart, or a later settlement of the same run -- adds nothing where the first
landed. That comment has to be the one the invocation's charge was written on:
an invocation of another repository, issue, or comment -- one a human replaced
included -- or of a workflow cycle the record is not on is refused, and so is
any over a damaged ledger, cycle identity, or usage counter, its receipt read
back included. One already covered answers COVERED whatever cycle it ran in,
since the ledger survives a restart and the counters with it.

Parser meanings hold: a result no process produced owes nothing even with
metrics beside it, a `None` usage owes no exit and no metric, and a parsed
`no-usage` run is one exit with no tokens and no cost. Nothing is read or
written for either kind that owes nothing, nor for a parsed usage no total
can take -- a negative count, a negative cost or one no float holds, or cost
evidence no usage record carries -- which is refused rather than committed as a
total the next reading would refuse (`usage_counters.countable`).

Only SETTLED answers (`AccountingOutcome.settled`) let work that depends on
the accounting follow. A refusal wrote nothing; an UNCONFIRMED write may read
either way until the receipt is read back. The caller holds the issue's writer
claim, as every stage handler does, so a moved record is a human's edit, not a
second writer's. The one caller is the tracked spawn
(`usage._run_agent_tracked`), which asks this of every result a process
returns before anything above it can discard the result, and holds the
result's disposition, and any further invocation a wrapper would make, on an
answer that is not settled: this is the only writer of the usage counters.
"""
from __future__ import annotations

import copy
import enum
import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    invocations as _invocations,
    issue_usage as _issue_usage,
    pinned_commit as _pinned_commit,
    pinned_commit_models as _commit_models,
    usage_counters as _usage_counters,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.late_split import keys as _late_keys

log = logging.getLogger("orchestrator.workflow")

# What this checkpoint writes, and the only fields it lays back onto its caller:
# no other road writes them, so a stage's own write keeps them as the comment
# spells them rather than as a state it holds.
ACCOUNTING = (*_issue_usage.USAGE_COUNTERS, _usage_receipts.RECEIPTS)


class AccountingStatus(enum.Enum):
    """What one checkpoint came to."""

    # This checkpoint landed the increment with its receipt.
    ACCOUNTED = "accounted"
    # The record already covers the invocation: nothing was added.
    COVERED = "covered"
    # Never invoked, or no usage parsed: nothing was read or written.
    NOTHING_OWED = "nothing_owed"
    # Sent and never confirmed: the record may read either way until the
    # receipt is read back, which asking again does first.
    UNCONFIRMED = "unconfirmed"
    # Nothing was written.
    REFUSED = "refused"


class AccountingRefusal(enum.Enum):
    """Why a checkpoint refused before its commit was asked; a refused commit names its own reason."""

    # An invoked result carrying no identity, which nothing could receipt.
    UNIDENTIFIED = "unidentified"
    # The identity names another repository, issue, or pinned comment than
    # the record's: a comment that replaced the one it was charged on included.
    FOREIGN = "foreign"
    # The identity names a workflow cycle the record is no longer on.
    OTHER_CYCLE = "other_cycle"
    # The run's parsed usage adds what no total is spelled as: a negative
    # count, a negative cost or one no float holds, or cost evidence no usage
    # record carries.
    UNCOUNTABLE = "uncountable"
    # The receipt ledger, the workflow cycle, or a usage counter reads as
    # nothing this build writes.
    DAMAGED = "damaged"


_SETTLED = frozenset((AccountingStatus.ACCOUNTED, AccountingStatus.COVERED, AccountingStatus.NOTHING_OWED))


@dataclass(frozen=True)
class AccountingOutcome:
    """One checkpoint's answer, and for a refusal its reason and the fields a refused commit named."""

    status: AccountingStatus
    refusal: AccountingRefusal | _commit_models.CommitRefusal | None = None
    fields: tuple[str, ...] = ()

    @property
    def settled(self) -> bool:
        """Whether the invocation is durably accounted or owed nothing: the only answers dependent work may follow."""
        return self.status in _SETTLED


def checkpoint(gh: GitHubClient, issue: Issue, state: PinnedState, agent_result: AgentResult) -> AccountingOutcome:
    """Account `agent_result`'s usage on `issue` once, over the pinned comment `state` names.

    `state` is the caller's own: its comment is the authoritative one the
    write is bound to, and has to be the one the invocation's charge was
    written on. On a settled answer the accounting fields landed --
    or already carried -- are laid back onto it as the comment's, so a later
    whole-state write neither drops them nor counts them as its own. Nothing
    else on it is read or moved.
    """
    if not agent_result.invoked or agent_result.usage is None:
        return AccountingOutcome(AccountingStatus.NOTHING_OWED)
    if agent_result.invocation is None:
        return _refused(issue, AccountingRefusal.UNIDENTIFIED)
    if not _usage_counters.countable(agent_result.usage):
        return _refused(issue, AccountingRefusal.UNCOUNTABLE)
    return _Checkpoint(gh, issue, state, agent_result.invocation, agent_result.usage).taken()


@dataclass(frozen=True)
class _Checkpoint:
    """One invocation's usage, the issue it is accounted on, and the caller state it is laid back onto."""

    gh: GitHubClient
    issue: Issue
    state: PinnedState
    invocation: AgentInvocation
    usage: UsageMetrics

    def taken(self) -> AccountingOutcome:
        """Read the receipt back over the authoritative comment, and commit the increment where it is missing."""
        authoritative = _commit_models.PinnedCommit.capture(self.state)
        fresh = _pinned_commit.reread(self.gh, self.issue, authoritative)
        if isinstance(fresh, _commit_models.CommitOutcome):
            return AccountingOutcome(AccountingStatus.REFUSED, fresh.refusal)
        receipts = _usage_receipts.read(fresh)
        refusal = self.refusal(fresh, receipts)
        if refusal is not None:
            return _refused(self.issue, refusal)
        if receipts.covers(self.invocation):
            self.laid_back(fresh)
            return AccountingOutcome(AccountingStatus.COVERED)
        return self.committed(fresh, receipts)

    def refusal(
        self, fresh: PinnedState, receipts: _usage_receipts.UsageReceipts | None,
    ) -> AccountingRefusal | None:
        """Why the invocation may not be accounted over `fresh` and its ledger `receipts`, or None.

        An invocation of another repository, issue, or pinned comment is
        refused before its ledger is read for it: a comment that replaced the
        one its charge was written on is no record of that run, whatever it
        copied. So is a damaged ledger, cycle identity, or usage counter,
        whatever any would say -- a cycle no reader can name is not the absent
        one, and a covered run's receipt read back beside a counter nobody
        kept settles nothing either. A covered invocation is refused for no
        cycle: its usage is already the issue's, so a restart since adds
        nothing to it.
        """
        own = (self.issue.number, fresh.repo_slug or "", fresh.comment_id)
        if (self.invocation.issue, self.invocation.repo, self.invocation.comment) != own:
            return AccountingRefusal.FOREIGN
        cycle = _invocations.cycle_of(fresh)
        if receipts is None or cycle is None or _usage_counters.miscounted(fresh.state_data):
            return AccountingRefusal.DAMAGED
        if receipts.covers(self.invocation) or cycle == self.invocation.cycle:
            return None
        return AccountingRefusal.OTHER_CYCLE

    def committed(self, fresh: PinnedState, receipts: _usage_receipts.UsageReceipts) -> AccountingOutcome:
        """Commit the increment and its receipt over `fresh`, held to the ledger and the cycle it was decided on.

        And, where `fresh` keeps no cost evidence, to the totals the evidence
        was started from (`EarlierUsage.decided_on`): an earlier build's runs
        are folded in once, as `fresh` counted them, and a count another road
        moved since is no reading that decision was taken over.
        """
        guard = _commit_models.PinnedCommit.capture(
            fresh,
            prerequisites=(
                _usage_receipts.RECEIPTS,
                _late_keys.CYCLE_ID,
                *_issue_usage.EarlierUsage.decided_on(fresh.state_data),
            ),
            owned=ACCOUNTING,
        )
        staged = dict(fresh.state_data)
        staged[_usage_receipts.RECEIPTS] = receipts.taking(self.invocation).spelled()
        folds = _usage_counters.usage_folds(self.usage, fresh.state_data)
        landed = _pinned_commit.commit(self.gh, self.issue, guard, staged, folds)
        if landed.status is _commit_models.CommitStatus.COMMITTED:
            self.laid_back(landed.reading)
            return AccountingOutcome(AccountingStatus.ACCOUNTED)
        if landed.status is _commit_models.CommitStatus.UNCONFIRMED:
            log.warning(
                "issue=#%d the usage of agent invocation %d/%s was sent and never confirmed; "
                "reading its receipt back before anything depends on it",
                self.issue.number, self.invocation.ordinal, self.invocation.nonce,
            )
            return AccountingOutcome(AccountingStatus.UNCONFIRMED)
        return AccountingOutcome(AccountingStatus.REFUSED, landed.refusal, landed.fields)

    def laid_back(self, reading: PinnedState) -> None:
        """Lay `reading`'s accounting fields onto the caller's state, as the comment's rather than its own moves."""
        for field in ACCOUNTING:
            if reading.carries(field):
                self.state.set(field, copy.deepcopy(reading.get(field)))
            else:
                self.state.state_data.pop(field, None)
        _pinned_commit.takes_in(self.state, reading.state_data, ACCOUNTING)


def _refused(issue: Issue, refusal: AccountingRefusal) -> AccountingOutcome:
    """One refusal before any commit, said locally; nothing was written for it."""
    log.warning(
        "issue=#%d accounting an agent invocation's usage was refused as %s; writing nothing",
        issue.number, refusal.value,
    )
    return AccountingOutcome(AccountingStatus.REFUSED, refusal)
