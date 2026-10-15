# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Onboarding inside `init`: each question, its default, its retries, and what a confirmed setup writes."""
from __future__ import annotations

import stat
from contextlib import chdir

from orchestrator.service.configure import ConfigureAnswers, configure
from orchestrator.service.dotenv_text import read_setting
from orchestrator.service.validation import validate_agent, validate_branch, validate_clone, validate_logins
from tests.service import init_test_support as _init, onboarding_test_support as _support
from tests.service.service_test_support import refusal

_WELCOME = (
    "No configuration at {0}. Let's create it.\n"
    "Nothing is written until the last question; Ctrl+C leaves everything as it is.\n\n"
)
_CLONE = "[1/6] Local clone of the repository to manage"
_API_TOKEN = "[4/6] GitHub token for acme/api (input hidden): \n"
_AUTHORS = "[5/6] GitHub logins whose issues the orchestrator may act on"
_KEEP = "Keep these agents? [Y/n]: \n"
_NO_MORE = "Add another repository? [y/N]: \n"
_FOUND = "Agents: implement=claude (found)  review=codex (found)  decompose=claude (found)\n"
_CLAUDE = "claude"
_PRIVATE_FILE = 0o600


class DefaultsTest(_support.OnboardingCase):
    """From the top of a clone, Enter answers every question but the token's.

    The clone is the current directory, the repository and branch are read
    off its `origin`, the authors are the token's owner, the people to
    mention are the authors, and the agents are the template's. The `.env`
    is the one `configure` writes for that clone and those authors, and the
    token file the one `set-token` writes, each written only once the last
    answer confirms them, after which `init` installs the service.
    """

    def test_enter_takes_each_default(self) -> None:
        settings = self.home / _support.SETTINGS_FILE
        token = self.home / _support.API_TOKEN_FILE

        with chdir(self.api):
            transcript = self.onboarded("", "", "", _support.API_TOKEN, *_support.AFTER_TOKEN)

        written_before = transcript.partition(f"Wrote {settings}\n")[0]
        self.assertEqual(written_before, "".join((
            _WELCOME.format(settings),
            f"{_CLONE} [{self.api}]: \n",
            "[2/6] GitHub repository (owner/name) [acme/api]: \n",
            "[3/6] Branch pull requests target [trunk]: \n",
            _API_TOKEN,
            "      the token reaches acme/api (owner: alice)\n",
            f"{_AUTHORS} [alice]: \n",
            "[6/6] GitHub logins to mention when a human is needed [alice]: \n",
            f"\n{_FOUND}{_KEEP}{_NO_MORE}",
            f"\nWrite {token} and {settings}? [Y/n]: \n",
            f"Saved the token for acme/api to {token}\n",
        )))
        self.assertEqual(_support.read(token), f"{_support.API_TOKEN}\n")
        self.assertEqual(stat.S_IMODE(token.stat().st_mode), _PRIVATE_FILE)
        self.assertEqual(self.github.requests, [
            ("/repos/acme/api", _support.API_TOKEN),
            ("/user", _support.API_TOKEN),
        ])
        self.assertEqual(tuple(self.timeline), _init.FIRST_INSTALL)
        onboarded = settings.read_bytes()
        settings.unlink()
        configure(
            ConfigureAnswers(clone=self.api, authors=_support.AUTHOR),
            search_path=self.shell["PATH"],
            package_root=self.home,
        )
        self.assertEqual(onboarded, settings.read_bytes())


class RetryTest(_support.OnboardingCase):
    """Each refused answer is printed beneath its question in its validator's words, and asked again.

    Outside a checkout the clone has no default, so an empty answer is
    refused too, and so is a repository the clone has no remote for, a token
    GitHub turns away, and an answer to a yes-or-no question that is neither.
    A token GitHub names no owner for leaves the authors without a default.
    """

    def test_each_refusal_asks_again(self) -> None:
        missing = str(self.home.parent / "missing")
        self.github.owners["ghp_unowned"] = ""

        transcript = self.onboarded(
            "", missing, self.api,
            "acme", "acme/other", "",
            "bad..branch", "release",
            "", "ghp_wrong", "ghp_unowned",
            "", "not a login!", "@alice, bob",
            "",
            "maybe", "", "", "",
        )

        self.assertIn("".join((
            f"{_CLONE}: \n",
            _support.beneath(refusal(validate_clone, "")),
            f"{_CLONE}: {missing}\n",
            _support.beneath(refusal(validate_clone, missing)),
            f"{_CLONE}: {self.api}\n",
            "[2/6] GitHub repository (owner/name) [acme/api]: acme\n",
            _support.beneath(
                "repository 'acme' is not written owner/name; give a GitHub owner and "
                "repository name joined by one '/', such as acme/api",
            ),
            "[2/6] GitHub repository (owner/name) [acme/api]: acme/other\n",
            _support.beneath(
                f"no remote of {self.api} points at acme/other on GitHub; add one, or "
                "say which repository and remote to use",
            ),
            "[2/6] GitHub repository (owner/name) [acme/api]: \n",
            "[3/6] Branch pull requests target [trunk]: bad..branch\n",
            _support.beneath(refusal(validate_branch, "bad..branch")),
            "[3/6] Branch pull requests target [trunk]: release\n",
            _API_TOKEN,
            _support.beneath("no token was given; give the repository's GitHub token"),
            _API_TOKEN,
            _support.beneath(
                "GitHub does not accept the token; it is mistyped, expired, or revoked "
                "(GitHub answered 401: Bad credentials)",
            ),
            _API_TOKEN,
            "      the token reaches acme/api\n",
            f"{_AUTHORS}: \n",
            _support.beneath(refusal(validate_logins, "")),
            f"{_AUTHORS}: not a login!\n",
            _support.beneath(refusal(validate_logins, "not a login!")),
            f"{_AUTHORS}: @alice, bob\n",
            "[6/6] GitHub logins to mention when a human is needed [alice,bob]: \n",
            f"\n{_FOUND}Keep these agents? [Y/n]: maybe\n",
            _support.beneath("'maybe' is neither yes nor no; answer y or n"),
            f"{_KEEP}{_NO_MORE}",
        )), transcript)
        self.assertNotIn("ghp_", transcript)
        written = _support.read(self.home / _support.SETTINGS_FILE)
        self.assertEqual(
            [read_setting(written, key) for key in ("REPOS", "ALLOWED_ISSUE_AUTHORS", "HITL_HANDLE")],
            [f"acme/api|{self.api}|release", "alice,bob", "alice,bob"],
        )


class TokenTest(_support.OnboardingCase):
    """A stored token is kept without a question, and an exported one is offered without being shown."""

    def test_a_stored_token_is_kept(self) -> None:
        token = self.home / _support.API_TOKEN_FILE
        token.parent.mkdir(parents=True)
        token.write_text(f"{_support.API_TOKEN}\n", encoding=_init.ENCODING)
        stored = token.stat()
        settings = self.home / _support.SETTINGS_FILE

        transcript = self.onboarded(self.api, "", "", *_support.AFTER_TOKEN)

        self.assertIn("".join((
            "[3/6] Branch pull requests target [trunk]: \n",
            f"[4/6] GitHub token for acme/api: keeping {token} (owner: alice)\n",
            f"{_AUTHORS} [alice]: \n",
        )), transcript)
        self.assertIn(f"\nWrite {settings}? [Y/n]: \n", transcript)
        self.assertNotIn("Saved the token", transcript)
        kept = token.stat()
        self.assertEqual((kept.st_mtime_ns, kept.st_mode), (stored.st_mtime_ns, stored.st_mode))
        self.assertEqual(self.github.requests, [("/user", _support.API_TOKEN)])

    def test_an_exported_token_is_offered(self) -> None:
        self.shell["GITHUB_TOKEN"] = _support.API_TOKEN

        transcript = self.onboarded(self.api, "", "", "", *_support.AFTER_TOKEN)

        self.assertIn(
            "[4/6] GitHub token for acme/api (input hidden) [exported GITHUB_TOKEN]: \n"
            "      the token reaches acme/api (owner: alice)\n",
            transcript,
        )
        self.assertNotIn(_support.API_TOKEN, transcript)
        saved = _support.read(self.home / _support.API_TOKEN_FILE)
        self.assertEqual(saved, f"{_support.API_TOKEN}\n")


class AgentsTest(_support.OnboardingCase):
    """A default agent not on the service's `PATH` is shown so, refused if kept, and replaced role by role."""

    def test_a_missing_agent_is_replaced(self) -> None:
        self.install_agents(_CLAUDE, "agy")
        missing = _support.beneath(refusal(validate_agent, "codex", self.shell["PATH"]))

        transcript = self.onboarded(
            self.api, "", "", _support.API_TOKEN, "", "",
            "y", "",
            "agy", "", _CLAUDE, "",
            "", "",
        )

        self.assertIn("".join((
            "Agents: implement=claude (found)  review=codex (not found on PATH)  decompose=claude (found)\n",
            f"Keep these agents? [y/N]: y\n{missing}",
            "Keep these agents? [y/N]: \n",
            "Agent that implements (claude/codex/agy) [claude]: agy\n",
            f"Agent that reviews (claude/codex/agy) [codex]: \n{missing}",
            "Agent that reviews (claude/codex/agy) [codex]: claude\n",
            "Agent that decomposes (claude/codex/agy) [claude]: \n",
        )), transcript)
        written = _support.read(self.home / _support.SETTINGS_FILE)
        self.assertEqual(
            [read_setting(written, key) for key in ("DEV_AGENT", "REVIEW_AGENT", "DECOMPOSE_AGENT")],
            ["agy", _CLAUDE, _CLAUDE],
        )


class FurtherRepositoryTest(_support.OnboardingCase):
    """Each further repository is asked its four questions, its clone offered nothing.

    A repository already given is refused whatever its case, and the further
    one is added to the `.env` the first one's `configure` wrote, as
    `add-repo` adds it, after every token is saved.
    """

    def test_a_second_repository_is_added(self) -> None:
        settings = self.home / _support.SETTINGS_FILE
        api_token = self.home / _support.API_TOKEN_FILE
        web_token = self.home / _support.WEB_TOKEN_FILE

        transcript = self.onboarded(
            self.api, "", "", _support.API_TOKEN, "", "", "",
            "y", "", self.web, "ACME/API", "", "", _support.WEB_TOKEN,
            "", "",
        )

        self.assertIn("".join((
            "Add another repository? [y/N]: y\n",
            "[1/4] Local clone of the repository to manage: \n",
            _support.beneath(refusal(validate_clone, "")),
            f"[1/4] Local clone of the repository to manage: {self.web}\n",
            "[2/4] GitHub repository (owner/name) [acme/web]: ACME/API\n",
            _support.beneath("ACME/API is already among the repositories given above; give another one"),
            "[2/4] GitHub repository (owner/name) [acme/web]: \n",
            "[3/4] Branch pull requests target [main]: \n",
            "[4/4] GitHub token for acme/web (input hidden): \n",
            "      the token reaches acme/web (owner: alice)\n",
            _NO_MORE,
            f"\nWrite {api_token}, {web_token}, and {settings}? [Y/n]: \n",
            f"Saved the token for acme/api to {api_token}\n",
            f"Saved the token for acme/web to {web_token}\n",
            f"Wrote {settings}\n",
            f"Added acme/web|{self.web}|main to REPOS in {settings}\n",
        )), transcript)
        self.assertEqual(
            read_setting(_support.read(settings), "REPOS"),
            f"acme/api|{self.api}|trunk;acme/web|{self.web}|main",
        )
        self.assertEqual(_support.read(web_token), f"{_support.WEB_TOKEN}\n")
