# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an installed orchestrator carries for setting itself up and managing its service.

``templates`` reads the two ``.env`` templates that ship beside it as package
data: ``.env.example``, the basic template a setup starts from, and
``.env.example.advanced``, the optional overrides and developer settings. Both
files live in this directory and nowhere else, so every install carries the
copies that match its own version, and a source checkout reads the same files
its documentation links to and its tests parse.

The rest is what a setup checks and derives before it writes anything.
``checkouts`` answers whether a directory is the top of a git checkout, as git
itself reads one, and ``paths`` where the running package sits -- its own
source checkout or an installed distribution -- where an installed one keeps
its ``.env`` and logs, and the refusal a setup command gives a source
checkout. ``validation`` holds one validator per setup field and the
``FieldError`` each refuses with; ``remote_urls`` reads which GitHub
repository a remote's URL names; ``clone_defaults`` derives a clone's
repository, remote, and base branch from its remotes; and ``repos_entry``
writes the ``REPOS`` entry those fields make.

Then the writing. ``dotenv_text`` sets a setting in a ``.env``'s text on the
line the configuration reads it from, and ``private_files`` writes a file
whole, mode 0600, into a directory made with mode 0700, as is each parent
missing above it. ``configure`` is the
command that writes an installed package's ``.env`` from the basic template
with all of the above, its core called in process with the answers as typed.
``tokens`` is the one that keeps a repository's token: read from standard
input -- at a terminal through ``token_prompt``, which refuses one that would
show it -- proved by ``token_probe``, read-only GitHub calls made with the
standard library, and written through ``private_files``.

Then the check. ``environment`` decides what the systemd user service runs
with, from the shell that sets it up: its ``HOME`` and ``USER``, and its
``PATH`` with only the absolute entries kept. ``checks`` is ``check``, which
refuses a source checkout as the setup commands do and judges an installed
setup in exactly that environment: a fresh interpreter of this package,
started with it, runs ``settings_report``, which resolves the
settings there and reports what keeps them from running the service -- with
the GitHub call ``token_probe`` makes per repository, unless the check is
local. ``commands`` puts all three commands on the command line
``orchestrator/cli.py`` parses.

Then the service. ``unit_file`` is the systemd user unit an installed package
runs as, quoted the way systemd reads it back, and the hand-written unit it
refuses to stand beside; ``unit_environment`` reads the environment and the
working directory that unit and the drop-ins ``unit_drop_ins`` finds for it
give the service, as systemd assembles them, through the part of the unit-file
syntax ``unit_syntax`` reads, and ``manager_environment`` what the user
manager's ``ManagerEnvironment=``, ``DefaultEnvironment=``, and
``environment.d`` hand every service beneath them, the latter through
``environment_syntax``; ``systemd`` asks the user manager, logind, and the
journal, each call bounded. ``installation`` is ``init``, which refuses what
it cannot install for, runs the full ``check``, writes the unit, and enables
it -- and linger -- without starting it, leaving the ``.env`` and the tokens
as it found them. ``lifecycle`` holds what the commands that manage the
installed service share, with ``stop`` and ``status``; ``starting`` is
``start`` and ``restart``, which run the local ``check`` in that environment
and directory before asking systemd anything and watch the service stay
active; and ``removal`` is ``remove``, which deletes the unit alone.
``service_commands`` puts them all on the command line beside the setup
commands.

Nothing here imports ``orchestrator.config`` as it is imported, or the GitHub
client that reads its token through it; ``settings_report`` imports the
configuration inside its call, which runs only in the interpreter ``checks``
starts. ``orchestrator.config`` resolves and validates the settings as it is
imported, and an installed package with no ``REPOS`` exits there -- which is
exactly the state a first setup starts from.
The configuration reads ``checkouts`` and ``paths`` back instead, to hold its
targets to the same check and to choose the ``.env`` it loads, which those two
can serve from below it because they import nothing beyond each other. This
initializer binds nothing, so naming the package costs no owner beneath it.
"""
