# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A launch refusing a value systemd would read differently names it, and never quotes it, since it may be a token."""
from __future__ import annotations

from tests.service import lifecycle_test_support as _support

_SECRET = "ghp_stand-in-secret-token"
_BACKSLASH = "\\"
_TOKEN_VALUE = "the value of GITHUB_TOKEN"
_ENVIRONMENT_D = "~/.config/environment.d/50.conf"
# Each value holding the token that is refused, where it is written, and what
# the refusal names in its place.
_REFUSED = (
    (_support.OVERRIDE, f"[Service]\nEnvironment=GITHUB_TOKEN={_SECRET} OTHER=%t\n", "the value of OTHER"),
    (_support.OVERRIDE, f'[Service]\nEnvironment="GITHUB_TOKEN={_SECRET}%t"\n', _TOKEN_VALUE),
    (_support.OVERRIDE, f"[Service]\nEnvironment=GITHUB_TOKEN={_SECRET}{_BACKSLASH}n\n", _TOKEN_VALUE),
    (_support.OVERRIDE, f'[Service]\nEnvironment="GITHUB_TOKEN={_SECRET}\n', "an unterminated quote"),
    (_ENVIRONMENT_D, f'GITHUB_TOKEN="{_SECRET}\n', _TOKEN_VALUE),
    (_ENVIRONMENT_D, f'"GITHUB_TOKEN="{_SECRET}\n', "line 1 holds an unterminated quote"),
    (_ENVIRONMENT_D, f"GITHUB_TOKEN={_SECRET}${{A:-$B}}\n", _TOKEN_VALUE),
    (_ENVIRONMENT_D, f"GITHUB_TOKEN={_SECRET} {_BACKSLASH}\n", "line 1 continues"),
    (
        "~/.config/systemd/user.conf.d/50.conf",
        f"[Manager]\nDefaultEnvironment=GITHUB_TOKEN={_SECRET}%H\n",
        _TOKEN_VALUE,
    ),
)


class SecretRefusalTest(_support.LifecycleCase):
    """Each reader names the file and the variable it refuses, asking systemd nothing, and quotes no value."""

    def test_no_refusal_quotes_a_value(self) -> None:
        for located, text, named in _REFUSED:
            with self.subTest(located=located, text=text):
                refusal = self._refusal(located, text)

                self.assertIn(named, refusal)
                self.assertNotIn(_SECRET, refusal)

    def _refusal(self, located: str, text: str) -> str:
        """What a start refuses ``text`` at ``located`` with, having asked systemd nothing and named the file."""
        self.timeline.clear()
        written = self.write_drop_in(located, text)
        status, stdout, stderr = self.launched(_support.START_COMMAND)
        written.unlink()
        self.assertEqual((status, stdout, self.timeline), (1, "", []))
        self.assertIn(f"{written} ", stderr)
        return stderr
