<#
    Vuelca el diagnóstico de la instalación a un JSON, sin secretos, para
    comparar dos equipos (versión, motor, configuración común, módulos).

        .\diagnostico.ps1 -Config "<ruta a odoo.local>" -Database <base>
#>
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'entre_ramblas',
    [string]$Salida
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe el archivo de configuración indicado.' }
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "No se encuentra el entorno virtual: $python" }

$argv = @((Join-Path $PSScriptRoot 'tools\diagnostico.py'), '--config', $Config, '--database', $Database)
if ($Salida) { $argv += @('--salida', $Salida) }
& $python @argv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el diagnóstico.' }
