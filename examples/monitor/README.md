# Separan Monitor executable model

This folder is a runnable, dependency-free model of the decision core in the
Separan Monitor v0.1 design. It demonstrates the part where monitoring events
become either a delivered notification or a suppression record with a reason.

Run it after installing Separan:

```console
separan examples/monitor/main.sep
```

The model exercises:

- log keyword inclusion and exclusion;
- the fixed suppression order;
- duplicate detection with a ten-minute window;
- transition-grace and maintenance suppression;
- EC2 state normalization;
- missing normal-job completion;
- complete in-memory notification history, including suppressed candidates.

`notify.sep` is the only notification exit. The other three modules normalize
their input and pass a candidate to it. State is passed explicitly between
functions, modeling the future DynamoDB boundary without hidden global state.

The output should end with:

```text
History: detected=7, sent=3, suppressed=4
State transitions recorded: 1
Job observations recorded: 1
```

## Honest implementation boundary

`monitor.yaml` is the proposed round-trippable GUI configuration, but the
current Separan runtime does not yet include YAML parsing, an AWS SDK, Lambda
packaging, or CloudFormation generation. This example therefore does not claim
to deploy AWS resources. SNS delivery and DynamoDB persistence are represented
by `SIMULATED` delivery and the explicit in-memory store.

The next dogfooding increments are:

1. a strict YAML module with source diagnostics;
2. typed AWS capability adapters for discovery and validation;
3. deterministic CloudFormation and CloudWatch Agent generators;
4. DynamoDB-backed state/history repositories;
5. a local GUI that round-trips `monitor.yaml` without semantic changes.
