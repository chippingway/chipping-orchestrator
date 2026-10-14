# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, clean-process import, and surface checks for the service package."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from tests.support.import_probes import CONFIGURATION_READS, probe_import

_ORCHESTRATOR = "orchestrator"

_PACKAGE = f"{_ORCHESTRATOR}.service"

_CHECKOUTS = "checkouts"

_VALIDATION = "validation"

_TEMPLATES = "templates"

_PATHS = "paths"

_REMOTE_URLS = "remote_urls"

_REPOS_ENTRY = "repos_entry"

_CLONE_DEFAULTS = "clone_defaults"

_DOTENV_TEXT = "dotenv_text"

_PRIVATE_FILES = "private_files"

_CONFIGURE = "configure"

_TOKEN_PROBE = "token_probe"

_TOKEN_PROMPT = "token_prompt"

_TOKENS = "tokens"

# What `configure` composes: every setup leaf it writes the `.env` through.
_CONFIGURE_CHAIN = (
    _CHECKOUTS,
    _CLONE_DEFAULTS,
    _DOTENV_TEXT,
    _PATHS,
    _PRIVATE_FILES,
    _REMOTE_URLS,
    _REPOS_ENTRY,
    _TEMPLATES,
    _VALIDATION,
)

# What `set-token` composes: the repository validator, the hidden prompt, the
# GitHub probe, and the private file writer it keeps the token through.
_TOKENS_CHAIN = (
    _CHECKOUTS,
    _PRIVATE_FILES,
    _TOKEN_PROBE,
    _TOKEN_PROMPT,
    _VALIDATION,
)

# Each owner, and the owners beside it that importing it loads too. Only the
# setup's own leaves read each other: the checkout check under the layout and
# the clone validator, the validator's refusal under the entry it writes and
# the `.env` lines, all of them under the clone's derived entry, every leaf
# under `configure` or `tokens`, and both of those under the command line
# above them.
_OWNERS = MappingProxyType({
    _TEMPLATES: (),
    _CHECKOUTS: (),
    _PATHS: (_CHECKOUTS,),
    _VALIDATION: (_CHECKOUTS,),
    _REMOTE_URLS: (),
    _REPOS_ENTRY: (_CHECKOUTS, _VALIDATION),
    _CLONE_DEFAULTS: (_CHECKOUTS, _REMOTE_URLS, _REPOS_ENTRY, _VALIDATION),
    _DOTENV_TEXT: (_CHECKOUTS, _VALIDATION),
    _PRIVATE_FILES: (),
    _CONFIGURE: _CONFIGURE_CHAIN,
    _TOKEN_PROBE: (),
    _TOKEN_PROMPT: (),
    _TOKENS: _TOKENS_CHAIN,
    "commands": (*_CONFIGURE_CHAIN, _CONFIGURE, *_TOKENS_CHAIN, _TOKENS),
})

# The declared inventory: the owners above, and the two templates `templates`
# reads as package data. A new file here is a deliberate edit and an entry in
# the module map, which is what the inventory check compares the directory
# against -- and a second copy of a template beside these would be one
# nothing reads.
_OWNER_FILES = tuple(f"{owner}.py" for owner in _OWNERS)

_PACKAGE_DATA = (".env.example", ".env.example.advanced")

# What a fresh import of each module may plant under the package: its own
# chain and nothing besides. `orchestrator.config` above all stays out, since
# importing it resolves the settings and an installed package with no `REPOS`
# exits there -- the state a first setup starts in -- and so does the GitHub
# client, which reads its token through it. The configuration reads
# `checkouts` and `paths` back, which is what these exact chains make safe.
_IMPORT_CHAINS = (
    (_PACKAGE, frozenset((_ORCHESTRATOR, _PACKAGE))),
    *(
        (
            f"{_PACKAGE}.{owner}",
            frozenset((
                _ORCHESTRATOR,
                _PACKAGE,
                *(f"{_PACKAGE}.{loaded}" for loaded in (owner, *beside)),
            )),
        )
        for owner, beside in _OWNERS.items()
    ),
)

_RESOLVER_HOOKS = ("__dir__", "__getattr__")


class ServiceInventoryTest(unittest.TestCase):
    """The declared owners and package data are the files on disk."""

    def test_declared_files_are_the_ones_on_disk(self) -> None:
        directory = Path(import_module(_PACKAGE).__file__).parent
        found = tuple(sorted(
            path.name
            for path in directory.iterdir()
            if path.is_file() and path.name != "__init__.py"
        ))
        self.assertEqual(found, tuple(sorted((*_OWNER_FILES, *_PACKAGE_DATA))))


class CleanProcessImportTest(unittest.TestCase):
    """Each module imports alone and loads no configuration.

    A fresh interpreter per module is the only place a stray import shows: a
    suite that has already imported the settings would resolve them off what
    that left behind, and a template read, a field check, or a derived entry
    would look free when it is not.
    """

    def test_each_module_costs_only_its_own_chain(self) -> None:
        for module, chain in _IMPORT_CHAINS:
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)
                self.assertEqual(probe.orchestrator_modules, chain)


class ConfigurationReadsTest(unittest.TestCase):
    """Importing the configuration plants the install facts and no other owner.

    The configuration reads `checkouts` and `paths` back from below, and the
    guards that let a module pay for the settings admit exactly the set
    declared beside the probes; this is where that set is held to what an
    import of the configuration really loads.
    """

    def test_config_plants_only_the_install_facts(self) -> None:
        probe = probe_import(f"{_ORCHESTRATOR}.config")
        self.assertEqual(probe.returncode, 0, msg=probe.stderr)
        planted = frozenset(
            name for name in probe.orchestrator_modules
            if name == _PACKAGE or name.startswith(f"{_PACKAGE}.")
        )
        self.assertEqual(planted, CONFIGURATION_READS)


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a marker: callers name the owner they need."""

    def test_initializer_publishes_nothing(self) -> None:
        initializer = import_module(_PACKAGE)
        for declared in ("__all__", *_RESOLVER_HOOKS):
            with self.subTest(declared=declared):
                self.assertNotIn(declared, initializer.__dict__)
        for name, bound in initializer.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(getattr(bound, "__name__", ""), f"{_PACKAGE}.{name}")


if __name__ == "__main__":
    unittest.main()
