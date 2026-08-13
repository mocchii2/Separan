"""Optional Oracle adapter backed by python-oracledb."""

from ._dbapi import DbApiAdapter, package_version
from ..errors import AdapterError, DriverNotInstalled


class OracleAdapter(DbApiAdapter):
    name = "oracle"
    placeholder_style = "numeric"

    def connect(self, options, runtime, position):
        try: import oracledb
        except ImportError: raise DriverNotInstalled(self.name, "oracle")
        for unsupported in ("charset", "ssl"):
            if unsupported in options: raise AdapterError("db_driver_error", f"Oracle does not accept connection option '{unsupported}'.")
        mode = options.get("mode", "thin")
        if mode not in ("thin", "thick"): raise AdapterError("db_driver_error", "Oracle mode must be 'thin' or 'thick'.")
        try:
            if mode == "thick" and oracledb.is_thin_mode(): oracledb.init_oracle_client()
            host = options.get("host")
            dsn = options["database"]
            if host:
                port = options.get("port", 1521)
                dsn = oracledb.makedsn(host, port, service_name=options["database"])
            kwargs = {"dsn": dsn, "tcp_connect_timeout": options["timeout_ms"] / 1000}
            for key in ("user", "password"):
                if key in options: kwargs[key] = options[key]
            native = oracledb.connect(**kwargs); native.autocommit = True
            self.module = oracledb; self.driver_version = package_version("oracledb"); self.mode = mode
            return native, options["database"], host
        except Exception as exc:
            category = "db_auth_error" if "ORA-01017" in str(exc) else "db_connection_error"
            raise AdapterError(category, str(exc))

    def begin(self, native):
        try: native.autocommit = False
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))
    def commit(self, native):
        try: native.commit(); native.autocommit = True
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))
    def rollback(self, native):
        try: native.rollback(); native.autocommit = True
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))
    def apply_timeout(self, native, cursor, timeout_ms):
        native.call_timeout = timeout_ms or 0
    def tables(self, native, **context):
        return [row[0] for row in self._all(native, "select table_name from user_tables order by table_name")]
    def columns(self, native, name, **context):
        rows = self._all(native, "select column_name, data_type, nullable, data_default, data_length from user_tab_columns where table_name = :1 order by column_id", (name.upper(),))
        if not rows: raise AdapterError("db_query_error", f"Table '{name}' does not exist.")
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "Y", "default": r[3], "length": r[4]} for r in rows]
    def indexes(self, native, name, **context):
        rows = self._all(native, "select i.index_name, c.column_name, i.uniqueness, i.index_type from user_indexes i join user_ind_columns c on c.index_name = i.index_name where i.table_name = :1 order by i.index_name, c.column_position", (name.upper(),))
        grouped = {}
        for index, column, uniqueness, kind in rows:
            item = grouped.setdefault(index, {"name": index, "columns": [], "unique": uniqueness == "UNIQUE", "primary": False, "type": kind.lower()})
            item["columns"].append(column)
        primary = self.primary_key(native, name)
        if primary:
            for item in grouped.values(): item["primary"] = item["name"] == primary["name"]
        return [grouped[key] for key in sorted(grouped)]
    def primary_key(self, native, name, **context):
        rows = self._all(native, "select c.constraint_name, cc.column_name from user_constraints c join user_cons_columns cc on cc.constraint_name = c.constraint_name where c.table_name = :1 and c.constraint_type = 'P' order by cc.position", (name.upper(),))
        return None if not rows else {"name": rows[0][0], "columns": [r[1] for r in rows]}
    def server_info(self, native, database, host, **context):
        return {"driver": self.name, "driver_version": self.driver_version, "server_version": native.version, "database_name": database, "server_host": host, "mode": self.mode}


ADAPTER = OracleAdapter()
