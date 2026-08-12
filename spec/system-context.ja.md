# 予約system context

> Reserved values describe the execution context. Dynamic operations remain functions.

`system` はruntimeが提供するread-onlyの予約namespaceである。代入、const宣言、function名、
parameter名、import alias、data block名、loop変数としてshadowできない。member代入はSeparanの
immutable objectモデルに含まれず、専用診断で拒否する。

| Member | 意味 |
|---|---|
| `system.version` | Separan language/runtime release |
| `system.engine` | 実装識別子（`python-reference`） |
| `system.script_path` | scriptの絶対path。pathなしsourceではnull |
| `system.script_name` | script file名。pathなしではnull |
| `system.script_dir` | script格納directoryの絶対path。pathなしではnull |
| `system.working_dir` | 起動時working directoryのsnapshot |
| `system.args` | script pathを含まないcommand arguments |
| `system.arg_count` | `system.args` の要素数 |
| `system.os` | `windows`、`linux`、`macos`、`unknown` |
| `system.arch` | 正規化した `x86_64`、`arm64`、`x86` またはhost fallback |
| `system.hostname` | hostname snapshot |
| `system.pid` | process ID |
| `system.runtime` | runtime family（reference engineでは `python`） |
| `system.cpu_count` | 使用可能なlogical CPU数（最低1） |

contextはInterpreter作成時に固定する。`system.args` にscript名は混ぜない。`system` 全体の表示は
`system:[READONLY]` のみとし、argumentやhost情報を不用意に一括出力しない。

時刻と乱数は動的操作なので `datetime_now()` とrandom関数のままにする。HTTP request情報は
request context、DBは明示的connection値を使う。cloud固有flagはcoreではなく拡張namespaceへ置く。

既存の `command_args()` と `script_path()` はv0.x互換aliasとして残す。新規コードでは安定した
実行metadataに `system` を推奨する。
