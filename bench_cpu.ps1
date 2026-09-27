param(
    [int]$Repeats = 5
)

$repo = $PSScriptRoot
$source = Join-Path $repo "examples\bench_cpu.sep"
$gatewaySource = Join-Path $repo "examples\bench_cpu_gateway.sep"
$cacheSource = Join-Path $repo "examples\bench_cache.sep"
$native = Join-Path $repo "reference\c\separan.exe"
$gateway = Join-Path $repo "reference\c\separan-gw.exe"
$python = Join-Path (Split-Path $repo -Parent | Split-Path -Parent) ".venv\Scripts\python.exe"

if (-not (Test-Path $native)) { throw "Build the native CLI first: make -C reference/c all" }
if (-not (Test-Path $gateway)) { throw "Build the native Gateway first: make -C reference/c gateway" }
if (-not (Test-Path $python)) { throw "Python venv not found: $python" }

$env:PYTHONPATH = Join-Path $repo "reference"

function Measure-Runner([string]$Name, [scriptblock]$Runner) {
    $times = @()
    $lastOutput = ""
    for ($index = 0; $index -lt $Repeats; $index++) {
        $output = ""
        $elapsed = Measure-Command { $output = (& $Runner | Out-String).Trim() }
        $times += $elapsed.TotalMilliseconds
        $lastOutput = $output
    }
    $ordered = $times | Sort-Object
    $median = $ordered[[int][Math]::Floor($ordered.Count / 2)]
    [PSCustomObject]@{
        Runtime = $Name
        MedianMilliseconds = [Math]::Round($median, 2)
        Samples = (($times | ForEach-Object { [Math]::Round($_, 2) }) -join ", ")
        Checksum = $lastOutput
    }
}

function Measure-Gateway([string]$Name, [string]$SourcePath, [string]$Request, [bool]$UseCache) {
    $cache = Join-Path $env:TEMP "separan-bench-cache-$PID"
    Remove-Item $cache -Recurse -Force -ErrorAction SilentlyContinue
    $arguments = @("--source", $SourcePath, "--stdio")
    if ($UseCache) { New-Item -ItemType Directory -Path $cache | Out-Null; $arguments += @("--cache-dir", $cache) }
    if ($UseCache) { $request | & $gateway @arguments | Out-Null }
    $times = @()
    $lastOutput = ""
    for ($index = 0; $index -lt $Repeats; $index++) {
        $output = ""
        $elapsed = Measure-Command { $output = ($request | & $gateway @arguments | Out-String).Trim() }
        $times += $elapsed.TotalMilliseconds
        $lastOutput = $output
    }
    Remove-Item $cache -Recurse -Force -ErrorAction SilentlyContinue
    $ordered = $times | Sort-Object
    [PSCustomObject]@{
        Runtime = $Name
        MedianMilliseconds = [Math]::Round($ordered[[int][Math]::Floor($ordered.Count / 2)], 2)
        Samples = (($times | ForEach-Object { [Math]::Round($_, 2) }) -join ", ")
        Checksum = $lastOutput
    }
}

@(
    Measure-Runner "C native" { & $native $source }
    Measure-Runner "Python reference" { & $python -m separan $source }
    Measure-Gateway "Gateway CPU no cache" $gatewaySource '{"method":"GET","path":"/bench"}' $false
    Measure-Gateway "Gateway CPU warm cache" $gatewaySource '{"method":"GET","path":"/bench"}' $true
    Measure-Gateway "Gateway startup no cache" $cacheSource '{"method":"GET","path":"/cache/1"}' $false
    Measure-Gateway "Gateway startup warm cache" $cacheSource '{"method":"GET","path":"/cache/1"}' $true
) | Format-Table -AutoSize
