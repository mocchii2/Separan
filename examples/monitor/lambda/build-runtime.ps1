param(
    [Parameter(Mandatory = $true)][string]$Bucket,
    [string]$Key = "separan-monitor/runtime.zip",
    [ValidateSet("x86_64", "arm64")][string]$Architecture = "x86_64"
)

$ErrorActionPreference = "Stop"
$exampleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $exampleRoot "monitor.sep"
$output = Join-Path ([IO.Path]::GetTempPath()) "separan-monitor-runtime.zip"

separan lambda-package $source --output $output --architecture $Architecture
if ($LASTEXITCODE -ne 0) { throw "Separan Lambda package build failed." }

aws s3 cp $output "s3://$Bucket/$Key"
if ($LASTEXITCODE -ne 0) { throw "Runtime upload failed." }

Write-Host "SeparanRuntimeBucket=$Bucket"
Write-Host "SeparanRuntimeKey=$Key"
