"""Optional MySQL adapter backed by Oracle MySQL Connector/Python."""

from ._dbapi import DbApiAdapter, package_version
from ..errors import AdapterError, DriverNotInstalled


class MySQLAdapter(DbApiAdapter):
    name = "mysql"
    def connect(self, options, runtime, position):
        try: import mysql.connector
        except ImportError: raise DriverNotInstalled(self.name, "mysql")
        if "mode" in options: raise AdapterError("db_driver_error", "MySQL does not accept connection option 'mode'.")
        kwargs = {"database": options["database"], "connection_timeout": max(1, (options["timeout_ms"] + 999) // 1000)}
        for key in ("host", "port", "user", "password", "charset"):
            if key in options: kwargs[key] = options[key]
        if "ssl" in options: kwargs["ssl_disabled"] = not options["ssl"]
        try:
            native = mysql.connector.connect(**kwargs); native.autocommit = True
            self.module = mysql.connector; self.driver_version = package_version("mysql-connector-python")
            return native, options["database"], options.get("host")
        except Exception as exc:
            category = "db_auth_error" if "access denied" in str(exc).lower() else "db_connection_error"
            raise AdapterError(category, str(exc))
    def apply_timeout(self, native, cursor, timeout_ms):
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (timeout_ms or 0,))
    def tables(self, native, **context):
        return [row[0] for row in self._all(native, "select table_name from information_schema.tables where table_schema = database() and table_type = 'BASE TABLE' order by table_name")]
    def columns(self, native, name, **context):
        rows = self._all(native, "select column_name, column_type, is_nullable, column_default, character_maximum_length from information_schema.columns where table_schema = database() and table_name = %s order by ordinal_position", (name,))
        if not rows: raise AdapterError("db_query_error", f"Table '{name}' does not exist.")
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3], "length": r[4]} for r in rows]
    def indexes(self, native, name, **context):
        rows = self._all(native, "select index_name, column_name, non_unique, index_type from information_schema.statistics where table_schema = database() and table_name = %s order by index_name, seq_in_index", (name,))
        grouped = {}
        for index, column, non_unique, kind in rows:
            item = grouped.setdefault(index, {"name": index, "columns": [], "unique": not bool(non_unique), "primary": index == "PRIMARY", "type": kind.lower()})
            item["columns"].append(column)
        return [grouped[key] for key in sorted(grouped)]
    def primary_key(self, native, name, **context):
        rows = self._all(native, "select constraint_name, column_name from information_schema.key_column_usage where table_schema = database() and table_name = %s and constraint_name = 'PRIMARY' order by ordinal_position", (name,))
        return None if not rows else {"name": rows[0][0], "columns": [r[1] for r in rows]}
    def server_info(self, native, database, host, **context):
        return {"driver": self.name, "driver_version": self.driver_version, "server_version": native.get_server_info(), "database_name": database, "server_host": host, "mode": None}


ADAPTER = MySQLAdapter()
