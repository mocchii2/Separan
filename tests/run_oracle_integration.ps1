[CmdletBinding()]
param(
    [string]$HostName = "host.docker.internal",
    [ValidateRange(1, 65535)]
    [int]$Port = 1521,
    [string]$Database = "FREEPDB1",
    [string]$SqlPlus = "C:\Oracle\product\26ai\dbhomeFree\bin\sqlplus.exe",
    [string]$Pytest = "pytest"
)

$prefix = "SEPARAN_TEST_ORACLE_"
$keys = @("HOST", "PORT", "DATABASE", "USER", "PASSWORD")
$previous = @{}
$userProvisionAttempted = $false
$testExitCode = 1

try {
    Push-Location (Join-Path $PSScriptRoot "..")
    foreach ($key in $keys) {
        $name = $prefix + $key
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    if (-not (Test-Path $SqlPlus)) {
        throw "sqlplus.exe was not found at the configured Oracle client path."
    }

    $randomBytes = [byte[]]::new(16)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $suffix = -join ($randomBytes | ForEach-Object { $_.ToString("x2") })
    $testUser = "SEPIT_$($suffix.Substring(0, 12))"
    $testPassword = -join ($randomBytes | ForEach-Object { $_.ToString("x2") })

    $setupSql = @"
whenever sqlerror exit sql.sqlcode
alter session set container=$Database;
create user $testUser identified by "$testPassword";
grant create session, create table to $testUser;
alter user $testUser quota 100M on USERS;
exit success
"@
    $userProvisionAttempted = $true
    $null = $setupSql | & $SqlPlus -L -S "/ as sysdba" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not provision the temporary Oracle test user through local OS authentication."
    }

    [Environment]::SetEnvironmentVariable($prefix + "HOST", $HostName, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PORT", "$Port", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "DATABASE", $Database, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "USER", $testUser, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PASSWORD", $testPassword, "Process")

    Write-Host "Running Oracle integration test at $HostName`:$Port ($Database) with a temporary user."
    & $Pytest -q tests/test_database_integration.py::ExternalDatabaseIntegrationTests::test_oracle_real_server
    $testExitCode = $LASTEXITCODE
}
finally {
    if ($userProvisionAttempted) {
        $cleanupSql = @"
whenever sqlerror exit sql.sqlcode
alter session set container=$Database;
begin
    execute immediate 'drop user $testUser cascade';
exception
    when others then
        if sqlcode != -1918 then raise; end if;
end;
/
exit success
"@
        $null = $cleanupSql | & $SqlPlus -L -S "/ as sysdba" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Temporary Oracle test user cleanup failed; inspect local Oracle users for the generated SEPIT account."
            $testExitCode = 1
        }
    }
    foreach ($key in $keys) {
        $name = $prefix + $key
        [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
    }
    $testPassword = $null
    $setupSql = $null
    $cleanupSql = $null
    $randomBytes = $null
    Pop-Location
}

exit $testExitCode