[CmdletBinding()]
param(
    [string]$HostName = "192.168.11.245",
    [ValidateRange(1, 65535)]
    [int]$Port = 3306,
    [string]$Database = "separan",
    [string]$User = "separan",
    [string]$Pytest = "pytest"
)

$prefix = "SEPARAN_TEST_MYSQL_"
$keys = @("HOST", "PORT", "DATABASE", "USER", "PASSWORD")
$previous = @{}
$securePassword = $null
$passwordPointer = [IntPtr]::Zero
$plainPassword = $null
$testExitCode = 1

try {
    Push-Location (Join-Path $PSScriptRoot "..")
    foreach ($key in $keys) {
        $name = $prefix + $key
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    $securePassword = Read-Host -Prompt "MySQL password for $User@$HostName" -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if ([string]::IsNullOrEmpty($plainPassword)) {
        throw "A non-empty MySQL password is required."
    }

    [Environment]::SetEnvironmentVariable($prefix + "HOST", $HostName, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PORT", "$Port", "Process")
    [Environment]::SetEnvironmentVariable($prefix + "DATABASE", $Database, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "USER", $User, "Process")
    [Environment]::SetEnvironmentVariable($prefix + "PASSWORD", $plainPassword, "Process")

    Write-Host "Running MySQL integration test at $HostName`:$Port ($Database)."
    & $Pytest -q tests/test_database_integration.py::ExternalDatabaseIntegrationTests::test_mysql_real_server
    $testExitCode = $LASTEXITCODE
}
finally {
    foreach ($key in $keys) {
        $name = $prefix + $key
        [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
    }
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    if ($securePassword) {
        $securePassword.Dispose()
    }
    $plainPassword = $null
    Pop-Location
}

exit $testExitCode