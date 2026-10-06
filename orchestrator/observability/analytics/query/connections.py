# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a read reaches the operator's Postgres target, and what a failure is.

`AnalyticsReadError` is the single exception every read wraps a driver failure
in, with the original preserved as `__cause__` so a caller can log or
introspect it without this package re-exporting psycopg's hierarchy. Under it
sit the two connect factories the read path defaults to, differing only in
whether the socket they open is meant to outlive the query: `default_connect`
for the open-per-query path, `default_persistent_connect` for the one a thread
keeps.

Both defer the psycopg import to call time, so importing a read model never
costs the driver -- `pyproject.toml` pins `psycopg[binary]`, but a caller that
only consumes the dataclasses (typing, tests, docs builds) must not meet an
ImportError -- and a test can inject a `connect(db_url)` factory of its own
without installing one.

Beside them are the two judgments a caller makes about a connection rather than
about a query: whether closing it failed, which is logged and swallowed because
the rows already came back, and whether an escaped error means the socket
itself is gone.
"""

from __future__ import annotations

import logging
from typing import Any

# Pinned to the name these lines were emitted under before this owner existed,
# rather than derived from the module path: a logger name is an operator-facing
# surface, so an installed filter or level set on it has to keep matching after
# the responsibility moves.
log = logging.getLogger("orchestrator.analytics.connection")

_BROKEN_SOCKET_ERRORS = ("OperationalError", "InterfaceError")


class AnalyticsReadError(RuntimeError):
    """Raised when a query against the analytics DB fails.

    The original psycopg / driver exception is preserved as ``__cause__`` so
    the caller can introspect it for logging without the read path
    re-exporting psycopg's exception hierarchy.
    """


def _psycopg() -> Any:
    """Import the driver at call time, as an `AnalyticsReadError` if absent."""
    try:
        import psycopg
    except ImportError as error:
        raise AnalyticsReadError(
            "psycopg is required for the analytics reads; reinstall chipping-orchestrator "
            "or run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync` in a source checkout"
        ) from error
    return psycopg


def _connect(db_url: str, **connect_kwargs: Any) -> Any:
    """Dial `db_url`, normalizing any driver failure to one exception type."""
    driver = _psycopg()
    try:
        return driver.connect(db_url, **connect_kwargs)
    except Exception as error:
        raise AnalyticsReadError(f"could not connect to analytics database: {error}") from error


def default_connect(db_url: str) -> Any:
    """Open the socket one query owns, mirroring the sync's own factory."""
    return _connect(db_url)


def default_persistent_connect(db_url: str) -> Any:
    """`default_connect` variant that opens with `autocommit=True`.

    `analytics_connection` keeps a single connection alive across many
    sequential reads on the same thread; psycopg's default "implicit
    transaction on first statement" behavior would leave the session idle in
    transaction after every SELECT (holding xmin, blocking vacuum) and, on a
    query error, in `aborted` state -- every subsequent read on the same
    thread-local would raise `InFailedSqlTransaction` until something rolled it
    back. Autocommit avoids both. This path is read-only by design; any future
    caller that needs an explicit transaction should open one inline with
    `with conn.transaction():` rather than disabling autocommit globally.
    """
    return _connect(db_url, autocommit=True)


def is_broken_connection_exc(exc: BaseException) -> bool:
    """True when `exc` looks like a torn-down psycopg socket.

    The check unwraps an `AnalyticsReadError` to inspect its `__cause__` (every
    driver-level error wraps through the query path). Class-name matching
    covers the common test case where a fake cursor raises a shim
    `OperationalError` / `InterfaceError` without psycopg installed; falls back
    to an `isinstance` check against the real psycopg classes when the driver
    is present.
    """
    cause: BaseException | None
    if isinstance(exc, AnalyticsReadError):
        cause = exc.__cause__
    else:
        cause = exc
    if cause is None:
        return False
    if type(cause).__name__ in _BROKEN_SOCKET_ERRORS:
        return True
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(cause, (psycopg.OperationalError, psycopg.InterfaceError))


def close_quietly(conn: Any) -> None:
    """Close `conn`, logging rather than raising when the driver refuses.

    A close that fails after the rows came back is the caller's problem with
    nothing left to do about it, so it must not turn a served read into a
    dashboard error.
    """
    try:
        conn.close()
    except Exception:
        log.exception("analytics read: connection close failed")
