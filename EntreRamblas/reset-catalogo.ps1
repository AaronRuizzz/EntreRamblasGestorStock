# Deja el catálogo a cero antes de una entrega. Conserva toda la configuración.
# El servidor Odoo debe estar PARADO.
param(
    [ValidatePattern('^[a-z][a-z0-9_]{0,62}$')][string]$Database = 'mi_base_stock',
    [string]$Config = (Join-Path $PSScriptRoot 'odoo.local'),
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "No se encuentra el entorno virtual: $python" }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'No existe el archivo de configuración indicado.' }
$resetArgs = @((Join-Path $PSScriptRoot 'tools\reset_catalog.py'),
    '-c', (Resolve-Path -LiteralPath $Config).Path, '-d', $Database)
if ($Yes) { $resetArgs += '--yes' }
& $python @resetArgs
if ($LASTEXITCODE -ne 0) { throw "El vaciado no se ha completado (código $LASTEXITCODE)." }
