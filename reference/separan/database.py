"""Driver-separated, capability-gated database API; SQLite reference driver."""

from dataclasses import dataclass
from datetime import date as PyDate, datetime as PyDateTime
import sqlite3
import time
import re

from .auth import SecretValue
from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction
from .temporal import DatetimeValue, DurationValue, format_datetime


@dataclass(eq=False)
class DbConnectionValue:
    driver: str
    database: str
    native: object
    closed: bool = False
    transaction_active: bool = False

    def __eq__(self, other): return self is other


def _connect(args, named, position, runtime):
    driver = named.get("driver")
    if type(driver) is not str or driver not in ("sqlite", "postgresql", "mysql", "oracle"):
        raise error("E900", "db_driver_error", "db_connect() requires a known driver.", position, actual=repr(driver))
    runtime.capabilities.require(runtime.capabilities.database, "database access", position)
    if driver not in runtime.capabilities.database_drivers:
        raise error("E900", "db_driver_error", f"Database driver '{driver}' is not allowed or installed in this host.", position, actual=driver)
    if driver != "sqlite": raise error("E900", "db_driver_error", f"Reference driver '{driver}' is not installed.", position, actual=driver)
    unknown = set(named) - {"driver", "host", "port", "database", "user", "password", "timeout", "charset", "ssl"}
    if unknown: raise error("E207", "Unknown named argument", f"db_connect() does not accept '{sorted(unknown)[0]}'.", position, actual=sorted(unknown)[0])
    database = named.get("database")
    if type(database) is not str or not database: runtime.type_error(position, "non-empty database string", runtime.type_name(database), "SQLite db_connect() requires database.")
    for forbidden in ("host", "port", "user", "password", "charset", "ssl"):
        if forbidden in named: raise error("E900", "db_driver_error", f"SQLite does not accept connection option '{forbidden}'.", position, actual=forbidden)
    timeout = named.get("timeout", DurationValue(5_000))
    if not isinstance(timeout, DurationValue) or timeout.milliseconds < 0: runtime.type_error(position, "non-negative duration", runtime.type_name(timeout), "db_connect() timeout must be a non-negative duration.")
    path = database if database == ":memory:" else str(runtime.capabilities.path(database, "db_connect", position))
    if database != ":memory:": runtime.capabilities.require(runtime.capabilities.write_files, "open SQLite database", position)
    try:
        native = sqlite3.connect(path, timeout=timeout.milliseconds / 1000, isolation_level=None)
        native.row_factory = sqlite3.Row
        native.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error as exc: raise error("E901", "db_connection_error", str(exc), position, actual=database)
    value = DbConnectionValue(driver, database, native); runtime.database_connections.append(value); return value


def _connection(value, position, runtime):
    if not isinstance(value, DbConnectionValue): runtime.type_error(position, "db_connection", runtime.type_name(value), "Database function requires a connection.")
    if value.closed: raise error("E901", "db_connection_error", "Database connection is closed.", position)
    return value


def _close(args, named, position, runtime):
    value = args[0]
    if not isinstance(value, DbConnectionValue): runtime.type_error(position, "db_connection", runtime.type_name(value), "db_close() requires a connection.")
    if value.closed: return None
    try: value.native.close(); value.closed = True; value.transaction_active = False
    except sqlite3.Error as exc: raise error("E901", "db_connection_error", str(exc), position)
    return None


def _parameter(value, position, runtime):
    if value is None or type(value) in (str, int, float): return value
    if type(value) is bool: return 1 if value else 0
    if isinstance(value, BytesValue): return value.value
    if isinstance(value, DatetimeValue): return format_datetime(value)
    if isinstance(value, SecretValue): raise error("E903", "db_query_error", "secret values cannot be bound as ordinary SQL data.", position)
    runtime.type_error(position, "SQL scalar parameter", runtime.type_name(value), "DB parameters must be explicit SQL scalar values.")


def _params(value, position, runtime):
    if type(value) is list: return tuple(_parameter(item, position, runtime) for item in value)
    if isinstance(value, ObjectValue): return {key: _parameter(item, position, runtime) for key, item in value.fields.items()}
    runtime.type_error(position, "list or object parameters", runtime.type_name(value), "DB parameters must use positional list or named object binding.")


def _timeout(named, position, runtime):
    value = named.get("timeout")
    if value is None: return None
    if not isinstance(value, DurationValue) or value.milliseconds < 0: runtime.type_error(position, "non-negative duration", runtime.type_name(value), "DB query timeout must be a non-negative duration.")
    return time.monotonic() + value.milliseconds / 1000


def _run(connection, sql, params, named, position, runtime):
    db = _connection(connection, position, runtime)
    if type(sql) is not str or not sql.strip(): runtime.type_error(position, "non-empty SQL string", runtime.type_name(sql), "Database SQL must be a non-empty string.")
    bound = _params(params, position, runtime); deadline = _timeout(named, position, runtime)
    if deadline is not None: db.native.set_progress_handler(lambda: 1 if time.monotonic() >= deadline else 0, 1000)
    try: return db, db.native.execute(sql, bound), deadline
    except sqlite3.IntegrityError as exc: raise error("E904", "db_constraint_error", str(exc), position)
    except sqlite3.OperationalError as exc:
        if deadline is not None and time.monotonic() >= deadline: raise error("E905", "db_timeout_error", "Database operation exceeded its timeout.", position)
        raise error("E903", "db_query_error", str(exc), position)
    except sqlite3.Error as exc: raise error("E903", "db_query_error", str(exc), position)


def _clear_timeout(db, deadline):
    if deadline is not None: db.native.set_progress_handler(None, 0)


def _result(value):
    if isinstance(value, bytes): return BytesValue(value)
    if isinstance(value, (PyDateTime, PyDate)): return value.isoformat()
    return value


def _query(mode):
    def implementation(args, named, position, runtime):
        db, cursor, deadline = _run(*args, named, position, runtime)
        try: rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            if deadline is not None and time.monotonic() >= deadline: raise error("E905", "db_timeout_error", "Database operation exceeded its timeout.", position)
            raise error("E903", "db_query_error", str(exc), position)
        finally: _clear_timeout(db, deadline)
        if mode == "scalar": return None if not rows else _result(rows[0][0])
        values = [ObjectValue.create({key: _result(row[key]) for key in row.keys()}) for row in rows]
        if mode == "one":
            if len(values) > 1: raise error("E906", "db_query_error", "db_query_one() returned more than one row.", position, actual=str(len(values)))
            return None if not values else values[0]
        return values
    return implementation


def _execute(args, named, position, runtime):
    db, cursor, deadline = _run(*args, named, position, runtime)
    try: return max(cursor.rowcount, 0)
    finally: _clear_timeout(db, deadline)


def begin(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if db.transaction_active: raise error("E907", "db_transaction_error", "Transaction already active.", position)
    try: db.native.execute("BEGIN"); db.transaction_active = True
    except sqlite3.Error as exc: raise error("E907", "db_transaction_error", str(exc), position)
    return None


def commit(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if not db.transaction_active: raise error("E907", "db_transaction_error", "No active transaction to commit.", position)
    try: db.native.execute("COMMIT"); db.transaction_active = False
    except sqlite3.Error as exc: raise error("E907", "db_transaction_error", str(exc), position)
    return None


def rollback(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if not db.transaction_active: raise error("E907", "db_transaction_error", "No active transaction to roll back.", position)
    try: db.native.execute("ROLLBACK"); db.transaction_active = False
    except sqlite3.Error as exc: raise error("E907", "db_transaction_error", str(exc), position)
    return None


def _begin(args, named, position, runtime): return begin(args[0], position, runtime)
def _commit(args, named, position, runtime): return commit(args[0], position, runtime)
def _rollback(args, named, position, runtime): return rollback(args[0], position, runtime)


def _table(connection, name, position, runtime):
    db = _connection(connection, position, runtime)
    if type(name) is not str or not name: runtime.type_error(position, "non-empty table name", runtime.type_name(name), "DB metadata table name must be a non-empty string.")
    found = db.native.execute("select 1 from sqlite_schema where type = 'table' and name = ?", (name,)).fetchone()
    if found is None: raise error("E903", "db_query_error", f"Table '{name}' does not exist.", position, actual=name)
    return db, '"' + name.replace('"', '""') + '"'


def _tables(args, named, position, runtime):
    db = _connection(args[0], position, runtime)
    return [row[0] for row in db.native.execute("select name from sqlite_schema where type = 'table' and name not like 'sqlite_%' order by name")]


def _columns(args, named, position, runtime):
    db, table = _table(args[0], args[1], position, runtime); result = []
    for row in db.native.execute(f"PRAGMA table_info({table})"):
        declared = row[2] or ""; match = re.search(r"\((\d+)\)", declared)
        result.append(ObjectValue.create({"name": row[1], "type": declared, "nullable": not bool(row[3]) and not bool(row[5]), "default": row[4], "length": None if match is None else int(match.group(1))}))
    return result


def _indexes(args, named, position, runtime):
    db, table = _table(args[0], args[1], position, runtime); result = []
    for row in db.native.execute(f"PRAGMA index_list({table})"):
        index_name = row[1]; quoted = '"' + index_name.replace('"', '""') + '"'
        columns = [item[2] for item in db.native.execute(f"PRAGMA index_info({quoted})")]
        result.append(ObjectValue.create({"name": index_name, "columns": columns, "unique": bool(row[2]), "primary": row[3] == "pk", "type": "btree"}))
    return sorted(result, key=lambda item: item.fields["name"])


def _primary_key(args, named, position, runtime):
    db, table = _table(args[0], args[1], position, runtime)
    fields = sorted(((row[5], row[1]) for row in db.native.execute(f"PRAGMA table_info({table})") if row[5]), key=lambda item: item[0])
    return None if not fields else ObjectValue.create({"name": None, "columns": [name for _, name in fields]})


def _server_info(args, named, position, runtime):
    db = _connection(args[0], position, runtime)
    return ObjectValue.create({"driver": "sqlite", "server_version": sqlite3.sqlite_version, "database_name": db.database, "server_host": None})


def _version(args, named, position, runtime): _connection(args[0], position, runtime); return sqlite3.sqlite_version


DB_BUILTINS = (
    UtilityFunction("db_connect", 0, 0, _connect, ("driver", "host", "port", "database", "user", "password", "timeout", "charset", "ssl")),
    UtilityFunction("db_close", 1, 1, _close),
    UtilityFunction("db_query", 3, 3, _query("all"), ("timeout",)),
    UtilityFunction("db_query_one", 3, 3, _query("one"), ("timeout",)),
    UtilityFunction("db_scalar", 3, 3, _query("scalar"), ("timeout",)),
    UtilityFunction("db_execute", 3, 3, _execute, ("timeout",)),
    UtilityFunction("db_begin", 1, 1, _begin), UtilityFunction("db_commit", 1, 1, _commit), UtilityFunction("db_rollback", 1, 1, _rollback),
    UtilityFunction("db_tables", 1, 1, _tables), UtilityFunction("db_columns", 2, 2, _columns),
    UtilityFunction("db_indexes", 2, 2, _indexes), UtilityFunction("db_primary_key", 2, 2, _primary_key),
    UtilityFunction("db_server_info", 1, 1, _server_info), UtilityFunction("db_version", 1, 1, _version),
)
