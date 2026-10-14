# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A token typed at a terminal that does not show it, or not read at all.

``getpass`` turns the terminal's echo off before it reads a line. Where it
cannot -- no controlling terminal it can open, or one whose settings it cannot
change -- it warns with ``GetPassWarning`` and then reads the line anyway, with
echo on, so the token would appear on the screen and in any recording of it.
Here that warning is the refusal: it is raised as an error at the moment it is
issued, which is before the fallback reads anything, and ``ask_hidden``
reports it as ``EchoError``.

``set-token`` asks for its token this way, and so can any setup that asks for
one at a prompt. Nothing here imports from the package.
"""
from __future__ import annotations

import getpass
import warnings


class EchoError(OSError):
    """A terminal that would show the token as it is typed; nothing was read.

    An ``OSError``, like any other terminal that cannot do what it was asked,
    so a caller already reporting a failed read reports this one with it.
    """


def ask_hidden(prompt: str) -> str:
    """The line typed after ``prompt`` with echo off, or ``EchoError``.

    Ctrl+D raises ``EOFError`` and Ctrl+C ``KeyboardInterrupt``, as
    ``getpass`` does, so the caller decides what an abandoned prompt means.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise EchoError(
                "this terminal cannot hide the token as it is typed, so none was "
                "read; pipe the token in or redirect a file in instead",
            ) from None
