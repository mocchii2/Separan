# AWS Lambda runtime

状態: v0.2 alphaの実験的preview。

Separan Lambda applicationは、2引数のentry functionを持つ通常の`.sep`です。

```separan
function:handler(event, context)
object:result
ok = true
request_id = context.aws_request_id
end_object:result
return result
end_function:handler
```

runtimeはLambda workerごとにapplicationを一度だけparseし、warm invocationではASTと
interpreterを再利用します。AWSのJSON objectは不変のSeparan `object`へ変換され、
戻り値はJSON互換値へ戻されます。

任意の対応host OSからLinux互換のdeploy ZIPを作成できます。

```console
separan lambda-package application.sep --output application.zip
```

LambdaはPython 3.13、handlerは`index.handler`を指定します。entry functionが
`handler`以外の場合は`SEPARAN_HANDLER`を設定します。package commandはWindowsの
binaryをコピーせず、対象architecture用Linux wheelを取得します。

Python bootstrapは実装adapterであり、application logicではありません。判断処理は
Separan側に置きます。AWSアクセスは明示的な`aws_*` host functionだけに限定します。
現在はenvironment、SNS、S3 JSON、DynamoDB、EC2／RDS状態取得、CloudWatch Logs decode、
Windows Event XML parse、CloudFormation custom resource responseを提供します。

host functionは言語builtinやuser functionを上書きできません。host側の失敗はSeparanの
source位置を保持した`SEPARAN E980: Lambda host error`として報告されます。
