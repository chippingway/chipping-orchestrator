# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The read-only GitHub calls a setup proves a token with."""
from __future__ import annotations

import threading
import traceback
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType
from typing import NamedTuple
from unittest.mock import patch

from orchestrator import __version__
from orchestrator.service import token_probe
from tests.service.service_test_support import fake_github

_TOKEN = "github_pat_11ABCDEFG0123456789_abcdefghijklmnop"
_REPOSITORY = "acme/api"
_REPOSITORY_PATH = f"/repos/{_REPOSITORY}"
_USER_PATH = "/user"
_LOCALHOST = "127.0.0.1"


# A path the local server was asked for, and the headers that came with it.
_Request = tuple[str, dict[str, str]]


class _Route(NamedTuple):
    """What the local server answers one path with."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


# What the local server answers each path with, the length header aside.
# `/moved` points at `/target`, which a followed redirect would request next
# and the server has no answer for.
_ROUTES = MappingProxyType({
    "/found": _Route(HTTPStatus.OK, (), b'{"full_name": "acme/api"}'),
    "/missing": _Route(HTTPStatus.NOT_FOUND, (), b'{"message": "Not Found"}'),
    "/moved": _Route(HTTPStatus.MOVED_PERMANENTLY, (("Location", "/target"),), b'{"message": "Moved Permanently"}'),
})

# The headers GitHub's REST API asks a client to send.
_SENT_HEADERS = MappingProxyType({
    "Authorization": f"Bearer {_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": f"chipping-orchestrator/{__version__}",
})

_BAD_CREDENTIALS = (
    "GitHub does not accept the token; it is mistyped, expired, or revoked "
    "(GitHub answered 401: Bad credentials)"
)


def _said(message: str) -> dict[str, str]:
    """The error document GitHub answers with, carrying ``message``."""
    return {"message": message}


def _formatted(error: BaseException) -> str:
    """``error`` as a traceback prints it, every exception it chains included."""
    return "".join(traceback.format_exception(error))


class _RecordingHandler(BaseHTTPRequestHandler):
    """Answers from `_ROUTES`, recording the path and headers of each request."""

    def do_GET(self) -> None:
        self.server.received.append((self.path, self.headers))
        route = _ROUTES[self.path]
        length = ("Content-Length", str(len(route.body)))
        self.send_response(route.status)
        for name, header_value in (*route.headers, length):
            self.send_header(name, header_value)
        self.end_headers()
        self.wfile.write(route.body)

    def log_message(self, *_logged: object) -> None:
        """Keep the server's access log out of the test output."""


class HttpGetTest(unittest.TestCase):
    """`http_get` sends the token in a header and nowhere else, and hands back
    every status it is answered with, an error and a redirect included. A
    redirect is not followed, so the token never travels to where one points.
    A request nobody answers raises the standard library's error.
    """

    def setUp(self) -> None:
        # The local server is reached directly, whatever proxy the
        # environment running the suite names.
        self.enterContext(patch.dict("os.environ", {"no_proxy": "*"}))
        server = ThreadingHTTPServer((_LOCALHOST, 0), _RecordingHandler)
        server.received = []
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self._server = server
        self._root = f"http://{_LOCALHOST}:{server.server_address[1]}"

    def test_every_status_is_an_answer(self) -> None:
        for path, route in _ROUTES.items():
            with self.subTest(path=path):
                answer = token_probe.http_get(f"{self._root}{path}", _TOKEN)
                self.assertEqual(answer, (route.status, route.body))

        # Each path asked once and `/target` never, the token in its header
        # every time and in no path.
        expected = [(asked, dict(_SENT_HEADERS)) for asked in _ROUTES]
        self.assertEqual(self._received(), expected)

    def test_an_unanswered_request_raises(self) -> None:
        # Closed, the server's port refuses the connection outright.
        self._server.shutdown()
        self._server.server_close()

        with self.assertRaises(OSError):
            token_probe.http_get(f"{self._root}/found", _TOKEN)

    def _received(self) -> list[_Request]:
        """Each path the server was asked for, with the GitHub headers it carried."""
        return [
            (asked, {name: sent[name] for name in _SENT_HEADERS})
            for asked, sent in self._server.received
        ]


class ReachRepositoryTest(unittest.TestCase):
    """A repository is proved with exactly one call, for the repository itself,
    and every way that call can fail is told apart in words that never carry
    the token -- even where GitHub's message or the transport's error does --
    and in a traceback that never does either, since the refusal chains no
    error behind it.
    """

    def test_one_call_proves_the_repository(self) -> None:
        with fake_github({_REPOSITORY_PATH: (200, {"full_name": _REPOSITORY})}) as github:
            token_probe.reach_repository(_TOKEN, _REPOSITORY)

            self.assertEqual(github.requests, [(f"{token_probe.API_ROOT}{_REPOSITORY_PATH}", _TOKEN)])

    def test_each_refusal_says_what_failed(self) -> None:
        for answer, expected in (
            ((401, _said("Bad credentials")), _BAD_CREDENTIALS),
            (
                (403, _said(f"Resource not accessible\nby {_TOKEN}")),
                (
                    "GitHub refused the token access to acme/api "
                    "(GitHub answered 403: Resource not accessible by ***)"
                ),
            ),
            (
                (404, _said("Not Found")),
                (
                    "the token cannot read acme/api; check the name, and that the token is "
                    "granted access to it (GitHub answered 404: Not Found)"
                ),
            ),
            (
                (301, _said("Moved Permanently")),
                (
                    "acme/api has moved on GitHub; give its current owner/name "
                    "(GitHub answered 301: Moved Permanently)"
                ),
            ),
            (
                (502, b"<html>Bad gateway</html>"),
                "GitHub did not confirm the token can read acme/api (GitHub answered 502)",
            ),
            (
                ConnectionResetError(f"reset while sending {_TOKEN}"),
                "GitHub could not be reached (reset while sending ***)",
            ),
            (
                ValueError(f"Invalid header value b'Bearer {_TOKEN}\\n'"),
                (
                    "the token holds a line break or a character no request can carry; "
                    "give the token alone, on one line"
                ),
            ),
        ):
            with self.subTest(answer=answer), fake_github({_REPOSITORY_PATH: answer}) as github:
                refused = self.assertRaises(token_probe.ProbeError)
                with refused:
                    token_probe.reach_repository(_TOKEN, _REPOSITORY)

                self.assertEqual(str(refused.exception), expected)
                self.assertNotIn(_TOKEN, _formatted(refused.exception))
                self.assertEqual(len(github.requests), 1)


class OwnerLoginTest(unittest.TestCase):
    """The token's own account is read with one call, and an answer that names
    no login is a refusal rather than an empty default, its traceback as free
    of the token as its words.
    """

    def test_the_login_answers(self) -> None:
        with fake_github({_USER_PATH: (200, {"login": "alice"})}) as github:
            self.assertEqual(token_probe.owner_login(_TOKEN), "alice")

            self.assertEqual(github.requests, [(f"{token_probe.API_ROOT}{_USER_PATH}", _TOKEN)])

    def test_no_login_is_refused(self) -> None:
        for answer, expected in (
            ((401, _said("Bad credentials")), _BAD_CREDENTIALS),
            (
                (200, {"login": ""}),
                "GitHub did not confirm the token can read the account it belongs to (GitHub answered 200)",
            ),
            (
                ConnectionResetError(f"reset while sending {_TOKEN}"),
                "GitHub could not be reached (reset while sending ***)",
            ),
        ):
            with self.subTest(answer=answer), fake_github({_USER_PATH: answer}):
                refused = self.assertRaises(token_probe.ProbeError)
                with refused:
                    token_probe.owner_login(_TOKEN)

                self.assertEqual(str(refused.exception), expected)
                self.assertNotIn(_TOKEN, _formatted(refused.exception))


if __name__ == "__main__":
    unittest.main()
