"""Built-in SQLite adapter backed by Python's sqlite3 module."""

import re
import sqlite3
import time

from ..errors import AdapterError


class _Cursor:
    def __init__(self, cursor, connection, timed):
        self._cursor = cursor; self._connection = connection; self._timed = timed
    @property
    def description(self): return self._cursor.description
    @property
    def rowcount(self): return self._cursor.rowcount
    def fetchall(self): return self._cursor.fetchall()
    def close(self):
        if self._timed: self._connection.set_progress_handler(None, 0)
        self._cursor.close()


class SQLiteAdapter:
    name = "sqlite"
    driver_version = sqlite3.sqlite_version

    def connect(self, options, runtime, position):
        for forbidden in ("host", "port", "user", "password", "charset", "ssl", "mode"):
            if forbidden in options:
                raise AdapterError("db_driver_error", f"SQLite does not accept connection option '{forbidden}'.")
        database = options["database"]
        path = database if database == ":memory:" else str(runtime.capabilities.path(database, "db_connect", position))
        if database != ":memory:": runtime.capabilities.require(runtime.capabilities.write_files, "open SQLite database", position)
        try:
            native = sqlite3.connect(path, timeout=options["timeout_ms"] / 1000, isolation_level=None)
            native.execute("PRAGMA foreign_keys = ON")
            return native, database, None
        except sqlite3.Error as exc: raise AdapterError("db_connection_error", str(exc))

    def close(self, native):
        try: native.close()
        except sqlite3.Error as exc: raise AdapterError("db_connection_error", str(exc))

    def execute(self, native, sql, params, timeout_ms):
        deadline = None if timeout_ms is None else time.monotonic() + timeout_ms / 1000
        if deadline is not None: native.set_progress_handler(lambda: 1 if time.monotonic() >= deadline else 0, 1000)
        try: return _Cursor(native.execute(sql, params), native, deadline is not None)
        except sqlite3.IntegrityError as exc: raise AdapterError("db_constraint_error", str(exc))
        except sqlite3.OperationalError as exc:
            if deadline is not None and time.monotonic() >= deadline: raise AdapterError("db_timeout_error", "Database operation exceeded its timeout.")
            raise AdapterError("db_query_error", str(exc))
        except sqlite3.Error as exc: raise AdapterError("db_query_error", str(exc))

    def raise_query_error(self, exc):
        if isinstance(exc, sqlite3.IntegrityError): raise AdapterError("db_constraint_error", str(exc))
        raise AdapterError("db_query_error", str(exc))

    def begin(self, native):
        try: native.execute("BEGIN")
        except sqlite3.Error as exc: raise AdapterError("db_transaction_error", str(exc))
    def commit(self, native):
        try: native.execute("COMMIT")
        except sqlite3.Error as exc: raise AdapterError("db_transaction_error", str(exc))
    def rollback(self, native):
        try: native.execute("ROLLBACK")
        except sqlite3.Error as exc: raise AdapterError("db_transaction_error", str(exc))

    def _table(self, native, name):
        if type(name) is not str or not name: raise AdapterError("db_query_error", "DB metadata table name must be a non-empty string.")
        found = native.execute("select 1 from sqlite_schema where type = 'table' and name = ?", (name,)).fetchone()
        if found is None: raise AdapterError("db_query_error", f"Table '{name}' does not exist.")
        return '"' + name.replace('"', '""') + '"'

    def tables(self, native, **context):
        return [row[0] for row in native.execute("select name from sqlite_schema where type = 'table' and name not like 'sqlite_%' order by name")]
    def columns(self, native, name, **context):
        table = self._table(native, name); result = []
        for row in native.execute(f"PRAGMA table_info({table})"):
            declared = row[2] or ""; match = re.search(r"\((\d+)\)", declared)
            result.append({"name": row[1], "type": declared, "nullable": not bool(row[3]) and not bool(row[5]), "default": row[4], "length": None if match is None else int(match.group(1))})
        return result
    def indexes(self, native, name, **context):
        table = self._table(native, name); result = []
        for row in native.execute(f"PRAGMA index_list({table})"):
            index_name = row[1]; quoted = '"' + index_name.replace('"', '""') + '"'
            columns = [item[2] for item in native.execute(f"PRAGMA index_info({quoted})")]
            result.append({"name": index_name, "columns": columns, "unique": bool(row[2]), "primary": row[3] == "pk", "type": "btree"})
        return sorted(result, key=lambda item: item["name"])
    def primary_key(self, native, name, **context):
        table = self._table(native, name)
        fields = sorted(((row[5], row[1]) for row in native.execute(f"PRAGMA table_info({table})") if row[5]), key=lambda item: item[0])
        return None if not fields else {"name": None, "columns": [name for _, name in fields]}
    def server_info(self, native, database, host, **context):
        return {"driver": self.name, "driver_version": self.driver_version, "server_version": sqlite3.sqlite_version, "database_name": database, "server_host": host, "mode": None}
    def version(self, native, **context): return sqlite3.sqlite_version


ADAPTER = SQLiteAdapter()
