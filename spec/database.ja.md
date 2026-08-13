# データベース標準 — v0.1プレビュー

> Explicit over implicit. Structure should be named, not guessed.

DB APIとdriver adapterは完全に分離する。SQLiteはPython標準`sqlite3`で標準搭載し、
PostgreSQL、MySQL、Oracle、Microsoft SQL ServerはそれぞれPsycopg 3、
MySQL Connector/Python、python-oracledb、pyodbcをlazy loadするoptional adapterとして実装する。未導入または
Capabilityで許可されていないdriverは`db_driver_error`となり、必要なinstall extraを表示する。

```console
pip install separan-lang
pip install "separan-lang[postgresql]"
pip install "separan-lang[mysql]"
pip install "separan-lang[oracle]"
pip install "separan-lang[sqlserver]"
pip install "separan-lang[db-all]"
```

SQL Server adapterはhost OSにMicrosoft ODBC Driver 18 for SQL Serverも必要とする。
Python extraが導入するのはpyodbcだけである。

内部構成は`db/core.py`、`db/registry.py`、`db/errors.py`と、`db/drivers/`配下の
公式adapterに分ける。optional Python packageはdriver選択時までimportしない。
単体CLIはデフォルトでSQLiteだけを許可する。remote adapterは実行時にも明示する。

```console
separan --allow-database-driver postgresql app.sep
```

組み込みhostは同じ境界を`RuntimeCapabilities.database_drivers`で制御する。

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

値は必ずbindする。同型listは`?` positional bindingに使う。異型parameterはobjectの
宣言順を`?`へ対応させる。`:name` named bindingはdriverが対応する場合の互換機能とし、
portableなSeparan SQLでは`?`を使う。null、number、string、
boolean、bytes、datetimeをbindできる。secretを通常のSQL値としてbindすることは禁止する。
SQL文字列連結は文法上禁止しないが強く非推奨とする。

Separanの位置bindは常に`?`を使う。adapterはSQL文字列、quoted identifier、行・block
comment、PostgreSQL dollar quote内を飛ばすscannerで、本物のplaceholderだけをnative
形式へ変換する。`LIMIT`、`RETURNING`、sequence、`MERGE`、PL/SQL、conflict構文などの
SQL dialectは統一せず、各database固有SQLをそのまま記述する。

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

`db_tables`、`db_columns`、`db_indexes`、`db_primary_key`、`db_server_info`、
`db_version`は共通result形を持つadapter操作として実装する。結果順は決定的。
`db_server_info`は`driver`、`driver_version`、`server_version`、`database_name`、
`server_host`、`mode`を返し、Oracleでは`thin`／`thick`も示す。SQL Serverでは認証方式
`windows`／`password`を示し、userとpasswordを両方省略した場合はWindows認証、片方だけなら
認証errorとする。暗号化接続をdefaultとし、自己署名証明書を許可するのは明示的なlocal hostだけ、
remote hostでは証明書検証を必須にする。SQL NULLはnull、BLOBはbytes。
SQLiteがboolean/datetimeの確実な結果型情報を持たない場合、nativeのnumber/stringを維持する。

DBアクセスには `database` Capabilityとdriver許可が必要。SQLite pathはfilesystem capability root内。
connection表示はdatabase識別子をredactし、単発実行終了時には未close接続も解放する。
接続・query timeoutはdurationで指定する。

catch可能な分類は `db_connection_error`、`db_auth_error`、`db_query_error`、
`db_constraint_error`、`db_timeout_error`、`db_transaction_error`、`db_driver_error`。
pool、streaming cursor、batch、prepared statement値、ORM、migration、DB固有監視namespaceは後回しとする。
