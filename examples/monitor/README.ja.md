# Separan Monitor 実行モデル

このフォルダは、Separan Monitor v0.1設計のうち、監視イベントを通知または理由付き
抑制履歴へ変換する判断coreを実行可能にしたモデルです。外部依存なしで動きます。

Separanをinstallした後、repository rootで実行します。

```console
separan examples/monitor/main.sep
```

次を一度に確認できます。

- log keywordのinclude／exclude
- 固定された抑制評価順
- 10分間のduplicate抑制
- 状態遷移猶予とmaintenanceによる抑制
- EC2状態イベントの正規化
- JOB正常終了が来なかった場合の検知
- 抑制された候補を含む全notification history

通知の出口は`notify.sep`だけです。他の3モジュールは入力を正規化し、通知候補を
`notify`へ渡します。状態は隠れたglobal変数ではなく明示的に関数間で受け渡し、将来の
DynamoDB境界を表現しています。

出力末尾は次のようになります。

```text
History: detected=7, sent=3, suppressed=4
State transitions recorded: 1
Job observations recorded: 1
```

## 実装済み境界

`monitor.yaml`はGUIと往復する予定の設定例です。ただし、現在のSeparan runtimeには
YAML parser、AWS SDK、Lambda packaging、CloudFormation generatorがまだありません。
そのため、この例はAWS resourceをdeployしたとは主張しません。SNS配信とDynamoDB永続化は、
`SIMULATED` deliveryと明示的なmemory storeで表現しています。

次のdogfooding実装候補は以下です。

1. source位置診断を持つ厳密なYAML module
2. discoveryと事前検証を行う型付きAWS capability adapter
3. 決定的なCloudFormation／CloudWatch Agent generator
4. DynamoDB版state／history repository
5. `monitor.yaml`を意味変更なしで往復するlocal GUI
