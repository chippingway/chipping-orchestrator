# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an installed orchestrator carries for setting itself up.

``templates`` reads the two ``.env`` templates that ship beside it as package
data: ``.env.example``, the basic template a setup starts from, and
``.env.example.advanced``, the optional overrides and developer settings. Both
files live in this directory and nowhere else, so every install carries the
copies that match its own version, and a source checkout reads the same files
its documentation links to and its tests parse.

Nothing here imports ``orchestrator.config``. That package resolves and
validates the settings as it is imported, and an installed package with no
``REPOS`` exits there -- which is exactly the state a first setup reads these
templates from. This initializer binds nothing, so naming the package costs no
owner beneath it.
"""
