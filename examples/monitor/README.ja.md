# Separan Monitor — CloudFormation一括デプロイ

[`monitor.yaml`](monitor.yaml)は、最大5台のEC2と最大5台のRDSを監視するための
CloudFormationテンプレートです。監視設定、CloudWatch Alarm、EventBridge、SNS、
DynamoDB、S3、IAM、および4本のinline Lambdaプログラムを1つのYAMLに収録しています。
CloudFormationコンソールでパラメータを入力してdeployすれば、選択した監視経路が作成されます。

## 監視と通知の経路

```text
A   EC2 CPU／Windows disk空き容量 ─ CloudWatch Alarm ─┐
A2  RDS CPU／空きstorage             CloudWatch Alarm ─┤
B   Windows log keyword ─┐                               │
C   Windows event ───────┼─ log2 Lambda ────────────────┤
D   RDS log keyword ─────┤                               ├─ notify Lambda
E   RDS service event ───┘                               │      ├─ SNS Email
F1  EventBridge定期確認 ───── status Lambda ────────────┤      ├─ SNS SMS
F2  EC2／RDS push・API event ─ status Lambda ───────────┘      └─ SNS → Teams
                                                               │
                                                               └─ DynamoDB（全候補、30日TTL）

S3 config/suppression.json ─┐
S3 config/holidays.json ─────┴─ notify Lambdaの送信判定
```

| 種別 | 対象 | 検知内容 |
|---|---|---|
| A | EC2 | `CPUUtilization`、CloudWatch Agentのlogical disk空き容量 |
| A2 | RDS | `CPUUtilization`、`FreeStorageSpace` |
| B | Windows | `ERROR`、`CRITICAL`、`重大`を含むevent log |
| C | Windows | Application／System／Securityのwarning以上のevent |
| D | RDS | export済みlogの`ERROR`、`CRITICAL`、`重大` |
| E | RDS | EventBridgeへ直接送られるDB instance event |
| F | EC2／RDS | 起動、停止、再起動、および状態変化 |

`notify`はA〜FとEmail／SMS／Teamsの組み合わせごとに別のtemplateを持ちます。
通知候補は送信・抑制のどちらでもDynamoDBへ保存され、既定では30日後にTTLで削除されます。
同一内容は既定で30分抑制され、起動・停止・再起動後のA／A2も指定分数だけ抑制されます。

## 5分でdeployする

1. AWS CloudFormationコンソールで「スタックの作成」→「新しいリソースを使用」を開きます。
2. 「テンプレートファイルのアップロード」で[`monitor.yaml`](monitor.yaml)を選びます。
3. EC2 instance ID、RDS DB instance identifier、通知先、しきい値をGUIで入力します。
   未使用の2〜5番slotは空のままで構いません。
4. IAM resource作成への同意を選択してstackを作成します。
5. Emailを指定した場合は、届いたSNS subscription確認メールを承認します。
6. stackの`Outputs`にあるS3 bucketで、必要に応じて抑制・休止設定を有効化します。

CPU、RDS空き容量、定期状態確認、EC2 state push、RDS eventは対象IDを入れるだけで作成されます。
追加準備が必要な経路は次のとおりです。

- EC2のdisk／Windows event log: `ConfigureWindowsAgents=true`にします。対象Windows EC2は
  Systems Managerのmanaged nodeで、全対象がパラメータ指定した同一IAM roleを使用している必要があります。
  テンプレートがCloudWatch Agentのinstall、Parameter Store設定、起動を関連付け、各処理の成功を
  最大15分待ちます。失敗時は監視できないままstackを成功扱いにせず、stack作成を失敗させます。
- RDS log: RDS側でCloudWatch Logs exportを有効化し、各`RdsLogGroup`へ既存log group名を指定します。
- Teams: 先にAmazon Q Developer in chat applicationsでMicrosoft Teams clientを認証し、
  tenant／team／channel IDを用意してから`EnableTeams=true`にします。
- API呼び出し直後の再起動・停止・起動push: CloudTrailでmanagement eventを記録しているaccountでは
  `AWS API Call via CloudTrail`もF2へ入ります。直接のEC2／RDS eventとF1定期確認はCloudTrailなしでも動きます。

CloudWatch AgentをSSMとParameter Storeで管理する方法は
[AWS公式手順](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/installing-cloudwatch-agent-ssm.html)、
RDSからEventBridgeへ届くeventの形式は
[AWS公式event reference](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-rds.html)を参照してください。

## 主なGUIパラメータ

- 監視対象: `Ec2Instance1..5`、`RdsInstance1..5`
- 表示名: `Ec2Name1..5`、`RdsName1..5`
- RDS log: `RdsLogGroup1..5`
- Metric: CPU%、EC2 disk空き%、RDS空きbytes、period、evaluation回数
- 状態変化抑制: 起動後・停止後・再起動後の分数
- 通知先: Email、E.164形式SMS、Teams
- 種別別route: `email,sms,teams`のcomma区切り
- 保存・重複抑制: history日数、同一内容を抑制する分数

## S3の抑制設定

stack作成時に、設定bucketへ次の2ファイルが初回だけ作成されます。stack更新では利用者の
編集内容を上書きしません。bucketとDynamoDB tableは誤削除防止のためstack削除後もretainされます。

`config/suppression.json`:

```json
{
  "version": 1,
  "rules": [
    {
      "id": "ignore-known-event",
      "enabled": true,
      "notification_types": ["B", "C"],
      "resource_ids": ["i-0123456789abcdef0"],
      "windows_sources": ["Application Error"],
      "event_ids": ["1000"],
      "content_contains": "hogehoge"
    }
  ]
}
```

各配列を空にすると、その項目は全値に一致します。`content_contains`は大文字小文字を区別しません。
この組み合わせにより、`windows source / event ID / content`だけでなく、通知種別・resource単位でも
全通知に共通の抑制判定を適用できます。

`config/holidays.json`:

```json
{
  "version": 1,
  "timezone": "Asia/Tokyo",
  "weekly": [
    {"enabled": true, "days": ["SAT", "SUN"], "start": "00:00", "end": "23:59"},
    {"enabled": true, "days": ["MON"], "start": "22:00", "end": "06:00"}
  ],
  "dates": [
    {"enabled": true, "date": "2026-12-31", "start": "18:00", "end": "23:59"}
  ]
}
```

曜日、日付、時間帯を指定でき、日をまたぐ時間帯にも対応します。

## 障害時の扱い

- SNSへの送信が失敗した場合は`DELIVERY_FAILED`を履歴化し、dedup予約を解除してLambda retryで再送できます。
- EC2／RDSの定期状態取得が権限・APIエラーになった場合は`check_failed`を通知し、直前の正常な状態を上書きしません。
- 起動・停止・再起動後のmetric抑制期限は状態が実際に変化した時だけ設定し、定期確認では延長しません。
- Windows eventはCloudWatch AgentからXML形式で受け、provider、event ID、level、messageを明示的に解析します。

## 実装上の境界

- 単一YAMLでdeployできますが、対象EC2／RDS自体は作成せず、同一account・regionの既存resourceを監視します。
- RDS direct eventはEventBridgeのbest-effort deliveryです。F1の定期確認が状態検知の補完経路になります。
- Teams通知はSNS topicをAmazon Q DeveloperのTeams channel configurationへ接続します。
- SSM Associationの完了待ちを使用するため、CloudFormation drift検査結果が正確でない場合があります。
- SMS、CloudWatch、Lambda、SNS、DynamoDB、S3などの利用料金が発生し得ます。
- DynamoDB TTL削除は期限直後の即時削除を保証する仕組みではありません。

## Separanで判断coreを試す

`.sep`の`notify`／`logcheck`／`status`／`normal_check`は、同じ抑制思想をローカルで確認する
実行可能なreference modelとして残しています。AWSへ接続せず実行できます。

```console
separan examples/monitor/main.sep
```

小さな設定モデルだけを見たい場合は[`model-config.yaml`](model-config.yaml)を参照してください。
