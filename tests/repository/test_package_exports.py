# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each package publishes, and what the rest of them publish instead.

Most initializers front no surface at all: importing one owner must not charge
the importer for its siblings, so the initializer binds nothing and a caller
names the module that defines what it wants. The few that do publish are listed
here, each because a caller is meant to reach the family through the package
rather than past it, and each publishes through an explicit `__all__` -- which
is what makes the surface a bounded thing a reader can see the whole of, and a
new name on it a deliberate edit.

What a publisher hands back is the owner's own object, bound once at import.
The module a published name reports is therefore the module that defines it,
which is where a reader looks for the source and where a patch has to land.
"""
from __future__ import annotations

import inspect
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType, ModuleType

from tests.repository.binding_test_support import module_level_names
from tests.repository.layout_test_support import (
    PACKAGE,
    PACKAGE_ROOT,
    dotted_name,
    package_directories,
)

_ANALYTICS = f"{PACKAGE}.observability.analytics"

# The packages a caller reaches a family through. The root publishes the
# distribution version; `agents`, `github`, `scheduler`, and `workflow` publish
# the API their domain is driven through; `config` publishes every resolved
# setting; and the two observability publishers front the usage parsers and the
# analytics recorders a producer appends with.
_PUBLISHERS = frozenset((
    PACKAGE,
    f"{PACKAGE}.agents",
    f"{PACKAGE}.config",
    f"{PACKAGE}.github",
    f"{PACKAGE}.scheduler",
    f"{PACKAGE}.workflow",
    f"{_ANALYTICS}.recording",
    f"{PACKAGE}.observability.usage",
))

# A marker initializer that loads a sibling for everyone who names the package.
# The name it binds is the sibling's own, which is what makes the eager import
# invisible in the namespace and visible only here, in the source.
_EAGER_MARKER = '''
"""A package marker that imports one of its owners."""
from orchestrator.git import commands
'''

# The sibling a publisher may hand back a name from: the record envelope both
# analytics sinks are written through is owned above the recorders that call it,
# so the recording surface publishes it from there.
_COMPOSED = MappingProxyType({
    f"{_ANALYTICS}.recording": f"{_ANALYTICS}.sink",
})


def _packages() -> frozenset[str]:
    """Every package in the production tree, by dotted name."""
    return frozenset(
        dotted_name(directory / "__init__.py", PACKAGE_ROOT)
        for directory in package_directories(PACKAGE_ROOT)
    )


def _initializer_path(package: str) -> Path:
    """Where the package's initializer sits on disk."""
    return PACKAGE_ROOT.joinpath(*package.split(".")[1:], "__init__.py")


def _home_of(bound: object) -> str:
    """The module a bound object belongs to, as it reports itself."""
    if isinstance(bound, ModuleType):
        return bound.__name__
    return str(getattr(bound, "__module__", ""))


def _undeclared_bindings(package: str) -> tuple[str, ...]:
    """The public names a publisher's namespace holds beyond its surface.

    Two things are allowed there unnamed by `__all__`. A submodule, which an
    import of it plants under its own name whatever alias the initializer used.
    And a name an import statement brought in from outside the package -- `os`,
    a `typing` name, the `__future__` flag -- which is a helper the initializer
    resolves its own values with rather than something it hands a caller.

    Anything else is either a name the initializer defined itself or one of the
    package's own it re-exports without saying so, and both are surface that
    `__all__` does not bound.
    """
    initializer = import_module(package)
    published = frozenset(initializer.__all__)
    imported = module_level_names(
        _initializer_path(package), from_imports=True,
    )
    return tuple(
        name
        for name, bound in initializer.__dict__.items()
        if not name.startswith("_")
        and name not in published
        and _home_of(bound) != f"{package}.{name}"
        and not (name in imported and not _home_of(bound).startswith(PACKAGE))
    )


def _published_definitions(package: str) -> tuple[tuple[str, str], ...]:
    """Each published class or function paired with the module defining it.

    A published value -- a resolved setting, the version string -- reports the
    module of its *type*, so only the definitions are asked where they come
    from.
    """
    initializer = import_module(package)
    published = (
        (name, getattr(initializer, name)) for name in initializer.__all__
    )
    return tuple(
        (name, defined.__module__)
        for name, defined in published
        if inspect.isclass(defined) or inspect.isroutine(defined)
    )


class PublisherInventoryTest(unittest.TestCase):
    """The packages carrying an `__all__` are the declared publishers."""

    def test_declaring_packages_are_the_publishers(self) -> None:
        declaring = frozenset(
            package for package in _packages()
            if hasattr(import_module(package), "__all__")
        )
        self.assertEqual(declaring, _PUBLISHERS)


class NarrowSurfaceTest(unittest.TestCase):
    """A publisher republishes its owners; the rest bind nothing at all."""

    def test_a_marker_initializer_binds_nothing(self) -> None:
        # Read the initializer's own statements, because the namespace cannot
        # answer this: importing `git.commands` from anywhere at all plants
        # `commands` on `orchestrator.git`, so a sibling the initializer
        # imported itself and one someone else's import left behind look
        # identical from the outside. What the source says is the difference,
        # and it is the whole difference -- an eager import here loads that
        # sibling for every caller who names the package.
        for package in _packages() - _PUBLISHERS:
            with self.subTest(package=package):
                self.assertEqual(
                    module_level_names(_initializer_path(package)),
                    frozenset(),
                )

    def test_an_eager_import_is_a_binding(self) -> None:
        # What the check above rejects, spelled out: importing a sibling is a
        # binding even where the name it lands under is the sibling's own.
        with TemporaryDirectory() as directory:
            initializer = Path(directory) / "__init__.py"
            initializer.write_text(_EAGER_MARKER, encoding="utf-8")
            bound = module_level_names(initializer)
        self.assertEqual(bound, frozenset(("commands",)))

    def test_a_marker_namespace_holds_only_submodules(self) -> None:
        # The other side of it: whatever an import elsewhere plants here is a
        # submodule of this package under its own name. Anything else would be
        # a re-export, making the initializer a second identity for an owner.
        for package in _packages() - _PUBLISHERS:
            initializer = import_module(package)
            for name, bound in initializer.__dict__.items():
                if name.startswith("__"):
                    continue
                with self.subTest(package=package, name=name):
                    self.assertEqual(
                        getattr(bound, "__name__", ""), f"{package}.{name}",
                    )

    def test_a_publisher_binds_nothing_undeclared(self) -> None:
        # `__all__` bounds a wildcard import, not the namespace: a name the
        # initializer defines beside it -- a helper, a constant, a re-export it
        # forgot to declare -- is still reachable as `package.name` and still a
        # second site for an owner to answer on. What a reader sees in `__all__`
        # has to be the whole of what the package publishes.
        for package in _PUBLISHERS:
            with self.subTest(package=package):
                self.assertEqual(_undeclared_bindings(package), ())

    def test_a_published_name_is_its_owner_s(self) -> None:
        for package in _PUBLISHERS:
            composed = _COMPOSED.get(package, package)
            for name, owner in _published_definitions(package):
                with self.subTest(package=package, name=name):
                    self.assertTrue(
                        owner.startswith((package, composed)),
                        f"{package} publishes {name} from {owner}",
                    )


if __name__ == "__main__":
    unittest.main()
