"""Shared mechanics for optional Python DB-API adapters."""

from importlib.metadata import PackageNotFoundError, version

from ..errors import AdapterError


def package_version(name):
    try: return version(name)
    except PackageNotFoundError: return "unknown"


class DbApiAdapter:
    placeholder_style = "format"

    def close(self, native):
        try: native.close()
        except Exception as exc: raise AdapterError("db_connection_error", str(exc))

    def execute(self, native, sql, params, timeout_ms):
        from ..core import rewrite_qmark_placeholders
        statement = rewrite_qmark_placeholders(sql, self.placeholder_style) if not isinstance(params, dict) else sql
        cursor = native.cursor()
        try:
            self.apply_timeout(native, cursor, timeout_ms)
            cursor.execute(statement, params)
            return cursor
        except Exception as exc:
            try: cursor.close()
            except Exception: pass
            self.raise_query_error(exc)

    def apply_timeout(self, native, cursor, timeout_ms):
        return None

    def raise_query_error(self, exc):
        name = type(exc).__name__.lower()
        text = str(exc)
        if any(word in name for word in ("integrity", "constraint", "unique")):
            raise AdapterError("db_constraint_error", text)
        if any(word in name for word in ("timeout", "cancel")):
            raise AdapterError("db_timeout_error", text)
        raise AdapterError("db_query_error", text)

    def begin(self, native):
        try:
            cursor = native.cursor(); cursor.execute("BEGIN"); cursor.close()
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))
    def commit(self, native):
        try:
            cursor = native.cursor(); cursor.execute("COMMIT"); cursor.close()
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))
    def rollback(self, native):
        try:
            cursor = native.cursor(); cursor.execute("ROLLBACK"); cursor.close()
        except Exception as exc: raise AdapterError("db_transaction_error", str(exc))

    def _all(self, native, sql, params=()):
        cursor = native.cursor()
        try: cursor.execute(sql, params); return cursor.fetchall()
        except Exception as exc: self.raise_query_error(exc)
        finally: cursor.close()

    def version(self, native, **context): return self.server_info(native, **context)["server_version"]
