# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One ``REPOS`` entry, written the way the configuration reads it back.

An entry is ``owner/name|target_root|base_branch``, then an optional remote
and an optional parallel limit. The fields are positional, so a parallel limit
is written behind its remote even where that remote is ``origin``, and the
remote is written whenever it is anything else: a clone whose GitHub remote is
not ``origin`` is recorded under the name it has.

The configuration splits a ``REPOS`` value into entries on ``;`` and line
breaks, an entry into fields on ``|``, and strips the blanks around each
field, so a field holding one of those, or blanks at either end, would come
back as something else. ``render`` refuses such a field rather than write it,
and holds the repository to the ``owner/name`` its validator accepts, which is
also what keeps an entry from reading as a comment.

Nothing here imports ``orchestrator.config``, which parses the entry back:
the format is the contract the two sides share, and a setup writes it on a
host where importing the configuration would exit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.service.validation import FieldError, validate_repository

DEFAULT_REMOTE = "origin"


def _require_writable(field: str) -> None:
    """Refuse a field the configuration would not read back as written."""
    # Split the way a `REPOS` value is read: what comes back has to be the
    # field alone, and stripping it must leave it as it was.
    pieces = field.replace("|", "\n").replace(";", "\n").splitlines()
    if pieces != [field] or field.strip() != field:
        raise FieldError(
            f"{field!r} cannot be written into a REPOS entry, which splits on "
            "'|', ';', and line breaks and strips the blanks around each field",
        )


@dataclass(frozen=True)
class RepositoryEntry:
    """The repository a ``REPOS`` entry names and where its clone sits."""

    repository: str
    clone: Path
    base_branch: str
    remote: str = DEFAULT_REMOTE
    parallel_limit: int | None = None

    def render(self) -> str:
        """The entry as a ``REPOS`` value spells it."""
        fields = [
            validate_repository(self.repository),
            str(self.clone),
            self.base_branch,
        ]
        if self.parallel_limit is not None or self.remote != DEFAULT_REMOTE:
            fields.append(self.remote)
        if self.parallel_limit is not None:
            if self.parallel_limit < 1:
                raise FieldError(
                    f"parallel limit {self.parallel_limit} is below 1, which "
                    "would block all work for the repository",
                )
            fields.append(str(self.parallel_limit))
        for field in fields:
            _require_writable(field)
        return "|".join(fields)
