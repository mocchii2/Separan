"""Opt-in real-server integration tests for external database drivers.

Set SEPARAN_TEST_<DRIVER>_HOST, _DATABASE, _USER, and _PASSWORD to enable a
backend. Tests create and remove a uniquely named table and never print config.
"""

import os
import sys
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute


class ExternalDatabaseIntegrationTests(unittest.TestCase):
    def test_required_backend_cannot_be_skipped(self):
        prefix = "SEPARAN_TEST_POSTGRESQL_"
        environment = {prefix + key: "" for key in ("HOST", "DATABASE", "USER", "PASSWORD")}
        environment["SEPARAN_TEST_DATABASE_REQUIRED"] = "postgresql"
        with patch.dict(os.environ, environment):
            with self.assertRaisesRegex(AssertionError, "postgresql integration is required"):
                self.run_backend("postgresql")

    def run_backend(self, driver):
        prefix = f"SEPARAN_TEST_{driver.upper()}_"
        required = ("HOST", "DATABASE", "USER", "PASSWORD")
        settings = {key: os.environ.get(prefix + key) for key in required}
        missing = [key for key, value in settings.items() if not value]
        if missing:
            required_backends = {
                item.strip().lower()
                for item in os.environ.get("SEPARAN_TEST_DATABASE_REQUIRED", "").split(",")
                if item.strip()
            }
            if driver in required_backends:
                self.fail(f"{driver} integration is required but missing {prefix}{', '.join(missing)}")
            self.skipTest(f"set {prefix}HOST/DATABASE/USER/PASSWORD to enable this integration test")

        port = os.environ.get(prefix + "PORT")
        table = "separan_it_" + uuid.uuid4().hex[:16]
        options = [
            f'driver = "{driver}"',
            f'host = "{settings["HOST"]}"',
            f'database = "{settings["DATABASE"]}"',
            f'user = "{settings["USER"]}"',
            f'password = env_get("{prefix}PASSWORD")',
        ]
        if port:
            options.append(f"port = {int(port)}")
        source = f'''SEP:main
+db = db_connect({", ".join(options)})
+db_execute(db, "create table {table} (id integer primary key)", [])
+db_execute(db, "insert into {table} (id) values (?)", [1])
+db_begin(db)
+db_execute(db, "insert into {table} (id) values (?)", [2])
+db_rollback(db)
+print db_scalar(db, "select count(*) from {table}", [])
+try :duplicate
+db_execute(db, "insert into {table} (id) values (?)", [1])
+catch db_constraint_error :duplicate
+print "constraint"
+endtry:duplicate
+db_close(db)
+END_SEP:main
+'''.replace("\n+", "\n")
        capabilities = replace(
            RuntimeCapabilities.local(ROOT),
            database_drivers=frozenset({"sqlite", driver}),
        )
        try:
            output = execute(source, capabilities=capabilities)[1]
            self.assertEqual(output, "1\nconstraint\n")
        finally:
            cleanup = f'''SEP:main
+db = db_connect({", ".join(options)})
+db_execute(db, "drop table {table}", [])
+db_close(db)
+END_SEP:main
+'''.replace("\n+", "\n")
            execute(cleanup, capabilities=capabilities)

    def test_postgresql_real_server(self):
        self.run_backend("postgresql")

    def test_mysql_real_server(self):
        self.run_backend("mysql")

    def test_oracle_real_server(self):
        self.run_backend("oracle")


if __name__ == "__main__":
    unittest.main()
