# Recupera en una base nueva. La original no se elimina ni se reemplaza.
param(
    [Parameter(Mandatory=$true)][string]$Archivo,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database,
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local'),
    [switch]$AllowLegacy
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) { throw 'No existe la copia indicada.' }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe la configuración indicada.' }
$restoreArgs = @((Join-Path $PSScriptRoot 'tools\restore_backup.py'),
    (Resolve-Path -LiteralPath $Archivo).Path, '-d', $Database, '-c', (Resolve-Path -LiteralPath $Config).Path)
if ($AllowLegacy) { $restoreArgs += '--allow-legacy' }
& $python @restoreArgs
if ($LASTEXITCODE -ne 0) { throw "La restauración no se ha completado (código $LASTEXITCODE). La base original se conserva." }
