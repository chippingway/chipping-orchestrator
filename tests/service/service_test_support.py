# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the service tests share: reading back the words a setup refuses with."""
from __future__ import annotations

from collections.abc import Callable

from orchestrator.service.validation import FieldError


def refusal(validator: Callable[..., object], *answer: object, **chosen: object) -> str:
    """The diagnostic ``validator`` refuses ``answer`` with.

    An answer it accepts fails the test that expected a refusal, naming what
    was accepted.
    """
    try:
        validator(*answer, **chosen)
    except FieldError as refused:
        return str(refused)
    raise AssertionError(f"{validator.__qualname__} accepted {answer!r} {chosen!r}")
