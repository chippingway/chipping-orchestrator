# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Configuration settings ownership and the package's import boundary."""

import importlib
import os
import subprocess
import sys
import unittest
from types import MappingProxyType

from orchestrator.config import credentials, environment

_CONFIG_MODULE = "orchestrator.config.settings"
_HERMETIC = MappingProxyType(
    {
        "ORCHESTRATOR_SKIP_DOTENV": "1",
        "ORCHESTRATOR_TOKEN_FILE": "/tmp/chipping-orchestrator-token-missing",
    }
)
# The resolver's repository list stays behind the settings accessor.
_INTERNAL_KEYS = frozenset(("REPO_SPECS",))
_INTERNAL_NAMES = (
    "_config_error",
    "_config_warning",
    "_parse_agent_spec",
)
_LEAF_ONLY_NAMES = (
    "_load_dotenv",
    "_parse_verify_commands",
    "_strip_dotenv_quotes",
    "_resolve_github_token",
    "RepoSpec",
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
    """Resolved settings live on their owner without loading via the package."""

    def setUp(self) -> None:
        self._config = importlib.import_module(_CONFIG_MODULE)

    def test_package_declares_no_settings(self) -> None:
        package = importlib.import_module("orchestrator.config")
        self.assertNotIn("__all__", package.__dict__)
        for name in (*_resolver_settings(), "REPO_ROOT", "default_repo_specs"):
            with self.subTest(name=name):
                self.assertNotIn(name, package.__dict__)

    def test_values_match_the_resolver_keys(self) -> None:
        bound = {
            name for name in self._config.__dict__
            if name.isupper() and not name.startswith("_")
        }
        self.assertEqual(bound, _resolver_settings() | {"REPO_ROOT"})

    def test_accessors_belong_to_settings(self) -> None:
        for name in (*_INTERNAL_NAMES, "default_repo_specs"):
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(self._config, name).__module__, _CONFIG_MODULE,
                )

    def test_repo_root_names_the_checkout(self) -> None:
        self.assertTrue((self._config.REPO_ROOT / "pyproject.toml").is_file())
        self.assertTrue((self._config.REPO_ROOT / "orchestrator").is_dir())

    def test_package_import_resolves_no_settings(self) -> None:
        # Invalid settings cannot prevent a caller from importing a config
        # model or parser: only importing the settings owner resolves them.
        command = (
            "import sys; import orchestrator.config; "
            "print(' '.join(sorted(name for name in sys.modules "
            "if name.startswith('orchestrator'))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            env={**os.environ, **_HERMETIC, "DEV_AGENT": "invalid-agent"},
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(completed.stdout.strip(), "orchestrator orchestrator.config")


class InternalApiTest(unittest.TestCase):
    """The settings accessors keep one diagnostic funnel and no leaf aliases."""

    def setUp(self) -> None:
        self._config = importlib.import_module(_CONFIG_MODULE)

    def test_internal_names_are_settings_accessors(self) -> None:
        for name in _INTERNAL_NAMES:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(self._config, name)))
        self.assertNotIn("__all__", self._config.__dict__)

    def test_a_leaf_only_name_is_not_bound_here(self) -> None:
        for name in _LEAF_ONLY_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(name, self._config.__dict__)

    def test_token_resolution_belongs_to_credentials(self) -> None:
        self.assertEqual(
            credentials.resolve_github_token.__module__, credentials.__name__,
        )

    def test_parse_agent_spec_binds_the_error_funnel(self) -> None:
        self.assertEqual(
            self._config._parse_agent_spec("DEV_AGENT", "codex -m gpt-5.5"),
            ("codex", ("-m", "gpt-5.5")),
        )
