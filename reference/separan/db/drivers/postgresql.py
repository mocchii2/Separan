"""Optional PostgreSQL adapter backed by Psycopg 3."""

from ._dbapi import DbApiAdapter, package_version
from ..errors import AdapterError, DriverNotInstalled


class PostgreSQLAdapter(DbApiAdapter):
    name = "postgresql"
    def connect(self, options, runtime, position):
        try: import psycopg
        except ImportError: raise DriverNotInstalled(self.name, "postgresql")
        for unsupported in ("charset", "mode"):
            if unsupported in options: raise AdapterError("db_driver_error", f"PostgreSQL does not accept connection option '{unsupported}'.")
        kwargs = {"dbname": options["database"], "connect_timeout": max(1, (options["timeout_ms"] + 999) // 1000)}
        for source, target in (("host", "host"), ("port", "port"), ("user", "user"), ("password", "password")):
            if source in options: kwargs[target] = options[source]
        if "ssl" in options: kwargs["sslmode"] = "require" if options["ssl"] else "disable"
        try:
            native = psycopg.connect(**kwargs); native.autocommit = True
            self.module = psycopg; self.driver_version = package_version("psycopg")
            return native, options["database"], options.get("host")
        except Exception as exc:
            category = "db_auth_error" if "auth" in str(exc).lower() or "password" in str(exc).lower() else "db_connection_error"
            raise AdapterError(category, str(exc))
    def apply_timeout(self, native, cursor, timeout_ms):
        cursor.execute("select set_config('statement_timeout', %s, false)", (str(timeout_ms or 0),))
    def tables(self, native, **context):
        return [row[0] for row in self._all(native, "select table_name from information_schema.tables where table_schema = current_schema() and table_type = 'BASE TABLE' order by table_name")]
    def columns(self, native, name, **context):
        rows = self._all(native, "select column_name, data_type, is_nullable, column_default, character_maximum_length from information_schema.columns where table_schema = current_schema() and table_name = %s order by ordinal_position", (name,))
        if not rows: raise AdapterError("db_query_error", f"Table '{name}' does not exist.")
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3], "length": r[4]} for r in rows]
    def indexes(self, native, name, **context):
        rows = self._all(native, "select ci.relname, array_agg(a.attname order by keys.ordinality), ix.indisunique, ix.indisprimary, am.amname from pg_class t join pg_namespace ns on ns.oid = t.relnamespace join pg_index ix on ix.indrelid = t.oid join pg_class ci on ci.oid = ix.indexrelid join pg_am am on am.oid = ci.relam join lateral unnest(ix.indkey) with ordinality keys(attnum, ordinality) on true join pg_attribute a on a.attrelid = t.oid and a.attnum = keys.attnum where ns.nspname = current_schema() and t.relname = %s group by ci.relname, ix.indisunique, ix.indisprimary, am.amname order by ci.relname", (name,))
        return [{"name": r[0], "columns": list(r[1]), "unique": bool(r[2]), "primary": bool(r[3]), "type": r[4]} for r in rows]
    def primary_key(self, native, name, **context):
        rows = self._all(native, "select kcu.constraint_name, kcu.column_name from information_schema.table_constraints tc join information_schema.key_column_usage kcu using (constraint_catalog, constraint_schema, constraint_name) where tc.table_schema = current_schema() and tc.table_name = %s and tc.constraint_type = 'PRIMARY KEY' order by kcu.ordinal_position", (name,))
        return None if not rows else {"name": rows[0][0], "columns": [r[1] for r in rows]}
    def server_info(self, native, database, host, **context):
        server_version = native.info.parameter_status("server_version") or str(native.info.server_version)
        return {"driver": self.name, "driver_version": self.driver_version, "server_version": server_version, "database_name": database, "server_host": host, "mode": None}


ADAPTER = PostgreSQLAdapter()
