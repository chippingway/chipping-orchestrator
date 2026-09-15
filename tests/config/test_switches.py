# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused configuration behavior tests."""

import itertools
import unittest

from tests.config import config_reload_helpers as _reload, config_test_values as _config_cases

# Default-on boolean switches, each resolved onto the config attribute its
# environment key names.
_BOOLEAN_SWITCHES = (
    _config_cases._DECOMPOSE_ENV,
    _config_cases._EXPOSE_REPOS_ENV,
    _config_cases._PR_REF_IN_SUBJECT_ENV,
)
_TRUTHY_SPELLINGS = ("on", "ON", " on ", _config_cases._ENABLED_ENV, "true", "True", "yes")
# Explicit off, the other falsy spellings, and an unrecognized value.
_DISABLING_SPELLINGS = (_config_cases._OFF, _config_cases._DISABLED_ENV, "false", "no", "enabled")


class BooleanSwitchConfigTest(unittest.TestCase):
    """The DECOMPOSE, EXPOSE_TRACKED_REPOS, and PR_REF_IN_SUBJECT switches
    default on and share SQUASH_ON_APPROVAL's strict parser: truthy spellings
    keep a switch on, and explicit off, the other falsy spellings, and any
    unrecognized value disable it, so a typo cannot silently flip the
    operator's intent.
    """

    def test_default_is_on(self) -> None:
        config = _reload.load_config()
        for switch in _BOOLEAN_SWITCHES:
            with self.subTest(switch=switch):
                self.assertTrue(getattr(config, switch))

    def test_truthy_spellings_keep_on(self) -> None:
        for switch, spelling in itertools.product(_BOOLEAN_SWITCHES, _TRUTHY_SPELLINGS):
            with self.subTest(switch=switch, value=spelling):
                config = _reload.load_config({switch: spelling})
                self.assertTrue(getattr(config, switch))

    def test_off_falsy_and_unrecognized_disable(self) -> None:
        for switch, spelling in itertools.product(_BOOLEAN_SWITCHES, _DISABLING_SPELLINGS):
            with self.subTest(switch=switch, value=spelling):
                config = _reload.load_config({switch: spelling})
                self.assertFalse(getattr(config, switch))


class InReviewDebounceConfigTest(unittest.TestCase):
    def test_default_is_ten_minutes(self) -> None:
        config = _reload.load_config()
        self.assertEqual(
            config.IN_REVIEW_DEBOUNCE_SECONDS,
            _config_cases._DEFAULT_DEBOUNCE_SECONDS,
        )

    def test_env_override(self) -> None:
        config = _reload.load_config(
            {
                "IN_REVIEW_DEBOUNCE_SECONDS": str(_config_cases._OVERRIDE_DEBOUNCE_SECONDS),
            }
        )
        self.assertEqual(
            config.IN_REVIEW_DEBOUNCE_SECONDS,
            _config_cases._OVERRIDE_DEBOUNCE_SECONDS,
        )


class MaxRetriesPerDayConfigTest(unittest.TestCase):
    def test_default_is_three(self) -> None:
        config = _reload.load_config()
        self.assertEqual(config.MAX_RETRIES_PER_DAY, 3)

    def test_env_override(self) -> None:
        config = _reload.load_config({"MAX_RETRIES_PER_DAY": "7"})
        self.assertEqual(config.MAX_RETRIES_PER_DAY, 7)

    def test_zero_means_unbounded(self) -> None:
        config = _reload.load_config({"MAX_RETRIES_PER_DAY": _config_cases._DISABLED_ENV})
        self.assertEqual(config.MAX_RETRIES_PER_DAY, 0)


class AllowedIssueAuthorsConfigTest(unittest.TestCase):
    """Author-allowlist for unlabeled-issue pickup. Empty (default) disables
    the filter so existing single-user setups keep working; a populated list
    guards against random users on public repos triggering agent runs."""

    def test_default_is_empty_tuple(self) -> None:
        config = _reload.load_config()
        self.assertEqual(config.ALLOWED_ISSUE_AUTHORS, ())

    def test_parses_comma_separated(self) -> None:
        config = _reload.load_config({"ALLOWED_ISSUE_AUTHORS": "alice,bob"})
        self.assertEqual(config.ALLOWED_ISSUE_AUTHORS, (_config_cases._ALICE, _config_cases._BOB))

    def test_strips_spaces_at_signs_and_duplicates(self) -> None:
        config = _reload.load_config({"ALLOWED_ISSUE_AUTHORS": " @alice, bob, ,alice,@carol "})
        self.assertEqual(config.ALLOWED_ISSUE_AUTHORS, (_config_cases._ALICE, _config_cases._BOB, "carol"))


class MaxConflictRoundsConfigTest(unittest.TestCase):
    """`MAX_CONFLICT_ROUNDS` parses identically to `MAX_REVIEW_ROUNDS`:
    integer, defaults to 3, env override wins.
    """

    def test_default_is_three(self) -> None:
        config = _reload.load_config()
        self.assertEqual(config.MAX_CONFLICT_ROUNDS, 3)

    def test_env_override(self) -> None:
        config = _reload.load_config({"MAX_CONFLICT_ROUNDS": "7"})
        self.assertEqual(config.MAX_CONFLICT_ROUNDS, 7)


class MaxAddedLinesConfigTest(unittest.TestCase):
    """The size ceiling a committed candidate publishes under.

    A positive integer validated at import like the parallelism caps, because
    zero or a negative one would call every candidate oversized and route a
    whole repository into adjudication rather than merely mis-sizing one issue.
    """

    def test_default_is_four_thousand(self) -> None:
        config = _reload.load_config()
        self.assertEqual(
            config.MAX_ADDED_LINES, _config_cases._DEFAULT_MAX_ADDED_LINES,
        )

    def test_env_override(self) -> None:
        config = _reload.load_config(
            {
                _config_cases._MAX_ADDED_LINES_ENV: str(
                    _config_cases._OVERRIDE_MAX_ADDED_LINES,
                ),
            }
        )
        self.assertEqual(
            config.MAX_ADDED_LINES, _config_cases._OVERRIDE_MAX_ADDED_LINES,
        )

    def test_blank_value_keeps_the_default(self) -> None:
        # An operator who commented the value out but left the key behind gets
        # the shipped ceiling rather than an abort.
        config = _reload.load_config({_config_cases._MAX_ADDED_LINES_ENV: "  "})
        self.assertEqual(
            config.MAX_ADDED_LINES, _config_cases._DEFAULT_MAX_ADDED_LINES,
        )

    def test_an_invalid_ceiling_aborts_at_import(self) -> None:
        for spelling in ("plenty", _config_cases._DISABLED_ENV, "-1", "4_000.5"):
            with self.subTest(value=spelling):
                error_message = _reload.config_error_message(
                    {_config_cases._MAX_ADDED_LINES_ENV: spelling},
                )
                self.assertIn(
                    _config_cases._MAX_ADDED_LINES_ENV, error_message,
                )
                self.assertIn(spelling, error_message)
