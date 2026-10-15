# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``add-repo``: one more repository in the ``REPOS`` of an installed package's ``.env``.

``add-repo`` adds the entry a clone makes to the ``REPOS`` setting of
``~/.config/chipping-orchestrator/.env``, the file ``configure`` wrote. The
configuration keeps the first value it reads for a key, so a second ``REPOS``
line would be ignored without a word: the entry is added at the end of the
line the configuration reads ``REPOS`` from, through ``dotenv_text``, and
every other line -- the comments around it, a commented-out example, a later
``REPOS`` line nothing reads -- stays as it was, byte for byte.

The entry is the one ``configure`` would write, made by ``entry_answers``: the
repository, its remote, and the base branch are read off the clone unless an
answer gives them, under the same field validators and the same messages.
``--remote`` names the remote outright, refused under that option too where
the entry cannot carry it, and a parallel limit is written behind its remote,
``origin`` included, since the fields are positional.

Everything is checked before anything is written, in this order: the package
must not run from a source checkout, which reads a ``.env`` of its own; the
installed ``.env`` has to exist, and to set ``REPOS``; each answer passes its
validator before the clone is read; and the repository must not be listed
already, compared as GitHub compares names, without regard to case. The file
is then written whole with mode 0600 through ``private_files``, in place of
the file read -- the one a symlink there leads to, so the link stays one.

The core is ``add_repo``, which takes the answers as typed, so the command
line and an onboarding adding a further repository in process write the same
line. A running service reads ``REPOS`` only as it starts, which the command
line, not the core, tells its operator. Nothing here imports
``orchestrator.config``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from orchestrator.service import paths
from orchestrator.service.dotenv_text import assign, read_setting
from orchestrator.service.entry_answers import answered_entry, checked
from orchestrator.service.private_files import write_private
from orchestrator.service.repos_entry import RepositoryEntry, writable_field

COMMAND = "add-repo"

_REPOS = "REPOS"
_ENCODING = "utf-8"

_UNCONFIGURED = (
    "no configuration exists at {0}, and add-repo adds a repository to one; "
    "write it for the first repository with chipping-orchestrator configure "
    "--clone PATH --authors LOGINS, then add each further one"
)
_NO_REPOS = (
    "no line of {0} sets REPOS, which add-repo adds the repository to; give "
    "it a REPOS line naming the repositories it already manages"
)
_LISTED = "REPOS in {0} already lists {1}; edit its entry there to change it"


@dataclass(frozen=True)
class AddRepoAnswers:
    """What ``add-repo`` is told, each answer as it was typed.

    The names are the command's options; ``None`` takes that option's
    default.
    """

    clone: str
    repo: str | None = None
    base_branch: str | None = None
    remote: str | None = None
    parallel: str | None = None


class AddRepoRefusal(Exception):
    """Why ``add-repo`` writes nothing, other than a field it refused."""


def _read(settings_file: Path) -> str:
    """The text of ``settings_file``, its line ends as they are."""
    if not os.path.lexists(settings_file):
        raise AddRepoRefusal(_UNCONFIGURED.format(settings_file))
    try:
        with settings_file.open(encoding=_ENCODING, newline="") as stream:
            return stream.read()
    except (OSError, UnicodeDecodeError) as error:
        raise AddRepoRefusal(f"{settings_file} cannot be read ({error})") from error


def _extended(listed: str, entry: RepositoryEntry, settings_file: Path) -> str:
    """``listed`` with ``entry`` added at its end, refused where it lists the repository already.

    An entry's repository is its first field, compared without regard to
    case; a commented-out entry's first field begins with ``#``, so it names
    no repository at all. The blanks at either end of ``listed`` are dropped:
    quotes may have kept them, which the unquoted line cannot, and the
    configuration reads each entry without them anyway.
    """
    wanted = entry.repository.lower()
    for line in listed.replace(";", "\n").splitlines():
        repository = line.partition("|")[0].strip()
        if repository.lower() == wanted:
            raise AddRepoRefusal(_LISTED.format(settings_file, repository))
    kept = listed.strip()
    separator = ";" if kept and not kept.endswith(";") else ""
    return f"{kept}{separator}{entry.render()}"


def _write(settings_file: Path, text: str) -> None:
    """Write ``text`` over the file ``settings_file`` names, whole and private."""
    target = Path(os.path.realpath(settings_file))
    try:
        write_private(target, text, replace=True)
    except OSError as error:
        raise AddRepoRefusal(f"{target} cannot be written ({error})") from error


def add_repo(
    answers: AddRepoAnswers,
    *,
    package_root: Path = paths.PACKAGE_ROOT,
) -> RepositoryEntry:
    """Add the entry ``answers`` make to the installed ``.env``'s ``REPOS``; return it.

    Raises ``AddRepoRefusal`` or ``FieldError``, with the whole diagnostic as
    its text, having written nothing.
    """
    refusal = paths.source_checkout_refusal(COMMAND, package_root)
    if refusal is not None:
        raise AddRepoRefusal(refusal)
    settings_file = paths.settings_file()
    text = _read(settings_file)
    listed = read_setting(text, _REPOS)
    if listed is None:
        raise AddRepoRefusal(_NO_REPOS.format(settings_file))
    entry = answered_entry(
        answers.clone,
        answers.repo,
        answers.base_branch,
        remote=answers.remote,
        parallel=answers.parallel,
    )
    checked("--remote", writable_field, entry.remote)
    _write(settings_file, assign(text, _REPOS, _extended(listed, entry, settings_file)))
    return entry
