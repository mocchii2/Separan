# データベース標準 — v0.1プレビュー

> Explicit over implicit. Structure should be named, not guessed.

リファレンス実装はドライバ境界とSQLite用Core APIを実装する。PostgreSQL、MySQL、Oracleは
正式なdriver名として予約するが、別adapterが必要である。未導入またはCapabilityで許可されない
driverは `db_driver_error` となる。

```separan
db = db_connect(driver = "sqlite", database = "app.db")
rows = db_query(db, "select id, name from users where active = ?", [true])
one = db_query_one(db, "select id, name from users where id = ?", [id])
count = db_scalar(db, "select count(*) from users", [])
changed = db_execute(db, "update users set active = :active where id = :id", params)
db_close(db)
```

`db_query` は全行を `list<object>` で返し、0件は `[]`。`db_query_one` は0件ならnull、
1件ならobject、2件以上ならerror。`db_scalar` は先頭行の先頭列、0行ならnull。
`db_execute` は影響行数を返し、DDLで不明な場合は0に正規化する。

値は必ずbindする。同型listは `?` positional binding、objectは `:name` named bindingに使う。
Separanの同型list規則を弱めないため、異型parameterはobjectを使う。null、number、string、
boolean、bytes、datetimeをbindできる。secretを通常のSQL値としてbindすることは禁止する。
SQL文字列連結は文法上禁止しないが強く非推奨とする。

## Transaction

```separan
transaction db :transfer
db_execute(db, "update accounts set balance = balance - ? where id = ?", debit)
db_execute(db, "update accounts set balance = balance + ? where id = ?", credit)
end_transaction:transfer
```

正常終了はcommit、未処理runtime errorはrollbackして再送出する。labelとcloser種別はParserで
検証する。手動APIは `db_begin`、`db_commit`、`db_rollback`。同一接続のnested transaction、
begin前のcommit/rollbackは `db_transaction_error`。

SQLiteでは `db_tables`、`db_columns`、`db_indexes`、`db_primary_key`、
`db_server_info`、`db_version` を実装する。結果順は決定的。SQL NULLはnull、BLOBはbytes。
SQLiteがboolean/datetimeの確実な結果型情報を持たない場合、nativeのnumber/stringを維持する。

DBアクセスには `database` Capabilityとdriver許可が必要。SQLite pathはfilesystem capability root内。
connection表示はdatabase識別子をredactし、単発実行終了時には未close接続も解放する。
接続・query timeoutはdurationで指定する。

catch可能な分類は `db_connection_error`、`db_auth_error`、`db_query_error`、
`db_constraint_error`、`db_timeout_error`、`db_transaction_error`、`db_driver_error`。
pool、streaming cursor、batch、prepared statement値、ORM、migration、DB固有監視namespaceは後回しとする。
