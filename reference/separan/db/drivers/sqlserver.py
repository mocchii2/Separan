"""Optional Microsoft SQL Server adapter backed by pyodbc."""

from ._dbapi import DbApiAdapter, package_version
from ..errors import AdapterError, DriverNotInstalled


def _odbc_value(value):
    return "{" + str(value).replace("}", "}}") + "}"


class SQLServerAdapter(DbApiAdapter):
    name = "sqlserver"
    placeholder_style = "qmark"

    def connect(self, options, runtime, position):
        try: import pyodbc
        except ImportError: raise DriverNotInstalled(self.name, "sqlserver")
        if hasattr(pyodbc, "drivers") and "ODBC Driver 18 for SQL Server" not in pyodbc.drivers():
            raise AdapterError("db_driver_error", "Microsoft ODBC Driver 18 for SQL Server is not installed on this host.")
        for unsupported in ("charset", "mode"):
            if unsupported in options:
                raise AdapterError("db_driver_error", f"SQL Server does not accept connection option '{unsupported}'.")
        host = options.get("host", ".\\SQLEXPRESS")
        if "port" in options:
            host = f"{host},{options['port']}"
        base_host = host.split(",", 1)[0].lower()
        local_host = base_host in (".", "(local)", "localhost", "127.0.0.1", "::1") or base_host.startswith((".\\", "localhost\\"))
        parts = [
            "DRIVER={ODBC Driver 18 for SQL Server}",
            f"SERVER={_odbc_value(host)}",
            f"DATABASE={_odbc_value(options['database'])}",
            "Encrypt=yes" if options.get("ssl", True) else "Encrypt=no",
            "TrustServerCertificate=yes" if local_host else "TrustServerCertificate=no",
        ]
        user = options.get("user")
        password = options.get("password")
        if user is None and password is None:
            parts.append("Trusted_Connection=yes")
            auth_mode = "windows"
        elif type(user) is str and type(password) is str:
            parts.extend((f"UID={_odbc_value(user)}", f"PWD={_odbc_value(password)}"))
            auth_mode = "password"
        else:
            raise AdapterError("db_auth_error", "SQL Server requires both user and password, or neither for Windows authentication.")
        try:
            native = pyodbc.connect(";".join(parts), timeout=max(1, (options["timeout_ms"] + 999) // 1000), autocommit=True)
            self.module = pyodbc
            self.driver_version = package_version("pyodbc")
            self.auth_mode = auth_mode
            return native, options["database"], host
        except Exception as exc:
            text = str(exc)
            lowered = text.lower()
            category = "db_auth_error" if "login failed" in lowered or "28000" in text else "db_connection_error"
            raise AdapterError(category, text)

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
        native.timeout = 0 if timeout_ms is None else max(1, (timeout_ms + 999) // 1000)

    def tables(self, native, **context):
        return [row[0] for row in self._all(native, "select table_name from information_schema.tables where table_schema = schema_name() and table_type = 'BASE TABLE' order by table_name")]

    def columns(self, native, name, **context):
        rows = self._all(native, "select column_name, data_type, is_nullable, column_default, character_maximum_length from information_schema.columns where table_schema = schema_name() and table_name = ? order by ordinal_position", (name,))
        if not rows: raise AdapterError("db_query_error", f"Table '{name}' does not exist.")
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3], "length": r[4]} for r in rows]

    def indexes(self, native, name, **context):
        rows = self._all(native, "select i.name, c.name, i.is_unique, i.is_primary_key, i.type_desc from sys.indexes i join sys.index_columns ic on ic.object_id = i.object_id and ic.index_id = i.index_id join sys.columns c on c.object_id = ic.object_id and c.column_id = ic.column_id where i.object_id = object_id(?) and i.name is not null order by i.name, ic.key_ordinal", (name,))
        grouped = {}
        for index, column, unique, primary, kind in rows:
            item = grouped.setdefault(index, {"name": index, "columns": [], "unique": bool(unique), "primary": bool(primary), "type": kind.lower()})
            item["columns"].append(column)
        return [grouped[key] for key in sorted(grouped)]

    def primary_key(self, native, name, **context):
        rows = self._all(native, "select kc.name, c.name from sys.key_constraints kc join sys.index_columns ic on ic.object_id = kc.parent_object_id and ic.index_id = kc.unique_index_id join sys.columns c on c.object_id = ic.object_id and c.column_id = ic.column_id where kc.parent_object_id = object_id(?) and kc.type = 'PK' order by ic.key_ordinal", (name,))
        return None if not rows else {"name": rows[0][0], "columns": [row[1] for row in rows]}

    def server_info(self, native, database, host, **context):
        row = self._all(native, "select cast(serverproperty('ProductVersion') as nvarchar(30))")[0]
        return {"driver": self.name, "driver_version": self.driver_version, "server_version": row[0], "database_name": database, "server_host": host, "mode": self.auth_mode}


ADAPTER = SQLServerAdapter()
