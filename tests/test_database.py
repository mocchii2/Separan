import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class DatabaseTests(unittest.TestCase):
    def test_sqlite_query_one_scalar_execute_and_blob(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
print type_of(db)
print db
print db_execute(db, "create table users(id integer primary key, name text unique, data blob)", [])
print db_execute(db, "insert into users(id, name, data) values (?, ?, ?)", [1, 1, 1])
db_execute(db, "delete from users", [])
object:params
id = 1
name = "Alice"
data = bytes_from_hex("00ff")
end_object:params
print db_execute(db, "insert into users(id, name, data) values (:id, :name, :data)", params)
row = db_query_one(db, "select id, name, data from users where id = ?", [1])
print row.id
print row.name
print hex_encode(row.data)
print db_scalar(db, "select count(*) from users", [])
print length(db_query(db, "select id, name from users", []))
print db_query_one(db, "select id from users where id = ?", [2])
db_close(db)
db_close(db)
end_function:main
'''
        output = execute(source)[1]
        self.assertEqual(output, "db_connection\ndb_connection(driver=sqlite, database=[REDACTED])\n0\n1\n1\n1\nAlice\n00FF\n1\n1\nnull\n")

    def test_query_one_cardinality_and_errors_are_catchable(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
db_execute(db, "create table t(id integer unique)", [])
db_execute(db, "insert into t values (?)", [1])
db_execute(db, "insert into t values (?)", [2])
try :query
row = db_query_one(db, "select id from t", [])
catch db_query_error :query
print "cardinality"
endtry:query
try :constraint
db_execute(db, "insert into t values (?)", [1])
catch db_constraint_error :constraint
print "constraint"
endtry:constraint
end_function:main
'''
        self.assertEqual(execute(source)[1], "cardinality\nconstraint\n")

    def test_driver_capability_sql_and_parameter_validation(self):
        with self.assertRaises(SeparanError) as caught:
            execute('function:main\ndb = db_connect(driver = "unknown", database = ":memory:")\nend_function:main\n')
        self.assertEqual(caught.exception.code, "E900")
        denied = RuntimeCapabilities.none(ROOT)
        with self.assertRaises(SeparanError) as caught:
            execute('function:main\ndb = db_connect(driver = "sqlite", database = ":memory:")\nend_function:main\n', capabilities=denied)
        self.assertEqual(caught.exception.code, "E720")
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
print db_query(db, "select ?", [duration("1s")])
end_function:main
'''
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, "E201")

    def test_labeled_transaction_commits_and_rolls_back_on_error(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
db_execute(db, "create table t(id integer unique)", [])
transaction db :commit_one
db_execute(db, "insert into t values (?)", [1])
end_transaction:commit_one
try :rollback_one
transaction db :failing
db_execute(db, "insert into t values (?)", [2])
db_execute(db, "insert into t values (?)", [1])
end_transaction:failing
catch db_constraint_error :rollback_one
print "rolled back"
endtry:rollback_one
print db_scalar(db, "select count(*) from t", [])
end_function:main
'''
        self.assertEqual(execute(source)[1], "rolled back\n1\n")

    def test_manual_transaction_state_is_explicit(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
db_execute(db, "create table t(id integer)", [])
db_begin(db)
db_execute(db, "insert into t values (?)", [1])
db_rollback(db)
print db_scalar(db, "select count(*) from t", [])
try :invalid_commit
db_commit(db)
catch db_transaction_error :invalid_commit
print "no transaction"
endtry:invalid_commit
db_begin(db)
try :nested
db_begin(db)
catch db_transaction_error :nested
print "already active"
endtry:nested
db_rollback(db)
end_function:main
'''
        self.assertEqual(execute(source)[1], "0\nno transaction\nalready active\n")

    def test_transaction_label_and_kind_are_parser_checked(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
transaction db :work
end_transaction:other
end_function:main
'''
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, "E104")

    def test_sqlite_metadata_and_server_information(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
db_execute(db, "create table users(id integer primary key, name varchar(40) not null, email text unique)", [])
db_execute(db, "create index users_name on users(name)", [])
print db_tables(db)
columns = db_columns(db, "users")
print columns[1].name
print columns[1].type
print columns[1].nullable
print columns[1].length
indexes = db_indexes(db, "users")
print length(indexes)
print indexes[0].name
pk = db_primary_key(db, "users")
print pk.columns
info = db_server_info(db)
print info.driver
print info.database_name
print db_version(db) == info.server_version
end_function:main
'''
        self.assertEqual(execute(source)[1], "[users]\nname\nvarchar(40)\nfalse\n40\n2\nsqlite_autoindex_users_1\n[id]\nsqlite\n:memory:\ntrue\n")

    def test_metadata_absence_is_explicit(self):
        source = '''function:main
db = db_connect(driver = "sqlite", database = ":memory:")
db_execute(db, "create table no_pk(value text)", [])
print db_primary_key(db, "no_pk")
print db_indexes(db, "no_pk")
print db_columns(db, "no_pk")[0].default
end_function:main
'''
        self.assertEqual(execute(source)[1], "null\n[]\nnull\n")
        with self.assertRaises(SeparanError) as caught:
            execute('function:main\ndb = db_connect(driver = "sqlite", database = ":memory:")\nprint db_columns(db, "missing")\nend_function:main\n')
        self.assertEqual(caught.exception.code, "E903")


if __name__ == "__main__": unittest.main()
