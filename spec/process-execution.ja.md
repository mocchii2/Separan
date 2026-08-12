# 外部process実行 — v0.2設計

状態: **実験的プレビュー実装あり。** `exec`、`exec_checked`、`shell_exec`、
`command_exists`と固定shape resultを利用できます。process-tree全体の終了保証、実行中の
streaming output上限、portable shell IDは正式v0.2までの残作業です。

> `shell_exec`より`exec`を優先する。

Separanではprogram直接実行を標準操作にします。shell解釈は、より強いcapabilityを
要求する、明示的で危険性の見える別操作です。

## 直接実行

```separan
result = exec("git", ["status"])

print result.exit_code
print result.stdout
print result.stderr
```

`exec(command, args, ...)`は一つの実行fileを直接起動します。引数をcommand stringへ
連結せず、pipe、redirect、wildcard、変数展開、command substitution、`&`、`;`、shell
quoteを解釈しません。

```separan
filename = input("file: ")
result = exec("tool", [filename])
```

`filename`に`&`、`;`、`*`、`$()`、空白が含まれても、値全体が一つの引数です。
この性質は全platformで満たす規範仕様です。

初期signatureはnamed optionを使います。

```separan
result = exec(
    "python",
    ["script.py"],
    cwd = "work",
    timeout = duration("30s"),
    env = {"MODE": "test", "LANG": "ja_JP.UTF-8"},
    input = "c\na\nb\n"
)
```

commandと全引数はstringです。空command名とNULを含むstringはエラーです。引数listは
同型で、変換せずargv vectorとして渡します。

## result型

非zero exit codeを含む通常終了は、不変の`exec_result`を返します。

| field | 型 | 意味 |
|---|---|---|
| `exit_code` | number | 整数exit code |
| `stdout` | stringまたはnull | decode済み標準出力。decode失敗時null |
| `stderr` | stringまたはnull | decode済み標準error。decode失敗時null |
| `stdout_bytes` | bytes | 正確な標準出力byte |
| `stderr_bytes` | bytes | 正確な標準error byte |
| `timed_out` | boolean | timeout終了が必要だったか |
| `duration` | duration | monotonic clockによる経過時間 |
| `command` | string | 表示用にsanitizeした解決済み実行path |

指定encodingでdecodeできない場合、`stdout`／`stderr`はstringではなくnullです。raw bytesは
利用できます。両streamは分離し、stream間の書き込み順序は保証しません。

signalやplatform固有異常終了は、adapterごとに文書化する負の`exit_code`へ対応させます。
成功code 0として扱いません。

## checked実行

```separan
try :run_git
result = exec_checked("git", ["pull"])
print result.stdout

catch command_error :run_git
print_error "git failed"
endtry:run_git
```

`exec_checked`のoption・実行意味は`exec`と同じですが、exit code非zeroで
`command_error`、timeoutでそのsubtypeの`command_timeout_error`をthrowします。errorは完全な`exec_result`を保持し、将来のcatch binding
で`error.result`として参照します。実行file不在、権限、spawn、encoding、resource limit
失敗はprocess result自体がないため、`exec`でも`exec_checked`でもerrorです。

## optionとdefault

| option | default | 規則 |
|---|---|---|
| `cwd` | capability作業directory | capability root内の相対path |
| `timeout` | `duration("30s")` | 正のduration、capability上限以下 |
| `env` | 空object | 明示的string-to-string追加／置換 |
| `inherit_env` | false | trueには別capability許可が必要 |
| `input` | null | string、bytes、null |
| `encoding` | `"utf-8"` | 出力text decode。locale fallbackなし |
| `max_stdout_bytes` | 1,048,576 | capability上限以下 |
| `max_stderr_bytes` | 1,048,576 | capability上限以下 |

default環境はhost継承ではなく最小環境です。adapterがplatform実行に必要な変数だけを
供給し、callerの`env`を重ねます。NULを含む環境名・値は禁止し、platform正規化後に
重複する名前はエラーです。

`inherit_env = true`ではhost secretがchildへ見える可能性があるため、sourceとhost
capabilityの両方でopt-inします。

`input`はstdinへ書いた後closeします。stringは指定encodingでencodeし、改行を追加しません。
nullならchild stdinは空でclose済みです。

## 実行file解決

process capabilityは許可実行identityを次のいずれかで指定します。

- 完全一致するcanonical executable path
- hostがcanonical pathへmapしたcommand名

現在directoryを暗黙検索しません。任意host PATH検索もdefaultでは無効です。capabilityは
固定順序の検索pathを提供できますが、解決済みcanonical pathはallowlistにも一致する必要が
あります。Windows extension probingとscript associationはadapterで明示設定しない限り
無効です。

`command_exists(name)`は`exec`と完全に同じ解決・capability規則を使います。存在しても
許可外の実行fileは公開しません。

```separan
if command_exists("git") :git_available
print "git found"
endif:git_available
```

実行file不在時にshell検索へfallbackしません。

## 作業directoryとpath

`cwd`はprocess capability rootから解決します。初期実装ではabsolute pathと`..` escapeを
拒否します。hostはさらに狭い作業directory集合を許可できます。引数はstringのままchildへ
渡し、pathらしい引数をSeparanが再解釈したりroot内だと保証したりしません。cwd外のfile／
networkアクセスを閉じるにはOS sandboxが必要で、host側の別責任です。

実行file allowlistだけでは、そのprogramが読む・書く・network接続する対象を制限できない
ことを文書上明示します。

## timeout・cancel・process tree

対応platformではruntime所有process group／job内で起動します。timeout時は次の順です。

1. 所有process tree全体へgraceful終了を要求。
2. default 2秒の固定grace期間を待機。
3. 残存processを強制終了。
4. 上限付きoutput pipeをdrain。
5. `exec`は`timed_out = true` result、`exec_checked`は`command_error`。

platformがtree終了を保証できない場合、capabilityが制限を宣言し、hostが弱いprocess隔離を
明示許可しない限り実行を拒否します。async、detached process、interactive TTY、background
jobは延期します。

## output上限

pipe deadlock防止のためstdout／stderrを並行消費します。上限はtext decode前のbyte単位です。
どちらかが上限を超えたらprocess treeを終了し`command_limit_error`にします。黙ってtruncate
しません。将来のstreaming APIは別名・別capabilityです。

text decodeは厳密です。不正byte列の場合、`exec`の対応text fieldはnullになります。
`exec_checked`も同じで、binary出力だけを理由に失敗しません。text必須のcallerは将来の
明示的`require_stdout_text(result)`またはbytesを利用します。

## shell実行

```separan
result = shell_exec("dir | findstr sep")
```

`shell_exec(command, ...)`は一つのstringを明示選択したshellへ渡します。通常の
`process_capability`では足りず、別の`shell_capability`が必要です。CLI safe modeとembedding
ではdefault無効です。

stable APIでは、host capabilityがshellを一つだけ定義している場合を除き、named `shell`
optionを必須にします。

```separan
result = shell_exec(
    "printf '%s\\n' *.sep",
    shell = "posix_sh",
    timeout = duration("10s")
)
```

portable shell IDは`posix_sh`、`powershell`、`cmd_windows`を予定します。syntax自体はportable
ではありません。`shell_exec`使用sourceはproject metadataでplatform前提を宣言すべきです。

`shell_exec`はSeparan変数を自動展開しません。非信頼dataの文字列連結はshell injectionです。

```separan
: 安全。filenameはargvの1要素
exec("tool", [filename])

: 危険。filenameがshell syntaxになる
shell_exec("tool " + filename, shell = "posix_sh")
```

static toolingは非const式を受ける`shell_exec`へwarningすべきです。shell表面を小さく保つため
`shell_exec_checked`は用意しません。result確認または将来の汎用`require_success(result)`を
使います。

## capability model

hostが`process_capability`を許可しない限りprocess実行は無効です。shellには追加で
`shell_capability`が必要です。capabilityは次を制限します。

- executable pathとcommand alias
- working-directory root
- 環境継承と許可変数名
- 最大引数数・argv合計byte
- timeout・process数
- stdin・captured output byte
- 弱いprocess-tree隔離を許すか
- child network accessをhost sandboxで制限するか

capabilityはhostが供給するruntime値で、Separan sourceから生成できません。import moduleが
callerより広いprocess権限を得ることもありません。

## error階層・診断

```text
runtime_error
└─ process_error
   ├─ command_not_found_error
   ├─ command_permission_error
   ├─ command_spawn_error
   ├─ command_limit_error
   └─ command_error             （exec_checked非zero exit）
      └─ command_timeout_error  （exec_checked timeout）
```

計画診断は`E800`～`E819`です。診断にはsanitize済み実行file、invalid argvのindex、cwd、
timeout、利用可能ならexit codeを含めます。hostがsecret指定した環境値、stdin、argumentは
redactします。直接`exec`の診断でshell command風の再構築文字列は表示しません。shell解釈が
あるように誤解させるためです。

## 実装・test要件

1. named argument、非破壊object API、bytes、duration、固定shape member access
2. catch可能runtime errorとprocess／shell capability注入
3. 決定的unit test用の注入可能process transport
4. 空白・shell metacharacterを含むargv round-trip platform test
5. 並行output上限・timeout tree test
6. 任意system toolではなくrepository所有helperを使うreal-process適合test

core適合testは`git`、`python`、`ping`、shellが特定名でinstalledであることへ依存しません。
