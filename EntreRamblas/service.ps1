param(
    [Parameter(Mandatory=$true)][ValidateSet('install','start','stop','remove','status')][string]$Action,
    [string]$Name = 'EntreRamblasOdoo',
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local'),
    [string]$Database = 'entre_ramblas',
    [string]$PostgreSQLService = ''
)
$ErrorActionPreference = 'Stop'
$serviceArgs = @((Join-Path $PSScriptRoot 'tools/windows_service.py'), $Action.ToLowerInvariant(),
    '--name', $Name, '--config', $Config, '--database', $Database)
if ($PostgreSQLService) { $serviceArgs += @('--postgres-service', $PostgreSQLService) }
& (Join-Path $PSScriptRoot 'venv/Scripts/python.exe') @serviceArgs
if ($LASTEXITCODE -ne 0) { throw "No se ha completado la operación del servicio (código $LASTEXITCODE)." }
