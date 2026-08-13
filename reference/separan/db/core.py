"""Driver-neutral, capability-gated database API."""

from dataclasses import dataclass
from datetime import date as PyDate, datetime as PyDateTime

from ..auth import SecretValue
from ..errors import error
from ..objects import ObjectValue
from ..randomness import BytesValue
from ..system_utilities import UtilityFunction
from ..temporal import DatetimeValue, DurationValue, format_datetime
from .errors import AdapterError
from .registry import get_driver, known_drivers


@dataclass(eq=False)
class DbConnectionValue:
    driver: str
    database: str
    native: object
    adapter: object
    host: str | None = None
    closed: bool = False
    transaction_active: bool = False

    def __eq__(self, other):
        return self is other


def scan_qmark_placeholders(sql):
    """Return qmark offsets outside SQL literals, identifiers, and comments."""
    offsets = []
    index = 0
    state = "code"
    dollar_tag = None
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "code":
            if char == "'": state = "single"
            elif char == '"': state = "double"
            elif char == "`": state = "backtick"
            elif char == "[": state = "bracket"
            elif char == "-" and next_char == "-": state = "line_comment"; index += 1
            elif char == "/" and next_char == "*": state = "block_comment"; index += 1
            elif char == "$":
                end = sql.find("$", index + 1)
                if end >= 0 and all(item == "_" or item.isalnum() for item in sql[index + 1:end]):
                    dollar_tag = sql[index:end + 1]; state = "dollar"; index = end
            elif char == "?": offsets.append(index)
        elif state == "single":
            if char == "'" and next_char == "'": index += 1
            elif char == "'": state = "code"
        elif state == "double":
            if char == '"' and next_char == '"': index += 1
            elif char == '"': state = "code"
        elif state == "backtick":
            if char == "`" and next_char == "`": index += 1
            elif char == "`": state = "code"
        elif state == "bracket":
            if char == "]" and next_char == "]": index += 1
            elif char == "]": state = "code"
        elif state == "line_comment":
            if char in "\r\n": state = "code"
        elif state == "block_comment":
            if char == "*" and next_char == "/": state = "code"; index += 1
        elif state == "dollar" and sql.startswith(dollar_tag, index):
            index += len(dollar_tag) - 1; state = "code"; dollar_tag = None
        index += 1
    return offsets


def rewrite_qmark_placeholders(sql, style):
    offsets = scan_qmark_placeholders(sql)
    if not offsets or style == "qmark":
        return sql
    output = []
    start = 0
    for number, offset in enumerate(offsets, 1):
        output.append(sql[start:offset])
        output.append("%s" if style == "format" else f":{number}")
        start = offset + 1
    output.append(sql[start:])
    return "".join(output)


def _raise_adapter(exc, position, actual=None):
    codes = {
        "db_driver_error": "E900", "db_connection_error": "E901",
        "db_auth_error": "E902", "db_query_error": "E903",
        "db_constraint_error": "E904", "db_timeout_error": "E905",
        "db_transaction_error": "E907",
    }
    raise error(codes.get(exc.category, "E903"), exc.category, exc.message, position, actual=actual)


def _connect(args, named, position, runtime):
    unknown = set(named) - {"driver", "host", "port", "database", "user", "password", "timeout", "charset", "ssl", "mode"}
    if unknown:
        name = sorted(unknown)[0]
        raise error("E207", "Unknown named argument", f"db_connect() does not accept '{name}'.", position, actual=name)
    driver = named.get("driver")
    if type(driver) is not str or driver not in known_drivers():
        raise error("E900", "db_driver_error", "db_connect() requires a known driver.", position, actual=repr(driver))
    runtime.capabilities.require(runtime.capabilities.database, "database access", position)
    if driver not in runtime.capabilities.database_drivers:
        raise error("E900", "db_driver_error", f"Database driver '{driver}' is not allowed by this host.", position, actual=driver)
    database = named.get("database")
    if type(database) is not str or not database:
        runtime.type_error(position, "non-empty database string", runtime.type_name(database), "db_connect() requires database.")
    timeout = named.get("timeout", DurationValue(5_000))
    if not isinstance(timeout, DurationValue) or timeout.milliseconds < 0:
        runtime.type_error(position, "non-negative duration", runtime.type_name(timeout), "db_connect() timeout must be a non-negative duration.")
    options = dict(named)
    options["timeout_ms"] = timeout.milliseconds
    password = options.get("password")
    if isinstance(password, SecretValue):
        try: options["password"] = password.value.decode("utf-8")
        except UnicodeDecodeError: raise error("E902", "db_auth_error", "Database password secret must be UTF-8 text.", position)
    elif password is not None and type(password) is not str:
        runtime.type_error(position, "secret or string password", runtime.type_name(password), "db_connect() password must be explicit text or secret.")
    adapter = get_driver(driver)
    try:
        native, canonical_database, host = adapter.connect(options, runtime, position)
    except AdapterError as exc:
        _raise_adapter(exc, position, driver)
    value = DbConnectionValue(driver, canonical_database, native, adapter, host)
    runtime.database_connections.append(value)
    return value


def _connection(value, position, runtime):
    if not isinstance(value, DbConnectionValue):
        runtime.type_error(position, "db_connection", runtime.type_name(value), "Database function requires a connection.")
    if value.closed:
        raise error("E901", "db_connection_error", "Database connection is closed.", position)
    return value


def _close(args, named, position, runtime):
    value = args[0]
    if not isinstance(value, DbConnectionValue):
        runtime.type_error(position, "db_connection", runtime.type_name(value), "db_close() requires a connection.")
    if value.closed: return None
    try: value.adapter.close(value.native)
    except AdapterError as exc: _raise_adapter(exc, position)
    value.closed = True; value.transaction_active = False
    return None


def _parameter(value, position, runtime):
    if value is None or type(value) in (str, int, float): return value
    if type(value) is bool: return value
    if isinstance(value, BytesValue): return value.value
    if isinstance(value, DatetimeValue): return format_datetime(value)
    if isinstance(value, SecretValue):
        raise error("E903", "db_query_error", "secret values cannot be bound as ordinary SQL data.", position)
    runtime.type_error(position, "SQL scalar parameter", runtime.type_name(value), "DB parameters must be explicit SQL scalar values.")


def _params(value, sql, position, runtime):
    if type(value) is list: return tuple(_parameter(item, position, runtime) for item in value)
    if isinstance(value, ObjectValue):
        converted = {key: _parameter(item, position, runtime) for key, item in value.fields.items()}
        if scan_qmark_placeholders(sql): return tuple(converted.values())
        return converted
    runtime.type_error(position, "list or object parameters", runtime.type_name(value), "DB parameters must use positional list or named object binding.")


def _run(connection, sql, params, named, position, runtime):
    db = _connection(connection, position, runtime)
    if type(sql) is not str or not sql.strip():
        runtime.type_error(position, "non-empty SQL string", runtime.type_name(sql), "Database SQL must be a non-empty string.")
    timeout = named.get("timeout")
    if timeout is not None and (not isinstance(timeout, DurationValue) or timeout.milliseconds < 0):
        runtime.type_error(position, "non-negative duration", runtime.type_name(timeout), "DB query timeout must be a non-negative duration.")
    try: return db, db.adapter.execute(db.native, sql, _params(params, sql, position, runtime), None if timeout is None else timeout.milliseconds)
    except AdapterError as exc: _raise_adapter(exc, position)


def _result(value):
    if isinstance(value, bytes): return BytesValue(value)
    if isinstance(value, (PyDateTime, PyDate)): return value.isoformat()
    return value


def _rows(cursor):
    names = [item[0] for item in (cursor.description or ())]
    return [ObjectValue.create({name: _result(value) for name, value in zip(names, row)}) for row in cursor.fetchall()]


def _query(mode):
    def implementation(args, named, position, runtime):
        db, cursor = _run(*args, named, position, runtime)
        try: values = _rows(cursor)
        except Exception as exc:
            try: db.adapter.raise_query_error(exc)
            except AdapterError as translated: _raise_adapter(translated, position)
        finally: cursor.close()
        if mode == "scalar":
            if not values: return None
            return next(iter(values[0].fields.values()))
        if mode == "one":
            if len(values) > 1: raise error("E906", "db_query_error", "db_query_one() returned more than one row.", position, actual=str(len(values)))
            return None if not values else values[0]
        return values
    return implementation


def _execute(args, named, position, runtime):
    _, cursor = _run(*args, named, position, runtime)
    try: return max(cursor.rowcount, 0)
    finally: cursor.close()


def begin(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if db.transaction_active: raise error("E907", "db_transaction_error", "Transaction already active.", position)
    try: db.adapter.begin(db.native)
    except AdapterError as exc: _raise_adapter(exc, position)
    db.transaction_active = True


def commit(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if not db.transaction_active: raise error("E907", "db_transaction_error", "No active transaction to commit.", position)
    try: db.adapter.commit(db.native)
    except AdapterError as exc: _raise_adapter(exc, position)
    db.transaction_active = False


def rollback(connection, position, runtime):
    db = _connection(connection, position, runtime)
    if not db.transaction_active: raise error("E907", "db_transaction_error", "No active transaction to roll back.", position)
    try: db.adapter.rollback(db.native)
    except AdapterError as exc: _raise_adapter(exc, position)
    db.transaction_active = False


def _begin(args, named, position, runtime): return begin(args[0], position, runtime)
def _commit(args, named, position, runtime): return commit(args[0], position, runtime)
def _rollback(args, named, position, runtime): return rollback(args[0], position, runtime)


def _metadata(method):
    def implementation(args, named, position, runtime):
        db = _connection(args[0], position, runtime)
        try: value = getattr(db.adapter, method)(db.native, *args[1:], database=db.database, host=db.host)
        except AdapterError as exc: _raise_adapter(exc, position)
        if method in ("columns", "indexes"):
            return [ObjectValue.create(item) for item in value]
        if method in ("primary_key", "server_info"):
            return None if value is None else ObjectValue.create(value)
        return value
    return implementation


DB_BUILTINS = (
    UtilityFunction("db_connect", 0, 0, _connect, ("driver", "host", "port", "database", "user", "password", "timeout", "charset", "ssl", "mode")),
    UtilityFunction("db_close", 1, 1, _close),
    UtilityFunction("db_query", 3, 3, _query("all"), ("timeout",)),
    UtilityFunction("db_query_one", 3, 3, _query("one"), ("timeout",)),
    UtilityFunction("db_scalar", 3, 3, _query("scalar"), ("timeout",)),
    UtilityFunction("db_execute", 3, 3, _execute, ("timeout",)),
    UtilityFunction("db_begin", 1, 1, _begin), UtilityFunction("db_commit", 1, 1, _commit), UtilityFunction("db_rollback", 1, 1, _rollback),
    UtilityFunction("db_tables", 1, 1, _metadata("tables")), UtilityFunction("db_columns", 2, 2, _metadata("columns")),
    UtilityFunction("db_indexes", 2, 2, _metadata("indexes")), UtilityFunction("db_primary_key", 2, 2, _metadata("primary_key")),
    UtilityFunction("db_server_info", 1, 1, _metadata("server_info")), UtilityFunction("db_version", 1, 1, _metadata("version")),
)
