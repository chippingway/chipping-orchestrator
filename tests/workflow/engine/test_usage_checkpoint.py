# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The accounting checkpoint: one invocation's usage counted on its issue once, through a guarded commit.

What it lands -- the increment and its receipt together, the accounting fields
and nothing else -- and what it refuses with nothing written: a record
admission refuses, deleted, replaced, or unreadable, a damaged ledger or
counter, an identity of another record or cycle, and a candidate past what one
comment holds. That a settlement asked again adds nothing, before or after its
receipt retires, across a lost response and a restart, that an edit nobody
confirmed authorizes nothing until the receipt is read back, and that a comment
replacing the one a run was charged on settles nothing of that run.
"""
from __future__ import annotations

import functools
import json
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import MAX_PINNED_BODY, SCHEMA_VERSION_KEY, pinned_state_body
from orchestrator.observability.usage import cost_evidence as _usage_cost
from orchestrator.observability.usage.metrics import UsageMetrics, parse_agent_usage
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    pinned_commit_models as _commit_models,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import late_restart_state as _late_restart_state
from tests.workflow.engine import usage_checkpoint_test_support as support

_ACCOUNTED = support.STATUS.ACCOUNTED
_COVERED = support.STATUS.COVERED
_REFUSED = support.STATUS.REFUSED
_REFUSAL = support.REFUSAL
_COMMIT_REFUSAL = _commit_models.CommitRefusal
_RETAINED = _usage_receipts.RETAINED_RECEIPTS
_FLOOR = support.FLOOR
_RECENT = support.RECENT
_FIRST = 1
_SECOND = 2
_THIRD = 3
_OTHER_NONCE = "00000000000000ff"
_FIRST_NONCE = support.invocation(_FIRST).nonce
_SECOND_NONCE = support.invocation(_SECOND).nonce
_LATE_CYCLE = 7
_RESTARTED_CYCLE = 8

# The ledger one run leaves.
_ONE_RECEIPT = MappingProxyType({_FLOOR: 0, _RECENT: [[_FIRST, _FIRST_NONCE]]})

# Every run up to one past the bound, and the ledger they leave: the first
# retired under the floor, the rest kept above it.
_PAST_THE_BOUND = range(_FIRST, _RETAINED + 2)
_PAST_THE_BOUND_RECEIPTS = tuple([ordinal, support.invocation(ordinal).nonce] for ordinal in _PAST_THE_BOUND)
_RETIRED_LEDGER = MappingProxyType({_FLOOR: _FIRST, _RECENT: list(_PAST_THE_BOUND_RECEIPTS[1:])})

# Runs a hand-edited count hands one ordinal, and a settlement landing behind a
# later one inside the window.
_OUT_OF_ORDER = (
    (_THIRD, {}),
    (_SECOND, {}),
    (_SECOND, {"nonce": _OTHER_NONCE}),
)

# The cycle a restart starts, over the one that ended; what is asked after it --
# the ended cycle's settled run, its unaccounted one, and the fresh cycle's own
# -- and what each comes to.
_RESTART = LateGeneration(
    cycle_id=_RESTARTED_CYCLE,
    root_issue=support.ISSUE,
    current_issue=support.ISSUE,
    lineage_depth=0,
    restart_predecessor=_LATE_CYCLE,
)
_AFTER_RESTART = (
    (_FIRST, _LATE_CYCLE),
    (_SECOND, _LATE_CYCLE),
    (_THIRD, _RESTARTED_CYCLE),
)
_ANSWERED_AFTER_RESTART = ((_COVERED, None), (_REFUSED, _REFUSAL.OTHER_CYCLE), (_ACCOUNTED, None))
_KEPT_AFTER_RESTART = MappingProxyType({
    _FLOOR: 0,
    _RECENT: [[_FIRST, _FIRST_NONCE], [_THIRD, support.invocation(_THIRD).nonce]],
})

# The cost two reported runs state together.
_TWICE_REPORTED = _usage_cost.reduce_costs((support.REPORTED_COST, support.REPORTED_COST))

# Cycle identities no build writes, each read as damage rather than as the
# absent cycle 0: only a field left out is no cycle.
_DAMAGED_CYCLES = ("damaged", 0, -1, True, None, 1.5)

# Unconfirmed reads of the comment, each refusing with nothing written.
_UNREAD = ("unreadable", "unanswered_once")

# Ledgers no build writes, each read as damage rather than as an empty one.
_DAMAGED_LEDGERS = MappingProxyType({
    "null": None,
    "a list": [[_FIRST, _FIRST_NONCE]],
    "no floor": {_RECENT: []},
    "an extra key": {_FLOOR: 0, _RECENT: [], "retired": []},
    "a flag for a floor": {_FLOOR: True, _RECENT: []},
    "a negative floor": {_FLOOR: -1, _RECENT: []},
    "a receipt with no nonce": {_FLOOR: 0, _RECENT: [[_FIRST]]},
    "an upper-case nonce": {_FLOOR: 0, _RECENT: [[_FIRST, _OTHER_NONCE.upper()]]},
    "a short nonce": {_FLOOR: 0, _RECENT: [[_FIRST, "01"]]},
    "receipts out of order": {_FLOOR: 0, _RECENT: [[_SECOND, _SECOND_NONCE], [_FIRST, _FIRST_NONCE]]},
    "a receipt twice": {_FLOOR: 0, _RECENT: [[_FIRST, _FIRST_NONCE], [_FIRST, _FIRST_NONCE]]},
    "a receipt at the floor": {_FLOOR: _FIRST, _RECENT: [[_FIRST, _FIRST_NONCE]]},
    "past the bound": {_FLOOR: 0, _RECENT: list(_PAST_THE_BOUND_RECEIPTS)},
})

# A counter spelled as nothing its writers write, a whole number past the
# largest float -- a count still, a cost no float holds -- and the meter a
# caller holds that nothing was laid onto.
_BROKEN = "broken"
_FLOAT_DIGITS_PAST = 400
_PAST_ANY_FLOAT = 10 ** _FLOAT_DIGITS_PAST
_NOTHING_COUNTED = (None, None, None, None)

# Two amounts each a float holds and their sum none does: evidence stating
# them on two bases, and a run stating the second unpriced beside the rest of
# its usage, as an Antigravity estimate partly priced would.
_HALF_PAST_ANY_FLOAT = 1e308
_REPORTED_PART = _usage_cost.CostContribution(_usage_cost.CLI_REPORTED, _HALF_PAST_ANY_FLOAT)
_GEMINI_PART = _usage_cost.CostContribution(_usage_cost.GEMINI_API_ESTIMATE, _HALF_PAST_ANY_FLOAT)
_PAST_ANY_FLOAT_TOGETHER = _usage_cost.CostEvidence(_usage_cost.COMPLETE, (_REPORTED_PART, _GEMINI_PART))
_HALF_PAST_ANY_FLOAT_UNPRICED = UsageMetrics(
    backend="agy",
    cost_source="unknown-price",
    cost_evidence=_usage_cost.CostEvidence(_usage_cost.INCOMPLETE, (_GEMINI_PART,)),
)

# Totals the run above cannot be added to without a cost total no float holds:
# an earlier build's cost, and this build's reported one.
_HALF_PAST_ANY_FLOAT_TOTALS = (
    MappingProxyType({support.RUNS: 1, support.TOKENS: 100, support.COST: _HALF_PAST_ANY_FLOAT}),
    MappingProxyType({
        support.RUNS: 1,
        support.COST: _HALF_PAST_ANY_FLOAT,
        support.EVIDENCE: _usage_cost.CostEvidence(_usage_cost.COMPLETE, (_REPORTED_PART,)).to_dict(),
    }),
)

# Counters spelled as nothing their writers write, each refusing the increment,
# and the run accounted over it: a priced one, or one that adds nothing to the
# cost total it is still held to.
_PRICED = MappingProxyType({})
_UNPRICED = MappingProxyType({"usage": support.UNPRICED})
_DAMAGED_COUNTERS = (
    (support.RUNS, True, _PRICED),
    (support.RUNS, "4", _PRICED),
    (support.RUNS, -1, _UNPRICED),
    (support.TOKENS, 1.5, _PRICED),
    (support.TOKENS, None, _UNPRICED),
    (support.COST, False, _PRICED),
    (support.COST, "0.5", _PRICED),
    (support.COST, -0.5, _PRICED),
    (support.COST, _BROKEN, _UNPRICED),
    (support.COST, True, _UNPRICED),
    (support.COST, _PAST_ANY_FLOAT, _PRICED),
    (support.COST, _PAST_ANY_FLOAT, _UNPRICED),
    (support.SOURCES, support.REPORTED, _PRICED),
    (support.SOURCES, [1], _UNPRICED),
    (support.EVIDENCE, _BROKEN, _PRICED),
    (support.EVIDENCE, _usage_cost.CostEvidence(_usage_cost.COMPLETE).to_dict(), _UNPRICED),
    (support.EVIDENCE, None, _UNPRICED),
    (support.EVIDENCE, _PAST_ANY_FLOAT_TOGETHER.to_dict(), _UNPRICED),
    (support.UNTOTALED, -1, _PRICED),
    (support.EARLIER, True, _UNPRICED),
    # The runs a total leaves unsettled are never written without the
    # evidence they were counted beside.
    (support.UNTOTALED, 1, _PRICED),
    (support.EARLIER, _SECOND, _UNPRICED),
)

# Identities of another record, and what each is refused as.
_FOREIGN = (
    ("another issue", {"issue": support.ISSUE + 1}, _REFUSAL.FOREIGN),
    ("another repository", {"repo": "someone/else"}, _REFUSAL.FOREIGN),
    ("no comment", {"comment": None}, _REFUSAL.FOREIGN),
    ("another cycle", {"cycle": _LATE_CYCLE}, _REFUSAL.OTHER_CYCLE),
    ("an unreadable cycle", {"cycle": None}, _REFUSAL.OTHER_CYCLE),
)

# Runs charged on a comment a human then replaced with a copy of its record:
# one the copy carries a receipt for, and one it does not.
_CHARGED_BEFORE_REPLACEMENT = (_FIRST, _SECOND)

# A field filling the comment to within `_HEADROOM` characters of its limit:
# room for the record as it reads, and none for a run and its receipt.
_PADDING = "padding"
_HEADROOM = 64
_UNPADDED = len(pinned_state_body({SCHEMA_VERSION_KEY: 1, _PADDING: ""}))
_FILLED = MAX_PINNED_BODY - _HEADROOM - _UNPADDED
_FILLER = "x" * _FILLED

# A record other roads own beside the meter -- a park, a watermark, and the
# lifetime ledger -- and the moves a caller stages over two of them.
_PARKED = "awaiting_human"
_WATERMARK = "last_action_comment_id"
_MOVED_WATERMARK = 60
_BESIDE = MappingProxyType({
    _PARKED: True,
    "park_reason": "agent_run_limit",
    _WATERMARK: 55,
    "agent_runs_used": 3,
    "agent_run_reservation": "started",
})

# A meter this build counted that another road folds into while the
# checkpoint decides -- a run of its own, priced on OpenAI's rates, and then
# one nobody priced -- and what both folds leave: every run once, and each
# basis's amount beside the reported run's, a subtotal since one run is
# unpriced.
_ESTIMATED = "estimated"
_OPENAI_COST = 0.25
_OPENAI_ESTIMATE = _usage_cost.CostContribution(_usage_cost.OPENAI_API_ESTIMATE, _OPENAI_COST)
_FOLDED_BEFORE = MappingProxyType({
    support.RUNS: 2,
    support.TOKENS: 10,
    support.SOURCES: [_ESTIMATED],
    support.EVIDENCE: _usage_cost.CostEvidence(_usage_cost.COMPLETE, (_OPENAI_ESTIMATE,)).to_dict(),
})
_TOKENS_MEANWHILE = 40
_FOLDED_MEANWHILE = MappingProxyType({
    support.RUNS: 3,
    support.TOKENS: _TOKENS_MEANWHILE,
    support.UNTOTALED: 1,
    support.EVIDENCE: _usage_cost.CostEvidence(_usage_cost.INCOMPLETE, (_OPENAI_ESTIMATE,)).to_dict(),
})
_FOLDED_BOTH = (4, _TOKENS_MEANWHILE + support.RUN_TOKENS, support.RUN_COST, [_ESTIMATED, support.REPORTED])
_FOLDED_EVIDENCE = (
    _usage_cost.CostEvidence(
        _usage_cost.INCOMPLETE, (*support.REPORTED_COST.contributions, _OPENAI_ESTIMATE),
    ).to_dict(),
    1,
    None,
)

# What a run that printed no usage states, and a record this build counted one such run on.
_NO_USAGE = _usage_cost.CostEvidence(_usage_cost.NO_USAGE).to_dict()
_COUNTED_ONCE = MappingProxyType({
    support.RUNS: 1,
    support.TOKENS: 0,
    support.SOURCES: ["no-usage"],
    support.EVIDENCE: _NO_USAGE,
})

# What another road moves between the read-back and the commit, and what the
# commit refuses it as: the fields it is held to, and totals it adds to.
_MEANWHILE_MOVES = (
    (support.RECEIPTS, {_FLOOR: 0, _RECENT: [[_SECOND, _SECOND_NONCE]]}, _COMMIT_REFUSAL.PREREQUISITE_CHANGED),
    (support.CYCLE, _LATE_CYCLE, _COMMIT_REFUSAL.PREREQUISITE_CHANGED),
    (support.COST, _BROKEN, _COMMIT_REFUSAL.OWNED_CONFLICT),
    (support.EVIDENCE, _BROKEN, _COMMIT_REFUSAL.OWNED_CONFLICT),
    (support.UNTOTALED, -1, _COMMIT_REFUSAL.OWNED_CONFLICT),
)

# Totals keeping no evidence -- an earlier build's runs, and an issue that
# counted nothing -- and a move another road lands on what the evidence is
# started from between the read-back and the commit: no run is folded over a
# start nobody decided it on.
# Each case is the record, the move, and the earlier runs kept once the run
# is asked again: every run the comment then counts without evidence.
_EARLIER_RUNS = MappingProxyType({support.RUNS: _SECOND, support.TOKENS: 9, support.COST: 1.0})
_START_MOVES = (
    (_EARLIER_RUNS, {support.RUNS: _THIRD}, _THIRD),
    (_EARLIER_RUNS, {support.COST: 2.0}, _SECOND),
    (MappingProxyType({}), {support.RUNS: _FIRST}, _FIRST),
    (MappingProxyType({}), {support.EVIDENCE: _NO_USAGE}, None),
)


def _repinned(world: support.AccountingWorld) -> None:
    """The pinned comment is replaced by another one carrying the same record."""
    world.github.seed_state(world.issue, **world.record())


def _restarted(world: support.AccountingWorld) -> None:
    """The restart projection rewrites the comment as the fresh cycle's whole durable state."""
    projected = world.github.read_pinned_state(world.issue)
    _late_restart_state._projected(projected, _RESTART, {})
    world.github.write_pinned_state(world.issue, projected)


# Parsed usage no counter's total is spelled as: a claude result reporting a
# negative cost, as the parser hands it back, and metrics carrying a
# non-finite cost or a negative or flag token count.
_CLAUDE = "claude"
_UNCOUNTABLE_USAGE = MappingProxyType({
    "a negative reported cost": parse_agent_usage(_CLAUDE, json.dumps({"type": "result", "total_cost_usd": -0.5})),
    "a non-finite cost": UsageMetrics(backend=_CLAUDE, cost_usd=float("nan"), cost_source=support.REPORTED),
    "a negative token count": UsageMetrics(backend=_CLAUDE, output_tokens=-1),
    "a flag for a token count": UsageMetrics(backend=_CLAUDE, input_tokens=True),
    "a negative cached count": UsageMetrics(backend=_CLAUDE, cached_tokens=-1),
    "cost evidence summing past any float": UsageMetrics(
        backend=_CLAUDE, cost_source="unknown-price", cost_evidence=_PAST_ANY_FLOAT_TOGETHER,
    ),
    "cost evidence no record carries": UsageMetrics(
        backend=_CLAUDE,
        cost_source="unknown-price",
        cost_evidence=_usage_cost.CostEvidence(
            "incomplete", (_usage_cost.CostContribution("anthropic-api-estimate", -0.5),),
        ),
    ),
})


# What spoils the comment the caller holds, and what the checkpoint refuses it as.
_SPOILS = (
    ("unsupported", functools.partial(support.unpinned, unsupported=True), _COMMIT_REFUSAL.UNSUPPORTED),
    ("malformed", functools.partial(support.unpinned, malformed=True), _COMMIT_REFUSAL.MALFORMED),
    ("deleted", support.unpinned, _COMMIT_REFUSAL.REPLACED),
    ("replaced", _repinned, _COMMIT_REFUSAL.REPLACED),
)


class ReceiptLifecycleTest(unittest.TestCase):
    """A settlement asked again adds nothing, however many receipts came after it."""

    def test_a_repeated_settlement_adds_nothing(self) -> None:
        # Asked again by the same process, and by a fresh one that holds
        # nothing of it but the record.
        world = support.seeded()
        first = world.ran(_FIRST)
        writes = world.github.write_state_calls

        repeated = (world.ran(_FIRST), world.restarted().ran(_FIRST))

        answered = [outcome.status for outcome in (first, *repeated)]
        self.assertEqual(answered, [_ACCOUNTED, _COVERED, _COVERED])
        self.assertTrue(all(outcome.settled for outcome in (first, *repeated)))
        self.assertEqual(support.counted(world.record()), support.ONE_RUN)
        self.assertEqual(world.github.write_state_calls, writes)
        self.assertEqual(world.record()[support.RECEIPTS], dict(_ONE_RECEIPT))

    def test_a_retired_receipt_refuses_its_replay(self) -> None:
        # Past the bound the oldest receipt retires under the floor. A replay
        # of it is covered by the floor, and so is a run at or below it never
        # accounted -- an undercount, never a second count.
        world = support.seeded()
        for ordinal in _PAST_THE_BOUND:
            self.assertIs(world.ran(ordinal).status, _ACCOUNTED)
        settled = world.snapshot()

        replays = (world.ran(_FIRST), world.ran(_FIRST, nonce=_OTHER_NONCE))

        self.assertEqual([replay.status for replay in replays], [_COVERED, _COVERED])
        self.assertEqual(world.snapshot(), settled)
        self.assertEqual(world.record()[support.RECEIPTS], dict(_RETIRED_LEDGER))
        self.assertEqual(world.record()[support.RUNS], len(_PAST_THE_BOUND))

    def test_a_restart_keeps_what_was_settled(self) -> None:
        # The restart projection keeps the ledger beside the meter it covers:
        # the ended cycle's settled run adds nothing, its unaccounted one is
        # not counted into the fresh cycle, and the fresh cycle's run is.
        world = support.seeded(**{support.CYCLE: _LATE_CYCLE})
        world.ran(_FIRST, cycle=_LATE_CYCLE)
        _restarted(world)

        answered = []
        for ordinal, cycle in _AFTER_RESTART:
            outcome = world.restarted().ran(ordinal, cycle=cycle)
            answered.append((outcome.status, outcome.refusal))

        self.assertEqual(tuple(answered), _ANSWERED_AFTER_RESTART)
        self.assertEqual(world.record()[support.RUNS], _SECOND)
        self.assertEqual(world.record()[support.RECEIPTS], dict(_KEPT_AFTER_RESTART))
        # The evidence the ended cycle's run was counted with is kept beside
        # its count, so the fresh cycle's run reduces into it rather than
        # reading it as an earlier build's run of unknown basis.
        self.assertEqual(world.record()[support.EVIDENCE], _TWICE_REPORTED.to_dict())
        self.assertNotIn(support.EARLIER, world.record())

    def test_shared_or_late_ordinals_each_count(self) -> None:
        # A hand-edited count can hand two processes one ordinal, and a
        # settlement can land behind a later one inside the window: each is a
        # run of its own, told apart by its nonce.
        world = support.seeded()

        outcomes = {world.ran(ordinal, **overrides).status for ordinal, overrides in _OUT_OF_ORDER}

        self.assertEqual(outcomes, {_ACCOUNTED})
        self.assertEqual(world.record()[support.RUNS], len(_OUT_OF_ORDER))


class UncertainWriteTest(unittest.TestCase):
    """An edit nobody confirmed settles nothing until its receipt is read back."""

    def test_a_lost_response_is_read_back(self) -> None:
        # The edit landed and its response was lost: asking again finds the
        # receipt and adds nothing.
        world, retried = self._retried_after("lost")

        self.assertIs(retried.status, _COVERED)
        self.assertEqual(support.counted(world.record()), support.ONE_RUN)
        self.assertEqual(support.counted(world.state.state_data), support.ONE_RUN)

    def test_a_refused_edit_is_sent_again(self) -> None:
        # The edit never landed: asking again finds no receipt and lands it.
        world, retried = self._retried_after("refused")

        self.assertIs(retried.status, _ACCOUNTED)
        self.assertEqual(support.counted(world.record()), support.ONE_RUN)
        self.assertEqual(support.counted(world.state.state_data), support.ONE_RUN)

    def test_a_damaged_read_back_settles_nothing(self) -> None:
        # The lost edit landed, and a counter beside its receipt is damaged
        # before the run is asked again: a receipt read back beside a counter
        # nobody kept settles nothing, and nothing is laid onto the caller.
        world, retried = self._retried_after("lost", **{support.COST: _BROKEN})

        self.assertEqual((retried.status, retried.refusal), (_REFUSED, _REFUSAL.DAMAGED))
        self.assertFalse(retried.settled)
        self.assertEqual(support.counted(world.state.state_data), _NOTHING_COUNTED)
        self.assertEqual(world.record()[support.COST], _BROKEN)

    def test_an_unreadable_read_back_writes_nothing(self) -> None:
        for failure in _UNREAD:
            with self.subTest(failure=failure):
                world = support.seeded(**{support.RUNS: _SECOND})
                getattr(world.github.pinned_failures, failure).add(support.ISSUE)

                self.assertEqual(world.refused_quietly(), (_REFUSED, _COMMIT_REFUSAL.UNREADABLE, (), True))

    def _retried_after(self, failure: str, **damaged) -> tuple:
        """One run whose edit `failure` leaves unconfirmed, asked again once the failure clears.

        Another road writes `damaged` over the record in between, where named.
        """
        world = support.seeded()
        held = world.snapshot()[-1]
        getattr(world.github.pinned_failures, failure).add(support.ISSUE)
        unconfirmed = world.ran(_FIRST)
        self.assertEqual(
            (unconfirmed.status, unconfirmed.settled, world.snapshot()[-1]),
            (support.STATUS.UNCONFIRMED, False, held),
            "an unconfirmed edit settles nothing and lays nothing back",
        )
        getattr(world.github.pinned_failures, failure).discard(support.ISSUE)
        if damaged:
            changed = world.github.read_pinned_state(world.issue)
            changed.state_data.update(damaged)
            world.github.write_pinned_state(world.issue, changed)
        return world, world.ran(_FIRST)


class RefusedRecordTest(unittest.TestCase):
    """What the checkpoint will not count on or write over, with nothing written."""

    def test_a_refused_record_is_left_standing(self) -> None:
        for spoiled, spoil, refusal in _SPOILS:
            with self.subTest(spoiled=spoiled):
                world = support.seeded(**{support.RUNS: _SECOND})
                spoil(world)

                self.assertEqual(world.refused_quietly(), (_REFUSED, refusal, (), True))

    def test_a_damaged_ledger_is_never_written(self) -> None:
        for damage, ledger in _DAMAGED_LEDGERS.items():
            with self.subTest(damage=damage):
                world = support.seeded(**{support.RECEIPTS: ledger})

                self.assertEqual(world.refused_quietly(_SECOND), (_REFUSED, _REFUSAL.DAMAGED, (), True))

    def test_a_damaged_cycle_is_no_absent_one(self) -> None:
        # A cycle-0 run -- the absent cycle's -- is not accounted over a
        # record whose cycle identity no reader can name.
        for spelled in _DAMAGED_CYCLES:
            with self.subTest(spelled=spelled):
                world = support.seeded(**{support.CYCLE: spelled})

                self.assertEqual(world.refused_quietly(), (_REFUSED, _REFUSAL.DAMAGED, (), True))

    def test_a_damaged_counter_refuses_the_run(self) -> None:
        for counter, spelled, run in _DAMAGED_COUNTERS:
            with self.subTest(counter=counter, spelled=spelled, priced=not run):
                world = support.seeded(**{counter: spelled})

                refused = world.refused_quietly(**run)

                self.assertEqual(refused, (_REFUSED, _REFUSAL.DAMAGED, (), True))

    def test_a_replacement_settles_no_earlier_run(self) -> None:
        # The comment a run was charged on is replaced by a copy of its record,
        # receipts and all, and the caller reads the replacement afresh: that
        # run is no run of the replacement, accounted there or not.
        world = support.seeded()
        charged_on = world.state.comment_id
        world.ran(_FIRST)
        _repinned(world)
        replacement = world.restarted()

        for ordinal in _CHARGED_BEFORE_REPLACEMENT:
            with self.subTest(ordinal=ordinal):
                self.assertEqual(
                    replacement.refused_quietly(ordinal, comment=charged_on), (_REFUSED, _REFUSAL.FOREIGN, (), True),
                )

    def test_another_records_invocation_is_refused(self) -> None:
        for named, overrides, refusal in _FOREIGN:
            with self.subTest(named=named):
                world = support.seeded()

                self.assertEqual(world.refused_quietly(**overrides), (_REFUSED, refusal, (), True))
        unidentified = support.seeded().account(support.invoked(None))
        self.assertEqual(unidentified.refusal, _REFUSAL.UNIDENTIFIED)

    def test_a_full_comment_writes_nothing(self) -> None:
        # The candidate is measured as it would be written, receipt included,
        # before anything goes out; a comment it would overflow keeps its record.
        world = support.seeded(**{_PADDING: _FILLER})

        self.assertLessEqual(len(pinned_state_body(world.record())), MAX_PINNED_BODY)
        self.assertEqual(world.refused_quietly(), (_REFUSED, _COMMIT_REFUSAL.OVERFLOW, (), True))


class GuardedFieldsTest(unittest.TestCase):
    """Only the accounting fields move, over whatever the comment carries when the commit lands."""

    def test_a_count_past_any_float_is_counted(self) -> None:
        # A count is a whole number of any size, added as one and never
        # converted: one past the largest float takes the run like any other.
        world = support.seeded(**{support.TOKENS: _PAST_ANY_FLOAT})

        self.assertIs(world.ran().status, _ACCOUNTED)
        self.assertEqual(world.record()[support.TOKENS], _PAST_ANY_FLOAT + support.RUN_TOKENS)

    def test_an_uncountable_run_is_never_committed(self) -> None:
        # A run whose parsed usage would land a total its own read-back
        # refuses is refused before anything is read, and alike when asked
        # again: no receipt was written for it, and no counter moved.
        for named, parsed in _UNCOUNTABLE_USAGE.items():
            with self.subTest(named=named):
                world = support.seeded(**{support.RUNS: _SECOND})
                refused = (_REFUSED, _REFUSAL.UNCOUNTABLE, (), True)

                self.assertEqual(world.refused_quietly(usage=parsed), refused)
                self.assertEqual(world.refused_quietly(usage=parsed), refused, "nothing was receipted for it")

    def test_a_cost_no_float_holds_is_never_committed(self) -> None:
        # Each basis's amount fits, but the issue's amounts together would
        # not: the commit refuses the evidence it would make, so nothing is
        # counted or receipted, and the receipt the totals read as still
        # renders, never failing on a sum it cannot state.
        for totals in _HALF_PAST_ANY_FLOAT_TOTALS:
            with self.subTest(evidenced=support.EVIDENCE in totals):
                world = support.seeded(**totals)

                refused = world.refused_quietly(_SECOND, usage=_HALF_PAST_ANY_FLOAT_UNPRICED)

                self.assertEqual(refused, (_REFUSED, _COMMIT_REFUSAL.OWNED_CONFLICT, (support.EVIDENCE,), True))
                self.assertIsNotNone(_issue_usage._format_issue_usage_verdict(world.restarted().state))

    def test_only_the_accounting_fields_change(self) -> None:
        # A park, a watermark, and the lifetime ledger beside the meter stay
        # as the comment carried them, and the watermark move the caller
        # staged is its own write to make; the checkpoint lays back only what
        # it landed, as the comment's.
        world = support.seeded(**_BESIDE)
        world.state.set(_WATERMARK, _MOVED_WATERMARK)

        self.assertIs(world.ran().status, _ACCOUNTED)

        landed = world.record()
        synced = json.loads(world.state.synced)
        self.assertLessEqual(_BESIDE.items(), landed.items())
        self.assertEqual(support.counted(landed), support.ONE_RUN)
        self.assertEqual(world.state.get(_WATERMARK), _MOVED_WATERMARK)
        self.assertEqual(support.counted(world.state.state_data), support.ONE_RUN)
        self.assertEqual(support.counted(synced), support.ONE_RUN)
        self.assertEqual(synced[support.RECEIPTS], landed[support.RECEIPTS])
        self.assertEqual(synced[_WATERMARK], _BESIDE[_WATERMARK])

    def test_another_roads_fold_is_kept(self) -> None:
        # Over totals this build counted, every total is added over the value
        # the commit finds: the other road's run, tokens, unknown token total,
        # and unpriced cost all stand beside this run's, each once.
        world = support.seeded(**_FOLDED_BEFORE)

        with world.interfering(**_FOLDED_MEANWHILE):
            outcome = world.ran()

        landed = world.record()
        self.assertIs(outcome.status, _ACCOUNTED)
        self.assertEqual(support.counted(landed), _FOLDED_BOTH)
        self.assertEqual(
            (landed[support.EVIDENCE], landed[support.UNTOTALED], landed.get(support.EARLIER)),
            _FOLDED_EVIDENCE,
        )

    def test_a_move_meanwhile_refuses(self) -> None:
        # The ledger or cycle the commit was decided on moved, or a total it
        # adds to was damaged, between the read-back and the commit's own
        # reading: nothing lands.
        for moved_field, moved, refusal in _MEANWHILE_MOVES:
            with self.subTest(moved_field=moved_field):
                world = support.seeded(**_COUNTED_ONCE)

                with world.interfering(**{moved_field: moved}):
                    outcome = world.ran()

                self.assertEqual((outcome.status, outcome.refusal), (_REFUSED, refusal))
                self.assertEqual(outcome.fields, (moved_field,))
                self.assertEqual(world.record()[support.RUNS], 1)

    def test_a_moved_start_refuses_until_read_again(self) -> None:
        # Where the totals keep no evidence, it is started from the runs and
        # cost the read-back found. Another road moving either, or landing
        # evidence of its own, before the commit reads refuses the run with
        # nothing landed; asked again, it starts from what the comment then
        # carries, a run counted without evidence kept as an earlier one.
        for record, move, earlier in _START_MOVES:
            with self.subTest(earlier=bool(record), moved=tuple(move)):
                world = support.seeded(**record)

                with world.interfering(**move):
                    refused = world.ran()

                self.assertEqual(
                    (refused.status, refused.refusal, refused.fields),
                    (_REFUSED, _COMMIT_REFUSAL.PREREQUISITE_CHANGED, tuple(move)),
                )
                self.assertIs(world.restarted().ran().status, _ACCOUNTED)
                self.assertEqual(world.record().get(support.EARLIER), earlier)


if __name__ == "__main__":
    unittest.main()
