# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Per-issue cumulative usage meter: what one accounted run adds to the totals,
the `_format_issue_usage_verdict` reader that renders the terminal receipt line,
and the tracked spawn that accounts every actual exit through the checkpoint as
it returns. Covers the non-overlapping token total and the runs it leaves
unsettled, the cost evidence reduced by basis and completeness -- reported,
estimated per provider, blended, incomplete, and an earlier build's runs of
unknown basis however many runs follow them -- the receipt's wording of each,
each exit counted once whatever its stage makes of it -- an interrupted one,
each attempt of a poisoned session's retry, and the disposition's own write
behind it -- and the hold an accounting left unresolved puts on the retry
behind it. A result with no process or no parsed usage owes nothing."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import cost_evidence as _usage_cost, token_evidence as _usage_tokens
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    issue_usage as _issue_usage,
    pinned_commit_models as _commit_models,
    usage_counters as _usage_counters,
)
from orchestrator.workflow.stages.implementing import resume as _resume, resume_request as _resume_request
from tests.workflow.engine import (
    usage_accumulator_test_support as support,
    usage_checkpoint_test_support as _accounting,
)
from tests.workflow.fixtures import REVIEWER_LAUNCH_KEYS, accounted, assert_only_accounted

FakeGitHubClient = support.FakeGitHubClient
make_issue = support.make_issue
REVIEW_APPROVED_MESSAGE = support.REVIEW_APPROVED_MESSAGE
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_PoisonedThenFreshRun = support._PoisonedThenFreshRun
_TEST_SPEC = support._TEST_SPEC
_agent = support._agent
_fake_worktree = support._fake_worktree
_open_pr_for = support._open_pr_for
_parsed = support.parsed
_stated = support.stated


_BACKEND_CLAUDE = "claude"
_BACKEND_CODEX = "codex"
_BACKEND_AGY = "agy"
_COST_SOURCE_NO_USAGE = "no-usage"
_COST_SOURCE_ESTIMATED = "estimated"
_COST_SOURCE_REPORTED = "reported"
_COST_SOURCE_UNKNOWN = "unknown-price"
_RUNS_KEY = "issue_agent_runs"
_TOKENS_KEY = "issue_total_tokens"
_UNTOTALED_KEY = "issue_total_tokens_unknown_runs"
_COST_KEY = "issue_total_cost_usd"
_COST_SOURCES_KEY = "issue_cost_sources"
_EVIDENCE_KEY = "issue_cost_evidence"
_EARLIER_KEY = "issue_unevidenced_runs"
_RESUME_ISSUE_NUMBER = 940
_POISONED_SESSION = "poisoned-sess"
_DEVELOPER_ISSUE_NUMBER = 30
_INTERRUPTED_DEVELOPER_ISSUE_NUMBER = 31
_REVIEWER_ISSUE_NUMBER = 32
_INTERRUPTED_REVIEWER_ISSUE_NUMBER = 33

# The bases and completeness a cost is stated with.
_CLI = _usage_cost.CLI_REPORTED
_ANTHROPIC = _usage_cost.ANTHROPIC_API_ESTIMATE
_OPENAI = _usage_cost.OPENAI_API_ESTIMATE
_GEMINI = _usage_cost.GEMINI_API_ESTIMATE
_UNKNOWN_BASIS = _usage_cost.UNKNOWN_BASIS
_COMPLETE = _usage_cost.COMPLETE
_INCOMPLETE = _usage_cost.INCOMPLETE
_NO_USAGE = _usage_cost.NO_USAGE
_UNKNOWN = _usage_cost.UNKNOWN

# The days an estimate's rates were verified on.
_JULY = "2026-07-15"
_AUGUST = "2026-08-01"
_SEPTEMBER = "2026-09-01"

# A Claude run whose CLI reported its cost, its four counters each a class of its own.
_CLAUDE_INPUT_TOKENS = 100
_CLAUDE_OUTPUT_TOKENS = 50
_CLAUDE_CACHE_READ_TOKENS = 30
_CLAUDE_CACHE_WRITE_TOKENS = 20
_CLAUDE_TOTAL_TOKENS = 200
_CLAUDE_RUN_COST = 1.5

# A run's input, its output, and the cached input a Codex run reports inside it.
_INPUT_TOKENS = 100
_OUTPUT_TOKENS = 40
_CACHED_TOKENS = 60
_INPUT_AND_OUTPUT = 140

# Amounts the runs below state, and what they add up to by basis.
_REPORTED_COST = 1.0
_GEMINI_COST = 0.25
_LATER_GEMINI_COST = 0.5
_OPENAI_COST = 0.5
_SMALL_COST = 0.5
_GEMINI_TOTAL = _GEMINI_COST + _LATER_GEMINI_COST
_COMPLETE_TOTAL = _REPORTED_COST + _GEMINI_TOTAL

# An amount a float holds, and evidence stating it on two bases, whose sum none does.
_HUGE_COST = 1e308
_PAST_ANY_FLOAT = _stated(_COMPLETE, (_CLI, _HUGE_COST), (_GEMINI, _HUGE_COST)).to_dict()

# Runs stated on every basis and completeness a parser writes: CLI-reported,
# Gemini-estimated twice on rates of two dates, partly priced on OpenAI's, and
# printing no usage.
_EVERY_BASIS = (
    _parsed(_stated(_COMPLETE, (_CLI, _REPORTED_COST)), input_tokens=_INPUT_TOKENS),
    _parsed(_stated(_COMPLETE, (_GEMINI, _GEMINI_COST, _AUGUST)), backend=_BACKEND_AGY, output_tokens=_OUTPUT_TOKENS),
    _parsed(
        _stated(_INCOMPLETE, (_OPENAI, _OPENAI_COST, _JULY)),
        backend=_BACKEND_CODEX,
        overlap=_usage_tokens.WITHIN_INPUT,
        input_tokens=_INPUT_TOKENS,
        cached_tokens=_CACHED_TOKENS,
    ),
    _parsed(_stated(_NO_USAGE)),
    _parsed(
        _stated(_COMPLETE, (_GEMINI, _LATER_GEMINI_COST, _SEPTEMBER)), backend=_BACKEND_AGY, input_tokens=_INPUT_TOKENS,
    ),
)
_EVERY_BASIS_TOKENS = 3 * _INPUT_TOKENS + _OUTPUT_TOKENS
_EVERY_BASIS_EVIDENCE = _stated(
    _INCOMPLETE,
    (_CLI, _REPORTED_COST),
    (_GEMINI, _GEMINI_TOTAL, _AUGUST, _SEPTEMBER),
    (_OPENAI, _OPENAI_COST, _JULY),
).to_dict()
_EVERY_SOURCE = (_COST_SOURCE_ESTIMATED, _COST_SOURCE_NO_USAGE, _COST_SOURCE_REPORTED, _COST_SOURCE_UNKNOWN)

# What a cost stating no usage is spelled as on the comment.
_NO_USAGE_SPELLED = _stated(_NO_USAGE).to_dict()

# Runs whose counters establish a non-overlapping total or leave it unknown,
# and what each adds to the token total (None for nothing): Codex's cached
# input inside its prompt, Claude's cache reads beside it, an Antigravity
# run's cache reads whose overlap nothing establishes, one that read no cache,
# and metrics built with no token evidence beside a cached count.
_PRICED = _stated(_COMPLETE, (_CLI, _SMALL_COST))
_UNPRICED = _stated(_INCOMPLETE)
_TOKEN_TOTALS = (
    (
        _parsed(
            _PRICED,
            backend=_BACKEND_CODEX,
            overlap=_usage_tokens.WITHIN_INPUT,
            input_tokens=_INPUT_TOKENS,
            cached_tokens=_CACHED_TOKENS,
            output_tokens=_OUTPUT_TOKENS,
        ),
        _INPUT_AND_OUTPUT,
    ),
    (
        _parsed(_PRICED, input_tokens=_INPUT_TOKENS, cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS),
        _INPUT_TOKENS + _CLAUDE_CACHE_READ_TOKENS,
    ),
    (
        _parsed(
            _UNPRICED,
            backend=_BACKEND_AGY,
            overlap=_usage_tokens.UNKNOWN,
            input_tokens=_INPUT_TOKENS,
            cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS,
        ),
        None,
    ),
    (
        _parsed(
            _UNPRICED, backend=_BACKEND_AGY, overlap=_usage_tokens.UNKNOWN,
            input_tokens=_INPUT_TOKENS, output_tokens=_OUTPUT_TOKENS,
        ),
        _INPUT_AND_OUTPUT,
    ),
    (
        support.UsageMetrics(
            backend=_BACKEND_CODEX,
            input_tokens=_INPUT_TOKENS,
            cached_tokens=_CACHED_TOKENS,
            cost_source=_COST_SOURCE_UNKNOWN,
        ),
        None,
    ),
)

# Totals an earlier build counted, with no evidence of what they mean: a cost
# total tagged reported, the same total tagged estimated -- read alike, since
# nothing is inferred from the tags -- and runs that summed no cost at all.
_EARLIER_RUNS = 2
_EARLIER_TOKENS = 9
_EARLIER_COST = 0.87
_EARLIER_COUNTS = ((_RUNS_KEY, _EARLIER_RUNS), (_TOKENS_KEY, _EARLIER_TOKENS))
_EARLIER_REPORTED = (*_EARLIER_COUNTS, (_COST_KEY, _EARLIER_COST), (_COST_SOURCES_KEY, [_COST_SOURCE_REPORTED]))
_EARLIER_ESTIMATED = (*_EARLIER_COUNTS, (_COST_KEY, _EARLIER_COST), (_COST_SOURCES_KEY, [_COST_SOURCE_ESTIMATED]))
_EARLIER_UNPRICED = (*_EARLIER_COUNTS, (_COST_SOURCES_KEY, [_COST_SOURCE_NO_USAGE]))

# Two runs this build counts over them -- one reported, one Gemini-estimated
# -- and what each meter's totals then state: those two runs' amounts, and the
# earlier runs' cost where they summed one, unknown in basis and completeness.
_LATER_RUNS = (
    _parsed(_stated(_COMPLETE, (_CLI, _SMALL_COST)), input_tokens=_INPUT_TOKENS),
    _parsed(_stated(_COMPLETE, (_GEMINI, _GEMINI_COST, _AUGUST)), backend=_BACKEND_AGY, output_tokens=_OUTPUT_TOKENS),
)
_LATER_PARTS = ((_CLI, _SMALL_COST), (_GEMINI, _GEMINI_COST, _AUGUST))
_LATER_TOTALS = (_EARLIER_RUNS + len(_LATER_RUNS), _EARLIER_TOKENS + _INPUT_AND_OUTPUT, None, _EARLIER_RUNS)
_EARLIER_METERS = (
    (_EARLIER_REPORTED, _stated(_UNKNOWN, *_LATER_PARTS, (_UNKNOWN_BASIS, _EARLIER_COST))),
    (_EARLIER_ESTIMATED, _stated(_UNKNOWN, *_LATER_PARTS, (_UNKNOWN_BASIS, _EARLIER_COST))),
    (_EARLIER_UNPRICED, _stated(_UNKNOWN, *_LATER_PARTS)),
)

# The receipts unstated costs read as: an earlier build's totals however they
# are tagged, those totals with a run of this build's counted after them, and
# evidence no reader takes, its amounts unreadable or summing past a float.
_EARLIER_TOKENS_TEXT = "9 tokens (2 runs counted without usage evidence)"
_UNKNOWN_EARLIER_COST = "$0.87 (basis unknown, completeness unknown)"
_LATER_RECORD = (
    (_RUNS_KEY, 3),
    (_TOKENS_KEY, 109),
    (_EARLIER_KEY, _EARLIER_RUNS),
    (_EVIDENCE_KEY, _stated(_UNKNOWN, (_CLI, _SMALL_COST), (_UNKNOWN_BASIS, _EARLIER_COST)).to_dict()),
)
_LATER_RECEIPT = (
    "3 agent runs · 109 tokens (2 runs counted without usage evidence) · "
    "$1.37 (blended: CLI-reported $0.50 + basis unknown $0.87, completeness unknown)"
)
_UNSTATED_RECEIPTS = (
    (_EARLIER_REPORTED, f"2 agent runs · {_EARLIER_TOKENS_TEXT} · {_UNKNOWN_EARLIER_COST}"),
    (_EARLIER_ESTIMATED, f"2 agent runs · {_EARLIER_TOKENS_TEXT} · {_UNKNOWN_EARLIER_COST}"),
    (_EARLIER_UNPRICED, f"2 agent runs · {_EARLIER_TOKENS_TEXT} · cost unknown"),
    (_LATER_RECORD, _LATER_RECEIPT),
    ((*_LATER_RECORD, (_EARLIER_KEY, 0), (_EVIDENCE_KEY, "broken")), "3 agent runs · 109 tokens · cost unknown"),
    ((*_LATER_RECORD, (_EARLIER_KEY, 0), (_EVIDENCE_KEY, _PAST_ANY_FLOAT)), "3 agent runs · 109 tokens · cost unknown"),
)

# Antigravity runs priced on Gemini rates -- the second's cache reads leaving
# its total unknown -- alone, and beside a reported run, and the receipt each
# set reads as once accounted.
_AGY_RUNS = (
    _parsed(
        _stated(_COMPLETE, (_GEMINI, _GEMINI_COST, _AUGUST)),
        backend=_BACKEND_AGY, overlap=_usage_tokens.UNKNOWN, input_tokens=_INPUT_TOKENS,
    ),
    _parsed(
        _stated(_COMPLETE, (_GEMINI, _LATER_GEMINI_COST, _SEPTEMBER)),
        backend=_BACKEND_AGY,
        overlap=_usage_tokens.UNKNOWN,
        input_tokens=_INPUT_TOKENS,
        cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS,
    ),
)
_REPORTED_RUN = _parsed(_stated(_COMPLETE, (_CLI, _REPORTED_COST)), output_tokens=_OUTPUT_TOKENS)
_READ_BACK = (
    (
        _AGY_RUNS,
        "2 agent runs · 100 tokens (subtotal: token total unknown for 1 run) · $0.75 (Gemini API token estimate)",
    ),
    (
        (*_AGY_RUNS, _REPORTED_RUN),
        (
            "3 agent runs · 140 tokens (subtotal: token total unknown for 1 run) · "
            "$1.75 (blended: CLI-reported $1.00 + Gemini API token estimate $0.75)"
        ),
    ),
)


# Results the checkpoint owes nothing for: a parse that failed, and metrics
# supplied beside a result no process produced.
_UNACCOUNTED = (
    {"usage": None},
    {"invoked": False},
)


# What a fold is handed beyond any total's spelling -- the run, the reading
# the fold was decided over, the total it lands on, and the value the comment
# carries there: a negative cost, a cost whose sum is past what a float holds,
# a token total no count is spelled as, evidence no reader takes, evidence a
# reading kept and the comment lost, evidence whose amounts on one basis or
# across two sum past a float, and evidence already carrying such a sum.
_NEGATIVE = -1
_FRACTIONAL_TOKENS = 1.5
_HUGE_EVIDENCE = _stated(_COMPLETE, (_CLI, _HUGE_COST))
_HUGE_UNPRICED = _stated(_INCOMPLETE, (_GEMINI, _HUGE_COST))
_KEPT_EVIDENCE = ((_EVIDENCE_KEY, _HUGE_EVIDENCE.to_dict()),)
_UNSPELLED_FOLDS = (
    (_parsed(_stated(_COMPLETE, (_CLI, _NEGATIVE))), (), _COST_KEY, _commit_models.ABSENT),
    (_parsed(_HUGE_EVIDENCE), (), _COST_KEY, _HUGE_COST),
    (_parsed(_PRICED), (), _TOKENS_KEY, _FRACTIONAL_TOKENS),
    (_parsed(_PRICED), (), _EVIDENCE_KEY, "broken"),
    (_parsed(_PRICED), _KEPT_EVIDENCE, _EVIDENCE_KEY, _commit_models.ABSENT),
    (_parsed(_HUGE_EVIDENCE), _KEPT_EVIDENCE, _EVIDENCE_KEY, _HUGE_EVIDENCE.to_dict()),
    (_parsed(_HUGE_UNPRICED), _KEPT_EVIDENCE, _EVIDENCE_KEY, _HUGE_EVIDENCE.to_dict()),
    (_parsed(_PRICED), (), _EVIDENCE_KEY, _PAST_ANY_FLOAT),
)


def _receipt(record) -> str | None:
    """The terminal receipt line the totals `record` -- a mapping, or its pairs -- carry read as."""
    return _issue_usage._format_issue_usage_verdict(PinnedState(state_data=dict(record)))


def _totals(record: dict) -> tuple:
    """What `record` counts and states: runs, tokens, the runs settled on neither, and the cost evidence."""
    return (
        record.get(_RUNS_KEY),
        record.get(_TOKENS_KEY),
        record.get(_UNTOTALED_KEY),
        record.get(_EARLIER_KEY),
        record.get(_EVIDENCE_KEY),
    )


class AccountedRunArithmeticTest(unittest.TestCase):
    """What accounted runs add to the totals: the token total, the cost evidence by basis, and the tags beside them."""

    def test_one_run_lands_its_evidence(self) -> None:
        # The run's every counter once, its CLI-reported cost on the cost
        # total and, spelled as its usage record spells it, on the evidence;
        # nothing is left unsettled, so neither unsettled count is written.
        world = _accounting.seeded()

        world.ran(usage=_parsed(
            _stated(_COMPLETE, (_CLI, _CLAUDE_RUN_COST)),
            input_tokens=_CLAUDE_INPUT_TOKENS,
            output_tokens=_CLAUDE_OUTPUT_TOKENS,
            cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS,
            cache_write_tokens=_CLAUDE_CACHE_WRITE_TOKENS,
        ))

        record = world.record()
        self.assertEqual(
            _accounting.counted(record),
            (1, _CLAUDE_TOTAL_TOKENS, _CLAUDE_RUN_COST, [_COST_SOURCE_REPORTED]),
        )
        self.assertEqual(
            record[_EVIDENCE_KEY],
            {
                "completeness": "complete",
                "contributions": [{"basis": "cli-reported", "amount_usd": _CLAUDE_RUN_COST, "rates_verified_on": []}],
            },
        )
        self.assertFalse({_UNTOTALED_KEY, _EARLIER_KEY} & record.keys())

    def test_tokens_count_each_token_once(self) -> None:
        # Each run adds its non-overlapping total where its evidence settles
        # one; where it does not, the run adds nothing to the token total and
        # one to the runs whose total is unknown.
        world = _accounting.seeded()
        settled = []
        for ordinal, (usage, added) in enumerate(_TOKEN_TOTALS, start=1):
            world.ran(ordinal, usage=usage)
            settled.append(added)

        self.assertEqual(
            _totals(world.record())[:3],
            (len(settled), sum(filter(None, settled)), settled.count(None)),
        )

    def test_runs_reduce_by_basis(self) -> None:
        # The cost evidence keeps each basis's amount apart -- an estimate's
        # rate dates beside it -- and the weakest completeness: one run partly
        # priced makes the whole a subtotal, and one printing no usage weakens
        # nothing. The cost total adds the complete costs alone, as it always
        # has, and the tags are the distinct sources, sorted.
        world = _accounting.seeded()
        for ordinal, usage in enumerate(_EVERY_BASIS, start=1):
            world.ran(ordinal, usage=usage)

        record = world.record()
        self.assertEqual(
            _accounting.counted(record),
            (len(_EVERY_BASIS), _EVERY_BASIS_TOKENS, _COMPLETE_TOTAL, list(_EVERY_SOURCE)),
        )
        self.assertEqual(record[_EVIDENCE_KEY], _EVERY_BASIS_EVIDENCE)

    def test_an_earlier_builds_runs_stay_unknown(self) -> None:
        # Totals an earlier build counted carry no evidence. The first run
        # this build counts over them folds them in as one record without
        # evidence -- their cost under the unknown basis, their completeness
        # unknown, whatever their tags say -- and keeps how many they were, so
        # neither a basis nor completeness is ever inferred for them however
        # many runs follow.
        for prior, evidence in _EARLIER_METERS:
            with self.subTest(prior=prior):
                world = _accounting.seeded(**dict(prior))
                for ordinal, usage in enumerate(_LATER_RUNS, start=_EARLIER_RUNS + 1):
                    world.ran(ordinal, usage=usage)

                self.assertEqual(
                    _totals(world.record()),
                    (*_LATER_TOTALS, evidence.to_dict()),
                )

    def test_the_checkpoint_owes_nothing_unparsed(self) -> None:
        # A parse that failed counts no exit and no metric, and a result no
        # process produced counts nothing even with metrics beside it: neither
        # is written, and both are settled.
        for overrides in _UNACCOUNTED:
            with self.subTest(**overrides):
                world = _accounting.seeded(**{_RUNS_KEY: 2})
                before = world.snapshot()

                outcome = world.ran(**overrides)

                self.assertEqual((outcome.status, outcome.settled), (_accounting.STATUS.NOTHING_OWED, True))
                self.assertEqual(world.snapshot(), before)

    def test_no_fold_lands_an_unspelled_total(self) -> None:
        # Each transformation holds what it adds and the total it makes to a
        # total's spelling, as well as the value it is laid over, so no
        # candidate carries a total its own read-back would refuse.
        for parsed, decided_over, counter, carried in _UNSPELLED_FOLDS:
            with self.subTest(counter=counter, carried=carried):
                fold = _usage_counters.usage_folds(parsed, dict(decided_over))[counter]

                self.assertIs(fold(carried, carried, carried), _commit_models.CONFLICT)


class FormatIssueUsageVerdictTest(unittest.TestCase):
    """The pure reader: `_format_issue_usage_verdict` renders the totals into the
    terminal receipt line, wording the cost off its evidence by basis and
    completeness and the tokens by the runs they settle no total for, and
    collapsing to None when nothing was counted."""

    def test_zero_runs_returns_none(self) -> None:
        # An empty state and an explicit zero both skip the line so a
        # terminal with no counted run posts no receipt.
        self.assertIsNone(_receipt({}))
        self.assertIsNone(_receipt(((_RUNS_KEY, 0), (_EVIDENCE_KEY, _NO_USAGE_SPELLED))))

    def test_cost_is_worded_by_basis_and_completeness(self) -> None:
        cases = (
            (_stated(_COMPLETE, (_CLI, _EARLIER_COST)), "$0.87 (CLI-reported)"),
            (_stated(_COMPLETE, (_GEMINI, _GEMINI_COST, _AUGUST)), "$0.25 (Gemini API token estimate)"),
            (_stated(_COMPLETE, (_ANTHROPIC, _EARLIER_COST)), "$0.87 (Anthropic API token estimate)"),
            (
                _stated(_COMPLETE, (_CLI, _EARLIER_COST), (_GEMINI, _GEMINI_COST)),
                "$1.12 (blended: CLI-reported $0.87 + Gemini API token estimate $0.25)",
            ),
            (_stated(_INCOMPLETE, (_OPENAI, _OPENAI_COST)), "$0.50 (OpenAI API token estimate, incomplete subtotal)"),
            (
                _stated(_INCOMPLETE, (_CLI, _EARLIER_COST), (_OPENAI, _OPENAI_COST)),
                "$1.37 (blended: CLI-reported $0.87 + OpenAI API token estimate $0.50, incomplete subtotal)",
            ),
            (_stated(_INCOMPLETE), "unpriced"),
            (_stated(_NO_USAGE), "no usage"),
            (_stated(_COMPLETE, (_CLI, 0)), "$0.00 (CLI-reported)"),
        )
        for evidence, expected_cost in cases:
            with self.subTest(expected_cost=expected_cost):
                record = {_RUNS_KEY: 3, _TOKENS_KEY: 45200, _EVIDENCE_KEY: evidence.to_dict()}
                expected = f":receipt: this issue: 3 agent runs · 45,200 tokens · {expected_cost}"

                self.assertEqual(_receipt(record), expected)

    def test_unstated_cost_stays_unknown(self) -> None:
        # Totals an earlier build counted read with an unknown basis and
        # completeness, whatever their tags say, and say how many runs they
        # are; so do runs this build counts after them, which make neither
        # known. Evidence no reader takes states no cost, its sum included.
        for record, expected in _UNSTATED_RECEIPTS:
            with self.subTest(expected=expected):
                self.assertEqual(_receipt(record), f":receipt: this issue: {expected}")

    def test_tokens_say_what_they_leave_unsettled(self) -> None:
        cases = (
            ({_UNTOTALED_KEY: 1}, "45,200 tokens (subtotal: token total unknown for 1 run)"),
            (
                {_UNTOTALED_KEY: 2, _EARLIER_KEY: 1},
                "45,200 tokens (subtotal: token total unknown for 2 runs; 1 run counted without usage evidence)",
            ),
            ({_TOKENS_KEY: 1234567}, "1,234,567 tokens"),
        )
        for unsettled, expected_tokens in cases:
            with self.subTest(expected_tokens=expected_tokens):
                record = {_RUNS_KEY: 3, _TOKENS_KEY: 45200, _EVIDENCE_KEY: _NO_USAGE_SPELLED, **unsettled}

                self.assertEqual(
                    _receipt(record), f":receipt: this issue: 3 agent runs · {expected_tokens} · no usage",
                )

    def test_accounted_runs_read_back_on_the_receipt(self) -> None:
        # Antigravity runs alone, priced on Gemini rates, read as a Gemini API
        # token estimate; mixed with a reported run they read as blended, with
        # each basis's amount beside the total.
        for runs, expected in _READ_BACK:
            with self.subTest(runs=len(runs)):
                world = _accounting.seeded()
                for ordinal, usage in enumerate(runs, start=1):
                    world.ran(ordinal, usage=usage)

                self.assertEqual(_receipt(world.record()), f":receipt: this issue: {expected}")


class DeveloperRunUsageAccumulationTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A fresh implementing spawn's exit is counted once, as it returns, and
    the handler's own write behind it keeps that count; an interrupted spawn
    returns without writing, and its exit alone is counted."""

    def test_fresh_spawn_persists_one_run(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(_DEVELOPER_ISSUE_NUMBER, label="workflow:implementing")
        gh.add_issue(issue)

        with patch.object(config, "DEV_AGENT", _BACKEND_CLAUDE):
            self._run_implementing(
                gh,
                issue,
                run_agent=_agent(session_id="sess-fresh", last_message="done"),
                has_new_commits=[False, True],
                push_branch=True,
            )

        state = gh.pinned_data(_DEVELOPER_ISSUE_NUMBER)
        self.assertEqual(accounted(state), (1, 1))
        # Empty stdout parses to a `no-usage` metric: a counted run with zero
        # tokens and no dollar cost.
        self.assertEqual(state[_TOKENS_KEY], 0)
        self.assertNotIn(_COST_KEY, state)
        self.assertEqual(state[_COST_SOURCES_KEY], [_COST_SOURCE_NO_USAGE])

    def test_interrupted_spawn_is_accounted_alone(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            _INTERRUPTED_DEVELOPER_ISSUE_NUMBER,
            label="workflow:implementing",
        )
        gh.add_issue(issue)
        # The drift baseline is seeded so the first encounter writes none.
        gh.seed_state(
            _INTERRUPTED_DEVELOPER_ISSUE_NUMBER,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        before = gh.pinned_data(_INTERRUPTED_DEVELOPER_ISSUE_NUMBER)

        with patch.object(config, "DEV_AGENT", _BACKEND_CLAUDE):
            self._run_implementing(
                gh,
                issue,
                run_agent=_agent(
                    session_id="sess-x", last_message="", interrupted=True,
                ),
                has_new_commits=[False],
            )

        # The shutdown-sweep contract returns before `write_pinned_state`, so
        # nothing of the run's disposition reaches GitHub; the exit it was is
        # counted once, as it returned.
        assert_only_accounted(self, before, gh.pinned_data(_INTERRUPTED_DEVELOPER_ISSUE_NUMBER))


class ResumeRunUsageAccumulationTest(unittest.TestCase):
    """`_resume_dev_with_text` counts every real agent exit once, as it
    returns: one for a plain resume, two when a poisoned resume triggers a
    fresh-spawn retry though only the retry is handed back -- and none
    retried behind a poisoned exit whose accounting is unresolved."""

    def test_plain_resume_counts_one_exit(self) -> None:
        gh, issue = self._seeded()
        gh.seed_state(
            _RESUME_ISSUE_NUMBER,
            dev_agent=_BACKEND_CLAUDE,
            dev_session_id="live-sess",
            silent_park_count=0,
        )
        state = gh.read_pinned_state(issue)

        with patch.object(
            _worktree_creation, "_ensure_worktree", _fake_worktree,
        ), patch.object(
            _agent_runner, "run_agent",
            lambda *agent_args, **agent_kwargs: _agent(
                session_id="live-sess",
                last_message="ok",
            ),
        ):
            _resume._resume_dev_with_text(_resume_request._DevResumeRequest(gh, _TEST_SPEC, issue, state, "go"))

        self.assertEqual(
            (accounted(gh.pinned_data(_RESUME_ISSUE_NUMBER)), accounted(state.state_data)),
            ((1, 1), (1, 1)),
        )

    def test_poisoned_retry_counts_both_exits(self) -> None:
        gh, issue, state = self._poisoned()

        run_recorder = _PoisonedThenFreshRun()

        with patch.object(
            _worktree_creation, "_ensure_worktree", _fake_worktree,
        ), patch.object(_agent_runner, "run_agent", run_recorder):
            _resume._resume_dev_with_text(_resume_request._DevResumeRequest(gh, _TEST_SPEC, issue, state, "go"))

        self.assertEqual(run_recorder.calls, [_POISONED_SESSION, None])
        # Both the poisoned resume and the fresh retry burned a real exit,
        # each accounted under its own receipt as it returned.
        self.assertEqual(
            (accounted(gh.pinned_data(_RESUME_ISSUE_NUMBER)), accounted(state.state_data)),
            ((2, 2), (2, 2)),
        )

    def test_unresolved_accounting_holds_the_retry(self) -> None:
        # The poisoned exit's accounting landed and its response was lost:
        # until a later reading says it landed, nothing that depends on it
        # follows -- no fresh retry is spawned, the resume answers held, and
        # the state the caller would write is withheld.
        gh, issue, state = self._poisoned()
        gh.pinned_failures.lost.add(_RESUME_ISSUE_NUMBER)
        run_recorder = _PoisonedThenFreshRun()

        with patch.object(
            _worktree_creation, "_ensure_worktree", _fake_worktree,
        ), patch.object(_agent_runner, "run_agent", run_recorder):
            resumed = _resume._resume_dev_with_text(
                _resume_request._DevResumeRequest(gh, _TEST_SPEC, issue, state, "go"),
            )

        self.assertEqual(run_recorder.calls, [_POISONED_SESSION])
        self.assertTrue(resumed[1].unaccounted)
        self.assertEqual((resumed[2], state.withheld), (True, True))
        self.assertEqual(accounted(gh.pinned_data(_RESUME_ISSUE_NUMBER)), (1, 1))

    def _seeded(self) -> tuple:
        """An issue resolving a conflict, on a client that holds it."""
        gh = FakeGitHubClient()
        issue = make_issue(_RESUME_ISSUE_NUMBER, label="workflow:resolving_conflict")
        gh.add_issue(issue)
        return gh, issue

    def _poisoned(self) -> tuple:
        """An issue whose pinned developer session is one the backend lost, and the state read off it."""
        gh, issue = self._seeded()
        gh.seed_state(
            _RESUME_ISSUE_NUMBER,
            dev_agent=_BACKEND_CLAUDE,
            dev_session_id=_POISONED_SESSION,
            silent_park_count=0,
        )
        return gh, issue, gh.read_pinned_state(issue)


class ReviewerRunUsageAccumulationTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A validating reviewer run's exit is counted once, as it returns, and
    the approval handoff's writes behind it keep that count; an interrupted
    reviewer's exit alone is counted."""

    def test_reviewer_run_persists_one_run(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(_REVIEWER_ISSUE_NUMBER, label="workflow:validating")
        gh.add_issue(issue)
        gh.seed_state(
            _REVIEWER_ISSUE_NUMBER,
            pr_number=_REVIEWER_ISSUE_NUMBER,
            branch="orchestrator/chippingway__chipping-orchestrator/issue-32",
            dev_agent=_BACKEND_CLAUDE,
            dev_session_id="dev-sess",
            review_round=0,
        )
        _open_pr_for(
            gh, issue_number=_REVIEWER_ISSUE_NUMBER, pr_number=_REVIEWER_ISSUE_NUMBER,
        )

        with patch.object(config, "REVIEW_AGENT", _BACKEND_CODEX):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(
                    session_id="rev-sess",
                    last_message=REVIEW_APPROVED_MESSAGE,
                ),
            )

        state = gh.pinned_data(_REVIEWER_ISSUE_NUMBER)
        self.assertEqual(accounted(state), (1, 1))
        self.assertEqual(state[_TOKENS_KEY], 0)
        self.assertEqual(state[_COST_SOURCES_KEY], [_COST_SOURCE_NO_USAGE])

    def test_interrupted_review_is_accounted_alone(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            _INTERRUPTED_REVIEWER_ISSUE_NUMBER,
            label="workflow:validating",
        )
        gh.add_issue(issue)
        gh.seed_state(
            _INTERRUPTED_REVIEWER_ISSUE_NUMBER,
            pr_number=_INTERRUPTED_REVIEWER_ISSUE_NUMBER,
            branch="orchestrator/chippingway__chipping-orchestrator/issue-33",
            dev_agent=_BACKEND_CLAUDE,
            dev_session_id="dev-sess",
            review_round=0,
            # Seed the drift baseline so `_detect_user_content_change` does not
            # itself write pinned state on first encounter -- this test asserts
            # the handler writes nothing of its own once the reviewer run is
            # interrupted.
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        _open_pr_for(
            gh, issue_number=_INTERRUPTED_REVIEWER_ISSUE_NUMBER, pr_number=_INTERRUPTED_REVIEWER_ISSUE_NUMBER,
        )
        before = gh.pinned_data(_INTERRUPTED_REVIEWER_ISSUE_NUMBER)

        with patch.object(config, "REVIEW_AGENT", _BACKEND_CODEX):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(
                    session_id="", last_message="", exit_code=1,
                    interrupted=True,
                ),
            )

        # A shutdown-killed reviewer returns before its return is written, so
        # no `reviewer_failed` park reaches GitHub; beside the launch's own
        # record, the exit it was is counted once, as it returned.
        state = gh.pinned_data(_INTERRUPTED_REVIEWER_ISSUE_NUMBER)
        assert_only_accounted(self, before, state, beside=REVIEWER_LAUNCH_KEYS)
        self.assertNotEqual(state.get("park_reason"), "reviewer_failed")
        self.assertFalse(state.get("awaiting_human"))


if __name__ == "__main__":
    unittest.main()
