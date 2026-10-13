# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `.env` templates this package ships, read from its own resources.

The two files sit beside this module as package data, listed by name in the
packaging configuration so the wheel and the source distribution both carry
them even where an ignore rule would drop them from the package glob. They are
read through `importlib.resources`, which answers for an editable checkout and
an installed wheel alike, so the copy a caller gets is always the one matching
the running version.

This owner imports nothing from the package: reading a template has to work on
a host with no configuration at all, where importing `orchestrator.config`
would exit.
"""
from __future__ import annotations

from importlib import resources

BASIC_TEMPLATE = ".env.example"
ADVANCED_TEMPLATE = ".env.example.advanced"
TEMPLATES = (BASIC_TEMPLATE, ADVANCED_TEMPLATE)

_PACKAGE = "orchestrator.service"


def template_text(name: str) -> str:
    """The text of the packaged template called `name`.

    Only the two templates answer: the package's other resources are its own
    modules, and handing one back as a template would let a misspelled name
    read as a setup.
    """
    if name not in TEMPLATES:
        raise ValueError(f"no packaged template is named {name!r}; expected one of {TEMPLATES}")
    return resources.files(_PACKAGE).joinpath(name).read_text(encoding="utf-8")
