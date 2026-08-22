# Separan Monitor — Separan-native Lambda runtime

[`monitor.yaml`](monitor.yaml) monitors up to five existing EC2 instances and
five existing RDS DB instances. CloudWatch, EventBridge, SNS, DynamoDB, S3, and
IAM remain CloudFormation resources. The four Lambda entrypoints execute the
same [Separan application](lambda/monitor.sep); Python is only the generic
reference-runtime adapter and contains no monitor policy.

## Build the Separan runtime artifact

The interpreter and its binary dependencies cannot be represented by
CloudFormation's single-file inline source form. Build one Linux-compatible ZIP
and upload it to an S3 bucket in the deployment region:

```powershell
./examples/monitor/build-runtime.ps1 -Bucket my-deployment-artifacts
```

The script prints the `SeparanRuntimeBucket` and `SeparanRuntimeKey` values to
enter in the CloudFormation GUI. The generated ZIP is about 7 MB and contains
`application.sep`, the Separan interpreter, Linux wheels, and a one-line
`index.handler` adapter. All four functions reuse that object and select their
Separan entrypoint through `SEPARAN_HANDLER`.

[`monitor-inline-python.yaml`](monitor-inline-python.yaml) is retained only as
the previous one-file compatibility sample. New development targets the native
Separan application.

## Pipeline

```text
A   EC2 CPU / Windows disk ─ CloudWatch Alarm ─┐
A2  RDS CPU / free storage ─ CloudWatch Alarm ─┤
B/C Windows logs/events ───── log2 Lambda ─────┤
D/E RDS logs/events ───────── log2 Lambda ─────┼─ notify Lambda
F1  scheduled state checks ── status Lambda ──┤      ├─ SNS Email
F2  EC2/RDS push events ───── status Lambda ──┘      ├─ SNS SMS
                                                      └─ SNS → Microsoft Teams
                                                               │
                                                               └─ DynamoDB history

S3 suppression.json + holidays.json ─ notify suppression policy
```

Notification types are fixed as follows:

- A: EC2 CPU and Windows logical-disk free space.
- A2: RDS CPU and free storage.
- B: Windows events containing `ERROR`, `CRITICAL`, or `重大`.
- C: Windows Application/System/Security events.
- D: exported RDS logs containing those keywords.
- E: RDS DB instance service events.
- F: EC2/RDS start, stop, reboot, and other state transitions.

The notify function has a separate template for every A–F and
Email/SMS/Teams combination. Every candidate, including suppressed candidates,
is written to DynamoDB. History expires after 30 days by default, identical
content is suppressed for 30 minutes, and A/A2 alerts are held during the
configured post-start/stop/reboot grace period.

## Deploy from the CloudFormation console

1. Choose **Create stack → With new resources**.
2. Upload [`monitor.yaml`](monitor.yaml).
3. Enter the runtime artifact bucket/key printed by `build-runtime.ps1`, then
   enter up to five EC2 instance IDs, five RDS identifiers, thresholds, and
   notification destinations. Leave unused slots empty.
4. Acknowledge IAM resource creation and create the stack.
5. Confirm the SNS email subscription if an email address was supplied.
6. Use the S3 bucket in stack Outputs to enable custom suppression and holiday rules.

Native CPU/storage metrics and state routes need only the target identifiers.
The following paths have extra prerequisites:

- Windows disk and event logs require `ConfigureWindowsAgents=true`. The Windows
  instances must already be Systems Manager managed nodes and use the common IAM
  role named in the parameters. The template installs/configures the CloudWatch Agent
  and waits up to 15 minutes for each association instead of silently completing the stack.
- RDS logs must already be exported to CloudWatch Logs; provide each existing log-group name.
- Microsoft Teams must first be authorized in Amazon Q Developer in chat applications;
  then provide tenant, team, and channel IDs and set `EnableTeams=true`.
- API-call push events use CloudTrail management events when a trail is configured.
  Direct EC2/RDS events and scheduled F1 checks do not depend on CloudTrail.

See the AWS documentation for [managing the CloudWatch Agent through Systems
Manager](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/installing-cloudwatch-agent-ssm.html),
[direct RDS EventBridge events](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-rds.html),
and [Microsoft Teams channel configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-chatbot-microsoftteamschannelconfiguration.html).

## S3 policy files

The stack seeds these files once and never overwrites operator edits during an update:

- `config/suppression.json`: matches notification types, resource IDs, Windows
  sources, event IDs, and a case-insensitive content substring. An empty list is
  a wildcard for that field.
- `config/holidays.json`: weekly and date-specific notification breaks, including
  time windows that cross midnight, evaluated in the configured timezone.

The S3 bucket and DynamoDB table use retain policies. DynamoDB TTL is enabled on
history/dedup/state records. AWS service charges may apply, and TTL expiration is
not an immediate-deletion guarantee.

## Failure behavior

- An SNS publish failure is stored as `DELIVERY_FAILED`; its dedup reservation is
  released so that the Lambda retry can deliver it.
- Periodic EC2/RDS API failures emit `check_failed` without overwriting the last
  known healthy resource state.
- Transition grace is set only on a real or pushed state transition and is never
  extended by an unchanged periodic check.
- Windows events are requested as XML and parsed for provider, event ID, level, and message.
- The SSM completion wait can make CloudFormation drift detection less accurate.

## Local Separan applications

The production Lambda logic is [`lambda/monitor.sep`](lambda/monitor.sep). The
older modular `.sep` files remain a runnable, AWS-free decision model:

```console
separan examples/monitor/main.sep
```

[`model-config.yaml`](model-config.yaml) is the smaller configuration-only model.
