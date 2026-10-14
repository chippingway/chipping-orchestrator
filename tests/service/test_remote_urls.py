# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which GitHub repository each form of a remote URL names, if any."""

import unittest

from orchestrator.service.remote_urls import repository_from_url

# Every form git accepts for a repository on github.com, each naming acme/api,
# the SSH forms on GitHub's port-443 endpoint `ssh.github.com` included.
_GITHUB_FORMS = (
    "https://github.com/acme/api.git",
    "https://github.com/acme/api",
    "https://github.com/acme/api/",
    "https://github.com/acme/api.git/",
    "http://github.com/acme/api.git",
    "https://x-access-token:secret@github.com/acme/api.git",
    "https://GitHub.COM/acme/api.git",
    "ssh://git@github.com/acme/api.git",
    "ssh://git@github.com:22/acme/api",
    "ssh://github.com/acme/api.git",
    "git+ssh://git@github.com/acme/api.git",
    "git://github.com/acme/api.git",
    "git@github.com:acme/api.git",
    "git@github.com:acme/api",
    "git@GitHub.com:acme/api.git/",
    "github.com:acme/api.git",
    "git@github.com:/acme/api.git",
    "ssh://git@ssh.github.com:443/acme/api.git",
    "ssh://git@SSH.GitHub.com:443/acme/api",
    "git@ssh.github.com:acme/api.git",
    "  https://github.com/acme/api.git\n",
)

# URLs that name no repository on github.com: another host, a lookalike, the
# SSH endpoint under a scheme it does not serve, an SSH host alias, a local
# path, and paths with too few or too many parts.
_OTHER_URLS = (
    "",
    "https://gitlab.com/acme/api.git",
    "https://github.com.evil.example/acme/api.git",
    "ssh://git@ssh.github.com.evil.example:443/acme/api.git",
    "https://ssh.github.com/acme/api.git",
    "https://evil.example/github.com/acme/api.git",
    "git@github-work:acme/api.git",
    "git@gitlab.com:acme/api.git",
    "file:///srv/git/acme/api.git",
    "ftp://github.com/acme/api.git",
    "/srv/git/github.com:acme/api.git",
    "../api",
    "https://github.com/acme",
    "https://github.com/acme/api/tree/main",
    "git@github.com:acme",
    "https://[github.com/acme/api.git",
)


class RepositoryFromUrlTest(unittest.TestCase):
    """Each GitHub form names its repository; nothing else names one."""

    def test_github_forms_name_the_repository(self) -> None:
        for url in _GITHUB_FORMS:
            with self.subTest(url=url):
                self.assertEqual(repository_from_url(url), "acme/api")

    def test_names_keep_their_spelling(self) -> None:
        self.assertEqual(
            repository_from_url("git@github.com:Acme-Labs/api.v2_x.git"), "Acme-Labs/api.v2_x",
        )

    def test_other_urls_name_none(self) -> None:
        for url in _OTHER_URLS:
            with self.subTest(url=url):
                self.assertIsNone(repository_from_url(url))


if __name__ == "__main__":
    unittest.main()
