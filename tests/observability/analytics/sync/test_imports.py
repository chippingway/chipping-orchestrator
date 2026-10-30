# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the sync owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics import sync as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _run_import_probe,
)

_PACKAGE = "orchestrator.observability.analytics.sync"

_CLI_OWNER = "cli"

_COLUMNS_OWNER = "columns"

_DATABASE_OWNER = "database"

_EVIDENCE_OWNER = "evidence"

_INGEST_OWNER = "ingest"

_MODELS_OWNER = "models"

_RECORDS_OWNER = "records"

_REDACTION_OWNER = "redaction"

_ROWS_OWNER = "rows"

_RUN_OWNER = "run"

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the module map, which is what the inventory check compares the directory
# against.
_OWNERS = (
    _CLI_OWNER,
    _COLUMNS_OWNER,
    _DATABASE_OWNER,
    _EVIDENCE_OWNER,
    _INGEST_OWNER,
    _MODELS_OWNER,
    _RECORDS_OWNER,
    _REDACTION_OWNER,
    _ROWS_OWNER,
    _RUN_OWNER,
)

# What each owner answers for, declared rather than discovered so a new public
# name is a deliberate edit: a second way to hash a record, lay a row out, or
# decide what a replay was asked for is a second place the dedup key, the
# INSERT's parameter order, or the no-op contract could disagree with the one
# the table is written through, and a second way to start one is a second place
# the arguments an operator passes and the code they read back could. The
# inventory owner reports nothing because the check reads `__module__`, which
# only a class or a function carries -- its whole surface is the column names,
# the promoted list, the JSONB pair, the required keys, the per-basis maps, and
# the derived and table-wide lists. `database` is likewise short one name: the
# view the refresh names is a string, as is the event `evidence` derives for.
_SURFACES = MappingProxyType({
    _CLI_OWNER: (
        "cli_parser",
        "configure_cli_logging",
        "main",
        "print_cli_result",
        "run_cli",
    ),
    _COLUMNS_OWNER: (),
    _DATABASE_OWNER: (
        "close_quietly",
        "default_connect",
        "default_json_adapter",
        "execute_rollup_refresh",
        "refresh_daily_rollup",
        "rollback_quietly",
    ),
    _EVIDENCE_OWNER: (
        "cost_amount_cells",
        "derived_columns",
        "rate_date_cells",
    ),
    _INGEST_OWNER: (
        "RecordIngester",
        "emit_progress",
        "existing_hashes",
        "flush_batch",
        "ingest_records",
        "note_malformed_line",
        "stream_records",
    ),
    _MODELS_OWNER: (
        "IngestContext",
        "SyncCounters",
        "SyncResult",
    ),
    _RECORDS_OWNER: (
        "canonical_json",
        "content_hash",
        "extra_columns",
        "issue_number",
        "parse_ts",
        "required_columns",
        "required_text",
    ),
    _REDACTION_OWNER: (
        "redact_db_url",
        "redacted_netloc",
        "redacted_query",
    ),
    _ROWS_OWNER: (
        "PreparedRecord",
        "RowProvenance",
        "build_insert_sql",
        "prepare_record",
        "row_values",
        "split_row",
    ),
    _RUN_OWNER: (
        "SyncRequest",
        "SyncRun",
        "sync_jsonl_to_postgres",
    ),
})

# Every owner that has to obtain the row translation from a sibling: the ingest
# loop that turns each line into a batched tuple, and the run that builds the
# statement those tuples are sent under once.
_TRANSLATION_CALLERS = (_INGEST_OWNER, _RUN_OWNER)

# The driver the ingestion opens its connection with. It is imported lazily
# inside the connect helper, and nothing here dials anything at import, so a
# caller that only hashes a record or lays a row out must not pay for it -- nor
# be unable to do either on a machine with no Postgres client installed.
_DRIVER_PROBE = """
import sys
import {module}
driver = [name for name in sys.modules if name.split('.')[0] == 'psycopg']
sys.exit(', '.join(driver) if driver else 0)
"""


def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


def _defined_here(owner: str) -> tuple[str, ...]:
    """Public names the owner defines, as opposed to ones it imported."""
    module = import_module(_qualified(owner))
    return tuple(sorted(
        name
        for name, member in module.__dict__.items()
        if not name.startswith("_")
        and getattr(member, "__module__", None) == module.__name__
    ))


class OwnerInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))


class PublicSurfaceTest(unittest.TestCase):
    """Each owner answers for a narrow, declared surface."""

    def test_public_names_are_the_declared_ones(self) -> None:
        for owner, surface in _SURFACES.items():
            with self.subTest(owner=owner):
                self.assertEqual(_defined_here(owner), surface)

    def test_no_surface_is_declared_twice(self) -> None:
        # The package initializer is a marker, so a name is reached on the
        # owner that defines it rather than published a second time above it.
        self.assertNotIn("__all__", _package.__dict__)
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertNotIn(
                    "__all__", import_module(_qualified(owner)).__dict__,
                )


class LayeringTest(unittest.TestCase):
    """The owners reach only siblings, never the driver, and the command names
    the service it drives.
    """

    def test_no_owner_reaches_outside_the_package(self) -> None:
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(("orchestrator.observability", "orchestrator._package"))
                        or imported == "orchestrator",
                        f"{owner} reaches {imported}",
                    )

    def test_no_owner_plants_the_driver(self) -> None:
        for owner in _OWNERS:
            probe = _DRIVER_PROBE.format(module=_qualified(owner))
            completed = _run_import_probe(probe)
            with self.subTest(owner=owner):
                self.assertEqual(
                    completed.returncode, 0, msg=completed.stderr,
                )

    def test_every_caller_names_the_mapping_owner(self) -> None:
        for caller in _TRANSLATION_CALLERS:
            with self.subTest(caller=caller):
                self.assertIn(
                    _qualified(_ROWS_OWNER),
                    _imported_orchestrator_modules(_qualified(caller)),
                )

    def test_the_command_names_the_service_owner(self) -> None:
        # The command owns the parser, the logging, and the stdout summary; the
        # replay under them is the service owner's, so it has to name it.
        self.assertIn(
            _qualified(_RUN_OWNER),
            _imported_orchestrator_modules(_qualified(_CLI_OWNER)),
        )


if __name__ == "__main__":
    unittest.main()
