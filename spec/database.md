# Database Standard — v0.1 preview

> Explicit over implicit. Structure should be named, not guessed.

The reference preview implements a driver boundary and the complete core API
for SQLite. PostgreSQL, MySQL, and Oracle are recognized driver names but require
separate host-installed adapters; requesting an unavailable or disallowed driver
is `db_driver_error`.

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
An object uses named `:name` binding and is the v0.1 solution for heterogeneous
parameters, because Separan deliberately does not weaken homogeneous lists.
Supported values are null, number, string, boolean, bytes, and datetime.
Secrets cannot be bound as ordinary data. SQL string concatenation remains
possible but is strongly discouraged.

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
`db_version` are implemented for SQLite. Lists are deterministically ordered.
SQL NULL maps to null and BLOB maps to bytes. SQLite has no reliable declared
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
