# AST sanity check for a PowerShell script. Reports parse errors without
# executing the script. Useful for verifying MFD-fix scripts before
# shipping in a release zip.
#
# Usage:
#   pwsh -File check-ps1-syntax.ps1 "<path to .ps1>"

param([Parameter(Mandatory=$true)][string]$Path)

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "File not found: $Path" -ForegroundColor Red
    exit 1
}

$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null

if ($errors.Count -gt 0) {
    foreach ($e in $errors) {
        Write-Host "Line $($e.Extent.StartLineNumber): $($e.Message)" -ForegroundColor Red
    }
    exit 1
}

Write-Host "OK -- script parses cleanly." -ForegroundColor Green
exit 0
