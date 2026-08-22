# AWS Lambda runtime

Status: Experimental preview in v0.2 alpha.

Separan Lambda applications are ordinary `.sep` files with a two-parameter
entry function:

```separan
function:handler(event, context)
object:result
ok = true
request_id = context.aws_request_id
end_object:result
return result
end_function:handler
```

The runtime parses the application once per Lambda worker and reuses its AST
and interpreter on warm invocations. AWS JSON objects cross the boundary as
immutable Separan `object` values. Results cross back as JSON-compatible values.

Build a Linux-compatible deployment artifact from any supported host OS:

```console
separan lambda-package application.sep --output application.zip
```

Use `index.handler`, Python 3.13, and set `SEPARAN_HANDLER` when the entry
function is not named `handler`. The package command installs Linux wheels for
the target architecture rather than copying incompatible Windows binaries.

The Python bootstrap is an implementation adapter, not application code.
Decisions remain in Separan. AWS access is limited to explicit `aws_*` host
functions: environment reads, SNS publishing, S3 JSON, DynamoDB records,
EC2/RDS state queries, CloudWatch Logs decoding, Windows Event XML parsing,
and CloudFormation custom-resource responses.

Host functions cannot replace language built-ins or user functions. Failures
cross the boundary as `SEPARAN E980: Lambda host error`, retaining Separan
source location diagnostics.
