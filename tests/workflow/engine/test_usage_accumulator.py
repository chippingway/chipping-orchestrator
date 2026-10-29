# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Per-issue cumulative usage meter: what one accounted run adds to the counters,
the `_format_issue_usage_verdict` reader that renders the terminal receipt line,
and the tracked spawn that accounts every actual exit through the checkpoint as
it returns. Covers the token formula (codex `cached_tokens` excluded), the cost
/ cost-source aggregates, the `(est.)` / `unknown` verdict slots, each exit
counted once whatever its stage makes of it -- an interrupted one, each attempt
of a poisoned session's retry, and the disposition's own write behind it -- and
the hold an accounting left unresolved puts on the retry behind it. A result
with no process or no parsed usage owes nothing."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
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


_BACKEND_CLAUDE = "claude"
_BACKEND_CODEX = "codex"
_COST_SOURCE_NO_USAGE = "no-usage"
_ESTIMATED_RUN_COST = 0.75
_COST_SOURCE_ESTIMATED = "estimated"
_COST_SOURCE_REPORTED = "reported"
_COST_SOURCE_UNKNOWN = "unknown-price"
_RUNS_KEY = "issue_agent_runs"
_TOKENS_KEY = "issue_total_tokens"
_COST_KEY = "issue_total_cost_usd"
_COST_SOURCES_KEY = "issue_cost_sources"
_RESUME_ISSUE_NUMBER = 940
_POISONED_SESSION = "poisoned-sess"
_DEVELOPER_ISSUE_NUMBER = 30
_INTERRUPTED_DEVELOPER_ISSUE_NUMBER = 31
_REVIEWER_ISSUE_NUMBER = 32
_INTERRUPTED_REVIEWER_ISSUE_NUMBER = 33
_CLAUDE_OUTPUT_TOKENS = 50
_CLAUDE_CACHE_READ_TOKENS = 30
_CLAUDE_CACHE_WRITE_TOKENS = 20
_CLAUDE_RUN_COST = 1.5
_CLAUDE_TOTAL_TOKENS = 200
_CODEX_OUTPUT_TOKENS = 40
_CODEX_TOTAL_TOKENS = 140
_MULTI_RUN_COST = 2.0
_MULTI_RUN_TOKENS = 22
_MULTI_RUN_TOTAL_COST = 3.0


def _usage(**overrides) -> UsageMetrics:
    base = {"backend": _BACKEND_CLAUDE, "cost_source": _COST_SOURCE_ESTIMATED}
    base.update(overrides)
    return UsageMetrics(**base)


# What an issue has counted before a run is accounted: nothing, and a meter
# another priced run already moved.
_PRIOR_METERS = (
    {},
    {_RUNS_KEY: 2, _TOKENS_KEY: 9, _COST_KEY: 1.0, _COST_SOURCES_KEY: [_COST_SOURCE_REPORTED]},
)

# Each meaning a parsed run's usage carries -- reported, estimated, unpriced,
# and `no-usage` costs, and codex's cached input inside its prompt -- and what
# it adds: its tokens, its cost (None for none), and its tag.
_PARSED_MEANINGS = (
    (
        _usage(cost_usd=_CLAUDE_RUN_COST, cost_source=_COST_SOURCE_REPORTED, input_tokens=100),
        (100, _CLAUDE_RUN_COST, _COST_SOURCE_REPORTED),
    ),
    (
        _usage(cost_usd=_ESTIMATED_RUN_COST, output_tokens=_CLAUDE_OUTPUT_TOKENS),
        (_CLAUDE_OUTPUT_TOKENS, _ESTIMATED_RUN_COST, _COST_SOURCE_ESTIMATED),
    ),
    (
        _usage(cost_source=_COST_SOURCE_UNKNOWN, cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS),
        (_CLAUDE_CACHE_READ_TOKENS, None, _COST_SOURCE_UNKNOWN),
    ),
    (_usage(cost_source=_COST_SOURCE_NO_USAGE), (0, None, _COST_SOURCE_NO_USAGE)),
    (
        _usage(backend=_BACKEND_CODEX, cost_source=_COST_SOURCE_REPORTED, input_tokens=100, cached_tokens=60),
        (100, None, _COST_SOURCE_REPORTED),
    ),
)


# Results the checkpoint owes nothing for: a parse that failed, and metrics
# supplied beside a result no process produced.
_UNACCOUNTED = (
    {"usage": None},
    {"invoked": False},
)


# What a fold is handed beyond any total's spelling, the counter it lands on,
# and the value the comment carries there: a negative cost and token count, and
# a cost whose sum is past what a float holds.
_NEGATIVE = -1
_HUGE_COST = 1e308
_UNSPELLED_FOLDS = (
    (_usage(cost_usd=_NEGATIVE), _COST_KEY, _commit_models.ABSENT),
    (_usage(output_tokens=_NEGATIVE), _TOKENS_KEY, 1),
    (_usage(cost_usd=_HUGE_COST), _COST_KEY, _HUGE_COST),
)


def _resume_seed():
    gh = FakeGitHubClient()
    issue = make_issue(_RESUME_ISSUE_NUMBER, label="workflow:resolving_conflict")
    gh.add_issue(issue)
    return gh, issue


class AccountedRunArithmeticTest(unittest.TestCase):
    """What one accounted run adds to the counters: token and cost math, and the cost-source aggregate."""

    def test_one_run_sums_and_records_source(self) -> None:
        world = _accounting.seeded()

        world.ran(usage=_usage(
            input_tokens=100,
            output_tokens=_CLAUDE_OUTPUT_TOKENS,
            cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS,
            cache_write_tokens=_CLAUDE_CACHE_WRITE_TOKENS,
            cost_usd=_CLAUDE_RUN_COST,
            cost_source=_COST_SOURCE_ESTIMATED,
        ))

        self.assertEqual(
            _accounting.counted(world.record()),
            (1, _CLAUDE_TOTAL_TOKENS, _CLAUDE_RUN_COST, [_COST_SOURCE_ESTIMATED]),
        )

    def test_codex_cached_tokens_excluded_from_total(self) -> None:
        # codex reports `input_tokens` as the whole prompt and `cached_tokens`
        # as the portion of it served from cache; summing the latter would
        # double-count part of the input.
        world = _accounting.seeded()

        world.ran(usage=_usage(
            backend=_BACKEND_CODEX,
            input_tokens=100,
            output_tokens=_CODEX_OUTPUT_TOKENS,
            cached_tokens=60,
            cost_usd=0.5,
            cost_source=_COST_SOURCE_REPORTED,
        ))

        self.assertEqual(world.record()[_TOKENS_KEY], _CODEX_TOTAL_TOKENS)

    def test_runs_dedupe_sources_and_none_cost(self) -> None:
        # A priced run, an unpriced run (cost None), and a second priced run
        # sharing the first's source, each under its own charge.
        world = _accounting.seeded()
        for ordinal, parsed in enumerate((
            _usage(input_tokens=10, cost_usd=1.0, cost_source=_COST_SOURCE_ESTIMATED),
            _usage(input_tokens=5, cost_usd=None, cost_source=_COST_SOURCE_UNKNOWN),
            _usage(output_tokens=7, cost_usd=_MULTI_RUN_COST, cost_source=_COST_SOURCE_ESTIMATED),
        ), start=1):
            world.ran(ordinal, usage=parsed)

        # The None-cost run adds nothing to the dollar total, and the tags are
        # the distinct sources, sorted, a terminal verdict reads (est.) and
        # unknown off.
        self.assertEqual(
            _accounting.counted(world.record()),
            (3, _MULTI_RUN_TOKENS, _MULTI_RUN_TOTAL_COST, [_COST_SOURCE_ESTIMATED, _COST_SOURCE_UNKNOWN]),
        )

    def test_each_parsed_meaning_lands_over_any_meter(self) -> None:
        # Over an empty meter and a moved one, each parsed meaning adds one
        # exit, its tokens, its cost where it has one -- a `None` cost leaving
        # the total as it stands -- and its tag.
        for prior in _PRIOR_METERS:
            for parsed, added in _PARSED_MEANINGS:
                with self.subTest(prior=prior, cost_source=parsed.cost_source):
                    world = _accounting.seeded(**prior)

                    world.ran(usage=parsed)

                    expected = self._added(prior, added)
                    self.assertEqual(_accounting.counted(world.record()), expected)

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
        # candidate carries a counter its own read-back would refuse.
        for parsed, counter, carried in _UNSPELLED_FOLDS:
            with self.subTest(counter=counter, carried=carried):
                fold = _usage_counters.usage_folds(parsed)[counter]

                self.assertIs(fold(carried, carried, carried), _commit_models.CONFLICT)

    def _added(self, prior: dict, added: tuple) -> tuple:
        """The meter `prior` carries with one run adding `added`'s tokens, cost, and tag."""
        tokens, cost, tag = added
        cost_total = prior.get(_COST_KEY)
        if cost is not None:
            cost_total = (cost_total or 0) + cost
        return (
            prior.get(_RUNS_KEY, 0) + 1,
            prior.get(_TOKENS_KEY, 0) + tokens,
            cost_total,
            sorted({*prior.get(_COST_SOURCES_KEY, []), tag}),
        )


class FormatIssueUsageVerdictTest(unittest.TestCase):
    """The pure reader: `_format_issue_usage_verdict` renders the counters
    into the terminal receipt line, marking `(est.)` / `unknown` off the
    cost-source set and collapsing to None when nothing was counted."""

    def test_zero_runs_returns_none(self) -> None:
        # An empty state and an explicit zero both skip the line so a
        # terminal with no counted run posts no receipt.
        self.assertIsNone(_issue_usage._format_issue_usage_verdict(PinnedState()))
        self.assertIsNone(
            _issue_usage._format_issue_usage_verdict(
                PinnedState(state_data={_RUNS_KEY: 0}),
            )
        )

    def test_verdict_slots_by_cost_source(self) -> None:
        cases = [
            # (sources, cost_usd) -> expected trailing cost slot
            ([_COST_SOURCE_REPORTED], 0.87, "$0.87"),
            ([_COST_SOURCE_ESTIMATED], 0.87, "$0.87 (est.)"),
            (
                [_COST_SOURCE_ESTIMATED, _COST_SOURCE_REPORTED],
                _CLAUDE_RUN_COST,
                "$1.50 (est.)",
            ),
            # An unpriced run collapses the whole figure to `unknown`, and
            # that dominates a co-present estimate (an unknown total is not
            # an estimate).
            ([_COST_SOURCE_UNKNOWN], None, "unknown"),
            ([_COST_SOURCE_ESTIMATED, _COST_SOURCE_UNKNOWN], 0.87, "unknown"),
            # A `no-usage` run priced nothing but blocks neither slot.
            ([_COST_SOURCE_NO_USAGE], None, "$0.00"),
        ]
        for sources, cost, expected_cost in cases:
            with self.subTest(sources=sources):
                verdict_data = {
                    _RUNS_KEY: 3,
                    _TOKENS_KEY: 45200,
                    _COST_SOURCES_KEY: sources,
                }
                if cost is not None:
                    verdict_data[_COST_KEY] = cost
                self.assertEqual(
                    _issue_usage._format_issue_usage_verdict(
                        PinnedState(state_data=verdict_data),
                    ),
                    f":receipt: this issue: 3 agent runs · "
                    f"45,200 tokens · {expected_cost}",
                )

    def test_tokens_are_thousands_separated(self) -> None:
        line = _issue_usage._format_issue_usage_verdict(
            PinnedState(state_data={
                _RUNS_KEY: 1,
                _TOKENS_KEY: 1234567,
                _COST_KEY: 12.3,
                _COST_SOURCES_KEY: [_COST_SOURCE_REPORTED],
            })
        )
        self.assertEqual(
            line,
            ":receipt: this issue: 1 agent runs · 1,234,567 tokens · $12.30",
        )


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
        gh, issue = _resume_seed()
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

    def _poisoned(self) -> tuple:
        """An issue whose pinned developer session is one the backend lost, and the state read off it."""
        gh, issue = _resume_seed()
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
