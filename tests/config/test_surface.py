# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Configuration package public surface, and the private API beside it."""

import importlib
import unittest
from types import MappingProxyType

from orchestrator.config import credentials, environment

_CONFIG_MODULE = "orchestrator.config"
_HERMETIC = MappingProxyType(
    {
        "ORCHESTRATOR_SKIP_DOTENV": "1",
        "ORCHESTRATOR_TOKEN_FILE": "/tmp/chipping-orchestrator-token-missing",
    }
)
# The internal resolver key backing the private `_REPO_SPECS`; the public
# surface exposes the `default_repo_specs` accessor instead.
_INTERNAL_KEYS = frozenset(("REPO_SPECS",))
_API_NAMES = frozenset(("RepoSpec", "default_repo_specs", "REPO_ROOT"))
# The package's own API: the diagnostics funnel its leaves are constructed
# with, the agent-spec parse bound onto that funnel, and the token resolution
# reached beside the settings here. Private on purpose, so deliberately
# excluded from `__all__`.
_INTERNAL_NAMES = (
    "_config_error",
    "_config_warning",
    "_parse_agent_spec",
    "_resolve_github_token",
)
# Names this module must not bind: the `.env` load, the verify-command parse,
# and the dotenv quote stripping each answer on the leaf that defines them, and
# a binding here would be a second site in front of that leaf -- one free to
# drift from it and invisible to a patch aimed at it. They are pinned as absent
# because nothing else would see one appear: the repository-wide surface check
# reads a package's public names, and a private name is outside it by design.
_LEAF_ONLY_NAMES = (
    "_load_dotenv",
    "_parse_verify_commands",
    "_strip_dotenv_quotes",
)


def _resolver_settings():
    config = importlib.import_module(_CONFIG_MODULE)
    resolved = environment._SettingsResolver(
        dict(_HERMETIC),
        config.REPO_ROOT,
        config._config_error,
        config._config_warning,
    ).resolve()
    return {key for key in resolved if key not in _INTERNAL_KEYS}


class PublicSurfaceTest(unittest.TestCase):
    """`orchestrator.config.__all__` is the exact public surface: the
    `RepoSpec` / `default_repo_specs` / `REPO_ROOT` package API plus every
    resolver-produced setting, with the internal `REPO_SPECS` list hidden
    behind the `default_repo_specs` accessor.
    """

    def setUp(self) -> None:
        self._config = importlib.import_module(_CONFIG_MODULE)

    def test_all_has_no_duplicates(self) -> None:
        exported = self._config.__all__
        self.assertEqual(len(exported), len(set(exported)))

    def test_all_matches_resolver_surface_plus_api(self) -> None:
        self.assertEqual(
            set(self._config.__all__),
            _resolver_settings() | _API_NAMES,
        )

    def test_all_names_are_resolvable_attributes(self) -> None:
        for name in self._config.__all__:
            self.assertTrue(hasattr(self._config, name), name)

    def test_repo_root_is_exported(self) -> None:
        # `runtime.self_update` reads `config.REPO_ROOT` at runtime, so it has
        # to stay part of the exported surface.
        self.assertIn("REPO_ROOT", self._config.__all__)

    def test_all_lists_only_public_names(self) -> None:
        # `from orchestrator.config import *` exports exactly `__all__`, so a
        # surface free of private names keeps the internal API off it.
        private = [name for name in self._config.__all__ if name.startswith("_")]
        self.assertEqual(private, [])


class InternalApiTest(unittest.TestCase):
    """The four private names are the package's own API, and stay private.

    Each has a caller that reaches it here rather than on the leaf beneath:
    the resolver and its leaves are constructed with the diagnostics funnel,
    the workflow stages re-parse a stored agent spec through the binding over
    it, and the GitHub client and the push path resolve a repo's token beside
    the settings this module holds. None is published: `__all__` is what an
    outside caller is invited onto, and this is not that.
    """

    def setUp(self) -> None:
        self._config = importlib.import_module(_CONFIG_MODULE)

    def test_internal_names_stay_unexported(self) -> None:
        for name in _INTERNAL_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(self._config, name))
                self.assertNotIn(name, self._config.__all__)

    def test_a_leaf_only_name_is_not_bound_here(self) -> None:
        # The dotenv and verify-command helpers belong to `_dotenv` and
        # `environment`, and a caller names the leaf. Binding one on the
        # package would give the same helper two import sites and two patch
        # targets, which is the ambiguity the leaves exist to avoid.
        for name in _LEAF_ONLY_NAMES:
            with self.subTest(name=name):
                self.assertFalse(hasattr(self._config, name))

    def test_the_token_resolver_is_the_owner_s(self) -> None:
        # Bound once at import to the `credentials` function, so a patch here
        # is what both callers resolve a token through.
        self.assertIs(
            self._config._resolve_github_token, credentials.resolve_github_token,
        )

    def test_parse_agent_spec_binds_the_error_funnel(self) -> None:
        self.assertEqual(
            self._config._parse_agent_spec("DEV_AGENT", "codex -m gpt-5.5"),
            ("codex", ("-m", "gpt-5.5")),
        )
