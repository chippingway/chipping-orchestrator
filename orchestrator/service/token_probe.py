# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read-only GitHub calls a setup proves a token with, before or after keeping it.

The polling process reaches GitHub through a client that resolves its token
and settings through ``orchestrator.config``, which a first setup cannot
import. So each call here is one ``GET`` against GitHub's REST API, made with
the standard library and the token the caller hands in, which nothing here
reads from or writes to anywhere.

- ``reach_repository`` asks for the repository itself, which GitHub answers
  only for a token that is valid and can read it. It is exactly one call, so a
  check spends one per configured repository and nothing besides.
- ``owner_login`` asks whose token it is: the login an onboarding offers as
  the default author.

A redirect is answered as the status it is rather than followed, so the token
reaches no host but GitHub's API, and a renamed or transferred repository is
reported under the name GitHub no longer answers for rather than proved under
another. A diagnostic is built from the status, GitHub's own message, and the
transport's error, with the token masked in each, so none of them carries it,
and a ``ProbeError`` chains no error behind it, so its traceback does not
either.

``http_get`` is where a request leaves the process, and the seam a test stands
a fake GitHub in for.
"""
from __future__ import annotations

import json
from contextlib import suppress
from http import HTTPStatus
from http.client import HTTPException
from types import MappingProxyType
from urllib import error as _url_errors, request as _url_requests

from orchestrator import __version__

API_ROOT = "https://api.github.com"

_TIMEOUT_SECONDS = 30
_MASK = "***"

# What a plain GET needs from urllib: the proxies the environment names, both
# schemes, and every status handed back as an answer. A redirect handler is
# the one part left out.
_OPENER_PARTS = (
    _url_requests.ProxyHandler,
    _url_requests.HTTPHandler,
    _url_requests.HTTPSHandler,
    _url_requests.HTTPDefaultErrorHandler,
    _url_requests.HTTPErrorProcessor,
)

# What a refusal means for the token, and what the operator can do about it.
_ADVICE = MappingProxyType({
    HTTPStatus.UNAUTHORIZED: "GitHub does not accept the token; it is mistyped, expired, or revoked",
    HTTPStatus.FORBIDDEN: "GitHub refused the token access to {subject}",
    HTTPStatus.NOT_FOUND: (
        "the token cannot read {subject}; check the name, and that the token "
        "is granted access to it"
    ),
})
_REDIRECTIONS = range(HTTPStatus.MULTIPLE_CHOICES, HTTPStatus.BAD_REQUEST)
_MOVED = "{subject} has moved on GitHub; give its current owner/name"
_UNCONFIRMED = "GitHub did not confirm the token can read {subject}"
_UNSENDABLE = (
    "the token holds a line break or a character no request can carry; give the "
    "token alone, on one line"
)


class ProbeError(Exception):
    """A GitHub call that did not prove what it asked; the text says why."""


def http_get(url: str, token: str) -> tuple[int, bytes]:
    """``GET`` ``url`` with ``token``, and the status and body that answered.

    Any status comes back as an answer, an error or a redirect included, so
    the caller reads GitHub's message for it; only a request nobody answered
    raises, with the ``OSError`` or ``HTTPException`` the standard library
    reports. The opener is built per call, so it reads the proxies the
    environment names now, and it is built without a redirect handler, which
    is what keeps a redirect an answer rather than a second request carrying
    the token.
    """
    opener = _url_requests.OpenerDirector()
    for part in _OPENER_PARTS:
        opener.add_handler(part())
    sent = _url_requests.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": f"chipping-orchestrator/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with opener.open(sent, timeout=_TIMEOUT_SECONDS) as answered:
            return answered.status, answered.read()
    except _url_errors.HTTPError as refused:
        with refused:
            return refused.code, refused.read()


def reach_repository(token: str, repository: str) -> None:
    """Prove ``token`` reads ``repository``, an ``owner/name``, or raise ``ProbeError``."""
    status, document = _answer(f"/repos/{repository}", token)
    if status != HTTPStatus.OK:
        raise ProbeError(_refusal(status, document, token, repository))


def owner_login(token: str) -> str:
    """The login of the account ``token`` belongs to, or ``ProbeError``."""
    status, document = _answer("/user", token)
    login = document.get("login") if isinstance(document, dict) else None
    if status == HTTPStatus.OK and isinstance(login, str) and login:
        return login
    raise ProbeError(_refusal(status, document, token, "the account it belongs to"))


def _masked(text: str, token: str) -> str:
    """``text`` on one line, with every copy of ``token`` in it masked."""
    if token:
        text = text.replace(token, _MASK)
    return " ".join(text.split())


def _answer(path: str, token: str) -> tuple[int, object]:
    """GitHub's status for ``path`` and the JSON document it answered with.

    A request that was never answered is refused only once its error is
    handled, so the refusal carries no chain: the transport's error, and the
    standard library's refusal of a header, can quote the token unmasked.
    """
    try:
        status, body = http_get(f"{API_ROOT}{path}", token)
    except (OSError, HTTPException) as unanswered:
        reason = f"GitHub could not be reached ({unanswered})"
    except ValueError:
        reason = _UNSENDABLE
    else:
        # A body that is not JSON answers as no document at all.
        with suppress(ValueError):
            return status, json.loads(body)
        return status, None
    raise ProbeError(_masked(reason, token))


def _refusal(status: int, document: object, token: str, subject: str) -> str:
    """Why an answer of ``status`` proves nothing about ``subject``."""
    advice = _MOVED if status in _REDIRECTIONS else _ADVICE.get(status, _UNCONFIRMED)
    message = document.get("message") if isinstance(document, dict) else None
    said = f": {message}" if isinstance(message, str) and message else ""
    reason = f"{advice.format(subject=subject)} (GitHub answered {status}{said})"
    return _masked(reason, token)
