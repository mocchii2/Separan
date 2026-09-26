[CmdletBinding()]
param(
    [string]$PostgresBin = "C:\PostgreSQL\18\bin",
    [ValidateRange(1024, 65535)]
    [int]$Port = 55432,
    [string]$Pytest = "pytest"
)

$prefix = "SEPARAN_TEST_POSTGRESQL_"
$keys = @("HOST", "PORT", "DATABASE", "USER", "PASSWORD")
$previous = @{}
$dataDirectory = Join-Path $env:TEMP ("separan-postgres-it-" + [guid]::NewGuid().ToString("N"))
$logPath = Join-Path $env:TEMP ("separan-postgres-it-" + [guid]::NewGuid().ToString("N") + ".log")
$serverStarted = $false
$testExitCode = 1

try {
    Push-Location (Join-Path $PSScriptRoot "..")
    foreach ($key in $keys) {
        $name = $prefix + $key
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    foreach ($tool in @("initdb.exe", "pg_ctl.exe", "psql.exe")) {
        if (-not (Test-Path (Join-Path $PostgresBin $tool))) {
            throw "Required PostgreSQL tool was not found: $tool"
        }
    }

    & (Join-Path $PostgresBin "initdb.exe") -D $dataDirectory -U postgres --auth-local=trust --auth-host=trust --no-instructions
    if ($LASTEXITCODE -ne 0) {
        throw "Could not initialize the disposable PostgreSQL test cluster."
    }

    & (Join-Path $PostgresBin "pg_ctl.exe") -D $dataDirectory -l $logPath -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start the disposable PostgreSQL test cluster."
    }
    $serverStarted = $true

    & (Join-Path $PostgresBin "psql.exe") -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $Port -U postgres -d postgres -c "CREATE ROLE separan LOGIN"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the disposable PostgreSQL test role."
    }
    & (Join-Path $PostgresBin "psql.exe") -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $Port -U postgres -d postgres -c "CREATE DATABASE separan OWNER separan"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the disposable PostgreSQL test database."
    }

    $randomBytes = [byte[]]::new(24)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $placeholderPassword = -join ($randomBytes | ForEach-Object { $_.ToString("x2") })

    [Environment]::SetEnvironmentVariable($prefix + "HOST", "127.0.0.1", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PORT", "$Port", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "DATABASE", "separan", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "USER", "separan", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PASSWORD", $placeholderPassword, "Process")

    Write-Host "Running PostgreSQL integration test on loopback port $Port with a disposable cluster."
    & $Pytest -q tests/test_database_integration.py::ExternalDatabaseIntegrationTests::test_postgresql_real_server
    $testExitCode = $LASTEXITCODE
}
finally {
    foreach ($key in $keys) {
        $name = $prefix + $key
        [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
    }
    $placeholderPassword = $null
    $randomBytes = $null

    if ($serverStarted) {
        & (Join-Path $PostgresBin "pg_ctl.exe") -D $dataDirectory -m fast -w stop | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "The disposable PostgreSQL server did not stop cleanly."
            $testExitCode = 1
        }
    }
    if (Test-Path $dataDirectory) {
        Remove-Item $dataDirectory -Recurse -Force
    }
    if (Test-Path $logPath) {
        Remove-Item $logPath -Force
    }
    Pop-Location
}

exit $testExitCode