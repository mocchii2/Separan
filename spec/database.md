# Database Standard — v0.1 preview

> Explicit over implicit. Structure should be named, not guessed.

The DB API and driver adapters are fully separated. SQLite is built in through
Python `sqlite3`; PostgreSQL, MySQL, Oracle, and Microsoft SQL Server use
lazy-loaded optional adapters backed by Psycopg 3, MySQL Connector/Python,
python-oracledb, and pyodbc respectively.
Requesting an unavailable or disallowed driver is `db_driver_error` and names
the exact installation extra.

```console
pip install separan-lang
pip install "separan-lang[postgresql]"
pip install "separan-lang[mysql]"
pip install "separan-lang[oracle]"
pip install "separan-lang[sqlserver]"
pip install "separan-lang[db-all]"
```

The SQL Server adapter also requires Microsoft ODBC Driver 18 for SQL Server on
the host operating system; the Python extra installs only pyodbc.

The implementation is divided into `db/core.py`, `db/registry.py`,
`db/errors.py`, and one module per official adapter under `db/drivers/`.
Optional Python packages are imported only when their driver is selected.
The standalone CLI allows SQLite by default. A remote adapter must also be
explicitly enabled for that run, for example:

```console
separan --allow-database-driver postgresql app.sep
```

Embedded hosts control the same boundary with
`RuntimeCapabilities.database_drivers`.

```separan
db = db_connect(driver = "sqlite", database = "app.db")
rows = db_query(db, "select id, name from users where active = ?", [true])
one = db_query_one(db, "select id, name from users where id = ?", [id])
count = db_scalar(db, "select count(*) from users", [])
changed = db_execute(db, "update users set active = ? where id = ?", params)
db_close(db)
```

`db_query` returns all rows as `list<object>` and returns `[]` for no rows.
`db_query_one` returns null, exactly one object, or an error for two or more
rows. `db_scalar` returns the first column of the first row or null. `db_execute`
returns affected rows, with unavailable DDL counts normalized to zero.

Parameters are always bound. A homogeneous list uses positional `?` binding.
An object may supply heterogeneous positional values in declaration order for
`?` placeholders. Named `:name` binding remains available where the selected
driver supports it, but portable Separan SQL uses `?`.
Supported values are null, number, string, boolean, bytes, and datetime.
Secrets cannot be bound as ordinary data. SQL string concatenation remains
possible but is strongly discouraged.

Separan positional binding always uses `?`. The selected adapter rewrites only
real placeholders to its native style; the scanner skips SQL string literals,
quoted identifiers, line and block comments, and PostgreSQL dollar-quoted
strings. SQL dialects themselves are not normalized: `LIMIT`, `RETURNING`,
sequences, `MERGE`, PL/SQL, and conflict syntax remain database-specific.

## Transactions

```separan
transaction db :transfer
db_execute(db, "update accounts set balance = balance - ? where id = ?", debit)
db_execute(db, "update accounts set balance = balance + ? where id = ?", credit)
end_transaction:transfer
```

Normal completion commits. An unhandled runtime error rolls back and propagates.
Labels and closer kinds are parser-validated. `db_begin`, `db_commit`, and
`db_rollback` provide a manual API. Nested transactions on one connection,
commit without begin, and rollback without begin are `db_transaction_error`.

## Metadata and types

`db_tables`, `db_columns`, `db_indexes`, `db_primary_key`, `db_server_info`, and
`db_version` are adapter operations with a common result shape. Lists are
deterministically ordered. `db_server_info` includes `driver`, `driver_version`,
`server_version`, `database_name`, `server_host`, and `mode`; Oracle reports
`thin` or `thick`. SQL Server reports `windows` or `password` authentication;
omitting both `user` and `password` selects Windows authentication, while
specifying only one is an authentication error. Encrypted connections are the
default. Self-signed certificates are trusted only for explicit local hosts;
remote hosts require certificate validation. SQL NULL maps to null and BLOB maps to bytes. SQLite has no reliable declared
boolean/datetime result type, so values returned by its native driver remain
numbers or strings; other adapters may perform stronger documented mapping.

DB access requires the `database` capability and an allowed driver. SQLite file
paths remain inside the filesystem capability root. Connection display redacts
the database identifier, and all open connections created by one-shot execution
are released at completion. Query and connection timeouts accept duration.

Catchable categories are `db_connection_error`, `db_auth_error`,
`db_query_error`, `db_constraint_error`, `db_timeout_error`,
`db_transaction_error`, and `db_driver_error`.

Pools, streaming cursors, batches, prepared-statement values, ORM, migrations,
and driver-specific monitoring namespaces are deferred.
